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

from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_sdk.contracts.context import BoundRuntimeContext
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage

from fred_runtime.support.thinking import thread_reasoning_within_open_turn
from fred_runtime.support.tool_loop import (
    ChatTurnTooLargeError,
    collect_tool_outputs,
    sanitize_dangling_tool_calls,
    total_char_len,
    trim_to_char_budget,
    trim_to_human_boundary,
)

from .shared import identity_kpi_dims, state_messages

logger = logging.getLogger(__name__)


class CheckpointHygieneMiddleware(AgentMiddleware):
    """
    Request-scoped message hygiene for every model call (legacy `reasoner` prep).

    Why this exists:
    - poisoned checkpoints (dangling tool calls from crashed turns) make OpenAI
      reject the payload with HTTP 400; unbounded history contaminates queries
    - raw provider reasoning blocks must never be replayed as such (the model
      client drops them anyway); the open turn's reasoning is instead carried
      back as text, see `thread_reasoning_within_open_turn`
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
        # Reasoning continuity (RUNTIME-05 Layer 2c, RFC Amendment E §E.3).
        # Provider-native reasoning blocks cannot be replayed as such — the model
        # client drops them — so the reasoning of the turn IN PROGRESS is carried
        # back as ordinary text and reasoning from closed turns is dropped.
        # Without this the model gets its own message back with the content
        # emptied, re-derives the plan, and re-issues the identical tool call:
        # measured 9/12 turns and 67 duplicate calls on a bare prompt, 0/12 with
        # this (p = 1.7e-4). Raw reasoning blocks are still never replayed.
        #
        # Must run BEFORE the size budget below (found in PR review): a
        # `thinking` block's own text isn't counted by `_message_char_len`
        # (it's structured reasoning content, not the plain `content` string
        # or a tool-call argument) until this call flattens it into ordinary
        # text. Budgeting first would measure the pre-flatten shape and miss
        # however large the rehomed reasoning trace turns out to be — the
        # budget must see what the handler will actually receive.
        messages = thread_reasoning_within_open_turn(messages)
        if self._max_history_chars is not None:
            # Message-count trim above says nothing about payload size: a
            # handful of large tool outputs (a generated document, a big RAG
            # hit) can stay far under the message cap while blowing past a
            # provider's real context window (#2350 field evidence: ~60
            # messages, 178k+ tokens). Trim again, this time by size.
            trimmed = trim_to_char_budget(messages, self._max_history_chars)
            if not trimmed and messages:
                # `trim_to_char_budget` can legitimately collapse to `[]`
                # when the only message it could keep under budget is a lone
                # trailing ToolMessage with no preceding AIMessage in the
                # window — an unsafe orphan boundary (e.g. one oversized RAG
                # result). `total_char_len([])` is then 0, which would
                # silently pass the check below and send the model an EMPTY
                # context — no user question, no tool result — instead of
                # failing the turn (found in PR review). Treat the collapse
                # itself as the over-budget signal: measure the pre-trim
                # total instead, guaranteed > budget since
                # `trim_to_char_budget` only trims when that already holds.
                actual_chars = total_char_len(messages)
            else:
                actual_chars = total_char_len(trimmed)
            if actual_chars > self._max_history_chars:
                # Even the trimmed window is too big: the CURRENT turn's own
                # content is the culprit, and no amount of dropping older
                # history can fix that. Fail the turn cleanly here rather
                # than forward a payload the provider will reject anyway.
                #
                # Both a log AND a counter, not just one: the log is the
                # per-occurrence detail for OpenSearch/incident digging; the
                # counter (`agent.turn_rejected_total`, same shape as the
                # sibling `agent.tool_failed_total` in
                # `ToolObservabilityMiddleware`) is what actually reaches
                # Grafana, since this middleware has no paired latency timer
                # to piggyback a `status` dim on. Whether
                # `_V2_MAX_HISTORY_CHARS` (calibrated off one field incident,
                # #2350) is well-tuned is exactly what this counter is for —
                # silent-by-default would hide that until a user complains
                # again. Numbers/identifiers only in both: no message
                # content, nothing GDPR-sensitive (`identity_kpi_dims` never
                # carries content, only opaque correlation identifiers, and
                # only the Prometheus-allow-listed subset of those ever
                # reaches Grafana — see `PROMETHEUS_ALLOWED_LABELS`).
                logger.warning(
                    "[TOOL LOOP] turn rejected: content too large even after "
                    "trim (%d chars > %d char budget)",
                    actual_chars,
                    self._max_history_chars,
                )
                if self._kpi is not None:
                    self._kpi.count(
                        "agent.turn_rejected_total",
                        1,
                        dims={
                            **identity_kpi_dims(self._binding),
                            "status": "error",
                            "error_code": ChatTurnTooLargeError.__name__,
                            "exception_type": ChatTurnTooLargeError.__name__,
                        },
                        actor=KPIActor(type="system"),
                    )
                raise ChatTurnTooLargeError(
                    limit_chars=self._max_history_chars,
                    actual_chars=actual_chars,
                )
            if len(trimmed) != len(messages):
                logger.debug(
                    "[TOOL LOOP] history trimmed by size: %d → %d chars "
                    "(max_history_chars=%d)",
                    total_char_len(messages),
                    actual_chars,
                    self._max_history_chars,
                )
                messages = sanitize_dangling_tool_calls(trimmed)
        response = await handler(
            request.override(messages=cast(list[AnyMessage], messages))
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
