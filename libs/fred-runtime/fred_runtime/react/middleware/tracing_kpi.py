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

"""TracingKpiMiddleware — model-call span, latency KPI, and call/response logs (#1972)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from typing import cast

from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.runtime import SpanPort, TracerPort
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from fred_runtime.runtime_support.model_metadata import runtime_metadata_from_message
from fred_runtime.runtime_support.trace_payloads import (
    final_assistant_message,
    serialize_messages,
    serialize_model_output,
    to_langfuse_usage,
)

from ..react_model_adapter import (
    TRACE_MODEL_SPAN_NAME,
    extract_model_name_from_model_response,
    extract_model_name_from_object,
)

logger = logging.getLogger(__name__)


class TracingKpiMiddleware(AgentMiddleware):
    """
    Model-call span, latency KPI, and call/response logs (legacy `_wrap`).

    Why this exists:
    - Fred tracing tags each model call with a `v2.react.model` span (model
      name) nested under the active agent span; KPI records
      `llm.call_latency_ms`; `[LLM][CALL]`/`[LLM][RESPONSE]` logs describe the
      exact request/response
    - this middleware is the INNERMOST `wrap_model_call` of the platform frame
      so span/KPI/log measure the bare model call, exactly as the legacy
      `reasoner` node wrapped only `model.ainvoke(...)`

    How to use:
    - always part of the frame; span/KPI are no-ops when tracer/kpi are None,
      the logs are emitted unconditionally (legacy behavior)
    """

    def __init__(
        self,
        *,
        tracer: TracerPort | None,
        kpi: BaseKPIWriter | None,
        binding: BoundRuntimeContext,
    ) -> None:
        super().__init__()
        self._tracer = tracer
        self._kpi = kpi
        self._binding = binding

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        model_name = extract_model_name_from_object(request.model)
        self._log_model_call(request)

        span = None
        if self._tracer is not None:
            attributes: dict[str, object] = {}
            if model_name is not None:
                attributes["model_name"] = model_name
            from ..react_tracing import active_agent_span

            span = self._tracer.start_span(
                name=TRACE_MODEL_SPAN_NAME,
                context=self._binding.portable_context,
                attributes=cast(dict[str, str | int | float | bool | None], attributes),
                parent=active_agent_span.get(),
            )
            # Serializing a full transcript is real work on the per-turn hot
            # path, so it happens only when a backend will actually store it.
            if self._tracer.captures_content:
                span.set_io(
                    input=serialize_messages(
                        list(request.messages),
                        system_prompt=request.system_prompt,
                    )
                )

        kpi_dims: dict[str, str | None] = {
            "agent_id": self._binding.portable_context.agent_name
            or self._binding.portable_context.agent_id,
        }
        if model_name is not None:
            kpi_dims["model_name"] = model_name

        kpi_ctx = (
            self._kpi.timer(
                "llm.call_latency_ms", dims=kpi_dims, actor=KPIActor(type="system")
            )
            if self._kpi is not None
            else None
        )
        # Use the timer as a sync context manager (allowed inside async
        # functions). _TimerImpl.__exit__ receives exc_type so
        # status=error/cancelled is set automatically on failure.
        with kpi_ctx if kpi_ctx is not None else nullcontext():
            try:
                response = await handler(request)
                if span is not None:
                    span.set_attribute("status", "ok")
                    response_model_name = extract_model_name_from_model_response(
                        response
                    )
                    if response_model_name is not None:
                        span.set_attribute("model_name", response_model_name)
                    self._record_model_response(
                        span, response, model_name=response_model_name or model_name
                    )
                self._log_model_response(response)
                return response
            except Exception:
                if span is not None:
                    span.set_attribute("status", "error")
                raise
            finally:
                if span is not None:
                    span.end()

    def _record_model_response(
        self,
        span: SpanPort,
        response: ModelResponse,
        *,
        model_name: str | None,
    ) -> None:
        """
        Attach the answer and the token accounting to the model-call span.

        Why this exists:
        - token counts and cost per call are the whole point of tracing an LLM
          call; without `set_usage` a tracing backend can only show latency
        - usage is technical measurement, so it is always recorded; the answer
          text is content and follows `captures_content` (§7)

        How to use:
        - called once per successful model call, before the span ends
        """

        messages = [
            message for message in response.result if isinstance(message, BaseMessage)
        ]
        if not messages:
            return

        assistant_message = final_assistant_message(messages)
        if assistant_message is not None:
            _, token_usage, finish_reason = runtime_metadata_from_message(
                assistant_message
            )
            usage = to_langfuse_usage(token_usage)
            if usage is not None or model_name is not None:
                span.set_usage(model=model_name, usage=usage)
            if finish_reason is not None:
                span.set_attribute("finish_reason", str(finish_reason))

        if self._tracer is not None and self._tracer.captures_content:
            span.set_io(output=serialize_model_output(messages))

    @staticmethod
    def _log_model_call(request: ModelRequest) -> None:
        # Never log message/question content here — this logger feeds the
        # generic app-log store (see docs/swift/platform/OBSERVABILITY-AND-AUDIT.md
        # §7: "Content ... Nowhere in any observability or audit stream").
        # Lengths and counts only.
        messages = list(request.messages)
        sys_text = request.system_prompt or ""
        tail = ", ".join(
            f"{type(m).__name__[0]}:{len(str(m.content))}c" for m in messages[-6:]
        )
        last_human_len = next(
            (
                len(m.content) if isinstance(m.content, str) else len(str(m.content))
                for m in reversed(messages)
                if isinstance(m, HumanMessage)
            ),
            None,
        )
        logger.info(
            "[LLM][CALL] sys=%dc total_msgs=%d hist_tail=[%s] question_len=%s",
            len(sys_text),
            len(messages) + (1 if request.system_message is not None else 0),
            tail,
            last_human_len,
        )

    @staticmethod
    def _log_model_response(response: ModelResponse) -> None:
        # Same rule as _log_model_call: no tool-argument values, no answer
        # text — names, keys, and lengths only.
        ai_message = next(
            (m for m in reversed(response.result) if isinstance(m, AIMessage)),
            None,
        )
        if ai_message is None:
            return
        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if tool_calls:
            logger.info(
                "[LLM][RESPONSE] tool_calls=%s",
                [
                    {
                        "name": tc.get("name")
                        if isinstance(tc, dict)
                        else getattr(tc, "name", "?"),
                        "arg_keys": list(
                            (tc.get("args") or {}) if isinstance(tc, dict) else {}
                        ),
                    }
                    for tc in tool_calls
                ],
            )
        else:
            text = (
                ai_message.content
                if isinstance(ai_message.content, str)
                else str(ai_message.content)
            )
            logger.info(
                "[LLM][RESPONSE] final answer_len=%d",
                len(text),
            )
