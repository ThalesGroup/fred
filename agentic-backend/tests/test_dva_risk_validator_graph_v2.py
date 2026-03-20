from __future__ import annotations

from types import SimpleNamespace

import pytest
from fred_core import VectorSearchHit

from agentic_backend.agents.v2.candidate.DVARiskValidatorAssistant.graph import (
    DVARiskValidatorGraph,
)
from agentic_backend.agents.v2.candidate.DVARiskValidatorAssistant.shared.models import (
    RiskAssessment,
)
from agentic_backend.agents.v2.candidate.DVARiskValidatorAssistant.shared.rendering import (
    render_report,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    AwaitingHumanRuntimeEvent,
    BoundRuntimeContext,
    ExecutionConfig,
    GraphRuntime,
    PortableContext,
    PortableEnvironment,
    PublishedArtifact,
    RuntimeServices,
    ToolInvocationResult,
    inspect_agent,
)
from agentic_backend.core.agents.v2.catalog import definition_to_agent_settings
from agentic_backend.core.agents.v2.context import (
    ArtifactScope,
    ToolContentBlock,
    ToolContentKind,
)
from agentic_backend.core.agents.v2.runtime import RuntimeEventKind


def _binding(session_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id,
            user_id="user-1",
            language="fr",
            selected_document_libraries_ids=["lib-1"],
            selected_document_uids=["doc-1"],
            selected_chat_context_ids=["ctx-1"],
            search_policy="hybrid",
        ),
        portable_context=PortableContext(
            request_id=f"req-{session_id}",
            correlation_id=f"corr-{session_id}",
            actor="user:test",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            agent_id="dva.risk_validator.graph.v2",
        ),
    )


def test_dva_graph_inspection_preview() -> None:
    definition = DVARiskValidatorGraph()

    inspection = inspect_agent(definition)

    assert inspection.agent_id == "dva.risk_validator.graph.v2"
    assert inspection.execution_category.value == "graph"
    assert inspection.preview.kind.value == "mermaid"
    assert "recommend_strategy" in inspection.preview.content
    assert "recommend_actions_mitigations" in inspection.preview.content


def test_dva_graph_chat_options_enabled() -> None:
    definition = DVARiskValidatorGraph()

    attach = next(
        field for field in definition.fields if field.key == "chat_options.attach_files"
    )
    libraries = next(
        field
        for field in definition.fields
        if field.key == "chat_options.libraries_selection"
    )
    documents = next(
        field
        for field in definition.fields
        if field.key == "chat_options.documents_selection"
    )
    rag_scope = next(
        field
        for field in definition.fields
        if field.key == "chat_options.search_rag_scoping"
    )

    assert attach.default is True
    assert libraries.default is True
    assert documents.default is True
    assert rag_scope.default is True

    settings = definition_to_agent_settings(
        definition,
        class_path="agentic_backend.agents.v2.candidate.DVARiskValidatorAssistant.graph.DVARiskValidatorGraph",
    )
    assert settings.chat_options.attach_files is True
    assert settings.chat_options.libraries_selection is True
    assert settings.chat_options.documents_selection is True
    assert settings.chat_options.search_rag_scoping is True


def test_dva_graph_declares_knowledge_search_tool() -> None:
    definition = DVARiskValidatorGraph()
    tool_refs = {tool.tool_ref for tool in definition.tool_requirements}
    assert "knowledge.search" in tool_refs


def test_report_includes_recommendation_sections() -> None:
    risk = RiskAssessment(
        risk_id="R-01",
        title="Test risk",
        source="source",
        order=1,
    )
    risk.recommendation.strategy = "Adopt a stricter control policy."
    risk.recommendation.actions = ["Action one", "Action two", "Action three"]

    report = render_report(risks=[risk], citations=[])

    assert "Recommended strategy (inferred)" in report
    assert "Recommended actions (inferred)" in report


@pytest.mark.asyncio
async def test_table_extraction_trims_to_max_count() -> None:
    definition = DVARiskValidatorGraph()
    table = (
        "| ID | Risk Title | Impact | Mitigation |\n"
        "| --- | --- | --- | --- |\n"
        "| 1 | Risk alpha | Impact | Mitigation |\n"
        "| 2 | Risk beta | Impact | Mitigation |\n"
        "| 3 | Risk gamma | Impact | Mitigation |\n"
    )
    hits = [
        VectorSearchHit(
            uid="hit-1",
            content=table,
            title="DVA",
            score=0.9,
            rank=1,
        )
    ]
    state = definition.state_model().model_validate(
        {
            "latest_user_text": "Analyse",
            "max_risk_count": 2,
            "risk_table_hits": [hit.model_dump(mode="json") for hit in hits],
        }
    )

    class FakeContext:
        model = None

    result = await definition.extract_source_risks(state, FakeContext())
    risks = result.state_update["risks"]
    assert len(risks) == 2


@pytest.mark.asyncio
async def test_dva_graph_asks_for_max_risk_count() -> None:
    definition = DVARiskValidatorGraph()
    runtime = GraphRuntime(definition=definition, services=RuntimeServices())
    runtime.bind(_binding("dva-graph-hitl"))
    executor = await runtime.get_executor()

    events = [
        event
        async for event in executor.stream(
            definition.input_model()(message="Analyse ce DVA"),
            ExecutionConfig(),
        )
    ]

    assert events
    assert events[-1].kind == RuntimeEventKind.AWAITING_HUMAN
    awaiting = events[-1]
    assert isinstance(awaiting, AwaitingHumanRuntimeEvent)
    assert "nombre maximum" in (awaiting.request.question or "")


@pytest.mark.asyncio
async def test_dva_graph_reasks_when_risk_count_too_large() -> None:
    definition = DVARiskValidatorGraph()

    class FakeContext:
        def __init__(self) -> None:
            self.calls = 0

        @property
        def binding(self):
            return _binding("dva-graph-reask")

        async def request_human_input(self, request):
            self.calls += 1
            if self.calls == 1:
                return {"answer": "42"}
            return {"answer": "10"}

    context = FakeContext()
    state = definition.state_model().model_validate(
        {"latest_user_text": "Analyse", "output_language": "fr"}
    )
    result = await definition.ask_max_risk_count(state, context)

    assert result.state_update["max_risk_count"] == 10
    assert context.calls == 2


@pytest.mark.asyncio
async def test_dva_graph_asks_for_risk_section_when_missing() -> None:
    definition = DVARiskValidatorGraph()

    class FakeContext:
        def __init__(self) -> None:
            self.binding = _binding("dva-graph-section")
            self.services = RuntimeServices(tool_invoker=SimpleNamespace())

        async def request_human_input(self, request):
            return {"answer": "Section risques"}

        async def invoke_tool(self, tool_ref, payload):
            return ToolInvocationResult(
                tool_ref=tool_ref,
                blocks=(
                    ToolContentBlock(kind=ToolContentKind.JSON, data={"hits": []}),
                ),
            )

    context = FakeContext()
    state = definition.state_model().model_validate(
        {"latest_user_text": "Analyse", "output_language": "fr"}
    )
    result = await definition.ask_risk_section(state, context)

    assert result.state_update["dva_invalid_reason"]


@pytest.mark.asyncio
async def test_dva_graph_publishes_artifacts_and_download_link() -> None:
    definition = DVARiskValidatorGraph()

    class FakeContext:
        def __init__(self) -> None:
            self.binding = _binding("dva-graph-publish")
            self.services = RuntimeServices(artifact_publisher=object())

        async def publish_text(self, *, file_name, text, title, content_type, **kwargs):
            return PublishedArtifact(
                scope=ArtifactScope.USER,
                key=file_name,
                file_name=file_name,
                size=len(text),
                href="https://example.test/download",
                document_uid=f"doc-{file_name}",
                mime=content_type,
                title=title,
            )

    context = FakeContext()
    state = definition.state_model().model_validate(
        {"latest_user_text": "Analyse", "report_markdown": "Report body"}
    )
    result = await definition.publish_outputs(state, context)

    assert result.state_update["published_report"].file_name == "result.md"
    assert result.state_update["published_index"].file_name == "risk_index.json"

    updated_state = state.model_copy(update=result.state_update)
    output = definition.build_output(updated_state)

    assert "Report body" in output.content
    assert output.ui_parts
    assert "http" not in output.content.lower()
    assert "Sources" not in output.content


@pytest.mark.asyncio
async def test_dva_graph_persists_session_scope_preferences() -> None:
    definition = DVARiskValidatorGraph()
    captured = {}

    class FakeContext:
        def __init__(self) -> None:
            self.binding = _binding("dva-graph-scope")
            self.services = RuntimeServices(tool_invoker=object())

        async def invoke_tool(self, tool_ref, payload):
            captured["tool_ref"] = tool_ref
            captured["payload"] = payload
            return ToolInvocationResult(tool_ref=tool_ref)

    context = FakeContext()
    report = PublishedArtifact(
        scope=ArtifactScope.USER,
        key="result.md",
        file_name="result.md",
        size=10,
        href="https://example.test/report",
        document_uid="doc-report",
        mime="text/markdown",
    )
    index = PublishedArtifact(
        scope=ArtifactScope.USER,
        key="risk_index.json",
        file_name="risk_index.json",
        size=10,
        href="https://example.test/index",
        document_uid="doc-index",
        mime="application/json",
    )
    state = definition.state_model().model_validate(
        {
            "latest_user_text": "Analyse",
            "published_report": report,
            "published_index": index,
        }
    )
    result = await definition.persist_session_scope(state, context)

    prefs = result.state_update["persisted_preferences"]
    assert captured["tool_ref"] == "session.preferences.update"
    assert prefs["includeSessionScope"] is True
    assert "doc-report" in prefs["documentUids"]
    assert "doc-index" in prefs["documentUids"]
