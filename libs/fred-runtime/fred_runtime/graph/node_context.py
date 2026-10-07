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

"""
The runtime implementation of the SDK's `GraphNodeContext`.

One `NodeContext` is built per node run. It gives the handler its model, tools,
sub-agents, files and HITL, and pushes every runtime event straight to the
executor's `sink` as it happens. Spans and KPIs for each call live here too.
"""

from __future__ import annotations

import json
import logging
import time as _time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Any, cast

from fred_core.portable import MetricsProvider, Span
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    AgentInvocationResult,
    BoundRuntimeContext,
    ConversationTurn,
    InvocationScope,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import (
    TuningValue,
)
from fred_sdk.contracts.runtime import (
    AssistantDeltaRuntimeEvent,
    HumanInputRequest,
    RuntimeEvent,
    RuntimeServices,
    StatusRuntimeEvent,
    ThoughtDeltaEvent,
    ThoughtEndEvent,
    ThoughtKind,
    ThoughtStartEvent,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
)
from fred_sdk.support.mcp_utils import normalize_mcp_content
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.errors import GraphBubbleUp, GraphInterrupt
from langgraph.func import task
from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from fred_runtime.common.context_aware_tool import ContextAwareTool
from fred_runtime.runtime_support.model_metadata import (
    runtime_metadata_from_message,
    sum_token_usage,
)
from fred_runtime.runtime_support.tool_approval import (
    GatedToolCall,
    ToolApproval,
    build_tool_approval_request,
    is_tool_approval_granted,
)
from fred_runtime.runtime_support.tool_execution import ToolExecution
from fred_runtime.runtime_support.trace_payloads import (
    serialize_messages,
    serialize_model_output,
    to_langfuse_usage,
)

logger = logging.getLogger(__name__)

# RFC AGENT-INVOKE: typed agent invocation — how many times invoke_agent re-asks a
# callee for a valid JSON object before giving up and returning structured=None.
_STRUCTURED_OUTPUT_MAX_ATTEMPTS = 2


def _structured_output_instruction(schema: dict[str, Any]) -> str:
    """Instruction appended to the callee message asking for schema-conformant JSON."""
    return (
        "\n\nIMPORTANT: Respond with ONLY a single valid JSON object that conforms to "
        "this JSON Schema. No prose, no explanation, no markdown code fences:\n"
        + json.dumps(schema, ensure_ascii=False)
    )


def _try_json_object(text: str) -> dict[str, Any] | None:
    """Parse ``text`` as JSON, returning it only if it is a JSON object."""
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of a single JSON object from an agent's free text.

    Tries, in order: the whole string, a fenced ``` block, then the first balanced
    ``{...}`` span. Returns ``None`` if nothing parses to an object.
    """
    if not text:
        return None
    candidate = text.strip()
    obj = _try_json_object(candidate)
    if obj is not None:
        return obj

    fence = candidate.find("```")
    if fence != -1:
        rest = candidate[fence + 3 :]
        if rest[:4].lower() == "json":
            rest = rest[4:]
        end = rest.find("```")
        if end != -1:
            obj = _try_json_object(rest[:end].strip())
            if obj is not None:
                return obj

    start = candidate.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(candidate)):
            char = candidate[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    obj = _try_json_object(candidate[start : index + 1])
                    if obj is not None:
                        return obj
                    break
        start = candidate.find("{", start + 1)
    return None


def _coerce_structured_payload(
    content: str, output_schema: type[BaseModel]
) -> dict[str, Any] | None:
    """Extract + validate a callee's text into ``output_schema``; ``None`` on failure."""
    parsed = _extract_json_object(content)
    if parsed is None:
        return None
    try:
        return output_schema.model_validate(parsed).model_dump(mode="json")
    except ValidationError:
        return None


@dataclass(slots=True)
class NodeContext:
    binding: BoundRuntimeContext
    services: RuntimeServices
    model: BaseChatModel | None
    graph_agent_id: str
    node_id: str
    allowed_tool_refs: frozenset[str]
    runtime_tools: Mapping[str, BaseTool]
    tuning_values: dict[str, TuningValue]
    # Receives every runtime event as it happens (LangGraph's stream writer),
    # so status and tool events keep their order relative to tokens.
    sink: Callable[[RuntimeEvent], None]
    tool_approval: ToolApproval | None = None
    checkpoint_tools: bool = False
    _last_model_name: str | None = None
    # A node may call the model several times; its usage is their sum.
    _total_token_usage: dict[str, int] | None = None
    _last_finish_reason: str | None = None
    # Pauses asked so far in this run of the node; see request_human_input.
    _pauses: int = 0

    def record_model_metadata(
        self,
        *,
        model_name: str | None,
        token_usage: dict[str, int] | None,
        finish_reason: str | None,
    ) -> None:
        """Fold one model call into this node's metadata; usage is summed."""
        if model_name:
            self._last_model_name = model_name
        if token_usage:
            self._total_token_usage = sum_token_usage(
                self._total_token_usage, token_usage
            )
        if finish_reason:
            self._last_finish_reason = finish_reason

    @property
    def last_model_metadata(
        self,
    ) -> tuple[str | None, dict[str, int] | None, str | None]:
        """Last model name and finish reason, with usage summed over the node."""
        return (
            self._last_model_name,
            self._total_token_usage,
            self._last_finish_reason,
        )

    def emit_status(
        self,
        status: str,
        detail: str | None = None,
    ) -> None:
        self.sink(StatusRuntimeEvent(sequence=0, status=status, detail=detail))

    def thinking(
        self,
        phase: ThoughtKind,
        *,
        title: str | None = None,
    ):
        thought_id = uuid.uuid4().hex
        start_time = _time.monotonic()
        conclusion_holder: list[str | None] = [None]
        ctx = self

        class _Writer:
            async def write(self, text: str) -> None:
                ctx.sink(
                    ThoughtDeltaEvent(sequence=0, thought_id=thought_id, delta=text)
                )

            async def conclude(self, text: str) -> None:
                conclusion_holder[0] = text

        @asynccontextmanager
        async def _ctx():
            ctx.sink(
                ThoughtStartEvent(
                    sequence=0,
                    thought_id=thought_id,
                    phase=phase,
                    title=title,
                    source="authored",
                )
            )
            writer = _Writer()
            try:
                yield writer
            finally:
                duration_ms = int((_time.monotonic() - start_time) * 1000)
                ctx.sink(
                    ThoughtEndEvent(
                        sequence=0,
                        thought_id=thought_id,
                        conclusion=conclusion_holder[0],
                        duration_ms=duration_ms,
                    )
                )

        return _ctx()

    def emit_thought(
        self,
        phase: ThoughtKind,
        text: str,
        *,
        title: str | None = None,
        conclusion: str | None = None,
    ) -> None:
        thought_id = uuid.uuid4().hex
        for event in (
            ThoughtStartEvent(
                sequence=0,
                thought_id=thought_id,
                phase=phase,
                title=title,
                source="authored",
            ),
            ThoughtDeltaEvent(sequence=0, thought_id=thought_id, delta=text),
            ThoughtEndEvent(
                sequence=0,
                thought_id=thought_id,
                conclusion=conclusion,
                duration_ms=None,
            ),
        ):
            self.sink(event)

    def emit_assistant_delta(self, delta: str) -> None:
        """Emit one assistant token delta."""
        self.sink(AssistantDeltaRuntimeEvent(sequence=0, delta=delta))

    def _require_model(self) -> BaseChatModel:
        if self.model is None:
            raise RuntimeError("GraphRuntime requires a bound chat model.")
        return self.model

    async def invoke_model(
        self,
        messages: list[BaseMessage],
    ) -> BaseMessage:
        """Call the bound model, streaming each token to the UI as it arrives."""
        model = self._require_model()
        model_name = _resolve_model_name(model)
        with _observe(
            self,
            "v2.graph.model",
            {"model_name": model_name},
            phase="v2_graph_model",
            dims={"model_name": model_name},
        ) as obs:
            accumulated: BaseMessage | None = None
            async for chunk in model.astream(messages):
                if isinstance(chunk.content, str) and chunk.content:
                    self.emit_assistant_delta(chunk.content)
                # Adding chunks merges usage, tool calls and response metadata.
                accumulated = (
                    chunk if accumulated is None else accumulated + chunk  # type: ignore[operator]
                )
            # astream raises rather than yield nothing, so this is never None.
            message = cast(BaseMessage, accumulated)
            name, usage, finish_reason = runtime_metadata_from_message(message)
            self.record_model_metadata(
                model_name=name or model_name,
                token_usage=usage,
                finish_reason=finish_reason,
            )
            if obs.span is not None:
                obs.span.set_usage(
                    model=name or model_name, usage=to_langfuse_usage(usage)
                )
                tracer = self.services.tracer
                if tracer is not None and tracer.captures_content:
                    obs.span.set_io(
                        input=serialize_messages(messages),
                        output=serialize_model_output([message]),
                    )
            return message

    async def invoke_structured_model(
        self,
        output_model: type[BaseModel],
        messages: list[BaseMessage],
    ) -> BaseModel:
        """Call the bound model for validated routing or extraction output."""
        model = self._require_model()
        model_name = _resolve_model_name(model)
        # include_raw: the parsed object alone carries no usage metadata, and
        # the call's tokens must still reach the turn total and the span.
        structured_model = model.with_structured_output(
            output_model,
            method="json_schema",
            include_raw=True,
        )
        observed = {"model_name": model_name, "output_model": output_model.__name__}
        with _observe(
            self,
            "v2.graph.structured_model",
            observed,
            phase="v2_graph_structured_model",
            dims=observed,
        ) as obs:
            response = cast(dict[str, Any], await structured_model.ainvoke(messages))
            raw = response["raw"]
            name, usage, finish_reason = (
                runtime_metadata_from_message(raw)
                if isinstance(raw, BaseMessage)
                else (None, None, None)
            )
            self.record_model_metadata(
                model_name=name or model_name,
                token_usage=usage,
                finish_reason=finish_reason,
            )
            if obs.span is not None:
                obs.span.set_usage(
                    model=name or model_name, usage=to_langfuse_usage(usage)
                )
            if response["parsing_error"] is not None:
                raise response["parsing_error"]
            parsed = response["parsed"]
            return (
                parsed
                if isinstance(parsed, output_model)
                else output_model.model_validate(parsed)
            )

    async def invoke_tool(
        self, tool_ref: str, payload: dict[str, object]
    ) -> ToolInvocationResult:
        if not self.checkpoint_tools:
            return await self._invoke_tool(tool_ref, payload)

        @task(name="fred_tool_ref")
        async def call() -> dict[str, object]:
            result = await self._invoke_tool(tool_ref, payload)
            return result.model_dump(mode="json")

        return ToolInvocationResult.model_validate(await call())

    async def invoke_runtime_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> object:
        if not self.checkpoint_tools:
            return await self._invoke_runtime_tool(tool_name, arguments)

        @task(name="fred_runtime_tool")
        async def call() -> object:
            return await self._invoke_runtime_tool(tool_name, arguments)

        return await call()

    async def _approve_tool(
        self, name: str, arguments: dict[str, object], call_id: str
    ) -> bool:
        if self.tool_approval is None:
            return True
        needs, question = self.tool_approval.decision(
            name, {"name": name, "args": arguments, "id": call_id}
        )
        if not needs:
            return True
        request = build_tool_approval_request(
            binding=self.binding,
            calls=[
                GatedToolCall(
                    tool_call_id=call_id,
                    tool_name=name,
                    tool_args=arguments,
                    question=question,
                )
            ],
        ).model_copy(update={"occurrence_id": call_id})
        return is_tool_approval_granted(interrupt(request.model_dump(mode="json")))

    def _refused_tool(self, name: str, call_id: str) -> ToolInvocationResult:
        result = ToolInvocationResult(
            tool_ref=name,
            is_error=True,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.TEXT, text="Tool execution was not approved."
                ),
            ),
        )
        self.sink(
            ToolResultRuntimeEvent(
                sequence=0,
                call_id=call_id,
                tool_name=name,
                content=_render_tool_result(result),
                is_error=True,
            )
        )
        return result

    async def _invoke_tool(
        self, tool_ref: str, payload: dict[str, object]
    ) -> ToolInvocationResult:
        tool_ref, payload, call_id = (
            await _checkpointed_tool_invocation(tool_ref, payload)
            if self.checkpoint_tools
            else (tool_ref, payload, _tool_call_id())
        )
        if tool_ref not in self.allowed_tool_refs:
            raise RuntimeError(
                f"Graph node attempted to invoke undeclared tool_ref '{tool_ref}'."
            )
        tool_invoker = self.services.tool_invoker
        if tool_invoker is None:
            raise RuntimeError("GraphRuntime requires RuntimeServices.tool_invoker.")

        self.sink(
            ToolCallRuntimeEvent(
                sequence=0,
                tool_name=tool_ref,
                call_id=call_id,
                arguments=payload,
            )
        )
        if not await self._approve_tool(tool_ref, payload, call_id):
            return self._refused_tool(tool_ref, call_id)
        with _observe(
            self,
            "v2.graph.tool",
            {"tool_ref": tool_ref, "call_id": call_id},
        ) as obs:
            result = await ToolExecution(
                kpi=self.services.kpi_writer, binding=self.binding
            ).run(
                lambda: tool_invoker.invoke(
                    ToolInvocationRequest(
                        tool_ref=tool_ref,
                        payload=payload,
                        context=self.binding.portable_context,
                    )
                ),
                tool_name=tool_ref,
                source="capability",
                span=obs.span,
            )
            if result.is_error:
                obs.fail()
        self.sink(
            ToolResultRuntimeEvent(
                sequence=0,
                call_id=call_id,
                tool_name=tool_ref,
                content=_render_tool_result(result),
                is_error=result.is_error,
                sources=result.sources,
                ui_parts=result.ui_parts,
                latency_ms=obs.elapsed_ms,
            )
        )
        return result

    async def _invoke_runtime_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> object:
        tool_name, arguments, call_id = (
            await _checkpointed_tool_invocation(tool_name, arguments)
            if self.checkpoint_tools
            else (tool_name, arguments, _tool_call_id())
        )
        tool = self.runtime_tools.get(tool_name)
        if tool is None:
            raise RuntimeError(f"Runtime tool '{tool_name}' is not available.")

        self.sink(
            ToolCallRuntimeEvent(
                sequence=0,
                tool_name=tool_name,
                call_id=call_id,
                arguments=arguments,
            )
        )
        if not await self._approve_tool(tool_name, arguments, call_id):
            return self._refused_tool(tool_name, call_id).model_dump(mode="json")
        with _observe(
            self,
            "v2.graph.runtime_tool",
            {"tool_name": tool_name, "call_id": call_id},
        ) as obs:
            try:
                raw_result = await ToolExecution(
                    kpi=self.services.kpi_writer, binding=self.binding
                ).run(
                    lambda: tool.ainvoke(
                        {
                            "type": "tool_call",
                            "id": call_id,
                            "name": tool_name,
                            "args": arguments,
                        }
                        if tool.response_format == "content_and_artifact"
                        else arguments
                    ),
                    tool_name=tool_name,
                    source="mcp"
                    if isinstance(tool, ContextAwareTool)
                    else "capability",
                    span=obs.span,
                )
                # A ToolCall envelope preserves MCP artifacts that plain args discard.
                if isinstance(raw_result, ToolMessage):
                    if raw_result.status == "error":
                        obs.fail()
                    artifact = raw_result.artifact
                    if isinstance(artifact, ToolInvocationResult):
                        if (
                            not artifact.blocks
                            and isinstance(raw_result.content, str)
                            and raw_result.content
                        ):
                            artifact = artifact.model_copy(
                                update={
                                    "blocks": (
                                        ToolContentBlock(
                                            kind=ToolContentKind.TEXT,
                                            text=raw_result.content,
                                        ),
                                    )
                                }
                            )
                        raw_result = artifact
                    else:
                        raw_result = (
                            artifact if artifact is not None else raw_result.content
                        )
                normalized = _normalize_runtime_tool_output(raw_result)
                # A capability tool reports failure with an is_error result rather
                # than raising; read it off the typed result before normalization
                # erases it, never off a dict key a plain tool might also carry.
                typed_result = (
                    raw_result if isinstance(raw_result, ToolInvocationResult) else None
                )
                if typed_result is not None and typed_result.is_error:
                    obs.fail()
                self.sink(
                    ToolResultRuntimeEvent(
                        sequence=0,
                        call_id=call_id,
                        tool_name=tool_name,
                        content=_stringify_content(normalized),
                        is_error=obs.failed,
                        sources=typed_result.sources if typed_result else (),
                        ui_parts=typed_result.ui_parts if typed_result else (),
                        latency_ms=obs.elapsed_ms,
                    )
                )
                return normalized
            except GraphBubbleUp:
                raise
            except Exception as exc:
                self.sink(
                    ToolResultRuntimeEvent(
                        sequence=0,
                        call_id=call_id,
                        tool_name=tool_name,
                        content=str(exc),
                        is_error=True,
                        latency_ms=obs.elapsed_ms,
                    )
                )
                raise

    async def invoke_agent(
        self,
        agent_id: str,
        message: str,
        *,
        prior_turns: tuple[ConversationTurn, ...] = (),
        output_schema: type[BaseModel] | None = None,
        scope: InvocationScope | None = None,
    ) -> AgentInvocationResult:
        """Invoke another registered agent for one turn (RFC AGENT-INVOKE).

        When ``output_schema`` is given the callee is asked for a JSON object of that
        shape; the validated payload is attached to ``result.structured`` (with a
        bounded retry, ``None`` if it could not be coerced). When ``scope`` is given,
        the callee's retrieval world is narrowed for this call only.
        """
        agent_invoker = self.services.agent_invoker
        if agent_invoker is None:
            raise RuntimeError(
                "GraphNodeContext.invoke_agent requires RuntimeServices.agent_invoker "
                "to be set. Inject an AgentInvokerPort implementation before running "
                "agents that call other agents."
            )

        self.emit_status("invoke_agent", detail=agent_id)

        schema_dict = (
            output_schema.model_json_schema() if output_schema is not None else None
        )
        max_attempts = (
            _STRUCTURED_OUTPUT_MAX_ATTEMPTS if output_schema is not None else 1
        )

        result: AgentInvocationResult | None = None
        with _observe(
            self,
            "v2.graph.agent",
            {"target_agent_id": agent_id},
            phase="v2_graph_agent",
            agent_step=f"{self.node_id}:{agent_id}",
            dims={"target_agent_id": agent_id},
        ) as obs:
            for attempt in range(max_attempts):
                effective_message = message
                if schema_dict is not None:
                    effective_message = message + _structured_output_instruction(
                        schema_dict
                    )
                    if attempt > 0:
                        effective_message = (
                            "Your previous response was not a valid JSON object. "
                            + effective_message
                        )
                result = await agent_invoker.invoke(
                    AgentInvocationRequest(
                        agent_id=agent_id,
                        message=effective_message,
                        context=self.binding.portable_context,
                        prior_turns=prior_turns,
                        scope=scope,
                        output_schema=schema_dict,
                    )
                )
                if output_schema is None or result.is_error:
                    break
                structured = _coerce_structured_payload(result.content, output_schema)
                if structured is not None:
                    result = result.model_copy(update={"structured": structured})
                    break

            assert result is not None
            if (
                output_schema is not None
                and not result.is_error
                and result.structured is None
            ):
                logger.warning(
                    "invoke_agent(%s): could not coerce output to %s after %d "
                    "attempt(s); returning structured=None",
                    agent_id,
                    output_schema.__name__,
                    max_attempts,
                )
            if result.is_error:
                obs.fail()
        return result

    async def request_human_input(self, request: HumanInputRequest) -> object:
        # Replayed from the node start on resume: `interrupt` then returns the
        # human's answer instead of raising. Every pause of one node shares its
        # Interrupt.id, so its rank in the node names it for the resume claim.
        if request.occurrence_id is None:
            request = request.model_copy(
                update={"occurrence_id": f"{self.node_id}#{self._pauses}"}
            )
        self._pauses += 1
        try:
            return interrupt(request.model_dump(mode="json"))
        except GraphInterrupt:
            span = _start_runtime_span(
                services=self.services,
                binding=self.binding,
                name="v2.graph.await_human",
                attributes={
                    "agent_id": self.graph_agent_id,
                    "node_id": self.node_id,
                    "stage": request.stage or "unspecified",
                },
            )
            if span is not None:
                span.set_attribute("status", "awaiting_human")
                span.end()
            raise


@dataclass(slots=True)
class _Observation:
    """One observed call: its span, its KPI dims and how long it has run."""

    span: Span | None
    kpi_dims: dict[str, str | None]
    started_at: float = field(default_factory=_time.monotonic)
    failed: bool = False

    def fail(self) -> None:
        """Mark a call that returned an error result without raising."""
        self.failed = True
        self.kpi_dims["status"] = "error"

    @property
    def elapsed_ms(self) -> int:
        return int((_time.monotonic() - self.started_at) * 1000)


@contextmanager
def _observe(
    ctx: NodeContext,
    span_name: str,
    attributes: Mapping[str, str | None],
    *,
    phase: str | None = None,
    agent_step: str | None = None,
    dims: Mapping[str, str | None] | None = None,
) -> Iterator[_Observation]:
    """Span and phase timer around one node call; their status follows the outcome."""
    span = _start_runtime_span(
        services=ctx.services,
        binding=ctx.binding,
        name=span_name,
        attributes={
            "agent_id": ctx.graph_agent_id,
            "node_id": ctx.node_id,
            **attributes,
        },
    )
    timer = (
        nullcontext({})
        if phase is None
        else _graph_phase_timer(
            metrics=ctx.services.metrics,
            binding=ctx.binding,
            agent_id=ctx.graph_agent_id,
            phase=phase,
            agent_step=agent_step or ctx.node_id,
            extra_dims={"node_id": ctx.node_id, **(dims or {})},
        )
    )
    try:
        with timer as kpi_dims:
            observation = _Observation(span=span, kpi_dims=kpi_dims)
            yield observation
    except Exception:
        if span is not None:
            span.set_attribute("status", "error")
        raise
    else:
        if span is not None:
            span.set_attribute("status", "error" if observation.failed else "ok")
    finally:
        if span is not None:
            span.end()


def _graph_phase_timer(
    *,
    metrics: MetricsProvider | None,
    binding: BoundRuntimeContext,
    agent_id: str,
    phase: str,
    agent_step: str,
    extra_dims: Mapping[str, str | None] | None = None,
):
    if metrics is None:
        return nullcontext({})
    dims: dict[str, str | None] = {
        "phase": phase,
        "agent_id": agent_id,
        "agent_step": agent_step,
    }
    dims.update(_runtime_observability_dims(binding=binding))
    if extra_dims:
        dims.update(dict(extra_dims))
    return metrics.timer(
        "app.phase_latency_ms",
        dims=dims,
    )


def _start_runtime_span(
    *,
    services: RuntimeServices,
    binding: BoundRuntimeContext,
    name: str,
    attributes: Mapping[str, str | int | float | bool | None] | None = None,
):
    tracer = services.tracer
    if tracer is None:
        return None
    span_attributes: dict[str, str | int | float | bool | None] = dict(
        _runtime_observability_dims(binding=binding)
    )
    if attributes:
        span_attributes.update(dict(attributes))
    try:
        return tracer.start_span(
            name=name, context=binding.portable_context, attributes=span_attributes
        )
    except Exception:
        # Tracing must never fail a turn.
        return None


def _runtime_observability_dims(
    *, binding: BoundRuntimeContext
) -> dict[str, str | None]:
    """The execution identity every span and KPI row of this run carries."""

    portable = binding.portable_context
    baggage = portable.baggage
    return {
        "user_id": portable.user_id,
        "team_id": portable.team_id,
        "session_id": portable.session_id,
        "trace_id": portable.trace_id,
        "correlation_id": portable.correlation_id,
        "agent_instance_id": baggage.get("agent_instance_id"),
        "template_agent_id": baggage.get("template_agent_id"),
        "execution_action": baggage.get("execution_action"),
    }


def _resolve_model_name(model: BaseChatModel) -> str | None:
    for attr_name in ("model_name", "model"):
        raw_value = getattr(model, attr_name, None)
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
    return None


def _render_tool_result(result: ToolInvocationResult) -> str:
    blocks = list(result.blocks)
    if blocks:
        rendered: list[str] = []
        for block in blocks:
            rendered.append(
                block.text if block.text is not None else json.dumps(block.data)
            )
        return "\n".join(part for part in rendered if part)
    return ""


def _normalize_runtime_tool_output(raw: object) -> object:
    if isinstance(raw, tuple):
        return [_normalize_runtime_tool_output(item) for item in raw]

    if isinstance(raw, list):
        raw = normalize_mcp_content(raw)

    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return raw
        return raw

    if isinstance(raw, (dict, list, str, int, float, bool)) or raw is None:
        return raw
    model_dump = getattr(raw, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return str(raw)


def _stringify_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _tool_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:20]}"


@task
async def _checkpointed_tool_invocation(
    name: str, arguments: dict[str, object]
) -> tuple[str, dict[str, object], str]:
    """Persist the exact invocation before approval, including across node replay."""
    return name, arguments, _tool_call_id()
