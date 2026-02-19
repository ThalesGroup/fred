# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import Any, List, Optional, Sequence, cast

from fred_core import VectorSearchHit
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph

from agentic_backend.agents.rags.structures import GradeDocumentsOutput
from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient
from agentic_backend.common.rags_utils import (
    attach_sources_to_llm_response,
    ensure_ranks,
    format_sources_for_prompt,
    sort_hits,
)
from agentic_backend.common.structures import AgentChatOptions, AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,
    get_document_library_tags_ids,
    get_document_uids,
    get_language,
    get_rag_knowledge_scope,
    get_search_policy,
    get_vector_search_scopes,
    is_corpus_only_mode,
)
from agentic_backend.core.runtime_source import expose_runtime_source

from .prompts import (
    gap_query_prompt,
    generate_answer_prompt,
    grade_documents_prompt,
    self_check_prompt,
    system_prompt,
)
from .structures import AegisGraphState, GapQueriesOutput, SelfCheckOutput

logger = logging.getLogger(__name__)


def mk_thought(*, label: str, node: str, task: str, content: str) -> AIMessage:
    """
    Emits a compact assistant-side "thought" for UI traces without revealing chain-of-thought.
    """
    return AIMessage(
        content="",
        response_metadata={
            "thought": content,
            "extras": {"task": task, "node": node, "label": label},
        },
    )


def _chunk_key(d: VectorSearchHit) -> str:
    """
    Stable key for chunk deduplication across corrective loops.
    """
    uid = getattr(d, "document_uid", None) or getattr(d, "uid", "") or ""
    page = getattr(d, "page", "")
    start = getattr(d, "char_start", "")
    end = getattr(d, "char_end", "")
    heading = getattr(d, "heading_slug", "") or getattr(d, "heading", "") or ""
    return f"{uid}|p={page}|cs={start}|ce={end}|h={heading}"


@expose_runtime_source("agent.Aegis")
class Aegis(AgentFlow):
    """
    Self-correcting RAG advisor (Self-RAG + Corrective-RAG).

    Aegis runs retrieval with reranking and optional grading, generates a draft,
    self-critiques grounding/citation coverage, and triggers corrective retrieval
    loops until quality gates pass or the iteration budget is exhausted.
    """

    tuning = AgentTuning(
        role="Self-correcting RAG advisor",
        description=(
            "Answers questions using retrieved document snippets with evidence-based citations. "
            "It self-critiques grounding and runs corrective retrieval loops when evidence is weak."
        ),
        tags=["document"],
        fields=[
            FieldSpec(
                key="prompts.system",
                type="prompt",
                title="System Prompt",
                description="Core instructions for evidence-based answers and citation style.",
                required=True,
                default=system_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.generate_answer",
                type="prompt",
                title="Generate Answer Prompt",
                description="Prompt used to produce the final structured response.",
                required=True,
                default=generate_answer_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.self_check",
                type="prompt",
                title="Self-Check Prompt",
                description="Prompt used by the self-critic to assess grounding and citations.",
                required=True,
                default=self_check_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.gap_queries",
                type="prompt",
                title="Gap Query Prompt",
                description="Prompt used to generate corrective follow-up queries.",
                required=True,
                default=gap_query_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="prompts.grade_documents",
                type="prompt",
                title="Grade Documents Prompt",
                description="Permissive prompt to keep only relevant documents.",
                required=True,
                default=grade_documents_prompt(),
                ui=UIHints(group="Prompts", multiline=True, markdown=True),
            ),
            FieldSpec(
                key="rag.top_k",
                type="integer",
                title="Top-K Documents",
                description="How many chunks to retrieve per question.",
                required=False,
                default=35,
                ui=UIHints(group="Retrieval"),
            ),
            FieldSpec(
                key="rag.top_r",
                type="integer",
                title="Top-R Rerank",
                description="How many reranked chunks to keep.",
                required=False,
                default=8,
                ui=UIHints(group="Reranking"),
            ),
            FieldSpec(
                key="rag.min_score",
                type="number",
                title="Minimum Score (semantic filter)",
                description="Filter semantic hits below this score (0 disables).",
                required=False,
                default=0.0,
                ui=UIHints(group="Retrieval"),
            ),
            FieldSpec(
                key="rag.max_iterations",
                type="integer",
                title="Corrective Iterations",
                description="Maximum corrective retrieval loops.",
                required=False,
                default=2,
                ui=UIHints(group="Retrieval"),
            ),
            FieldSpec(
                key="quality.min_docs",
                type="integer",
                title="Minimum Documents",
                description="Minimum documents required before finalizing an answer.",
                required=False,
                default=3,
                ui=UIHints(group="Quality"),
            ),
            FieldSpec(
                key="output.include_sources_section",
                type="boolean",
                title="Include Sources Section",
                description="Whether to include the Sources section in the final answer.",
                required=False,
                default=True,
                ui=UIHints(group="Output"),
            ),
            FieldSpec(
                key="output.include_inferred_recos",
                type="boolean",
                title="Include Inferred Recommendations",
                description=(
                    "Whether to include inferred recommendations (auto-disabled in corpus-only mode)."
                ),
                required=False,
                default=True,
                ui=UIHints(group="Output"),
            ),
        ],
    )

    default_chat_options = AgentChatOptions(
        search_policy_selection=True,
        libraries_selection=True,
        search_rag_scoping=True,
        attach_files=True,
        documents_selection=True,
    )

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings=agent_settings)

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        self.search_client = VectorSearchClient(agent=self)
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(AegisGraphState)

        builder.add_node("retrieve", self._retrieve)
        builder.add_node("rerank", self._rerank)
        builder.add_node("grade_documents", self._grade_documents)
        builder.add_node("generate_draft", self._generate_draft)
        builder.add_node("self_check", self._self_check)
        builder.add_node("corrective_plan", self._corrective_plan)
        builder.add_node("corrective_retrieve", self._corrective_retrieve)
        builder.add_node("no_results", self._no_results)
        builder.add_node("finalize_success", self._finalize_success)
        builder.add_node("finalize_best_effort", self._finalize_best_effort)

        builder.set_entry_point("retrieve")
        builder.add_conditional_edges(
            "retrieve",
            self._route_after_retrieve,
            {
                "rerank": "rerank",
                "no_results": "no_results",
            },
        )
        builder.add_edge("rerank", "grade_documents")
        builder.add_edge("grade_documents", "generate_draft")
        builder.add_edge("generate_draft", "self_check")
        builder.add_conditional_edges(
            "self_check",
            self._route_after_self_check,
            {
                "finalize_success": "finalize_success",
                "corrective_plan": "corrective_plan",
                "finalize_best_effort": "finalize_best_effort",
            },
        )
        builder.add_edge("corrective_plan", "corrective_retrieve")
        builder.add_edge("corrective_retrieve", "generate_draft")
        builder.add_edge("no_results", "finalize_best_effort")
        builder.add_edge("finalize_success", END)
        builder.add_edge("finalize_best_effort", END)

        return builder

    # -----------------------------
    # Helpers
    # -----------------------------
    def _render_tuned_prompt(self, key: str, **tokens) -> str:
        prompt = self.get_tuned_text(key)
        if not prompt:
            logger.warning("Aegis: no tuned prompt found for %s", key)
            raise RuntimeError(f"Aegis: no tuned prompt found for '{key}'.")
        return self.render(prompt, **tokens)

    def _system_prompt(self) -> str:
        response_language = get_language(self.get_runtime_context()) or "English"
        return self._render_tuned_prompt(
            "prompts.system", response_language=response_language
        )

    def _extract_question_from_messages(self, messages: Sequence[Any]) -> Optional[str]:
        if not messages:
            return None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = getattr(msg, "content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        for msg in reversed(messages):
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content.strip():
                return content.strip()
        return None

    def _merge_hits(self, hits: Sequence[VectorSearchHit]) -> List[VectorSearchHit]:
        seen = set()
        merged: List[VectorSearchHit] = []
        for h in hits:
            key = _chunk_key(h)
            if key in seen:
                continue
            seen.add(key)
            merged.append(h)
        return merged

    def _followup_top_k(self, base_top_k: int) -> int:
        return max(8, min(12, max(1, base_top_k // 4)))

    def _passes_self_check(self, check: SelfCheckOutput, *, min_docs_ok: bool) -> bool:
        grounded = str(check.grounded).lower() == "yes"
        answers = str(check.answers_question).lower() == "yes"
        coverage = str(check.citation_coverage).lower() != "weak"
        unsupported = bool(check.unsupported_claims)
        return grounded and answers and coverage and min_docs_ok and not unsupported

    # -----------------------------
    # Nodes
    # -----------------------------
    async def _retrieve(self, state: AegisGraphState) -> AegisGraphState:
        question = state.get("question")
        if not question:
            question = self._extract_question_from_messages(state.get("messages") or [])
        if not question:
            raise RuntimeError("Aegis: missing question for retrieval.")

        runtime_context = self.get_runtime_context()
        rag_scope = get_rag_knowledge_scope(runtime_context)
        state["question"] = question
        state["iteration"] = int(state.get("iteration", 0) or 0)

        if rag_scope == "general_only":
            # Respect the user-selected scope: no retrieval.
            state["documents"] = []
            state["sources"] = []
            state["decision"] = "no_results"
            state["messages"] = [
                mk_thought(
                    label="general_only",
                    node="retrieve",
                    task="retrieval",
                    content="General-only scope selected; skipping retrieval.",
                )
            ]
            return state

        if not runtime_context or not runtime_context.session_id:
            raise RuntimeError(
                "Runtime context missing session_id; required for scoped retrieval."
            )

        doc_tag_ids = get_document_library_tags_ids(runtime_context)
        document_uids = get_document_uids(runtime_context)
        search_policy = get_search_policy(runtime_context)
        include_session_scope, include_corpus_scope = get_vector_search_scopes(
            runtime_context
        )
        top_k = self.get_tuned_int("rag.top_k", default=35)

        with self.kpi_timer(
            "agent.step_latency_ms",
            dims={"step": "vector_search", "policy": search_policy},
        ):
            hits = await self.search_client.search(
                question=question,
                top_k=top_k,
                document_library_tags_ids=doc_tag_ids,
                document_uids=document_uids,
                search_policy=search_policy,
                session_id=runtime_context.session_id,
                include_session_scope=include_session_scope,
                include_corpus_scope=include_corpus_scope,
            )

        hits = sort_hits(hits)
        ensure_ranks(hits)

        min_score = self.get_tuned_number("rag.min_score", default=0.0)
        if search_policy == "semantic" and min_score and min_score > 0:
            hits = [
                h
                for h in hits
                if isinstance(h.score, (int, float)) and h.score >= min_score
            ]

        if not hits:
            state["documents"] = []
            state["sources"] = []
            state["decision"] = "no_results"
            state["messages"] = [
                mk_thought(
                    label="retrieve_none",
                    node="retrieve",
                    task="retrieval",
                    content="No relevant documents found.",
                )
            ]
            return state

        state["documents"] = hits
        state["sources"] = hits
        state["decision"] = "rerank"
        state["messages"] = [
            mk_thought(
                label="retrieve",
                node="retrieve",
                task="retrieval",
                content=f"Retrieved {len(hits)} candidate chunks.",
            )
        ]
        return state

    async def _rerank(self, state: AegisGraphState) -> AegisGraphState:
        question = cast(str, state.get("question"))
        documents = cast(List[VectorSearchHit], state.get("documents") or [])
        if not documents:
            state["messages"] = [
                mk_thought(
                    label="rerank_skip",
                    node="rerank",
                    task="reranking",
                    content="No documents to rerank.",
                )
            ]
            return state

        top_r = self.get_tuned_int("rag.top_r", default=8)
        with self.kpi_timer("agent.step_latency_ms", dims={"step": "rerank"}):
            reranked = await self.search_client.rerank(
                question=question, documents=documents, top_r=top_r
            )

        merged = self._merge_hits(list(reranked) + list(documents))
        ensure_ranks(merged)

        state["documents"] = merged
        state["sources"] = merged
        state["messages"] = [
            mk_thought(
                label="rerank",
                node="rerank",
                task="reranking",
                content=f"Reranked and kept {len(merged)} chunks.",
            )
        ]
        return state

    async def _grade_documents(self, state: AegisGraphState) -> AegisGraphState:
        question = cast(str, state.get("question"))
        documents = cast(List[VectorSearchHit], state.get("documents") or [])
        if not documents:
            state["messages"] = [
                mk_thought(
                    label="grade_skip",
                    node="grade_documents",
                    task="retrieval",
                    content="No documents to grade.",
                )
            ]
            return state

        template = (
            self.get_tuned_text("prompts.grade_documents") or grade_documents_prompt()
        )
        grade_prompt = ChatPromptTemplate.from_template(template)
        chain = grade_prompt | self.model.with_structured_output(GradeDocumentsOutput)

        irrelevant_documents = cast(
            List[VectorSearchHit], state.get("irrelevant_documents", [])
        )
        irrelevant_keys = {_chunk_key(doc) for doc in irrelevant_documents}
        to_grade = [d for d in documents if _chunk_key(d) not in irrelevant_keys]

        filtered: List[VectorSearchHit] = []
        with self.kpi_timer("agent.step_latency_ms", dims={"step": "grade_documents"}):
            for doc in to_grade:
                doc_context = (
                    f"Title: {doc.title or doc.file_name}\n"
                    f"Page: {getattr(doc, 'page', 'n/a')}\n"
                    f"Content:\n{doc.content}"
                )
                llm_response = await chain.ainvoke(
                    {"question": question, "document": doc_context}
                )
                score = cast(GradeDocumentsOutput, llm_response)
                if str(score.binary_score).lower() == "yes":
                    filtered.append(doc)
                else:
                    irrelevant_documents.append(doc)

        min_docs = self.get_tuned_int("quality.min_docs", default=3)
        if not filtered and documents:
            kept = documents[:min_docs]
        elif 0 < len(filtered) < min_docs:
            kept = filtered.copy()
            seen = {_chunk_key(doc) for doc in kept}
            for doc in documents:
                if len(kept) >= min_docs:
                    break
                key = _chunk_key(doc)
                if key not in seen:
                    kept.append(doc)
                    seen.add(key)
        else:
            kept = filtered

        kept = self._merge_hits(kept)
        kept = sort_hits(kept)
        ensure_ranks(kept)

        state["documents"] = kept
        state["sources"] = kept
        state["irrelevant_documents"] = irrelevant_documents
        state["messages"] = [
            mk_thought(
                label="grade_documents",
                node="grade_documents",
                task="retrieval",
                content=f"Kept {len(kept)} of {len(documents)} chunks.",
            )
        ]
        return state

    async def _generate_draft(self, state: AegisGraphState) -> AegisGraphState:
        question = cast(str, state.get("question"))
        documents = cast(List[VectorSearchHit], state.get("documents") or [])
        runtime_context = self.get_runtime_context()
        response_language = get_language(runtime_context) or "English"

        sources_block = (
            format_sources_for_prompt(documents, snippet_chars=500)
            if documents
            else "(no sources)"
        )

        include_sources = bool(self.get_tuned_any("output.include_sources_section"))
        allow_inferred = bool(self.get_tuned_any("output.include_inferred_recos"))
        if is_corpus_only_mode(runtime_context):
            allow_inferred = False

        inferred_recos_policy = (
            "Disabled in corpus-only mode. Output the heading and the single sentence: "
            "Disabled in corpus-only mode."
            if not allow_inferred
            else (
                "Allowed. Each bullet must start with 'Inferred:' and cite the source(s) that "
                "triggered the inference. If the inference is generic best-practice, say so explicitly."
            )
        )
        sources_section_policy = (
            "Include a numbered list matching the [n] citations. If no sources are provided, "
            "write 'No sources available.'"
            if include_sources
            else "Omit the Sources section content."
        )

        template = (
            self.get_tuned_text("prompts.generate_answer") or generate_answer_prompt()
        )
        system_text = self._system_prompt()

        messages = [
            SystemMessage(content=system_text),
            HumanMessage(
                content=self.render(
                    template,
                    question=question,
                    sources=sources_block,
                    response_language=response_language,
                    inferred_recos_policy=inferred_recos_policy,
                    sources_section_policy=sources_section_policy,
                )
            ),
        ]

        chat_context = await self.chat_context_text()
        if chat_context:
            messages.append(HumanMessage(content=chat_context))

        with self.kpi_timer("agent.step_latency_ms", dims={"step": "generate_draft"}):
            response = await self.model.ainvoke(messages)

        response = cast(AIMessage, response)
        state["draft_answer"] = response
        state["sources"] = documents
        state["messages"] = [
            mk_thought(
                label="generate_draft",
                node="generate_draft",
                task="answering",
                content="Drafted an answer from current sources.",
            )
        ]
        return state

    async def _self_check(self, state: AegisGraphState) -> AegisGraphState:
        question = cast(str, state.get("question"))
        draft = cast(AIMessage, state.get("draft_answer"))
        documents = cast(List[VectorSearchHit], state.get("documents") or [])

        sources_block = (
            format_sources_for_prompt(documents, snippet_chars=300)
            if documents
            else "(no sources)"
        )
        answer_text = self._get_text_content(draft)

        template = self.get_tuned_text("prompts.self_check") or self_check_prompt()
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | self.model.with_structured_output(SelfCheckOutput)

        with self.kpi_timer("agent.step_latency_ms", dims={"step": "self_check"}):
            llm_response = await chain.ainvoke(
                {
                    "question": question,
                    "answer": answer_text,
                    "sources": sources_block,
                }
            )
        check = cast(SelfCheckOutput, llm_response)

        summary = (
            f"Self-check: grounded={check.grounded}, answers={check.answers_question}, "
            f"coverage={check.citation_coverage}, confidence={check.confidence}."
        )
        state["self_check"] = check
        state["messages"] = [
            mk_thought(
                label="self_check",
                node="self_check",
                task="quality",
                content=summary,
            )
        ]
        return state

    async def _corrective_plan(self, state: AegisGraphState) -> AegisGraphState:
        iteration = int(state.get("iteration", 0) or 0)
        max_iterations = self.get_tuned_int("rag.max_iterations", default=2)
        check = cast(SelfCheckOutput, state.get("self_check"))

        if iteration >= max_iterations:
            state["decision"] = "finalize_best_effort"
            state["messages"] = [
                mk_thought(
                    label="budget_exhausted",
                    node="corrective_plan",
                    task="quality",
                    content="Corrective budget exhausted; finalizing best-effort answer.",
                )
            ]
            return state

        queries: List[str] = []
        if check and check.suggested_queries:
            queries = [q.strip() for q in check.suggested_queries if q.strip()]

        if not queries:
            template = self.get_tuned_text("prompts.gap_queries") or gap_query_prompt()
            prompt = ChatPromptTemplate.from_template(template)
            chain = prompt | self.model.with_structured_output(GapQueriesOutput)
            missing = ", ".join(check.missing_aspects or []) or "unspecified gaps"
            with self.kpi_timer("agent.step_latency_ms", dims={"step": "gap_queries"}):
                llm_response = await chain.ainvoke(
                    {"question": state.get("question"), "missing_aspects": missing}
                )
            output = cast(GapQueriesOutput, llm_response)
            queries = [q.strip() for q in output.queries if q.strip()]

        if not queries:
            queries = [cast(str, state.get("question"))]

        queries = queries[:3]
        state["followup_queries"] = queries
        state["decision"] = "corrective_retrieve"
        state["messages"] = [
            mk_thought(
                label="corrective_plan",
                node="corrective_plan",
                task="quality",
                content=f"Planned {len(queries)} follow-up queries.",
            )
        ]
        return state

    async def _corrective_retrieve(self, state: AegisGraphState) -> AegisGraphState:
        question = cast(str, state.get("question"))
        runtime_context = self.get_runtime_context()
        if not runtime_context or not runtime_context.session_id:
            raise RuntimeError(
                "Runtime context missing session_id; required for scoped retrieval."
            )

        followups = cast(List[str], state.get("followup_queries") or [])
        if not followups:
            followups = [question]

        doc_tag_ids = get_document_library_tags_ids(runtime_context)
        document_uids = get_document_uids(runtime_context)
        search_policy = get_search_policy(runtime_context)
        include_session_scope, include_corpus_scope = get_vector_search_scopes(
            runtime_context
        )
        top_k = self.get_tuned_int("rag.top_k", default=35)
        per_query_k = self._followup_top_k(top_k)

        merged_hits: List[VectorSearchHit] = list(state.get("documents") or [])

        with self.kpi_timer(
            "agent.step_latency_ms", dims={"step": "corrective_retrieve"}
        ):
            for q in followups:
                hits = await self.search_client.search(
                    question=q,
                    top_k=per_query_k,
                    document_library_tags_ids=doc_tag_ids,
                    document_uids=document_uids,
                    search_policy=search_policy,
                    session_id=runtime_context.session_id,
                    include_session_scope=include_session_scope,
                    include_corpus_scope=include_corpus_scope,
                )
                merged_hits.extend(hits)

        merged_hits = self._merge_hits(merged_hits)
        merged_hits = sort_hits(merged_hits)
        ensure_ranks(merged_hits)

        min_score = self.get_tuned_number("rag.min_score", default=0.0)
        if search_policy == "semantic" and min_score and min_score > 0:
            merged_hits = [
                h
                for h in merged_hits
                if isinstance(h.score, (int, float)) and h.score >= min_score
            ]

        state["documents"] = merged_hits
        state["sources"] = merged_hits
        state["iteration"] = int(state.get("iteration", 0) or 0) + 1
        state["messages"] = [
            mk_thought(
                label="corrective_retrieve",
                node="corrective_retrieve",
                task="retrieval",
                content=f"Corrective retrieval merged to {len(merged_hits)} chunks.",
            )
        ]
        return state

    async def _no_results(self, state: AegisGraphState) -> AegisGraphState:
        question = cast(str, state.get("question"))
        runtime_context = self.get_runtime_context()
        response_language = get_language(runtime_context) or "English"

        template = (
            self.get_tuned_text("prompts.generate_answer") or generate_answer_prompt()
        )
        system_text = self._system_prompt()
        inferred_policy = (
            "Disabled in corpus-only mode. Output the heading and the single sentence: "
            "Disabled in corpus-only mode."
        )
        include_sources = bool(self.get_tuned_any("output.include_sources_section"))
        sources_section_policy = (
            "Include a numbered list matching the [n] citations. If no sources are provided, "
            "write 'No sources available.'"
            if include_sources
            else "Omit the Sources section content."
        )

        messages = [
            SystemMessage(content=system_text),
            HumanMessage(
                content=self.render(
                    template,
                    question=question,
                    sources="(no sources)",
                    response_language=response_language,
                    inferred_recos_policy=inferred_policy,
                    sources_section_policy=sources_section_policy,
                )
            ),
        ]

        with self.kpi_timer("agent.step_latency_ms", dims={"step": "no_results"}):
            response = await self.model.ainvoke(messages)

        state["draft_answer"] = cast(AIMessage, response)
        state["sources"] = []
        state["messages"] = [
            mk_thought(
                label="no_results",
                node="no_results",
                task="answering",
                content="No sources available; generated best-effort response.",
            )
        ]
        return state

    async def _finalize_success(self, state: AegisGraphState) -> AegisGraphState:
        answer = cast(AIMessage, state.get("draft_answer"))
        hits = cast(List[VectorSearchHit], state.get("sources") or [])
        attach_sources_to_llm_response(answer, hits)

        state["messages"] = [answer]
        state["question"] = ""
        state["sources"] = []
        state["documents"] = []
        state["iteration"] = 0
        state["draft_answer"] = None
        state["self_check"] = None
        state["followup_queries"] = []
        state["decision"] = None
        return state

    async def _finalize_best_effort(self, state: AegisGraphState) -> AegisGraphState:
        answer = cast(AIMessage, state.get("draft_answer"))
        hits = cast(List[VectorSearchHit], state.get("sources") or [])
        attach_sources_to_llm_response(answer, hits)

        state["messages"] = [answer]
        state["question"] = ""
        state["sources"] = []
        state["documents"] = []
        state["iteration"] = 0
        state["draft_answer"] = None
        state["self_check"] = None
        state["followup_queries"] = []
        state["decision"] = None
        return state

    # -----------------------------
    # Routing
    # -----------------------------
    async def _route_after_retrieve(self, state: AegisGraphState) -> str:
        decision = state.get("decision")
        if decision == "no_results":
            return "no_results"
        return "rerank"

    async def _route_after_self_check(self, state: AegisGraphState) -> str:
        check = cast(SelfCheckOutput, state.get("self_check"))
        documents = cast(List[VectorSearchHit], state.get("documents") or [])
        min_docs = self.get_tuned_int("quality.min_docs", default=3)
        min_docs_ok = len(documents) >= min_docs

        if check and self._passes_self_check(check, min_docs_ok=min_docs_ok):
            return "finalize_success"

        iteration = int(state.get("iteration", 0) or 0)
        max_iterations = self.get_tuned_int("rag.max_iterations", default=2)
        if iteration >= max_iterations:
            return "finalize_best_effort"
        return "corrective_plan"
