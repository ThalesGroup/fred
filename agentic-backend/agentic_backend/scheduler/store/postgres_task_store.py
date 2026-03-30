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
from typing import Any, Dict, List, Optional, Sequence, cast

from fred_core.sql.async_session import make_session_factory, use_session
from pydantic import TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from agentic_backend.scheduler.agent_contracts import AgentContextRefsV1
from agentic_backend.scheduler.store.task_models import AgentTaskRow
from agentic_backend.scheduler.task_structures import (
    AgentTaskForbiddenError,
    AgentTaskNotFoundError,
    AgentTaskRecordV1,
    AgentTaskStatus,
)

from .base_task_store import BaseAgentTaskStore

logger = logging.getLogger(__name__)

AgentContextAdapter = TypeAdapter(AgentContextRefsV1)


class PostgresAgentTaskStore(BaseAgentTaskStore):
    """
    PostgreSQL-backed Agent Task registry (ORM sessions).
    """

    def __init__(self, engine: AsyncEngine):
        self._sessions = make_session_factory(engine)

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
        session: AsyncSession | None = None,
    ) -> AgentTaskRecordV1:
        now = datetime.now(timezone.utc)
        ctx_obj = context or AgentContextRefsV1()

        async with use_session(self._sessions, session) as s:
            existing = await s.get(AgentTaskRow, task_id)
            if existing:
                return self._row_to_record(existing)

            row = AgentTaskRow(
                task_id=task_id,
                user_id=user_id,
                target_agent=target_agent,
                request_text=request_text,
                workflow_id=workflow_id,
                run_id=run_id,
                status=AgentTaskStatus.QUEUED.value,
                created_at=now,
                updated_at=now,
                context_json=AgentContextAdapter.dump_python(ctx_obj, mode="json"),
                parameters_json=parameters or {},
                percent_complete=0.0,
            )
            s.add(row)
            await s.flush()
            return self._row_to_record(row)

    async def get(
        self, task_id: str, session: AsyncSession | None = None
    ) -> AgentTaskRecordV1:
        async with use_session(self._sessions, session) as s:
            row = await s.get(AgentTaskRow, task_id)
        if row is None:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")
        return self._row_to_record(row)

    async def get_for_user(
        self, *, task_id: str, user_id: str, session: AsyncSession | None = None
    ) -> AgentTaskRecordV1:
        async with use_session(self._sessions, session) as s:
            row = await s.get(AgentTaskRow, task_id)
        if row is None:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")
        if row.user_id != user_id:
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
        session: AsyncSession | None = None,
    ) -> List[AgentTaskRecordV1]:
        query = select(AgentTaskRow).where(AgentTaskRow.user_id == user_id)
        if statuses:
            query = query.where(AgentTaskRow.status.in_([s.value for s in statuses]))
        if target_agent:
            query = query.where(AgentTaskRow.target_agent == target_agent)
        query = query.order_by(AgentTaskRow.created_at.desc()).limit(limit)

        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(query)).scalars().all()
        return [self._row_to_record(row) for row in rows]

    async def update_handle(
        self,
        *,
        task_id: str,
        workflow_id: str,
        run_id: Optional[str],
        session: AsyncSession | None = None,
    ) -> None:
        async with use_session(self._sessions, session) as s:
            result = cast(
                CursorResult,
                await s.execute(
                    update(AgentTaskRow)
                    .where(AgentTaskRow.task_id == task_id)
                    .values(
                        workflow_id=workflow_id,
                        run_id=run_id,
                        updated_at=datetime.now(timezone.utc),
                    )
                ),
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
        error_json: Optional[Dict[str, Any]] = None,
        session: AsyncSession | None = None,
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

        async with use_session(self._sessions, session) as s:
            result = cast(
                CursorResult,
                await s.execute(
                    update(AgentTaskRow)
                    .where(AgentTaskRow.task_id == task_id)
                    .values(**values)
                ),
            )
        if result.rowcount == 0:
            raise AgentTaskNotFoundError(f"Task '{task_id}' not found")

    def _row_to_record(self, row: AgentTaskRow) -> AgentTaskRecordV1:
        validated_context = AgentContextAdapter.validate_python(row.context_json or {})
        return AgentTaskRecordV1(
            task_id=row.task_id,
            user_id=row.user_id,
            target_agent=row.target_agent,
            status=AgentTaskStatus(row.status),
            request_text=row.request_text,
            context=validated_context,
            parameters=row.parameters_json or {},
            workflow_id=row.workflow_id,
            run_id=row.run_id,
            last_message=row.last_message,
            percent_complete=row.percent_complete or 0.0,
            artifacts=row.artifacts_json or [],
            error_details=row.error_json,
            blocked_details=row.blocked_json,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
