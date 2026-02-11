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
from typing import List, Optional

from fred_core.sql import AsyncBaseSqlStore, json_for_engine
from pydantic import TypeAdapter
from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.agents.store.base_agent_store import (
    AgentNotFoundError,
    BaseAgentStore,
)

logger = logging.getLogger(__name__)

AgentSettingsAdapter = TypeAdapter(AgentSettings)


class PostgresAgentStore(BaseAgentStore):
    """
    PostgreSQL-backed agent store using JSONB (async).
    """

    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str = "agents_"):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._seed_marker_id = "__static_seeded__"

        json_type = json_for_engine(self.store.engine)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("id", String, primary_key=True),
            Column("name", String),
            Column("payload_json", json_type),
            keep_existing=True,
        )

        async def _create():
            async with self.store.engine.begin() as conn:  # type: ignore[attr-defined]
                try:
                    await conn.run_sync(metadata.create_all)
                except OperationalError as exc:
                    # SQLite may raise if create_all races; ignore "already exists"
                    msg = str(exc).lower()
                    if "already exists" not in msg:
                        raise

        try:
            loop = asyncio.get_running_loop()
            self._create_task = loop.create_task(_create())
        except RuntimeError:
            self._create_task = None
            asyncio.run(_create())
        logger.info("[AGENTS][PG][ASYNC] Table ready: %s", self.table_name)

    async def _ensure_table(self) -> None:
        task = getattr(self, "_create_task", None)
        if task is not None and not task.done():
            await task

    async def save(
        self,
        settings: AgentSettings,
        tuning: AgentTuning,
    ) -> None:
        await self._ensure_table()
        if settings.id == self._seed_marker_id:
            raise ValueError("Invalid agent id: reserved for seed marker")

        payload = AgentSettingsAdapter.dump_python(
            settings, mode="json", exclude_none=True
        )
        if tuning is not None and "tuning" not in payload:
            try:
                payload["tuning"] = tuning.model_dump(exclude_none=True)
            except Exception:
                logger.warning(
                    "[STORE][PG][AGENTS] Could not embed tuning into AgentSettings for '%s'",
                    settings.id,
                )
                pass

        async with self.store.begin() as conn:
            await self.store.upsert(
                conn,
                self.table,
                values={
                    "id": settings.id,
                    "name": settings.name,
                    "payload_json": payload,
                },
                pk_cols=["id"],
            )

    async def load_all(self) -> List[AgentSettings]:
        await self._ensure_table()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table.c.payload_json, self.table.c.id)
            )
            rows = result.fetchall()

        out: List[AgentSettings] = []
        for payload_json, agent_id in rows:
            if agent_id == self._seed_marker_id:
                continue
            try:
                out.append(AgentSettingsAdapter.validate_python(payload_json or {}))
            except Exception as e:
                logger.error("[STORE][PG][AGENTS] Failed to parse AgentSettings: %s", e)
        return out

    async def get(
        self,
        agent_id: str,
    ) -> Optional[AgentSettings]:
        await self._ensure_table()
        if agent_id == self._seed_marker_id:
            return None
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table.c.payload_json).where(self.table.c.id == agent_id)
            )
            row = result.fetchone()
        if not row:
            return None
        try:
            return AgentSettingsAdapter.validate_python(row[0] or {})
        except Exception as e:
            logger.error(
                "[STORE][PG][AGENTS] Failed to parse AgentSettings for '%s': %s",
                agent_id,
                e,
            )
            return None

    async def delete(
        self,
        agent_id: str,
    ) -> None:
        await self._ensure_table()
        if agent_id == self._seed_marker_id:
            return
        async with self.store.begin() as conn:
            result = await conn.execute(
                self.table.delete().where(self.table.c.id == agent_id)
            )
        if result.rowcount == 0:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")

    async def static_seeded(self) -> bool:
        await self._ensure_table()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table.c.id).where(self.table.c.id == self._seed_marker_id)
            )
            row = result.fetchone()
        return bool(row)

    async def mark_static_seeded(self) -> None:
        await self._ensure_table()
        async with self.store.begin() as conn:
            await self.store.upsert(
                conn,
                self.table,
                values={
                    "id": self._seed_marker_id,
                    "name": self._seed_marker_id,
                    "payload_json": {},
                },
                pk_cols=["id"],
            )
