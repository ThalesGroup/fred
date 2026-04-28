from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

from langchain_core.tools import BaseTool, tool

# from langgraph.prebuilt import ToolRuntime
from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient

# from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


def build_kf_vector_search_tools(agent: KnowledgeFlowAgentContext) -> list[BaseTool]:
    """Return in-process LangChain tools for Knowledge Flow vector search."""

    @tool("search_documents_using_vectorization")
    async def kf_vector_search(
        # todo: set back when gitlab agents do not call this tool directly with ainvoke (and use VectorSearchClient directly instead)
        # runtime: ToolRuntime[RuntimeContext],
        question: str,
        top_k: int = 5,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        document_uids: Optional[Sequence[str]] = None,
    ) -> str:
        """Search the user's document library using semantic similarity (RAG).

        Call this tool for ANY factual, technical, or domain-specific question BEFORE
        answering from training knowledge. The library may contain more specific,
        recent, or context-specific information than you already know — always search
        first, even when you believe you can answer without it.

        Skip this tool only for purely conversational exchanges (greetings, thanks,
        clarifying what was just said) where no document lookup could add value.

        By default, keep a top_k of 5.

        Returns ranked hits with title, content, and rank. For each answer:
        - Cite sources with bracketed numbers matching hit rank: [1], [2], etc.
        - Combine multiple sources when relevant: [1][3].
        - Only use information actually present in the returned hits. Do not invent or infer facts beyond what the hits contain.
        """
        client = VectorSearchClient(agent=agent)
        hits = await client.agent_search(
            # todo: retrieve agent settings and runtime_context from `runtime.context.context` (lanchain)
            agent_settings=agent.agent_settings,
            runtime_context=agent.runtime_context,
            question=question,
            top_k=top_k,
            document_library_tags_ids=document_library_tags_ids,
            document_uids=document_uids,
        )

        # todo: return a string to agent and json metadata for the UI ?
        serialized = [h.model_dump() if hasattr(h, "model_dump") else h for h in hits]
        return json.dumps(serialized, ensure_ascii=False)

    return [kf_vector_search]
