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
import time
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    TypedDict,
    cast,
)

from fred_core import OwnerFilter, VectorSearchHit
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph, add_messages

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient
from agentic_backend.common.llm_errors import (
    error_log_context,
    guardrail_fallback_message,
    normalize_llm_exception,
)
from agentic_backend.common.rags_utils import (
    attach_sources_to_llm_response,
    ensure_ranks,
    format_sources_for_prompt,
    sort_hits,
)
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

logger = logging.getLogger(__name__)


class RicoGraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    documents: List[VectorSearchHit]
    sources: List[VectorSearchHit]
    retrieval_total_hits: int
    retrieval_latency_ms: int
    retrieval_search_policy: str
    retrieval_top_k: int
    retrieval_doc_tag_ids: List[str]
    retrieval_document_uids: List[str]
    retrieval_augmented_question: str
    retrieval_keywords: List[str]


# -----------------------------
# Spec-only tuning (class-level)
# -----------------------------
# Dev note:
# - These are *UI schema fields* (spec). Live values come from AgentSettings.tuning
#   and are applied by AgentFlow at runtime.
RAG_TUNING = AgentTuning(
    # High-level role as seen by UI / other tools
    role="Document Retrieval Agent",
    description=(
        "A general-purpose RAG agent that answers questions using retrieved document snippets. "
        "It grounds all claims in the provided sources, cites them inline, and explicitly acknowledges "
        "when the evidence is weak, conflicting, or missing."
    ),
    tags=["document"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="RAG System Prompt",
            description=(
                "Defines the assistant’s behavior for evidence-based answers, source usage, and citation style."
            ),
            required=True,
            default=(
                "You are a general-purpose document retrieval and question-answering assistant.\n"
                "\n"
                "Your job is to answer user questions using the document excerpts (sources) that are provided to you.\n"
                "\n"
                "Core rules:\n"
                "- Treat the provided sources as your primary ground truth for factual claims.\n"
                "- When you make a factual claim supported by a source, add bracketed numeric citations like [1], [2]\n"
                "  that correspond to the numbered sources you were given.\n"
                "- If multiple sources support the same statement, you may list several citations (e.g. [1][3]).\n"
                "- You may summarize, rephrase, and organize the content from the sources, but do not invent new facts\n"
                "  that are not supported by them.\n"
                "- If the sources are incomplete, ambiguous, or do not directly answer the question, say this explicitly\n"
                "  and avoid speculation.\n"
                "- If the user asks for background information that clearly goes beyond the sources, briefly explain\n"
                "  that this is outside the provided documents instead of guessing.\n"
                "\n"
                "Style guidelines:\n"
                "- Be clear, concise, and neutral in tone.\n"
                "- Prefer short paragraphs and, when helpful, bullet lists.\n"
                "- Make the reasoning easy to follow, but do not expose chain-of-thought step by step.\n"
                "- Always respond in {response_language}.\n"
                "\n"
                "Today is {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.with_sources",
            type="prompt",
            title="Answer With Sources",
            description=(
                "User-facing instructions when sources are available. "
                "Include placeholders for {question} and {sources}."
            ),
            required=True,
            default=(
                "Base your answer on the following documents. Prioritize these sources and cite the document title.\n"
                "If the information is missing, cautiously supplement with your general knowledge and state that it does not come from the documents.\n"
                "If the sources conflict or are insufficient, mention it briefly.\n\n"
                "Question:\n{question}\n\n"
                "Documents:\n{sources}\n"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.no_sources",
            type="prompt",
            title="Answer Without Sources",
            description=(
                "Instructions when no usable sources remain after filtering. Include a {question} placeholder."
            ),
            required=True,
            default=(
                "No relevant documents were found to answer this question. Respond using your general knowledge and explicitly state that your answer does not come from the provided documents.\n\n"
                "Question:\n{question}"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.no_results",
            type="prompt",
            title="No Results Message",
            description=(
                "Message sent to the model when the search returns no documents at all. "
                "Include placeholders for {question} and {response_language}."
            ),
            required=True,
            default=(
                "No relevant information was found in the selected corpus (libraries and session attachments) for this question.\n"
                "Start your answer with one explicit sentence in {response_language} stating that there is no supporting information in the corpus.\n"
                "Then, if corpus-only mode is active, explain that you cannot answer without corpus evidence.\n"
                "Otherwise, you may provide a concise general-knowledge answer, clearly labeled as not grounded in corpus documents.\n\n"
                "Question:\n{question}"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.keyword_expansion",
            type="prompt",
            title="Keyword Expansion Prompt",
            description=(
                "Prompt used to extract keywords before retrieval. Include the {question} placeholder."
            ),
            required=True,
            default=(
                "Here is a user question:\n"
                "{question}\n\n"
                "List at most 6 important keywords or keyphrases for a focused document search.\n"
                "- Reply only with a comma-separated list.\n"
                "- No sentences, no numbering."
            ),
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
            key="chat_options.deep_search_delegate",
            type="boolean",
            title="Deep search delegate toggle",
            description="Allow delegation to a senior agent for deep search.",
            required=False,
            default=False,
            ui=UIHints(group="Chat options"),
        ),
        FieldSpec(
            key="chat_options.include_corpus_in_search",
            type="boolean",
            title="Include corpus in search",
            description="Allow corpus retrieval alongside attachments/session scope.",
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
            default=8,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="rag.keyword_expansion",
            type="boolean",
            title="Enable Keyword Expansion",
            description=(
                "If enabled, the model first extracts keywords and augments the query before vector search to widen recall."
            ),
            required=False,
            default=False,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="rag.history_max_messages",
            type="integer",
            title="Conversation Memory",
            description="How many recent messages to include before the current question.",
            required=False,
            default=10,
            ui=UIHints(group="Prompts"),
        ),
        FieldSpec(
            key="rag.min_score",
            type="number",
            title="Minimum Score (filter)",
            description=(
                "Semantic search only: filter out vector hits with a score below this value. "
                "Ignored for other search modes. Set 0.0 to disable (default)."
            ),
            required=False,
            default=0.0,
            ui=UIHints(group="Retrieval"),
        ),
    ],
)


@expose_runtime_source("agent.Rico")
class Rico(AgentFlow):
    """
    Retrieval-Augmented Generation expert.

    Key principles (aligned with AgentFlow):
    - No hidden prompt composition. This node explicitly chooses which tuned fields to use.
    - Graph is built in async_init() and compiled lazily via AgentFlow.get_compiled_graph().
    - Chat context text is *opt-in* (governed by a tuning boolean).
    """

    tuning = RAG_TUNING  # UI schema only; live values are in AgentSettings.tuning

    async def async_init(self, runtime_context: RuntimeContext):
        """Bind the model, create the vector search client, and build the graph."""
        self.model = get_default_chat_model()
        self.search_client = VectorSearchClient(agent=self)
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(RicoGraphState)
        builder.add_node("corpus_research", self._corpus_research_step)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "corpus_research")
        builder.add_edge("corpus_research", "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    # -----------------------------
    # Small helpers (local policy)
    # -----------------------------
    def _mk_progress_thought(self, *, text: str, node: str, label: str) -> AIMessage:
        return AIMessage(
            content="",
            response_metadata={
                "thought": text,
                "extras": {"task": "progress", "node": node, "label": label},
            },
        )

    def _mk_tool_call(
        self, *, call_id: str, name: str, args: Dict[str, Any]
    ) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"id": call_id, "name": name, "args": args}],
            response_metadata={"extras": {"task": "retrieval", "node": name}},
        )

    def _mk_tool_result(
        self,
        *,
        call_id: str,
        content: str,
        ok: Optional[bool] = None,
        latency_ms: Optional[int] = None,
        extras: Optional[Dict[str, Any]] = None,
        sources: Optional[List[VectorSearchHit]] = None,
    ) -> ToolMessage:
        md: Dict[str, Any] = {}
        if extras:
            md["extras"] = extras
        if latency_ms is not None:
            md["latency_ms"] = latency_ms
        if ok is not None:
            md["ok"] = ok
        if sources:
            md["sources"] = [
                s.model_dump() if hasattr(s, "model_dump") else s for s in sources
            ]
        return ToolMessage(content=content, tool_call_id=call_id, response_metadata=md)

    def _attach_latency_to_ai_message(
        self, message: AIMessage, *, latency_ms: int
    ) -> AIMessage:
        md = getattr(message, "response_metadata", {}) or {}
        md["latency_ms"] = latency_ms
        setattr(message, "response_metadata", md)
        return message

    def _progress_text(self, *, fr: str, en: str) -> str:
        language = self._normalize_response_language(
            get_language(self.get_runtime_context()),
            default="English",
        ).lower()
        return fr if language.startswith("fr") else en

    async def _corpus_research_step(self, state: RicoGraphState):
        question = self._current_question(state)
        runtime_context = self.get_runtime_context()
        if get_rag_knowledge_scope(runtime_context) == "general_only":
            return {
                "question": question,
                "documents": [],
                "sources": [],
                "retrieval_total_hits": 0,
                "messages": [
                    self._mk_progress_thought(
                        text=self._progress_text(
                            fr="Mode connaissance générale: recherche corpus ignorée.",
                            en="General-knowledge mode: corpus search skipped.",
                        ),
                        node="corpus_research",
                        label="corpus_research",
                    )
                ],
            }

        call_id = "tc_corpus_research_1"
        start = time.perf_counter()
        search_policy = "hybrid"
        top_k = self.get_tuned_int("rag.top_k", default=10)
        doc_tag_ids: List[str] = []
        document_uids: List[str] = []
        augmented_question = question
        keywords: List[str] = []
        hits: List[VectorSearchHit] = []

        call_msg = self._mk_tool_call(
            call_id=call_id,
            name="corpus_research",
            args={
                "query": question,
                "top_k": top_k,
            },
        )
        try:
            if not runtime_context or not runtime_context.session_id:
                raise RuntimeError(
                    "Runtime context missing session_id; required for scoped retrieval."
                )

            doc_tag_ids = get_document_library_tags_ids(runtime_context) or []
            document_uids = get_document_uids(runtime_context) or []
            search_policy = get_search_policy(runtime_context)
            top_k = self.get_tuned_int("rag.top_k", default=10)

            if bool(self.get_tuned_any("rag.keyword_expansion")):
                augmented_question, keywords = await self._expand_with_keywords(
                    question
                )

            include_session_scope, include_corpus_scope = get_vector_search_scopes(
                runtime_context
            )
            async with self.phase("vector_search"):
                hits = await self.search_client.search(
                    question=augmented_question,
                    top_k=top_k,
                    document_library_tags_ids=doc_tag_ids,
                    document_uids=document_uids,
                    search_policy=search_policy,
                    team_id=self.get_settings().team_id,
                    owner_filter=OwnerFilter.TEAM
                    if self.get_settings().team_id
                    else OwnerFilter.PERSONAL,
                    session_id=runtime_context.session_id,
                    include_session_scope=include_session_scope,
                    include_corpus_scope=include_corpus_scope,
                )
            latency_ms = int((time.perf_counter() - start) * 1000)
            result_msg = self._mk_tool_result(
                call_id=call_id,
                content=f"Retrieved {len(hits)} candidates.",
                ok=True,
                latency_ms=latency_ms,
                extras={"task": "retrieval", "node": "corpus_research"},
                sources=hits,
            )
            return {
                "question": question,
                "documents": hits,
                "sources": hits,
                "retrieval_total_hits": len(hits),
                "retrieval_latency_ms": latency_ms,
                "retrieval_search_policy": search_policy,
                "retrieval_top_k": top_k,
                "retrieval_doc_tag_ids": doc_tag_ids,
                "retrieval_document_uids": document_uids,
                "retrieval_augmented_question": augmented_question,
                "retrieval_keywords": keywords,
                "messages": [call_msg, result_msg],
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "Rico: corpus_research failed question=%r search_policy=%s top_k=%s",
                question,
                search_policy,
                top_k,
            )
            result_msg = self._mk_tool_result(
                call_id=call_id,
                content=f"Corpus retrieval failed: {e}",
                ok=False,
                latency_ms=latency_ms,
                extras={"task": "retrieval", "node": "corpus_research"},
            )
            return {
                "question": question,
                "documents": [],
                "sources": [],
                "retrieval_total_hits": 0,
                "retrieval_latency_ms": latency_ms,
                "retrieval_search_policy": search_policy,
                "retrieval_top_k": top_k,
                "retrieval_doc_tag_ids": doc_tag_ids,
                "retrieval_document_uids": document_uids,
                "retrieval_augmented_question": augmented_question,
                "retrieval_keywords": keywords,
                "messages": [call_msg, result_msg],
            }

    @staticmethod
    def _last_human_index(messages: Sequence[AnyMessage]) -> int | None:
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                return i
        return None

    def _latest_user_question(self, messages: Sequence[AnyMessage]) -> str:
        idx = self._last_human_index(messages)
        if idx is None:
            raise TypeError("No user message found in state.")
        last = messages[idx]
        if not isinstance(last.content, str):
            raise TypeError(
                f"Expected string content for the latest user message, got: {type(last.content).__name__}"
            )
        return last.content

    def _current_question(self, state: RicoGraphState) -> str:
        messages = cast(Sequence[AnyMessage], state.get("messages") or [])
        if self._last_human_index(messages) is not None:
            return self._latest_user_question(messages)

        question = cast(Optional[str], state.get("question"))
        if isinstance(question, str) and question:
            return question

        raise TypeError("No user question found in state.")

    def _history_before_current_question(
        self,
        messages: Sequence[AnyMessage],
        *,
        max_messages: int,
    ) -> list[AnyMessage]:
        idx = self._last_human_index(messages)
        if idx is None:
            return []
        prior = list(messages[:idx])
        return self.get_recent_history(
            prior,
            max_messages=max_messages,
            include_system=False,
            include_tool=False,
            drop_last=False,
        )

    def _render_tuned_prompt(self, key: str, **tokens) -> str:
        prompt = self.get_tuned_text(key)
        if not prompt:
            logger.warning("Rico: no tuned prompt found for %s", key)
            raise RuntimeError(f"Rico: no tuned prompt found for '{key}'.")
        return self.render(prompt, **tokens)

    @staticmethod
    def _normalize_response_language(
        language: str | None, default: str = "English"
    ) -> str:
        """
        Normalize locale-like values (e.g. fr, fr-FR, en-US) to model-friendly labels.
        """
        if not language:
            return default
        normalized = language.strip()
        if not normalized:
            return default
        key = normalized.lower().replace("_", "-")
        if key.startswith("fr"):
            return "français"
        if key.startswith("en"):
            return "English"
        return normalized

    @staticmethod
    def _empty_corpus_notice(response_language: str) -> str:
        lang = response_language.lower()
        if lang.startswith("fr"):
            return (
                "Aucune information pertinente n'a été trouvée dans le corpus "
                "sélectionné (bibliothèques et pièces jointes de session)."
            )
        return (
            "No relevant information was found in the selected corpus "
            "(libraries and session attachments)."
        )

    def _system_prompt(self) -> str:
        """
        Resolve the RAG system prompt from tuning; optionally append chat context text if enabled.
        """
        response_language = self._normalize_response_language(
            get_language(self.get_runtime_context()),
            default="English",
        )
        sys_text = self._render_tuned_prompt(
            "prompts.system", response_language=response_language
        )  # token-safe rendering (e.g. {today})

        logger.debug(
            "Rico: resolved system prompt (len=%d, language=%s)",
            len(sys_text),
            response_language or "default",
        )
        return sys_text

    async def _expand_with_keywords(self, question: str) -> Tuple[str, List[str]]:
        """
        Ask the model for a short list of keywords and append them to the query for retrieval.
        """
        prompt = self._render_tuned_prompt(
            "prompts.keyword_expansion", question=question
        )
        try:
            with self.kpi_timer(
                "agent.step_latency_ms", dims={"step": "keyword_expansion"}
            ):
                resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            raw = resp.content if isinstance(resp.content, str) else ""
            keywords = [kw.strip() for kw in raw.split(",") if kw.strip()]
            if not keywords:
                return question, []
            augmented = f"{question} {' '.join(keywords)}"
            return augmented, keywords
        except Exception as e:
            logger.warning(
                "Rico: keyword expansion failed, using raw question. err=%s", e
            )
            return question, []

    # -----------------------------
    # Node: reasoner
    # -----------------------------
    async def _run_reasoning_step(self, state: RicoGraphState):
        if self.model is None:
            raise RuntimeError(
                "Model is not initialized. Did you forget to call async_init()?"
            )

        state_messages = cast(Sequence[AnyMessage], state.get("messages") or [])
        question = self._current_question(state)
        runtime_context = self.get_runtime_context()
        doc_tag_ids = cast(List[str], state.get("retrieval_doc_tag_ids") or [])
        document_uids = cast(List[str], state.get("retrieval_document_uids") or [])
        search_policy = cast(Optional[str], state.get("retrieval_search_policy"))
        top_k = cast(Optional[int], state.get("retrieval_top_k"))
        hits = list(cast(List[VectorSearchHit], state.get("documents") or []))
        retrieval_total_hits = int(state.get("retrieval_total_hits", 0) or 0)
        retrieval_latency_ms = int(state.get("retrieval_latency_ms", 0) or 0)
        retrieval_keywords = cast(List[str], state.get("retrieval_keywords") or [])
        retrieval_augmented_question = (
            cast(Optional[str], state.get("retrieval_augmented_question")) or question
        )

        try:
            rag_scope = get_rag_knowledge_scope(runtime_context)
            response_language = self._normalize_response_language(
                get_language(runtime_context),
                default="English",
            )
            chat_context = await self.chat_context_text()
            include_chat_context = self.get_field_spec(
                "prompts.include_chat_context"
            ) is None or bool(self.get_tuned_any("prompts.include_chat_context"))
            logger.debug(
                "[AGENT] Rico prompt check: response_language=%s include_chat_context=%s system_prompt=%r chat_context=%r",
                response_language,
                include_chat_context,
                self._system_prompt(),
                chat_context,
            )

            if rag_scope == "general_only":
                logger.info("Rico: general-only mode; bypassing retrieval.")
                sys_msg = SystemMessage(content=self._system_prompt())
                history_max = self.get_tuned_int(
                    "rag.history_max_messages", default=6, min_value=0
                )
                history = self._history_before_current_question(
                    state_messages,
                    max_messages=history_max,
                )
                human_msg = HumanMessage(
                    content=self._render_tuned_prompt(
                        "prompts.no_sources", question=question
                    )
                )
                messages = [sys_msg, *history, human_msg]
                messages = await self.with_chat_context_text(messages)
                async with self.phase("answer_general_only"):
                    llm_start = time.perf_counter()
                    answer = cast(AIMessage, await self.model.ainvoke(messages))
                answer = self._attach_latency_to_ai_message(
                    answer,
                    latency_ms=int((time.perf_counter() - llm_start) * 1000),
                )
                return {"messages": [answer]}

            logger.debug(
                "[AGENT] reasoning start question=%r doc_tag_ids=%s document_uids=%s search_policy=%s top_k=%s rag_scope=%s retrieval_hits=%d retrieval_latency_ms=%d",
                question,
                doc_tag_ids,
                document_uids,
                search_policy,
                top_k,
                rag_scope,
                retrieval_total_hits,
                retrieval_latency_ms,
            )
            logger.info(
                "[AGENT][SESSION PATH] question=%r runtime_context.session_id=%s rag_scope=%s search_policy=%s doc_tag_ids=%s document_uids=%s retrieval_hits=%d",
                question,
                runtime_context.session_id if runtime_context else None,
                rag_scope,
                search_policy,
                doc_tag_ids,
                document_uids,
                retrieval_total_hits,
            )
            logger.debug(
                "[AGENT] retrieval inputs augmented_question=%r keywords=%s",
                retrieval_augmented_question,
                retrieval_keywords,
            )
            logger.debug("[AGENT] corpus_research returned %d hit(s)", len(hits))
            if hits:
                hit_summaries = []
                for h in hits[:10]:
                    score = (
                        f"{h.score:.3f}" if isinstance(h.score, (int, float)) else "NA"
                    )
                    label = h.title or h.file_name or h.uid
                    section = f" section={h.section}" if h.section else ""
                    page = f" page={h.page}" if h.page is not None else ""
                    hit_summaries.append(
                        f"[{h.rank}] score={score} title={label}{section}{page}"
                    )
                logger.debug("[AGENT] top hits: %s", "; ".join(hit_summaries))
            if not hits:
                sys_msg = SystemMessage(content=self._system_prompt())
                history_max = self.get_tuned_int(
                    "rag.history_max_messages", default=6, min_value=0
                )
                history = self._history_before_current_question(
                    state_messages,
                    max_messages=history_max,
                )
                if is_corpus_only_mode(runtime_context):
                    if response_language.lower().startswith("fr"):
                        warn = (
                            f"{self._empty_corpus_notice(response_language)}\n\n"
                            "Tu dois indiquer clairement que tu ne peux pas répondre "
                            "de façon fiable sans preuves dans le corpus, puis proposer "
                            "de reformuler la question ou d'ajouter des documents."
                        )
                    else:
                        warn = (
                            f"{self._empty_corpus_notice(response_language)}\n\n"
                            "You must clearly state that you cannot provide a reliable "
                            "answer without corpus evidence, then ask the user to "
                            "refine the request or upload relevant documents."
                        )
                else:
                    no_results_text = self._render_tuned_prompt(
                        "prompts.no_results",
                        question=question,
                        response_language=response_language,
                    )
                    warn = (
                        f"{self._empty_corpus_notice(response_language)}\n\n"
                        f"{no_results_text}"
                    )
                messages = [sys_msg, *history, HumanMessage(content=warn)]
                messages = await self.with_chat_context_text(messages)

                async with self.phase("answer_no_results"):
                    llm_start = time.perf_counter()
                    answer = cast(AIMessage, await self.model.ainvoke(messages))
                answer = self._attach_latency_to_ai_message(
                    answer,
                    latency_ms=int((time.perf_counter() - llm_start) * 1000),
                )
                return {"messages": [answer]}

            # 3) Deterministic ordering + fill ranks
            hits = sort_hits(hits)
            ensure_ranks(hits)

            # 3b) Optional score filter
            min_score = self.get_tuned_number("rag.min_score", default=0.0)
            if search_policy == "semantic" and min_score and min_score > 0:
                before = len(hits)
                hits = [
                    h
                    for h in hits
                    if isinstance(h.score, (int, float)) and h.score >= min_score
                ]
                logger.debug(
                    "Rico: score filter applied min_score=%.3f kept=%d/%d",
                    min_score,
                    len(hits),
                    before,
                )
            elif search_policy and search_policy != "semantic":
                logger.debug(
                    "Rico: skipping min_score filter because search_policy=%s",
                    search_policy,
                )

            if not hits:
                sys_msg = SystemMessage(content=self._system_prompt())
                history_max = self.get_tuned_int(
                    "rag.history_max_messages", default=6, min_value=0
                )
                history = self._history_before_current_question(
                    state_messages,
                    max_messages=history_max,
                )
                if is_corpus_only_mode(runtime_context):
                    no_sources_text = (
                        "No relevant documents were found for this question. "
                        "Answer that you cannot respond without corpus documents and refrain from using general knowledge.\n\n"
                        f"Question:\n{question}"
                    )
                else:
                    no_sources_text = self._render_tuned_prompt(
                        "prompts.no_sources", question=question
                    )
                human_msg = HumanMessage(content=no_sources_text)
                messages = [sys_msg, *history, human_msg]
                messages = await self.with_chat_context_text(messages)
                async with self.phase("answer_no_sources"):
                    llm_start = time.perf_counter()
                    answer = cast(AIMessage, await self.model.ainvoke(messages))
                answer = self._attach_latency_to_ai_message(
                    answer,
                    latency_ms=int((time.perf_counter() - llm_start) * 1000),
                )
                return {"messages": [answer]}

            # 4) Build messages explicitly (no magic)
            #    - One SystemMessage with policy/tone (from tuning)
            #    - One HumanMessage with task + formatted sources
            sys_msg = SystemMessage(content=self._system_prompt())
            sources_block = format_sources_for_prompt(hits, snippet_chars=500)
            logger.debug(
                "[AGENT] prepared %d source(s) for prompt (chars=%s)",
                len(hits),
                len(sources_block),
            )
            history_max = self.get_tuned_int(
                "rag.history_max_messages", default=6, min_value=0
            )
            history = self._history_before_current_question(
                state_messages,
                max_messages=history_max,
            )
            guardrails = ""
            if is_corpus_only_mode(runtime_context):
                guardrails = (
                    "\n\nIMPORTANT: Answer strictly using the provided documents. "
                    "If they are insufficient, state that you cannot answer without evidence from the corpus. "
                    "Do not rely on your general knowledge."
                )
            human_msg = HumanMessage(
                content=self._render_tuned_prompt(
                    "prompts.with_sources",
                    question=question,
                    sources=sources_block,
                )
                + guardrails
            )
            logger.debug(
                "[AGENT] prompt lengths sys=%d human=%d sources_chars=%d",
                len(sys_msg.content),
                len(human_msg.content),
                len(sources_block),
            )

            # 5) Ask the model
            messages = [sys_msg, *history, human_msg]
            messages = await self.with_chat_context_text(messages)

            logger.debug(
                "[AGENT] invoking model with %d messages (sys_len=%d human_len=%d)",
                len(messages),
                len(sys_msg.content),
                len(human_msg.content),
            )
            async with self.phase("answer_with_sources"):
                llm_start = time.perf_counter()
                answer = cast(AIMessage, await self.model.ainvoke(messages))
            answer = self._attach_latency_to_ai_message(
                answer,
                latency_ms=int((time.perf_counter() - llm_start) * 1000),
            )

            # 6) Attach rich sources metadata for the UI
            attach_sources_to_llm_response(answer, hits)

            return {"messages": [answer]}

        except Exception as e:
            info = normalize_llm_exception(e)
            hits_count = len(hits)
            log_ctx = error_log_context(
                info,
                extra={
                    "question": question,
                    "doc_tag_ids": doc_tag_ids,
                    "search_policy": search_policy,
                    "top_k": top_k,
                    "hits_count": hits_count,
                    "exception": str(e),
                },
            )
            logger.error(
                "[AGENT] error in reasoning step (guardrail=%s type=%s status=%s detail=%r): %s",
                info.is_guardrail,
                info.type_name,
                info.status,
                info.detail,
                e,
                extra={"err_ctx": log_ctx},
                exc_info=True,
            )

            fallback_text = guardrail_fallback_message(
                info,
                language=self._normalize_response_language(
                    get_language(runtime_context),
                    default="English",
                ),
                default_message="An unexpected error occurred while searching documents. Please try again.",
            )
            llm_start = time.perf_counter()
            fallback = cast(
                AIMessage,
                await self.model.ainvoke([HumanMessage(content=fallback_text)]),
            )
            fallback = self._attach_latency_to_ai_message(
                fallback,
                latency_ms=int((time.perf_counter() - llm_start) * 1000),
            )
            return {"messages": [fallback]}
