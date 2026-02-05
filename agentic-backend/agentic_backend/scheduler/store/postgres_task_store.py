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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from fred_core.sql import BaseSqlStore
from pydantic import TypeAdapter
from sqlalchemy import Column, Float, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.engine import Engine

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
        self, engine: Engine, table_name: str = "agent_tasks", prefix: str = "sched_"
    ):
        self.store = BaseSqlStore(engine, prefix=prefix)
        self.table_name = self.store.prefixed(table_name)

        metadata = MetaData()
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
            Column("context_json", JSONB, nullable=False),
            Column("parameters_json", JSONB, nullable=False),
            Column("last_message", String, nullable=True),
            Column("percent_complete", Float, nullable=False, default=0.0),
            Column("blocked_json", JSONB, nullable=True),
            Column("artifacts_json", JSONB, nullable=True),
            Column("error_json", JSONB, nullable=True),  # Standardized to _json
            keep_existing=True,
        )

        metadata.create_all(self.store.engine)
        logger.info("[SCHEDULER][PG] Agent tasks table ready: %s", self.table_name)

    def create(
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

        with self.store.begin() as conn:
            # Idempotent create: if the task already exists, return it untouched.
            existing = conn.execute(
                select(self.table).where(self.table.c.task_id == task_id)
            ).fetchone()
            if existing:
                return self._row_to_record(existing)
            conn.execute(self.table.insert().values(**values))

        return self.get(task_id)

    def get(self, task_id: str) -> AgentTaskRecordV1:
        with self.store.begin() as conn:
            row = conn.execute(
                select(self.table).where(self.table.c.task_id == task_id)
            ).fetchone()

        if not row:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")

        return self._row_to_record(row)

    def get_for_user(self, *, task_id: str, user_id: str) -> AgentTaskRecordV1:
        with self.store.begin() as conn:
            row = conn.execute(
                select(self.table).where(self.table.c.task_id == task_id)
            ).fetchone()

        if not row:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")

        if row._mapping.get("user_id") != user_id:
            raise AgentTaskForbiddenError(
                f"Task '{task_id}' is not owned by user '{user_id}'"
            )

        return self._row_to_record(row)

    def list_for_user(
        self,
        *,
        user_id: str,
        limit: int = 20,
        statuses: Optional[Sequence[AgentTaskStatus]] = None,
        target_agent: Optional[str] = None,
    ) -> List[AgentTaskRecordV1]:
        query = select(self.table).where(self.table.c.user_id == user_id)

        if statuses:
            query = query.where(
                self.table.c.status.in_([status.value for status in statuses])
            )

        if target_agent:
            query = query.where(self.table.c.target_agent == target_agent)

        query = query.order_by(self.table.c.created_at.desc()).limit(limit)

        with self.store.begin() as conn:
            rows = conn.execute(query).fetchall()

        return [self._row_to_record(row) for row in rows]

    def update_handle(
        self, *, task_id: str, workflow_id: str, run_id: Optional[str]
    ) -> None:
        values: Dict[str, Any] = {
            "workflow_id": workflow_id,
            "run_id": run_id,
            "updated_at": datetime.now(timezone.utc),
        }

        with self.store.begin() as conn:
            result = conn.execute(
                self.table.update()
                .where(self.table.c.task_id == task_id)
                .values(**values)
            )

        if result.rowcount == 0:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")

    def update_status(
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

        with self.store.begin() as conn:
            result = conn.execute(
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
