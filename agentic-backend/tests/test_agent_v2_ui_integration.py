from __future__ import annotations

from typing import Any, cast

import pytest
from fred_core import KeycloakUser, VectorSearchHit
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.messages.tool import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from agentic_backend.agents.v2 import (
    ArtifactReportDemoV2Definition,
    BasicReActDefinition,
    PostalTrackingDefinition,
    RagExpertV2Definition,
)
from agentic_backend.agents.v2.production.basic_react.profiles.custodian import (
    CUSTODIAN_PROFILE,
)
from agentic_backend.agents.v2.production.basic_react.profiles.log_genius import (
    LOG_GENIUS_PROFILE,
)
from agentic_backend.agents.v2.production.basic_react.profiles.rag_expert import (
    RAG_EXPERT_PROFILE,
)
from agentic_backend.agents.v2.production.basic_react.profiles.sentinel import (
    SENTINEL_PROFILE,
)
from agentic_backend.common.structures import Agent
from agentic_backend.core.agents.agent_class_resolver import (
    AgentImplementationKind,
    resolve_agent_class,
    resolve_agent_reference,
)
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    GraphRuntime,
    PortableContext,
    PortableEnvironment,
    RuntimeServices,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolInvokerPort,
    ToolProviderPort,
)
from agentic_backend.core.agents.v2.catalog import (
    apply_profile_defaults_to_settings,
    apply_react_profile_to_definition,
    build_bound_runtime_context,
    build_definition_from_settings,
    definition_to_agent_settings,
    definition_to_agent_tuning,
)
from agentic_backend.core.agents.v2.models import ToolRefRequirement
from agentic_backend.core.agents.v2.react_profiles import list_react_profiles
from agentic_backend.core.agents.v2.react_runtime import ReActRuntime
from agentic_backend.core.agents.v2.runtime import (
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    HumanInputRequest,
)
from agentic_backend.core.agents.v2.session_agent import (
    V2SessionAgent,
    _legacy_events_from_runtime_event,
    _react_input_from_state,
)
from agentic_backend.core.chatbot.chat_schema import (
    GeoPart,
    LinkKind,
    LinkPart,
    TextPart,
    TokenUsageSource,
)
from agentic_backend.core.chatbot.stream_transcoder import StreamTranscoder
from tests.test_agent_v2_react_runtime import (
    StaticChatModelFactory,
    ToolFriendlyFakeChatModel,
)
from tests.test_tracking_graph_v2 import TrackingDemoToolProvider

CUSTODIAN_PROFILE_ID = CUSTODIAN_PROFILE.profile_id
LOG_GENIUS_PROFILE_ID = LOG_GENIUS_PROFILE.profile_id
RAG_EXPERT_PROFILE_ID = RAG_EXPERT_PROFILE.profile_id
SENTINEL_PROFILE_ID = SENTINEL_PROFILE.profile_id


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


def test_v2_session_agent_omits_empty_choices_for_free_text_interrupts() -> None:
    legacy_events = _legacy_events_from_runtime_event(
        AwaitingHumanRuntimeEvent(
            request=HumanInputRequest(
                stage="bid_intake_clarification",
                title="Preciser les informations manquantes",
                question="Merci de completer les informations d'offre manquantes.",
                free_text=True,
            )
        ),
        requested_modes=frozenset({"updates"}),
    )

    assert legacy_events == [
        {
            "__interrupt__": {
                "value": {
                    "stage": "bid_intake_clarification",
                    "title": "Preciser les informations manquantes",
                    "question": "Merci de completer les informations d'offre manquantes.",
                    "free_text": True,
                }
            }
        }
    ]


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


def _test_user() -> KeycloakUser:
    return KeycloakUser.model_validate(
        {
            "uid": "user-1",
            "username": "alice",
            "roles": ["admin"],
            "groups": [],
        }
    )


def test_build_bound_runtime_context_carries_readable_trace_identity() -> None:
    binding = build_bound_runtime_context(
        user=_test_user(),
        runtime_context=RuntimeContext(
            session_id="session-42",
            user_id="user-1",
        ),
        agent_id="agent-uuid-123",
        agent_name="Rico",
        team_id="team-bidgpt",
    )
    portable = binding.portable_context

    assert portable.agent_id == "agent-uuid-123"
    assert portable.agent_name == "Rico"
    assert portable.session_id == "session-42"
    assert portable.user_id == "user-1"
    assert portable.user_name == "alice"
    assert portable.team_id == "team-bidgpt"


def test_resolve_agent_class_accepts_v2_definitions() -> None:
    resolved = resolve_agent_class(
        "agentic_backend.agents.v2.production.basic_react.profiles.rag_expert_agent.RagExpertV2Definition"
    )

    assert resolved.implementation_kind == AgentImplementationKind.V2_DEFINITION


def test_resolve_agent_class_accepts_v2_graph_definitions() -> None:
    resolved = resolve_agent_class(
        "agentic_backend.agents.v2.demos.postal_tracking.Definition"
    )

    assert resolved.implementation_kind == AgentImplementationKind.V2_DEFINITION


def test_resolve_agent_class_accepts_v2_artifact_report_definition() -> None:
    resolved = resolve_agent_class(
        "agentic_backend.agents.v2.demos.artifact_report.ArtifactReportDemoV2Definition"
    )

    assert resolved.implementation_kind == AgentImplementationKind.V2_DEFINITION


def test_resolve_agent_reference_accepts_v2_definition_ref() -> None:
    resolved = resolve_agent_reference(
        class_path=None,
        definition_ref="v2.react.basic",
    )

    assert resolved.implementation_kind == AgentImplementationKind.V2_DEFINITION
    assert resolved.definition_ref == "v2.react.basic"
    assert (
        resolved.class_path
        == "agentic_backend.agents.v2.production.basic_react.BasicReActDefinition"
    )


def test_artifact_report_demo_declares_publish_capability() -> None:
    definition = ArtifactReportDemoV2Definition()

    assert definition.execution_category.value == "react"
    assert [tool.tool_ref for tool in definition.tool_requirements] == [
        "resources.fetch_text",
        "artifacts.publish_text",
    ]
    assert "downloadable text deliverables" in definition.system_prompt_template


def test_build_definition_from_settings_applies_persisted_prompt_override() -> None:
    base_definition = RagExpertV2Definition()
    base_tuning = definition_to_agent_tuning(base_definition)
    tuned_fields = []
    for field in base_tuning.fields:
        if field.key == "system_prompt_template":
            tuned_fields.append(
                field.model_copy(
                    update={
                        "default": "You are the persisted RAG agent. Today is {today}."
                    }
                )
            )
        else:
            tuned_fields.append(field)

    settings = Agent(
        id="rag-ui-agent",
        name="RAG UI Agent",
        class_path="agentic_backend.agents.v2.production.basic_react.profiles.rag_expert_agent.RagExpertV2Definition",
        tuning=AgentTuning(
            role="Persisted role",
            description="Persisted description",
            tags=["rag", "persisted"],
            fields=tuned_fields,
        ),
    )

    definition = build_definition_from_settings(
        definition_class=RagExpertV2Definition,
        settings=settings,
    )

    assert definition.agent_id == "rag-ui-agent"
    assert definition.role == "Persisted role"
    assert definition.description == "Persisted description"
    assert (
        definition.system_prompt_template
        == "You are the persisted RAG agent. Today is {today}."
    )


def test_basic_react_profile_field_lists_available_backend_profiles() -> None:
    definition = BasicReActDefinition()

    profile_field = next(
        field for field in definition.fields if field.key == "react_profile_id"
    )
    available_profile_ids = [profile.profile_id for profile in list_react_profiles()]

    assert profile_field.type == "select"
    assert profile_field.enum == available_profile_ids
    assert profile_field.default == available_profile_ids[0]


def test_build_definition_from_settings_applies_custodian_profile_defaults() -> None:
    base_definition = BasicReActDefinition()
    tuned_fields = []
    for field in base_definition.fields:
        if field.key == "react_profile_id":
            tuned_fields.append(
                field.model_copy(update={"default": CUSTODIAN_PROFILE_ID})
            )
        else:
            tuned_fields.append(field.model_copy(deep=True))

    settings = Agent(
        id="custodian-react-agent",
        name="Custodian",
        class_path="agentic_backend.agents.v2.production.basic_react.BasicReActDefinition",
        tuning=AgentTuning(
            role=base_definition.role,
            description=base_definition.description,
            tags=list(base_definition.tags),
            fields=tuned_fields,
        ),
    )

    definition = build_definition_from_settings(
        definition_class=BasicReActDefinition,
        settings=settings,
    )
    effective_settings = apply_profile_defaults_to_settings(
        definition=definition,
        settings=settings,
    )

    assert definition.react_profile_id == CUSTODIAN_PROFILE_ID
    assert definition.role == "Data & Corpus Custodian"
    assert definition.enable_tool_approval is True
    assert definition.approval_required_tools == (
        "build_corpus_toc",
        "revectorize_corpus",
        "purge_vectors",
    )
    assert (
        "safe operator for user files and knowledge corpora"
        in definition.system_prompt_template
    )
    assert effective_settings.tuning is not None
    assert [server.id for server in effective_settings.tuning.mcp_servers] == [
        "mcp-knowledge-flow-fs",
        "mcp-knowledge-flow-corpus",
    ]


def test_build_definition_from_settings_applies_rag_expert_profile_defaults() -> None:
    base_definition = BasicReActDefinition()
    tuned_fields = []
    for field in base_definition.fields:
        if field.key == "react_profile_id":
            tuned_fields.append(
                field.model_copy(update={"default": RAG_EXPERT_PROFILE_ID})
            )
        else:
            tuned_fields.append(field.model_copy(deep=True))

    settings = Agent(
        id="rag-expert-react-agent",
        name="RAG Expert",
        class_path="agentic_backend.agents.v2.production.basic_react.BasicReActDefinition",
        tuning=AgentTuning(
            role=base_definition.role,
            description=base_definition.description,
            tags=list(base_definition.tags),
            fields=tuned_fields,
        ),
    )

    definition = build_definition_from_settings(
        definition_class=BasicReActDefinition,
        settings=settings,
    )
    effective_settings = apply_profile_defaults_to_settings(
        definition=definition,
        settings=settings,
    )

    assert definition.react_profile_id == RAG_EXPERT_PROFILE_ID
    assert definition.role == "Document-grounded RAG expert"
    assert definition.enable_tool_approval is False
    assert "retrieval-augmented assistant" in definition.description.lower()
    assert [tool.tool_ref for tool in definition.tool_requirements] == [
        "knowledge.search"
    ]
    assert effective_settings.tuning is not None
    assert effective_settings.tuning.mcp_servers == []
    assert effective_settings.chat_options.attach_files is True
    assert effective_settings.chat_options.libraries_selection is True
    assert effective_settings.chat_options.search_rag_scoping is True


def test_profiled_basic_react_creation_settings_start_with_selected_profile() -> None:
    base_definition = BasicReActDefinition()
    effective_definition = apply_react_profile_to_definition(
        base_definition,
        RAG_EXPERT_PROFILE_ID,
    )
    base_settings = definition_to_agent_settings(
        base_definition,
        class_path="agentic_backend.agents.v2.production.basic_react.BasicReActDefinition",
        enabled=True,
    )
    effective_settings = apply_profile_defaults_to_settings(
        definition=effective_definition,
        settings=base_settings,
    )

    assert effective_settings.tuning is not None
    assert effective_settings.tuning.role == effective_definition.role
    assert effective_settings.tuning.description == effective_definition.description
    react_profile_field = next(
        field
        for field in effective_settings.tuning.fields
        if field.key == "react_profile_id"
    )
    assert react_profile_field.default == RAG_EXPERT_PROFILE_ID


def test_build_definition_from_settings_applies_sentinel_profile_defaults() -> None:
    base_definition = BasicReActDefinition()
    tuned_fields = []
    for field in base_definition.fields:
        if field.key == "react_profile_id":
            tuned_fields.append(
                field.model_copy(update={"default": SENTINEL_PROFILE_ID})
            )
        else:
            tuned_fields.append(field.model_copy(deep=True))

    settings = Agent(
        id="sentinel-react-agent",
        name="Sentinel",
        class_path="agentic_backend.agents.v2.production.basic_react.BasicReActDefinition",
        tuning=AgentTuning(
            role=base_definition.role,
            description=base_definition.description,
            tags=list(base_definition.tags),
            fields=tuned_fields,
        ),
    )

    definition = build_definition_from_settings(
        definition_class=BasicReActDefinition,
        settings=settings,
    )
    effective_settings = apply_profile_defaults_to_settings(
        definition=definition,
        settings=settings,
    )

    assert definition.react_profile_id == SENTINEL_PROFILE_ID
    assert definition.role == "sentinel_expert"
    assert definition.enable_tool_approval is False
    assert "operations and monitoring agent" in definition.system_prompt_template
    assert effective_settings.tuning is not None
    assert [server.id for server in effective_settings.tuning.mcp_servers] == [
        "mcp-knowledge-flow-opensearch-ops",
    ]


def test_build_definition_from_settings_applies_log_genius_profile_defaults() -> None:
    base_definition = BasicReActDefinition()
    tuned_fields = []
    for field in base_definition.fields:
        if field.key == "react_profile_id":
            tuned_fields.append(
                field.model_copy(update={"default": LOG_GENIUS_PROFILE_ID})
            )
        else:
            tuned_fields.append(field.model_copy(deep=True))

    settings = Agent(
        id="log-genius-react-agent",
        name="LogGenius",
        class_path="agentic_backend.agents.v2.production.basic_react.BasicReActDefinition",
        tuning=AgentTuning(
            role=base_definition.role,
            description=base_definition.description,
            tags=list(base_definition.tags),
            fields=tuned_fields,
        ),
    )

    definition = build_definition_from_settings(
        definition_class=BasicReActDefinition,
        settings=settings,
    )
    effective_settings = apply_profile_defaults_to_settings(
        definition=definition,
        settings=settings,
    )

    assert definition.react_profile_id == LOG_GENIUS_PROFILE_ID
    assert definition.role == "log_genius"
    assert "logs_query" in definition.system_prompt_template
    assert [tool.tool_ref for tool in definition.tool_requirements] == [
        "logs.query",
        "traces.summarize_conversation",
    ]
    assert effective_settings.tuning is not None
    assert effective_settings.tuning.mcp_servers == []


def test_graph_definition_applies_default_mcp_servers_to_effective_settings() -> None:
    definition = PostalTrackingDefinition()
    settings = definition_to_agent_settings(
        definition,
        class_path=("agentic_backend.agents.v2.demos.postal_tracking.Definition"),
        enabled=True,
    )

    effective_settings = apply_profile_defaults_to_settings(
        definition=definition,
        settings=settings,
    )

    assert effective_settings.tuning is not None
    assert [server.id for server in effective_settings.tuning.mcp_servers] == [
        "mcp-postal-business-demo",
        "mcp-iot-tracking-demo",
    ]


def test_build_definition_from_settings_applies_rag_expert_tool_defaults() -> None:
    base_definition = BasicReActDefinition()
    tuned_fields = []
    for field in base_definition.fields:
        if field.key == "react_profile_id":
            tuned_fields.append(
                field.model_copy(update={"default": RAG_EXPERT_PROFILE_ID})
            )
        else:
            tuned_fields.append(field.model_copy(deep=True))

    settings = Agent(
        id="rag-expert-tool-react-agent",
        name="RAG Expert Tool",
        class_path="agentic_backend.agents.v2.production.basic_react.BasicReActDefinition",
        tuning=AgentTuning(
            role=base_definition.role,
            description=base_definition.description,
            tags=list(base_definition.tags),
            fields=tuned_fields,
        ),
    )

    definition = build_definition_from_settings(
        definition_class=BasicReActDefinition,
        settings=settings,
    )
    effective_settings = apply_profile_defaults_to_settings(
        definition=definition,
        settings=settings,
    )

    assert definition.react_profile_id == RAG_EXPERT_PROFILE_ID
    assert len(definition.tool_requirements) == 1
    assert definition.tool_requirements[0].tool_ref == "knowledge.search"
    assert effective_settings.tuning is not None
    assert effective_settings.chat_options.attach_files is True
    assert effective_settings.chat_options.libraries_selection is True
    assert effective_settings.tuning.mcp_servers == []


def test_react_input_from_restored_history_preserves_tool_call_pairing() -> None:
    input_model = _react_input_from_state(
        {
            "messages": [
                HumanMessage(content="peux tu me lister mes fichiers ?"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "call-restore-1",
                            "name": "list_files",
                            "args": {"prefix": ""},
                        }
                    ],
                ),
                ToolMessage(
                    content="[]",
                    name="list_files",
                    tool_call_id="call-restore-1",
                ),
                AIMessage(content="Je ne vois actuellement aucun fichier."),
            ]
        }
    )

    assert input_model.messages[1].role.value == "assistant"
    assert input_model.messages[1].tool_calls[0].call_id == "call-restore-1"
    assert input_model.messages[1].tool_calls[0].name == "list_files"
    assert input_model.messages[2].role.value == "tool"
    assert input_model.messages[2].tool_name == "list_files"
    assert input_model.messages[2].tool_call_id == "call-restore-1"


@pytest.mark.asyncio
async def test_stream_transcoder_handles_v2_session_agent() -> None:
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
    runtime.bind(_binding("ui-session", agent_id=definition.agent_id))
    agent = V2SessionAgent(runtime=runtime)

    emitted: list[dict] = []
    transcoder = StreamTranscoder()
    messages = await transcoder.stream_agent_response(
        agent=agent,
        input_messages=[HumanMessage(content="What is the release date?")],
        session_id="ui-session",
        exchange_id="exchange-1",
        agent_id=definition.agent_id,
        base_rank=1,
        start_seq=0,
        callback=emitted.append,
        user_context=_test_user(),
        runtime_context=RuntimeContext(session_id="ui-session", user_id="user-1"),
    )

    assert len(tool_invoker.calls) == 1
    final_part = messages[-1].parts[0]
    assert isinstance(final_part, TextPart)
    assert final_part.text == "The release date is 2025-01-01 [doc-1]."
    assert [message.channel for message in messages] == [
        "tool_call",
        "tool_result",
        "final",
    ]
    assert len(messages[-1].metadata.sources) == 1
    assert messages[-1].metadata.sources[0].uid == "doc-1"
    assert messages[-1].metadata.sources[0].title == "Release Plan"
    assert emitted[-1]["parts"][0]["text"] == "The release date is 2025-01-01 [doc-1]."


@pytest.mark.asyncio
async def test_stream_transcoder_carries_v2_token_usage_to_final_message() -> None:
    definition = BasicReActDefinition()
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
    runtime.bind(_binding("usage-ui-session", agent_id=definition.agent_id))
    agent = V2SessionAgent(runtime=runtime)

    transcoder = StreamTranscoder()
    messages = await transcoder.stream_agent_response(
        agent=agent,
        input_messages=[HumanMessage(content="Say hello")],
        session_id="usage-ui-session",
        exchange_id="exchange-usage-1",
        agent_id=definition.agent_id,
        base_rank=1,
        start_seq=0,
        callback=lambda _: None,
        user_context=_test_user(),
        runtime_context=RuntimeContext(session_id="usage-ui-session", user_id="user-1"),
    )

    final_message = messages[-1]
    assert final_message.metadata.model == "gpt-test"
    assert final_message.metadata.finish_reason == "stop"
    assert final_message.metadata.token_usage is not None
    assert final_message.metadata.token_usage.input_tokens == 11
    assert final_message.metadata.token_usage.output_tokens == 7
    assert final_message.metadata.token_usage.total_tokens == 18
    assert final_message.metadata.token_usage_source == TokenUsageSource.updates


@pytest.mark.asyncio
async def test_stream_transcoder_carries_v2_geo_and_link_parts_from_tool_results() -> (
    None
):
    definition = BasicReActDefinition(
        tool_requirements=(
            ToolRefRequirement(
                tool_ref="geo.render_points",
                description="Render a map from latitude/longitude points.",
            ),
        )
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

    class GeoRecordingToolInvoker(ToolInvokerPort):
        async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
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

    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_invoker=GeoRecordingToolInvoker(),
        ),
    )
    runtime.bind(_binding("geo-ui-session", agent_id=definition.agent_id))
    agent = V2SessionAgent(runtime=runtime)

    transcoder = StreamTranscoder()
    messages = await transcoder.stream_agent_response(
        agent=agent,
        input_messages=[HumanMessage(content="Show nearby offices on a map.")],
        session_id="geo-ui-session",
        exchange_id="exchange-geo-1",
        agent_id=definition.agent_id,
        base_rank=1,
        start_seq=0,
        callback=lambda _: None,
        user_context=_test_user(),
        runtime_context=RuntimeContext(session_id="geo-ui-session", user_id="user-1"),
    )

    final_parts = messages[-1].parts
    assert isinstance(final_parts[0], TextPart)
    assert final_parts[0].text == "Here is the office map."
    assert any(getattr(part, "type", None) == "geo" for part in final_parts)
    assert any(getattr(part, "type", None) == "link" for part in final_parts)


@pytest.mark.asyncio
async def test_v2_session_agent_supports_interrupt_resume() -> None:
    definition = BasicReActDefinition(enable_tool_approval=True)
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

    class ApprovalToolProvider(ToolProviderPort):
        def __init__(self) -> None:
            self._binding: BoundRuntimeContext | None = None

        def bind(self, binding: BoundRuntimeContext) -> None:
            self._binding = binding

        async def activate(self) -> None:
            return None

        def get_tools(self) -> tuple[BaseTool, ...]:
            class _Args(BaseModel):
                ticket_id: str

            async def _update_ticket(ticket_id: str) -> str:
                return f"ticket {ticket_id} updated"

            return (
                StructuredTool.from_function(
                    func=None,
                    coroutine=_update_ticket,
                    name="update_ticket",
                    description="Update an incident ticket.",
                    args_schema=_Args,
                ),
            )

        async def aclose(self) -> None:
            return None

    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_provider=ApprovalToolProvider(),
            checkpointer=MemorySaver(),
        ),
    )
    runtime.bind(_binding("hitl-ui-session", agent_id=definition.agent_id))
    agent = V2SessionAgent(runtime=runtime)

    first_pass_events = [
        event
        async for event in agent.astream_updates(
            state={"messages": [HumanMessage(content="Update the incident.")]},
            config={"configurable": {"thread_id": "hitl-ui-session"}},
            stream_mode=["updates"],
        )
    ]
    interrupt_payload = cast(
        dict[str, Any],
        cast(dict[str, Any], first_pass_events[1]["__interrupt__"])["value"],
    )
    assert isinstance(interrupt_payload.get("checkpoint_id"), str)
    expected_interrupt_payload = {
        "stage": "tool_approval",
        "title": "Confirm tool execution",
        "question": (
            "The agent wants to execute `update_ticket`. "
            "This may modify state or trigger an external action. "
            "Do you want to continue?"
        ),
        "choices": [
            {
                "id": "proceed",
                "label": "Proceed",
                "description": "Run this tool now.",
                "default": True,
            },
            {
                "id": "cancel",
                "label": "Cancel",
                "description": "Do not run this tool; let the agent replan.",
                "default": False,
            },
        ],
        "free_text": True,
        "metadata": {
            "tool_name": "update_ticket",
            "tool_args_preview": '{"ticket_id": "INC-42"}',
        },
        "checkpoint_id": interrupt_payload["checkpoint_id"],
    }
    assert first_pass_events[1] == {
        "__interrupt__": {
            "value": expected_interrupt_payload,
        }
    }

    resumed_events = [
        event
        async for event in agent.astream_updates(
            state=Command(resume={"choice_id": "proceed"}),
            config={
                "configurable": {
                    "thread_id": "hitl-ui-session",
                    "checkpoint_id": interrupt_payload["checkpoint_id"],
                }
            },
            stream_mode=["updates"],
        )
    ]
    final_event = cast(dict[str, Any], resumed_events[-1])
    agent_payload = cast(dict[str, Any], final_event["agent"])
    messages_payload = cast(list[Any], agent_payload["messages"])
    final_message = messages_payload[0]
    assert isinstance(final_message, AIMessage)
    assert final_message.content == "The ticket was updated."


def test_v2_session_agent_bridge_exposes_assistant_deltas_in_messages_mode() -> None:
    legacy_events = _legacy_events_from_runtime_event(
        AssistantDeltaRuntimeEvent(sequence=0, delta="Bonjour"),
        requested_modes=frozenset({"messages", "updates"}),
    )

    assert len(legacy_events) == 1
    mode, payload = cast(
        tuple[str, tuple[AIMessageChunk, dict[str, str]]], legacy_events[0]
    )
    assert mode == "messages"
    chunk, chunk_metadata = payload
    assert isinstance(chunk, AIMessageChunk)
    assert chunk.content == "Bonjour"
    assert chunk_metadata == {"langgraph_node": "agent"}


@pytest.mark.asyncio
async def test_v2_session_agent_bridge_supports_graph_runtime_hitl_and_geo_parts() -> (
    None
):
    definition = PostalTrackingDefinition()
    checkpointer = MemorySaver()
    runtime = GraphRuntime(
        definition=definition,
        services=RuntimeServices(
            tool_provider=TrackingDemoToolProvider(),
            checkpointer=checkpointer,
        ),
    )
    runtime.bind(_binding("tracking-graph-ui-session", agent_id=definition.agent_id))
    agent = V2SessionAgent(runtime=runtime)

    first_pass_events = [
        event
        async for event in agent.astream_updates(
            state={
                "messages": [
                    HumanMessage(
                        content="Peux-tu rerouter ce colis vers un point relais ?"
                    )
                ]
            },
            config={"configurable": {"thread_id": "tracking-graph-ui-session"}},
            stream_mode=["updates"],
        )
    ]

    interrupt_event = cast(dict[str, Any], first_pass_events[-1])
    interrupt_payload = cast(
        dict[str, Any], cast(dict[str, Any], interrupt_event["__interrupt__"])["value"]
    )
    assert interrupt_payload["stage"] == "tracking_resolution"
    assert interrupt_payload["choices"][0]["id"].startswith("reroute:")
    assert isinstance(interrupt_payload.get("checkpoint_id"), str)

    resumed_events = [
        event
        async for event in agent.astream_updates(
            state=Command(resume={"choice_id": "reroute:PP-75015-1"}),
            config={
                "configurable": {
                    "thread_id": "tracking-graph-ui-session",
                    "checkpoint_id": interrupt_payload["checkpoint_id"],
                }
            },
            stream_mode=["updates"],
        )
    ]

    final_event = cast(dict[str, Any], resumed_events[-1])
    agent_payload = cast(dict[str, Any], final_event["agent"])
    messages_payload = cast(list[Any], agent_payload["messages"])
    final_message = messages_payload[0]
    assert isinstance(final_message, AIMessage)
    assert "PKG-DEMO-001" in final_message.content
    fred_parts = cast(
        list[dict[str, Any]], final_message.additional_kwargs.get("fred_parts", [])
    )
    assert len(fred_parts) == 1
    assert fred_parts[0]["type"] == "geo"
    assert fred_parts[0]["geojson"]["type"] == "FeatureCollection"
