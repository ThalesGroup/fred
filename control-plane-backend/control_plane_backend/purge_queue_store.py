from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fred_core.sql import (
    AsyncBaseSqlStore,
    advisory_lock_key,
    run_ddl_with_advisory_lock,
)
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, MetaData, String, Table, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_PENDING = "pending"
_DONE = "done"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PurgeQueueItem(BaseModel):
    session_id: str = Field(..., min_length=1)
    team_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    due_at: datetime
    created_at: datetime


class PurgeQueueStore:
    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str = ""):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._ddl_lock_id = advisory_lock_key(self.table_name)
        self._schema_ready_task: asyncio.Task[None] | None = None

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("session_id", String, primary_key=True),
            Column("team_id", String, index=True, nullable=False),
            Column("user_id", String, index=True, nullable=False),
            Column("due_at", DateTime(timezone=True), index=True, nullable=False),
            Column("status", String, index=True, nullable=False),
            Column("created_at", DateTime(timezone=True), index=True, nullable=False),
            Column("updated_at", DateTime(timezone=True), index=True, nullable=False),
            keep_existing=True,
        )

        async def _create() -> None:
            await run_ddl_with_advisory_lock(
                engine=self.store.engine,
                lock_key=self._ddl_lock_id,
                ddl_sync_fn=metadata.create_all,
                logger=logger,
            )

        try:
            loop = asyncio.get_running_loop()
            self._schema_ready_task = loop.create_task(_create())
        except RuntimeError:
            asyncio.run(_create())
        logger.info("[PURGE_QUEUE] Table ready: %s", self.table_name)

    async def _ensure_schema_ready(self) -> None:
        if self._schema_ready_task is not None:
            await self._schema_ready_task

    async def enqueue(
        self,
        *,
        session_id: str,
        team_id: str,
        user_id: str,
        due_at: datetime,
    ) -> None:
        await self._ensure_schema_ready()
        now = _utcnow()
        async with self.store.begin() as conn:
            await self.store.upsert(
                conn,
                self.table,
                values={
                    "session_id": session_id,
                    "team_id": team_id,
                    "user_id": user_id,
                    "due_at": due_at,
                    "status": _PENDING,
                    "created_at": now,
                    "updated_at": now,
                },
                pk_cols=["session_id"],
                update_cols=["team_id", "user_id", "due_at", "status", "updated_at"],
            )

    async def list_due(self, *, limit: int) -> list[PurgeQueueItem]:
        await self._ensure_schema_ready()
        now = _utcnow()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(
                    self.table.c.session_id,
                    self.table.c.team_id,
                    self.table.c.user_id,
                    self.table.c.due_at,
                    self.table.c.created_at,
                )
                .where(self.table.c.status == _PENDING)
                .where(self.table.c.due_at <= now)
                .order_by(self.table.c.due_at.asc(), self.table.c.session_id.asc())
                .limit(limit)
            )
            rows = result.fetchall()

        return [
            PurgeQueueItem(
                session_id=row[0],
                team_id=row[1],
                user_id=row[2],
                due_at=row[3],
                created_at=row[4],
            )
            for row in rows
        ]

    async def mark_done(self, *, session_id: str) -> None:
        await self._ensure_schema_ready()
        async with self.store.begin() as conn:
            await conn.execute(
                update(self.table)
                .where(self.table.c.session_id == session_id)
                .values(status=_DONE, updated_at=_utcnow())
            )
