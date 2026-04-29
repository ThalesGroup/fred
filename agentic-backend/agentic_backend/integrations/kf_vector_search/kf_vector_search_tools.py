from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

from langchain_core.tools import BaseTool, tool

# from langgraph.prebuilt import ToolRuntime
from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient
from agentic_backend.common.rags_utils import ensure_ranks, sort_hits
from agentic_backend.core.agents.v2.contracts.context import ToolInvocationResult

# from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


def build_kf_vector_search_tools(agent: KnowledgeFlowAgentContext) -> list[BaseTool]:
    """Return in-process LangChain tools for Knowledge Flow vector search."""

    @tool(
        "search_documents_using_vectorization", response_format="content_and_artifact"
    )
    async def kf_vector_search(
        # todo: set back when gitlab agents do not call this tool directly with ainvoke (and use VectorSearchClient directly instead)
        # runtime: ToolRuntime[RuntimeContext],
        question: str,
        top_k: int = 5,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        document_uids: Optional[Sequence[str]] = None,
    ) -> tuple[str, ToolInvocationResult]:
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

        hits = sort_hits(hits)
        ensure_ranks(hits)

        logger.info(
            "[OBS][SEARCH][TOOL] question=%r top_k=%d llm_scoped_libs=%s llm_scoped_uids=%s -> hits_to_llm=%d titles=%s",
            question[:80],
            top_k,
            list(document_library_tags_ids) if document_library_tags_ids else None,
            list(document_uids) if document_uids else None,
            len(hits),
            [h.title for h in hits],
        )
        serialized = [h.model_dump() if hasattr(h, "model_dump") else h for h in hits]
        artifact = ToolInvocationResult(
            tool_ref="kf_vector_search",
            sources=tuple(hits),
        )
        return json.dumps(serialized, ensure_ascii=False), artifact

    return [kf_vector_search]
