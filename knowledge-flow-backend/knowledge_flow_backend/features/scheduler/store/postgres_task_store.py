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
from typing import Optional

from fred_core.sql.async_session import make_session_factory, use_session
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from knowledge_flow_backend.features.scheduler.store.base_task_store import BaseWorkflowTaskStore
from knowledge_flow_backend.features.scheduler.store.task_models import WorkflowTaskRow
from knowledge_flow_backend.features.scheduler.store.task_structures import (
    WorkflowTaskNotFoundError,
    WorkflowTaskRecord,
    WorkflowTaskStatus,
)

logger = logging.getLogger(__name__)


class PostgresWorkflowTaskStore(BaseWorkflowTaskStore):
    """PostgreSQL-backed workflow task tracking store using declarative ORM."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def upsert_current_document(
        self,
        *,
        workflow_id: str,
        document_uid: Optional[str],
        filename: Optional[str],
        session: AsyncSession | None = None,
    ) -> WorkflowTaskRecord:
        now = datetime.now(timezone.utc)
        async with use_session(self._sessions, session) as s:
            row = await s.get(WorkflowTaskRow, workflow_id)
            if row is not None:
                row.current_document_uid = document_uid
                row.current_filename = filename
                row.status = WorkflowTaskStatus.RUNNING.value
                row.updated_at = now
            else:
                row = WorkflowTaskRow(
                    workflow_id=workflow_id,
                    current_document_uid=document_uid,
                    current_filename=filename,
                    status=WorkflowTaskStatus.RUNNING.value,
                    created_at=now,
                    updated_at=now,
                )
                s.add(row)
            # Keep a local copy to return after the session closes
            record = self._row_to_record(row)
        return record

    async def update_status(
        self,
        *,
        workflow_id: str,
        status: WorkflowTaskStatus,
        last_error: Optional[str] = None,
        session: AsyncSession | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with use_session(self._sessions, session) as s:
            row = await s.get(WorkflowTaskRow, workflow_id)
            if row is not None:
                row.status = status.value
                row.last_error = last_error
                row.updated_at = now
            else:
                row = WorkflowTaskRow(
                    workflow_id=workflow_id,
                    current_document_uid=None,
                    current_filename=None,
                    status=status.value,
                    last_error=last_error,
                    created_at=now,
                    updated_at=now,
                )
                s.add(row)

    async def get(self, workflow_id: str, session: AsyncSession | None = None) -> WorkflowTaskRecord:
        async with use_session(self._sessions, session) as s:
            row = await s.get(WorkflowTaskRow, workflow_id)
        if row is None:
            raise WorkflowTaskNotFoundError(f"Workflow '{workflow_id}' not found")
        return self._row_to_record(row)

    @staticmethod
    def _row_to_record(row: WorkflowTaskRow) -> WorkflowTaskRecord:
        return WorkflowTaskRecord(
            workflow_id=row.workflow_id,
            current_document_uid=row.current_document_uid,
            current_filename=row.current_filename,
            status=WorkflowTaskStatus(row.status),
            last_error=row.last_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
