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
from typing import Any, Dict, Optional

from fred_core import KeycloakUser, get_current_user
from app.common.utils import log_exception
from app.features.pull.controller import PullDocumentsResponse
from app.features.pull.service import PullDocumentService
from fastapi import APIRouter, Body, Depends, HTTPException

from app.common.structures import Status
from app.application_context import ApplicationContext
from app.features.metadata.service import InvalidMetadataRequest, MetadataNotFound, MetadataService, MetadataUpdateError
from app.features.metadata.structures import (
    GetDocumentMetadataResponse,
    GetDocumentsMetadataResponse,
    UpdateDocumentMetadataResponse,
    UpdateRetrievableRequest,
)
from threading import Lock

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

lock = Lock()


class BrowseDocumentsRequest(BaseModel):
    source_tag: str = Field(..., description="Tag of the document source to browse (pull or push)")
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata filters")
    offset: int = Field(0, ge=0)
    limit: int = Field(50, gt=0, le=500)


def handle_exception(e: Exception) -> HTTPException:
    if isinstance(e, MetadataNotFound):
        return HTTPException(status_code=404, detail=str(e))
    elif isinstance(e, InvalidMetadataRequest):
        return HTTPException(status_code=400, detail=str(e))
    elif isinstance(e, MetadataUpdateError):
        return HTTPException(status_code=500, detail=str(e))
    return HTTPException(status_code=500, detail="Internal server error")


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

        @router.post(
            "/documents/metadata",
            tags=["Documents"],
            response_model=GetDocumentsMetadataResponse,
            summary="List metadata for all ingested documents (optional filters)",
            description=(
                "Returns metadata for all ingested documents in the knowledge base. "
                "You can optionally filter by metadata fields such as tags, title, source_tag, or retrievability.\n\n"
                "**Note:** Only ingested documents have persisted metadata. "
                "Discovered files (e.g., in pull-mode) are not returned by this endpoint — see `/documents/pull`."
            ),
        )
        def get_documents_metadata(filters: Dict[str, Any] = Body(default={})):
            try:
                push_docs = self.service.get_documents_metadata(filters)
                return GetDocumentsMetadataResponse(status=Status.SUCCESS, documents=push_docs)
            except Exception as e:
                log_exception(e)
                raise handle_exception(e)

        @router.get(
            "/document/{document_uid}",
            tags=["Documents"],
            response_model=GetDocumentMetadataResponse,
            summary="Fetch metadata for an ingested document",
            description=(
                "Returns full metadata for a document that has already been ingested, either via push or pull. "
                "This endpoint does not support transient/discovered documents that haven't been ingested yet. "
                "Use `/documents/pull` to inspect discovered-but-unprocessed files."
            ),
        )
        def get_document_metadata(document_uid: str):
            try:
                metadata = self.service.get_document_metadata(document_uid)
                return GetDocumentMetadataResponse(status=Status.SUCCESS, metadata=metadata)
            except Exception as e:
                raise handle_exception(e)

        @router.put(
            "/document/{document_uid}",
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
        def update_document_retrievable(document_uid: str, update: UpdateRetrievableRequest, user: KeycloakUser = Depends(get_current_user),):
            try:
                self.service.update_document_retrievable(document_uid, update.retrievable, user.username)
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
        def browse_documents(req: BrowseDocumentsRequest):
            config = self.context.get_config().document_sources.get(req.source_tag)
            if not config:
                raise HTTPException(status_code=404, detail=f"Source tag '{req.source_tag}' not found")

            try:
                if config.type == "push":
                    filters = req.filters or {}
                    filters["source_tag"] = req.source_tag
                    docs = self.service.get_documents_metadata(filters)
                    paginated = docs[req.offset : req.offset + req.limit]
                    return PullDocumentsResponse(documents=paginated, total=len(docs))

                elif config.type == "pull":
                    docs, total = self.pull_document_service.list_pull_documents(source_tag=req.source_tag, offset=req.offset, limit=req.limit)
                    # You could apply extra filtering here if needed
                    return PullDocumentsResponse(documents=docs, total=total)

                else:
                    raise HTTPException(status_code=400, detail=f"Unsupported source type '{config.type}'")

            except Exception as e:
                log_exception(e, "An unexpected error occurred while rbrowsing document")
                raise HTTPException(status_code=500, detail="Internal server error")
