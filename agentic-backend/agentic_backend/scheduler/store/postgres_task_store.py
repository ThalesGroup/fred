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
from typing import Any, Dict, List, Optional, Sequence

from fred_core.sql import (
    AsyncBaseSqlStore,
    advisory_lock_key,
    json_for_engine,
    run_ddl_with_advisory_lock,
)
from pydantic import TypeAdapter
from sqlalchemy import Column, Float, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_backend.scheduler.agent_contracts import AgentContextRefsV1
from agentic_backend.scheduler.task_structures import (
    AgentTaskForbiddenError,
    AgentTaskNotFoundError,
    AgentTaskRecordV1,
    AgentTaskStatus,
)

from .base_task_store import BaseAgentTaskStore

logger = logging.getLogger(__name__)

# Used for explicit validation to satisfy type checkers
AgentContextAdapter = TypeAdapter(AgentContextRefsV1)


class PostgresAgentTaskStore(BaseAgentTaskStore):
    """
    PostgreSQL-backed Agent Task registry.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        table_name: str = "agent_tasks",
        prefix: str = "sched_",
    ):
        self.store = AsyncBaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)
        self._ddl_lock_id = advisory_lock_key(self.table_name)

        metadata = MetaData()
        json_type = json_for_engine(self.store.engine)
        self.table = Table(
            self.table_name,
            metadata,
            Column("task_id", String, primary_key=True),
            Column("user_id", String, index=True, nullable=False),
            Column("target_agent", String, index=True, nullable=False),
            Column("request_text", String, nullable=False),
            Column("workflow_id", String, unique=True, index=True, nullable=False),
            Column("run_id", String, nullable=True),
            Column("status", String, index=True, nullable=False),
            Column("created_at", TIMESTAMP(timezone=True), nullable=False),
            Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
            Column("context_json", json_type, nullable=False),
            Column("parameters_json", json_type, nullable=False),
            Column("last_message", String, nullable=True),
            Column("percent_complete", Float, nullable=False, default=0.0),
            Column("blocked_json", json_type, nullable=True),
            Column("artifacts_json", json_type, nullable=True),
            Column("error_json", json_type, nullable=True),  # Standardized to _json
            keep_existing=True,
        )

        async def _create():
            await run_ddl_with_advisory_lock(
                engine=self.store.engine,
                lock_key=self._ddl_lock_id,
                ddl_sync_fn=metadata.create_all,
                logger=logger,
            )

        # Kick off table creation without blocking callers.
        try:
            loop = asyncio.get_running_loop()
            self._create_task = loop.create_task(_create())
        except RuntimeError:
            self._create_task = None
            asyncio.run(_create())

        logger.info(
            "[SCHEDULER][PG][ASYNC] Agent tasks table ready: %s", self.table_name
        )

    async def _ensure_table(self) -> None:
        task = getattr(self, "_create_task", None)
        if task is not None and not task.done():
            await task

    async def create(
        self,
        *,
        task_id: str,
        user_id: str,
        target_agent: str,
        request_text: str,
        workflow_id: str,
        run_id: Optional[str] = None,
        context: Optional[AgentContextRefsV1] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AgentTaskRecordV1:
        await self._ensure_table()
        now = datetime.now(timezone.utc)
        ctx_obj = context or AgentContextRefsV1()

        values = {
            "task_id": task_id,
            "user_id": user_id,
            "target_agent": target_agent,
            "request_text": request_text,
            "workflow_id": workflow_id,
            "run_id": run_id,
            "status": AgentTaskStatus.QUEUED.value,
            "created_at": now,
            "updated_at": now,
            "context_json": AgentContextAdapter.dump_python(ctx_obj, mode="json"),
            "parameters_json": parameters or {},
            "percent_complete": 0.0,
        }

        async with self.store.begin() as conn:
            # Idempotent create: if the task already exists, return it untouched.
            existing_result = await conn.execute(
                select(self.table).where(self.table.c.task_id == task_id)
            )
            existing = existing_result.fetchone()
            if existing:
                return self._row_to_record(existing)
            await conn.execute(self.table.insert().values(**values))

        return await self.get(task_id)

    async def get(self, task_id: str) -> AgentTaskRecordV1:
        await self._ensure_table()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table).where(self.table.c.task_id == task_id)
            )
            row = result.fetchone()

        if not row:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")

        return self._row_to_record(row)

    async def get_for_user(self, *, task_id: str, user_id: str) -> AgentTaskRecordV1:
        await self._ensure_table()
        async with self.store.begin() as conn:
            result = await conn.execute(
                select(self.table).where(self.table.c.task_id == task_id)
            )
            row = result.fetchone()

        if not row:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")

        if row._mapping.get("user_id") != user_id:
            raise AgentTaskForbiddenError(
                f"Task '{task_id}' is not owned by user '{user_id}'"
            )

        return self._row_to_record(row)

    async def list_for_user(
        self,
        *,
        user_id: str,
        limit: int = 20,
        statuses: Optional[Sequence[AgentTaskStatus]] = None,
        target_agent: Optional[str] = None,
    ) -> List[AgentTaskRecordV1]:
        await self._ensure_table()
        query = select(self.table).where(self.table.c.user_id == user_id)

        if statuses:
            query = query.where(
                self.table.c.status.in_([status.value for status in statuses])
            )

        if target_agent:
            query = query.where(self.table.c.target_agent == target_agent)

        query = query.order_by(self.table.c.created_at.desc()).limit(limit)

        async with self.store.begin() as conn:
            result = await conn.execute(query)
            rows = result.fetchall()

        return [self._row_to_record(row) for row in rows]

    async def update_handle(
        self, *, task_id: str, workflow_id: str, run_id: Optional[str]
    ) -> None:
        await self._ensure_table()
        values: Dict[str, Any] = {
            "workflow_id": workflow_id,
            "run_id": run_id,
            "updated_at": datetime.now(timezone.utc),
        }

        async with self.store.begin() as conn:
            result = await conn.execute(
                self.table.update()
                .where(self.table.c.task_id == task_id)
                .values(**values)
            )

        if result.rowcount == 0:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")

    async def update_status(
        self,
        *,
        task_id: str,
        status: AgentTaskStatus,
        last_message: Optional[str] = None,
        percent_complete: Optional[float] = None,
        blocked: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[str]] = None,
        error_json: Optional[Dict[str, Any]] = None,  # Corrected parameter name
    ) -> None:
        await self._ensure_table()
        values: Dict[str, Any] = {
            "status": status.value,
            "updated_at": datetime.now(timezone.utc),
        }

        if last_message is not None:
            values["last_message"] = last_message
        if percent_complete is not None:
            values["percent_complete"] = percent_complete
        if blocked is not None:
            values["blocked_json"] = blocked
        if artifacts is not None:
            values["artifacts_json"] = artifacts
        if error_json is not None:
            values["error_json"] = error_json

        async with self.store.begin() as conn:
            result = await conn.execute(
                self.table.update()
                .where(self.table.c.task_id == task_id)
                .values(**values)
            )
        if result.rowcount == 0:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")

    def _row_to_record(self, row: Any) -> AgentTaskRecordV1:
        m = dict(row._mapping)

        # Explicit validation to satisfy static analysis
        context_data = m.get("context_json") or {}
        validated_context = AgentContextAdapter.validate_python(context_data)

        return AgentTaskRecordV1(
            task_id=m["task_id"],
            user_id=m["user_id"],
            target_agent=m["target_agent"],
            status=AgentTaskStatus(m["status"]),
            request_text=m["request_text"],
            context=validated_context,
            parameters=m.get("parameters_json") or {},
            workflow_id=m["workflow_id"],
            run_id=m.get("run_id"),
            last_message=m.get("last_message"),
            percent_complete=m.get("percent_complete") or 0.0,
            artifacts=m.get("artifacts_json") or [],
            error_details=m.get(
                "error_json"
            ),  # Maps DB error_json to Pydantic error_details
            blocked_details=m.get("blocked_json"),
            created_at=m["created_at"],
            updated_at=m["updated_at"],
        )
