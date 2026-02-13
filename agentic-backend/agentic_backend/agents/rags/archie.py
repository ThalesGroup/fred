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
    should_skip_rag_search,
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
    role="Expert RAO Thales",
    description=(
        "Agent RAG expert pour les réponses aux appels d’offres Thales. Archie analyse, sélectionne et synthétise "
        "les informations issues des documents techniques, administratifs et méthodologiques (RAO, annexes, notes internes, fiches de service…). "
        "Il rédige des réponses structurées, précises et argumentées, adaptées aux attentes des clients et conformes "
        "aux bonnes pratiques RAO Thales : cohérence technique, pertinence des arguments, mise en avant de la valeur ajoutée, "
        "respect des exigences du cahier des charges et absence d'engagement non validé.\n\n"
        "Archie s’appuie prioritairement sur les extraits de documents fournis.  \n"
        "Lorsqu’une information est manquante ou partielle, il complète prudemment sa réponse à l’aide de connaissances générales "
    ),
    tags=["document"],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="RAG System Prompt",
            description=(
                "Sets the assistant policy for evidence-based answers and citation style."
            ),
            required=True,
            default=(
                "Tu es Archie, un expert Thales spécialisé dans l’analyse documentaire et la rédaction de réponses aux appels d’offres (RAO).\n"
                "\n"
                "Tu disposes de plusieurs extraits de documents techniques, administratifs ou méthodologiques fournis par l’utilisateur.\n"
                "Ton rôle est de construire des réponses claires, fiables, structurées et argumentées, adaptées à un contexte RAO et appuyées sur les documents fournis.\n"
                "\n"
                "Tes principes de réponse :\n"
                "1. Priorité aux documents\n"
                "   - Analyse attentivement les extraits fournis.\n"
                "   - Utilise-les comme base principale de ta réponse.\n"
                "   - Cite systématiquement la source utilisée (titre du document ou nom du fichier).\n"
                "\n"
                "2. Compléments hors documents\n"
                "   - Si les documents ne contiennent pas directement l’information demandée, complète la réponse avec tes connaissances générales (cybersécurité, SOC, cloud, systèmes critiques, certifications, normes, ITIL…).\n"
                "   - Mentionne explicitement lorsque ces compléments ne proviennent pas des documents fournis.\n"
                "\n"
                "3. Clarté et qualité rédactionnelle\n"
                "   - Reformule les contenus pour les rendre lisibles, pertinents et synthétiques.\n"
                "   - Adapte la granularité de ta réponse :\n"
                "     • synthétique pour les questions générales ;\n"
                "     • détaillée, argumentée et méthodologique pour les questions techniques ou complexes.\n"
                "\n"
                "4. Structure recommandée (si pertinente)\n"
                "   - Contexte / Enjeux\n"
                "   - Approche proposée / Méthodologie\n"
                "   - Capacités et valeur ajoutée Thales\n"
                "   - Éléments techniques ou organisationnels (ex : sécurité, certifications, gouvernance…)\n"
                "   - Limites ou informations manquantes\n"
                "   - Sources utilisées\n"
                "\n"
                "5. Exigences RAO Thales\n"
                "   - Pas d’engagement contractuel non présent dans les documents.\n"
                "   - Pas d’assertion qui contredirait les extraits fournis.\n"
                "   - Signale si les documents se contredisent ou sont incomplets.\n"
                "\n"
                "Sois précis, rigoureux, factuel et orienté valeur.\n"
                "\n"
                "Nous sommes le {today}.\n"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.with_sources",
            type="prompt",
            title="Réponse avec sources",
            description="Instructions quand des sources sont disponibles. Inclure {question} et {sources}.",
            required=True,
            default=(
                "Base ta réponse sur les documents suivants. Appuie-toi en priorité sur ces sources et cite le titre du document utilisé.\n"
                "Si l'information manque, complète prudemment avec tes connaissances générales et précise que ce n'est pas issu des documents.\n"
                "Si les sources se contredisent ou sont insuffisantes, signale-le brièvement.\n\n"
                "Question :\n{question}\n\n"
                "Documents :\n{sources}\n"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.no_sources",
            type="prompt",
            title="Réponse sans sources",
            description="Instructions quand aucune source pertinente n'est disponible. Inclure {question}.",
            required=True,
            default=(
                "Aucun document pertinent n'a été trouvé pour répondre à cette question. "
                "Réponds en t'appuyant sur tes connaissances générales et précise explicitement "
                "que ta réponse ne provient pas des documents fournis.\n\n"
                "Question :\n{question}"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.no_results",
            type="prompt",
            title="Message en absence de résultats",
            description="Message envoyé quand la recherche ne retourne aucun document. Peut utiliser {question}.",
            required=True,
            default=(
                "Je n'ai trouvé aucun document pertinent. Peux-tu reformuler ou préciser ta demande ?"
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="prompts.keyword_expansion",
            type="prompt",
            title="Extraction de mots-clés",
            description="Prompt pour extraire des mots-clés avant la recherche. Inclure {question}.",
            required=True,
            default=(
                "Voici une question utilisateur :\n"
                "{question}\n\n"
                "Donne au plus 6 mots-clés ou expressions importants pour une recherche documentaire précise.\n"
                "- Réponds uniquement par une liste séparée par des virgules.\n"
                "- Pas de phrase, pas de numérotation."
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
                "Extract keywords with the LLM and append them to the search query to widen recall."
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
            description="Filter out retrieved chunks with a score below this value (set to 0 to disable).",
            required=False,
            default=0.6,
            ui=UIHints(group="Retrieval"),
        ),
    ],
)


@expose_runtime_source("agent.Archie")
class Archie(AgentFlow):
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
            logger.warning("Archie: no tuned prompt found for %s", key)
            raise RuntimeError(f"Archie: no tuned prompt found for '{key}'.")
        return self.render(prompt, **tokens)

    def _system_prompt(self) -> str:
        """
        Resolve the RAG system prompt from tuning; optionally append chat context text if enabled.
        """
        response_language = get_language(self.get_runtime_context()) or ""

        sys_text = self._render_tuned_prompt(
            "prompts.system", response_language=response_language
        )  # token-safe rendering (e.g. {today})

        logger.debug(
            "Archie: resolved system prompt (len=%d, language=%s)",
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
            resp = await self.model.ainvoke([HumanMessage(content=prompt)])
            raw = resp.content if isinstance(resp.content, str) else ""
            keywords = [kw.strip() for kw in raw.split(",") if kw.strip()]
            if not keywords:
                return question, []
            augmented = f"{question} {' '.join(keywords)}"
            return augmented, keywords
        except Exception as e:
            logger.warning(
                "Archie: keyword expansion failed, using raw question. err=%s", e
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
        runtime_context = self.get_runtime_context()
        rag_scope = get_rag_knowledge_scope(runtime_context)
        logger.debug(
            "[AGENT] rag_scope=%s skip_rag_search=%s",
            rag_scope,
            should_skip_rag_search(runtime_context),
        )
        # Last user question (MessagesState ensures 'messages' is AnyMessage[])
        last = state["messages"][-1]
        if not isinstance(last.content, str):
            raise TypeError(
                f"Expected string content for the last message, got: {type(last.content).__name__}"
            )
        question = last.content

        try:
            response_language = get_language(runtime_context) or "français"
            chat_context = await self.chat_context_text()
            include_chat_context = self.get_field_spec(
                "prompts.include_chat_context"
            ) is None or bool(self.get_tuned_any("prompts.include_chat_context"))
            logger.debug(
                "[AGENT] archie prompt check: response_language=%s include_chat_context=%s system_prompt=%r chat_context=%r",
                response_language,
                include_chat_context,
                self._system_prompt(),
                chat_context,
            )
            skip_rag = should_skip_rag_search(runtime_context)
            if skip_rag:
                logger.debug("Archie: general-only mode; bypassing retrieval.")
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
                with self.kpi_timer(
                    "agent.step_latency_ms", dims={"step": "answer_general_only"}
                ):
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
                    "[AGENT]: keyword expansion enabled; raw_question=%r keywords=%s augmented=%r",
                    question,
                    keywords,
                    augmented_question,
                )
            else:
                logger.debug(
                    "[AGENT]: keyword expansion disabled; using raw_question=%r",
                    question,
                )

            # 1) Build retrieval scope from runtime context
            doc_tag_ids = get_document_library_tags_ids(runtime_context)
            document_uids = get_document_uids(runtime_context)
            search_policy = get_search_policy(runtime_context)
            corpus_only = is_corpus_only_mode(runtime_context)
            top_k = self.get_tuned_int("rag.top_k", default=10)
            logger.debug(
                "[AGENT]: reasoning start question=%r doc_tag_ids=%s document_uids=%s search_policy=%s top_k=%s",
                question,
                doc_tag_ids,
                document_uids,
                search_policy,
                top_k,
            )
            logger.debug(
                "[AGENT][SESSION PATH] question=%r runtime_context.session_id=%s rag_scope=%s search_policy=%s doc_tag_ids=%s document_uids=%s",
                question,
                runtime_context.session_id if runtime_context else None,
                rag_scope,
                search_policy,
                doc_tag_ids,
                document_uids,
            )

            # 2) Vector search
            session_id = runtime_context.session_id if runtime_context else None
            include_session_scope, include_corpus_scope = get_vector_search_scopes(
                runtime_context
            )
            if (
                not session_id
                and runtime_context
                and runtime_context.attachments_markdown
                and include_session_scope
            ):
                logger.warning(
                    "Archie: runtime_context.session_id is missing; attached-file retrieval will be skipped."
                )
            async with self.phase("vector_search"):
                hits: List[VectorSearchHit] = await self.search_client.search(
                    question=augmented_question,
                    top_k=top_k,
                    document_library_tags_ids=doc_tag_ids,
                    document_uids=document_uids,
                    search_policy=search_policy,
                    session_id=session_id,
                    include_session_scope=include_session_scope,
                    include_corpus_scope=include_corpus_scope,
                )
            logger.info("[AGENT]: vector search returned %d hit(s)", len(hits))
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
                logger.debug("[AGENT]: top hits: %s", "; ".join(hit_summaries))
            if not hits:
                if corpus_only:
                    warn = (
                        "No relevant documents were found for this question. "
                        "You must not use general knowledge in this mode. Explain that you cannot answer without corpus documents "
                        "and invite the user to refine the request or provide documents."
                    )
                else:
                    warn = self._render_tuned_prompt(
                        "prompts.no_results", question=question
                    )
                messages = await self.with_chat_context_text(
                    [HumanMessage(content=warn)]
                )

                async with self.phase("answer_no_results"):
                    return {"messages": [await self.model.ainvoke(messages)]}

            # 3) Deterministic ordering + fill ranks
            hits = sort_hits(hits)
            ensure_ranks(hits)

            # 3b) Optional score filter
            min_score = self.get_tuned_number("rag.min_score", default=0.6)
            if search_policy == "semantic" and min_score and min_score > 0:
                before = len(hits)
                hits = [
                    h
                    for h in hits
                    if isinstance(h.score, (int, float)) and h.score >= min_score
                ]
                logger.debug(
                    "[AGENT]: score filter applied min_score=%.3f kept=%d/%d",
                    min_score,
                    len(hits),
                    before,
                )
            elif search_policy != "semantic":
                logger.debug(
                    "[AGENT]: skipping min_score filter because search_policy=%s",
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
                if corpus_only:
                    no_sources_text = (
                        "No relevant documents were found for this question. "
                        "Answer that you cannot respond without corpus documents and do not use general knowledge.\n\n"
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
            if corpus_only:
                guardrails = (
                    "\n\nIMPORTANT: Answer strictly using the provided documents. "
                    "If they are insufficient, state that you cannot answer without evidence from the corpus and avoid using general knowledge."
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
                "[AGENT]: prompt lengths sys=%d human=%d sources_chars=%d",
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
                language=get_language(runtime_context) or "français",
                default_message="An unexpected error occurred while searching documents. Please try again.",
            )
            fallback = await self.model.ainvoke([HumanMessage(content=fallback_text)])
            return {"messages": [fallback]}
