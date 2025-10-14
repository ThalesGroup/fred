# app/agents/rag/rag_expert.py
# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0

import logging
from typing import List

from fred_core import VectorSearchHit, get_model
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph

from app.common.rags_utils import (
    attach_sources_to_llm_response,
    ensure_ranks,
    format_sources_for_prompt,
    sort_hits,
)
from app.common.structures import AgentChatOptions
from app.common.vector_search_client import VectorSearchClient
from app.core.agents.agent_flow import AgentFlow
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from app.core.agents.runtime_context import (
    get_document_library_tags_ids,
    get_search_policy,
)
from app.core.runtime_source import expose_runtime_source

logger = logging.getLogger(__name__)

# -----------------------------
# Spec-only tuning (class-level)
# -----------------------------
# Dev note:
# - These are *UI schema fields* (spec). Live values come from AgentSettings.tuning
#   and are applied by AgentFlow at runtime.
RAG_TUNING = AgentTuning(
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
                "You answer strictly based on the retrieved document chunks.\n"
                "Always cite claims using bracketed numeric markers like [1], [2], matching the provided sources list.\n"
                "Be concise and factual. If evidence is weak or missing, say so."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
        FieldSpec(
            key="rag.top_k",
            type="integer",
            title="Top-K Documents",
            description="How many chunks to retrieve per question.",
            required=False,
            default=3,
            ui=UIHints(group="Retrieval"),
        ),
        FieldSpec(
            key="prompts.include_chat_context",
            type="boolean",
            title="Append Chat Context to System Prompt",
            description="If true, append the runtime chat context text after the system prompt.",
            required=False,
            default=False,
            ui=UIHints(group="Prompts"),
        ),
    ]
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
    default_chat_options = AgentChatOptions(
        search_policy_selection=True,
        libraries_selection=True,
    )

    async def async_init(self):
        """Bind the model, create the vector search client, and build the graph."""
        self.model = get_model(self.agent_settings.model)
        self.search_client = VectorSearchClient()
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
    def _system_prompt(self) -> str:
        """
        Resolve the RAG system prompt from tuning; optionally append chat context text if enabled.
        """
        sys_tpl = self.get_tuned_text("prompts.system")
        if not sys_tpl:
            logger.warning("Rico: no tuned system prompt found, using fallback.")
            raise RuntimeError("Rico: no tuned system prompt found.")
        sys_text = self.render(sys_tpl)  # token-safe rendering (e.g. {today})

        return sys_text

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
            # 1) Build retrieval scope from runtime context
            doc_tag_ids = get_document_library_tags_ids(self.get_runtime_context())
            search_policy = get_search_policy(self.get_runtime_context())
            top_k = self.get_tuned_int("search.top_k", default=3)

            # 2) Vector search
            hits: List[VectorSearchHit] = self.search_client.search(
                question=question,
                top_k=top_k,
                document_library_tags_ids=doc_tag_ids,
                search_policy=search_policy,
            )
            if not hits:
                warn = "I couldn't find any relevant documents. Try rephrasing or expanding your query?"
                messages = self.with_chat_context_text([HumanMessage(content=warn)])

                return {"messages": [await self.model.ainvoke(messages)]}

            # 3) Deterministic ordering + fill ranks
            hits = sort_hits(hits)
            ensure_ranks(hits)

            # 4) Build messages explicitly (no magic)
            #    - One SystemMessage with policy/tone (from tuning)
            #    - One HumanMessage with task + formatted sources
            sys_msg = SystemMessage(content=self._system_prompt())
            sources_block = format_sources_for_prompt(hits, snippet_chars=500)
            human_msg = HumanMessage(
                content=(
                    "Use ONLY the sources below. When you state a fact, add citations like [1] or [1][2]. "
                    "If sources disagree or are insufficient, say so briefly.\n\n"
                    f"Question:\n{question}\n\n"
                    f"Sources:\n{sources_block}\n"
                )
            )

            # 5) Ask the model
            messages = [sys_msg, human_msg]
            messages = self.with_chat_context_text(messages)

            answer = await self.model.ainvoke(messages)

            # 6) Attach rich sources metadata for the UI
            attach_sources_to_llm_response(answer, hits)

            return {"messages": [answer]}

        except Exception:
            logger.exception("Rico: error in reasoning step.")
            fallback = await self.model.ainvoke(
                [
                    HumanMessage(
                        content="An unexpected error occurred while searching documents. Please try again."
                    )
                ]
            )
            return {"messages": [fallback]}
