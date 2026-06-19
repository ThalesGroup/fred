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

from __future__ import annotations

import logging
import re
from datetime import datetime
from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user
from pydantic import BaseModel, Field

from agentic_backend.core.chatbot.chatbot_controller import get_session_orchestrator
from agentic_backend.core.chatbot.session_orchestrator import SessionOrchestrator
from agentic_backend.core.session.stores.base_writable_document_store import (
    WritableDocumentAuthor,
    WritableDocumentNotFoundError,
    WritableDocumentRecord,
    WritableDocumentsDisabledError,
)
from agentic_backend.core.writable_documents.docx_export import markdown_to_docx_bytes

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Writable Documents"])

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


def _map_store_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, WritableDocumentsDisabledError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Writable documents are not enabled.",
        )
    if isinstance(exc, WritableDocumentNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    raise exc


@router.get(
    "/writable-documents/{session_id}",
    response_model=List[WritableDocumentResponse],
    summary="List writable documents for a session",
)
async def list_writable_documents(
    session_id: str,
    user: KeycloakUser = Depends(get_current_user),
    orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> List[WritableDocumentResponse]:
    try:
        records = await orchestrator.list_writable_documents(session_id, user)
    except (WritableDocumentsDisabledError, WritableDocumentNotFoundError) as exc:
        raise _map_store_errors(exc)
    return [WritableDocumentResponse.from_record(r) for r in records]


@router.get(
    "/writable-documents/{session_id}/{document_id}",
    response_model=WritableDocumentResponse,
    summary="Get a single writable document",
)
async def get_writable_document(
    session_id: str,
    document_id: str,
    user: KeycloakUser = Depends(get_current_user),
    orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> WritableDocumentResponse:
    try:
        record = await orchestrator.get_writable_document(session_id, document_id, user)
    except (WritableDocumentsDisabledError, WritableDocumentNotFoundError) as exc:
        raise _map_store_errors(exc)
    return WritableDocumentResponse.from_record(record)


@router.put(
    "/writable-documents/{session_id}/{document_id}",
    response_model=WritableDocumentResponse,
    summary="Update a writable document (user edit)",
)
async def update_writable_document(
    session_id: str,
    document_id: str,
    payload: WritableDocumentUpdate,
    user: KeycloakUser = Depends(get_current_user),
    orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> WritableDocumentResponse:
    try:
        record = await orchestrator.update_user_writable_document(
            session_id=session_id,
            document_id=document_id,
            user=user,
            content_md=payload.content_md,
            title=payload.title,
        )
    except (WritableDocumentsDisabledError, WritableDocumentNotFoundError) as exc:
        raise _map_store_errors(exc)
    return WritableDocumentResponse.from_record(record)


@router.get(
    "/writable-documents/{session_id}/{document_id}/export",
    summary="Export a writable document (Word .docx or Markdown)",
)
async def export_writable_document(
    session_id: str,
    document_id: str,
    format: WritableDocumentExportFormat = Query(WritableDocumentExportFormat.docx),
    user: KeycloakUser = Depends(get_current_user),
    orchestrator: SessionOrchestrator = Depends(get_session_orchestrator),
) -> StreamingResponse:
    try:
        record = await orchestrator.get_writable_document(session_id, document_id, user)
    except (WritableDocumentsDisabledError, WritableDocumentNotFoundError) as exc:
        raise _map_store_errors(exc)

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
