from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime

from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


def build_kf_vector_search_tools(agent: KnowledgeFlowAgentContext) -> list[BaseTool]:
    """Return in-process LangChain tools for Knowledge Flow vector search."""

    @tool("semantic_search")
    async def kf_vector_search(
        runtime: ToolRuntime[RuntimeContext],
        query: str,
        top_k: int = 5,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        document_uids: Optional[Sequence[str]] = None,
    ) -> str:
        """Semantic search in the user documents (RAG)"""
        client = VectorSearchClient(agent=agent)
        hits = await client.agent_search(
            agent_settings=agent.agent_settings,
            runtime_context=runtime.context,
            question=query,
            top_k=top_k,
            document_library_tags_ids=document_library_tags_ids,
            document_uids=document_uids,
        )

        # todo: return a string to agent and json metadata for the UI ?
        serialized = [h.model_dump() if hasattr(h, "model_dump") else h for h in hits]
        return json.dumps({"hits": serialized}, ensure_ascii=False)

    return [kf_vector_search]
