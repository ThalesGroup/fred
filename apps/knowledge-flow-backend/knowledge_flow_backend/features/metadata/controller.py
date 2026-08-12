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
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException
from fred_core import KeycloakUser, get_current_user
from fred_core.documents.document_structures import DocumentMetadata
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.utils import log_exception
from knowledge_flow_backend.features.metadata.service import (
    DocumentNameCollisionError,
    InvalidMetadataRequest,
    MetadataNotFound,
    MetadataService,
    MetadataUpdateError,
    StoreAuditFixResponse,
    StoreAuditReport,
)


class BrowseDocumentsResponse(BaseModel):
    total: int
    documents: List[DocumentMetadata]


logger = logging.getLogger(__name__)

lock = Lock()


class BrowseDocumentsByTagRequest(BaseModel):
    tag_id: str = Field(..., description="Library tag identifier")
    offset: int = Field(0, ge=0)
    limit: int = Field(50, gt=0, le=500)


class TagSizesRequest(BaseModel):
    tag_ids: List[str] = Field(..., description="Library tag identifiers to total")


class TagSizesResponse(BaseModel):
    sizes: Dict[str, int] = Field(..., description="Total document bytes per requested tag id (0 when unknown/empty)")


class LabelMutationRequest(BaseModel):
    """Canonical transport for a label add/remove batch. Replaces the label as
    a raw URL path segment (`POST/DELETE /documents/{uid}/labels/{label}`,
    still available for existing consumers — see their descriptions), which
    cannot carry `/`, `#`, `?`, a literal `%`, or reliably round-trip through
    every client's URL handling. A JSON body has none of those limits."""

    add: List[str] = Field(default_factory=list, description="Labels to add.")
    remove: List[str] = Field(default_factory=list, description="Labels to remove. Wins over `add` when the same value appears in both.")


def handle_exception(e: Exception) -> HTTPException | Exception:
    if isinstance(e, MetadataNotFound):
        return HTTPException(status_code=404, detail=str(e))
    elif isinstance(e, InvalidMetadataRequest):
        return HTTPException(status_code=400, detail=str(e))
    elif isinstance(e, DocumentNameCollisionError):
        return HTTPException(status_code=409, detail=str(e))
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

    def __init__(self, router: APIRouter):
        self.context = ApplicationContext.get_instance()
        self.service = MetadataService()
        self.content_store = ApplicationContext.get_instance().get_content_store()

        # ---- Local schemas for responses ----
        class VectorChunk(BaseModel):
            chunk_uid: str = Field(..., description="Unique identifier of the chunk")
            vector: List[float] = Field(..., description="Chunk embedding")

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

        @router.put(
            "/document/metadata/{document_uid}/title",
            tags=["Documents"],
            response_model=None,
            summary="Rename a document (display title)",
            description=("Updates the browser-display title for an ingested document. Cosmetic only: citations and vector search keep referencing the original ingested file name."),
        )
        async def update_document_metadata_title(
            document_uid: str,
            title: str = Body(..., embed=True),
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                await self.service.update_document_title(user, document_uid, title, user.uid)
            except Exception as e:
                raise handle_exception(e)

        @router.put(
            "/document/metadata/{document_uid}/name",
            tags=["Documents"],
            response_model=DocumentMetadata,
            response_model_exclude_none=True,
            summary="Rename a document (real file name)",
            description=(
                "Updates the document's actual file name (`identity.document_name`), not just its "
                "display title. Propagates to the vector index's copy of the name on each chunk "
                "(best-effort — never fails the request) and to the content-store filename lookup. "
                "Does not change `document_uid`, storage keys, or embeddings, and does not touch "
                "existing chat/session citations, which keep referencing the name at the time they "
                "were created. The extension cannot be changed by a rename."
            ),
        )
        async def rename_document(
            document_uid: str,
            name: str = Body(..., embed=True),
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                return await self.service.rename_document(user, document_uid, name, user.uid)
            except Exception as e:
                raise handle_exception(e)

        @router.post(
            "/documents/metadata/browse",
            tags=["Documents"],
            summary="Paginated documents by library tag",
            response_model=BrowseDocumentsResponse,
            description="Returns documents for a library tag with pagination support.",
        )
        async def browse_documents_by_tag(req: BrowseDocumentsByTagRequest, user: KeycloakUser = Depends(get_current_user)):
            docs, total = await self.service.browse_documents_in_tag(user, tag_id=req.tag_id, offset=req.offset, limit=req.limit)
            logger.info(
                "[PAGINATION] browse_documents_by_tag tag=%s offset=%s limit=%s returned=%s total=%s",
                req.tag_id,
                req.offset,
                req.limit,
                len(docs),
                total,
            )
            return BrowseDocumentsResponse(documents=docs, total=total)

        @router.post(
            "/documents/metadata/tag-sizes",
            tags=["Documents"],
            summary="Total document bytes per library tag",
            response_model=TagSizesResponse,
            description=(
                "Returns the summed original file size (bytes) of all documents in each "
                "requested library tag. Reliable and independent of pagination — used to "
                "show a folder's total size while it is collapsed."
            ),
        )
        async def tag_sizes(req: TagSizesRequest, user: KeycloakUser = Depends(get_current_user)):
            sizes = await self.service.total_size_by_tags(user, req.tag_ids)
            return TagSizesResponse(sizes=sizes)

        # === Business labels (descriptive) ====================================
        # Labels describe documents (e.g. 'DAT', 'MEX') with NO scope/permission
        # meaning; mirrors the tag add/remove shape but without any ReBAC on the
        # label. Used to target search subsets.
        @router.patch(
            "/documents/{document_uid}/labels",
            tags=["Documents"],
            operation_id="mutate_document_labels",
            response_model=list[str],
            summary="Add and/or remove descriptive business labels on a document",
            description=(
                "Canonical label transport: a JSON body carrying the labels to add and/or remove in one "
                "request, in place of a raw URL path segment (see the deprecated single-label "
                "POST/DELETE routes below). Supports any Unicode text, including characters a URL path "
                "segment cannot carry reliably ('/', '#', '?', '%'). A value present in both `add` and "
                "`remove` ends up absent (`remove` wins). Idempotent: re-adding an already-present label "
                "or re-removing an absent one is a no-op, and an empty request returns the current set "
                "unchanged. Returns the document's full, canonical stored label set."
            ),
        )
        async def mutate_document_labels(document_uid: str, req: LabelMutationRequest, user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.mutate_document_labels(user, document_uid, add=req.add, remove=req.remove, modified_by=user.uid)
            except Exception as e:
                raise handle_exception(e)

        @router.post(
            "/documents/{document_uid}/labels/{label}",
            tags=["Documents"],
            operation_id="add_document_label",
            response_model=list[str],
            deprecated=True,
            summary="Add a descriptive business label to a document",
            description=(
                "Deprecated: use PATCH /documents/{document_uid}/labels instead — this route places "
                "the label as a raw URL path segment, which cannot carry '/', '#', '?', or a literal "
                "'%' reliably. Kept only for existing consumers that already send labels this route can "
                "transport; it is a thin adapter onto the same MetadataService.mutate_document_labels "
                "used by the PATCH route, not a second mutation implementation. Removal condition: once "
                "no known consumer calls this route directly (frontend already migrated off it)."
            ),
        )
        async def add_document_label(document_uid: str, label: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.add_label_to_document(user, document_uid, label, user.uid)
            except Exception as e:
                raise handle_exception(e)

        @router.delete(
            "/documents/{document_uid}/labels/{label}",
            tags=["Documents"],
            operation_id="remove_document_label",
            response_model=list[str],
            deprecated=True,
            summary="Remove a descriptive business label from a document",
            description=(
                "Deprecated: use PATCH /documents/{document_uid}/labels instead — same reasoning and "
                "removal condition as the deprecated POST route above. A thin adapter onto "
                "MetadataService.mutate_document_labels, not a second mutation implementation."
            ),
        )
        async def remove_document_label(document_uid: str, label: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.remove_label_from_document(user, document_uid, label, user.uid)
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/documents/labels",
            tags=["Documents"],
            operation_id="list_document_labels",
            response_model=list[str],
            summary="List the distinct business labels in use",
            description="Returns the distinct descriptive labels across the documents the user can read.",
        )
        async def list_document_labels(user: KeycloakUser = Depends(get_current_user)):
            try:
                return await self.service.list_document_labels(user)
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/documents/by-label/{label}",
            tags=["Documents"],
            operation_id="list_documents_by_label",
            response_model=BrowseDocumentsResponse,
            summary="List documents carrying a business label",
            description=(
                "Resolves a label to the readable documents carrying it (search resolve-then-target). The label "
                "rides as a raw URL path segment here, so it cannot reliably carry '/', '#', '?', a literal '%', "
                "or arbitrary Unicode — use GET /documents/by-label (query parameter) for those. Kept unchanged "
                "for existing consumers; both routes resolve through the same MetadataService.get_documents_with_label."
            ),
        )
        async def list_documents_by_label(label: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                docs = await self.service.get_documents_with_label(user, label)
                return BrowseDocumentsResponse(documents=docs, total=len(docs))
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/documents/by-label",
            tags=["Documents"],
            operation_id="resolve_documents_by_label",
            response_model=BrowseDocumentsResponse,
            summary="List documents carrying a business label (query parameter transport)",
            description=(
                "Canonical label resolution: the label rides as a query parameter, so it carries any Unicode "
                "text with no character restriction — symmetric with the PATCH /documents/{document_uid}/labels "
                "mutation transport. Resolves through the same MetadataService.get_documents_with_label as the "
                "path-segment GET /documents/by-label/{label} route above (kept for existing consumers), not a "
                "second lookup implementation."
            ),
        )
        async def resolve_documents_by_label(label: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                docs = await self.service.get_documents_with_label(user, label)
                return BrowseDocumentsResponse(documents=docs, total=len(docs))
            except Exception as e:
                raise handle_exception(e)

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

        @router.delete("/documents/{document_uid}/chunks/{chunk_id}", tags=["Documents"], summary="Delete chunk", description="Delete the chunk", status_code=200)
        async def delete_chunk(
            document_uid: str,
            chunk_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            try:
                await self.service.delete_chunk(user, document_uid, chunk_id)
            except Exception as e:
                raise handle_exception(e)
