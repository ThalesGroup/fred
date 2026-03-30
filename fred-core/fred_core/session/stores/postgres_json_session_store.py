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

import asyncio
import logging
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from fred_core.session.stores.base_json_session_store import BaseJsonSessionStore
from fred_core.sql import (
    AsyncBaseSqlStore,
    advisory_lock_key,
    run_ddl_with_advisory_lock,
)

logger = logging.getLogger(__name__)


class PostgresJsonSessionStore(BaseJsonSessionStore):
    """PostgreSQL session storage for JSON payloads.

    This store is schema-agnostic and can be reused across services.
    Domain services are responsible for mapping their own Pydantic models to/from
    JSON payloads.
    """

    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str = "sessions_"):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._ddl_lock_id = advisory_lock_key(self.table_name)
        self._schema_ready_task: asyncio.Task[None] | None = None

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("session_id", String, primary_key=True),
            Column("user_id", String, index=True),
            Column("team_id", String, index=True),
            Column("agent_id", String, index=True),
            Column("session_data", JSON),
            Column("updated_at", DateTime(timezone=True), index=True),
            keep_existing=True,
        )

        def _ensure_schema(sync_conn: Any) -> None:
            metadata.create_all(sync_conn)
            insp = inspect(sync_conn)
            cols = {c["name"] for c in insp.get_columns(self.table_name)}
            if "team_id" not in cols:
                # SQLite compatibility:
                # some bundled SQLite versions reject `ADD COLUMN IF NOT EXISTS`.
                # We already checked column presence via inspector, so plain ADD
                # is safe and works across Postgres + SQLite.
                sync_conn.execute(
                    text(f'ALTER TABLE "{self.table_name}" ADD COLUMN team_id VARCHAR')
                )
                logger.info(
                    "[SESSION][PG] Added missing team_id column to %s",
                    self.table_name,
                )
            sync_conn.execute(
                text(
                    f'CREATE INDEX IF NOT EXISTS "ix_{self.table_name}_team_id" '
                    f'ON "{self.table_name}" (team_id)'
                )
            )

        async def _create() -> None:
            await run_ddl_with_advisory_lock(
                engine=self.store.engine,
                lock_key=self._ddl_lock_id,
                ddl_sync_fn=_ensure_schema,
                logger=logger,
            )

        try:
            loop = asyncio.get_running_loop()
            self._schema_ready_task = loop.create_task(_create())
        except RuntimeError:
            asyncio.run(_create())
        logger.info("[SESSION][PG][ASYNC] Table ready: %s", self.table_name)

    async def _ensure_schema_ready(self) -> None:
        if self._schema_ready_task is not None:
            await self._schema_ready_task

    async def save(
        self,
        *,
        session_id: str,
        user_id: str,
        updated_at: datetime,
        payload: Mapping[str, Any],
        team_id: str | None = None,
        agent_id: str = "",
    ) -> None:
        await self._ensure_schema_ready()
        async with self.store.begin() as conn:
            await self.save_with_conn(
                conn,
                session_id=session_id,
                user_id=user_id,
                updated_at=updated_at,
                payload=payload,
                team_id=team_id,
                agent_id=agent_id,
            )

    async def save_with_conn(
        self,
        conn: AsyncConnection,
        *,
        session_id: str,
        user_id: str,
        updated_at: datetime,
        payload: Mapping[str, Any],
        team_id: str | None = None,
        agent_id: str = "",
    ) -> None:
        await self._ensure_schema_ready()
        await self.store.upsert(
            conn,
            self.table,
            values={
                "session_id": session_id,
                "user_id": user_id,
                "team_id": team_id,
                "agent_id": agent_id,
                "session_data": dict(payload),
                "updated_at": updated_at,
            },
            pk_cols=["session_id"],
        )

    async def get_payload(self, session_id: str) -> dict[str, Any] | None:
        await self._ensure_schema_ready()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table.c.session_data).where(
                    self.table.c.session_id == session_id
                )
            )
            row = result.fetchone()
        if not row:
            return None
        raw = row[0]
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        return dict(raw)

    async def delete(self, session_id: str) -> None:
        await self._ensure_schema_ready()
        async with self.store.begin() as conn:
            await conn.execute(
                self.table.delete().where(self.table.c.session_id == session_id)
            )

    async def get_payloads_for_user(self, user_id: str) -> list[dict[str, Any]]:
        await self._ensure_schema_ready()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table.c.session_data)
                .where(self.table.c.user_id == user_id)
                .order_by(self.table.c.updated_at.desc())
            )
            rows = result.fetchall()

        payloads: list[dict[str, Any]] = []
        for row in rows:
            raw = row[0]
            if raw is None:
                continue
            payloads.append(raw if isinstance(raw, dict) else dict(raw))
        return payloads

    async def count_for_user(self, user_id: str) -> int:
        await self._ensure_schema_ready()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(func.count()).where(self.table.c.user_id == user_id)
            )
            return int(result.scalar_one())
