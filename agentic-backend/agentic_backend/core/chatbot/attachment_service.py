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
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import httpx
from fastapi import HTTPException, UploadFile
from fred_core import KeycloakUser

from agentic_backend.common.kf_fast_text_client import KfFastTextClient
from agentic_backend.core.chatbot.chat_schema import SessionSchema
from agentic_backend.core.session.session_cache import CachedSession, SessionCache
from agentic_backend.core.session.stores.base_session_attachment_store import (
    BaseSessionAttachmentStore,
    SessionAttachmentRecord,
)
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore

logger = logging.getLogger(__name__)


def _utcnow_dt() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _request_error_detail(exc: httpx.RequestError) -> str:
    detail = str(exc).strip()
    if detail:
        return detail
    request = getattr(exc, "request", None)
    method = getattr(request, "method", None)
    url = str(getattr(request, "url", "")) if request is not None else ""
    exc_type = type(exc).__name__
    if method and url:
        return f"{exc_type} on {method} {url}"
    if url:
        return f"{exc_type} on {url}"
    return exc_type


def _extract_http_error_detail(exc: httpx.HTTPStatusError) -> object:
    """
    Relay upstream KF error payload as-is when possible.

    Priority:
    1) JSON payload's `detail` field when present
    2) Full JSON payload
    3) Raw response text
    4) Exception string fallback
    """
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)

    try:
        payload = response.json()
        if isinstance(payload, dict) and "detail" in payload:
            return payload["detail"]
        return payload
    except Exception:
        text = (response.text or "").strip()
        return text or str(exc)


class AttachmentService:
    """
    Dedicated service for chat attachment ingestion and persistence.

    Keeps SessionOrchestrator focused on chat orchestration while preserving
    the existing attachment behavior and API contract.
    """

    def __init__(
        self,
        *,
        session_store: BaseSessionStore,
        attachments_store: Optional[BaseSessionAttachmentStore],
        session_cache: SessionCache,
        create_empty_session: Callable[[KeycloakUser], Awaitable[SessionSchema]],
        get_session: Callable[[str, str], Awaitable[SessionSchema]],
        max_attached_files_per_user: Optional[int],
        max_attached_file_size_mb: Optional[int],
        max_attached_file_size_bytes: Optional[int],
    ) -> None:
        self.session_store = session_store
        self.attachments_store = attachments_store
        self.session_cache = session_cache
        self.create_empty_session = create_empty_session
        self.get_session = get_session
        self.max_attached_files_per_user = max_attached_files_per_user
        self.max_attached_file_size_mb = max_attached_file_size_mb
        self.max_attached_file_size_bytes = max_attached_file_size_bytes

    async def add_attachment_from_upload(
        self,
        *,
        user: KeycloakUser,
        access_token: str,
        session_id: Optional[str],
        file: UploadFile,
        max_chars: int = 12_000,
        include_tables: bool = True,
        add_page_headings: bool = False,
    ) -> dict:
        if not self.attachments_store:
            logger.error(
                "[SESSIONS][ATTACH] Attachment uploads disabled: no attachments_store configured."
            )
            raise HTTPException(
                status_code=501,
                detail={
                    "code": "attachments_disabled",
                    "message": "Attachment uploads are disabled (no attachment store configured).",
                },
            )

        # Enforce per-user attachment count limit.
        max_files_user = self.max_attached_files_per_user
        try:
            if max_files_user is not None and self.attachments_store:
                total_for_user = 0
                user_sessions = await self.session_store.get_for_user(user.uid)
                if user_sessions:
                    session_ids = [s.id for s in user_sessions]
                    total_for_user = await self.attachments_store.count_for_sessions(
                        session_ids
                    )

                if total_for_user >= max_files_user:
                    logger.warning(
                        "[SESSIONS][ATTACH] User %s has %d attachments, exceeding limit of %d",
                        user.uid,
                        total_for_user,
                        max_files_user,
                    )
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "code": "attachment_limit_reached",
                            "message": f"Attachment limit reached ({max_files_user} files per user).",
                        },
                    )
        except HTTPException:
            raise
        except Exception:
            logger.exception("[SESSIONS][ATTACH] Failed to enforce attachment limit")

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "missing_filename",
                    "message": "Uploaded file must have a filename.",
                },
            )

        size_limit_bytes = self.max_attached_file_size_bytes
        if size_limit_bytes is not None:
            content = await file.read(size_limit_bytes + 1)
            if len(content) > size_limit_bytes:
                logger.warning(
                    "[SESSIONS][ATTACH] File too large: %s bytes=%d limit=%d (user=%s)",
                    file.filename,
                    len(content),
                    size_limit_bytes,
                    user.uid,
                )
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "attachment_too_large",
                        "message": f"Attachment exceeds limit ({self.max_attached_file_size_mb} MB).",
                    },
                )
        else:
            content = await file.read()

        # If no session_id was provided (first interaction), create one now.
        if not session_id:
            session = await self.create_empty_session(user)
        else:
            session = await self.get_session(user.uid, session_id)

        # Prevent duplicate filenames within a session.
        try:
            if self.attachments_store:
                existing = await self.attachments_store.list_for_session(
                    session_id=session.id
                )
                if any(rec.name == file.filename for rec in existing):
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "attachment_duplicate",
                            "message": f"Attachment '{file.filename}' already exists in this session.",
                        },
                    )
        except HTTPException:
            raise
        except Exception:
            logger.exception(
                "[SESSIONS][ATTACH] Failed during duplicate attachment check"
            )

        client = KfFastTextClient(access_token=access_token)

        attachment_id = str(uuid.uuid4())

        # Single call: ingest vectors and get compact summary in the same response.
        summary_md = "_(No summary returned by Knowledge Flow)_"
        document_uid: Optional[str] = None
        try:
            ingest_resp = await client.ingest_text_from_bytes(
                filename=file.filename,
                content=content,
                session_id=session.id,
                scope="session",
                options={
                    "max_chars": None,
                    "include_tables": include_tables,
                    "add_page_headings": add_page_headings,
                    "return_per_page": True,
                    "include_summary": True,
                    "summary_max_chars": max_chars,
                },
            )
            document_uid = ingest_resp.get("document_uid")
            summary_md = (ingest_resp.get("summary_md") or "").strip()
            if "\x00" in summary_md:
                summary_md = summary_md.replace("\x00", "")
            if not summary_md:
                summary_md = "_(No summary returned by Knowledge Flow)_"
            logger.info(
                "[SESSIONS][ATTACH] Received summary + ingested vectors for %s bytes=%d chars=%d doc_uid=%s chunks=%s",
                file.filename,
                len(content),
                len(summary_md),
                document_uid,
                ingest_resp.get("chunks"),
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 502
            upstream_detail = _extract_http_error_detail(exc)
            logger.error(
                "Knowledge Flow rejected fast ingest for attachment %s (user=%s, status=%s, detail=%s)",
                file.filename,
                user.uid,
                status,
                upstream_detail,
            )
            raise HTTPException(status_code=status, detail=upstream_detail) from exc
        except httpx.ReadTimeout as exc:
            detail = _request_error_detail(exc)
            logger.error(
                "Knowledge Flow timeout during fast ingest %s (user=%s): %s",
                file.filename,
                user.uid,
                detail,
            )
            raise HTTPException(status_code=504, detail=detail) from exc
        except httpx.RequestError as exc:
            detail = _request_error_detail(exc)
            logger.error(
                "Knowledge Flow unreachable during fast ingest %s (user=%s): %s",
                file.filename,
                user.uid,
                detail,
            )
            raise HTTPException(status_code=502, detail=detail) from exc
        except Exception as exc:
            logger.exception(
                "[SESSIONS][ATTACH] Unexpected error during fast ingest for %s",
                file.filename,
            )
            raise HTTPException(status_code=500, detail=str(exc))

        # Persist metadata for UI.
        if self.attachments_store:
            now = _utcnow_dt()
            try:
                record = SessionAttachmentRecord(
                    session_id=session.id,
                    attachment_id=attachment_id,
                    name=file.filename,
                    summary_md=summary_md,
                    mime=file.content_type,
                    size_bytes=len(content),
                    document_uid=document_uid,
                    created_at=now,
                    updated_at=now,
                )
                await self.attachments_store.save(record)
                logger.info(
                    "[SESSIONS][ATTACH] Persisted summary for session=%s attachment=%s chars=%d",
                    session.id,
                    attachment_id,
                    len(summary_md),
                )
                cached = self.session_cache.get(session.id)
                if cached:
                    attachments = (cached.attachments or []) + [record]
                    self.session_cache.set(
                        session.id,
                        CachedSession(session=cached.session, attachments=attachments),
                    )
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.debug(
                            "[SESSIONS][ATTACH] cache updated after add session=%s attachments=%d",
                            session.id,
                            len(attachments),
                        )
            except Exception:
                logger.exception(
                    "[SESSIONS][ATTACH] Failed to persist attachment summary for session=%s attachment=%s",
                    session.id,
                    attachment_id,
                )

        return {
            "session_id": session.id,
            "attachment_id": attachment_id,
            "filename": file.filename,
            "mime": file.content_type,
            "size_bytes": len(content),
            "preview_chars": min(len(summary_md), 300),
            "session": session.model_dump(),
        }
