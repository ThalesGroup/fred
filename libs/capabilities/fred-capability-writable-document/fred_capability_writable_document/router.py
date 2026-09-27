# Copyright Thales 2026
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

"""The writable_document capability's own routes (#1905, RFC §9.1).

Auto-mounted by the pod under `/capabilities/writable_document` with the same
bearer the pod validates for `/agents/*`. The pod applies a global
`get_current_user` guard, but every handler ALSO binds the identity itself
(`Depends(get_current_user)`) and authorizes `row.user_id == user.uid` — a
document is only reachable by the chat user who owns its session (404 on missing,
403 on a foreign user). Typed request/response models so the per-capability
OpenAPI dump generates a fully-typed RTK Query slice.

The route `operation_id`s are stable and meaningful because they become the
generated frontend hook names (`listWritableDocuments`, `getWritableDocument`,
`updateWritableDocument`, `exportWritableDocument`).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel, Field

from fred_capability_writable_document.docx_export import markdown_to_docx_bytes
from fred_capability_writable_document.store import (
    WritableDocumentAuthor,
    WritableDocumentRecord,
    get_writable_document_store,
)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_MARKDOWN_MIME = "text/markdown"


class WritableDocumentExportFormat(str, Enum):
    """Supported export formats (future-proofed as an enum)."""

    docx = "docx"
    md = "md"


class WritableDocumentResponse(BaseModel):
    """Writable document as returned to the frontend."""

    session_id: str
    document_id: str
    title: str
    content_md: str
    updated_by: WritableDocumentAuthor
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_record(cls, record: WritableDocumentRecord) -> "WritableDocumentResponse":
        return cls(
            session_id=record.session_id,
            document_id=record.document_id,
            title=record.title,
            content_md=record.content_md,
            updated_by=record.updated_by,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class WritableDocumentUpdate(BaseModel):
    """Payload for a user edit of a writable document."""

    content_md: str
    title: Optional[str] = Field(default=None)


def _sanitize_filename(name: str) -> str:
    """Make a safe, non-empty ASCII-ish filename stem from a document title."""
    cleaned = re.sub(r"[^\w\-. ]+", "", name).strip().replace(" ", "_")
    return cleaned or "document"


async def _authorized_record(
    session_id: str, document_id: str, user: KeycloakUser
) -> WritableDocumentRecord:
    """Fetch one document and authorize the caller (404 missing / 403 foreign)."""
    record = await get_writable_document_store().get(session_id, document_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Writable document {document_id} not found for session {session_id}.",
        )
    if record.user_id != user.uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access this document.",
        )
    return record


def build_router() -> APIRouter:
    """Build the capability's APIRouter (no prefix — the pod mounts it under
    `/capabilities/writable_document`)."""

    router = APIRouter(tags=["Writable Documents"])

    @router.get(
        "/sessions/{session_id}/documents",
        response_model=List[WritableDocumentResponse],
        operation_id="listWritableDocuments",
        summary="List writable documents for a session",
    )
    async def list_writable_documents(
        session_id: str,
        user: KeycloakUser = Depends(get_current_user),
    ) -> List[WritableDocumentResponse]:
        records = await get_writable_document_store().list_for_session(session_id)
        # A session belongs to one user; still scope by user_id defensively.
        return [
            WritableDocumentResponse.from_record(r)
            for r in records
            if r.user_id == user.uid
        ]

    @router.get(
        "/sessions/{session_id}/documents/{document_id}",
        response_model=WritableDocumentResponse,
        operation_id="getWritableDocument",
        summary="Get a single writable document",
    )
    async def get_writable_document(
        session_id: str,
        document_id: str,
        user: KeycloakUser = Depends(get_current_user),
    ) -> WritableDocumentResponse:
        record = await _authorized_record(session_id, document_id, user)
        return WritableDocumentResponse.from_record(record)

    @router.put(
        "/sessions/{session_id}/documents/{document_id}",
        response_model=WritableDocumentResponse,
        operation_id="updateWritableDocument",
        summary="Update a writable document (user edit)",
    )
    async def update_writable_document(
        session_id: str,
        document_id: str,
        payload: WritableDocumentUpdate,
        user: KeycloakUser = Depends(get_current_user),
    ) -> WritableDocumentResponse:
        existing = await _authorized_record(session_id, document_id, user)
        # A user edit: mark authorship user, CLEAR agent_notified_at so the
        # middleware re-notifies the agent, preserve created_at (the store does).
        updated = await get_writable_document_store().upsert(
            WritableDocumentRecord(
                session_id=session_id,
                document_id=document_id,
                user_id=existing.user_id,
                title=payload.title if payload.title is not None else existing.title,
                content_md=payload.content_md,
                updated_by="user",
                agent_notified_at=None,
                created_at=existing.created_at,
            )
        )
        return WritableDocumentResponse.from_record(updated)

    @router.get(
        "/sessions/{session_id}/documents/{document_id}/export",
        operation_id="exportWritableDocument",
        summary="Export a writable document (Word .docx or Markdown)",
    )
    async def export_writable_document(
        session_id: str,
        document_id: str,
        format: WritableDocumentExportFormat = Query(WritableDocumentExportFormat.docx),
        user: KeycloakUser = Depends(get_current_user),
    ) -> StreamingResponse:
        record = await _authorized_record(session_id, document_id, user)

        if format is WritableDocumentExportFormat.md:
            # The document is stored as Markdown, so this is a passthrough.
            data = record.content_md.encode("utf-8")
            media_type = _MARKDOWN_MIME
        else:
            data = markdown_to_docx_bytes(record.content_md, title=record.title)
            media_type = _DOCX_MIME

        filename = f"{_sanitize_filename(record.title)}.{format.value}"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(iter([data]), media_type=media_type, headers=headers)

    return router
