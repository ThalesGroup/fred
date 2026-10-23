# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Persist the narrow source list exposed by one conversation sandbox."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fred_core.sql.async_session import make_session_factory, use_session
from fred_pod.security.structure import KeycloakUser
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.content.sandbox_scope import (
    MAX_MOUNTED_FILE_BYTES,
    authorize_corpus_source,
)
from knowledge_flow_backend.models.sandbox_view_models import (
    SandboxAttachmentOriginalRow,
    SandboxViewRow,
)

VIEW_KEY_RE = re.compile(r"[a-f0-9]{64}\Z")
MAX_VIEW_FILES = 32
MAX_VIEW_BYTES = 100 * 1024 * 1024
MAX_VIEW_REQUESTS_PER_MINUTE = 120
VIEW_TTL = timedelta(minutes=130)


def _expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class MountedSource:
    path: str
    kind: str
    uid: str
    name: str
    size: int


class SandboxViewStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def retain_attachment_original(
        self,
        *,
        context: ApplicationContext,
        document_uid: str,
        session_id: str,
        user_id: str,
        name: str,
        raw_path: Path,
        content_type: str,
    ) -> None:
        name = _safe_name(name)
        size = raw_path.stat().st_size
        if size > MAX_MOUNTED_FILE_BYTES:
            return
        object_key = f"sandbox-attachments/{document_uid}/original"
        await asyncio.to_thread(
            context.get_content_store().put_file,
            object_key,
            raw_path,
            content_type=content_type,
        )
        try:
            async with use_session(self._sessions) as db:
                db.add(
                    SandboxAttachmentOriginalRow(
                        document_uid=document_uid,
                        session_id=session_id,
                        user_id=user_id,
                        name=name,
                        size=size,
                        object_key=object_key,
                    )
                )
        except BaseException:
            try:
                await asyncio.to_thread(context.get_content_store().delete_object, object_key)
            except FileNotFoundError:
                pass
            raise

    async def delete_attachment_original(
        self,
        *,
        context: ApplicationContext,
        document_uid: str,
        user_id: str,
        platform_bypass: bool,
    ) -> None:
        async with use_session(self._sessions) as db:
            original = await db.get(SandboxAttachmentOriginalRow, document_uid)
            if original is None:
                return
            if not platform_bypass and original.user_id != user_id:
                raise PermissionError("Attachment original access denied")
            try:
                await asyncio.to_thread(context.get_content_store().delete_object, original.object_key)
            except FileNotFoundError:
                pass
            await db.delete(original)

    async def _check_session(self, session_id: str, user_id: str, team_id: str, *, session=None) -> None:
        async with use_session(self._sessions, session) as db:
            row = (
                await db.execute(
                    text("SELECT user_id, team_id FROM session_metadata WHERE session_id = :session_id AND deleted_at IS NULL"),
                    {"session_id": session_id},
                )
            ).first()
        if row is None or row.user_id != user_id or row.team_id != team_id:
            raise PermissionError("Conversation access denied")

    async def bind_corpus(
        self,
        *,
        key: str,
        session_id: str,
        team_id: str,
        user: KeycloakUser,
        document_uid: str,
        context: ApplicationContext | None = None,
    ) -> MountedSource:
        if not VIEW_KEY_RE.fullmatch(key):
            raise ValueError("Invalid sandbox view key")
        await self._check_session(session_id, user.uid, team_id)
        source = await authorize_corpus_source(user, team_id, document_uid, context=context)
        path = f"corpus/{source.document_uid}/{source.name}"
        mounted = MountedSource(
            path=path,
            kind="corpus",
            uid=source.document_uid,
            name=source.name,
            size=source.size,
        )
        await self._bind(key, session_id, team_id, user.uid, mounted)
        return mounted

    async def bind_attachment(
        self,
        *,
        key: str,
        session_id: str,
        team_id: str,
        user: KeycloakUser,
        attachment_id: str,
        context: ApplicationContext | None = None,
    ) -> MountedSource:
        if not VIEW_KEY_RE.fullmatch(key):
            raise ValueError("Invalid sandbox view key")
        context = context or ApplicationContext.get_instance()
        await self._check_session(session_id, user.uid, team_id)
        await context.get_rebac_engine().require_active_account(user.uid)
        async with use_session(self._sessions) as db:
            row = (
                await db.execute(
                    text(
                        "SELECT a.name, a.document_uid, o.user_id, o.size "
                        "FROM session_attachments a "
                        "JOIN sandbox_attachment_originals o "
                        "ON o.document_uid = a.document_uid AND o.session_id = a.session_id "
                        "WHERE a.session_id = :session_id AND a.attachment_id = :attachment_id"
                    ),
                    {"session_id": session_id, "attachment_id": attachment_id},
                )
            ).first()
        if row is None or row.user_id != user.uid:
            raise FileNotFoundError("Attachment original is unavailable")
        if row.size < 0 or row.size > MAX_MOUNTED_FILE_BYTES:
            raise ValueError("Attachment exceeds the sandbox file limit")
        name = _safe_name(row.name)
        mounted = MountedSource(
            path=f"attachments/{attachment_id}/{name}",
            kind="attachment",
            uid=row.document_uid,
            name=name,
            size=row.size,
        )
        await self._bind(key, session_id, team_id, user.uid, mounted)
        return mounted

    async def _bind(self, key: str, session_id: str, team_id: str, user_id: str, source: MountedSource) -> None:
        now = datetime.now(timezone.utc)
        async with use_session(self._sessions) as db:
            await db.execute(delete(SandboxViewRow).where(SandboxViewRow.expires_at < now))
            row = await db.get(SandboxViewRow, key, with_for_update=True)
            if row is None:
                row = SandboxViewRow(
                    key=key,
                    session_id=session_id,
                    user_id=user_id,
                    team_id=team_id,
                    expires_at=now + VIEW_TTL,
                    sources={},
                    bytes_served=0,
                    request_window_started_at=now,
                    request_window_count=0,
                )
                db.add(row)
            elif row.session_id != session_id or row.user_id != user_id or row.team_id != team_id:
                raise PermissionError("Sandbox view access denied")
            sources = dict(row.sources)
            if len(sources) >= MAX_VIEW_FILES and source.path not in sources:
                raise ValueError("Sandbox view file limit reached")
            sources[source.path] = {
                "kind": source.kind,
                "uid": source.uid,
                "name": source.name,
                "size": source.size,
            }
            row.sources = sources
            row.expires_at = now + VIEW_TTL

    async def list_sources(self, key: str) -> tuple[SandboxViewRow | None, list[MountedSource]]:
        if not VIEW_KEY_RE.fullmatch(key):
            raise FileNotFoundError("Sandbox view is unavailable")
        async with use_session(self._sessions) as db:
            row = await db.get(SandboxViewRow, key, with_for_update=True)
            if row is None:
                return None, []
            if _expired(row.expires_at):
                raise FileNotFoundError("Sandbox view has expired")
            now = datetime.now(timezone.utc)
            window_started = row.request_window_started_at
            if window_started.tzinfo is None:
                window_started = window_started.replace(tzinfo=timezone.utc)
            if now - window_started >= timedelta(minutes=1):
                row.request_window_started_at = now
                row.request_window_count = 0
            if row.request_window_count >= MAX_VIEW_REQUESTS_PER_MINUTE:
                raise PermissionError("Sandbox view request rate exceeded")
            row.request_window_count += 1
            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at - now < timedelta(minutes=30):
                row.expires_at = now + VIEW_TTL
            sources: list[MountedSource] = []
            for path, item in row.sources.items():
                kind, uid, name, size = (
                    item.get("kind"),
                    item.get("uid"),
                    item.get("name"),
                    item.get("size"),
                )
                if not isinstance(kind, str) or not isinstance(uid, str) or not isinstance(name, str) or not isinstance(size, int) or size < 0:
                    raise FileNotFoundError("Sandbox view has invalid source metadata")
                sources.append(MountedSource(path=path, kind=kind, uid=uid, name=name, size=size))
            return row, sources

    async def revoke(self, key: str) -> None:
        if not VIEW_KEY_RE.fullmatch(key):
            raise ValueError("Invalid sandbox view key")
        async with use_session(self._sessions) as db:
            row = await db.get(SandboxViewRow, key)
            if row is not None:
                await db.delete(row)

    async def reserve_bytes(self, key: str, count: int) -> None:
        if count < 0 or count > MAX_MOUNTED_FILE_BYTES:
            raise ValueError("Sandbox read exceeds file limit")
        async with use_session(self._sessions) as db:
            row = await db.get(SandboxViewRow, key, with_for_update=True)
            if row is None or _expired(row.expires_at) or row.bytes_served + count > MAX_VIEW_BYTES:
                raise PermissionError("Sandbox read quota exceeded")
            row.bytes_served += count

    async def attachment_original(self, session_id: str, user_id: str, document_uid: str) -> SandboxAttachmentOriginalRow:
        async with use_session(self._sessions) as db:
            original = await db.get(SandboxAttachmentOriginalRow, document_uid)
            attached = (
                await db.execute(
                    text("SELECT 1 FROM session_attachments WHERE session_id = :session_id AND document_uid = :document_uid"),
                    {"session_id": session_id, "document_uid": document_uid},
                )
            ).first()
        if original is None or attached is None or original.session_id != session_id or original.user_id != user_id:
            raise FileNotFoundError("Attachment original is unavailable")
        return original


def _safe_name(name: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise ValueError("Unsafe sandbox file name")
    return name
