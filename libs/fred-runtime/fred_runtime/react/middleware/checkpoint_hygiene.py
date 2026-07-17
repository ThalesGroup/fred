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

"""CheckpointHygieneMiddleware — request-scoped model-input hygiene (#1972)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage

from fred_runtime.support.thinking import strip_reasoning_from_history
from fred_runtime.support.tool_loop import (
    collect_tool_outputs,
    sanitize_dangling_tool_calls,
    trim_to_human_boundary,
)

from .shared import state_messages

logger = logging.getLogger(__name__)


class CheckpointHygieneMiddleware(AgentMiddleware):
    """
    Request-scoped message hygiene for every model call (legacy `reasoner` prep).

    Why this exists:
    - poisoned checkpoints (dangling tool calls from crashed turns) make OpenAI
      reject the payload with HTTP 400; replayed reasoning blocks make Mistral
      reject with HTTP 422; unbounded history contaminates queries
    - the legacy loop applied sanitize → trim → reasoning-strip to the MODEL
      INPUT only, never to the persisted checkpoint — so this must be a
      `wrap_model_call` request override, NOT a `before_model` state update
      (state updates would rewrite the checkpoint and destroy history)

    How to use:
    - first middleware of the platform frame; nothing may see an unsanitized
      model request
    """

    def __init__(self, *, max_history_messages: int | None) -> None:
        super().__init__()
        self._max_history_messages = max_history_messages

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        messages = sanitize_dangling_tool_calls(list(request.messages))
        if self._max_history_messages is not None:
            trimmed = trim_to_human_boundary(messages, self._max_history_messages)
            logger.debug(
                "[TOOL LOOP] history trimmed: %d → %d messages (max_history_messages=%d)",
                len(messages),
                len(trimmed),
                self._max_history_messages,
            )
            # Trimming can itself cut a pair in half (no HumanMessage boundary
            # found inside the trimmed window falls back to a raw slice) and
            # front the result with an orphaned ToolMessage sanitize never saw —
            # it already ran on the untrimmed list above. Re-run it: idempotent
            # on an already-clean list, closes the gap on a freshly-cut one.
            messages = sanitize_dangling_tool_calls(trimmed)
        # Strip provider-native reasoning from replayed assistant messages
        # (RUNTIME-05 Layer 2c): reasoning-capable models (Mistral via the
        # OpenAI-compatible client, Claude extended thinking) leave reasoning
        # blocks in the checkpointed AIMessage. Replaying them makes Mistral
        # reject the request (HTTP 422) and pollutes context. The reasoning was
        # already surfaced to the UI as THOUGHT_* events.
        messages = strip_reasoning_from_history(messages)
        response = await handler(
            request.override(messages=cast("list[AnyMessage]", messages))
        )
        self._attach_tool_outputs(response, request)
        return response

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
