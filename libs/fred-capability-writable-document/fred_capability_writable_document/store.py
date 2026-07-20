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

"""Persistence for the writable_document capability (#1905, RFC §7.1).

Why this module exists:
- the capability owns ONE table, `cap_writable_document_docs`, on its OWN
  isolated `DeclarativeBase` with NO foreign keys (the boot hygiene contract the
  registry enforces): `session_id` and `user_id` reference core ids as plain
  columns so install/uninstall ordering stays free
- the store is reached through an OVERRIDABLE module-level provider
  (`get_writable_document_store`). Production resolves a `SqlWritableDocumentStore`
  built lazily from the pod's own Postgres config; offline tests substitute an
  in-memory fake via `set_store_provider` — so neither the chat-time middleware
  nor the router ever binds an engine at import time.

Record semantics (ported from Kea's `writable_document_store`, extended for the
Swift edit-notification model, RFC §5): a document is keyed by
`(session_id, document_id)`, carries the owning chat `user_id` for router authz,
tracks the last author (`updated_by`), and records `agent_notified_at` — when the
agent was last told about a user edit. A user edit clears `agent_notified_at` so
the middleware re-notifies on the next turn; `mark_agent_notified` stamps it.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

WritableDocumentAuthor = Literal["agent", "user"]


def _utcnow() -> datetime:
    """Timezone-aware UTC now (all stored timestamps are aware)."""

    return datetime.now(timezone.utc)


def new_document_id() -> str:
    """Mint a fresh document id (Kea convention: an opaque uuid4 string)."""

    return str(uuid.uuid4())


# --- Owned table (RFC §7.1) ------------------------------------------------
#
# Under its OWN declarative base so its metadata never mixes with fred-runtime's
# or another capability's; migrations ship beside this module and apply under
# `cap_writable_document_alembic_version`.


class WritableDocumentBase(DeclarativeBase):
    """Isolated declarative base for the writable_document capability's table."""


class WritableDocumentDoc(WritableDocumentBase):
    """
    One session-scoped collaborative Markdown document (#1905).

    Hygiene (RFC §7.1, enforced at pod boot):
    - name is prefixed `cap_writable_document_` (the `cap_<id>_` convention)
    - no foreign keys — `session_id` / `user_id` reference core ids as PLAIN
      columns, so install/uninstall ordering stays free
    """

    __tablename__ = "cap_writable_document_docs"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # The chat user who owns the session — the router authorizes reads/edits
    # against this (a document is only reachable by its owner).
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(16), nullable=False)
    # When the agent was last told about a user edit (Swift replacement for Kea's
    # orchestrator last-activity bookkeeping). NULL after a user edit → pending
    # notification; stamped by `mark_agent_notified`.
    agent_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


# --- Record (transport between store and callers) --------------------------


@dataclass
class WritableDocumentRecord:
    """A collaborative Markdown document scoped to one chat session.

    Co-authored over time by the agent (via the ``write_document`` tool) and the
    user (via the editor pane). Only the last author is tracked (``updated_by``).
    """

    session_id: str
    document_id: str
    user_id: str
    title: str
    content_md: str
    updated_by: WritableDocumentAuthor = "agent"
    agent_notified_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _to_record(row: WritableDocumentDoc) -> WritableDocumentRecord:
    return WritableDocumentRecord(
        session_id=row.session_id,
        document_id=row.document_id,
        user_id=row.user_id,
        title=row.title,
        content_md=row.content_md,
        updated_by=("user" if row.updated_by == "user" else "agent"),
        agent_notified_at=row.agent_notified_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# --- Store contract + SQL implementation -----------------------------------


class WritableDocumentStore(ABC):
    """Persistence contract for session-scoped writable documents (RFC §7.1)."""

    @abstractmethod
    async def upsert(
        self, record: WritableDocumentRecord
    ) -> WritableDocumentRecord:  # pragma: no cover - interface
        """Create or update a document; bumps ``updated_at``, preserves ``created_at``."""

    @abstractmethod
    async def get(
        self, session_id: str, document_id: str
    ) -> WritableDocumentRecord | None:  # pragma: no cover - interface
        ...

    @abstractmethod
    async def list_for_session(
        self, session_id: str
    ) -> list[WritableDocumentRecord]:  # pragma: no cover - interface
        ...

    @abstractmethod
    async def list_user_edited_unnotified(
        self, session_id: str
    ) -> list[WritableDocumentRecord]:  # pragma: no cover - interface
        """User-edited documents the agent has not been notified about yet."""

    @abstractmethod
    async def mark_agent_notified(
        self, session_id: str, document_id: str, ts: datetime
    ) -> None:  # pragma: no cover - interface
        """Record that the agent was told about a user edit at ``ts``."""


class SqlWritableDocumentStore(WritableDocumentStore):
    """Async SQLAlchemy-backed store over ``cap_writable_document_docs``."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def upsert(self, record: WritableDocumentRecord) -> WritableDocumentRecord:
        async with self._sessionmaker() as session:
            async with session.begin():
                row = await session.get(
                    WritableDocumentDoc, (record.session_id, record.document_id)
                )
                now = _utcnow()
                if row is None:
                    row = WritableDocumentDoc(
                        session_id=record.session_id,
                        document_id=record.document_id,
                        user_id=record.user_id,
                        title=record.title,
                        content_md=record.content_md,
                        updated_by=record.updated_by,
                        agent_notified_at=record.agent_notified_at,
                        created_at=record.created_at or now,
                        updated_at=now,
                    )
                    session.add(row)
                else:
                    # Preserve created_at; overwrite the mutable content/authorship.
                    row.user_id = record.user_id
                    row.title = record.title
                    row.content_md = record.content_md
                    row.updated_by = record.updated_by
                    row.agent_notified_at = record.agent_notified_at
                    row.updated_at = now
            await session.refresh(row)
            return _to_record(row)

    async def get(
        self, session_id: str, document_id: str
    ) -> WritableDocumentRecord | None:
        async with self._sessionmaker() as session:
            row = await session.get(WritableDocumentDoc, (session_id, document_id))
            return _to_record(row) if row is not None else None

    async def list_for_session(self, session_id: str) -> list[WritableDocumentRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(WritableDocumentDoc).where(
                    WritableDocumentDoc.session_id == session_id
                )
            )
            return [_to_record(row) for row in result.scalars().all()]

    async def list_user_edited_unnotified(
        self, session_id: str
    ) -> list[WritableDocumentRecord]:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(WritableDocumentDoc).where(
                    WritableDocumentDoc.session_id == session_id,
                    WritableDocumentDoc.updated_by == "user",
                    WritableDocumentDoc.agent_notified_at.is_(None),
                )
            )
            return [_to_record(row) for row in result.scalars().all()]

    async def mark_agent_notified(
        self, session_id: str, document_id: str, ts: datetime
    ) -> None:
        async with self._sessionmaker() as session:
            async with session.begin():
                row = await session.get(WritableDocumentDoc, (session_id, document_id))
                if row is not None:
                    row.agent_notified_at = ts


# --- Overridable provider (RFC §3.5 — services never bind at import time) ---

_provider: Callable[[], WritableDocumentStore] | None = None


@dataclass
class _EngineCache:
    """Lazily-built async engine + sessionmaker, cached for the process."""

    engine: AsyncEngine | None = field(default=None)
    sessionmaker: async_sessionmaker[AsyncSession] | None = field(default=None)


_engine_cache = _EngineCache()


def _default_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Build (once) the async sessionmaker from the pod's own Postgres config.

    Reuses fred-core's `create_async_engine_from_config` rather than assembling a
    URL by hand — the same helper fred-runtime's own stores use — so the sqlite
    laptop escape hatch and pool settings stay identical.
    """

    if _engine_cache.sessionmaker is None:
        from fred_core.sql import create_async_engine_from_config
        from fred_runtime.app.config_loader import load_agent_pod_config

        engine = create_async_engine_from_config(
            load_agent_pod_config().storage.postgres
        )
        _engine_cache.engine = engine
        _engine_cache.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return _engine_cache.sessionmaker


def get_writable_document_store() -> WritableDocumentStore:
    """Resolve the writable-document store (test-overridable provider seam)."""

    if _provider is not None:
        return _provider()
    return SqlWritableDocumentStore(_default_sessionmaker())


def set_store_provider(provider: Callable[[], WritableDocumentStore]) -> None:
    """Override the store resolution (tests inject an in-memory fake)."""

    global _provider
    _provider = provider


def clear_store_provider() -> None:
    """Restore the default (Postgres-backed) store resolution."""

    global _provider
    _provider = None
