from __future__ import annotations

import time
from contextlib import AbstractContextManager
from typing import Any, Callable, Iterable, Optional, cast

import pytest
from fred_core.common import ModelConfiguration
from fred_core.kpi import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import Dims, KPIActor, MetricType
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from agentic_backend.core.agents.agent_spec import FieldSpec
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    ArtifactPublisherPort,
    ArtifactPublishRequest,
    AwaitingHumanRuntimeEvent,
    BoundRuntimeContext,
    ChatModelFactoryPort,
    ExecutionConfig,
    FetchedResource,
    FinalRuntimeEvent,
    GraphAgentDefinition,
    GraphConditionalDefinition,
    GraphDefinition,
    GraphEdgeDefinition,
    GraphExecutionOutput,
    GraphNodeContext,
    GraphNodeDefinition,
    GraphNodeResult,
    GraphNodeShape,
    GraphRouteDefinition,
    GraphRuntime,
    HumanChoiceOption,
    HumanInputRequest,
    PortableContext,
    PortableEnvironment,
    PublishedArtifact,
    ResourceFetchRequest,
    ResourceReaderPort,
    ResourceScope,
    RuntimeServices,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolInvokerPort,
    ToolRefRequirement,
    WorkspaceClientFactoryPort,
    WorkspaceClientPort,
    inspect_agent,
)
from agentic_backend.core.agents.v2.model_routing import (
    ModelCapability,
    ModelProfile,
    ModelRouteMatch,
    ModelRouteRule,
    ModelRoutingPolicy,
    ModelRoutingResolver,
    RoutedChatModelFactory,
)


class DemoInput(BaseModel):
    text: str


class DemoState(BaseModel):
    text: str
    lookup_summary: str | None = None
    approved: bool | None = None
    published_report: PublishedArtifact | None = None
    final_text: str | None = None


class DemoWorkspaceClient(WorkspaceClientPort):
    def __init__(self, *, session_id: str | None):
        self.session_id = session_id


class DemoWorkspaceFactory(WorkspaceClientFactoryPort):
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    def build(self, binding: BoundRuntimeContext) -> WorkspaceClientPort:
        session_id = binding.runtime_context.session_id
        self.calls.append(session_id)
        return DemoWorkspaceClient(session_id=session_id)


class DemoToolInvoker(ToolInvokerPort):
    def __init__(self) -> None:
        self.requests: list[ToolInvocationRequest] = []

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        self.requests.append(request)
        query = str(request.payload.get("query") or "")
        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.TEXT,
                    text=f"Lookup summary for {query}",
                ),
            ),
        )


class StaticChatModelFactory(ChatModelFactoryPort):
    def __init__(self, model: FakeMessagesListChatModel) -> None:
        self.model = model

    def build(self, definition, binding: BoundRuntimeContext):  # type: ignore[override]
        del definition, binding
        return self.model


class RecordingRoutingModelProvider:
    def __init__(self, models_by_name: dict[str, FakeMessagesListChatModel]) -> None:
        self._models_by_name = models_by_name
        self.calls: list[tuple[str, str]] = []

    def build_model(  # type: ignore[override]
        self,
        model_config: ModelConfiguration,
        *,
        capability: ModelCapability,
    ) -> object:
        self.calls.append((capability.value, model_config.name))
        return self._models_by_name[model_config.name]


class RecordingKPIWriter(BaseKPIWriter):
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(
        self,
        *,
        name: str,
        type: MetricType,
        value: Optional[float] = None,
        unit: Optional[str] = None,
        dims: Optional[Dims] = None,
        cost: Optional[dict] = None,
        quantities: Optional[dict] = None,
        labels: Optional[Iterable[str]] = None,
        trace: Optional[dict] = None,
        timestamp=None,
        actor: KPIActor,
    ) -> None:
        self.events.append(
            {
                "name": name,
                "type": type,
                "value": value,
                "unit": unit,
                "dims": dict(dims or {}),
                "actor": actor,
            }
        )

    class _Timer(AbstractContextManager[Dims]):
        def __init__(
            self,
            *,
            writer: RecordingKPIWriter,
            name: str,
            dims: Optional[Dims],
            unit: str,
            actor: KPIActor,
        ) -> None:
            self._writer = writer
            self._name = name
            self._dims = dict(dims or {})
            self._unit = unit
            self._actor = actor
            self._start = 0.0

        def __enter__(self) -> Dims:
            self._start = time.perf_counter()
            return self._dims

        def __exit__(self, exc_type, exc, tb) -> bool:
            if exc_type is not None and "status" not in self._dims:
                self._dims["status"] = "error"
            elif "status" not in self._dims:
                self._dims["status"] = "ok"
            elapsed_ms = (time.perf_counter() - self._start) * 1000.0
            self._writer.emit(
                name=self._name,
                type="timer",
                value=elapsed_ms if self._unit == "ms" else elapsed_ms / 1000.0,
                unit=self._unit,
                dims=self._dims,
                actor=self._actor,
            )
            return False

    def timer(
        self,
        name: str,
        *,
        dims: Optional[Dims] = None,
        unit: str = "ms",
        labels: Optional[Iterable[str]] = None,
        actor: KPIActor,
    ) -> AbstractContextManager[Dims]:
        del labels
        return self._Timer(
            writer=self,
            name=name,
            dims=dims,
            unit=unit,
            actor=actor,
        )

    def timed(
        self,
        name: str,
        *,
        unit: str = "ms",
        static_dims: Optional[Dims] = None,
        actor: KPIActor,
    ) -> Callable:
        def decorator(fn: Callable) -> Callable:
            def wrapped(*args: Any, **kwargs: Any):
                with self.timer(name, unit=unit, dims=static_dims, actor=actor):
                    return fn(*args, **kwargs)

            return wrapped

        return decorator

    def count(
        self,
        name: str,
        inc: int = 1,
        *,
        dims: Optional[Dims] = None,
        labels: Optional[Iterable[str]] = None,
        actor: KPIActor,
    ) -> None:
        del labels
        self.emit(
            name=name,
            type="counter",
            value=float(inc),
            unit="count",
            dims=dims,
            actor=actor,
        )

    def gauge(
        self,
        name: str,
        value: float,
        *,
        unit: Optional[str] = None,
        dims: Optional[Dims] = None,
        actor: KPIActor,
    ) -> None:
        self.emit(
            name=name,
            type="gauge",
            value=value,
            unit=unit,
            dims=dims,
            actor=actor,
        )

    def log_llm(self, **kwargs) -> None:
        return None

    def doc_used(self, **kwargs) -> None:
        return None

    def vectorization_result(self, **kwargs) -> None:
        return None

    def api_call(self, **kwargs) -> None:
        return None

    def api_error(self, **kwargs) -> None:
        return None

    def record_error(self, **kwargs) -> None:
        return None


class DemoArtifactPublisher(ArtifactPublisherPort):
    def __init__(self) -> None:
        self.bind_calls: list[str | None] = []
        self.requests: list[ArtifactPublishRequest] = []

    def bind(self, binding: BoundRuntimeContext) -> None:
        self.bind_calls.append(binding.runtime_context.session_id)

    async def publish(self, request: ArtifactPublishRequest) -> PublishedArtifact:
        self.requests.append(request)
        return PublishedArtifact(
            scope=request.scope,
            key=request.key or "v2/demo/report.txt",
            file_name=request.file_name,
            size=len(request.content_bytes),
            href="https://example.test/report.txt",
            mime=request.content_type,
            title=request.title,
        )


class DemoResourceReader(ResourceReaderPort):
    def __init__(self) -> None:
        self.bind_calls: list[str | None] = []
        self.keys: list[str] = []

    def bind(self, binding: BoundRuntimeContext) -> None:
        self.bind_calls.append(binding.runtime_context.session_id)

    async def fetch(self, request: ResourceFetchRequest) -> FetchedResource:
        self.keys.append(request.key)
        return FetchedResource(
            scope=request.scope,
            key=request.key,
            file_name="demo-template.md",
            size=len(b"# Template\n"),
            content_bytes=b"# Template\n",
            content_type="text/markdown; charset=utf-8",
        )


class DemoGraphAgent(GraphAgentDefinition):
    agent_id: str = "demo.graph"
    role: str = "demo"
    description: str = "Demo graph agent"
    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System prompt",
            required=True,
            default="You are a concise demo agent.",
        ),
    )
    tool_requirements: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(tool_ref="search:v1"),
    )

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="DemoState",
            entry_node="lookup",
            nodes=(
                GraphNodeDefinition(
                    node_id="lookup",
                    title="Lookup context",
                    shape=GraphNodeShape.ROUND,
                ),
                GraphNodeDefinition(
                    node_id="approval",
                    title="Request approval",
                    shape=GraphNodeShape.DIAMOND,
                ),
                GraphNodeDefinition(
                    node_id="approved",
                    title="Approved path",
                ),
                GraphNodeDefinition(
                    node_id="rejected",
                    title="Rejected path",
                ),
            ),
            edges=(GraphEdgeDefinition(source="lookup", target="approval"),),
            conditionals=(
                GraphConditionalDefinition(
                    source="approval",
                    routes=(
                        GraphRouteDefinition(
                            route_key="approved",
                            target="approved",
                            label="approved",
                        ),
                        GraphRouteDefinition(
                            route_key="rejected",
                            target="rejected",
                            label="rejected",
                        ),
                    ),
                ),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return DemoInput

    def state_model(self) -> type[BaseModel]:
        return DemoState

    def output_model(self) -> type[BaseModel]:
        return GraphExecutionOutput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        model = cast(DemoInput, input_model)
        return DemoState(text=model.text)

    def node_handlers(self) -> dict[str, object]:
        return {
            "lookup": self.lookup,
            "approval": self.approval,
            "approved": self.approved,
            "rejected": self.rejected,
        }

    def build_output(self, state: BaseModel) -> BaseModel:
        graph_state = cast(DemoState, state)
        ui_parts = ()
        if graph_state.published_report is not None:
            ui_parts = (graph_state.published_report.to_link_part(),)
        return GraphExecutionOutput(
            content=graph_state.final_text or "",
            ui_parts=ui_parts,
        )

    async def lookup(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = cast(DemoState, state)
        workspace = cast(DemoWorkspaceClient | None, context.workspace_client)
        session_hint = workspace.session_id if workspace is not None else "n/a"
        context.emit_status("lookup", f"session={session_hint}")
        context.emit_assistant_delta("Looking up context...")
        result = await context.invoke_tool("search:v1", {"query": graph_state.text})
        summary = result.blocks[0].text if result.blocks else "n/a"
        return GraphNodeResult(
            state_update={
                "lookup_summary": summary,
            }
        )

    async def approval(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = cast(DemoState, state)
        decision = await context.request_human_input(
            HumanInputRequest(
                title="Approve demo action",
                question="Should the workflow continue?",
                choices=(
                    HumanChoiceOption(id="approved", label="Approve", default=True),
                    HumanChoiceOption(id="rejected", label="Reject"),
                ),
                metadata={"lookup_summary": graph_state.lookup_summary or ""},
            )
        )
        choice_id = str(
            cast(dict[str, object], decision).get("choice_id") or "rejected"
        )
        approved = choice_id == "approved"
        return GraphNodeResult(
            state_update={"approved": approved},
            route_key="approved" if approved else "rejected",
        )

    async def approved(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = cast(DemoState, state)
        artifact = await context.publish_text(
            file_name="demo-report.txt",
            text=f"Approved flow with {graph_state.lookup_summary}",
            title="Open generated report",
            content_type="text/plain; charset=utf-8",
        )
        return GraphNodeResult(
            state_update={
                "published_report": artifact,
                "final_text": f"Approved flow with {graph_state.lookup_summary}",
            }
        )

    async def rejected(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = cast(DemoState, state)
        return GraphNodeResult(
            state_update={
                "final_text": f"Rejected flow after {graph_state.lookup_summary}",
            }
        )


class ResourceGraphAgent(GraphAgentDefinition):
    agent_id: str = "resource.graph"
    role: str = "resource demo"
    description: str = "Resource fetch demo graph agent"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="DemoState",
            entry_node="read_template",
            nodes=(
                GraphNodeDefinition(node_id="read_template", title="Read template"),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return DemoInput

    def state_model(self) -> type[BaseModel]:
        return DemoState

    def output_model(self) -> type[BaseModel]:
        return GraphExecutionOutput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        model = cast(DemoInput, input_model)
        return DemoState(text=model.text)

    def node_handlers(self) -> dict[str, object]:
        return {"read_template": self.read_template}

    def build_output(self, state: BaseModel) -> BaseModel:
        graph_state = cast(DemoState, state)
        return GraphExecutionOutput(content=graph_state.final_text or "")

    async def read_template(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        template = await context.fetch_text_resource(
            key="report-template.md",
            scope=ResourceScope.AGENT_CONFIG,
        )
        return GraphNodeResult(
            state_update={"final_text": f"Loaded template: {template.strip()}"}
        )


class ModelGraphAgent(GraphAgentDefinition):
    agent_id: str = "model.graph"
    role: str = "model demo"
    description: str = "Model invocation demo graph agent"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="DemoState",
            entry_node="draft",
            nodes=(GraphNodeDefinition(node_id="draft", title="Draft response"),),
        )

    def input_model(self) -> type[BaseModel]:
        return DemoInput

    def state_model(self) -> type[BaseModel]:
        return DemoState

    def output_model(self) -> type[BaseModel]:
        return GraphExecutionOutput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        del binding
        model = cast(DemoInput, input_model)
        return DemoState(text=model.text)

    def node_handlers(self) -> dict[str, object]:
        return {"draft": self.draft}

    def build_output(self, state: BaseModel) -> BaseModel:
        graph_state = cast(DemoState, state)
        return GraphExecutionOutput(content=graph_state.final_text or "")

    async def draft(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = cast(DemoState, state)
        response = await context.invoke_model(
            [HumanMessage(content=graph_state.text)],
            operation="draft_summary",
        )
        return GraphNodeResult(
            state_update={"final_text": cast(str, getattr(response, "content", ""))}
        )


class MultiModelGraphState(BaseModel):
    text: str
    draft_text: str = ""
    final_text: str | None = None


class MultiModelGraphAgent(GraphAgentDefinition):
    agent_id: str = "multi_model.graph"
    role: str = "multi model graph demo"
    description: str = "Graph agent testing operation-based routed models."

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="MultiModelGraphState",
            entry_node="draft",
            nodes=(
                GraphNodeDefinition(node_id="draft", title="Draft"),
                GraphNodeDefinition(node_id="self_check", title="Self-check"),
            ),
            edges=(GraphEdgeDefinition(source="draft", target="self_check"),),
        )

    def input_model(self) -> type[BaseModel]:
        return DemoInput

    def state_model(self) -> type[BaseModel]:
        return MultiModelGraphState

    def output_model(self) -> type[BaseModel]:
        return GraphExecutionOutput

    def build_initial_state(
        self, input_model: BaseModel, binding: BoundRuntimeContext
    ) -> BaseModel:
        del binding
        model = cast(DemoInput, input_model)
        return MultiModelGraphState(text=model.text)

    def node_handlers(self) -> dict[str, object]:
        return {"draft": self.draft, "self_check": self.self_check}

    def build_output(self, state: BaseModel) -> BaseModel:
        graph_state = cast(MultiModelGraphState, state)
        return GraphExecutionOutput(content=graph_state.final_text or "")

    async def draft(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = cast(MultiModelGraphState, state)
        response = await context.invoke_model(
            [HumanMessage(content=graph_state.text)],
            operation="generate_draft",
        )
        return GraphNodeResult(
            state_update={"draft_text": cast(str, getattr(response, "content", ""))}
        )

    async def self_check(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = cast(MultiModelGraphState, state)
        response = await context.invoke_model(
            [HumanMessage(content=graph_state.draft_text)],
            operation="self_check",
        )
        return GraphNodeResult(
            state_update={"final_text": cast(str, getattr(response, "content", ""))}
        )


def _binding(session_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id=session_id, user_id="user-1"),
        portable_context=PortableContext(
            request_id=f"req-{session_id}",
            correlation_id=f"corr-{session_id}",
            actor="user:demo",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            agent_id="demo.graph",
        ),
    )


def test_graph_agent_inspection_is_pure_and_structured() -> None:
    definition = DemoGraphAgent()

    inspection = inspect_agent(definition)

    assert inspection.agent_id == "demo.graph"
    assert inspection.execution_category.value == "graph"
    assert len(inspection.fields) == 1
    assert len(inspection.tool_requirements) == 1
    assert inspection.preview.kind.value == "mermaid"
    assert "flowchart TD;" in inspection.preview.content
    assert "Lookup context" in inspection.preview.content
    assert "Request approval" in inspection.preview.content


def test_graph_definition_rejects_dangling_edges() -> None:
    with pytest.raises(ValueError, match="target='missing'"):
        GraphDefinition(
            state_model_name="BrokenState",
            entry_node="start",
            nodes=(GraphNodeDefinition(node_id="start", title="Start"),),
            edges=(GraphEdgeDefinition(source="start", target="missing"),),
        )


@pytest.mark.asyncio
async def test_graph_runtime_rebind_rebuilds_context_scoped_helpers() -> None:
    definition = DemoGraphAgent()
    workspace_factory = DemoWorkspaceFactory()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(workspace_client_factory=workspace_factory),
    )

    runtime.bind(_binding("s1"))
    first_executor = await runtime.get_executor()
    assert workspace_factory.calls == ["s1"]
    assert isinstance(runtime.workspace_client, DemoWorkspaceClient)
    assert runtime.workspace_client.session_id == "s1"

    runtime.bind(_binding("s2"))
    second_executor = await runtime.get_executor()

    assert workspace_factory.calls == ["s1", "s2"]
    assert isinstance(runtime.workspace_client, DemoWorkspaceClient)
    assert runtime.workspace_client.session_id == "s2"
    assert first_executor is not second_executor


@pytest.mark.asyncio
async def test_graph_runtime_supports_tool_calls_hitl_resume_and_structured_output() -> (
    None
):
    definition = DemoGraphAgent()
    tool_invoker = DemoToolInvoker()
    artifact_publisher = DemoArtifactPublisher()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_invoker=tool_invoker,
            artifact_publisher=artifact_publisher,
        ),
    )
    runtime.bind(_binding("s1"))
    executor = await runtime.get_executor()

    first_run = [
        event
        async for event in executor.stream(
            DemoInput(text="parcel-123"),
            ExecutionConfig(),
        )
    ]

    assert [event.kind.value for event in first_run] == [
        "status",
        "assistant_delta",
        "tool_call",
        "tool_result",
        "awaiting_human",
    ]
    assert tool_invoker.requests[0].tool_ref == "search:v1"
    waiting_event = cast(AwaitingHumanRuntimeEvent, first_run[-1])
    assert waiting_event.request.title == "Approve demo action"

    resumed_run = [
        event
        async for event in executor.stream(
            DemoInput(text="ignored-on-resume"),
            ExecutionConfig(resume_payload={"choice_id": "approved"}),
        )
    ]

    assert [event.kind.value for event in resumed_run] == ["final"]
    final_event = cast(FinalRuntimeEvent, resumed_run[0])
    assert "Approved flow with Lookup summary for parcel-123" in final_event.content
    assert len(final_event.ui_parts) == 1
    assert final_event.ui_parts[0].type == "link"
    assert artifact_publisher.bind_calls == ["s1"]
    assert artifact_publisher.requests[0].file_name == "demo-report.txt"
    assert artifact_publisher.requests[0].content_bytes.startswith(
        b"Approved flow with"
    )


@pytest.mark.asyncio
async def test_graph_runtime_emits_phase_metrics_per_node_and_tool_call() -> None:
    definition = DemoGraphAgent()
    tool_invoker = DemoToolInvoker()
    kpi = RecordingKPIWriter()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_invoker=tool_invoker,
            kpi=kpi,
        ),
    )
    runtime.bind(_binding("metrics-session"))

    executor = await runtime.get_executor()
    _ = [
        event
        async for event in executor.stream(
            DemoInput(text="parcel-456"),
            ExecutionConfig(),
        )
    ]

    phase_events = [
        event for event in kpi.events if event["name"] == "app.phase_latency_ms"
    ]

    assert len(phase_events) >= 3
    assert any(
        event["dims"].get("phase") == "v2_graph_node"
        and event["dims"].get("agent_id") == "demo.graph"
        and event["dims"].get("agent_step") == "lookup"
        and event["dims"].get("status") == "ok"
        for event in phase_events
    )
    assert any(
        event["dims"].get("phase") == "v2_graph_tool"
        and event["dims"].get("agent_id") == "demo.graph"
        and event["dims"].get("agent_step") == "lookup:search:v1"
        and event["dims"].get("tool_name") == "search:v1"
        and event["dims"].get("status") == "ok"
        for event in phase_events
    )
    assert any(
        event["dims"].get("phase") == "v2_graph_node"
        and event["dims"].get("agent_step") == "approval"
        and event["dims"].get("status") == "awaiting_human"
        for event in phase_events
    )


@pytest.mark.asyncio
async def test_graph_runtime_fetches_agent_resources_through_typed_reader() -> None:
    resource_reader = DemoResourceReader()
    runtime = GraphRuntime(
        definition=ResourceGraphAgent(),
        services=RuntimeServices(resource_reader=resource_reader),
    )
    runtime.bind(_binding("resource-session"))

    executor = await runtime.get_executor()
    output = await executor.invoke(
        DemoInput(text="load template"),
        ExecutionConfig(),
    )

    assert output.content == "Loaded template: # Template"
    assert resource_reader.bind_calls == ["resource-session"]
    assert resource_reader.keys == ["report-template.md"]


@pytest.mark.asyncio
async def test_graph_runtime_emits_phase_metrics_for_model_invocation() -> None:
    kpi = RecordingKPIWriter()
    runtime = GraphRuntime(
        definition=ModelGraphAgent(),
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(
                FakeMessagesListChatModel(
                    responses=[AIMessage(content="Model draft complete")]
                )
            ),
            kpi=kpi,
        ),
    )
    runtime.bind(_binding("model-session"))

    executor = await runtime.get_executor()
    output = await executor.invoke(
        DemoInput(text="prepare a short summary"),
        ExecutionConfig(),
    )

    assert output.content == "Model draft complete"
    phase_events = [
        event for event in kpi.events if event["name"] == "app.phase_latency_ms"
    ]
    assert any(
        event["dims"].get("phase") == "v2_graph_model"
        and event["dims"].get("agent_id") == "model.graph"
        and event["dims"].get("agent_step") == "draft:draft_summary"
        and event["dims"].get("node_id") == "draft"
        and event["dims"].get("operation") == "draft_summary"
        and event["dims"].get("status") == "ok"
        for event in phase_events
    )


@pytest.mark.asyncio
async def test_graph_runtime_routes_model_per_operation_with_routed_factory() -> None:
    definition = MultiModelGraphAgent()
    provider = RecordingRoutingModelProvider(
        {
            "default-model": FakeMessagesListChatModel(
                responses=[AIMessage(content="default response")]
            ),
            "draft-model": FakeMessagesListChatModel(
                responses=[AIMessage(content="draft response")]
            ),
            "check-model": FakeMessagesListChatModel(
                responses=[AIMessage(content="checked response")]
            ),
        }
    )
    policy = ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: "profile.default"},
        profiles=(
            ModelProfile(
                profile_id="profile.default",
                capability=ModelCapability.CHAT,
                model=ModelConfiguration(
                    provider="openai",
                    name="default-model",
                    settings={},
                ),
            ),
            ModelProfile(
                profile_id="profile.draft",
                capability=ModelCapability.CHAT,
                model=ModelConfiguration(
                    provider="openai",
                    name="draft-model",
                    settings={},
                ),
            ),
            ModelProfile(
                profile_id="profile.check",
                capability=ModelCapability.CHAT,
                model=ModelConfiguration(
                    provider="openai",
                    name="check-model",
                    settings={},
                ),
            ),
        ),
        rules=(
            ModelRouteRule(
                rule_id="graph.generate_draft",
                capability=ModelCapability.CHAT,
                target_profile_id="profile.draft",
                match=ModelRouteMatch(
                    purpose="chat",
                    agent_id=definition.agent_id,
                    operation="generate_draft",
                ),
            ),
            ModelRouteRule(
                rule_id="graph.self_check",
                capability=ModelCapability.CHAT,
                target_profile_id="profile.check",
                match=ModelRouteMatch(
                    purpose="chat",
                    agent_id=definition.agent_id,
                    operation="self_check",
                ),
            ),
        ),
    )
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=RoutedChatModelFactory(
                resolver=ModelRoutingResolver(policy),
                provider=provider,
                default_purpose="chat",
            )
        ),
    )
    runtime.bind(_binding("graph-model-routing"))

    executor = await runtime.get_executor()
    output = await executor.invoke(
        DemoInput(text="Prepare a concise answer."),
        ExecutionConfig(),
    )

    assert output.content == "checked response"
    selected_model_names = [name for _, name in provider.calls]
    assert selected_model_names.count("draft-model") == 1
    assert selected_model_names.count("check-model") == 1
