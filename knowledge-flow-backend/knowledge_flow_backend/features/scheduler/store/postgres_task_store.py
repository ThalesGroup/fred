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
from datetime import datetime, timezone
from typing import Optional

from fred_core.sql import (
    AsyncBaseSqlStore,
    advisory_lock_key,
    run_ddl_with_advisory_lock,
)
from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncEngine

from knowledge_flow_backend.features.scheduler.store.base_task_store import BaseWorkflowTaskStore
from knowledge_flow_backend.features.scheduler.store.task_structures import (
    WorkflowTaskNotFoundError,
    WorkflowTaskRecord,
    WorkflowTaskStatus,
)

logger = logging.getLogger(__name__)


class PostgresWorkflowTaskStore(BaseWorkflowTaskStore):
    """
    PostgreSQL-backed workflow task tracking store.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        table_name: str = "workflow_tasks",
        prefix: str = "sched_",
    ) -> None:
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._ddl_lock_id = advisory_lock_key(self.table_name)

        metadata = MetaData()
        self.table = Table(
            self.table_name,
            metadata,
            Column("workflow_id", String, primary_key=True),
            Column("current_document_uid", String, nullable=True),
            Column("current_filename", String, nullable=True),
            Column("status", String, nullable=False),
            Column("last_error", String, nullable=True),
            Column("created_at", TIMESTAMP(timezone=True), nullable=False),
            Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
            keep_existing=True,
        )

        async def _create():
            await run_ddl_with_advisory_lock(
                engine=self.store.engine,
                lock_key=self._ddl_lock_id,
                ddl_sync_fn=metadata.create_all,
                logger=logger,
            )

        try:
            loop = asyncio.get_running_loop()
            self._create_task = loop.create_task(_create())
        except RuntimeError:
            self._create_task = None
            asyncio.run(_create())

        logger.info("[SCHEDULER][PG][ASYNC] Workflow tasks table ready: %s", self.table_name)

    async def _ensure_table(self) -> None:
        task = getattr(self, "_create_task", None)
        if task is not None and not task.done():
            await task

    async def upsert_current_document(
        self,
        *,
        workflow_id: str,
        document_uid: Optional[str],
        filename: Optional[str],
    ) -> WorkflowTaskRecord:
        await self._ensure_table()
        now = datetime.now(timezone.utc)
        async with self.store.begin() as conn:
            existing_result = await conn.execute(select(self.table).where(self.table.c.workflow_id == workflow_id))
            existing = existing_result.fetchone()
            if existing:
                await conn.execute(
                    self.table.update()
                    .where(self.table.c.workflow_id == workflow_id)
                    .values(
                        current_document_uid=document_uid,
                        current_filename=filename,
                        status=WorkflowTaskStatus.RUNNING.value,
                        updated_at=now,
                    )
                )
            else:
                await conn.execute(
                    self.table.insert().values(
                        workflow_id=workflow_id,
                        current_document_uid=document_uid,
                        current_filename=filename,
                        status=WorkflowTaskStatus.RUNNING.value,
                        created_at=now,
                        updated_at=now,
                    )
                )

        return await self.get(workflow_id)

    async def update_status(
        self,
        *,
        workflow_id: str,
        status: WorkflowTaskStatus,
        last_error: Optional[str] = None,
    ) -> None:
        await self._ensure_table()
        now = datetime.now(timezone.utc)
        async with self.store.begin() as conn:
            existing_result = await conn.execute(select(self.table).where(self.table.c.workflow_id == workflow_id))
            existing = existing_result.fetchone()
            if existing:
                await conn.execute(
                    self.table.update()
                    .where(self.table.c.workflow_id == workflow_id)
                    .values(
                        status=status.value,
                        last_error=last_error,
                        updated_at=now,
                    )
                )
            else:
                await conn.execute(
                    self.table.insert().values(
                        workflow_id=workflow_id,
                        current_document_uid=None,
                        current_filename=None,
                        status=status.value,
                        last_error=last_error,
                        created_at=now,
                        updated_at=now,
                    )
                )

    async def get(self, workflow_id: str) -> WorkflowTaskRecord:
        await self._ensure_table()
        async with self.store.begin() as conn:
            result = await conn.execute(select(self.table).where(self.table.c.workflow_id == workflow_id))
            row = result.fetchone()

        if not row:
            raise WorkflowTaskNotFoundError(f"Workflow '{workflow_id}' not found")

        return self._row_to_record(row)

    def _row_to_record(self, row) -> WorkflowTaskRecord:
        data = row._mapping
        return WorkflowTaskRecord(
            workflow_id=data["workflow_id"],
            current_document_uid=data.get("current_document_uid"),
            current_filename=data.get("current_filename"),
            status=WorkflowTaskStatus(data["status"]),
            last_error=data.get("last_error"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
