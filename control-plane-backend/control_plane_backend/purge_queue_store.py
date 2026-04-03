from __future__ import annotations

import logging
from datetime import datetime

from fred_core.sql import make_session_factory, use_session
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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
    ) -> None:
        row = PurgeQueueRow(
            session_id=session_id,
            team_id=team_id,
            user_id=user_id,
            due_at=due_at,
            status=_PENDING,
        )
        async with use_session(self._sessions, session) as s:
            await s.merge(row)

    async def list_due(
        self,
        *,
        limit: int,
        session: AsyncSession | None = None,
    ) -> list[PurgeQueueItem]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(PurgeQueueRow)
                        .where(PurgeQueueRow.status == _PENDING)
                        .where(PurgeQueueRow.due_at <= func.now())
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
