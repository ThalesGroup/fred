from __future__ import annotations

import pytest
from fred_core import PostgresStoreConfig
from fred_core.sql import create_async_engine_from_config
from fred_core import VectorSearchHit
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from agentic_backend.agents.v2 import BasicReActV2Definition, RagExpertV2Definition
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.chatbot.chat_schema import GeoPart, LinkKind, LinkPart
from agentic_backend.core.agents.v2 import (
    ArtifactPublishRequest,
    ArtifactPublisherPort,
    AwaitingHumanRuntimeEvent,
    BoundRuntimeContext,
    ChatModelFactoryPort,
    ExecutionConfig,
    FetchedResource,
    PortableContext,
    PortableEnvironment,
    PublishedArtifact,
    ResourceFetchRequest,
    ResourceReaderPort,
    ResourceScope,
    RuntimeEventKind,
    RuntimeServices,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolInvokerPort,
    ToolProviderPort,
    inspect_agent,
)
from agentic_backend.core.agents.v2.models import ToolRefRequirement
from agentic_backend.core.agents.v2.react_runtime import (
    ReActInput,
    ReActMessage,
    ReActMessageRole,
    ReActRuntime,
)
from agentic_backend.core.agents.v2.runtime import FinalRuntimeEvent
from agentic_backend.core.agents.v2.sql_checkpointer import FredSqlCheckpointer


class ToolFriendlyFakeChatModel(FakeMessagesListChatModel):
    """
    Small test-only model adapter.

    The stock fake chat model does not implement `bind_tools()`, but `create_agent()`
    requires it. Returning `self` is sufficient for deterministic unit tests
    because the responses are already scripted.
    """

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self


class StaticChatModelFactory(ChatModelFactoryPort):
    def __init__(self, model: ToolFriendlyFakeChatModel) -> None:
        self.model = model
        self.calls: list[tuple[str, str | None]] = []

    def build(self, definition, binding: BoundRuntimeContext):  # type: ignore[override]
        self.calls.append((definition.agent_id, binding.runtime_context.session_id))
        return self.model


class RecordingToolInvoker(ToolInvokerPort):
    def __init__(self) -> None:
        self.calls: list[ToolInvocationRequest] = []

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        self.calls.append(request)
        return ToolInvocationResult(
            tool_ref=request.tool_ref,
            blocks=(
                ToolContentBlock(
                    kind=ToolContentKind.JSON,
                    data={
                        "hits": [
                            {
                                "content": "The release date is 2025-01-01.",
                                "uid": "doc-1",
                                "title": "Release Plan",
                                "score": 0.98,
                                "rank": 1,
                            }
                        ]
                    },
                ),
            ),
            sources=(_vector_search_hit(),),
        )


class RecordingToolProvider(ToolProviderPort):
    def __init__(self, *, tool_name: str = "ops_status") -> None:
        self.bind_calls: list[str | None] = []
        self.activate_calls = 0
        self.close_calls = 0
        self._binding: BoundRuntimeContext | None = None
        self._tool_name = tool_name

    def bind(self, binding: BoundRuntimeContext) -> None:
        self._binding = binding
        self.bind_calls.append(binding.runtime_context.session_id)

    async def activate(self) -> None:
        self.activate_calls += 1

    def get_tools(self) -> tuple[BaseTool, ...]:
        async def _ops_status() -> str:
            return "cluster green"

        return (
            StructuredTool.from_function(
                func=None,
                coroutine=_ops_status,
                name=self._tool_name,
                description="Inspect the current operational status.",
            ),
        )

    async def aclose(self) -> None:
        self.close_calls += 1


class RecordingArtifactPublisher(ArtifactPublisherPort):
    def __init__(self) -> None:
        self.bind_calls: list[str | None] = []
        self.requests: list[ArtifactPublishRequest] = []

    def bind(self, binding: BoundRuntimeContext) -> None:
        self.bind_calls.append(binding.runtime_context.session_id)

    async def publish(self, request: ArtifactPublishRequest) -> PublishedArtifact:
        self.requests.append(request)
        return PublishedArtifact(
            scope=request.scope,
            key=request.key or "v2/demo/summary.txt",
            file_name=request.file_name,
            size=len(request.content_bytes),
            href="https://example.test/download/summary.txt",
            mime=request.content_type,
            title=request.title,
        )


class RecordingResourceReader(ResourceReaderPort):
    def __init__(self) -> None:
        self.bind_calls: list[str | None] = []
        self.requests: list[ResourceFetchRequest] = []

    def bind(self, binding: BoundRuntimeContext) -> None:
        self.bind_calls.append(binding.runtime_context.session_id)

    async def fetch(self, request: ResourceFetchRequest) -> FetchedResource:
        self.requests.append(request)
        return FetchedResource(
            scope=request.scope,
            key=request.key,
            file_name="report-template.md",
            size=len(b"# Report Template\n"),
            content_bytes=b"# Report Template\n",
            content_type="text/markdown; charset=utf-8",
        )


def _binding(session_id: str, *, agent_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id,
            user_id="user-1",
            language="en-US",
        ),
        portable_context=PortableContext(
            request_id=f"req-{session_id}",
            correlation_id=f"corr-{session_id}",
            actor="user:demo",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            agent_id=agent_id,
        ),
    )


def _user_input(text: str) -> ReActInput:
    return ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content=text),)
    )


def _vector_search_hit() -> VectorSearchHit:
    return VectorSearchHit.model_validate(
        {
            "content": "The release date is 2025-01-01.",
            "uid": "doc-1",
            "title": "Release Plan",
            "score": 0.98,
            "rank": 1,
        }
    )


@pytest.mark.asyncio
async def test_basic_react_runtime_invokes_without_tools() -> None:
    definition = BasicReActV2Definition()
    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="Hello from the v2 runtime.")]
    )
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(chat_model_factory=StaticChatModelFactory(model)),
    )
    runtime.bind(_binding("basic-session", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    output = await executor.invoke(_user_input("Say hello"), ExecutionConfig())

    assert output.final_message.role == ReActMessageRole.ASSISTANT
    assert output.final_message.content == "Hello from the v2 runtime."
    assert [message.role for message in output.transcript][
        -1
    ] == ReActMessageRole.ASSISTANT


@pytest.mark.asyncio
async def test_basic_react_runtime_stream_preserves_model_and_token_usage() -> None:
    definition = BasicReActV2Definition()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="Hello from the v2 runtime.",
                response_metadata={
                    "model_name": "gpt-test",
                    "finish_reason": "stop",
                },
                usage_metadata={
                    "input_tokens": 11,
                    "output_tokens": 7,
                    "total_tokens": 18,
                },
            )
        ]
    )
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(chat_model_factory=StaticChatModelFactory(model)),
    )
    runtime.bind(_binding("basic-stream-usage", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    events = [
        event
        async for event in executor.stream(
            _user_input("Say hello"),
            ExecutionConfig(),
        )
    ]

    final_event = events[-1]
    assert isinstance(final_event, FinalRuntimeEvent)
    assert final_event.content == "Hello from the v2 runtime."
    assert final_event.model_name == "gpt-test"
    assert final_event.finish_reason == "stop"
    assert final_event.token_usage == {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
    }


@pytest.mark.asyncio
async def test_basic_react_runtime_uses_runtime_provided_tools() -> None:
    definition = BasicReActV2Definition()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "ops_status",
                        "args": {},
                    }
                ],
            ),
            AIMessage(content="The cluster status is green."),
        ]
    )
    tool_provider = RecordingToolProvider()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_provider=tool_provider,
        ),
    )
    runtime.bind(_binding("ops-session", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    output = await executor.invoke(
        _user_input("Check the platform status."),
        ExecutionConfig(),
    )

    assert tool_provider.bind_calls == ["ops-session"]
    assert tool_provider.activate_calls == 1
    assert output.final_message.content == "The cluster status is green."


@pytest.mark.asyncio
async def test_basic_react_runtime_publish_text_tool_returns_link_part() -> None:
    definition = BasicReActV2Definition(
        tool_requirements=(
            ToolRefRequirement(
                tool_ref="artifacts.publish_text",
                description="Publish a generated text summary for the user.",
            ),
        )
    )
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-publish-1",
                        "name": "artifacts_publish_text",
                        "args": {
                            "file_name": "summary.txt",
                            "content": "Weekly summary",
                            "title": "Download summary",
                        },
                    }
                ],
            ),
            AIMessage(content="Your downloadable summary is ready."),
        ]
    )
    artifact_publisher = RecordingArtifactPublisher()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            artifact_publisher=artifact_publisher,
        ),
    )
    runtime.bind(_binding("artifact-session", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    events = [
        event
        async for event in executor.stream(
            _user_input("Prepare a short downloadable summary."),
            ExecutionConfig(),
        )
    ]

    final_event = events[-1]
    assert isinstance(final_event, FinalRuntimeEvent)
    assert final_event.content == "Your downloadable summary is ready."
    assert len(final_event.ui_parts) == 1
    assert isinstance(final_event.ui_parts[0], LinkPart)
    assert final_event.ui_parts[0].href == "https://example.test/download/summary.txt"
    assert artifact_publisher.bind_calls == ["artifact-session"]
    assert artifact_publisher.requests[0].file_name == "summary.txt"
    assert artifact_publisher.requests[0].content_bytes == b"Weekly summary"


@pytest.mark.asyncio
async def test_basic_react_runtime_fetch_text_tool_returns_template_text() -> None:
    definition = BasicReActV2Definition(
        tool_requirements=(
            ToolRefRequirement(
                tool_ref="resources.fetch_text",
                description="Fetch a stored text template for the current agent.",
            ),
        )
    )
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-fetch-1",
                        "name": "resources_fetch_text",
                        "args": {
                            "key": "report-template.md",
                            "scope": ResourceScope.AGENT_CONFIG.value,
                        },
                    }
                ],
            ),
            AIMessage(content="I loaded the configured report template."),
        ]
    )
    resource_reader = RecordingResourceReader()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            resource_reader=resource_reader,
        ),
    )
    runtime.bind(_binding("resource-session", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    events = [
        event
        async for event in executor.stream(
            _user_input("Load the configured report template."),
            ExecutionConfig(),
        )
    ]

    final_event = events[-1]
    assert isinstance(final_event, FinalRuntimeEvent)
    assert final_event.content == "I loaded the configured report template."
    assert resource_reader.bind_calls == ["resource-session"]
    assert resource_reader.requests[0].key == "report-template.md"
    assert resource_reader.requests[0].scope == ResourceScope.AGENT_CONFIG


@pytest.mark.asyncio
async def test_basic_react_runtime_pauses_for_tool_approval_and_resumes() -> None:
    definition = BasicReActV2Definition(enable_tool_approval=True)
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-approval-1",
                        "name": "update_ticket",
                        "args": {"ticket_id": "INC-42"},
                    }
                ],
            ),
            AIMessage(content="The ticket was updated."),
        ]
    )

    class ApprovalToolProvider(RecordingToolProvider):
        def __init__(self) -> None:
            super().__init__(tool_name="update_ticket")
            self.update_calls: list[str] = []

        def get_tools(self) -> tuple[BaseTool, ...]:
            async def _update_ticket(ticket_id: str) -> str:
                self.update_calls.append(ticket_id)
                return f"ticket {ticket_id} updated"

            class _Args(BaseModel):
                ticket_id: str

            return (
                StructuredTool.from_function(
                    func=None,
                    coroutine=_update_ticket,
                    name="update_ticket",
                    description="Update an incident ticket.",
                    args_schema=_Args,
                ),
            )

    tool_provider = ApprovalToolProvider()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_provider=tool_provider,
            checkpointer=MemorySaver(),
        ),
    )
    runtime.bind(_binding("approval-session", agent_id=definition.agent_id))

    executor = await runtime.get_executor()

    first_pass_events = [
        event
        async for event in executor.stream(
            _user_input("Update the incident."),
            ExecutionConfig(thread_id="approval-session"),
        )
    ]

    assert [event.kind for event in first_pass_events] == [
        RuntimeEventKind.TOOL_CALL,
        RuntimeEventKind.AWAITING_HUMAN,
    ]
    awaiting_human = first_pass_events[-1]
    assert isinstance(awaiting_human, AwaitingHumanRuntimeEvent)
    assert awaiting_human.request.stage == "tool_approval"
    assert awaiting_human.request.metadata["tool_name"] == "update_ticket"
    assert awaiting_human.request.checkpoint_id is not None

    resumed_events = [
        event
        async for event in executor.stream(
            _user_input("Update the incident."),
            ExecutionConfig(
                thread_id="approval-session",
                checkpoint_id=awaiting_human.request.checkpoint_id,
                resume_payload={"choice_id": "proceed"},
            ),
        )
    ]

    assert resumed_events
    assert resumed_events[-1].kind == RuntimeEventKind.FINAL
    final_event = resumed_events[-1]
    assert isinstance(final_event, FinalRuntimeEvent)
    assert final_event.content == "The ticket was updated."
    assert tool_provider.update_calls == ["INC-42"]


@pytest.mark.asyncio
async def test_basic_react_runtime_resume_survives_runtime_rebind() -> None:
    definition = BasicReActV2Definition(enable_tool_approval=True)
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-approval-1",
                        "name": "update_ticket",
                        "args": {"ticket_id": "INC-42"},
                    }
                ],
            ),
            AIMessage(content="The ticket was updated."),
        ]
    )

    class ApprovalToolProvider(RecordingToolProvider):
        def __init__(self) -> None:
            super().__init__(tool_name="update_ticket")
            self.update_calls: list[str] = []

        def get_tools(self) -> tuple[BaseTool, ...]:
            async def _update_ticket(ticket_id: str) -> str:
                self.update_calls.append(ticket_id)
                return f"ticket {ticket_id} updated"

            class _Args(BaseModel):
                ticket_id: str

            return (
                StructuredTool.from_function(
                    func=None,
                    coroutine=_update_ticket,
                    name="update_ticket",
                    description="Update an incident ticket.",
                    args_schema=_Args,
                ),
            )

    tool_provider = ApprovalToolProvider()
    checkpointer = MemorySaver()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_provider=tool_provider,
            checkpointer=checkpointer,
        ),
    )
    runtime.bind(_binding("approval-rebind-session", agent_id=definition.agent_id))
    first_executor = await runtime.get_executor()

    first_pass_events = [
        event
        async for event in first_executor.stream(
            _user_input("Update the incident."),
            ExecutionConfig(thread_id="approval-rebind-session"),
        )
    ]
    awaiting_human = first_pass_events[-1]
    assert isinstance(awaiting_human, AwaitingHumanRuntimeEvent)
    assert awaiting_human.request.checkpoint_id is not None

    runtime.bind(_binding("approval-rebind-session", agent_id=definition.agent_id))
    resumed_executor = await runtime.get_executor()

    resumed_events = [
        event
        async for event in resumed_executor.stream(
            _user_input("Update the incident."),
            ExecutionConfig(
                thread_id="approval-rebind-session",
                checkpoint_id=awaiting_human.request.checkpoint_id,
                resume_payload={"choice_id": "proceed"},
            ),
        )
    ]

    final_event = resumed_events[-1]
    assert isinstance(final_event, FinalRuntimeEvent)
    assert final_event.content == "The ticket was updated."


@pytest.mark.asyncio
async def test_basic_react_runtime_resume_survives_runtime_reconstruction() -> None:
    definition = BasicReActV2Definition(enable_tool_approval=True)
    checkpointer = MemorySaver()

    def _build_runtime(model: ToolFriendlyFakeChatModel) -> ReActRuntime:
        class ApprovalToolProvider(RecordingToolProvider):
            def __init__(self) -> None:
                super().__init__(tool_name="update_ticket")
                self.update_calls: list[str] = []

            def get_tools(self) -> tuple[BaseTool, ...]:
                async def _update_ticket(ticket_id: str) -> str:
                    self.update_calls.append(ticket_id)
                    return f"ticket {ticket_id} updated"

                class _Args(BaseModel):
                    ticket_id: str

                return (
                    StructuredTool.from_function(
                        func=None,
                        coroutine=_update_ticket,
                        name="update_ticket",
                        description="Update an incident ticket.",
                        args_schema=_Args,
                    ),
                )

        runtime = ReActRuntime(
            definition=definition,
            services=RuntimeServices(
                chat_model_factory=StaticChatModelFactory(model),
                tool_provider=ApprovalToolProvider(),
                checkpointer=checkpointer,
            ),
        )
        runtime.bind(_binding("approval-restart-session", agent_id=definition.agent_id))
        return runtime

    first_runtime = _build_runtime(
        ToolFriendlyFakeChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call-approval-1",
                            "name": "update_ticket",
                            "args": {"ticket_id": "INC-42"},
                        }
                    ],
                )
            ]
        )
    )
    first_executor = await first_runtime.get_executor()
    first_pass_events = [
        event
        async for event in first_executor.stream(
            _user_input("Update the incident."),
            ExecutionConfig(thread_id="approval-restart-session"),
        )
    ]
    awaiting_human = first_pass_events[-1]
    assert isinstance(awaiting_human, AwaitingHumanRuntimeEvent)
    assert awaiting_human.request.checkpoint_id is not None

    second_runtime = _build_runtime(
        ToolFriendlyFakeChatModel(
            responses=[
                AIMessage(content="The ticket was updated."),
            ]
        )
    )
    resumed_executor = await second_runtime.get_executor()
    resumed_events = [
        event
        async for event in resumed_executor.stream(
            _user_input("Update the incident."),
            ExecutionConfig(
                thread_id="approval-restart-session",
                checkpoint_id=awaiting_human.request.checkpoint_id,
                resume_payload={"choice_id": "proceed"},
            ),
        )
    ]

    final_event = resumed_events[-1]
    assert isinstance(final_event, FinalRuntimeEvent)
    assert final_event.content == "The ticket was updated."


@pytest.mark.asyncio
async def test_basic_react_runtime_resume_survives_sql_checkpointer_reconstruction(
    tmp_path,
) -> None:
    definition = BasicReActV2Definition(enable_tool_approval=True)
    sqlite_path = tmp_path / "react_runtime_checkpoints.sqlite3"
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(sqlite_path))
    )

    def _build_runtime(
        model: ToolFriendlyFakeChatModel, checkpointer: FredSqlCheckpointer
    ) -> ReActRuntime:
        class ApprovalToolProvider(RecordingToolProvider):
            def __init__(self) -> None:
                super().__init__(tool_name="update_ticket")

            def get_tools(self) -> tuple[BaseTool, ...]:
                async def _update_ticket(ticket_id: str) -> str:
                    return f"ticket {ticket_id} updated"

                class _Args(BaseModel):
                    ticket_id: str

                return (
                    StructuredTool.from_function(
                        func=None,
                        coroutine=_update_ticket,
                        name="update_ticket",
                        description="Update an incident ticket.",
                        args_schema=_Args,
                    ),
                )

        runtime = ReActRuntime(
            definition=definition,
            services=RuntimeServices(
                chat_model_factory=StaticChatModelFactory(model),
                tool_provider=ApprovalToolProvider(),
                checkpointer=checkpointer,
            ),
        )
        runtime.bind(_binding("approval-sql-session", agent_id=definition.agent_id))
        return runtime

    try:
        first_runtime = _build_runtime(
            ToolFriendlyFakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "call-approval-sql-1",
                                "name": "update_ticket",
                                "args": {"ticket_id": "INC-42"},
                            }
                        ],
                    )
                ]
            ),
            FredSqlCheckpointer(engine),
        )
        first_executor = await first_runtime.get_executor()
        first_pass_events = [
            event
            async for event in first_executor.stream(
                _user_input("Update the incident."),
                ExecutionConfig(thread_id="approval-sql-session"),
            )
        ]
        awaiting_human = first_pass_events[-1]
        assert isinstance(awaiting_human, AwaitingHumanRuntimeEvent)
        assert awaiting_human.request.checkpoint_id is not None

        second_runtime = _build_runtime(
            ToolFriendlyFakeChatModel(
                responses=[
                    AIMessage(content="The ticket was updated."),
                ]
            ),
            FredSqlCheckpointer(engine),
        )
        resumed_executor = await second_runtime.get_executor()
        resumed_events = [
            event
            async for event in resumed_executor.stream(
                _user_input("Update the incident."),
                ExecutionConfig(
                    thread_id="approval-sql-session",
                    checkpoint_id=awaiting_human.request.checkpoint_id,
                    resume_payload={"choice_id": "proceed"},
                ),
            )
        ]

        final_event = resumed_events[-1]
        assert isinstance(final_event, FinalRuntimeEvent)
        assert final_event.content == "The ticket was updated."
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rag_react_runtime_routes_tool_calls_through_tool_invoker() -> None:
    definition = RagExpertV2Definition()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "knowledge_search",
                        "args": {"query": "release date", "top_k": 8},
                    }
                ],
            ),
            AIMessage(content="The release date is 2025-01-01 [doc-1]."),
        ]
    )
    tool_invoker = RecordingToolInvoker()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_invoker=tool_invoker,
        ),
    )
    runtime.bind(_binding("rag-session", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    output = await executor.invoke(
        _user_input("What is the release date?"), ExecutionConfig()
    )

    assert len(tool_invoker.calls) == 1
    assert tool_invoker.calls[0].tool_ref == "knowledge.search"
    assert tool_invoker.calls[0].payload == {"query": "release date", "top_k": 8}
    assert output.final_message.content == "The release date is 2025-01-01 [doc-1]."


@pytest.mark.asyncio
async def test_basic_react_runtime_routes_logs_query_through_tool_invoker() -> None:
    definition = BasicReActV2Definition(
        tool_requirements=(
            ToolRefRequirement(
                tool_ref="logs.query",
                description="Query recent logs for triage.",
            ),
        )
    )
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-logs-1",
                        "name": "logs_query",
                        "args": {
                            "window_minutes": 5,
                            "limit": 500,
                            "min_level": "WARNING",
                            "include_agentic": True,
                            "include_knowledge_flow": True,
                            "max_events": 200,
                        },
                    }
                ],
            ),
            AIMessage(content="The main issue is repeated permission failures."),
        ]
    )
    tool_invoker = RecordingToolInvoker()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_invoker=tool_invoker,
        ),
    )
    runtime.bind(_binding("logs-session", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    output = await executor.invoke(
        _user_input("Analyze the recent platform failures."),
        ExecutionConfig(),
    )

    assert len(tool_invoker.calls) == 1
    assert tool_invoker.calls[0].tool_ref == "logs.query"
    assert tool_invoker.calls[0].payload == {
        "window_minutes": 5,
        "limit": 500,
        "min_level": "WARNING",
        "include_agentic": True,
        "include_knowledge_flow": True,
        "max_events": 200,
    }
    assert (
        output.final_message.content
        == "The main issue is repeated permission failures."
    )


@pytest.mark.asyncio
async def test_basic_react_runtime_routes_geo_render_points_with_ui_parts() -> None:
    definition = BasicReActV2Definition(
        tool_requirements=(
            ToolRefRequirement(
                tool_ref="geo.render_points",
                description="Render a map from latitude and longitude points.",
            ),
        )
    )

    class GeoToolInvoker(ToolInvokerPort):
        def __init__(self) -> None:
            self.calls: list[ToolInvocationRequest] = []

        async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
            self.calls.append(request)
            return ToolInvocationResult(
                tool_ref=request.tool_ref,
                blocks=(
                    ToolContentBlock(
                        kind=ToolContentKind.TEXT,
                        text="Nearby offices: displaying 1 point on the map.",
                    ),
                ),
                ui_parts=(
                    GeoPart(
                        geojson={
                            "type": "FeatureCollection",
                            "features": [
                                {
                                    "type": "Feature",
                                    "geometry": {
                                        "type": "Point",
                                        "coordinates": [2.3522, 48.8566],
                                    },
                                    "properties": {"name": "Paris"},
                                }
                            ],
                        },
                        popup_property="name",
                        fit_bounds=True,
                    ),
                    LinkPart(
                        href="https://example.test/map",
                        title="Open full map",
                        kind=LinkKind.external,
                    ),
                ),
            )

    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-map-1",
                        "name": "geo_render_points",
                        "args": {
                            "title": "Nearby offices",
                            "points": [
                                {
                                    "name": "Paris",
                                    "latitude": 48.8566,
                                    "longitude": 2.3522,
                                }
                            ],
                        },
                    }
                ],
            ),
            AIMessage(content="Here is the office map."),
        ]
    )
    tool_invoker = GeoToolInvoker()
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_invoker=tool_invoker,
        ),
    )
    runtime.bind(_binding("geo-session", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    events = [
        event
        async for event in executor.stream(
            _user_input("Show nearby offices on a map."),
            ExecutionConfig(),
        )
    ]

    tool_result = next(
        event for event in events if event.kind == RuntimeEventKind.TOOL_RESULT
    )
    final_event = next(
        event for event in events if event.kind == RuntimeEventKind.FINAL
    )

    assert len(tool_invoker.calls) == 1
    assert tool_invoker.calls[0].tool_ref == "geo.render_points"
    assert tool_invoker.calls[0].payload["title"] == "Nearby offices"
    assert len(tool_result.ui_parts) == 2
    assert getattr(tool_result.ui_parts[0], "type", None) == "geo"
    assert getattr(tool_result.ui_parts[1], "type", None) == "link"
    assert len(final_event.ui_parts) == 2
    assert getattr(final_event.ui_parts[0], "type", None) == "geo"
    assert getattr(final_event.ui_parts[1], "type", None) == "link"


@pytest.mark.asyncio
async def test_rag_stream_emits_tool_and_final_events() -> None:
    definition = RagExpertV2Definition()
    model = ToolFriendlyFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "knowledge_search",
                        "args": {"query": "release date", "top_k": 8},
                    }
                ],
            ),
            AIMessage(content="The release date is 2025-01-01 [doc-1]."),
        ]
    )
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_invoker=RecordingToolInvoker(),
        ),
    )
    runtime.bind(_binding("rag-stream", agent_id=definition.agent_id))

    executor = await runtime.get_executor()
    events = [
        event
        async for event in executor.stream(
            _user_input("What is the release date?"),
            ExecutionConfig(),
        )
    ]

    assert RuntimeEventKind.TOOL_CALL in [event.kind for event in events]
    assert RuntimeEventKind.TOOL_RESULT in [event.kind for event in events]
    assert RuntimeEventKind.FINAL in [event.kind for event in events]
    final_event = events[-1]
    assert isinstance(final_event, FinalRuntimeEvent)
    assert final_event.content == "The release date is 2025-01-01 [doc-1]."
    assert final_event.sources[0].uid == "doc-1"


@pytest.mark.asyncio
async def test_react_runtime_rejects_duplicate_tool_names() -> None:
    definition = RagExpertV2Definition()
    model = ToolFriendlyFakeChatModel(
        responses=[AIMessage(content="This response should never be reached.")]
    )
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_invoker=RecordingToolInvoker(),
            tool_provider=RecordingToolProvider(tool_name="knowledge_search"),
        ),
    )
    runtime.bind(_binding("duplicate-tools", agent_id=definition.agent_id))

    with pytest.raises(RuntimeError, match="Duplicate tool name"):
        await runtime.get_executor()


def test_rag_definition_inspection_stays_small_and_declared() -> None:
    inspection = inspect_agent(RagExpertV2Definition())

    assert inspection.execution_category.value == "react"
    assert inspection.tool_requirements[0].kind == "tool_ref"
    assert inspection.tool_requirements[0].tool_ref == "knowledge.search"
    assert "Declared tools: 1" in inspection.preview.content
