"""
Aegis-like Graph v2 skeleton.

This file is intentionally a starter template, not a production migration.
It demonstrates how the v1 Aegis story (retrieve -> draft -> self-check ->
corrective loop) can be expressed with the v2 graph contract.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

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
    ToolRefRequirement,
)

DEFAULT_GENERATE_DRAFT_PROMPT = (
    "You are Aegis v2 skeleton. Write a concise grounded draft answer.\n"
    "Question:\n{question}\n\n"
    "Retrieved context:\n{retrieved_context}\n\n"
    "Rules:\n"
    "- Use only retrieved evidence.\n"
    "- If evidence is weak, state uncertainty explicitly.\n"
    "- Keep answer practical and short."
)

DEFAULT_SELF_CHECK_PROMPT = (
    "Evaluate the grounded quality of the following answer.\n"
    "Return strict JSON with keys:\n"
    '- "grounded" (boolean)\n'
    '- "confidence" (number between 0 and 1)\n'
    '- "notes" (string)\n'
    '- "followup_queries" (array of strings)\n\n'
    "Question:\n{question}\n\n"
    "Answer:\n{draft_answer}\n\n"
    "Retrieved context:\n{retrieved_context}"
)

DEFAULT_CORRECTIVE_QUERY_PROMPT = (
    "Generate up to 3 short follow-up retrieval queries to reduce uncertainty.\n"
    "Question:\n{question}\n\n"
    "Current answer:\n{draft_answer}\n\n"
    "Self-check notes:\n{self_check_notes}\n\n"
    'Return JSON: {{"queries": ["..."]}}'
)

logger = logging.getLogger(__name__)


def _aegis_graph_skeleton_fields() -> tuple[FieldSpec, ...]:
    return (
        FieldSpec(
            key="generate_draft_prompt_template",
            type="prompt",
            title="Generate draft prompt",
            description=(
                "Prompt used in node `generate_draft` (operation=generate_draft)."
            ),
            required=True,
            default=DEFAULT_GENERATE_DRAFT_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="self_check_prompt_template",
            type="prompt",
            title="Self-check prompt",
            description=("Prompt used in node `self_check` (operation=self_check)."),
            required=True,
            default=DEFAULT_SELF_CHECK_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="corrective_query_prompt_template",
            type="prompt",
            title="Corrective query prompt",
            description=(
                "Prompt used to propose follow-up retrieval queries "
                "(operation=corrective_queries)."
            ),
            required=True,
            default=DEFAULT_CORRECTIVE_QUERY_PROMPT,
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="retrieval_top_k",
            type="integer",
            title="Retrieval Top-K",
            description="Number of chunks requested per retrieval call.",
            required=False,
            default=8,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="max_iterations",
            type="integer",
            title="Corrective iterations",
            description="Maximum corrective loops before best-effort finalization.",
            required=False,
            default=2,
            ui=UIHints(group="Quality"),
        ),
        FieldSpec(
            key="self_check_min_confidence",
            type="number",
            title="Self-check confidence threshold",
            description=(
                "If self-check confidence is below this threshold, trigger a "
                "corrective loop."
            ),
            required=False,
            default=0.65,
            ui=UIHints(group="Quality"),
        ),
    )


class AegisGraphSkeletonInput(BaseModel):
    message: str = Field(..., min_length=1)


class AegisGraphSkeletonState(BaseModel):
    latest_user_text: str
    retrieval_query: str | None = None
    retrieved_context: str = ""
    retrieved_chunk_count: int = 0
    draft_answer: str = ""
    self_check_grounded: bool = False
    self_check_confidence: float = 0.0
    self_check_notes: str = ""
    followup_queries: list[str] = Field(default_factory=list)
    iteration: int = 0
    final_text: str | None = None
    done_reason: str | None = None


class AegisGraphV2SkeletonDefinition(GraphAgentDefinition):
    """
    Aegis-like workflow skeleton for v2 graph runtime.

    Goal:
    - provide a concrete migration scaffold for v1 Aegis developers
    - keep business flow explicit and testable
    - demonstrate operation-aware model calls (`generate_draft`, `self_check`)
    """

    agent_id: str = "aegis.graph.skeleton.v2"
    role: str = "Aegis graph skeleton"
    description: str = (
        "Skeleton of a self-correcting RAG workflow (retrieve, draft, self-check, "
        "corrective loop) using GraphRuntime."
    )
    tags: tuple[str, ...] = ("aegis", "graph", "rag", "skeleton", "v2")
    generate_draft_prompt_template: str = Field(
        default=DEFAULT_GENERATE_DRAFT_PROMPT,
        min_length=1,
    )
    self_check_prompt_template: str = Field(
        default=DEFAULT_SELF_CHECK_PROMPT,
        min_length=1,
    )
    corrective_query_prompt_template: str = Field(
        default=DEFAULT_CORRECTIVE_QUERY_PROMPT,
        min_length=1,
    )
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    max_iterations: int = Field(default=2, ge=0, le=10)
    self_check_min_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    fields: tuple[FieldSpec, ...] = _aegis_graph_skeleton_fields()
    tool_requirements: tuple[ToolRefRequirement, ...] = (
        ToolRefRequirement(
            tool_ref="knowledge.search",
            description="Retrieve candidate chunks from selected document scopes.",
        ),
    )

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="AegisGraphSkeletonState",
            entry_node="route_request",
            nodes=(
                GraphNodeDefinition(
                    node_id="route_request",
                    title="Route request",
                    shape=GraphNodeShape.DIAMOND,
                ),
                GraphNodeDefinition(
                    node_id="retrieve_context",
                    title="Retrieve context",
                ),
                GraphNodeDefinition(
                    node_id="grade_context",
                    title="Grade context",
                ),
                GraphNodeDefinition(
                    node_id="generate_draft",
                    title="Generate draft",
                ),
                GraphNodeDefinition(
                    node_id="self_check",
                    title="Self-check",
                    shape=GraphNodeShape.DIAMOND,
                ),
                GraphNodeDefinition(
                    node_id="corrective_plan",
                    title="Corrective plan",
                    shape=GraphNodeShape.DIAMOND,
                ),
                GraphNodeDefinition(
                    node_id="corrective_retrieve",
                    title="Corrective retrieve",
                ),
                GraphNodeDefinition(
                    node_id="finalize",
                    title="Finalize",
                    shape=GraphNodeShape.ROUND,
                ),
            ),
            edges=(
                GraphEdgeDefinition(source="retrieve_context", target="grade_context"),
                GraphEdgeDefinition(source="grade_context", target="generate_draft"),
                GraphEdgeDefinition(source="generate_draft", target="self_check"),
                GraphEdgeDefinition(
                    source="corrective_retrieve",
                    target="grade_context",
                    label="retry with new evidence",
                ),
            ),
            conditionals=(
                GraphConditionalDefinition(
                    source="route_request",
                    routes=(
                        GraphRouteDefinition(
                            route_key="analyze",
                            target="retrieve_context",
                            label="analyze",
                        ),
                        GraphRouteDefinition(
                            route_key="unsupported",
                            target="finalize",
                            label="unsupported",
                        ),
                    ),
                ),
                GraphConditionalDefinition(
                    source="self_check",
                    routes=(
                        GraphRouteDefinition(
                            route_key="finalize",
                            target="finalize",
                            label="quality ok",
                        ),
                        GraphRouteDefinition(
                            route_key="corrective",
                            target="corrective_plan",
                            label="needs corrective loop",
                        ),
                    ),
                ),
                GraphConditionalDefinition(
                    source="corrective_plan",
                    routes=(
                        GraphRouteDefinition(
                            route_key="retrieve_more",
                            target="corrective_retrieve",
                            label="retrieve more",
                        ),
                        GraphRouteDefinition(
                            route_key="stop",
                            target="finalize",
                            label="stop",
                        ),
                    ),
                ),
            ),
        )

    def input_model(self) -> type[BaseModel]:
        return AegisGraphSkeletonInput

    def state_model(self) -> type[BaseModel]:
        return AegisGraphSkeletonState

    def output_model(self) -> type[BaseModel]:
        return GraphExecutionOutput

    def build_initial_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
    ) -> BaseModel:
        del binding
        model = AegisGraphSkeletonInput.model_validate(input_model)
        return AegisGraphSkeletonState(latest_user_text=model.message.strip())

    def node_handlers(self) -> dict[str, object]:
        return {
            "route_request": self.route_request,
            "retrieve_context": self.retrieve_context,
            "grade_context": self.grade_context,
            "generate_draft": self.generate_draft,
            "self_check": self.self_check,
            "corrective_plan": self.corrective_plan,
            "corrective_retrieve": self.corrective_retrieve,
            "finalize": self.finalize,
        }

    def build_output(self, state: BaseModel) -> BaseModel:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        text = graph_state.final_text or graph_state.draft_answer
        return GraphExecutionOutput(content=text)

    async def route_request(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        user_text = graph_state.latest_user_text.strip()
        if len(user_text) < 3:
            context.emit_status("routing", "Request too short; finalize directly.")
            return GraphNodeResult(
                state_update={
                    "final_text": (
                        "Please provide a fuller question so Aegis can run "
                        "retrieval and grounded analysis."
                    ),
                    "done_reason": "unsupported_request",
                },
                route_key="unsupported",
            )
        context.emit_status("routing", "Routing request to Aegis analysis flow.")
        return GraphNodeResult(
            state_update={
                "retrieval_query": user_text,
                "final_text": None,
            },
            route_key="analyze",
        )

    async def retrieve_context(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        query = graph_state.retrieval_query or graph_state.latest_user_text
        context.emit_status("context_retrieval", "Searching document corpus.")
        try:
            result = await context.invoke_tool(
                "knowledge.search",
                {"query": query, "top_k": self.retrieval_top_k},
            )
        except Exception:
            context.emit_status(
                "context_retrieval",
                "Retrieval failed; continue with empty context.",
            )
            return GraphNodeResult(
                state_update={"retrieved_context": "", "retrieved_chunk_count": 0}
            )

        rendered = self._render_sources(result.sources)
        return GraphNodeResult(
            state_update={
                "retrieved_context": rendered,
                "retrieved_chunk_count": len(result.sources),
            }
        )

    async def grade_context(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        # Skeleton behavior: keep retrieval deterministic, avoid extra parsing
        # complexity here. Teams can replace this node with structured grading.
        context.emit_status(
            "analysis",
            (
                f"Context prepared with {graph_state.retrieved_chunk_count} chunks "
                "for draft generation."
            ),
        )
        return GraphNodeResult()

    async def generate_draft(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        prompt = self.generate_draft_prompt_template.format(
            question=graph_state.latest_user_text,
            retrieved_context=(
                graph_state.retrieved_context or "(no retrieved context available)"
            ),
        )
        context.emit_status("analysis", "Generating grounded draft answer.")
        if context.model is None:
            fallback = (
                "Draft (fallback): I could not access a model. "
                f"Retrieved chunks: {graph_state.retrieved_chunk_count}."
            )
            return GraphNodeResult(state_update={"draft_answer": fallback})
        try:
            response = await context.invoke_model(
                [HumanMessage(content=prompt)],
                operation="generate_draft",
            )
        except Exception:
            fallback = "Draft (fallback): model call failed during generate_draft."
            return GraphNodeResult(state_update={"draft_answer": fallback})

        return GraphNodeResult(
            state_update={
                "draft_answer": self._message_to_text(getattr(response, "content", "")),
            }
        )

    async def self_check(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        context.emit_status("analysis", "Running self-check quality gate.")

        if context.model is None:
            grounded = graph_state.retrieved_chunk_count > 0
            confidence = 0.6 if grounded else 0.2
            notes = "Heuristic self-check used because model is unavailable."
            route_key = (
                "finalize"
                if grounded and confidence >= self.self_check_min_confidence
                else "corrective"
            )
            return GraphNodeResult(
                state_update={
                    "self_check_grounded": grounded,
                    "self_check_confidence": confidence,
                    "self_check_notes": notes,
                    "followup_queries": []
                    if grounded
                    else [graph_state.latest_user_text],
                },
                route_key=route_key,
            )

        prompt = self.self_check_prompt_template.format(
            question=graph_state.latest_user_text,
            draft_answer=graph_state.draft_answer or "(empty draft)",
            retrieved_context=graph_state.retrieved_context or "(no context)",
        )
        try:
            response = await context.invoke_model(
                [HumanMessage(content=prompt)],
                operation="self_check",
            )
            payload = self._parse_json_object(
                self._message_to_text(getattr(response, "content", ""))
            )
        except Exception:
            payload = {}

        grounded = bool(payload.get("grounded", False))
        confidence = self._coerce_confidence(payload.get("confidence"))
        notes = str(payload.get("notes") or "").strip()
        followup_queries = self._coerce_queries(payload.get("followup_queries"))
        if not followup_queries and not grounded:
            followup_queries = [graph_state.latest_user_text]

        route_key = (
            "finalize"
            if grounded and confidence >= self.self_check_min_confidence
            else "corrective"
        )
        return GraphNodeResult(
            state_update={
                "self_check_grounded": grounded,
                "self_check_confidence": confidence,
                "self_check_notes": notes,
                "followup_queries": followup_queries,
            },
            route_key=route_key,
        )

    async def corrective_plan(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        if graph_state.iteration >= self.max_iterations:
            context.emit_status(
                "fallback",
                "Corrective iteration budget exhausted; finalizing best effort.",
            )
            return GraphNodeResult(
                state_update={"done_reason": "max_iterations_reached"},
                route_key="stop",
            )
        context.emit_status(
            "clarification",
            (
                f"Preparing corrective retrieval loop "
                f"({graph_state.iteration + 1}/{self.max_iterations})."
            ),
        )
        return GraphNodeResult(route_key="retrieve_more")

    async def corrective_retrieve(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        followups = graph_state.followup_queries
        query = followups[0] if followups else graph_state.latest_user_text

        # Optional model-assisted follow-up query synthesis.
        if context.model is not None and graph_state.self_check_notes.strip():
            prompt = self.corrective_query_prompt_template.format(
                question=graph_state.latest_user_text,
                draft_answer=graph_state.draft_answer or "(empty)",
                self_check_notes=graph_state.self_check_notes,
            )
            try:
                response = await context.invoke_model(
                    [HumanMessage(content=prompt)],
                    operation="corrective_queries",
                )
                payload = self._parse_json_object(
                    self._message_to_text(getattr(response, "content", ""))
                )
                generated = self._coerce_queries(payload.get("queries"))
                if generated:
                    query = generated[0]
            except Exception:
                # Keep retrieval flow resilient: fall back to the previous query.
                logger.debug(
                    "[AegisGraphV2Skeleton] corrective query synthesis failed; using fallback query.",
                    exc_info=True,
                )

        context.emit_status("context_retrieval", "Running corrective retrieval query.")
        try:
            result = await context.invoke_tool(
                "knowledge.search",
                {"query": query, "top_k": max(3, self.retrieval_top_k // 2)},
            )
        except Exception:
            return GraphNodeResult(
                state_update={"iteration": graph_state.iteration + 1}
            )

        merged_context = "\n\n".join(
            part
            for part in (
                graph_state.retrieved_context,
                self._render_sources(result.sources),
            )
            if part
        )
        return GraphNodeResult(
            state_update={
                "retrieval_query": query,
                "retrieved_context": merged_context,
                "retrieved_chunk_count": (
                    graph_state.retrieved_chunk_count + len(result.sources)
                ),
                "iteration": graph_state.iteration + 1,
            }
        )

    async def finalize(
        self, state: BaseModel, context: GraphNodeContext
    ) -> GraphNodeResult:
        graph_state = AegisGraphSkeletonState.model_validate(state)
        del context
        summary = (
            graph_state.final_text or graph_state.draft_answer or "No answer generated."
        )
        quality_line = (
            f"\n\nSelf-check: grounded={graph_state.self_check_grounded}, "
            f"confidence={graph_state.self_check_confidence:.2f}, "
            f"iterations={graph_state.iteration}."
        )
        if graph_state.done_reason:
            quality_line += f"\nReason: {graph_state.done_reason}."
        return GraphNodeResult(
            state_update={
                "final_text": summary + quality_line,
            }
        )

    @staticmethod
    def _render_sources(sources: tuple[Any, ...]) -> str:
        lines: list[str] = []
        for index, hit in enumerate(sources[:12], start=1):
            title = str(
                getattr(hit, "title", None)
                or getattr(hit, "file_name", None)
                or getattr(hit, "uid", f"chunk-{index}")
            )
            content = str(getattr(hit, "content", "")).strip()
            if len(content) > 500:
                content = content[:500].rstrip() + " ..."
            lines.append(f"[{index}] {title}\n{content}")
        return "\n\n".join(lines)

    @staticmethod
    def _message_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(part.strip() for part in parts if part.strip())
        return str(content).strip()

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, object]:
        if not text:
            return {}
        stripped = text.strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _coerce_confidence(value: object) -> float:
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, int | float):
            return max(0.0, min(1.0, float(value)))
        if isinstance(value, str):
            try:
                return max(0.0, min(1.0, float(value.strip())))
            except ValueError:
                return 0.0
        return 0.0

    @staticmethod
    def _coerce_queries(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            query = item.strip()
            if not query:
                continue
            cleaned.append(query)
        return cleaned[:3]
