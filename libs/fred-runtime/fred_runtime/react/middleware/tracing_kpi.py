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

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import UUID

from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_core.kpi.kpi_writer_structures import Dims, MetricNames
from fred_core.model.diagnostics import active_model_http, effective_model_settings
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.runtime import SpanPort, TracerPort
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables.config import (
    ensure_config,
    merge_configs,
    set_config_context,
)

from fred_runtime.common.outbound_credentials import delegation_enabled
from fred_runtime.runtime_support.llm_diagnostics import (
    LlmObservation,
    LlmProgressCallback,
    Scalar,
    attach_failure,
    change_active,
    classify_error,
    streaming_selection,
)
from fred_runtime.runtime_support.model_metadata import runtime_metadata_from_message
from fred_runtime.runtime_support.trace_payloads import (
    final_assistant_message,
    model_request_char_sizes,
    serialize_model_output,
    serialize_model_request,
    to_langfuse_usage,
)

from ..react_model_adapter import (
    TRACE_MODEL_SPAN_NAME,
    extract_model_name_from_model_response,
    extract_model_name_from_object,
)

logger = logging.getLogger(__name__)


class _ModelInputCallback(LlmProgressCallback):
    """Capture post-middleware model input on this invocation's existing span."""

    def __init__(
        self, observation: LlmObservation, span: SpanPort, *, captures_content: bool
    ) -> None:
        super().__init__(observation)
        self._span = span
        self._captures_content = captures_content

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],  # opaque: LangChain callback metadata
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,  # opaque: provider invocation parameters from LangChain
    ) -> None:
        """Record final messages/tools while preserving progress and model timings."""

        super().on_chat_model_start(
            serialized, messages, run_id=run_id, parent_run_id=parent_run_id, **kwargs
        )
        # Downstream middleware can still replace the request; callbacks see
        # the final messages and bound tools without retaining their content.
        started = time.monotonic()
        try:
            with suppress(Exception):
                final_messages = messages[0]
                tools = (kwargs.get("invocation_params") or {}).get("tools") or []
                sizes = model_request_char_sizes(final_messages, tools=tools)
                sizes["chars_system"] = model_request_char_sizes(
                    [message for message in final_messages if message.type == "system"]
                )["chars_messages"]
                sizes["chars_messages"] -= sizes["chars_system"]
                for key, value in sizes.items():
                    self._span.set_attribute(key, value)
                if self._captures_content:
                    self._span.set_io(
                        input=serialize_model_request(final_messages, tools=tools)
                    )
        finally:
            # Keep trace preparation outside the measured model-call interval.
            self.observation.http.started += time.monotonic() - started


class TracingKpiMiddleware(AgentMiddleware):
    """Measure the shared model boundary without capturing streaming content."""

    def __init__(
        self,
        *,
        tracer: TracerPort | None,
        kpi: BaseKPIWriter | None,
        binding: BoundRuntimeContext,
        role: str = "root",
    ) -> None:
        super().__init__()
        self._tracer = tracer
        self._kpi = kpi
        self._binding = binding
        self._role = "child" if role == "child" else "root"

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        model_name = extract_model_name_from_object(request.model) or "unknown"
        sizes: dict[str, int] = {}
        settings = effective_model_settings(request.model)
        streaming = streaming_selection(
            request.model, request.model_settings, has_tools=bool(request.tools)
        )
        observation = LlmObservation(
            model=model_name,
            role=self._role,
            streaming=streaming,
        )
        observation.http.allow_request_ids = not delegation_enabled()
        token = active_model_http.set(observation.http)
        span: SpanPort | None = None
        captures_content = False
        outcome = "ok"
        error_fields: dict[str, Scalar] = {"error_code": "none"}
        response_fields: dict[str, Scalar] = {}
        response_model_name: str | None = None
        handler_ended: float | None = None
        dims: Dims = {"model_name": model_name, "llm_role": self._role}
        active = change_active(model_name, self._role, 1)
        try:
            with suppress(Exception):
                sizes = model_request_char_sizes(
                    request.messages,
                    system_prompt=request.system_prompt,
                    tools=request.tools,
                )
                logger.info(
                    "event=llm_call_started llm_call_id=%s model=%s role=%s settings=%s sizes=%s",
                    observation.call_id,
                    model_name,
                    self._role,
                    settings,
                    sizes,
                    extra={
                        "llm_call_id": observation.call_id,
                        "model_name": model_name,
                        "llm_role": self._role,
                        **sizes,
                        "message_count": len(request.messages),
                        "tool_count": len(request.tools),
                    },
                )
                self._log_model_call(request)
            if self._kpi is not None:
                with suppress(Exception):
                    self._kpi.gauge(
                        MetricNames.LLM_ACTIVE_CALLS,
                        active,
                        dims=dims,
                        actor=KPIActor(type="system"),
                    )
            if self._tracer is not None:
                with suppress(Exception):
                    from ..react_tracing import active_agent_span

                    span = self._tracer.start_span(
                        name=TRACE_MODEL_SPAN_NAME,
                        context=self._binding.portable_context,
                        attributes={
                            "model_name": model_name,
                            "llm_call_id": observation.call_id,
                            "llm_role": self._role,
                        },
                        parent=active_agent_span.get(),
                    )
                    for key, value in sizes.items():
                        span.set_attribute(key, value)
                    captures_content = self._tracer.captures_content
            callback = (
                _ModelInputCallback(
                    observation,
                    span,
                    captures_content=captures_content,
                )
                if span is not None
                else LlmProgressCallback(observation)
            )
            config = merge_configs(ensure_config(), {"callbacks": [callback]})

            async def invoke_model() -> ModelResponse:
                nonlocal handler_ended
                # Exclude telemetry setup/teardown from model boundary timings.
                observation.http.started = time.monotonic()
                try:
                    return await handler(request)
                finally:
                    handler_ended = time.monotonic()

            with set_config_context(config) as context:
                response = await asyncio.create_task(invoke_model(), context=context)
            with suppress(Exception):
                if span is not None:
                    response_model_name = (
                        extract_model_name_from_model_response(response) or model_name
                    )
                    span.set_attribute("model_name", response_model_name)
                    self._record_model_response(
                        span, response, model_name=response_model_name
                    )
                self._log_model_response(response)
                message = final_assistant_message(response.result)
                if message is not None:
                    _, usage, reason = runtime_metadata_from_message(message)
                    response_fields["usage_available"] = usage is not None
                    if usage is not None:
                        for key in ("input_tokens", "output_tokens", "total_tokens"):
                            if key in usage:
                                response_fields[key] = usage[key]
                    if reason is not None:
                        response_fields["finish_reason"] = str(reason)
            return response
        except BaseException as exc:
            outcome = (
                "cancelled" if isinstance(exc, asyncio.CancelledError) else "error"
            )
            error_fields = classify_error(exc)
            if error_fields["error_code"] == "stream_idle_timeout":
                observation.streaming = True
            with suppress(Exception):
                attach_failure(
                    exc,
                    {
                        **observation.fields(at=handler_ended),
                        "status": outcome,
                        **error_fields,
                    },
                )
            raise
        finally:
            active_model_http.reset(token)
            active = change_active(model_name, self._role, -1)
            fields = {
                **observation.fields(at=handler_ended),
                **response_fields,
                "status": outcome,
                **error_fields,
            }
            with suppress(Exception):
                logger.log(
                    logging.WARNING if outcome == "error" else logging.INFO,
                    "event=llm_call_completed diagnostics=%s",
                    fields,
                    extra=fields,
                )
            if span is not None:
                with suppress(Exception):
                    for key, value in fields.items():
                        if key == "model_name" and response_model_name is not None:
                            value = response_model_name
                        span.set_attribute(key, value)
                with suppress(Exception):
                    span.end()
            if self._kpi is not None:
                actor = KPIActor(type="system")
                with suppress(Exception):
                    self._kpi.gauge(
                        MetricNames.LLM_ACTIVE_CALLS, active, dims=dims, actor=actor
                    )
                terminal_dims: Dims = {
                    **dims,
                    "status": outcome,
                    "error_code": str(error_fields["error_code"]),
                }
                with suppress(Exception):
                    self._kpi.count(
                        MetricNames.LLM_CALLS, 1, dims=terminal_dims, actor=actor
                    )
                measurements: dict[str, float] = {
                    "call_latency_ms": float(fields["elapsed_ms"] or 0)
                }
                for name in (
                    "first_chunk_ms",
                    "max_chunk_gap_ms",
                    "terminal_silence_ms",
                ):
                    if name in fields:
                        measurements[name] = float(fields[name] or 0)
                for name, value in measurements.items():
                    metric_dims = terminal_dims
                    if name == "call_latency_ms":
                        metric_dims = {
                            "model_name": model_name,
                            "status": outcome,
                            "agent_id": self._binding.portable_context.agent_name
                            or self._binding.portable_context.agent_id,
                        }
                    with suppress(Exception):
                        self._kpi.emit(
                            name=f"llm.{name}",
                            type="timer",
                            value=value,
                            unit="ms",
                            dims=metric_dims,
                            actor=actor,
                        )

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
            if delegation_enabled():
                logger.info(
                    "[LLM][RESPONSE] tool_calls=%d total_args=%d",
                    len(tool_calls),
                    sum(
                        len((tc.get("args") or {})) if isinstance(tc, dict) else 0
                        for tc in tool_calls
                    ),
                )
            else:
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
