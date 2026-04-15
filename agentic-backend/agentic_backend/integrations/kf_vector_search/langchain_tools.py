from __future__ import annotations

import json
import logging
from typing import Optional, Sequence

from langchain_core.tools import BaseTool, tool

from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.common.kf_vectorsearch_client import VectorSearchClient

logger = logging.getLogger(__name__)


def build_kf_vector_search_tools(agent: KnowledgeFlowAgentContext) -> list[BaseTool]:
    """Return in-process LangChain tools for Knowledge Flow vector search."""
    client = VectorSearchClient(agent=agent)

    @tool("kf_vector_search")
    async def kf_vector_search(
        question: str,
        top_k: int = 10,
        document_library_tags_ids: Optional[Sequence[str]] = None,
        document_uids: Optional[Sequence[str]] = None,
    ) -> str:
        """Search the Knowledge Flow vector index and return matching document chunks."""
        hits = await client.search(
            question=question,
            top_k=top_k,
            document_library_tags_ids=document_library_tags_ids,
            document_uids=document_uids,
        )
        # todo: return a string and not json ?
        return json.dumps(
            [h.model_dump() if hasattr(h, "model_dump") else h for h in hits],
            ensure_ascii=False,
        )

    return [kf_vector_search]
