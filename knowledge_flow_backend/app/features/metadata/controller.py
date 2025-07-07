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
from typing import Any, Dict
from fastapi import APIRouter, Body, HTTPException

from app.common.structures import Status
from app.core.stores.content.content_storage_factory import get_content_store
from app.features.metadata.service import InvalidMetadataRequest, MetadataNotFound, MetadataService, MetadataUpdateError
from app.features.metadata.structures import DeleteDocumentMetadataResponse, GetDocumentMetadataResponse, GetDocumentsMetadataResponse, UpdateDocumentMetadataRequest, UpdateDocumentMetadataResponse, UpdateRetrievableRequest
from threading import Lock

logger = logging.getLogger(__name__)

lock = Lock()

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

    def __init__(self, router: APIRouter):
        self.service = MetadataService()
        self.content_store = get_content_store()

        def handle_exception(e: Exception) -> HTTPException:
            if isinstance(e, MetadataNotFound):
                return HTTPException(status_code=404, detail=str(e))
            elif isinstance(e, InvalidMetadataRequest):
                return HTTPException(status_code=400, detail=str(e))
            elif isinstance(e, MetadataUpdateError):
                return HTTPException(status_code=500, detail=str(e))
            return HTTPException(status_code=500, detail="Internal server error")

        @router.post(
            "/documents/metadata",
            tags=["Metadata"],
            response_model=GetDocumentsMetadataResponse,
            summary="List document metadata, with optional filters. All documents if no filters are given.",
        )
        def get_documents_metadata(filters: Dict[str, Any] = Body(default={})):
            try:
                return self.service.get_documents_metadata(filters)
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/document/{document_uid}",
            tags=["Metadata"],
            response_model=GetDocumentMetadataResponse,
            summary="Get metadata for a specific document",
        )
        def get_document_metadata(document_uid: str):
            try:
                return self.service.get_document_metadata(document_uid)
            except Exception as e:
                raise handle_exception(e)

        @router.put(
            "/document/{document_uid}",
            tags=["Metadata"],
            response_model=UpdateDocumentMetadataResponse,
            summary="Update 'retrievable' field of a document",
        )
        def update_document_retrievable(document_uid: str, update: UpdateRetrievableRequest):
            try:
                return self.service.update_document_retrievable(document_uid, update)
            except Exception as e:
                raise handle_exception(e)

        @router.delete(
            "/document/{document_uid}",
            tags=["Metadata"],
            response_model=DeleteDocumentMetadataResponse,
            summary="Delete document metadata",
        )
        def delete_document_metadata(document_uid: str):
            try:
                with lock:
                    self.service.delete_document_metadata(document_uid)
                    self.content_store.delete_content(document_uid)
                    return DeleteDocumentMetadataResponse(
                        status=Status.SUCCESS,
                        message=f"Metadata for document {document_uid} has been deleted.",
                    )
            except Exception as e:
                logger.exception(f"Failed to delete document metadata: {e}")
                raise handle_exception(e)

        @router.post(
            "/document/{document_uid}/update_metadata",
            tags=["Metadata"],
            response_model=UpdateDocumentMetadataResponse,
            summary="Update multiple metadata fields for a document",
        )
        def update_document_metadata(document_uid: str, update: UpdateDocumentMetadataRequest):
            try:
                return self.service.update_document_metadata(
                    document_uid,
                    update.model_dump(exclude_none=True),
                )
            except Exception as e:
                logger.error(f"Failed to update metadata for {document_uid}: {e}")
                raise handle_exception(e)
