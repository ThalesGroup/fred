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

from fred_core.sql import (
    AsyncBaseSqlStore,
    advisory_lock_key,
    run_ddl_with_advisory_lock,
)
from pydantic import TypeAdapter
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select
from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_backend.core.feedback.feedback_structures import FeedbackRecord
from agentic_backend.core.feedback.store.base_feedback_store import BaseFeedbackStore

logger = logging.getLogger(__name__)

FeedbackAdapter = TypeAdapter(FeedbackRecord)


class PostgresFeedbackStore(BaseFeedbackStore):
    """
    PostgreSQL-backed feedback store using a single table.
    Mirrors the DuckDB/OpenSearch variants.
    """

    def __init__(self, engine: AsyncEngine, table_name: str, prefix: str = "feedback_"):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._ddl_lock_id = advisory_lock_key(self.table_name)
        self._create_task: asyncio.Task[None] | None = None

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("id", String, primary_key=True),
            Column("session_id", String, nullable=False),
            Column("message_id", String, nullable=False),
            Column("agent_id", String, nullable=False),
            Column("rating", Integer, nullable=False),
            Column("comment", Text, nullable=True),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("user_id", String, nullable=False),
            keep_existing=True,
        )

        try:
            loop = asyncio.get_running_loop()
            self._create_task = loop.create_task(self._create_table())
        except RuntimeError:
            logger.info(
                "[FEEDBACK][PG][ASYNC] Table bootstrap deferred until first async use: %s",
                self.table_name,
            )

    async def _create_table(self) -> None:
        await run_ddl_with_advisory_lock(
            engine=self.store.engine,
            lock_key=self._ddl_lock_id,
            ddl_sync_fn=self.table.metadata.create_all,
            logger=logger,
        )
        logger.info("[FEEDBACK][PG][ASYNC] Table ready: %s", self.table_name)

    async def _ensure_table(self) -> None:
        task = self._create_task
        if task is None:
            task = asyncio.get_running_loop().create_task(self._create_table())
            self._create_task = task
        await task

    async def list(self) -> List[FeedbackRecord]:
        await self._ensure_table()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table).order_by(self.table.c.created_at.desc())
            )
            rows = result.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get(self, feedback_id: str) -> Optional[FeedbackRecord]:
        await self._ensure_table()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table).where(self.table.c.id == feedback_id)
            )
            row = result.fetchone()
        return self._row_to_record(row) if row else None

    async def save(self, feedback: FeedbackRecord) -> None:
        await self._ensure_table()
        values = FeedbackAdapter.dump_python(feedback, mode="python", exclude_none=True)
        async with self.store.begin() as conn:
            await self.store.upsert(
                conn,
                self.table,
                values=values,
                pk_cols=["id"],
            )
        logger.info("[FEEDBACK][PG] Saved feedback entry '%s'", feedback.id)

    async def delete(self, feedback_id: str) -> None:
        await self._ensure_table()
        async with self.store.begin() as conn:
            result = await conn.execute(
                self.table.delete().where(self.table.c.id == feedback_id)
            )
        deleted = getattr(result, "rowcount", None)
        if deleted:
            logger.info("[FEEDBACK][PG] Deleted feedback entry '%s'", feedback_id)
        else:
            logger.warning(
                "[FEEDBACK][PG] Feedback entry '%s' not found for deletion",
                feedback_id,
            )

    def _row_to_record(self, row) -> FeedbackRecord:
        data = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        try:
            return FeedbackAdapter.validate_python(data)
        except Exception:
            logger.exception(
                "[FEEDBACK][PG] Failed to parse feedback row id=%s", data.get("id")
            )
            raise
