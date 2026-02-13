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
from typing import List, Tuple

from fred_core import VectorSearchHit
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph

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
                "Message sent to the model when the search returns no documents at all. Include a {question} placeholder if needed."
            ),
            required=True,
            default=(
                "No relevant documents or uploaded files were found in the selected libraries "
                "to answer this question. Please refine the query (e.g., add date/location constraints, a specific document type, or alternate keywords), "
                "or upload supporting documents so I can work with concrete sources.\n\n"
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
        builder = StateGraph(MessagesState)
        builder.add_node("reasoner", self._run_reasoning_step)
        builder.add_edge(START, "reasoner")
        builder.add_edge("reasoner", END)
        return builder

    # -----------------------------
    # Small helpers (local policy)
    # -----------------------------
    def _render_tuned_prompt(self, key: str, **tokens) -> str:
        prompt = self.get_tuned_text(key)
        if not prompt:
            logger.warning("Rico: no tuned prompt found for %s", key)
            raise RuntimeError(f"Rico: no tuned prompt found for '{key}'.")
        return self.render(prompt, **tokens)

    def _system_prompt(self) -> str:
        """
        Resolve the RAG system prompt from tuning; optionally append chat context text if enabled.
        """
        response_language = get_language(self.get_runtime_context()) or "English"
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
    async def _run_reasoning_step(self, state: MessagesState):
        if self.model is None:
            raise RuntimeError(
                "Model is not initialized. Did you forget to call async_init()?"
            )

        # Last user question (MessagesState ensures 'messages' is AnyMessage[])
        last = state["messages"][-1]
        if not isinstance(last.content, str):
            raise TypeError(
                f"Expected string content for the last message, got: {type(last.content).__name__}"
            )
        question = last.content

        try:
            runtime_context = self.get_runtime_context()
            rag_scope = get_rag_knowledge_scope(runtime_context)
            response_language = get_language(runtime_context) or "English"
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
                history = self.get_recent_history(
                    state["messages"],
                    max_messages=history_max,
                    include_system=False,
                    include_tool=False,
                    drop_last=True,
                )
                human_msg = HumanMessage(
                    content=self._render_tuned_prompt(
                        "prompts.no_sources", question=question
                    )
                )
                messages = [sys_msg, *history, human_msg]
                messages = await self.with_chat_context_text(messages)
                async with self.phase("answer_general_only"):
                    answer = await self.model.ainvoke(messages)
                return {"messages": [answer]}

            # 0) Optional keyword expansion to widen recall
            augmented_question = question
            keywords: List[str] = []
            if bool(self.get_tuned_any("rag.keyword_expansion")):
                augmented_question, keywords = await self._expand_with_keywords(
                    question
                )
                logger.debug(
                    "[AGENT] keyword expansion enabled; raw_question=%r keywords=%s augmented=%r",
                    question,
                    keywords,
                    augmented_question,
                )
            else:
                logger.debug(
                    "[AGENT] keyword expansion disabled; using raw_question=%r",
                    question,
                )

            # 1) Build retrieval scope from runtime context
            doc_tag_ids = get_document_library_tags_ids(runtime_context)
            document_uids = get_document_uids(runtime_context)
            search_policy = get_search_policy(runtime_context)
            top_k = self.get_tuned_int("rag.top_k", default=10)
            logger.debug(
                "[AGENT] reasoning start question=%r doc_tag_ids=%s document_uids=%s search_policy=%s top_k=%s rag_scope=%s",
                question,
                doc_tag_ids,
                document_uids,
                search_policy,
                top_k,
                rag_scope,
            )
            logger.info(
                "[AGENT][SESSION PATH] question=%r runtime_context.session_id=%s rag_scope=%s search_policy=%s doc_tag_ids=%s document_uids=%s",
                question,
                runtime_context.session_id if runtime_context else None,
                rag_scope,
                search_policy,
                doc_tag_ids,
                document_uids,
            )

            if not runtime_context or not runtime_context.session_id:
                raise RuntimeError(
                    "Runtime context missing session_id; required for scoped retrieval."
                )
            include_session_scope, include_corpus_scope = get_vector_search_scopes(
                runtime_context
            )

            # 2) Vector search
            async with self.phase("vector_search"):
                hits: List[VectorSearchHit] = await self.search_client.search(
                    question=augmented_question,
                    top_k=top_k,
                    document_library_tags_ids=doc_tag_ids,
                    document_uids=document_uids,
                    search_policy=search_policy,
                    session_id=runtime_context.session_id,
                    include_session_scope=include_session_scope,
                    include_corpus_scope=include_corpus_scope,
                )
            logger.debug("[AGENT] vector search returned %d hit(s)", len(hits))
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
                if is_corpus_only_mode(runtime_context):
                    warn = (
                        "No relevant documents or attached files were found in the selected libraries, "
                        "and I am restricted to the corpus only. Please provide documents or refine your query."
                    )
                else:
                    warn = (
                        "I couldn't find any relevant documents or uploaded attachments for that question. "
                        "Try asking about something covered by the selected libraries or upload relevant files."
                    )
                messages = [HumanMessage(content=warn)]
                messages = await self.with_chat_context_text(messages)

                async with self.phase("answer_no_results"):
                    return {"messages": [await self.model.ainvoke(messages)]}

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
            elif search_policy != "semantic":
                logger.debug(
                    "Rico: skipping min_score filter because search_policy=%s",
                    search_policy,
                )

            if not hits:
                sys_msg = SystemMessage(content=self._system_prompt())
                history_max = self.get_tuned_int(
                    "rag.history_max_messages", default=6, min_value=0
                )
                history = self.get_recent_history(
                    state["messages"],
                    max_messages=history_max,
                    include_system=False,
                    include_tool=False,
                    drop_last=True,
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
                    answer = await self.model.ainvoke(messages)
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
            history = self.get_recent_history(
                state["messages"],
                max_messages=history_max,
                include_system=False,
                include_tool=False,
                drop_last=True,
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
                answer = await self.model.ainvoke(messages)

            # 6) Attach rich sources metadata for the UI
            attach_sources_to_llm_response(answer, hits)

            return {"messages": [answer]}

        except Exception as e:
            info = normalize_llm_exception(e)
            hits_count = (
                len(locals().get("hits", []))
                if isinstance(locals().get("hits", None), list)
                else 0
            )
            log_ctx = error_log_context(
                info,
                extra={
                    "question": question,
                    "doc_tag_ids": locals().get("doc_tag_ids"),
                    "search_policy": locals().get("search_policy"),
                    "top_k": locals().get("top_k"),
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
                language=get_language(runtime_context) or "English",
                default_message="An unexpected error occurred while searching documents. Please try again.",
            )
            fallback = await self.model.ainvoke([HumanMessage(content=fallback_text)])
            return {"messages": [fallback]}
