# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fred_core.documents.access import SpaceNotFoundError, SpacePendingDeletionError
from fred_core.documents.transport import DocumentAccessContext
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.features.document_scope import document_access_context
from knowledge_flow_backend.features.document_tree.service import DocumentTreeService
from knowledge_flow_backend.features.document_tree.structures import DocumentTreeResponse
from knowledge_flow_backend.security.weaver_admission import _space_error, delegated_person, require_space_read


class DocumentTreeController:
    def __init__(self, router: APIRouter):
        self.service = DocumentTreeService()

        @router.get(
            "/documents/tree",
            tags=["Vector Search"],
            operation_id="list_document_tree",
            summary="List visible corpus folders and documents",
            description="Returns structured spaces, folders and visible published documents in the authorized context space and ancestors, intersected with the context selection. Conversation attachments are excluded. folder_id starts at an in-scope folder; absent means root. Folder and document records together are capped by limit (default 1000, maximum 5000), ordered by space, folder ID path and name, with IDs breaking ties. Ancestor folders provide structure only, never permission to read their other contents. An empty result means no visible entries in this selection. truncated=true reports omitted records and does not establish completeness; there is no continuation token. This is not an existence oracle: an unavailable or out-of-scope folder returns the same 404 folder_not_found.",
            response_model=DocumentTreeResponse,
        )
        async def list_document_tree(
            folder_id: UUID | None = None,
            limit: int = Query(default=1000, ge=1, le=5000),
            context: DocumentAccessContext = Depends(document_access_context),
            person: AssertedUser = Depends(delegated_person),
        ) -> DocumentTreeResponse:
            authorized_space_ids = await require_space_read(person, context.space_id)
            try:
                return await self.service.tree(context=context, user_id=person.uid, authorized_space_ids=authorized_space_ids, folder_id=folder_id, limit=limit)
            except (SpaceNotFoundError, SpacePendingDeletionError) as exc:
                raise _space_error(exc) from None
