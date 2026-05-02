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

import asyncio
import logging
from typing import Any, List, Optional, Sequence, cast

from fred_core.store import VectorSearchHit
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from agentic_backend.agents.v1.production.rags.structures import GradeDocumentsOutput
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
                key="chat_options.attach_files",
                type="boolean",
                title="Allow file attachments",
                description="Show file upload/attachment controls for this agent.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.libraries_selection",
                type="boolean",
                title="Document libraries picker",
                description="Let users select document libraries/knowledge sources for this agent.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.search_policy_selection",
                type="boolean",
                title="Search policy selector",
                description="Expose the search policy toggle (hybrid/semantic/strict).",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.search_rag_scoping",
                type="boolean",
                title="RAG scope selector",
                description="Expose the RAG scope control (documents-only vs hybrid vs general knowledge).",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
            ),
            FieldSpec(
                key="chat_options.documents_selection",
                type="boolean",
                title="Specific documents picker",
                description="Let users restrict retrieval to explicitly selected documents.",
                required=False,
                default=True,
                ui=UIHints(group="Chat options"),
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
        """
        Why this exists:
            Initialize the Aegis runtime with retrieval services and a local internal model copy.

        How to use:
            The agent runtime calls this once before graph execution so Aegis can
            reuse the shared chat model for output quality while disabling token
            streaming on its internal LLM-only steps.
        """
        await super().async_init(runtime_context)
        self.model = get_default_chat_model()
        self.internal_model = self._make_internal_model(self.model)
        self.search_client = VectorSearchClient(agent=self)
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """
        Why this exists:
            Assemble the Aegis LangGraph flow using the v1 runtime contract.

        How to use:
            Call during agent initialization, then compile/stream the graph through
            the standard agent runtime entrypoint.
        """
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

        builder.add_edge(START, "retrieve")
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
    def _make_internal_model(self, model: Any) -> Any:
        """
        Why this exists:
            Create an Aegis-local model copy that suppresses token streaming for internal LLM calls.

        How to use:
            Pass the shared default chat model and use the returned copy for
            grading, self-check, draft generation, and fallback answer steps.
        """
        try:
            if hasattr(model, "model_copy"):
                return model.model_copy(update={"disable_streaming": True})
        except Exception:
            logger.debug(
                "Aegis: model_copy(disable_streaming=True) failed", exc_info=True
            )

        try:
            if hasattr(model, "copy"):
                return model.copy(update={"disable_streaming": True})
        except Exception:
            logger.debug("Aegis: copy(disable_streaming=True) failed", exc_info=True)

        try:
            if hasattr(model, "bind"):
                return model.bind(stream=False)
        except Exception:
            logger.debug("Aegis: bind(stream=False) failed", exc_info=True)

        logger.warning(
            "Aegis: could not create internal non-streaming model; using default model"
        )
        return model

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

    def _build_final_answer_message(
        self, state: AegisGraphState, hits: List[VectorSearchHit]
    ) -> AIMessage:
        """
        Why this exists:
            Build a clean final assistant message from the internal draft state.

        How to use:
            Call from finalization nodes to re-wrap the internal draft as the
            runtime-visible final answer and attach sources safely.
        """
        answer = cast(AIMessage | None, state.get("draft_answer"))
        text = self._get_text_content(answer).strip() if answer is not None else ""
        if not text:
            text = (
                "Aegis could not produce a final answer from the current evidence. "
                "Please retry or refine the question."
            )
        metadata: dict[str, Any] = {"extras": {"agent": "Aegis", "final": True}}
        if answer is not None:
            old_metadata = getattr(answer, "response_metadata", {}) or {}
            for key in ("token_usage", "model_name", "finish_reason"):
                if key in old_metadata:
                    metadata[key] = old_metadata[key]
            old_extras = old_metadata.get("extras")
            if isinstance(old_extras, dict):
                metadata["extras"] = {**old_extras, "agent": "Aegis", "final": True}
        final = AIMessage(content=text, response_metadata=metadata)
        attach_sources_to_llm_response(final, hits)
        return final

    async def _ainvoke_internal_model(self, messages: List[Any]) -> AIMessage:
        """
        Why this exists:
            Execute internal Aegis model calls without exposing token chunks to the shared runtime stream.

        How to use:
            Pass the prepared message list for internal business steps such as
            draft generation or no-results fallback generation.
        """
        response = await asyncio.to_thread(self.internal_model.invoke, messages)
        return cast(AIMessage, response)

    async def _ainvoke_internal_chain(self, chain: Any, payload: dict[str, Any]) -> Any:
        """
        Why this exists:
            Execute structured internal chains through a non-streaming code path.

        How to use:
            Pass a LangChain runnable plus its input payload for grading,
            self-check, and corrective query generation steps.
        """
        return await asyncio.to_thread(chain.invoke, payload)

    # -----------------------------
    # Nodes
    # -----------------------------
    async def _retrieve(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Retrieve the initial corpus evidence for the current question.

        How to use:
            LangGraph calls this node with the current state and expects only the
            updated retrieval fields plus any emitted trace messages.
        """
        question = state.get("question")
        if not question:
            question = self._extract_question_from_messages(state.get("messages") or [])
        if not question:
            raise RuntimeError("Aegis: missing question for retrieval.")

        runtime_context = self.get_runtime_context()
        rag_scope = get_rag_knowledge_scope(runtime_context)
        iteration = int(state.get("iteration", 0) or 0)

        if rag_scope == "general_only":
            # Respect the user-selected scope: no retrieval.
            return {
                "question": question,
                "iteration": iteration,
                "documents": [],
                "sources": [],
                "decision": "no_results",
                "messages": [
                    mk_thought(
                        label="general_only",
                        node="retrieve",
                        task="retrieval",
                        content="General-only scope selected; skipping retrieval.",
                    )
                ],
            }

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
            return {
                "question": question,
                "iteration": iteration,
                "documents": [],
                "sources": [],
                "decision": "no_results",
                "messages": [
                    mk_thought(
                        label="retrieve_none",
                        node="retrieve",
                        task="retrieval",
                        content="No relevant documents found.",
                    )
                ],
            }

        return {
            "question": question,
            "iteration": iteration,
            "documents": hits,
            "sources": hits,
            "decision": "rerank",
            "messages": [
                mk_thought(
                    label="retrieve",
                    node="retrieve",
                    task="retrieval",
                    content=f"Retrieved {len(hits)} candidate chunks.",
                )
            ],
        }

    async def _rerank(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Improve ordering and coverage of retrieved chunks before grading.

        How to use:
            Provide `question` and `documents` in state; this node returns only the
            reranked document-related fields and a trace message.
        """
        question = cast(str, state.get("question"))
        documents = cast(List[VectorSearchHit], state.get("documents") or [])
        if not documents:
            return {
                "messages": [
                    mk_thought(
                        label="rerank_skip",
                        node="rerank",
                        task="reranking",
                        content="No documents to rerank.",
                    )
                ]
            }

        top_r = self.get_tuned_int("rag.top_r", default=8)
        with self.kpi_timer("agent.step_latency_ms", dims={"step": "rerank"}):
            reranked = await self.search_client.rerank(
                question=question, documents=documents, top_r=top_r
            )

        merged = self._merge_hits(list(reranked) + list(documents))
        ensure_ranks(merged)

        return {
            "documents": merged,
            "sources": merged,
            "messages": [
                mk_thought(
                    label="rerank",
                    node="rerank",
                    task="reranking",
                    content=f"Reranked and kept {len(merged)} chunks.",
                )
            ],
        }

    async def _grade_documents(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Filter obviously irrelevant chunks while preserving enough evidence.

        How to use:
            Provide retrieved `documents`; this returns the kept set, the tracked
            irrelevant set, and a trace message without mutating input state.
        """
        question = cast(str, state.get("question"))
        documents = cast(List[VectorSearchHit], state.get("documents") or [])
        if not documents:
            return {
                "messages": [
                    mk_thought(
                        label="grade_skip",
                        node="grade_documents",
                        task="retrieval",
                        content="No documents to grade.",
                    )
                ]
            }

        template = (
            self.get_tuned_text("prompts.grade_documents") or grade_documents_prompt()
        )
        grade_prompt = ChatPromptTemplate.from_template(template)
        chain = grade_prompt | self.internal_model.with_structured_output(
            GradeDocumentsOutput
        )

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
                llm_response = await self._ainvoke_internal_chain(
                    chain, {"question": question, "document": doc_context}
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

        return {
            "documents": kept,
            "sources": kept,
            "irrelevant_documents": irrelevant_documents,
        }

    async def _generate_draft(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Generate the current best answer draft from the selected sources.

        How to use:
            Provide `question` and `documents`; this returns the draft AI message,
            the current sources snapshot, and a trace message.
        """
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
            response = await self._ainvoke_internal_model(messages)

        response = cast(AIMessage, response)
        return {
            "draft_answer": response,
            "sources": documents,
        }

    async def _self_check(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Evaluate whether the current draft is grounded enough to finalize.

        How to use:
            Provide `draft_answer` and `documents`; this returns the structured
            self-check result plus a compact trace message.
        """
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
        chain = prompt | self.internal_model.with_structured_output(SelfCheckOutput)

        with self.kpi_timer("agent.step_latency_ms", dims={"step": "self_check"}):
            llm_response = await self._ainvoke_internal_chain(
                chain,
                {
                    "question": question,
                    "answer": answer_text,
                    "sources": sources_block,
                },
            )
        check = cast(SelfCheckOutput, llm_response)

        return {
            "self_check": check,
        }

    async def _corrective_plan(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Decide whether Aegis should retrieve again and with which follow-up queries.

        How to use:
            Provide `self_check` and `iteration`; this returns the next decision,
            any follow-up queries, and a trace message.
        """
        iteration = int(state.get("iteration", 0) or 0)
        max_iterations = self.get_tuned_int("rag.max_iterations", default=2)
        check = cast(SelfCheckOutput, state.get("self_check"))

        if iteration >= max_iterations:
            return {
                "decision": "finalize_best_effort",
            }

        queries: List[str] = []
        if check and check.suggested_queries:
            queries = [q.strip() for q in check.suggested_queries if q.strip()]

        if not queries:
            template = self.get_tuned_text("prompts.gap_queries") or gap_query_prompt()
            prompt = ChatPromptTemplate.from_template(template)
            chain = prompt | self.internal_model.with_structured_output(
                GapQueriesOutput
            )
            missing = ", ".join(check.missing_aspects or []) or "unspecified gaps"
            with self.kpi_timer("agent.step_latency_ms", dims={"step": "gap_queries"}):
                llm_response = await self._ainvoke_internal_chain(
                    chain,
                    {"question": state.get("question"), "missing_aspects": missing},
                )
            output = cast(GapQueriesOutput, llm_response)
            queries = [q.strip() for q in output.queries if q.strip()]

        if not queries:
            queries = [cast(str, state.get("question"))]

        queries = queries[:3]
        return {
            "followup_queries": queries,
            "decision": "corrective_retrieve",
        }

    async def _corrective_retrieve(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Run follow-up retrieval queries and merge new evidence into the draft context.

        How to use:
            Provide `followup_queries` plus the current retrieval state; this returns
            merged sources, the incremented iteration counter, and a trace message.
        """
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

        return {
            "documents": merged_hits,
            "sources": merged_hits,
            "iteration": int(state.get("iteration", 0) or 0) + 1,
        }

    async def _no_results(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Produce a best-effort draft when retrieval yields no corpus evidence.

        How to use:
            Provide `question`; this returns a draft answer with empty sources and a
            trace message so finalization can emit a normal assistant update.
        """
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
            response = await self._ainvoke_internal_model(messages)

        return {
            "draft_answer": cast(AIMessage, response),
            "sources": [],
        }

    async def _finalize_success(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Emit the validated final assistant answer as a LangGraph `messages` update.

        How to use:
            Provide `draft_answer` and `sources`; this returns the final AI message
            plus the state reset fields expected after a completed turn.
        """
        hits = cast(List[VectorSearchHit], state.get("sources") or [])
        answer = self._build_final_answer_message(state, hits)
        logger.info(
            "[AEGIS][FINAL_EMIT] mode=success content_len=%d sources=%d",
            len(self._get_text_content(answer)),
            len(hits),
        )
        return {
            "messages": [answer],
            "question": "",
            "sources": [],
            "documents": [],
            "iteration": 0,
            "draft_answer": None,
            "self_check": None,
            "followup_queries": [],
            "decision": None,
            "irrelevant_documents": [],
        }

    async def _finalize_best_effort(self, state: AegisGraphState) -> AegisGraphState:
        """
        Why this exists:
            Emit the best-effort assistant answer when quality gates do not fully pass.

        How to use:
            Provide `draft_answer` and `sources`; this returns the final AI message
            under `messages` and clears transient graph fields for the next turn.
        """
        hits = cast(List[VectorSearchHit], state.get("sources") or [])
        answer = self._build_final_answer_message(state, hits)
        logger.info(
            "[AEGIS][FINAL_EMIT] mode=best_effort content_len=%d sources=%d",
            len(self._get_text_content(answer)),
            len(hits),
        )
        return {
            "messages": [answer],
            "question": "",
            "sources": [],
            "documents": [],
            "iteration": 0,
            "draft_answer": None,
            "self_check": None,
            "followup_queries": [],
            "decision": None,
            "irrelevant_documents": [],
        }

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
            logger.info(
                "[AEGIS][GRAPH_ROUTE] from=self_check to=finalize_success iteration=%d min_docs_ok=%s",
                int(state.get("iteration", 0) or 0),
                min_docs_ok,
            )
            return "finalize_success"

        iteration = int(state.get("iteration", 0) or 0)
        max_iterations = self.get_tuned_int("rag.max_iterations", default=2)
        if iteration >= max_iterations:
            logger.info(
                "[AEGIS][GRAPH_ROUTE] from=self_check to=finalize_best_effort iteration=%d min_docs_ok=%s",
                iteration,
                min_docs_ok,
            )
            return "finalize_best_effort"
        logger.info(
            "[AEGIS][GRAPH_ROUTE] from=self_check to=corrective_plan iteration=%d min_docs_ok=%s",
            iteration,
            min_docs_ok,
        )
        return "corrective_plan"
