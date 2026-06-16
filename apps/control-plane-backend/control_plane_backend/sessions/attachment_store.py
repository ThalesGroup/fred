from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.session_attachment_models import SessionAttachmentRow


@dataclass
class SessionAttachmentRecord:
    """In-memory projection of one persisted session attachment summary."""

    session_id: str
    attachment_id: str
    name: str
    summary_md: str
    document_uid: str | None = None
    storage_key: str | None = None
    mime: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BaseSessionAttachmentStore(ABC):
    """Persistence contract for session-scoped attachment summaries."""

    @abstractmethod
    async def save(
        self, record: SessionAttachmentRecord, session: AsyncSession | None = None
    ) -> None:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def list_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> list[SessionAttachmentRecord]:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def delete(
        self, session_id: str, attachment_id: str, session: AsyncSession | None = None
    ) -> None:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def delete_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> None:  # pragma: no cover - interface
        pass

    @abstractmethod
    async def count_for_sessions(
        self, session_ids: list[str], session: AsyncSession | None = None
    ) -> int:  # pragma: no cover - interface
        pass


class SessionAttachmentStore(BaseSessionAttachmentStore):
    """
    PostgreSQL-backed storage for session attachments.

    Why this class exists:
    - Swift needs the same persisted attachment summary behavior as `main`
      so chat attachments survive reloads and can be managed later
    - the only Swift-specific schema extension is `storage_key`, used for
      storage cleanup orchestration

    How to use it:
    - call `save()` after a successful upload + fast-ingest cycle
    - call `list_for_session()` to hydrate the drawer/source of truth
    - call `delete()` / `delete_for_session()` during explicit cleanup flows
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def save(
        self, record: SessionAttachmentRecord, session: AsyncSession | None = None
    ) -> None:
        now = datetime.now(timezone.utc)
        row = SessionAttachmentRow(
            session_id=record.session_id,
            attachment_id=record.attachment_id,
            name=record.name,
            mime=record.mime,
            size_bytes=record.size_bytes,
            summary_md=record.summary_md,
            document_uid=record.document_uid,
            storage_key=record.storage_key,
            created_at=record.created_at or now,
            updated_at=record.updated_at or now,
        )
        async with use_session(self._sessions, session) as s:
            await s.merge(row)

    async def list_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> list[SessionAttachmentRecord]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(SessionAttachmentRow)
                        .where(SessionAttachmentRow.session_id == session_id)
                        .order_by(SessionAttachmentRow.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
        return [
            SessionAttachmentRecord(
                session_id=row.session_id,
                attachment_id=row.attachment_id,
                name=row.name,
                mime=row.mime,
                size_bytes=row.size_bytes,
                summary_md=row.summary_md,
                document_uid=row.document_uid,
                storage_key=row.storage_key,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def delete(
        self, session_id: str, attachment_id: str, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(SessionAttachmentRow).where(
                    SessionAttachmentRow.session_id == session_id,
                    SessionAttachmentRow.attachment_id == attachment_id,
                )
            )

    async def delete_for_session(
        self, session_id: str, session: AsyncSession | None = None
    ) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(
                delete(SessionAttachmentRow).where(
                    SessionAttachmentRow.session_id == session_id
                )
            )

    async def count_for_sessions(
        self, session_ids: list[str], session: AsyncSession | None = None
    ) -> int:
        if not session_ids:
            return 0
        async with use_session(self._sessions, session) as s:
            result = await s.execute(
                select(func.count())
                .select_from(SessionAttachmentRow)
                .where(SessionAttachmentRow.session_id.in_(session_ids))
            )
            return result.scalar() or 0
