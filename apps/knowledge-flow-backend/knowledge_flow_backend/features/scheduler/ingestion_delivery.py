# Copyright Thales 2026
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

"""Atomic document admission and retryable delivery of ingestion batches."""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4
from weakref import WeakKeyDictionary

from fastapi import BackgroundTasks
from fred_core import KeycloakUser
from fred_core.sql import make_session_factory
from fred_core.tasks.models import TaskState, TaskTarget
from fred_core.tasks.service import TaskService
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from knowledge_flow_backend.features.scheduler.base_scheduler import BaseScheduler, WorkflowHandle
from knowledge_flow_backend.features.scheduler.scheduler_structures import PipelineDefinition
from knowledge_flow_backend.models.task_models import ACTIVE_DOCUMENT_INDEX, IngestionSubmissionRow, KfTaskRunRow

logger = logging.getLogger(__name__)

_memory_delivery_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()


class IngestionAlreadyActive(ValueError):
    pass


class IngestionDelivery:
    def __init__(self, engine: AsyncEngine, task_service: TaskService, scheduler: BaseScheduler) -> None:
        self.sessions = make_session_factory(engine)
        self.tasks = task_service
        self.scheduler = scheduler

    async def admit(self, user: KeycloakUser, definition: PipelineDefinition, team_ids: dict[str, str | None]) -> str:
        if not definition.files:
            raise ValueError("At least one document is required")
        definition.workflow_id = f"ingestion-{uuid4()}"
        try:
            async with self.sessions.begin() as session:
                for file in definition.files:
                    uid = file.to_virtual_metadata().document_uid if file.is_pull() else file.document_uid
                    if not uid:
                        raise ValueError("A document UID is required for ingestion")
                    if file.task_id:
                        # Internal source synchronization already created this task.
                        run = await session.get(KfTaskRunRow, file.task_id, with_for_update=True)
                        if (
                            run is None
                            or run.kind != "ingestion"
                            or TaskState(run.state).is_terminal
                            or run.created_by != user.uid
                            or not run.target
                            or run.target.get("type") != "document"
                            or run.target.get("id") != uid
                        ):
                            raise ValueError("Invalid existing ingestion task")
                        if run.execution_id is not None:
                            raise IngestionAlreadyActive("This ingestion task has already been submitted")
                        run.execution_id = definition.workflow_id
                    else:
                        file.task_id = self.tasks.store.new_task_id()
                        await self.tasks.store.create(
                            task_id=file.task_id,
                            kind="ingestion",
                            created_by=user.uid,
                            team_id=team_ids.get(uid),
                            target=TaskTarget(type="document", id=uid, label=file.display_name or uid),
                            execution_id=definition.workflow_id,
                            session=session,
                        )
                session.add(IngestionSubmissionRow(workflow_id=definition.workflow_id, definition=definition.model_dump(mode="json")))
        except IntegrityError as exc:
            if ACTIVE_DOCUMENT_INDEX in str(exc.orig):
                raise IngestionAlreadyActive("An ingestion is already active for one of these documents. Refresh its task status before retrying.") from exc
            raise
        return definition.workflow_id

    async def deliver(self, workflow_id: str, background_tasks: BackgroundTasks | None = None) -> WorkflowHandle:
        from knowledge_flow_backend.features.scheduler.in_memory_scheduler import InMemoryScheduler

        memory = isinstance(self.scheduler, InMemoryScheduler)
        if memory and background_tasks is not None:
            background_tasks.add_task(self.deliver, workflow_id)
            return WorkflowHandle(workflow_id=workflow_id)
        if memory:
            return await self._deliver_memory(workflow_id)
        async with self.sessions.begin() as session:
            row = await session.scalar(select(IngestionSubmissionRow).where(IngestionSubmissionRow.workflow_id == workflow_id).with_for_update(skip_locked=True))
            if row is None:
                return WorkflowHandle(workflow_id=workflow_id)
            row.attempted_at = datetime.now(timezone.utc)
            try:
                definition = PipelineDefinition.model_validate(row.definition)
            except ValueError:
                row.last_error = "Invalid persisted ingestion payload"
                logger.warning("Invalid pending ingestion %s", workflow_id)
                return WorkflowHandle(workflow_id=workflow_id)
            try:
                handle = await self.scheduler.start_document_processing(
                    user=definition.files[0].processed_by,
                    definition=definition,
                    background_tasks=background_tasks,
                )
            except Exception as exc:
                # A timeout can mean Temporal accepted the workflow. Keep both
                # the reservation and its immutable payload for an idempotent retry.
                row.last_error = type(exc).__name__
                logger.warning("Ingestion delivery deferred for %s", workflow_id, exc_info=True)
                return WorkflowHandle(workflow_id=workflow_id)
            await session.execute(delete(IngestionSubmissionRow).where(IngestionSubmissionRow.workflow_id == workflow_id))
            return handle

    async def _deliver_memory(self, workflow_id: str) -> WorkflowHandle:
        # Memory mode is local-only. Serialize its deliveries without holding
        # a pooled SQL connection while activities acquire their own sessions.
        lock = _memory_delivery_locks.setdefault(asyncio.get_running_loop(), asyncio.Lock())
        async with lock:
            async with self.sessions() as session:
                row = await session.get(IngestionSubmissionRow, workflow_id)
                if row is None:
                    return WorkflowHandle(workflow_id=workflow_id)
                definition = PipelineDefinition.model_validate(row.definition)
            pending = []
            for file in definition.files:
                run = await self.tasks.store.get_run(file.task_id) if file.task_id else None
                if run is not None and not TaskState(run.state).is_terminal:
                    pending.append(file)
            definition.files = pending
            if pending:
                await self.scheduler.start_document_processing(user=pending[0].processed_by, definition=definition)
            async with self.sessions.begin() as session:
                await session.execute(delete(IngestionSubmissionRow).where(IngestionSubmissionRow.workflow_id == workflow_id))
            return WorkflowHandle(workflow_id=workflow_id)

    async def retry_pending(self) -> None:
        seen: set[str] = set()
        deadline = asyncio.get_running_loop().time() + 20
        while len(seen) < 200 and asyncio.get_running_loop().time() < deadline:
            async with self.sessions() as session:
                query = select(IngestionSubmissionRow.workflow_id).where(IngestionSubmissionRow.workflow_id.not_in(seen)).order_by(IngestionSubmissionRow.attempted_at.asc().nullsfirst()).limit(8)
                ids = list(await session.scalars(query))
            if not ids:
                return
            seen.update(ids)
            results = await asyncio.gather(*(self.deliver(workflow_id) for workflow_id in ids), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    logger.warning("Pending ingestion delivery could not complete: %s", type(result).__name__)
