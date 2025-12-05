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
from threading import Lock
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.document_structures import DocumentMetadata, ProcessingGraph, ProcessingSummary
from knowledge_flow_backend.common.utils import log_exception
from knowledge_flow_backend.features.metadata.service import InvalidMetadataRequest, MetadataNotFound, MetadataService, MetadataUpdateError, StoreAuditFixResponse, StoreAuditReport
from knowledge_flow_backend.features.pull.controller import PullDocumentsResponse
from knowledge_flow_backend.features.pull.service import PullDocumentService


class SortOption(BaseModel):
    field: str
    direction: Literal["asc", "desc"]


logger = logging.getLogger(__name__)

lock = Lock()


class BrowseDocumentsRequest(BaseModel):
    source_tag: str = Field(..., description="Tag of the document source to browse (pull or push)")
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata filters")
    offset: int = Field(0, ge=0)
    limit: int = Field(50, gt=0, le=500)
    sort_by: Optional[List[SortOption]] = None


def handle_exception(e: Exception) -> HTTPException | Exception:
    if isinstance(e, MetadataNotFound):
        return HTTPException(status_code=404, detail=str(e))
    elif isinstance(e, InvalidMetadataRequest):
        return HTTPException(status_code=400, detail=str(e))
    elif isinstance(e, MetadataUpdateError):
        return e  # Will be handled by generic_exception_handler as 500

    return e


class MetadataController:
    """
    Controller responsible for exposing CRUD operations on document metadata.

    This controller is central to the management of structured metadata associated
    with ingested documents. Metadata supports multiple use cases including:
      - User-facing previews and descriptive content (e.g., title, description)
      - Access control (via future integration with tags and user/project ownership)
      - Feature toggling (e.g., `retrievable` flag for filtering indexed documents)
      - Domain-based filtering or annotation for downstream agents

    Features:
    ---------
    - Retrieve metadata for one or many documents
    - Update selective metadata fields (title, description, domain, tags)
    - Toggle a document’s `retrievable` status (used by vector search filters)
    - Delete metadata and optionally the associated raw content

    Forward-looking Design:
    -----------------------
    While this controller supports basic metadata management, a **tag-driven metadata
    model** is emerging as the long-term foundation for:
      - enforcing fine-grained access control
      - enabling project/user scoping
      - querying and filtering documents across different controllers (e.g., vector search, tabular)

    Therefore, this controller **may evolve** to rely on normalized tag-based metadata
    and decouple fixed field updates from dynamic metadata structures (author, source, etc.).

    Notes for developers:
    ---------------------
    - The `update_metadata` endpoint accepts arbitrary subsets of metadata fields.
    - The current metadata model allows extensibility (value type: `Dict[str, Any]`)
    - All business exceptions are wrapped and exposed as HTTP errors only in the controller.
    """

    def __init__(self, router: APIRouter, pull_document_service: PullDocumentService):
        self.context = ApplicationContext.get_instance()
        self.service = MetadataService()
        self.content_store = ApplicationContext.get_instance().get_content_store()
        self.pull_document_service = pull_document_service

        # ---- Schemas locaux pour les réponses ----
        class VectorChunk(BaseModel):
            chunk_uid: str = Field(..., description="Identifiant unique du chunk")
            vector: List[float] = Field(..., description="Embedding du chunk")

        @router.post(
            "/documents/metadata/search",
            tags=["Documents"],
            response_model=List[DocumentMetadata],
            summary="List metadata for all ingested documents (optional filters)",
            description=(
                "Returns metadata for all ingested documents in the knowledge base. "
                "You can optionally filter by metadata fields such as tags, title, source_tag, or retrievability.\n\n"
                "**Note:** Only ingested documents have persisted metadata. "
                "Discovered files (e.g., in pull-mode) are not returned by this endpoint — see `/documents/pull`."
            ),
        )
        async def search_document_metadata(filters: Dict[str, Any] = Body(default={}), user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.get_documents_metadata(user, filters)
            except Exception as e:
                log_exception(e)
                raise handle_exception(e)

        @router.get(
            "/documents/metadata/{document_uid}",
            tags=["Documents"],
            response_model=DocumentMetadata,
            summary="Fetch metadata for an ingested document",
            description=(
                "Returns full metadata for a document that has already been ingested, either via push or pull. "
                "This endpoint does not support transient/discovered documents that haven't been ingested yet. "
                "Use `/documents/pull` to inspect discovered-but-unprocessed files."
            ),
        )
        async def get_document_metadata(document_uid: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.get_document_metadata(user, document_uid)
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/documents/processing/graph",
            tags=["Documents"],
            response_model=ProcessingGraph,
            summary="Get processing graph for all documents",
            description=(
                "Returns a lightweight graph describing how ingested documents relate to downstream artifacts "
                "(per-document vector indexes and SQL tables). The graph is expressed as nodes and edges that can "
                "be consumed directly by the UI for visualization."
            ),
        )
        async def get_processing_graph(user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.get_processing_graph(user)
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/documents/processing/summary",
            tags=["Documents"],
            response_model=ProcessingSummary,
            summary="Get consolidated processing status for all documents",
            description=(
                "Returns an aggregate view of processing status across all documents visible to the current user, including counts of fully processed, in-progress, failed, and not-started documents."
            ),
        )
        async def get_processing_summary(user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.get_processing_summary(user)
            except Exception as e:
                raise handle_exception(e)

        @router.put(
            "/document/metadata/{document_uid}",
            tags=["Documents"],
            response_model=None,
            summary="Toggle document retrievability (indexed for search)",
            description=(
                "Updates the `retrievable` flag for an ingested document. "
                "This affects whether the document is considered by vector search and agent responses.\n\n"
                "This endpoint applies only to ingested documents. For discovered files not yet ingested, "
                "the flag has no effect."
            ),
        )
        async def update_document_metadata_retrievable(
            document_uid: str,
            retrievable: bool,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                await self.service.update_document_retrievable(user, document_uid, retrievable, user.uid)
            except Exception as e:
                raise handle_exception(e)

        @router.post(
            "/documents/browse",
            tags=["Documents"],
            summary="Unified endpoint to browse documents from any source (push or pull)",
            response_model=PullDocumentsResponse,
            description="""
            Returns a paginated list of documents from any configured source.

            - If the source is **push**, returns metadata for ingested documents (with filters).
            - If the source is **pull**, returns both ingested and discovered-but-not-ingested documents.
            - Supports optional filtering and pagination.

            **Example filters:** `tags`, `retrievable`, `title`, etc.
            """,
        )
        async def browse_documents(req: BrowseDocumentsRequest, user: KeycloakUser = Depends(get_current_user)):
            config = self.context.get_config().document_sources.get(req.source_tag)
            if not config:
                raise HTTPException(status_code=404, detail=f"Source tag '{req.source_tag}' not found")

            if config.type == "push":
                filters = req.filters or {}
                filters["source"] = {"source_tag": req.source_tag}
                docs = await self.service.get_documents_metadata(user, filters)
                sort_by = req.sort_by or [SortOption(field="document_name", direction="asc")]

                for sort in reversed(sort_by):  # Apply last sort first for correct multi-field sorting
                    docs.sort(
                        key=lambda d: getattr(d, sort.field, "") or "",  # fallback to empty string
                        reverse=(sort.direction == "desc"),
                    )

                paginated = docs[req.offset : req.offset + req.limit]
                return PullDocumentsResponse(documents=paginated, total=len(docs))

            elif config.type == "pull":
                docs, total = self.pull_document_service.list_pull_documents(user, source_tag=req.source_tag, offset=req.offset, limit=req.limit)
                # You could apply extra filtering here if needed
                return PullDocumentsResponse(documents=docs, total=total)

            else:
                raise HTTPException(status_code=400, detail=f"Unsupported source type '{config.type}'")

        @router.get(
            "/documents/{document_uid}/vectors",
            tags=["Documents"],
            summary="Get document chunk vectors (embeddings)",
            description="Returns the list of chunk vectors (embeddings) associated with the given document.",
            response_model=List[VectorChunk],
        )
        async def document_vectors(
            document_uid: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                raw = await self.service.get_document_vectors(user, document_uid)
                return [VectorChunk(**item) for item in raw]
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/documents/{document_uid}/chunks",
            tags=["Documents"],
            summary="Get document chunks with metadata",
            description="Returns the list of chunks associated with the given document, including their metadata.",
            response_model=List[Dict[str, Any]],
        )
        async def document_chunks(
            document_uid: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                chunks = await self.service.get_document_chunks(user, document_uid)
                return chunks
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/documents/audit",
            tags=["Documents"],
            summary="Audit metadata/content/vector stores for orphan or partial data",
            response_model=StoreAuditReport,
            description="Scans the metadata, content, and vector stores to surface inconsistencies (orphan vectors/content or partially deleted documents).",
        )
        async def audit_documents(user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.audit_stores(user)
            except Exception as e:
                log_exception(e)
                raise handle_exception(e)

        @router.post(
            "/documents/audit/fix",
            tags=["Documents"],
            summary="Delete orphan or partial document data across stores",
            response_model=StoreAuditFixResponse,
            description="Runs the audit and deletes any orphan data to keep metadata, content, and vector stores in sync.",
        )
        async def fix_documents(user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.fix_store_anomalies(user)
            except Exception as e:
                log_exception(e)
                raise handle_exception(e)

        @router.get(
            "/documents/{document_uid}/chunks/{chunk_id}",
            tags=["Documents"],
            summary="Get chunk with metadata",
            description="Returns the chunk, including their metadata.",
            response_model=Dict[str, Any],
        )
        async def get_chunk(
            document_uid: str,
            chunk_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                chunk = await self.service.get_chunk(user, document_uid, chunk_id)
                return chunk
            except Exception as e:
                raise handle_exception(e)

        @router.delete(
            "/documents/{document_uid}/chunks/{chunk_id}",
            tags=["Documents"],
            summary="Delete chunk",
            description="Delete the chunk",
            status_code=200
        )
        async def delete_chunk(
            document_uid: str,
            chunk_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                await self.service.delete_chunk(user, document_uid, chunk_id)
            except Exception as e:
                raise handle_exception(e)
