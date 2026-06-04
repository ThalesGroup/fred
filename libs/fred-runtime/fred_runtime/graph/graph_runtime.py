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
Executable runtime for v2 graph agents.

Read this file when you need to answer practical questions:
- Why did a node run (or not run)?
- Why did the run pause for HITL?
- Which tool call was made from which node?
- Which state was persisted and resumed?

Graph agent business logic stays in definition files. This runtime handles
orchestration, streaming events, checkpoints, and resume behavior.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time as _time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Protocol, cast

from fred_core.portable import MetricsProvider
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    AgentInvocationResult,
    ArtifactPublishRequest,
    ArtifactScope,
    BoundRuntimeContext,
    ConversationTurn,
    FetchedResource,
    PublishedArtifact,
    ResourceFetchRequest,
    ResourceScope,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
    GraphConditionalDefinition,
    GraphDefinition,
    TuningValue,
)
from fred_sdk.contracts.runtime import (
    AgentRuntime,
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    Executor,
    FinalRuntimeEvent,
    HumanInputRequest,
    NodeErrorRuntimeEvent,
    RuntimeEvent,
    RuntimeServices,
    StatusRuntimeEvent,
    ThoughtDeltaEvent,
    ThoughtEndEvent,
    ThoughtKind,
    ThoughtRecord,
    ThoughtStartEvent,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
)
from fred_sdk.graph.runtime import (
    GraphExecutionOutput,
    GraphNodeContext,
    GraphNodeResult,
)
from fred_sdk.support.mcp_utils import normalize_mcp_content
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, empty_checkpoint
from pydantic import BaseModel

from fred_runtime.runtime_support.checkpoints import (
    AsyncCheckpointReader,
    AsyncCheckpointWriter,
)
from fred_runtime.runtime_support.model_metadata import runtime_metadata_from_message

logger = logging.getLogger(__name__)

GraphNodeHandler = Callable[
    [BaseModel, GraphNodeContext], GraphNodeResult | Awaitable[GraphNodeResult]
]


class _CheckpointTupleLike(Protocol):
    checkpoint: Checkpoint


@dataclass(frozen=True, slots=True)
class _PendingGraphCheckpoint:
    state: BaseModel
    node_id: str
    request: HumanInputRequest
    checkpoint_id: str | None = None


class _AwaitHumanInterrupt(Exception):
    def __init__(self, request: HumanInputRequest):
        super().__init__("Graph execution is awaiting human input.")
        self.request = request


@dataclass(slots=True)
class _GraphNodeExecutionContext:
    binding: BoundRuntimeContext
    services: RuntimeServices
    model: BaseChatModel | None
    model_resolver: Callable[[str], BaseChatModel | None] | None
    graph_agent_id: str
    node_id: str
    allowed_tool_refs: frozenset[str]
    runtime_tools: Mapping[str, BaseTool]
    tuning_values: dict[str, TuningValue]
    _events: list[RuntimeEvent] = field(default_factory=list)
    _thought_records: list[ThoughtRecord] = field(default_factory=list)
    _resume_payload: object | None = None
    # Live event sink injected by the executor when streaming is active.
    # AssistantDeltaRuntimeEvents are forwarded here immediately instead of
    # being buffered in _events, so the caller receives tokens in real time.
    _live_emit: Callable[[RuntimeEvent], None] | None = None
    _last_model_name: str | None = None
    _last_token_usage: dict[str, int] | None = None
    _last_finish_reason: str | None = None

    @property
    def events(self) -> tuple[RuntimeEvent, ...]:
        return tuple(self._events)

    @property
    def thought_records(self) -> tuple[ThoughtRecord, ...]:
        return tuple(self._thought_records)

    def record_model_metadata(
        self,
        *,
        model_name: str | None,
        token_usage: dict[str, int] | None,
        finish_reason: str | None,
    ) -> None:
        """
        Capture the latest model metadata observed inside this node.

        Why this exists:
        - graph nodes can invoke multiple model calls across one turn
        - the runtime needs one reliable place to record the latest token usage

        How to use:
        - call after a model invocation returns or streams its final chunk

        Example:
        - `context.record_model_metadata(model_name=name, token_usage=usage, finish_reason=reason)`
        """

        if model_name:
            self._last_model_name = model_name
        if token_usage:
            self._last_token_usage = token_usage
        if finish_reason:
            self._last_finish_reason = finish_reason

    @property
    def last_model_metadata(
        self,
    ) -> tuple[str | None, dict[str, int] | None, str | None]:
        """
        Return the latest model metadata recorded by this node.

        Why this exists:
        - the executor needs a stable readout after the node completes

        How to use:
        - read after the node handler finishes

        Example:
        - `model_name, usage, finish_reason = context.last_model_metadata`
        """

        return (
            self._last_model_name,
            self._last_token_usage,
            self._last_finish_reason,
        )

    def _forward(self, event: RuntimeEvent) -> None:
        if self._live_emit is not None:
            self._live_emit(event)
        else:
            self._events.append(event)

    def emit_status(
        self,
        status: str,
        detail: str | None = None,
    ) -> None:
        self._events.append(
            StatusRuntimeEvent(sequence=0, status=status, detail=detail)
        )

    def thinking(
        self,
        phase: ThoughtKind,
        *,
        title: str | None = None,
    ):
        thought_id = uuid.uuid4().hex
        start_time = _time.monotonic()
        accumulated: list[str] = []
        conclusion_holder: list[str | None] = [None]
        ctx = self

        class _Writer:
            async def write(self, text: str) -> None:
                accumulated.append(text)
                ctx._forward(
                    ThoughtDeltaEvent(sequence=0, thought_id=thought_id, delta=text)
                )

            async def conclude(self, text: str) -> None:
                conclusion_holder[0] = text

        @asynccontextmanager
        async def _ctx():
            ctx._forward(
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
                ctx._forward(
                    ThoughtEndEvent(
                        sequence=0,
                        thought_id=thought_id,
                        conclusion=conclusion_holder[0],
                        duration_ms=duration_ms,
                    )
                )
                ctx._thought_records.append(
                    ThoughtRecord(
                        thought_id=thought_id,
                        phase=phase,
                        title=title,
                        text="".join(accumulated),
                        conclusion=conclusion_holder[0],
                        duration_ms=duration_ms,
                        source="authored",
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
            self._forward(event)
        self._thought_records.append(
            ThoughtRecord(
                thought_id=thought_id,
                phase=phase,
                title=title,
                text=text,
                conclusion=conclusion,
                duration_ms=None,
                source="authored",
            )
        )

    def emit_assistant_delta(self, delta: str) -> None:
        """
        Emit one assistant token delta.

        When a live-emit sink is present (streaming mode), the delta is
        forwarded immediately to the caller without buffering. Otherwise it is
        stored in _events for batch delivery, which preserves backward
        compatibility with the invoke() path.
        """
        self._forward(AssistantDeltaRuntimeEvent(sequence=0, delta=delta))

    async def invoke_model(
        self,
        messages: list[BaseMessage],
        *,
        operation: str = "default",
    ) -> BaseMessage:
        """
        Invoke the bound chat model and stream token deltas in real time.

        Why streaming and not ainvoke:
        - ainvoke blocks until the full response is ready; the caller sees
          nothing until generation completes
        - astream forwards each token as an AssistantDeltaRuntimeEvent so the
          UI receives tokens progressively, matching the ReAct runtime behavior

        Why invoke_structured_model still uses ainvoke:
        - structured output (with_structured_output / json_schema) must parse
          the complete JSON before validation; partial JSON is not useful

        Token accumulation:
        - LangChain AIMessageChunk supports chunk += chunk, which merges
          tool_calls, response_metadata, and usage_metadata correctly
        - the final accumulated chunk is cast to AIMessage so callers get a
          fully-populated BaseMessage with all metadata intact
        """
        resolved_model = (
            self.model_resolver(operation)
            if self.model_resolver is not None
            else self.model
        )
        if resolved_model is None:
            raise RuntimeError("GraphRuntime requires a bound chat model.")

        model_name = _resolve_model_name(resolved_model)
        span = _start_runtime_span(
            services=self.services,
            binding=self.binding,
            name="v2.graph.model",
            attributes={
                "agent_id": self.graph_agent_id,
                "node_id": self.node_id,
                "operation": operation,
                "model_name": model_name,
            },
        )
        with _graph_phase_timer(
            metrics=self.services.metrics,
            binding=self.binding,
            agent_id=self.graph_agent_id,
            phase="v2_graph_model",
            agent_step=f"{self.node_id}:{operation}",
            extra_dims={
                "node_id": self.node_id,
                "operation": operation,
                "model_name": model_name,
            },
        ):
            try:
                captured_model_name = model_name
                captured_token_usage: dict[str, int] | None = None
                captured_finish_reason: str | None = None
                accumulated: BaseMessage | None = None
                async for chunk in resolved_model.astream(messages):
                    if isinstance(chunk, BaseMessage):
                        (
                            chunk_model_name,
                            chunk_usage,
                            chunk_finish_reason,
                        ) = runtime_metadata_from_message(chunk)
                        if chunk_model_name:
                            captured_model_name = chunk_model_name
                        if chunk_usage:
                            captured_token_usage = chunk_usage
                        if chunk_finish_reason:
                            captured_finish_reason = chunk_finish_reason
                    delta_text = chunk.content if isinstance(chunk.content, str) else ""
                    if delta_text:
                        self.emit_assistant_delta(delta_text)
                    if accumulated is None:
                        accumulated = chunk
                    else:
                        accumulated = accumulated + chunk  # type: ignore[operator]
                if accumulated is None:
                    # astream yielded nothing — fall back to an empty message
                    accumulated = cast(
                        BaseMessage, await resolved_model.ainvoke(messages)
                    )
                if isinstance(accumulated, BaseMessage):
                    (
                        final_model_name,
                        final_token_usage,
                        final_finish_reason,
                    ) = runtime_metadata_from_message(accumulated)
                    if final_model_name:
                        captured_model_name = final_model_name
                    if final_token_usage:
                        captured_token_usage = final_token_usage
                    if final_finish_reason:
                        captured_finish_reason = final_finish_reason
                self.record_model_metadata(
                    model_name=captured_model_name,
                    token_usage=captured_token_usage,
                    finish_reason=captured_finish_reason,
                )
                if span is not None:
                    span.set_attribute("status", "ok")
                return accumulated
            except Exception:
                if span is not None:
                    span.set_attribute("status", "error")
                raise
            finally:
                if span is not None:
                    span.end()

    async def invoke_structured_model(
        self,
        output_model: type[BaseModel],
        messages: list[BaseMessage],
        *,
        operation: str = "default",
    ) -> BaseModel:
        """
        Invoke one structured-output control step with the bound chat model.

        Use this when a graph node needs validated routing or extraction output
        instead of plain assistant text.
        """

        resolved_model = (
            self.model_resolver(operation)
            if self.model_resolver is not None
            else self.model
        )
        if resolved_model is None:
            raise RuntimeError("GraphRuntime requires a bound chat model.")

        model_name = _resolve_model_name(resolved_model)
        span = _start_runtime_span(
            services=self.services,
            binding=self.binding,
            name="v2.graph.structured_model",
            attributes={
                "agent_id": self.graph_agent_id,
                "node_id": self.node_id,
                "operation": operation,
                "model_name": model_name,
                "output_model": output_model.__name__,
            },
        )
        structured_model = resolved_model.with_structured_output(
            output_model,
            method="json_schema",
        )
        with _graph_phase_timer(
            metrics=self.services.metrics,
            binding=self.binding,
            agent_id=self.graph_agent_id,
            phase="v2_graph_structured_model",
            agent_step=f"{self.node_id}:{operation}",
            extra_dims={
                "node_id": self.node_id,
                "operation": operation,
                "model_name": model_name,
                "output_model": output_model.__name__,
            },
        ):
            try:
                response = await structured_model.ainvoke(messages)
                if isinstance(response, output_model):
                    validated = response
                elif isinstance(response, BaseModel):
                    validated = output_model.model_validate(response.model_dump())
                elif isinstance(response, dict):
                    validated = output_model.model_validate(response)
                else:
                    validated = output_model.model_validate(dict(response))
                if isinstance(response, BaseMessage):
                    (
                        response_model_name,
                        response_token_usage,
                        response_finish_reason,
                    ) = runtime_metadata_from_message(response)
                else:
                    response_model_name = None
                    response_token_usage = None
                    response_finish_reason = None
                self.record_model_metadata(
                    model_name=response_model_name or model_name,
                    token_usage=response_token_usage,
                    finish_reason=response_finish_reason,
                )
                if span is not None:
                    span.set_attribute("status", "ok")
                return validated
            except Exception:
                if span is not None:
                    span.set_attribute("status", "error")
                raise
            finally:
                if span is not None:
                    span.end()

    async def invoke_tool(
        self, tool_ref: str, payload: dict[str, object]
    ) -> ToolInvocationResult:
        if tool_ref not in self.allowed_tool_refs:
            raise RuntimeError(
                f"Graph node attempted to invoke undeclared tool_ref '{tool_ref}'."
            )
        tool_invoker = self.services.tool_invoker
        if tool_invoker is None:
            raise RuntimeError("GraphRuntime requires RuntimeServices.tool_invoker.")

        call_id = f"call_{uuid.uuid4().hex[:20]}"
        self._events.append(
            ToolCallRuntimeEvent(
                sequence=0,
                tool_name=tool_ref,
                call_id=call_id,
                arguments=payload,
            )
        )
        span = _start_runtime_span(
            services=self.services,
            binding=self.binding,
            name="v2.graph.tool",
            attributes={
                "agent_id": self.graph_agent_id,
                "node_id": self.node_id,
                "tool_ref": tool_ref,
                "call_id": call_id,
            },
        )
        try:
            with _graph_phase_timer(
                metrics=self.services.metrics,
                binding=self.binding,
                agent_id=self.graph_agent_id,
                phase="v2_graph_tool",
                agent_step=f"{self.node_id}:{tool_ref}",
                extra_dims={
                    "node_id": self.node_id,
                    "tool_name": tool_ref,
                },
            ) as kpi_dims:
                result = await tool_invoker.invoke(
                    ToolInvocationRequest(
                        tool_ref=tool_ref,
                        payload=payload,
                        context=self.binding.portable_context,
                    )
                )
                if result.is_error:
                    kpi_dims["status"] = "error"
                    if span is not None:
                        span.set_attribute("status", "error")
                elif span is not None:
                    span.set_attribute("status", "ok")
        except Exception:
            if span is not None:
                span.set_attribute("status", "error")
            raise
        finally:
            if span is not None:
                span.end()
        self._events.append(
            ToolResultRuntimeEvent(
                sequence=0,
                call_id=call_id,
                tool_name=tool_ref,
                content=_render_tool_result(result),
                is_error=result.is_error,
                sources=result.sources,
                ui_parts=result.ui_parts,
            )
        )
        return result

    async def invoke_runtime_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> object:
        tool = self.runtime_tools.get(tool_name)
        if tool is None:
            raise RuntimeError(f"Runtime tool '{tool_name}' is not available.")

        call_id = f"call_{uuid.uuid4().hex[:20]}"
        self._events.append(
            ToolCallRuntimeEvent(
                sequence=0,
                tool_name=tool_name,
                call_id=call_id,
                arguments=arguments,
            )
        )
        span = _start_runtime_span(
            services=self.services,
            binding=self.binding,
            name="v2.graph.runtime_tool",
            attributes={
                "agent_id": self.graph_agent_id,
                "node_id": self.node_id,
                "tool_name": tool_name,
                "call_id": call_id,
            },
        )
        with _graph_phase_timer(
            metrics=self.services.metrics,
            binding=self.binding,
            agent_id=self.graph_agent_id,
            phase="v2_graph_runtime_tool",
            agent_step=f"{self.node_id}:{tool_name}",
            extra_dims={
                "node_id": self.node_id,
                "tool_name": tool_name,
            },
        ):
            try:
                raw_result = await tool.ainvoke(arguments)
                normalized = _normalize_runtime_tool_output(raw_result)
                self._events.append(
                    ToolResultRuntimeEvent(
                        sequence=0,
                        call_id=call_id,
                        tool_name=tool_name,
                        content=_stringify_content(normalized),
                        is_error=False,
                    )
                )
                if span is not None:
                    span.set_attribute("status", "ok")
                return normalized
            except Exception as exc:
                self._events.append(
                    ToolResultRuntimeEvent(
                        sequence=0,
                        call_id=call_id,
                        tool_name=tool_name,
                        content=str(exc),
                        is_error=True,
                    )
                )
                if span is not None:
                    span.set_attribute("status", "error")
                raise
            finally:
                if span is not None:
                    span.end()

    async def invoke_agent(
        self,
        agent_id: str,
        message: str,
        *,
        prior_turns: tuple[ConversationTurn, ...] = (),
    ) -> AgentInvocationResult:
        agent_invoker = self.services.agent_invoker
        if agent_invoker is None:
            raise RuntimeError(
                "GraphNodeContext.invoke_agent requires RuntimeServices.agent_invoker "
                "to be set. Inject an AgentInvokerPort implementation before running "
                "agents that call other agents."
            )

        self.emit_status("invoke_agent", detail=agent_id)

        span = _start_runtime_span(
            services=self.services,
            binding=self.binding,
            name="v2.graph.agent",
            attributes={
                "agent_id": self.graph_agent_id,
                "node_id": self.node_id,
                "target_agent_id": agent_id,
            },
        )
        try:
            with _graph_phase_timer(
                metrics=self.services.metrics,
                binding=self.binding,
                agent_id=self.graph_agent_id,
                phase="v2_graph_agent",
                agent_step=f"{self.node_id}:{agent_id}",
                extra_dims={
                    "node_id": self.node_id,
                    "target_agent_id": agent_id,
                },
            ) as kpi_dims:
                result = await agent_invoker.invoke(
                    AgentInvocationRequest(
                        agent_id=agent_id,
                        message=message,
                        context=self.binding.portable_context,
                        prior_turns=prior_turns,
                    )
                )
                if result.is_error:
                    kpi_dims["status"] = "error"
                    if span is not None:
                        span.set_attribute("status", "error")
                elif span is not None:
                    span.set_attribute("status", "ok")
        except Exception:
            if span is not None:
                span.set_attribute("status", "error")
            raise
        finally:
            if span is not None:
                span.end()
        return result

    async def publish_text(
        self,
        *,
        file_name: str,
        text: str,
        key: str | None = None,
        title: str | None = None,
        content_type: str = "text/plain; charset=utf-8",
        scope: ArtifactScope = ArtifactScope.USER,
        target_user_id: str | None = None,
    ) -> PublishedArtifact:
        return await self.publish_bytes(
            file_name=file_name,
            content_bytes=text.encode("utf-8"),
            key=key,
            title=title,
            content_type=content_type,
            scope=scope,
            target_user_id=target_user_id,
        )

    async def publish_bytes(
        self,
        *,
        file_name: str,
        content_bytes: bytes,
        key: str | None = None,
        title: str | None = None,
        content_type: str | None = None,
        scope: ArtifactScope = ArtifactScope.USER,
        target_user_id: str | None = None,
    ) -> PublishedArtifact:
        artifact_publisher = self.services.artifact_publisher
        if artifact_publisher is None:
            raise RuntimeError(
                "GraphRuntime requires RuntimeServices.artifact_publisher to publish generated files."
            )
        span = _start_runtime_span(
            services=self.services,
            binding=self.binding,
            name="v2.graph.publish_artifact",
            attributes={
                "agent_id": self.graph_agent_id,
                "node_id": self.node_id,
                "file_name": file_name,
                "scope": scope.value,
            },
        )
        try:
            artifact = await artifact_publisher.publish(
                ArtifactPublishRequest(
                    file_name=file_name,
                    content_bytes=content_bytes,
                    scope=scope,
                    key=key,
                    content_type=content_type,
                    title=title,
                    target_user_id=target_user_id,
                )
            )
            if span is not None:
                span.set_attribute("status", "ok")
            return artifact
        except Exception:
            if span is not None:
                span.set_attribute("status", "error")
            raise
        finally:
            if span is not None:
                span.end()

    async def fetch_resource(
        self,
        *,
        key: str,
        scope: ResourceScope = ResourceScope.AGENT_CONFIG,
        target_user_id: str | None = None,
    ) -> FetchedResource:
        resource_reader = self.services.resource_reader
        if resource_reader is None:
            raise RuntimeError(
                "GraphRuntime requires RuntimeServices.resource_reader to fetch templates or supporting resources."
            )
        span = _start_runtime_span(
            services=self.services,
            binding=self.binding,
            name="v2.graph.fetch_resource",
            attributes={
                "agent_id": self.graph_agent_id,
                "node_id": self.node_id,
                "resource_key": key,
                "scope": scope.value,
            },
        )
        try:
            resource = await resource_reader.fetch(
                ResourceFetchRequest(
                    key=key,
                    scope=scope,
                    target_user_id=target_user_id,
                )
            )
            if span is not None:
                span.set_attribute("status", "ok")
            return resource
        except Exception:
            if span is not None:
                span.set_attribute("status", "error")
            raise
        finally:
            if span is not None:
                span.end()

    async def fetch_text_resource(
        self,
        *,
        key: str,
        scope: ResourceScope = ResourceScope.AGENT_CONFIG,
        target_user_id: str | None = None,
        encoding: str = "utf-8",
    ) -> str:
        resource = await self.fetch_resource(
            key=key,
            scope=scope,
            target_user_id=target_user_id,
        )
        return resource.as_text(encoding=encoding)

    async def request_human_input(self, request: HumanInputRequest) -> object:
        if self._resume_payload is not None:
            payload = self._resume_payload
            self._resume_payload = None
            return payload
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
        raise _AwaitHumanInterrupt(request)


class _DeterministicGraphExecutor(Executor[BaseModel, BaseModel]):
    """
    Deterministic step-by-step graph executor.

    Execution loop:
    1. Compute starting point (fresh turn or resume).
    2. Run one node handler.
    3. Merge state update.
    4. Resolve next node from route/direct edge.
    5. Persist completion or pending HITL checkpoint.
    """

    def __init__(
        self,
        *,
        definition: GraphAgentDefinition,
        binding: BoundRuntimeContext,
        services: RuntimeServices,
        model: BaseChatModel | None,
        runtime_tools: tuple[BaseTool, ...],
        pending_checkpoints: dict[str, _PendingGraphCheckpoint],
    ) -> None:
        self._definition = definition
        self._binding = binding
        self._services = services
        self._model = model
        self._models_by_operation: dict[str, BaseChatModel] = {}
        if model is not None:
            self._models_by_operation["default"] = model
        self._runtime_tools = {tool.name: tool for tool in runtime_tools}
        self._graph = definition.build_graph()
        self._handlers = _validated_handlers(definition=definition, graph=self._graph)
        self._allowed_tool_refs = frozenset(
            requirement.tool_ref for requirement in definition.declared_tool_refs
        )
        self._pending_checkpoints = pending_checkpoints
        # Pre-compute node lookups.
        self._nodes_by_id = {node.node_id: node for node in self._graph.nodes}
        # Pre-compute the parallel group lookup: fan_out_node -> (fan_in_node, [members])
        self._parallel_groups: dict[str, tuple[str, tuple[str, ...]]] = {
            group[0]: (group[1], group[2:]) for group in self._graph.parallel_groups
        }
        self._last_model_name: str | None = None
        self._last_token_usage: dict[str, int] | None = None
        self._last_finish_reason: str | None = None
        self._thought_records: list[ThoughtRecord] = []

    def _reset_model_metadata(self) -> None:
        """
        Clear any model metadata captured during a previous graph run.

        Why this exists:
        - executor instances are reused across turns for cached agents
        - token usage must reflect the current run only

        How to use:
        - call once at the start of `_execute(...)`

        Example:
        - `self._reset_model_metadata()`
        """

        self._last_model_name = None
        self._last_token_usage = None
        self._last_finish_reason = None
        self._thought_records = []

    def _record_model_metadata(
        self,
        *,
        model_name: str | None,
        token_usage: dict[str, int] | None,
        finish_reason: str | None,
    ) -> None:
        """
        Capture the latest model metadata observed in the graph run.

        Why this exists:
        - the final graph event should expose the most recent model usage data
        - graph nodes can call multiple models; we keep the latest non-empty view

        How to use:
        - call after a node finishes executing

        Example:
        - `self._record_model_metadata(model_name=name, token_usage=usage, finish_reason=reason)`
        """

        if model_name:
            self._last_model_name = model_name
        if token_usage:
            self._last_token_usage = token_usage
        if finish_reason:
            self._last_finish_reason = finish_reason

    def _model_for_operation(self, operation: str) -> BaseChatModel | None:
        cached = self._models_by_operation.get(operation)
        if cached is not None:
            return cached
        factory = self._services.chat_model_factory
        if factory is not None:
            resolved = factory.build_for_operation(
                definition=self._definition,
                binding=self._binding,
                purpose="chat",
                operation=operation,
            )
            if resolved is not None:
                if isinstance(resolved, BaseChatModel):
                    self._models_by_operation[operation] = resolved
                    return resolved
        return self._model

    async def invoke(
        self, input_model: BaseModel, config: ExecutionConfig
    ) -> BaseModel:
        return await self._execute(
            input_model=input_model,
            config=config,
            emit_event=None,
        )

    async def stream(
        self, input_model: BaseModel, config: ExecutionConfig
    ) -> AsyncIterator[RuntimeEvent]:
        """
        Stream runtime events as they are emitted by each graph node.

        Previous implementation collected all events during _execute() then
        replayed them after completion — blocking the caller until the entire
        graph finished. This implementation uses asyncio.Queue so each event
        is yielded immediately when the node emits it, giving the same
        real-time token streaming behaviour as the V2 ReAct runtime.
        """
        queue: asyncio.Queue[RuntimeEvent | None] = asyncio.Queue()
        sequence = 0

        def _put(event: RuntimeEvent) -> None:
            # Called synchronously from within the async _execute loop.
            # put_nowait is safe here: both producer and consumer run in the
            # same event loop; the queue is unbounded so it never blocks.
            queue.put_nowait(event)

        execute_task = asyncio.create_task(
            self._execute(input_model=input_model, config=config, emit_event=_put)
        )

        # Signal end-of-stream via sentinel once the task finishes (normal or error).
        # _execute() already emits a FinalRuntimeEvent on error when emit_event is set,
        # so by the time the sentinel arrives all events are already in the queue.
        execute_task.add_done_callback(lambda _: queue.put_nowait(None))

        while True:
            event = await queue.get()
            if event is None:
                break
            yield _resequence_event(event, sequence)
            sequence += 1

        # Re-raise any exception that escaped _execute's own error handler.
        if not execute_task.cancelled():
            execute_task.result()

    async def _execute(
        self,
        *,
        input_model: BaseModel,
        config: ExecutionConfig,
        emit_event: Callable[[RuntimeEvent], None] | None,
    ) -> BaseModel:
        self._reset_model_metadata()
        state, node_id, resume_payload = await self._starting_point(
            input_model=input_model,
            config=config,
        )
        checkpoint_key = self._checkpoint_key(config)
        steps = 0
        try:
            return await self._execute_loop(
                state=state,
                node_id=node_id,
                resume_payload=resume_payload,
                checkpoint_key=checkpoint_key,
                steps=steps,
                config=config,
                emit_event=emit_event,
            )
        except Exception as exc:
            logger.exception(
                "[V2][GRAPH] Unhandled exception in graph agent=%s",
                self._definition.agent_id,
            )
            error_content = f"An error occurred: {exc}"
            if emit_event is not None:
                emit_event(FinalRuntimeEvent(sequence=0, content=error_content))
                return GraphExecutionOutput(content=error_content)
            raise

    async def _execute_loop(
        self,
        *,
        state: BaseModel,
        node_id: str | None,
        resume_payload: object,
        checkpoint_key: str,
        steps: int,
        config: ExecutionConfig,
        emit_event: Callable[[RuntimeEvent], None] | None,
    ) -> BaseModel:
        while node_id is not None:
            if steps >= config.max_steps:
                raise RuntimeError(
                    f"Graph execution exceeded max_steps={config.max_steps}."
                )
            steps += 1

            handler = self._handlers[node_id]
            node_context = _GraphNodeExecutionContext(
                binding=self._binding,
                services=self._services,
                model=self._model,
                model_resolver=self._model_for_operation,
                graph_agent_id=self._definition.agent_id,
                node_id=node_id,
                allowed_tool_refs=self._allowed_tool_refs,
                runtime_tools=self._runtime_tools,
                tuning_values=self._definition.tuning_values,
                _resume_payload=resume_payload,
                # Inject the live-emit sink so invoke_model can forward token
                # deltas directly to the queue without buffering.
                _live_emit=emit_event,
            )
            node_span = _start_runtime_span(
                services=self._services,
                binding=self._binding,
                name="v2.graph.node",
                attributes={
                    "agent_id": self._definition.agent_id,
                    "node_id": node_id,
                    "step_index": steps,
                },
            )
            with _graph_phase_timer(
                metrics=self._services.metrics,
                binding=self._binding,
                agent_id=self._definition.agent_id,
                phase="v2_graph_node",
                agent_step=node_id,
                extra_dims={"node_id": node_id},
            ) as kpi_dims:
                try:
                    raw_result = handler(state, node_context)
                    result = (
                        await raw_result
                        if inspect.isawaitable(raw_result)
                        else cast(GraphNodeResult, raw_result)
                    )
                    result = GraphNodeResult.model_validate(result)
                    if node_span is not None:
                        node_span.set_attribute("status", "ok")
                except _AwaitHumanInterrupt as interrupt:
                    kpi_dims["status"] = "awaiting_human"
                    if node_span is not None:
                        node_span.set_attribute("status", "awaiting_human")
                    pending_checkpoint = _PendingGraphCheckpoint(
                        state=state,
                        node_id=node_id,
                        request=interrupt.request,
                    )
                    pending_checkpoint = await self._store_pending_checkpoint(
                        checkpoint_key=checkpoint_key,
                        config=config,
                        pending=pending_checkpoint,
                    )
                    self._pending_checkpoints[checkpoint_key] = pending_checkpoint
                    if emit_event is not None:
                        request = pending_checkpoint.request
                        if pending_checkpoint.checkpoint_id is not None:
                            request = request.model_copy(
                                update={
                                    "checkpoint_id": pending_checkpoint.checkpoint_id
                                }
                            )
                        emit_event(
                            AwaitingHumanRuntimeEvent(sequence=0, request=request)
                        )
                        return self._definition.output_model().model_construct()
                    raise RuntimeError(
                        "Graph execution is awaiting human input. Use stream() to surface the request."
                    ) from interrupt
                except Exception as node_exc:
                    if node_span is not None:
                        node_span.set_attribute("status", "error")
                    on_error_target = self._nodes_by_id[node_id].on_error
                    if on_error_target is not None:
                        # Graceful error recovery: merge 'node_error' into state,
                        # emit a structured event, and continue at the declared
                        # fallback node instead of crashing the whole execution.
                        logger.warning(
                            "[V2][GRAPH] Node %r raised; routing to on_error=%r. agent=%s error=%s",
                            node_id,
                            on_error_target,
                            self._definition.agent_id,
                            node_exc,
                        )
                        if emit_event is not None:
                            emit_event(
                                NodeErrorRuntimeEvent(
                                    sequence=0,
                                    node_id=node_id,
                                    error_message=str(node_exc),
                                    routed_to=on_error_target,
                                )
                            )
                        state = _merge_state(state, {"node_error": str(node_exc)})
                        node_id = on_error_target
                        continue
                    raise
                finally:
                    if node_span is not None:
                        node_span.end()

            if emit_event is not None:
                for event in node_context.events:
                    # AssistantDeltaRuntimeEvents were already forwarded in
                    # real time via _live_emit inside invoke_model; skip them
                    # here to avoid duplicates. All other event kinds
                    # (status, tool_call, tool_result, thought_*) are still
                    # buffered in _events and emitted after the node completes.
                    if not isinstance(event, AssistantDeltaRuntimeEvent):
                        emit_event(event)

            self._thought_records.extend(node_context.thought_records)

            (
                node_model_name,
                node_token_usage,
                node_finish_reason,
            ) = node_context.last_model_metadata
            self._record_model_metadata(
                model_name=node_model_name,
                token_usage=node_token_usage,
                finish_reason=node_finish_reason,
            )

            state = _merge_state(state, result.state_update)

            # Check whether this node is a fan-out node for a parallel group.
            parallel_group = self._parallel_groups.get(node_id)
            if parallel_group is not None:
                fan_in_node, members = parallel_group
                steps += len(members)
                if steps >= config.max_steps:
                    raise RuntimeError(
                        f"Graph execution exceeded max_steps={config.max_steps}."
                    )
                state = await self._run_parallel_group(
                    state=state,
                    members=members,
                    emit_event=emit_event,
                )
                node_id = fan_in_node
            else:
                node_id = _next_node_id(
                    graph=self._graph,
                    current_node_id=node_id,
                    route_key=result.route_key,
                )
            resume_payload = None

        self._pending_checkpoints.pop(checkpoint_key, None)
        completed_state = self._definition.build_completed_state(state)
        await self._store_completed_state(
            checkpoint_key=checkpoint_key,
            config=config,
            state=completed_state,
        )
        output_model = self._definition.output_model().model_validate(
            self._definition.build_output(completed_state)
        )
        if self._thought_records and isinstance(output_model, GraphExecutionOutput):
            output_model = output_model.model_copy(
                update={"thought_trace": tuple(self._thought_records)}
            )
        if emit_event is not None:
            emit_event(
                _final_event_from_output(
                    output_model,
                    model_name=self._last_model_name,
                    token_usage=self._last_token_usage,
                    finish_reason=self._last_finish_reason,
                )
            )
        return output_model

    async def _run_parallel_group(
        self,
        *,
        state: BaseModel,
        members: tuple[str, ...],
        emit_event: Callable[[RuntimeEvent], None] | None,
    ) -> BaseModel:
        """
        Execute a set of member nodes concurrently via asyncio.gather.

        Why this exists:
        - fan-out/fan-in parallelism lets IO-bound nodes (tool calls, resource
          fetches) run simultaneously instead of sequentially, which reduces
          latency proportionally to the number of parallel members
        - gather is used instead of threads because all operations are async-
          native; no thread overhead, no GIL contention

        Constraints:
        - member nodes must not call invoke_model (no LLM streaming in parallel;
          token order would be undefined and UX degraded)
        - HITL (request_human_input) is not supported inside member nodes
        - state updates from members are merged in declaration order
          (last-writer-wins per key); authors should write to distinct state fields

        How to use it:
        - called automatically by _execute_loop when the current node_id is a
          registered fan-out node; do not call directly
        """

        async def _run_member(member_id: str) -> Mapping[str, object]:
            handler = self._handlers[member_id]
            # _live_emit is intentionally None: member nodes do not stream
            # tokens (invoke_model is disallowed); buffered events are
            # emitted after gather completes to preserve a coherent order.
            node_context = _GraphNodeExecutionContext(
                binding=self._binding,
                services=self._services,
                model=self._model,
                model_resolver=self._model_for_operation,
                graph_agent_id=self._definition.agent_id,
                node_id=member_id,
                allowed_tool_refs=self._allowed_tool_refs,
                runtime_tools=self._runtime_tools,
                tuning_values=self._definition.tuning_values,
                _live_emit=None,
            )
            node_span = _start_runtime_span(
                services=self._services,
                binding=self._binding,
                name="v2.graph.node",
                attributes={
                    "agent_id": self._definition.agent_id,
                    "node_id": member_id,
                    "parallel": "true",
                },
            )
            with _graph_phase_timer(
                metrics=self._services.metrics,
                binding=self._binding,
                agent_id=self._definition.agent_id,
                phase="v2_graph_node",
                agent_step=member_id,
                extra_dims={"node_id": member_id, "parallel": "true"},
            ):
                try:
                    raw_result = handler(state, node_context)
                    result = (
                        await raw_result
                        if inspect.isawaitable(raw_result)
                        else cast(GraphNodeResult, raw_result)
                    )
                    result = GraphNodeResult.model_validate(result)
                    if node_span is not None:
                        node_span.set_attribute("status", "ok")
                except Exception:
                    if node_span is not None:
                        node_span.set_attribute("status", "error")
                    raise
                finally:
                    if node_span is not None:
                        node_span.end()

            if emit_event is not None:
                for event in node_context.events:
                    emit_event(event)

            self._thought_records.extend(node_context.thought_records)
            return result.state_update

        updates_list = await asyncio.gather(*[_run_member(m) for m in members])

        # Merge all updates into state in declaration order (last-writer-wins).
        merged = state
        for updates in updates_list:
            merged = _merge_state(merged, updates)
        return merged

    async def _starting_point(
        self,
        *,
        input_model: BaseModel,
        config: ExecutionConfig,
    ) -> tuple[BaseModel, str | None, object | None]:
        checkpoint_key = self._checkpoint_key(config)
        if config.resume_payload is not None:
            pending_checkpoint = self._pending_checkpoints.get(checkpoint_key)
            if pending_checkpoint is None:
                pending_checkpoint = await self._load_pending_checkpoint(
                    checkpoint_key=checkpoint_key,
                    config=config,
                )
                if pending_checkpoint is not None:
                    self._pending_checkpoints[checkpoint_key] = pending_checkpoint
            if pending_checkpoint is None:
                if config.checkpoint_id is not None:
                    raise RuntimeError(
                        "Graph execution received a resume payload for a stale or unknown checkpoint."
                    )
                raise RuntimeError(
                    "Graph execution received a resume payload without a pending checkpoint."
                )
            if (
                config.checkpoint_id is not None
                and pending_checkpoint.checkpoint_id is not None
                and config.checkpoint_id != pending_checkpoint.checkpoint_id
            ):
                raise RuntimeError(
                    "Graph execution received a resume payload for a stale or unknown checkpoint."
                )
            return (
                pending_checkpoint.state,
                pending_checkpoint.node_id,
                config.resume_payload,
            )

        previous_state = await self._load_latest_completed_state(
            checkpoint_key=checkpoint_key,
            config=config,
        )
        # The runtime persists the last completed state for the conversation.
        # The agent decides whether that prior state should influence the new
        # turn, for example by remembering a parcel, case, or selected asset.
        # When invoked by another agent, invocation_turns seeds cross-turn
        # context on the first call (previous_state takes priority when it exists).
        initial_state = self._definition.build_turn_state(
            input_model,
            self._binding,
            previous_state=previous_state,
            invocation_turns=config.invocation_turns,
        )
        state = self._definition.state_model().model_validate(initial_state)
        return state, self._graph.entry_node, None

    def _checkpoint_key(self, config: ExecutionConfig) -> str:
        if config.session_id:
            return config.session_id
        runtime_session_id = self._binding.runtime_context.session_id
        if runtime_session_id:
            return runtime_session_id
        portable_session_id = self._binding.portable_context.session_id
        if portable_session_id:
            return portable_session_id
        return "__default__"

    async def _store_pending_checkpoint(
        self,
        *,
        checkpoint_key: str,
        config: ExecutionConfig,
        pending: _PendingGraphCheckpoint,
    ) -> _PendingGraphCheckpoint:
        checkpointer = self._services.checkpointer
        if checkpointer is None:
            return pending

        checkpoint = empty_checkpoint()
        checkpoint_id = str(checkpoint["id"])
        serialized_request = pending.request.model_dump(mode="json")
        serialized_state = pending.state.model_dump(mode="json")
        channel_values = {
            "runtime_kind": "graph_v2",
            "pending": True,
            "pending_checkpoint_id": checkpoint_id,
            "agent_id": self._definition.agent_id,
            "node_id": pending.node_id,
            "request": serialized_request,
            "state": serialized_state,
            "last_completed_state": await self._load_completed_state_payload(
                checkpoint_key=checkpoint_key
            ),
        }
        checkpoint["channel_values"] = channel_values
        checkpoint["channel_versions"] = {
            key: checkpoint_id for key in channel_values.keys()
        }
        stored_config = await self._aput_checkpoint(
            config={
                "configurable": {
                    "thread_id": checkpoint_key,
                    "checkpoint_ns": "",
                    **(
                        {"checkpoint_id": config.checkpoint_id}
                        if config.checkpoint_id
                        else {}
                    ),
                }
            },
            checkpoint=checkpoint,
            metadata={"source": "update", "step": 0, "parents": {}},
            new_versions=dict(checkpoint["channel_versions"]),
        )
        stored_checkpoint_id = (
            cast(dict[str, object], stored_config.get("configurable") or {}).get(
                "checkpoint_id"
            )
            if isinstance(stored_config, dict)
            else None
        )
        resolved_checkpoint_id = (
            str(stored_checkpoint_id)
            if isinstance(stored_checkpoint_id, str)
            else checkpoint_id
        )
        return _PendingGraphCheckpoint(
            state=pending.state,
            node_id=pending.node_id,
            request=pending.request.model_copy(
                update={"checkpoint_id": resolved_checkpoint_id}
            ),
            checkpoint_id=resolved_checkpoint_id,
        )

    async def _load_pending_checkpoint(
        self,
        *,
        checkpoint_key: str,
        config: ExecutionConfig,
    ) -> _PendingGraphCheckpoint | None:
        checkpointer = self._services.checkpointer
        if checkpointer is None:
            return None

        checkpoint_tuple = await self._get_checkpoint_tuple(
            config={
                "configurable": {
                    "thread_id": checkpoint_key,
                    "checkpoint_ns": "",
                }
            }
        )
        if checkpoint_tuple is None:
            return None
        checkpoint = checkpoint_tuple.checkpoint
        channel_values = checkpoint.get("channel_values", {})
        if not isinstance(channel_values, dict):
            return None
        if channel_values.get("runtime_kind") != "graph_v2":
            return None
        if channel_values.get("pending") is not True:
            return None

        raw_state = channel_values.get("state")
        raw_node_id = channel_values.get("node_id")
        raw_request = channel_values.get("request")
        raw_checkpoint_id = (
            channel_values.get("pending_checkpoint_id")
            or checkpoint.get("id")
            or config.checkpoint_id
        )
        if not isinstance(raw_state, dict) or not isinstance(raw_node_id, str):
            return None

        state = self._definition.state_model().model_validate(raw_state)
        request = HumanInputRequest.model_validate(raw_request or {})
        checkpoint_id = (
            str(raw_checkpoint_id) if isinstance(raw_checkpoint_id, str) else None
        )
        if checkpoint_id is not None:
            request = request.model_copy(update={"checkpoint_id": checkpoint_id})
        return _PendingGraphCheckpoint(
            state=state,
            node_id=raw_node_id,
            request=request,
            checkpoint_id=checkpoint_id,
        )

    async def _clear_pending_checkpoint(
        self, *, checkpoint_key: str, config: ExecutionConfig
    ) -> None:
        await self._store_graph_checkpoint(
            checkpoint_key=checkpoint_key,
            config=config,
            pending=False,
            checkpoint_id=None,
            node_id=None,
            request=None,
            state=None,
            completed_state=await self._load_completed_state_payload(
                checkpoint_key=checkpoint_key
            ),
        )

    async def _store_completed_state(
        self,
        *,
        checkpoint_key: str,
        config: ExecutionConfig,
        state: BaseModel,
    ) -> None:
        await self._store_graph_checkpoint(
            checkpoint_key=checkpoint_key,
            config=config,
            pending=False,
            checkpoint_id=None,
            node_id=None,
            request=None,
            state=None,
            completed_state=state.model_dump(mode="json"),
        )

    async def _store_graph_checkpoint(
        self,
        *,
        checkpoint_key: str,
        config: ExecutionConfig,
        pending: bool,
        checkpoint_id: str | None,
        node_id: str | None,
        request: dict[str, object] | None,
        state: dict[str, object] | None,
        completed_state: dict[str, object] | None,
    ) -> None:
        checkpointer = self._services.checkpointer
        if checkpointer is None:
            return

        checkpoint = empty_checkpoint()
        stored_checkpoint_id = str(checkpoint["id"])
        channel_values = {
            "runtime_kind": "graph_v2",
            "pending": pending,
            "pending_checkpoint_id": checkpoint_id,
            "agent_id": self._definition.agent_id,
            "node_id": node_id,
            "request": request,
            "state": state,
            "last_completed_state": completed_state,
        }
        checkpoint["channel_values"] = channel_values
        checkpoint["channel_versions"] = {
            key: stored_checkpoint_id for key in channel_values.keys()
        }
        await self._aput_checkpoint(
            config={
                "configurable": {
                    "thread_id": checkpoint_key,
                    "checkpoint_ns": "",
                    **(
                        {"checkpoint_id": config.checkpoint_id}
                        if config.checkpoint_id
                        else {}
                    ),
                }
            },
            checkpoint=checkpoint,
            metadata={"source": "update", "step": 0, "parents": {}},
            new_versions=dict(checkpoint["channel_versions"]),
        )

    async def _load_completed_state_payload(
        self, *, checkpoint_key: str
    ) -> dict[str, object] | None:
        checkpointer = self._services.checkpointer
        if checkpointer is None:
            return None
        checkpoint_tuple = await self._get_checkpoint_tuple(
            config={"configurable": {"thread_id": checkpoint_key, "checkpoint_ns": ""}}
        )
        if checkpoint_tuple is None:
            return None
        checkpoint = checkpoint_tuple.checkpoint
        channel_values = checkpoint.get("channel_values", {})
        if not isinstance(channel_values, dict):
            return None
        raw_completed_state = channel_values.get("last_completed_state")
        if isinstance(raw_completed_state, dict):
            return cast(dict[str, object], raw_completed_state)
        return None

    async def _load_latest_completed_state(
        self,
        *,
        checkpoint_key: str,
        config: ExecutionConfig,
    ) -> BaseModel | None:
        del config
        raw_completed_state = await self._load_completed_state_payload(
            checkpoint_key=checkpoint_key
        )
        if raw_completed_state is None:
            return None
        return self._definition.state_model().model_validate(raw_completed_state)

    async def _aput_checkpoint(
        self,
        *,
        config: Mapping[str, object],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Mapping[str, str | int | float],
    ) -> Mapping[str, object]:
        checkpointer = cast(AsyncCheckpointWriter | None, self._services.checkpointer)
        if checkpointer is None:
            return config
        try:
            return cast(
                Mapping[str, object],
                await checkpointer.aput(
                    cast(
                        RunnableConfig,
                        {
                            "configurable": dict(
                                cast(Mapping[str, object], config["configurable"])
                            )
                        },
                    ),
                    checkpoint,
                    metadata,
                    new_versions,
                ),
            )
        except AttributeError as exc:
            raise RuntimeError(
                "Configured graph checkpointer must implement async aput()."
            ) from exc

    async def _get_checkpoint_tuple(
        self, *, config: Mapping[str, object]
    ) -> _CheckpointTupleLike | None:
        checkpointer = cast(AsyncCheckpointReader | None, self._services.checkpointer)
        if checkpointer is None:
            return None
        try:
            return cast(
                _CheckpointTupleLike | None,
                await checkpointer.aget_tuple(
                    cast(
                        RunnableConfig,
                        {
                            "configurable": dict(
                                cast(Mapping[str, object], config["configurable"])
                            )
                        },
                    )
                ),
            )
        except AttributeError as exc:
            raise RuntimeError(
                "Configured graph checkpointer must implement async aget_tuple()."
            ) from exc


class GraphRuntime(AgentRuntime[GraphAgentDefinition, BaseModel, BaseModel]):
    """
    Runtime implementation for `GraphAgentDefinition`.

    Where to look when debugging:
    - runtime tool/model wiring: `on_activate(...)`
    - executor construction: `build_executor(...)`
    - pending HITL lifecycle: `_pending_checkpoints`
    """

    def __init__(self, *, definition: GraphAgentDefinition, services: RuntimeServices):
        super().__init__(definition=definition, services=services)
        self._model: BaseChatModel | None = None
        # Session-scoped pending checkpoints must survive executor rebuilds on bind().
        self._pending_checkpoints: dict[str, _PendingGraphCheckpoint] = {}

    def on_bind(self, binding: BoundRuntimeContext) -> None:
        if self.services.tool_provider is not None:
            self.services.tool_provider.bind(binding)
        if self.services.artifact_publisher is not None:
            self.services.artifact_publisher.bind(binding)
        if self.services.resource_reader is not None:
            self.services.resource_reader.bind(binding)

    async def on_activate(self, binding: BoundRuntimeContext) -> None:
        if self.services.chat_model_factory is not None:
            self._model = cast(
                BaseChatModel,
                self.services.chat_model_factory.build(self.definition, binding),
            )
        if self.services.tool_provider is not None:
            await self.services.tool_provider.activate()

    async def build_executor(
        self, binding: BoundRuntimeContext
    ) -> Executor[BaseModel, BaseModel]:
        runtime_tools = (
            cast(tuple[BaseTool, ...], self.services.tool_provider.get_tools())
            if self.services.tool_provider is not None
            else ()
        )
        return _DeterministicGraphExecutor(
            definition=self.definition,
            binding=binding,
            services=self.services,
            model=self._model,
            runtime_tools=runtime_tools,
            pending_checkpoints=self._pending_checkpoints,
        )

    async def on_dispose(self) -> None:
        if self.services.tool_provider is not None:
            await self.services.tool_provider.aclose()
        self._model = None
        self._pending_checkpoints.clear()


def _validated_handlers(
    *, definition: GraphAgentDefinition, graph: GraphDefinition
) -> dict[str, GraphNodeHandler]:
    raw_handlers = dict(definition.node_handlers())
    validated: dict[str, GraphNodeHandler] = {}
    for node in graph.nodes:
        handler = raw_handlers.get(node.node_id)
        if not callable(handler):
            raise RuntimeError(
                f"Graph runtime is missing an executable handler for node '{node.node_id}'."
            )
        validated[node.node_id] = cast(GraphNodeHandler, handler)
    return validated


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
        groups=binding.runtime_context.user_groups,
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
        try:
            return tracer.start_span(name=name, attributes=span_attributes)
        except Exception:
            return None


def _runtime_observability_dims(
    *, binding: BoundRuntimeContext
) -> dict[str, str | None]:
    """
    Derive the shared observability identity set for one bound execution.

    Why this exists:
    - runtime KPI rows and spans must preserve the same managed execution
      identity across execute, resume, and HITL flows
    - centralising the projection avoids drift between metrics and tracing

    How to use it:
    - call from span/timer helpers right before emitting observability payloads
    - prefer adding new managed identity fields here rather than duplicating
      ad hoc dims at each call site

    Example:
    - `dims = _runtime_observability_dims(binding=binding)`
    """

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
        "checkpoint_id": baggage.get("checkpoint_id"),
        "execution_action": baggage.get("execution_action"),
    }


def _resolve_model_name(model: BaseChatModel) -> str | None:
    for attr_name in ("model_name", "model"):
        raw_value = getattr(model, attr_name, None)
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
    return None


def _merge_state(state: BaseModel, update: Mapping[str, object]) -> BaseModel:
    if not update:
        return state
    return state.model_copy(update=dict(update))


def _next_node_id(
    *,
    graph: GraphDefinition,
    current_node_id: str,
    route_key: str | None,
) -> str | None:
    direct_edges = [edge for edge in graph.edges if edge.source == current_node_id]
    conditional = _conditional_for_node(graph, current_node_id)

    if conditional is not None and direct_edges:
        raise RuntimeError(
            f"Node '{current_node_id}' mixes direct edges and conditional routes."
        )

    if conditional is not None:
        resolved_route_key = route_key or conditional.default_route_key
        if not resolved_route_key:
            raise RuntimeError(
                f"Node '{current_node_id}' requires a route_key but none was returned."
            )
        for route in conditional.routes:
            if route.route_key == resolved_route_key:
                return route.target
        raise RuntimeError(
            f"Node '{current_node_id}' returned unknown route_key '{resolved_route_key}'."
        )

    if not direct_edges:
        return None
    if len(direct_edges) > 1:
        raise RuntimeError(
            f"Node '{current_node_id}' has multiple direct edges; use conditionals instead."
        )
    return direct_edges[0].target


def _conditional_for_node(
    graph: GraphDefinition, node_id: str
) -> GraphConditionalDefinition | None:
    for conditional in graph.conditionals:
        if conditional.source == node_id:
            return conditional
    return None


def _resequence_event(event: RuntimeEvent, sequence: int) -> RuntimeEvent:
    return cast(RuntimeEvent, event.model_copy(update={"sequence": sequence}))


def _final_event_from_output(
    output_model: BaseModel,
    *,
    model_name: str | None = None,
    token_usage: dict[str, int] | None = None,
    finish_reason: str | None = None,
) -> FinalRuntimeEvent:
    """
    Build the canonical FinalRuntimeEvent from a graph output model.

    Why this exists:
    - graph agents can return either GraphExecutionOutput or a custom output model
    - the runtime still needs one consistent final event shape for the UI

    How to use:
    - pass the validated output model plus optional model metadata captured during execution

    Example:
    - `event = _final_event_from_output(output_model, model_name=name, token_usage=usage)`
    """

    if isinstance(output_model, GraphExecutionOutput):
        return FinalRuntimeEvent(
            sequence=0,
            content=output_model.content,
            sources=output_model.sources,
            ui_parts=output_model.ui_parts,
            model_name=model_name,
            token_usage=token_usage or output_model.token_usage,
            finish_reason=finish_reason,
        )

    payload = output_model.model_dump(mode="json")
    content = payload.get("content")
    if not isinstance(content, str):
        content = json.dumps(payload, ensure_ascii=False, indent=2)
    return FinalRuntimeEvent(
        sequence=0,
        content=content,
        model_name=model_name,
        token_usage=token_usage,
        finish_reason=finish_reason,
    )


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
    if isinstance(raw, tuple) and len(raw) == 2:
        content, artifact = raw
        normalized_artifact = _normalize_runtime_tool_output(artifact)
        if isinstance(normalized_artifact, (dict, list)):
            return normalized_artifact
        raw = normalize_mcp_content(content)

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
