from __future__ import annotations

from typing import cast

import pytest
from pydantic import BaseModel

from agentic_backend.core.agents.agent_spec import FieldSpec
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    ArtifactPublishRequest,
    ArtifactPublisherPort,
    AwaitingHumanRuntimeEvent,
    BoundRuntimeContext,
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
