"""
Graph v2 example for initial bid qualification.

This workflow intentionally covers only the first useful step:
- route request
- retrieve context from corpus
- extract requirements/constraints
- ask clarifications when data is missing
- publish a structured summary
"""

# TODO(bid-intake): Do one more authoring-alignment pass after the first field
# test with a real bid manager.
# - The LLM prompts already follow the packaged Markdown pattern.
# - The fallback lexicon already follows the packaged JSON pattern.
# - The remaining fixed French UX strings in this file are still graph
#   orchestration copy (node titles, route labels, status text, clarification
#   text, summary headings, artifact labels, unsupported-path message).
# - These strings are deterministic workflow/UI copy, not model prompts, but
#   they should eventually be externalized into a dedicated resource layer so
#   this agent fully matches the developer pattern we want to promote.

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field

from agentic_backend.core.agents.agent_spec import FieldSpec, UIHints
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
    ToolContentKind,
    ToolInvocationResult,
    ToolRefRequirement,
)
from agentic_backend.core.agents.v2.lexicon_resources import load_agent_lexicon_json
from agentic_backend.core.agents.v2.prompt_resources import (
    load_agent_prompt_markdown,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class BidIntakeRoutingLexicon(FrozenModel):
    bid_signals: tuple[str, ...] = ()
    requirement_signals: tuple[str, ...] = ()
    constraint_signals: tuple[str, ...] = ()
    deliverable_signals: tuple[str, ...] = ()
    compliance_signals: tuple[str, ...] = ()
    customer_markers: tuple[str, ...] = ()
    scope_markers: tuple[str, ...] = ()
    timeline_markers: tuple[str, ...] = ()
    budget_markers: tuple[str, ...] = ()
    evaluation_markers: tuple[str, ...] = ()
    fallback_analyze_markers: tuple[str, ...] = ()
    missing_information_labels: dict[str, str] = Field(default_factory=dict)


DEFAULT_ROUTING_LEXICON = BidIntakeRoutingLexicon.model_validate(
    load_agent_lexicon_json(
        package="agentic_backend.agents.v2.candidate.bid_mgr",
        file_name="bid_intake_routing_lexicon.json",
    )
)
DEFAULT_ROUTER_PROMPT = load_agent_prompt_markdown(
    package="agentic_backend.agents.v2.candidate.bid_mgr",
    file_name="bid_intake_router_prompt.md",
)
DEFAULT_ANALYSIS_PROMPT = load_agent_prompt_markdown(
    package="agentic_backend.agents.v2.candidate.bid_mgr",
    file_name="bid_intake_analysis_prompt.md",
)


def _bid_intake_fields() -> tuple[FieldSpec, ...]:
    return (
        FieldSpec(
            key="router_prompt_template",
            type="prompt",
            title="Prompt de routage",
            description=(
                "Instructions du routeur d'intention. Utiliser le placeholder "
                "`{latest_user}` pour injecter le dernier message utilisateur."
            ),
            required=True,
            default=DEFAULT_ROUTER_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="analysis_prompt_template",
            type="prompt",
            title="Prompt d'analyse",
            description=(
                "Instructions d'extraction de la synthese initiale. Utiliser les "
                "placeholders `{brief}` et `{retrieved_context}` pour injecter le "
                "brief client accumule et les extraits recuperes depuis le corpus."
            ),
            required=True,
            default=DEFAULT_ANALYSIS_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="chat_options.attach_files",
            type="boolean",
            title="Autoriser les pieces jointes",
            description=(
                "Expose les pieces jointes de session pour permettre l'analyse d'un "
                "dossier bid ajoute directement dans la conversation."
            ),
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.libraries_selection",
            type="boolean",
            title="Selection des bibliotheques",
            description=(
                "Expose le selecteur de bibliotheques documentaires afin de "
                "cibler le corpus RAO de cette analyse."
            ),
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.search_rag_scoping",
            type="boolean",
            title="Selection du mode RAG",
            description=(
                "Expose le selecteur corpus uniquement / hybride / connaissances "
                "generales pour piloter la recherche du dossier."
            ),
            required=False,
            default=True,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="routing_lexicon",
            type="object",
            title="Lexique de routage et de fallback",
            description=(
                "Vocabulaire metier utilise pour le fallback de routage et pour "
                "les extractions heuristiques de secours. Ce lexique reste "
                "secondaire par rapport au routage semantique par le modele."
            ),
            required=True,
            default=DEFAULT_ROUTING_LEXICON.model_dump(mode="json"),
            ui=UIHints(group="Routing", textarea=True),
        ),
    )


class BidIntakeGraphInput(BaseModel):
    message: str = Field(..., min_length=1)


class BidIntakeGraphState(BaseModel):
    latest_user_text: str
    accumulated_brief: str
    routing_source: str | None = None
    routing_reason: str | None = None
    routing_confidence: float = 0.0
    retrieval_query: str | None = None
    retrieved_corpus_context: str | None = None
    retrieved_hit_count: int = 0
    customer_name: str | None = None
    opportunity_name: str | None = None
    scope_summary: str | None = None
    requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    compliance_items: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    recommended_next_step: str | None = None
    needs_clarification: bool = False
    clarification_round: int = 0
    published_summary: PublishedArtifact | None = None
    final_text: str | None = None


class Definition(GraphAgentDefinition):
    """
    Focused bid-intake workflow built with `GraphAgentDefinition`.

    Quick edit guide:
    - node sequence and branches: `build_graph()`
    - extraction prompts: markdown resources
    - fallback vocabulary: `routing_lexicon`
    - output document shape: `_render_summary(...)`
    """

    agent_id: str = "bid.intake.graph.v2"
    role: str = "Assistant de qualification d'offre"
    description: str = (
        "Analyse un brief client initial, extrait les exigences et contraintes, "
        "demande les informations manquantes et produit une synthese structuree."
    )
    tags: tuple[str, ...] = ("bid", "graph", "qualification", "requirements", "demo")
    router_prompt_template: str = Field(default=DEFAULT_ROUTER_PROMPT, min_length=1)
    analysis_prompt_template: str = Field(
        default=DEFAULT_ANALYSIS_PROMPT,
        min_length=1,
    )
    routing_lexicon: dict[str, object] = Field(
        default_factory=lambda: DEFAULT_ROUTING_LEXICON.model_dump(mode="json")
    )
    fields: tuple[FieldSpec, ...] = _bid_intake_fields()
    tool_requirements: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref="knowledge.search",
            description=(
                "Recherche les extraits pertinents dans le corpus de l'equipe ou "
                "les documents selectionnes pour alimenter l'analyse initiale d'offre."
            ),
        ),
    )

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="BidIntakeGraphState",
            entry_node="route_request",
            nodes=(
                GraphNodeDefinition(
                    node_id="route_request",
                    title="Router la demande",
                    shape=GraphNodeShape.DIAMOND,
                ),
                GraphNodeDefinition(
                    node_id="analyze_intake",
                    title="Analyser le brief client",
                ),
                GraphNodeDefinition(
                    node_id="retrieve_bid_context",
                    title="Chercher dans le corpus bid",
                ),
                GraphNodeDefinition(
                    node_id="request_clarifications",
                    title="Demander des clarifications",
                ),
                GraphNodeDefinition(
                    node_id="build_summary",
                    title="Construire la synthese",
                ),
                GraphNodeDefinition(
                    node_id="unsupported_request",
                    title="Gerer une demande hors perimetre",
                ),
                GraphNodeDefinition(
                    node_id="finalize",
                    title="Finaliser la reponse",
                    shape=GraphNodeShape.ROUND,
                ),
            ),
            edges=(
                GraphEdgeDefinition(
                    source="retrieve_bid_context",
                    target="analyze_intake",
                ),
                GraphEdgeDefinition(
                    source="request_clarifications",
                    target="analyze_intake",
                ),
                GraphEdgeDefinition(source="build_summary", target="finalize"),
                GraphEdgeDefinition(source="unsupported_request", target="finalize"),
            ),
            conditionals=(
                GraphConditionalDefinition(
                    source="route_request",
                    routes=(
                        GraphRouteDefinition(
                            route_key="analyze",
                            target="retrieve_bid_context",
                            label="qualification offre",
                        ),
                        GraphRouteDefinition(
                            route_key="unsupported",
                            target="unsupported_request",
                            label="hors perimetre",
                        ),
                    ),
                ),
                GraphConditionalDefinition(
                    source="analyze_intake",
                    routes=(
                        GraphRouteDefinition(
                            route_key="clarify",
                            target="request_clarifications",
                            label="clarifier",
                        ),
                        GraphRouteDefinition(
                            route_key="summarize",
                            target="build_summary",
                            label="synthese",
                        ),
                    ),
                ),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return BidIntakeGraphInput

    def state_model(self) -> type[BaseModel]:
        return BidIntakeGraphState

    def output_model(self) -> type[BaseModel]:
        return GraphExecutionOutput

    def build_initial_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
    ) -> BaseModel:
        del binding
        model = BidIntakeGraphInput.model_validate(input_model)
        return BidIntakeGraphState(
            latest_user_text=model.message,
            accumulated_brief=model.message.strip(),
        )

    def node_handlers(self) -> dict[str, object]:
        return {
            "route_request": self.route_request,
            "retrieve_bid_context": self.retrieve_bid_context,
            "analyze_intake": self.analyze_intake,
            "request_clarifications": self.request_clarifications,
            "build_summary": self.build_summary,
            "unsupported_request": self.unsupported_request,
            "finalize": self.finalize,
        }

    def build_output(self, state: BaseModel) -> BaseModel:
        graph_state = BidIntakeGraphState.model_validate(state)
        ui_parts = ()
        if graph_state.published_summary is not None:
            ui_parts = (graph_state.published_summary.to_link_part(),)
        return GraphExecutionOutput(
            content=graph_state.final_text or "",
            ui_parts=ui_parts,
        )

    async def route_request(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = BidIntakeGraphState.model_validate(state)
        latest_user = graph_state.latest_user_text.strip()
        decision = await self._route_intent_with_model(
            context=context,
            latest_user=latest_user,
        )
        route_key = str(decision.get("route") or "unsupported").strip().lower()
        state_update = {
            "routing_source": str(decision.get("_source") or "unknown"),
            "routing_reason": str(decision.get("reason") or "").strip() or None,
            "routing_confidence": self._coerce_confidence(decision.get("confidence")),
        }

        if route_key == "analyze":
            context.emit_status(
                "routing",
                "Intention de qualification detectee ; routage vers l'analyse.",
            )
            context.emit_status(
                "bid_intake",
                "Brief client detecte ; lancement de l'analyse de qualification.",
            )
            return GraphNodeResult(state_update=state_update, route_key="analyze")

        return GraphNodeResult(state_update=state_update, route_key="unsupported")

    async def retrieve_bid_context(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = BidIntakeGraphState.model_validate(state)
        query = self._build_retrieval_query(graph_state)
        state_update: dict[str, object] = {
            "retrieval_query": query or None,
            "retrieved_corpus_context": None,
            "retrieved_hit_count": 0,
        }

        if not query:
            return GraphNodeResult(state_update=state_update)

        if context.services.tool_invoker is None:
            context.emit_status(
                "bid_corpus_search",
                "Recherche corpus indisponible ; poursuite avec le brief fourni.",
            )
            return GraphNodeResult(state_update=state_update)

        context.emit_status(
            "bid_corpus_search",
            "Recherche des extraits pertinents dans le corpus bid selectionne.",
        )
        try:
            result = await context.invoke_tool(
                "knowledge.search",
                {"query": query, "top_k": 6},
            )
        except Exception:
            context.emit_status(
                "bid_corpus_search",
                "Echec de la recherche corpus ; poursuite avec le brief fourni.",
            )
            return GraphNodeResult(state_update=state_update)

        hits = self._extract_search_hits(result)
        corpus_context = self._render_corpus_context(hits)
        return GraphNodeResult(
            state_update={
                **state_update,
                "retrieved_corpus_context": corpus_context or None,
                "retrieved_hit_count": len(hits),
            }
        )

    async def analyze_intake(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = BidIntakeGraphState.model_validate(state)
        context.emit_status(
            "bid_intake_analysis",
            "Extraction des exigences client, contraintes et informations manquantes.",
        )

        analysis = await self._analyze_with_model(
            context=context,
            brief=graph_state.accumulated_brief,
            retrieved_context=graph_state.retrieved_corpus_context
            or "Aucun extrait pertinent n'a ete recupere depuis le corpus Fred.",
        )
        if analysis is None:
            analysis = self._fallback_analysis(graph_state.accumulated_brief)
        normalized = self._normalize_analysis_payload(analysis)
        raw_missing_information = normalized.get("missing_information")
        missing_information = (
            [item for item in raw_missing_information if isinstance(item, str)]
            if isinstance(raw_missing_information, list)
            else []
        )
        normalized["missing_information"] = self._localize_missing_information(
            missing_information
        )

        needs_clarification = (
            normalized["needs_clarification"]
            and bool(normalized["missing_information"])
            and graph_state.clarification_round == 0
        )

        return GraphNodeResult(
            state_update={
                "customer_name": normalized["customer_name"],
                "opportunity_name": normalized["opportunity_name"],
                "scope_summary": normalized["scope_summary"],
                "requirements": normalized["requirements"],
                "constraints": normalized["constraints"],
                "deliverables": normalized["deliverables"],
                "compliance_items": normalized["compliance_items"],
                "assumptions": normalized["assumptions"],
                "ambiguities": normalized["ambiguities"],
                "missing_information": normalized["missing_information"],
                "recommended_next_step": normalized["recommended_next_step"],
                "needs_clarification": needs_clarification,
            },
            route_key="clarify" if needs_clarification else "summarize",
        )

    async def request_clarifications(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = BidIntakeGraphState.model_validate(state)
        missing_items = graph_state.missing_information[:5]
        if not missing_items:
            return GraphNodeResult(
                state_update={
                    "clarification_round": graph_state.clarification_round + 1
                }
            )

        question_lines = [
            "J'ai besoin de quelques elements supplementaires pour qualifier correctement cette opportunite.",
            "Merci de repondre en texte libre avec les informations que vous connaissez sur les points suivants :",
            *[f"- {item}" for item in missing_items],
        ]
        decision = await context.request_human_input(
            HumanInputRequest(
                stage="bid_intake_clarification",
                title="Preciser les informations manquantes",
                question="\n".join(question_lines),
                free_text=True,
                metadata={
                    "missing_count": len(missing_items),
                    "clarification_round": graph_state.clarification_round + 1,
                },
            )
        )
        answer = self._extract_free_text(decision)
        updated_brief = graph_state.accumulated_brief
        if answer:
            updated_brief = (
                f"{updated_brief}\n\nPrecision du bid manager :\n{answer.strip()}"
            )

        return GraphNodeResult(
            state_update={
                "accumulated_brief": updated_brief,
                "clarification_round": graph_state.clarification_round + 1,
            }
        )

    async def build_summary(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = BidIntakeGraphState.model_validate(state)
        summary_text = self._render_summary(graph_state)
        state_update: dict[str, object] = {"final_text": summary_text}

        if context.services.artifact_publisher is not None:
            artifact = await context.publish_text(
                file_name=self._summary_file_name(graph_state),
                text=summary_text,
                title="Telecharger la synthese de qualification",
                content_type="text/markdown; charset=utf-8",
            )
            state_update["published_summary"] = artifact
            state_update["final_text"] = (
                f"{summary_text}\n\nUne copie persistante a ete enregistree dans Fred "
                "et est disponible en telechargement."
            )

        return GraphNodeResult(state_update=state_update)

    async def unsupported_request(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        del state, context
        return GraphNodeResult(
            state_update={
                "final_text": (
                    "Ce premier workflow de qualification attend un brief client, "
                    "un extrait de RFI/RFP ou des notes de capture decrivant les "
                    "exigences, contraintes, livrables, budget, jalons ou attentes "
                    "de conformite."
                )
            }
        )

    async def finalize(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        del state, context
        return GraphNodeResult()

    async def _analyze_with_model(
        self,
        *,
        context: GraphNodeContext,
        brief: str,
        retrieved_context: str,
    ) -> dict[str, Any] | None:
        if context.model is None:
            return None

        prompt = self._render_prompt_template(
            self.analysis_prompt_template,
            brief=brief,
            retrieved_context=retrieved_context,
        )
        try:
            response = await context.invoke_model(
                [HumanMessage(content=prompt)],
                operation="analysis",
            )
        except Exception:
            return None

        content = self._message_content_to_text(getattr(response, "content", ""))
        return self._parse_json_object_from_text(content)

    async def _route_intent_with_model(
        self,
        *,
        context: GraphNodeContext,
        latest_user: str,
    ) -> dict[str, Any]:
        if context.model is None or not latest_user.strip():
            return self._fallback_intent_router(latest_user=latest_user)

        prompt = self._intent_router_prompt(latest_user=latest_user)
        try:
            response = await context.invoke_model(
                [HumanMessage(content=prompt)],
                operation="intent_router",
            )
            text = self._message_content_to_text(getattr(response, "content", ""))
            parsed = self._parse_json_object_from_text(text) or {}
            if not parsed:
                raise ValueError("empty/invalid JSON router output")

            route_raw = str(parsed.get("route") or "").strip().lower()
            route = (
                "analyze"
                if route_raw in {"analyze", "analysis", "bid_intake"}
                else "unsupported"
            )
            return {
                "route": route,
                "confidence": self._coerce_confidence(parsed.get("confidence")),
                "reason": str(parsed.get("reason") or "").strip(),
                "_source": "llm_router",
            }
        except Exception:
            return self._fallback_intent_router(latest_user=latest_user)

    def _intent_router_prompt(self, *, latest_user: str) -> str:
        return self._render_prompt_template(
            self.router_prompt_template,
            latest_user=latest_user,
        )

    def _fallback_intent_router(self, *, latest_user: str) -> dict[str, Any]:
        if self._looks_like_bid_intake(latest_user):
            return {
                "route": "analyze",
                "confidence": 0.35,
                "reason": "fallback heuristique: signaux explicites de qualification d'offre detectes",
                "_source": "fallback",
            }
        return {
            "route": "unsupported",
            "confidence": 0.15,
            "reason": "fallback heuristique: aucun signal suffisant de qualification d'offre",
            "_source": "fallback",
        }

    @classmethod
    def _normalize_analysis_payload(cls, payload: dict[str, Any]) -> dict[str, object]:
        customer_name = cls._coerce_optional_text(payload.get("customer_name"))
        opportunity_name = cls._coerce_optional_text(payload.get("opportunity_name"))
        scope_summary = cls._coerce_optional_text(payload.get("scope_summary"))
        requirements = cls._coerce_str_list(payload.get("requirements"))
        constraints = cls._coerce_str_list(payload.get("constraints"))
        deliverables = cls._coerce_str_list(payload.get("deliverables"))
        compliance_items = cls._coerce_str_list(payload.get("compliance_items"))
        assumptions = cls._coerce_str_list(payload.get("assumptions"))
        ambiguities = cls._coerce_str_list(payload.get("ambiguities"))
        missing_information = cls._coerce_str_list(payload.get("missing_information"))
        recommended_next_step = cls._coerce_optional_text(
            payload.get("recommended_next_step")
        ) or cls._default_next_step(missing_information)
        needs_clarification = bool(payload.get("needs_clarification"))

        if not scope_summary:
            summary_parts = []
            if requirements:
                summary_parts.append(requirements[0])
            if constraints:
                summary_parts.append(f"Contrainte principale : {constraints[0]}")
            scope_summary = " ".join(summary_parts)[:280] or None

        if not requirements and payload.get("scope_summary"):
            requirements = [str(payload["scope_summary"]).strip()]

        if missing_information and not needs_clarification:
            needs_clarification = len(missing_information) >= 3

        return {
            "customer_name": customer_name,
            "opportunity_name": opportunity_name,
            "scope_summary": scope_summary,
            "requirements": requirements,
            "constraints": constraints,
            "deliverables": deliverables,
            "compliance_items": compliance_items,
            "assumptions": assumptions,
            "ambiguities": ambiguities,
            "missing_information": missing_information,
            "needs_clarification": needs_clarification,
            "recommended_next_step": recommended_next_step,
        }

    def _fallback_analysis(self, brief: str) -> dict[str, Any]:
        lexicon = self._routing_lexicon()
        text = brief.strip()
        sentences = self._candidate_sentences(text)
        requirements = [
            sentence
            for sentence in sentences
            if self._contains_any(sentence, lexicon.requirement_signals)
        ][:8]
        constraints = [
            sentence
            for sentence in sentences
            if self._contains_any(sentence, lexicon.constraint_signals)
        ][:8]
        deliverables = [
            sentence
            for sentence in sentences
            if self._contains_any(sentence, lexicon.deliverable_signals)
        ][:6]
        compliance_items = [
            sentence
            for sentence in sentences
            if self._contains_any(sentence, lexicon.compliance_signals)
        ][:6]

        missing_information: list[str] = []
        labels = lexicon.missing_information_labels
        if not self._contains_any(text, lexicon.customer_markers):
            missing_information.append(labels["customer_contracting_authority"])
        if not self._contains_any(text, lexicon.scope_markers):
            missing_information.append(labels["solution_scope_perimeter"])
        if not self._contains_any(text, lexicon.timeline_markers):
            missing_information.append(labels["submission_timeline"])
        if not self._contains_any(text, lexicon.budget_markers):
            missing_information.append(labels["budget_expectations"])
        if not self._contains_any(text, lexicon.evaluation_markers):
            missing_information.append(labels["evaluation_criteria"])

        needs_clarification = bool(missing_information) and (
            len(missing_information) >= 3 or not requirements
        )

        return {
            "customer_name": None,
            "opportunity_name": None,
            "scope_summary": text[:280] if text else None,
            "requirements": requirements[:8] or ([text[:180]] if text else []),
            "constraints": constraints[:8],
            "deliverables": deliverables[:6],
            "compliance_items": compliance_items[:6],
            "assumptions": [],
            "ambiguities": [],
            "missing_information": missing_information[:5],
            "needs_clarification": needs_clarification,
            "recommended_next_step": self._default_next_step(missing_information),
        }

    def _build_retrieval_query(self, state: BidIntakeGraphState) -> str:
        base_text = state.accumulated_brief.strip() or state.latest_user_text.strip()
        if not base_text:
            return ""

        collapsed = re.sub(r"\s+", " ", base_text).strip()
        lexicon = self._routing_lexicon()
        signal_bank = list(
            dict.fromkeys(
                (
                    *lexicon.requirement_signals[:2],
                    *lexicon.constraint_signals[:2],
                    *lexicon.deliverable_signals[:2],
                    *lexicon.evaluation_markers[:2],
                    *lexicon.compliance_signals[:2],
                )
            )
        )
        suffix = " ".join(signal_bank[:8]).strip()
        query = collapsed if not suffix else f"{collapsed} {suffix}"
        if len(query) <= 420:
            return query
        return query[:417].rsplit(" ", 1)[0].strip() + "..."

    @classmethod
    def _extract_search_hits(
        cls, result: ToolInvocationResult
    ) -> list[dict[str, object]]:
        for block in result.blocks:
            if block.kind != ToolContentKind.JSON or not isinstance(block.data, dict):
                continue
            raw_hits = block.data.get("hits")
            if not isinstance(raw_hits, list):
                continue
            return [
                hit
                for hit in raw_hits
                if isinstance(hit, dict)
                and cls._coerce_optional_text(hit.get("content"))
            ]
        return []

    @classmethod
    def _render_corpus_context(cls, hits: list[dict[str, object]]) -> str:
        sections: list[str] = []
        for index, hit in enumerate(hits[:5], start=1):
            title = (
                cls._coerce_optional_text(hit.get("title"))
                or cls._coerce_optional_text(hit.get("uid"))
                or f"document-{index}"
            )
            content = (
                cls._coerce_optional_text(hit.get("content"))
                or cls._coerce_optional_text(hit.get("snippet"))
                or cls._coerce_optional_text(hit.get("text"))
            )
            if not content:
                continue
            compact = re.sub(r"\s+", " ", content).strip()
            if len(compact) > 900:
                compact = compact[:897].rstrip() + "..."
            sections.append(f"[Extrait {index}] {title}\n{compact}")
        return "\n\n".join(sections).strip()

    @classmethod
    def _render_summary(cls, state: BidIntakeGraphState) -> str:
        lines = [
            "# Synthese De Qualification D'Offre",
            "",
            "Cette sortie est volontairement limitee a la premiere etape de qualification.",
            "",
            f"- Client : {state.customer_name or 'n/a'}",
            f"- Opportunite : {state.opportunity_name or 'n/a'}",
            f"- Tours de clarification : {state.clarification_round}",
            "",
            "## Resume Du Perimetre",
            state.scope_summary or "n/a",
            "",
            "## Exigences Client",
            *cls._render_bullets(state.requirements),
            "",
            "## Contraintes Client",
            *cls._render_bullets(state.constraints),
            "",
            "## Livrables Attendus",
            *cls._render_bullets(state.deliverables),
            "",
            "## Points De Conformite / Gouvernance",
            *cls._render_bullets(state.compliance_items),
            "",
            "## Ambiguites Et Hypotheses",
            *cls._render_bullets(state.ambiguities or state.assumptions),
            "",
            "## Informations Encore Manquantes",
            *cls._render_bullets(state.missing_information),
            "",
            "## Prochaine Etape Recommandee",
            state.recommended_next_step
            or "Valider cette qualification avec le bid manager avant le Gate 1.",
        ]
        return "\n".join(lines).strip()

    @classmethod
    def _summary_file_name(cls, state: BidIntakeGraphState) -> str:
        base = state.opportunity_name or state.customer_name or "bid-intake-summary"
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", base.strip()).strip("-._").lower()
        if not slug:
            slug = "bid-intake-summary"
        return f"{slug}.md"

    @staticmethod
    def _render_bullets(items: list[str]) -> list[str]:
        if not items:
            return ["- n/a"]
        return [f"- {item}" for item in items]

    @staticmethod
    def _extract_free_text(decision: object) -> str:
        if isinstance(decision, str):
            return decision.strip()
        if isinstance(decision, dict):
            for key in ("answer", "text", "notes", "message"):
                value = decision.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    @staticmethod
    def _default_next_step(missing_information: list[str]) -> str:
        if missing_information:
            return (
                "Valider les informations d'offre manquantes avec le capture leader "
                "ou le bid manager avant de preparer le Gate 1."
            )
        return (
            "Transformer cette qualification en pack de cadrage Gate 1 avec les "
            "responsables, les hypotheses de solution de reference et une premiere "
            "synthese executive."
        )

    @staticmethod
    def _render_prompt_template(template: str, /, **values: str) -> str:
        try:
            return template.format(**values)
        except KeyError as exc:
            missing_key = exc.args[0]
            raise ValueError(
                f"Missing placeholder '{missing_key}' in bid-intake prompt rendering."
            ) from exc

    def _looks_like_bid_intake(self, text: str) -> bool:
        lexicon = self._routing_lexicon()
        normalized = self._normalize_text(text)
        if not normalized:
            return False
        keyword_hits = sum(
            1
            for keyword in lexicon.bid_signals
            if self._normalize_text(keyword) in normalized
        )
        if keyword_hits >= 1:
            return True
        return len(normalized) > 200 and any(
            self._normalize_text(token) in normalized
            for token in lexicon.fallback_analyze_markers
        )

    @staticmethod
    def _message_content_to_text(content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            return "\n".join(part.strip() for part in chunks if part.strip()).strip()
        return str(content).strip()

    @staticmethod
    def _parse_json_object_from_text(text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if not stripped:
            return None
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return None
        candidate = stripped[start : end + 1]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _coerce_confidence(value: object) -> float:
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, int | float):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            try:
                return max(0.0, min(1.0, float(value.strip())))
            except ValueError:
                return 0.0
        return 0.0

    @staticmethod
    def _coerce_optional_text(value: object) -> str | None:
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return None

    def _routing_lexicon(self) -> BidIntakeRoutingLexicon:
        return BidIntakeRoutingLexicon.model_validate(self.routing_lexicon)

    @classmethod
    def _coerce_str_list(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                continue
            text = re.sub(r"\s+", " ", item).strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned.append(text)
        return cleaned

    def _localize_missing_information(self, items: list[str]) -> list[str]:
        localized: list[str] = []
        labels = self._routing_lexicon().missing_information_labels
        mappings = {
            "customer contracting authority": labels["customer_contracting_authority"],
            "scope and target solution perimeter": labels["solution_scope_perimeter"],
            "submission timeline key dates": labels["submission_timeline"],
            "budget or price expectations": labels["budget_expectations"],
            "evaluation criteria winning factors": labels["evaluation_criteria"],
            "target submission date": labels["target_submission_date"],
        }
        for item in items:
            normalized = self._normalize_text(item)
            replacement = mappings.get(normalized)
            localized.append(replacement or item)
        return localized

    @classmethod
    def _candidate_sentences(cls, text: str) -> list[str]:
        parts = re.split(r"[\n\r;]+|(?<=[.!?])\s+", text)
        sentences: list[str] = []
        for part in parts:
            cleaned = re.sub(r"\s+", " ", part).strip(" -\t")
            if len(cleaned) >= 12:
                sentences.append(cleaned)
        return sentences[:20]

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        raw = (text or "").strip().lower()
        raw = "".join(
            ch
            for ch in unicodedata.normalize("NFKD", raw)
            if not unicodedata.combining(ch)
        )
        raw = re.sub(r"[^a-z0-9]+", " ", raw)
        return " ".join(raw.split())

    @classmethod
    def _contains_any(cls, text: str, terms: tuple[str, ...]) -> bool:
        normalized = cls._normalize_text(text)
        return any(cls._normalize_text(term) in normalized for term in terms)
