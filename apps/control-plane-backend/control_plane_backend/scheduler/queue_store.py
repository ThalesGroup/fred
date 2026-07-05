from __future__ import annotations

import logging
from datetime import datetime

from fred_core.sql import make_session_factory, use_session
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.purge_queue_models import PurgeQueueRow

logger = logging.getLogger(__name__)

_PENDING = "pending"
_DONE = "done"


class PurgeQueueItem(BaseModel):
    session_id: str = Field(..., min_length=1)
    team_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    due_at: datetime
    created_at: datetime


class PurgeQueueStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def enqueue(
        self,
        *,
        session_id: str,
        team_id: str,
        user_id: str,
        due_at: datetime,
        session: AsyncSession | None = None,
    ) -> bool:
        """Enqueue a pending purge for `session_id`, due at `due_at`.

        Returns True when a *new* pending row was inserted, False when an
        existing pending entry was kept (idempotent no-op). Callers that also
        create a scheduled erasure task gate that task on this flag so a retried /
        double-clicked deferred delete does not mint a duplicate task (CTRLP-12).
        """
        async with use_session(self._sessions, session) as s:
            # Idempotent for an already-pending session: the primary key is
            # session_id, so a naive merge() of a repeated delete would reset an
            # existing PENDING row's status and push its due_at further out —
            # letting an API replay indefinitely postpone the scheduled erasure
            # (CTRLP-12). Keep the first pending entry's due_at/status intact and
            # only insert when there is no pending entry. A prior DONE row is
            # allowed to be re-scheduled (a genuinely new deferred delete).
            existing = await s.get(PurgeQueueRow, session_id)
            if existing is not None and existing.status == _PENDING:
                return False
            await s.merge(
                PurgeQueueRow(
                    session_id=session_id,
                    team_id=team_id,
                    user_id=user_id,
                    due_at=due_at,
                    status=_PENDING,
                )
            )
            return True

    async def list_due(
        self,
        *,
        limit: int,
        session: AsyncSession | None = None,
    ) -> list[PurgeQueueItem]:
        """
        Return pending purge-queue items whose due time is in the past.

        Why this function exists:
        - lifecycle runners need one ordered source of pending purge work
        - queue filtering should use the same timezone-aware UTC policy as the
          ORM defaults

        How to use it:
        - call with a bounded `limit` from the lifecycle candidate listing path
        - callers decide whether to dry-run, delete, or mark items done later

        Example:
        - `due_items = await store.list_due(limit=100)`
        """

        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(PurgeQueueRow)
                        .where(PurgeQueueRow.status == _PENDING)
                        .where(PurgeQueueRow.due_at <= utcnow())
                        .order_by(
                            PurgeQueueRow.due_at.asc(), PurgeQueueRow.session_id.asc()
                        )
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [
            PurgeQueueItem(
                session_id=row.session_id,
                team_id=row.team_id,
                user_id=row.user_id,
                due_at=row.due_at,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def mark_done(
        self,
        *,
        session_id: str,
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(
                update(PurgeQueueRow)
                .where(PurgeQueueRow.session_id == session_id)
                .values(status=_DONE)
            )
