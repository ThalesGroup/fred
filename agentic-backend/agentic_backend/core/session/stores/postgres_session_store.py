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
from typing import Any, Dict, List, Optional

from fred_core.sql import AsyncBaseSqlStore
from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_backend.core.chatbot.chat_schema import SessionSchema
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore

logger = logging.getLogger(__name__)


class PostgresSessionStore(BaseSessionStore):
    """
    PostgreSQL-backed session store using JSONB.
    """

    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str = "sessions_"):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("session_id", String, primary_key=True),
            Column("user_id", String, index=True),
            Column("agent_id", String, index=True),
            Column("session_data", JSON),
            Column("updated_at", DateTime(timezone=True), index=True),
            keep_existing=True,
        )

        async def _create():
            async with self.store.engine.begin() as conn:  # type: ignore[attr-defined]
                await conn.run_sync(metadata.create_all)

        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_create())
        except RuntimeError:
            asyncio.run(_create())
        logger.info("[SESSION][PG][ASYNC] Table ready: %s", self.table_name)

    async def save(self, session: SessionSchema) -> None:
        async with self.store.begin() as conn:
            await self.save_with_conn(conn, session)

    async def save_with_conn(self, conn, session: SessionSchema) -> None:
        """
        Same as save(), but reuses the provided AsyncConnection so callers can
        bundle writes in a single transaction.
        """
        payload: Dict[str, Any] = session.model_dump(mode="json")
        await self.store.upsert(
            conn,
            self.table,
            values={
                "session_id": session.id,
                "user_id": session.user_id,
                "agent_id": payload.get("agent_id", ""),
                "session_data": payload,
                "updated_at": session.updated_at,
            },
            pk_cols=["session_id"],
        )

    async def get(self, session_id: str) -> Optional[SessionSchema]:
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table.c.session_data).where(
                    self.table.c.session_id == session_id
                )
            )
            row = result.fetchone()
        if not row:
            return None
        return SessionSchema.model_validate(row[0])

    async def delete(self, session_id: str) -> None:
        async with self.store.begin() as conn:
            await conn.execute(
                self.table.delete().where(self.table.c.session_id == session_id)
            )

    async def get_for_user(self, user_id: str) -> List[SessionSchema]:
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table.c.session_data)
                .where(self.table.c.user_id == user_id)
                .order_by(self.table.c.updated_at.desc())
            )
            rows = result.fetchall()
        return [SessionSchema.model_validate(r[0]) for r in rows]

    async def count_for_user(self, user_id: str) -> int:
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(func.count()).where(self.table.c.user_id == user_id)
            )
            return int(result.scalar_one())
