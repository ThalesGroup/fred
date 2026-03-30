from __future__ import annotations

from typing import cast

import pytest
from langchain_core.language_models.chat_models import BaseChatModel

from agentic_backend.agents.v2.definition_refs import (
    class_path_for_definition_ref,
)
from agentic_backend.agents.v2.production.dva_risk_validator import (
    DVARiskValidatorGraph,
    DVARiskValidatorQA,
)
from agentic_backend.agents.v2.production.dva_risk_validator.graph_state import (
    CitationSource,
    DVARiskValidatorState,
    RiskEvidence,
    RiskRecord,
)
from agentic_backend.agents.v2.production.dva_risk_validator.graph_steps import (
    _clean_extracted_risk_titles,
    _derive_coverage_reference,
    _result_contains_risk_table_signal,
    ask_max_risk_count_step,
    maybe_ask_risk_section_step,
    preview_required_nodes,
    publish_outputs_step,
)
from agentic_backend.agents.v2.production.dva_risk_validator.reporting import (
    blocker_status_for_risk,
    render_validation_report,
)
from agentic_backend.agents.v2.production.dva_risk_validator.session_scope import (
    merge_session_scope,
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    ArtifactScope,
    BoundRuntimeContext,
    GraphNodeContext,
    HumanInputRequest,
    PortableContext,
    PortableEnvironment,
    PublishedArtifact,
    RuntimeServices,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from agentic_backend.core.agents.v2.support.builtins import TOOL_REF_KNOWLEDGE_SEARCH


class _FakeContext:
    """Small graph context fake for offline unit tests."""

    def __init__(
        self,
        *,
        human_payload: object | None = None,
    ) -> None:
        self._human_payload = human_payload
        self.requests: list[HumanInputRequest] = []
        self.published: list[tuple[str, str]] = []

    @property
    def binding(self) -> BoundRuntimeContext:
        return BoundRuntimeContext(
            runtime_context=RuntimeContext(
                session_id="session-1",
                selected_document_libraries_ids=["lib-1"],
                selected_document_uids=["doc-1"],
                search_policy="semantic",
            ),
            portable_context=PortableContext(
                request_id="req-1",
                correlation_id="corr-1",
                actor="user:test",
                tenant="fred",
                environment=PortableEnvironment.DEV,
                session_id="session-1",
                agent_id="production.dva_risk_validator.graph",
            ),
        )

    @property
    def services(self) -> RuntimeServices:
        return cast(RuntimeServices, object())

    @property
    def model(self) -> BaseChatModel | None:
        return None

    def emit_status(self, status: str, detail: str | None = None) -> None:
        del status, detail

    def emit_assistant_delta(self, delta: str) -> None:
        del delta

    async def invoke_model(self, messages, *, operation="default"):
        del messages, operation
        raise RuntimeError("Not expected in this test context.")

    async def invoke_structured_model(
        self, output_model, messages, *, operation="default"
    ):
        del output_model, messages, operation
        raise RuntimeError("Not expected in this test context.")

    async def invoke_tool(
        self, tool_ref: str, payload: dict[str, object]
    ) -> ToolInvocationResult:
        assert tool_ref == TOOL_REF_KNOWLEDGE_SEARCH
        query = str(payload.get("query") or "")
        text = (
            "table des risques - propriétaire - date cible"
            if "risques" in query
            else "risk table owner target date"
        )
        return ToolInvocationResult(
            tool_ref=tool_ref,
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
        )

    async def invoke_runtime_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> object:
        del tool_name, arguments
        return None

    async def publish_text(self, **kwargs: object) -> PublishedArtifact:
        file_name = str(kwargs["file_name"])
        text = str(kwargs["text"])
        self.published.append((file_name, text))
        uid = "doc-result" if file_name == "result.md" else "doc-index"
        return PublishedArtifact(
            scope=ArtifactScope.USER,
            key=f"v2/{file_name}",
            file_name=file_name,
            size=len(text.encode("utf-8")),
            href=f"https://example.test/{file_name}",
            document_uid=uid,
            mime=str(kwargs.get("content_type") or "text/plain"),
            title=str(kwargs.get("title") or file_name),
        )

    async def publish_bytes(self, **kwargs: object) -> PublishedArtifact:
        del kwargs
        raise RuntimeError("Not expected in this test context.")

    async def fetch_resource(self, **kwargs: object) -> object:
        del kwargs
        raise RuntimeError("Not expected in this test context.")

    async def fetch_text_resource(self, **kwargs: object) -> str:
        del kwargs
        raise RuntimeError("Not expected in this test context.")

    async def request_human_input(self, request: HumanInputRequest) -> object:
        self.requests.append(request)
        return self._human_payload or {"text": "5"}


def _state_for_steps() -> DVARiskValidatorState:
    return DVARiskValidatorState(
        latest_user_text="Analyze this DVA.",
        all_risks=[
            RiskRecord(
                risk_id="R-01",
                title="Missing governance traceability",
                risk_type="Source",
                source_order=1,
                priority="P1",
                evidence=RiskEvidence(),
            )
        ],
        report_markdown="# report",
        risk_index_json="{}",
    )


def test_definition_wiring_and_stable_ids() -> None:
    graph = DVARiskValidatorGraph()
    qa = DVARiskValidatorQA()

    assert graph.agent_id == "production.dva_risk_validator.graph"
    assert qa.agent_id == "production.dva_risk_validator.qa"

    assert (
        class_path_for_definition_ref("v2.production.dva_risk_validator.graph")
        == "agentic_backend.agents.v2.production.dva_risk_validator.DVARiskValidatorGraph"
    )
    assert (
        class_path_for_definition_ref("v2.production.dva_risk_validator.qa")
        == "agentic_backend.agents.v2.production.dva_risk_validator.DVARiskValidatorQA"
    )


def test_chat_options_defaults_are_enabled_for_both_agents() -> None:
    graph_fields = {field.key: field for field in DVARiskValidatorGraph().fields}
    qa_fields = {field.key: field for field in DVARiskValidatorQA().fields}

    for key in (
        "chat_options.attach_files",
        "chat_options.libraries_selection",
        "chat_options.documents_selection",
        "chat_options.search_rag_scoping",
    ):
        assert graph_fields[key].default is True
        assert qa_fields[key].default is True


def test_graph_preview_contains_expected_major_nodes() -> None:
    preview = DVARiskValidatorGraph().preview().content
    for node_id in preview_required_nodes():
        assert node_id in preview


@pytest.mark.asyncio
async def test_risk_table_failure_path_emits_human_input_request() -> None:
    context = _FakeContext(human_payload={"text": "Section 5 - Matrice des risques"})

    result = await maybe_ask_risk_section_step(
        DVARiskValidatorState(
            latest_user_text="Validate",
            risk_table_located=False,
        ),
        cast(GraphNodeContext, context),
    )

    assert context.requests
    assert result.state_update["risk_section_hint"] == "Section 5 - Matrice des risques"


@pytest.mark.asyncio
async def test_max_risk_hitl_retries_when_above_30() -> None:
    context = _FakeContext(human_payload={"text": "35"})

    result = await ask_max_risk_count_step(
        DVARiskValidatorState(latest_user_text="Validate"),
        cast(GraphNodeContext, context),
    )

    assert result.route_key == "retry"


def test_report_format_sections_in_order_and_sources_at_end() -> None:
    risk = RiskRecord(
        risk_id="R-01",
        title="Supplier disruption",
        risk_type="Source",
        source_order=1,
        priority="P2",
        treatment_status="Partial",
        blocker=True,
        blocker_reason="Missing action owner.",
        evidence=RiskEvidence(
            coverage_ref="Risk section A",
            coverage_citation=1,
            strategy_text="Containment strategy",
            strategy_citation=1,
            actions=["Set fallback supplier"],
            action_citations=[1],
            owner_text="NO EVIDENCE FOUND",
            target_date_text="2026-06-30",
            target_date_citation=1,
            mapping_text="Section A",
            mapping_citation=1,
            evidence_status="Partial",
        ),
    )
    report = render_validation_report(
        [risk],
        [
            CitationSource(
                index=1, title="DVA", file_name="dva.pdf", document_uid="doc-1"
            )
        ],
    )

    s1 = report.index("## DVA Risks (Full List, Source Order)")
    s2 = report.index(
        "## Coverage List with reference to the paragraph that covers the risk"
    )
    s3 = report.index("## Treatment Validation Summary")
    s4 = report.index("## Treatment Validation Details")
    s5 = report.index("## Blockers & PDA Action Plan")
    s6 = report.index("## Sources")
    assert s1 < s2 < s3 < s4 < s5 < s6
    assert report.strip().endswith("document_uid=doc-1")


def test_blocker_rule_marks_missing_strategy_owner_or_target_date() -> None:
    risk = RiskRecord(
        risk_id="R-02",
        title="Delayed remediation",
        risk_type="Source",
        source_order=2,
        priority="P1",
        evidence=RiskEvidence(
            strategy_text="NO EVIDENCE FOUND",
            owner_text="NO EVIDENCE FOUND",
            target_date_text="NO EVIDENCE FOUND",
        ),
    )

    blocker, reason = blocker_status_for_risk(risk)
    assert blocker is True
    assert "strategy" in reason
    assert "action owner" in reason
    assert "action target date" in reason


@pytest.mark.asyncio
async def test_artifact_publication_and_ui_link_parts() -> None:
    context = _FakeContext()
    state = _state_for_steps()

    publish_result = await publish_outputs_step(state, cast(GraphNodeContext, context))
    updated = state.model_copy(update=publish_result.state_update)

    assert [name for name, _ in context.published] == ["result.md", "risk_index.json"]

    output = DVARiskValidatorGraph().build_output(updated)
    assert output.ui_parts
    assert len(output.ui_parts) == 2


def test_session_scope_persistence_merges_generated_document_uids() -> None:
    runtime_context = RuntimeContext(
        selected_document_libraries_ids=["lib-a"],
        selected_document_uids=["doc-source"],
        search_policy="semantic",
    )

    merged = merge_session_scope(
        runtime_context,
        generated_document_uids=["doc-result", "doc-index", "doc-result"],
    )

    assert merged.selected_document_libraries_ids == ["lib-a"]
    assert merged.selected_document_uids == ["doc-source", "doc-result", "doc-index"]
    assert merged.include_session_scope is True
    assert merged.search_policy == "semantic"


def test_qa_grounding_declares_knowledge_search_and_sources_contract() -> None:
    qa = DVARiskValidatorQA()
    refs = [item.tool_ref for item in qa.declared_tool_refs]

    assert TOOL_REF_KNOWLEDGE_SEARCH in refs
    assert "Sources" in qa.system_prompt_template


def test_risk_table_detection_accepts_bilingual_treatment_signals() -> None:
    result = ToolInvocationResult(
        tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
        blocks=(
            ToolContentBlock(
                kind=ToolContentKind.TEXT,
                text=(
                    "Analyse des risques: propriétaire, date cible, mesures de "
                    "mitigation pour chaque risque."
                ),
            ),
        ),
    )
    assert _result_contains_risk_table_signal(result) is True


def test_clean_extracted_risk_titles_filters_markdown_noise() -> None:
    cleaned = _clean_extracted_risk_titles(
        [
            "| **ID** | **Risk Title** | **Strategy** | **Impact** |",
            "| Core delivery risks | 1 | Cross-team dependency drift | Reduce | Schedule impact |",
            "[3. RISK REGISTER [10]][10]",
            "> In any case, highlight major points such as major risks and mitigation actions",
        ]
    )
    assert cleaned == ["Cross-team dependency drift"]


def test_coverage_reference_uses_clean_risk_table_row_label() -> None:
    risk_title = "Cross-team dependency drift"
    risk_text = (
        "| | **ID** | **Risk Title** | **Strategy** | **Impact** | **Action** |\n"
        "|----------|-----|--------------|---------|----------------|--------------------|\n"
        "| Core delivery risks | 1 | Cross-team dependency drift | Reduce | Schedule impact | Align interfaces |"
    )
    result = ToolInvocationResult(
        tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=risk_text),),
    )
    coverage = _derive_coverage_reference(
        risk_title=risk_title,
        risk_text=risk_text,
        search_result=result,
    )
    assert coverage == "Risk table row (Core delivery risks, ID 1)"
