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

import inspect
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Protocol, cast

from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_core.store import VectorSearchHit
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, empty_checkpoint
from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.common.tool_node_utils import normalize_mcp_content

from .checkpoints import AsyncCheckpointReader, AsyncCheckpointWriter
from .context import (
    ArtifactPublishRequest,
    ArtifactScope,
    BoundRuntimeContext,
    FetchedResource,
    PublishedArtifact,
    ResourceFetchRequest,
    ResourceScope,
    ToolInvocationRequest,
    ToolInvocationResult,
    UiPart,
)
from .model_routing.provider import RoutedChatModelFactory
from .models import (
    GraphAgentDefinition,
    GraphConditionalDefinition,
    GraphDefinition,
    ToolRefRequirement,
)
from .runtime import (
    AgentRuntime,
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    Executor,
    FinalRuntimeEvent,
    HumanInputRequest,
    RuntimeEvent,
    RuntimeServices,
    StatusRuntimeEvent,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
    WorkspaceClientPort,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class GraphExecutionOutput(FrozenModel):
    """Final user-facing outcome of a graph run."""

    content: str = ""
    sources: tuple[VectorSearchHit, ...] = ()
    ui_parts: tuple[UiPart, ...] = ()


class GraphNodeResult(FrozenModel):
    """Result of one business step in the graph."""

    state_update: dict[str, object] = Field(default_factory=dict)
    route_key: str | None = None


class GraphNodeContext(Protocol):
    """
    Runtime capabilities available inside one node handler.

    Node handlers should stay business-focused: read state, call these methods,
    return `GraphNodeResult`. Orchestration and persistence are handled by the
    runtime executor.
    """

    @property
    def binding(self) -> BoundRuntimeContext:
        raise NotImplementedError()

    @property
    def services(self) -> RuntimeServices:
        raise NotImplementedError()

    @property
    def model(self) -> BaseChatModel | None:
        raise NotImplementedError()

    @property
    def workspace_client(self) -> WorkspaceClientPort | None:
        raise NotImplementedError()

    def emit_status(self, status: str, detail: str | None = None) -> None:
        raise NotImplementedError()

    def emit_assistant_delta(self, delta: str) -> None:
        raise NotImplementedError()

    async def invoke_model(
        self,
        messages: list[BaseMessage],
        *,
        operation: str = "default",
    ) -> BaseMessage:
        raise NotImplementedError()

    async def invoke_tool(
        self, tool_ref: str, payload: dict[str, object]
    ) -> ToolInvocationResult:
        raise NotImplementedError()

    async def invoke_runtime_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> object:
        raise NotImplementedError()

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
        raise NotImplementedError()

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
        raise NotImplementedError()

    async def fetch_resource(
        self,
        *,
        key: str,
        scope: ResourceScope = ResourceScope.AGENT_CONFIG,
        target_user_id: str | None = None,
    ) -> FetchedResource:
        raise NotImplementedError()

    async def fetch_text_resource(
        self,
        *,
        key: str,
        scope: ResourceScope = ResourceScope.AGENT_CONFIG,
        target_user_id: str | None = None,
        encoding: str = "utf-8",
    ) -> str:
        raise NotImplementedError()

    async def request_human_input(self, request: HumanInputRequest) -> object:
        raise NotImplementedError()


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
    workspace_client: WorkspaceClientPort | None
    graph_agent_id: str
    node_id: str
    allowed_tool_refs: frozenset[str]
    runtime_tools: Mapping[str, BaseTool]
    _events: list[RuntimeEvent] = field(default_factory=list)
    _resume_payload: object | None = None

    @property
    def events(self) -> tuple[RuntimeEvent, ...]:
        return tuple(self._events)

    def emit_status(self, status: str, detail: str | None = None) -> None:
        self._events.append(
            StatusRuntimeEvent(sequence=0, status=status, detail=detail)
        )

    def emit_assistant_delta(self, delta: str) -> None:
        self._events.append(AssistantDeltaRuntimeEvent(sequence=0, delta=delta))

    async def invoke_model(
        self,
        messages: list[BaseMessage],
        *,
        operation: str = "default",
    ) -> BaseMessage:
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
            kpi=self.services.kpi,
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
                response = cast(BaseMessage, await resolved_model.ainvoke(messages))
                if span is not None:
                    span.set_attribute("status", "ok")
                return response
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
                kpi=self.services.kpi,
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
            kpi=self.services.kpi,
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
        workspace_client: WorkspaceClientPort | None,
        pending_checkpoints: dict[str, _PendingGraphCheckpoint],
    ) -> None:
        self._definition = definition
        self._binding = binding
        self._services = services
        self._model = model
        self._routed_model_factory = (
            services.chat_model_factory
            if isinstance(services.chat_model_factory, RoutedChatModelFactory)
            else None
        )
        self._models_by_operation: dict[str, BaseChatModel] = {}
        if model is not None:
            self._models_by_operation["default"] = model
        self._runtime_tools = {tool.name: tool for tool in runtime_tools}
        self._workspace_client = workspace_client
        self._graph = definition.build_graph()
        self._handlers = _validated_handlers(definition=definition, graph=self._graph)
        self._allowed_tool_refs = frozenset(
            requirement.tool_ref
            for requirement in definition.tool_requirements
            if isinstance(requirement, ToolRefRequirement)
        )
        self._pending_checkpoints = pending_checkpoints

    def _model_for_operation(self, operation: str) -> BaseChatModel | None:
        cached = self._models_by_operation.get(operation)
        if cached is not None:
            return cached
        if self._routed_model_factory is None:
            return self._model
        model, _ = self._routed_model_factory.build_for_chat(
            definition=self._definition,
            binding=self._binding,
            purpose="chat",
            operation=operation,
        )
        self._models_by_operation[operation] = model
        return model

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
        sequence = 0
        emitted_events: list[RuntimeEvent] = []

        def _collect(event: RuntimeEvent) -> None:
            emitted_events.append(event)

        await self._execute(
            input_model=input_model,
            config=config,
            emit_event=_collect,
        )

        for event in emitted_events:
            yield _resequence_event(event, sequence)
            sequence += 1

    async def _execute(
        self,
        *,
        input_model: BaseModel,
        config: ExecutionConfig,
        emit_event: Callable[[RuntimeEvent], None] | None,
    ) -> BaseModel:
        state, node_id, resume_payload = await self._starting_point(
            input_model=input_model,
            config=config,
        )
        checkpoint_key = self._checkpoint_key(config)
        steps = 0

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
                workspace_client=self._workspace_client,
                graph_agent_id=self._definition.agent_id,
                node_id=node_id,
                allowed_tool_refs=self._allowed_tool_refs,
                runtime_tools=self._runtime_tools,
                _resume_payload=resume_payload,
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
                kpi=self._services.kpi,
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

            state = _merge_state(state, result.state_update)
            node_id = _next_node_id(
                graph=self._graph,
                current_node_id=node_id,
                route_key=result.route_key,
            )
            resume_payload = None

        self._pending_checkpoints.pop(checkpoint_key, None)
        await self._store_completed_state(
            checkpoint_key=checkpoint_key,
            config=config,
            state=state,
        )
        output_model = self._definition.output_model().model_validate(
            self._definition.build_output(state)
        )
        if emit_event is not None:
            emit_event(_final_event_from_output(output_model))
        return output_model

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
        initial_state = self._definition.build_turn_state(
            input_model,
            self._binding,
            previous_state=previous_state,
        )
        state = self._definition.state_model().model_validate(initial_state)
        return state, self._graph.entry_node, None

    def _checkpoint_key(self, config: ExecutionConfig) -> str:
        if config.thread_id:
            return config.thread_id
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
            self._model = self.services.chat_model_factory.build(
                self.definition, binding
            )
        if self.services.tool_provider is not None:
            await self.services.tool_provider.activate()

    async def build_executor(
        self, binding: BoundRuntimeContext
    ) -> Executor[BaseModel, BaseModel]:
        runtime_tools = (
            self.services.tool_provider.get_tools()
            if self.services.tool_provider is not None
            else ()
        )
        return _DeterministicGraphExecutor(
            definition=self.definition,
            binding=binding,
            services=self.services,
            model=self._model,
            runtime_tools=runtime_tools,
            workspace_client=self.workspace_client,
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
    kpi: BaseKPIWriter | None,
    binding: BoundRuntimeContext,
    agent_id: str,
    phase: str,
    agent_step: str,
    extra_dims: Mapping[str, str | None] | None = None,
):
    if kpi is None:
        return nullcontext({})
    dims: dict[str, str | None] = {
        "phase": phase,
        "agent_id": agent_id,
        "agent_step": agent_step,
    }
    if extra_dims:
        dims.update(dict(extra_dims))
    return kpi.timer(
        "app.phase_latency_ms",
        dims=dims,
        actor=KPIActor(
            type="system",
            groups=binding.runtime_context.user_groups,
        ),
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
    try:
        return tracer.start_span(
            name=name,
            context=binding.portable_context,
            attributes=attributes,
        )
    except Exception:
        return None


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


def _final_event_from_output(output_model: BaseModel) -> FinalRuntimeEvent:
    if isinstance(output_model, GraphExecutionOutput):
        return FinalRuntimeEvent(
            sequence=0,
            content=output_model.content,
            sources=output_model.sources,
            ui_parts=output_model.ui_parts,
        )

    payload = output_model.model_dump(mode="json")
    content = payload.get("content")
    if not isinstance(content, str):
        content = json.dumps(payload, ensure_ascii=False, indent=2)
    return FinalRuntimeEvent(sequence=0, content=content)


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
