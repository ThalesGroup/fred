from __future__ import annotations

import json
import re
from typing import Any, Iterable

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.common.rags_utils import trim_snippet
from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
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
    HumanInputRequest,
    PublishedArtifact,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.builtin_tools import TOOL_REF_KNOWLEDGE_SEARCH
from agentic_backend.core.agents.v2.prompt_resources import load_packaged_markdown

from ..shared.citations import build_citation_index, citations_for_hits
from ..shared.language import bilingual_queries, detect_language
from ..shared.models import CitationRecord, RiskAssessment, RiskIndex, RiskTreatment
from ..shared.rendering import render_report
from ..shared.retrieval import extract_hits, hits_to_dicts, hits_to_prompt_context

RISK_TABLE_QUERIES_EN = (
    "risk table",
    "risk register",
    "risks and mitigations",
    "risk assessment",
    "risk matrix",
)
RISK_TABLE_QUERIES_FR = (
    "table des risques",
    "registre des risques",
    "liste des risques",
    "analyse des risques",
    "matrice des risques",
    "mesures de mitigation",
)

DEFAULT_RISK_TABLE_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=(
        "agents",
        "v2",
        "candidate",
        "DVARiskValidatorAssistant",
        "graph",
        "prompts",
        "risk_table_extract.md",
    ),
)
DEFAULT_INFERRED_RISKS_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=(
        "agents",
        "v2",
        "candidate",
        "DVARiskValidatorAssistant",
        "graph",
        "prompts",
        "inferred_risks.md",
    ),
)
DEFAULT_TREATMENT_VALIDATION_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=(
        "agents",
        "v2",
        "candidate",
        "DVARiskValidatorAssistant",
        "graph",
        "prompts",
        "treatment_validation.md",
    ),
)
DEFAULT_RECOMMEND_STRATEGY_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=(
        "agents",
        "v2",
        "candidate",
        "DVARiskValidatorAssistant",
        "graph",
        "prompts",
        "recommend_strategy.md",
    ),
)
DEFAULT_RECOMMEND_ACTIONS_PROMPT = load_packaged_markdown(
    package="agentic_backend",
    path_parts=(
        "agents",
        "v2",
        "candidate",
        "DVARiskValidatorAssistant",
        "graph",
        "prompts",
        "recommend_actions.md",
    ),
)


class DVARiskValidatorInput(BaseModel):
    message: str = Field(..., min_length=1)


class DVARiskValidatorState(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    latest_user_text: str
    max_risk_count: int | None = None
    output_language: str | None = None
    risk_table_queries: list[str] = Field(default_factory=list)
    risk_table_hits: list[dict[str, Any]] = Field(default_factory=list)
    risk_table_found: bool = False
    risk_table_rows: dict[str, str] = Field(default_factory=dict)
    risk_section_hint: str | None = None
    dva_invalid_reason: str | None = None
    risks: list[RiskAssessment] = Field(default_factory=list)
    risk_evidence: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    report_markdown: str | None = None
    published_report: PublishedArtifact | None = None
    published_index: PublishedArtifact | None = None
    persisted_preferences: dict[str, Any] | None = None


class DVARiskValidatorGraph(GraphAgentDefinition):
    agent_id: str = "dva.risk_validator.graph.v2"
    role: str = "DVA Risk Validator (Graph)"
    description: str = "Validates that DVA risks are treated, traceable, and evidenced with explicit recommendations."
    tags: tuple[str, ...] = ("dva", "risk", "validator", "graph", "v2")

    risk_table_prompt_template: str = Field(
        default=DEFAULT_RISK_TABLE_PROMPT, min_length=1
    )
    inferred_risks_prompt_template: str = Field(
        default=DEFAULT_INFERRED_RISKS_PROMPT, min_length=1
    )
    treatment_validation_prompt_template: str = Field(
        default=DEFAULT_TREATMENT_VALIDATION_PROMPT, min_length=1
    )
    recommend_strategy_prompt_template: str = Field(
        default=DEFAULT_RECOMMEND_STRATEGY_PROMPT, min_length=1
    )
    recommend_actions_prompt_template: str = Field(
        default=DEFAULT_RECOMMEND_ACTIONS_PROMPT, min_length=1
    )
    retrieval_top_k: int = Field(default=6, ge=1, le=20)

    fields: tuple[FieldSpec, ...] = (
        FieldSpec(
            key="risk_table_prompt_template",
            type="prompt",
            title="Risk table extraction prompt",
            description="Prompt used to extract the ordered risk table.",
            required=True,
            default=DEFAULT_RISK_TABLE_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="inferred_risks_prompt_template",
            type="prompt",
            title="Inferred risks prompt",
            description="Prompt used to infer additional risks.",
            required=True,
            default=DEFAULT_INFERRED_RISKS_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="treatment_validation_prompt_template",
            type="prompt",
            title="Treatment validation prompt",
            description="Prompt used to validate treatment coverage.",
            required=True,
            default=DEFAULT_TREATMENT_VALIDATION_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="recommend_strategy_prompt_template",
            type="prompt",
            title="Recommendation strategy prompt",
            description="Prompt used to infer strategies.",
            required=True,
            default=DEFAULT_RECOMMEND_STRATEGY_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="recommend_actions_prompt_template",
            type="prompt",
            title="Recommendation actions prompt",
            description="Prompt used to infer actions/mitigations.",
            required=True,
            default=DEFAULT_RECOMMEND_ACTIONS_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="retrieval_top_k",
            type="integer",
            title="Retrieval Top-K",
            description="Number of snippets requested per retrieval call.",
            required=False,
            default=6,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Enable attachments",
            description="Allow session attachments and file uploads.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Enable library selection",
            description="Allow selecting document libraries for retrieval.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.documents_selection",
            type="boolean",
            title="Enable document selection",
            description="Allow selecting specific documents for retrieval.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.search_rag_scoping",
            type="boolean",
            title="Enable RAG scope selection",
            description="Allow choosing corpus-only, hybrid, or general search.",
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
    )

    tool_requirements: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref=TOOL_REF_KNOWLEDGE_SEARCH,
            description="Search DVA documents and session scope.",
        ),
        ToolRefRequirement(
            tool_ref="session.preferences.update",
            description="Persist session scope preferences for QA follow-up.",
        ),
    )

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="DVARiskValidatorState",
            entry_node="route_or_start",
            nodes=(
                GraphNodeDefinition(
                    node_id="route_or_start",
                    title="Start",
                    shape=GraphNodeShape.ROUND,
                ),
                GraphNodeDefinition(
                    node_id="ask_max_risk_count",
                    title="Ask max risk count",
                ),
                GraphNodeDefinition(
                    node_id="locate_risk_table",
                    title="Locate risk table",
                ),
                GraphNodeDefinition(
                    node_id="ask_risk_section",
                    title="Ask risk table section",
                    shape=GraphNodeShape.DIAMOND,
                ),
                GraphNodeDefinition(
                    node_id="extract_source_risks",
                    title="Extract source risks",
                ),
                GraphNodeDefinition(
                    node_id="enrich_to_requested_count",
                    title="Enrich with inferred risks",
                ),
                GraphNodeDefinition(
                    node_id="retrieve_coverage_evidence",
                    title="Retrieve coverage evidence",
                ),
                GraphNodeDefinition(
                    node_id="validate_treatment",
                    title="Validate treatment",
                ),
                GraphNodeDefinition(
                    node_id="recommend_strategy",
                    title="Recommend strategy",
                ),
                GraphNodeDefinition(
                    node_id="recommend_actions_mitigations",
                    title="Recommend actions",
                ),
                GraphNodeDefinition(
                    node_id="build_report",
                    title="Build report",
                ),
                GraphNodeDefinition(
                    node_id="publish_outputs",
                    title="Publish outputs",
                ),
                GraphNodeDefinition(
                    node_id="persist_session_scope",
                    title="Persist session scope",
                ),
                GraphNodeDefinition(
                    node_id="finalize",
                    title="Finalize",
                    shape=GraphNodeShape.ROUND,
                ),
            ),
            edges=(
                GraphEdgeDefinition(
                    source="route_or_start", target="ask_max_risk_count"
                ),
                GraphEdgeDefinition(
                    source="ask_max_risk_count", target="locate_risk_table"
                ),
                GraphEdgeDefinition(
                    source="extract_source_risks", target="enrich_to_requested_count"
                ),
                GraphEdgeDefinition(
                    source="enrich_to_requested_count",
                    target="retrieve_coverage_evidence",
                ),
                GraphEdgeDefinition(
                    source="retrieve_coverage_evidence", target="validate_treatment"
                ),
                GraphEdgeDefinition(
                    source="validate_treatment", target="recommend_strategy"
                ),
                GraphEdgeDefinition(
                    source="recommend_strategy", target="recommend_actions_mitigations"
                ),
                GraphEdgeDefinition(
                    source="recommend_actions_mitigations", target="build_report"
                ),
                GraphEdgeDefinition(source="build_report", target="publish_outputs"),
                GraphEdgeDefinition(
                    source="publish_outputs", target="persist_session_scope"
                ),
                GraphEdgeDefinition(source="persist_session_scope", target="finalize"),
            ),
            conditionals=(
                GraphConditionalDefinition(
                    source="locate_risk_table",
                    routes=(
                        GraphRouteDefinition(
                            route_key="found",
                            target="extract_source_risks",
                            label="risk table found",
                        ),
                        GraphRouteDefinition(
                            route_key="missing",
                            target="ask_risk_section",
                            label="risk table missing",
                        ),
                    ),
                ),
                GraphConditionalDefinition(
                    source="ask_risk_section",
                    routes=(
                        GraphRouteDefinition(
                            route_key="found",
                            target="extract_source_risks",
                            label="risk table found",
                        ),
                        GraphRouteDefinition(
                            route_key="missing",
                            target="extract_source_risks",
                            label="risk table missing",
                        ),
                    ),
                ),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return DVARiskValidatorInput

    def state_model(self) -> type[BaseModel]:
        return DVARiskValidatorState

    def output_model(self) -> type[BaseModel]:
        return GraphExecutionOutput

    def build_initial_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
    ) -> BaseModel:
        model = DVARiskValidatorInput.model_validate(input_model)
        user_language = (binding.runtime_context.language or "").strip().lower()
        return DVARiskValidatorState(
            latest_user_text=model.message,
            output_language=user_language or None,
        )

    def node_handlers(self) -> dict[str, object]:
        return {
            "route_or_start": self.route_or_start,
            "ask_max_risk_count": self.ask_max_risk_count,
            "locate_risk_table": self.locate_risk_table,
            "ask_risk_section": self.ask_risk_section,
            "extract_source_risks": self.extract_source_risks,
            "enrich_to_requested_count": self.enrich_to_requested_count,
            "retrieve_coverage_evidence": self.retrieve_coverage_evidence,
            "validate_treatment": self.validate_treatment,
            "recommend_strategy": self.recommend_strategy,
            "recommend_actions_mitigations": self.recommend_actions_mitigations,
            "build_report": self.build_report,
            "publish_outputs": self.publish_outputs,
            "persist_session_scope": self.persist_session_scope,
            "finalize": self.finalize,
        }

    def build_output(self, state: BaseModel) -> BaseModel:
        graph_state = DVARiskValidatorState.model_validate(state)
        ui_parts = ()
        if graph_state.published_report is not None:
            ui_parts = (graph_state.published_report.to_link_part(),)
        return GraphExecutionOutput(
            content=graph_state.report_markdown or "",
            ui_parts=ui_parts,
        )

    async def route_or_start(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        del context
        graph_state = DVARiskValidatorState.model_validate(state)
        return GraphNodeResult(
            state_update={"latest_user_text": graph_state.latest_user_text}
        )

    async def ask_max_risk_count(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        question = "Indique le nombre maximum de risques a analyser (max 30)."
        while True:
            decision = await context.request_human_input(
                HumanInputRequest(
                    stage="dva_risk_count",
                    title="Nombre maximum de risques",
                    question=question,
                    free_text=True,
                )
            )
            answer = self._extract_free_text(decision)
            max_count = self._coerce_int(answer)
            if max_count is None or max_count <= 0:
                question = "Merci d'indiquer un nombre entier positif (max 30)."
                continue
            if max_count > 30:
                question = (
                    "C'est un nombre important. Merci d'indiquer un nombre strictement "
                    "inferieur a 30."
                )
                continue
            return GraphNodeResult(state_update={"max_risk_count": max_count})

    async def locate_risk_table(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        language = graph_state.output_language or ""
        if language not in {"fr", "en"}:
            language = "fr"
        queries = bilingual_queries(
            primary_language=language,
            english_queries=RISK_TABLE_QUERIES_EN,
            french_queries=RISK_TABLE_QUERIES_FR,
        )
        hits = await self._run_queries(context, queries)
        found = bool(hits)
        detected_language = graph_state.output_language
        if not detected_language and hits:
            detected_language = detect_language(
                [getattr(hit, "content", "") for hit in hits]
            )
        return GraphNodeResult(
            state_update={
                "risk_table_queries": list(queries),
                "risk_table_hits": hits_to_dicts(hits),
                "risk_table_found": found,
                "output_language": detected_language,
            },
            route_key="found" if found else "missing",
        )

    async def ask_risk_section(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        decision = await context.request_human_input(
            HumanInputRequest(
                stage="dva_risk_section",
                title="Section des risques",
                question=(
                    "Je ne trouve pas la table des risques. "
                    "Indique le nom de la section ou du chapitre qui la contient."
                ),
                free_text=True,
            )
        )
        section_hint = self._extract_free_text(decision) or None
        hits: list[Any] = []
        if section_hint:
            hits = await self._run_queries(context, [section_hint])
        found = bool(hits)
        state_update = {
            "risk_section_hint": section_hint,
            "risk_table_hits": hits_to_dicts(hits),
            "risk_table_found": found,
        }
        if not found:
            state_update["dva_invalid_reason"] = (
                "DVA invalid: risk table not found after human input."
            )
        return GraphNodeResult(
            state_update=state_update,
            route_key="found" if found else "missing",
        )

    async def extract_source_risks(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        if not graph_state.risk_table_hits:
            return GraphNodeResult(state_update={"risks": []})
        hits = self._hits_from_state(graph_state.risk_table_hits)
        table_risks = self._extract_table_risks(hits)
        if table_risks:
            risks = self._assign_risk_ids(table_risks, source="source")
            max_count = graph_state.max_risk_count
            if max_count and len(risks) > max_count:
                risks = risks[:max_count]
            row_map = self._build_row_map(table_risks, risks)
            return GraphNodeResult(
                state_update={
                    "risks": risks,
                    "risk_table_rows": row_map,
                }
            )
        prompt_context = hits_to_prompt_context(hits)
        parsed = await self._invoke_json_prompt(
            context=context,
            prompt_template=self.risk_table_prompt_template,
            operation="risk_table_extract",
            retrieved_context=prompt_context,
        )
        risk_items = parsed.get("risks") if isinstance(parsed, dict) else None
        extracted: list[dict[str, str]] = []
        if isinstance(risk_items, list):
            for item in risk_items:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                if not title or self._is_noise_title(title):
                    continue
                extracted.append(
                    {
                        "id": str(item.get("id") or "").strip(),
                        "title": title,
                    }
                )
        if not extracted:
            extracted = self._fallback_extract_from_hits(hits)
        if not extracted:
            return GraphNodeResult(
                state_update={
                    "risks": [],
                    "dva_invalid_reason": (
                        "DVA invalid: risk table could not be parsed."
                    ),
                }
            )
        risks = self._assign_risk_ids(extracted, source="source")
        max_count = graph_state.max_risk_count
        if max_count and len(risks) > max_count:
            risks = risks[:max_count]
        row_map = self._build_row_map(extracted, risks)
        return GraphNodeResult(
            state_update={
                "risks": risks,
                "risk_table_rows": row_map,
            }
        )

    async def enrich_to_requested_count(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        max_count = graph_state.max_risk_count or len(graph_state.risks)
        if len(graph_state.risks) >= max_count:
            return GraphNodeResult(state_update={"risks": graph_state.risks})
        existing_titles = [risk.title for risk in graph_state.risks]
        prompt_context = "\n".join(existing_titles)
        parsed = await self._invoke_json_prompt(
            context=context,
            prompt_template=self.inferred_risks_prompt_template,
            operation="infer_risks",
            retrieved_context="\n".join(existing_titles[:8]),
            existing_risks=prompt_context,
        )
        inferred_list = parsed.get("risks") if isinstance(parsed, dict) else None
        inferred_items: list[dict[str, str]] = []
        if isinstance(inferred_list, list):
            for item in inferred_list:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                if not title or title in existing_titles:
                    continue
                inferred_items.append({"id": "", "title": title})
        needed = max_count - len(graph_state.risks)
        inferred_items = inferred_items[:needed]
        inferred_risks = self._assign_risk_ids(
            inferred_items,
            source="inferred",
            start_index=len(graph_state.risks) + 1,
            existing_ids=[r.risk_id for r in graph_state.risks],
        )
        return GraphNodeResult(
            state_update={"risks": graph_state.risks + inferred_risks}
        )

    async def retrieve_coverage_evidence(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        evidence: dict[str, list[dict[str, Any]]] = {}
        for risk in graph_state.risks:
            queries = self._coverage_queries(risk.title, graph_state.output_language)
            hits = await self._run_queries(context, queries, top_k=4)
            evidence[risk.risk_id] = hits_to_dicts(hits)
        return GraphNodeResult(state_update={"risk_evidence": evidence})

    async def validate_treatment(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        updated: list[RiskAssessment] = []
        for risk in graph_state.risks:
            hits = self._hits_from_state(
                graph_state.risk_evidence.get(risk.risk_id, [])
            )
            row_text = graph_state.risk_table_rows.get(risk.risk_id, "").strip()
            if hits:
                prompt_context = hits_to_prompt_context(hits)
            else:
                prompt_context = "NO EVIDENCE FOUND"
            if row_text:
                prompt_context = f"Table row:\\n{row_text}\\n\\n{prompt_context}"
            parsed = await self._invoke_json_prompt(
                context=context,
                prompt_template=self.treatment_validation_prompt_template,
                operation="validate_treatment",
                risk_title=risk.title,
                retrieved_context=prompt_context,
            )
            assessment = risk.model_copy(deep=True)
            treatment = self._apply_treatment_from_parsed(assessment, parsed, hits)
            assessment.treatment = treatment
            assessment = self._apply_validation_defaults(assessment, hits)
            updated.append(assessment)
        return GraphNodeResult(state_update={"risks": updated})

    async def recommend_strategy(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        updated: list[RiskAssessment] = []
        for risk in graph_state.risks:
            parsed = await self._invoke_json_prompt(
                context=context,
                prompt_template=self.recommend_strategy_prompt_template,
                operation="recommend_strategy",
                risk_title=risk.title,
                dva_context=trim_snippet(graph_state.latest_user_text, 400),
            )
            assessment = risk.model_copy(deep=True)
            strategy = None
            if isinstance(parsed, dict):
                strategy = str(parsed.get("strategy") or "").strip() or None
            assessment.recommendation.strategy = strategy
            updated.append(assessment)
        return GraphNodeResult(state_update={"risks": updated})

    async def recommend_actions_mitigations(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        updated: list[RiskAssessment] = []
        for risk in graph_state.risks:
            parsed = await self._invoke_json_prompt(
                context=context,
                prompt_template=self.recommend_actions_prompt_template,
                operation="recommend_actions",
                risk_title=risk.title,
            )
            actions: list[str] = []
            if isinstance(parsed, dict):
                raw_actions = parsed.get("actions")
                if isinstance(raw_actions, list):
                    for action in raw_actions:
                        text = str(action or "").strip()
                        if text:
                            actions.append(text)
            assessment = risk.model_copy(deep=True)
            assessment.recommendation.actions = actions[:3]
            updated.append(assessment)
        return GraphNodeResult(state_update={"risks": updated})

    async def build_report(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        del context
        graph_state = DVARiskValidatorState.model_validate(state)
        all_hits = []
        for hit_list in graph_state.risk_evidence.values():
            all_hits.extend(self._hits_from_state(hit_list))
        citations, index_map = build_citation_index(all_hits)
        updated: list[RiskAssessment] = []
        for risk in graph_state.risks:
            hits = self._hits_from_state(
                graph_state.risk_evidence.get(risk.risk_id, [])
            )
            assessment = risk.model_copy(deep=True)
            assessment.coverage.citations = citations_for_hits(hits, index_map)
            if not assessment.coverage.section and hits:
                assessment.coverage.section = hits[0].section or hits[0].title
            updated.append(assessment)
        report = render_report(
            risks=updated,
            citations=citations,
            dva_invalid_reason=graph_state.dva_invalid_reason,
        )
        return GraphNodeResult(
            state_update={
                "risks": updated,
                "report_markdown": report,
                "citations": [c.model_dump(mode="json") for c in citations],
            }
        )

    async def publish_outputs(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        report_text = graph_state.report_markdown or ""
        state_update: dict[str, object] = {}
        if context.services.artifact_publisher is not None:
            report_artifact = await context.publish_text(
                file_name="result.md",
                text=report_text,
                title="DVA risk validation report",
                content_type="text/markdown; charset=utf-8",
            )
            risk_index = self._build_risk_index(
                graph_state, context.binding.runtime_context
            )
            index_artifact = await context.publish_text(
                file_name="risk_index.json",
                text=json.dumps(risk_index.as_json(), ensure_ascii=False, indent=2),
                title="DVA risk index",
                content_type="application/json; charset=utf-8",
            )
            state_update["published_report"] = report_artifact
            state_update["published_index"] = index_artifact
        return GraphNodeResult(state_update=state_update)

    async def persist_session_scope(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = DVARiskValidatorState.model_validate(state)
        prefs = self._build_session_preferences(
            context.binding.runtime_context,
            graph_state.published_report,
            graph_state.published_index,
        )
        try:
            await context.invoke_tool(
                "session.preferences.update", {"preferences": prefs}
            )
        except Exception:
            pass
        return GraphNodeResult(state_update={"persisted_preferences": prefs})

    async def finalize(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        del state, context
        return GraphNodeResult()

    def _coverage_queries(self, title: str, language: str | None) -> list[str]:
        base = title.strip()
        if not base:
            return []
        english = [
            f"{base} mitigation",
            f"{base} treatment",
            f"{base} owner",
        ]
        french = [
            f"{base} mitigation",
            f"{base} traitement",
            f"{base} responsable",
        ]
        primary = language or "fr"
        return bilingual_queries(
            primary_language="en" if primary == "en" else "fr",
            english_queries=english,
            french_queries=french,
        )

    async def _run_queries(
        self,
        context: GraphNodeContext,
        queries: Iterable[str],
        top_k: int | None = None,
    ) -> list[Any]:
        hits: list[Any] = []
        if context.services.tool_invoker is None:
            return hits
        for query in queries:
            if not query:
                continue
            result = await context.invoke_tool(
                TOOL_REF_KNOWLEDGE_SEARCH,
                {"query": query, "top_k": top_k or self.retrieval_top_k},
            )
            hits.extend(extract_hits(result))
            if hits:
                break
        return hits

    def _extract_free_text(self, decision: object) -> str:
        if isinstance(decision, dict):
            for key in ("text", "answer", "notes"):
                value = decision.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(decision, str):
            return decision.strip()
        return ""

    def _coerce_int(self, value: str | None) -> int | None:
        if not value:
            return None
        match = re.search(r"\d+", value)
        if not match:
            return None
        try:
            return int(match.group(0))
        except ValueError:
            return None

    def _render_prompt(self, template: str, **kwargs: str) -> str:
        prompt = template
        for key, value in kwargs.items():
            prompt = prompt.replace("{" + key + "}", value)
        return prompt

    async def _invoke_json_prompt(
        self,
        *,
        context: GraphNodeContext,
        prompt_template: str,
        operation: str,
        **kwargs: str,
    ) -> dict[str, Any]:
        if context.model is None:
            return {}
        prompt = self._render_prompt(prompt_template, **kwargs)
        response = await context.invoke_model(
            [HumanMessage(content=prompt)], operation=operation
        )
        content = getattr(response, "content", "")
        text = content if isinstance(content, str) else ""
        return self._parse_json_object(text)

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {}
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}

    def _fallback_extract_from_hits(self, hits: list[Any]) -> list[dict[str, str]]:
        extracted = self._extract_table_risks(hits)
        if extracted:
            return extracted
        return []

    def _extract_table_risks(self, hits: list[Any]) -> list[dict[str, str]]:
        extracted: list[dict[str, str]] = []
        for hit in hits:
            content = (getattr(hit, "content", None) or "").strip()
            if "|" not in content:
                continue
            lines = [line for line in content.splitlines() if "|" in line]
            if not lines:
                continue
            header_index = self._find_table_header_index(lines)
            if header_index is None:
                continue
            header_line = lines[header_index].strip()
            header_cells = self._split_table_row(lines[header_index])
            id_idx = self._find_header_index(header_cells, {"id", "identifiant"})
            title_idx = self._find_header_index(
                header_cells,
                {"risk title", "titre", "titre du risque", "risque", "risk"},
            )
            if title_idx is None:
                continue
            for row in lines[header_index + 1 :]:
                if self._is_table_separator(row):
                    continue
                cells = self._split_table_row(row)
                if len(cells) <= title_idx:
                    continue
                title = cells[title_idx].strip()
                if not title or self._is_noise_title(title):
                    continue
                risk_id = ""
                if id_idx is not None and len(cells) > id_idx:
                    risk_id = cells[id_idx].strip()
                record: dict[str, str] = {
                    "id": risk_id,
                    "title": title,
                    "row_text": row.strip(),
                    "row_context": f"{header_line}\n{row.strip()}",
                }
                record.update(self._parse_table_fields_from_row(header_cells, cells))
                extracted.append(record)
        return extracted

    def _find_table_header_index(self, lines: list[str]) -> int | None:
        for idx, line in enumerate(lines):
            cells = self._split_table_row(line)
            joined = " ".join(cells).lower()
            if "risk title" in joined or "titre" in joined or "risque" in joined:
                return idx
        return None

    def _split_table_row(self, line: str) -> list[str]:
        trimmed = line.strip().strip("|")
        return [cell.strip() for cell in trimmed.split("|")]

    def _is_table_separator(self, line: str) -> bool:
        stripped = line.strip().strip("|").replace(":", "").replace("-", "")
        return not stripped

    def _find_header_index(self, cells: list[str], tokens: set[str]) -> int | None:
        for idx, cell in enumerate(cells):
            lowered = cell.lower().strip()
            for token in tokens:
                if token in lowered:
                    return idx
        return None

    def _is_noise_title(self, title: str) -> bool:
        lowered = title.lower().strip()
        if lowered in {"risk title", "risque", "risques", "impact", "mitigation"}:
            return True
        if (
            lowered.startswith("[")
            or lowered.startswith(">")
            or lowered.startswith("*")
        ):
            return True
        if "risk title" in lowered:
            return True
        if len(re.findall(r"[a-zA-Z]", lowered)) < 3:
            return True
        return False

    def _parse_table_fields_from_row(
        self, header_cells: list[str], row_cells: list[str]
    ) -> dict[str, str]:
        def _cell_value(idx: int | None) -> str:
            if idx is None or idx >= len(row_cells):
                return ""
            return row_cells[idx].strip()

        def _find(tokens: set[str]) -> int | None:
            return self._find_header_index(header_cells, tokens)

        return {
            "strategy": _cell_value(_find({"strategie", "strategy"})),
            "actions": _cell_value(
                _find(
                    {
                        "action",
                        "actions",
                        "mitigation",
                        "mitigations",
                        "mesures",
                        "traitement",
                        "measure",
                        "measures",
                    }
                )
            ),
            "owner": _cell_value(
                _find({"owner", "responsable", "proprietaire", "pilote"})
            ),
            "target_date": _cell_value(
                _find({"target date", "date", "echeance", "deadline"})
            ),
            "mapping": _cell_value(_find({"mapping", "dva mapping", "lien"})),
        }

    def _assign_risk_ids(
        self,
        items: list[dict[str, str]],
        *,
        source: str,
        start_index: int = 1,
        existing_ids: list[str] | None = None,
    ) -> list[RiskAssessment]:
        existing_ids = existing_ids or []
        prefix, width = self._infer_id_pattern(
            [item.get("id", "") for item in items] + existing_ids
        )
        risks: list[RiskAssessment] = []
        counter = start_index
        for item in items:
            raw_id = (item.get("id") or "").strip()
            risk_id = raw_id
            if risk_id:
                if risk_id.isdigit():
                    if prefix:
                        risk_id = f"{prefix}{risk_id.zfill(width)}"
                    elif width > len(risk_id):
                        risk_id = risk_id.zfill(width)
            else:
                risk_id = f"{prefix}{str(counter).zfill(width)}"
            assessment = RiskAssessment(
                risk_id=risk_id,
                title=item.get("title", "").strip(),
                source=source,  # type: ignore[arg-type]
                order=counter,
            )
            self._apply_table_treatment_fields(assessment, item)
            risks.append(assessment)
            counter += 1
        return risks

    def _infer_id_pattern(self, ids: list[str]) -> tuple[str, int]:
        for value in ids:
            if not value:
                continue
            if value.strip().isdigit():
                return "", len(value.strip())
            match = re.match(r"([A-Za-z]+[-_ ]?)(\d+)", value.strip())
            if match:
                return match.group(1), max(2, len(match.group(2)))
        return "R-", 2

    def _hits_from_state(self, hits: list[dict[str, Any]]) -> list[Any]:
        from fred_core import VectorSearchHit

        return [VectorSearchHit.model_validate(hit) for hit in hits]

    def _apply_treatment_from_parsed(
        self,
        assessment: RiskAssessment,
        parsed: dict[str, Any],
        hits: list[Any],
    ) -> RiskTreatment:
        treatment = assessment.treatment.model_copy(deep=True)
        if isinstance(parsed, dict):
            strategy = str(parsed.get("strategy") or "").strip()
            if strategy:
                treatment.strategy = strategy
            raw_actions = parsed.get("actions")
            actions: list[str] = []
            if isinstance(raw_actions, list):
                for action in raw_actions:
                    text = str(action or "").strip()
                    if text:
                        actions.append(text)
            if actions:
                treatment.actions = actions
            owner = str(parsed.get("owner") or "").strip()
            if owner:
                treatment.owner = owner
            target_date = str(parsed.get("target_date") or "").strip()
            if target_date:
                treatment.target_date = target_date
            mapping = str(parsed.get("mapping") or "").strip()
            if mapping:
                treatment.mapping = mapping
            assessment.coverage.section = (
                str(parsed.get("coverage_section") or "").strip() or None
            )
            priority = str(parsed.get("inferred_priority") or "").strip()
            if priority in {"P0", "P1", "P2", "P3"}:
                assessment.inferred_priority = priority  # type: ignore[assignment]
            treatment_status = str(parsed.get("treatment_status") or "").strip()
            if treatment_status in {"Adequate", "Partial", "Missing"}:
                assessment.treatment_status = treatment_status  # type: ignore[assignment]
            evidence_status = str(parsed.get("evidence_status") or "").strip()
            if evidence_status in {"Sufficient", "Partial", "NO EVIDENCE FOUND"}:
                assessment.evidence.status = evidence_status  # type: ignore[assignment]
        if hits and not assessment.coverage.section:
            assessment.coverage.section = hits[0].section or hits[0].title
        return treatment

    def _apply_table_treatment_fields(
        self, assessment: RiskAssessment, item: dict[str, str]
    ) -> None:
        strategy = (item.get("strategy") or "").strip()
        if strategy:
            assessment.treatment.strategy = strategy
        actions = (item.get("actions") or "").strip()
        if actions:
            assessment.treatment.actions = [actions]
        owner = (item.get("owner") or "").strip()
        if owner:
            assessment.treatment.owner = owner
        target_date = (item.get("target_date") or "").strip()
        if target_date:
            assessment.treatment.target_date = target_date
        mapping = (item.get("mapping") or "").strip()
        if mapping:
            assessment.treatment.mapping = mapping

    def _build_row_map(
        self, items: list[dict[str, str]], risks: list[RiskAssessment]
    ) -> dict[str, str]:
        rows: dict[str, str] = {}
        for item, risk in zip(items, risks):
            row_text = (item.get("row_context") or item.get("row_text") or "").strip()
            if row_text:
                rows[risk.risk_id] = row_text
        return rows

    def _apply_validation_defaults(
        self, assessment: RiskAssessment, hits: list[Any]
    ) -> RiskAssessment:
        has_strategy = bool(assessment.treatment.strategy)
        has_actions = bool(assessment.treatment.actions)
        has_owner = bool(assessment.treatment.owner)
        has_target = bool(assessment.treatment.target_date)

        if not hits:
            assessment.evidence.status = "NO EVIDENCE FOUND"
        elif has_strategy and has_actions and has_owner and has_target:
            assessment.evidence.status = "Sufficient"
        else:
            assessment.evidence.status = "Partial"

        if has_strategy and has_actions:
            assessment.treatment_status = "Adequate"
        elif has_strategy or has_actions or has_owner or has_target:
            assessment.treatment_status = "Partial"
        else:
            assessment.treatment_status = "Missing"

        if not has_strategy or not has_owner or not has_target:
            assessment.blocker = True
            missing = []
            if not has_strategy:
                missing.append("strategy")
            if not has_owner:
                missing.append("owner")
            if not has_target:
                missing.append("target date")
            assessment.blocker_reason = (
                "Missing required fields: " + ", ".join(missing)
                if missing
                else "Missing required fields"
            )
        else:
            assessment.blocker = False
            assessment.blocker_reason = None
        return assessment

    def _build_risk_index(
        self, graph_state: DVARiskValidatorState, runtime_context: RuntimeContext
    ) -> RiskIndex:
        citations = [
            CitationRecord.model_validate(item) for item in graph_state.citations
        ]
        risk_index = RiskIndex(
            generated_at=RiskIndex.build_timestamp(),
            source_document_uids=list(runtime_context.selected_document_uids or []),
            source_document_library_ids=list(
                runtime_context.selected_document_libraries_ids or []
            ),
            include_session_scope=True,
            search_policy=runtime_context.search_policy,
            risks=graph_state.risks,
            citations=citations,
        )
        return risk_index

    def _build_session_preferences(
        self,
        runtime_context: RuntimeContext,
        report_artifact: PublishedArtifact | None,
        index_artifact: PublishedArtifact | None,
    ) -> dict[str, Any]:
        document_uids: list[str] = []
        if runtime_context.selected_document_uids:
            document_uids.extend(runtime_context.selected_document_uids)
        for artifact in (report_artifact, index_artifact):
            if artifact and artifact.document_uid:
                if artifact.document_uid not in document_uids:
                    document_uids.append(artifact.document_uid)
        prefs: dict[str, Any] = {
            "includeSessionScope": True,
            "searchPolicy": runtime_context.search_policy or "hybrid",
        }
        if runtime_context.selected_chat_context_ids:
            prefs["chatContextIds"] = list(runtime_context.selected_chat_context_ids)
        if runtime_context.selected_document_libraries_ids:
            prefs["documentLibraryIds"] = list(
                runtime_context.selected_document_libraries_ids
            )
        if document_uids:
            prefs["documentUids"] = document_uids
        return prefs
