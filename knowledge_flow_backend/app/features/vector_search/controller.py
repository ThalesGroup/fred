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
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException
from langchain.schema.document import Document

from app.features.vector_search.service import VectorSearchService
from app.features.vector_search.structures import DocumentSource, SearchRequest

logger = logging.getLogger(__name__)


def handle_exception(e: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail="Internal server error")


class VectorSearchController:
    """app/features/tabular/__init__.py
    Controller responsible for document search using vector similarity.

    This controller exposes a REST API endpoint for embedding-based search
    over previously ingested and vectorized documents. Results are returned
    as ranked `DocumentSource` objects with associated similarity scores and metadata.

    Exposure:
    ---------
    This controller is **also registered as an MCP tool** in `main.py` under the name
    `"search_documents_using_vectorization"` and can be invoked programmatically by
    agents such as Dominic. This makes it a central capability in the Knowledge Flow
    architecture, bridging both REST and agentic workflows.

    Current Usage:
    --------------
    - Accessed directly via REST (e.g., for external tools or UIs)
    - Invoked by agents via MCP workflows (e.g., from LangGraph plans)

    Limitations and Design Considerations:
    --------------------------------------
    The implementation performs a simple similarity search over the vector index,
    without caching, reranking, or context-aware adaptation.

    Future directions include:
    - Avoiding redundant queries for the same session
    - Introducing query memory or context for improved relevance
    - Supporting advanced filtering (e.g., by tags, access rights)
    - Integrating hybrid keyword + vector search
    """

    def __init__(self, router: APIRouter):
        self.service = VectorSearchService()

        @router.post(
            "/vector/search",
            tags=["Vector Search"],
            summary="Search documents using vectorization",
            description="Search documents using vectorization. Returns a list of documents that match the query.",
            response_model=List[DocumentSource],
            operation_id="search_documents_using_vectorization",
        )
        def vector_search(request: SearchRequest):
            try:
                results = self.service.similarity_search_with_score(request.query, k=request.top_k, tags=request.tags)
                return [self._to_document_source(doc, score, rank) for rank, (doc, score) in enumerate(results, start=1)]
            except Exception as e:
                logger.error("Vector search failed:", e)
                raise handle_exception(e)

    def _to_document_source(self, doc: Document, score: float, rank: int) -> DocumentSource:
        metadata = doc.metadata
        print("doc", doc.__dict__)
        try:
            return DocumentSource(
                content=doc.page_content,
                file_path=metadata.get("source") or "Unknown",
                file_name=metadata.get("document_name") or "Unknown",
                page=metadata.get("page"),
                uid=metadata.get("document_uid") or "Unknown",
                modified=metadata.get("modified") or "Unknown",
                title=metadata.get("title") or "Unknown",
                author=metadata.get("author") or "Unknown",
                created=metadata.get("created") or "Unknown",
                type=metadata.get("category") or "document",
                score=score,
                rank=rank,
                embedding_model=str(metadata.get("embedding_model") or "unknown_model"),
                vector_index=metadata.get("vector_index") or "unknown_index",
                token_count=metadata.get("token_count") or None,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                retrieval_session_id=metadata.get("retrieval_session_id"),
            )
        except Exception as e:
            logger.warning("Failed to convert Document to DocumentSource. Error:", e, "Document:", doc.__dict__)
            raise e
