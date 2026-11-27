# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CheckpointHygieneMiddleware — request-scoped model-input hygiene."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import NoReturn, cast

from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_sdk.contracts.context import BoundRuntimeContext
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage

from fred_runtime.support.reasoning_replay import replays_native_reasoning
from fred_runtime.support.thinking import (
    keep_native_reasoning,
    thread_reasoning_within_open_turn,
)
from fred_runtime.support.tool_loop import (
    ChatTurnTooLargeError,
    ChatTurnTooManyMessagesError,
    collect_tool_outputs,
    compact_history_to_budget,
    sanitize_dangling_tool_calls,
    strip_message_names,
    total_char_len,
)

from .shared import identity_kpi_dims, state_messages

logger = logging.getLogger(__name__)


class CheckpointHygieneMiddleware(AgentMiddleware):
    """
    Request-scoped message hygiene for every model call (legacy `reasoner` prep).

    Why this exists:
    - poisoned checkpoints (dangling tool calls from crashed turns) make OpenAI
      reject the payload with HTTP 400; unbounded history contaminates queries
    - raw provider reasoning blocks are not replayed as such (the model client
      drops them); the open turn's reasoning is instead carried back as text,
      see `thread_reasoning_within_open_turn`. Mistral is the exception: it
      gets every turn's reasoning back natively, see `keep_native_reasoning`
    - the legacy loop applied sanitize → trim → reasoning handling to the MODEL
      INPUT only, never to the persisted checkpoint — so this must be a
      `wrap_model_call` request override, NOT a `before_model` state update
      (state updates would rewrite the checkpoint and destroy history)

    How to use:
    - first middleware of the platform frame; nothing may see an unsanitized
      model request
    """

    def __init__(
        self,
        *,
        max_history_messages: int | None,
        binding: BoundRuntimeContext,
        kpi: BaseKPIWriter | None,
        max_history_chars: int | None = None,
    ) -> None:
        super().__init__()
        self._max_history_messages = max_history_messages
        self._max_history_chars = max_history_chars
        self._binding = binding
        self._kpi = kpi

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        messages = strip_message_names(
            sanitize_dangling_tool_calls(list(request.messages))
        )
        if self._max_history_messages is not None:
            compacted = compact_history_to_budget(
                messages,
                self._max_history_messages,
                len,
                max_completed_turns=max(1, self._max_history_messages // 2),
            )
            if len(compacted) > self._max_history_messages:
                self._record_budget_rejection(
                    ChatTurnTooManyMessagesError(
                        limit_messages=self._max_history_messages,
                        actual_messages=len(compacted),
                    )
                )
            messages = compacted
        # Reasoning continuity: without it the model re-issues its last call.
        # Count trimming first avoids rewriting history that will be dropped.
        if replays_native_reasoning(request.model):
            messages = keep_native_reasoning(messages)
        else:
            messages = thread_reasoning_within_open_turn(messages)
        if self._max_history_chars is not None:
            compacted = compact_history_to_budget(
                messages, self._max_history_chars, total_char_len
            )
            actual_chars = total_char_len(compacted)
            if actual_chars > self._max_history_chars:
                self._record_budget_rejection(
                    ChatTurnTooLargeError(
                        limit_chars=self._max_history_chars,
                        actual_chars=actual_chars,
                    )
                )
            messages = compacted
        response = await handler(
            request.override(messages=cast(list[AnyMessage], messages))
        )
        self._attach_tool_outputs(response, request)
        return response

    def _record_budget_rejection(self, error: RuntimeError) -> NoReturn:
        logger.warning("[TOOL LOOP] model input rejected: %s", error)
        if self._kpi is not None:
            self._kpi.count(
                "agent.turn_rejected_total",
                1,
                dims={
                    **identity_kpi_dims(self._binding),
                    "status": "error",
                    "error_code": type(error).__name__,
                    "exception_type": type(error).__name__,
                },
                actor=KPIActor(type="system"),
            )
        raise error

    @staticmethod
    def _attach_tool_outputs(response: ModelResponse, request: ModelRequest) -> None:
        """
        Attach the latest tool outputs to the response metadata (legacy behavior).

        Why this exists:
        - the legacy `reasoner` node recorded the latest ToolMessage payload per
          tool name under `response_metadata["tools"]`; re-homed unchanged
        """

        ai_message = next(
            (m for m in reversed(response.result) if isinstance(m, AIMessage)),
            None,
        )
        if ai_message is None:
            return
        tool_payloads = collect_tool_outputs(state_messages(request.state))
        md = getattr(ai_message, "response_metadata", {}) or {}
        tools_md = md.get("tools", {}) or {}
        tools_md.update(tool_payloads)
        md["tools"] = tools_md
        ai_message.response_metadata = md
