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

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from fred_core.scheduler import SchedulerBackend, TemporalClientProvider
from fred_core.tasks.bus import IEventBus, MemoryEventBus, PostgresEventBus
from fred_core.tasks.models import (
    StartTaskRequest,
    StartTaskResponse,
    TaskEvent,
    TaskListResponse,
)
from fred_core.tasks.orm_models import TaskRunRow
from fred_core.tasks.scheduler import IScheduler, MemoryScheduler, TemporalScheduler
from fred_core.tasks.store import TaskNotFoundError, TaskStore

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(
        self,
        store: TaskStore,
        bus: IEventBus,
        scheduler: IScheduler,
    ) -> None:
        self.store = store
        self.bus = bus
        self._scheduler = scheduler

    @classmethod
    def build(
        cls,
        engine: AsyncEngine,
        backend: SchedulerBackend,
        default_task_queue: str = "tasks",
        temporal_client_provider: TemporalClientProvider | None = None,
        postgres_dsn: str | None = None,
    ) -> "TaskService":
        store = TaskStore(engine)
        if backend == SchedulerBackend.TEMPORAL:
            if temporal_client_provider is None:
                raise ValueError(
                    "temporal_client_provider required for TEMPORAL backend"
                )
            bus: IEventBus = PostgresEventBus(postgres_dsn or "")
            scheduler: IScheduler = TemporalScheduler(
                client_provider=temporal_client_provider,
                task_queue=default_task_queue,
            )
        else:
            bus = MemoryEventBus()
            scheduler = MemoryScheduler()
        return cls(store=store, bus=bus, scheduler=scheduler)

    async def start(
        self,
        request: StartTaskRequest,
        created_by: str | None,
        team_id: str | None = None,
    ) -> StartTaskResponse:
        task_id = self.store.new_task_id()
        await self.store.create(
            task_id=task_id,
            kind=request.kind,
            created_by=created_by,
            team_id=team_id,
        )
        logger.info("[TaskService] starting task_id=%s kind=%s", task_id, request.kind)
        return StartTaskResponse(task_id=task_id)

    async def cancel(self, task_id: str) -> None:
        run = await self.store.get_run(task_id)
        if run is None:
            raise TaskNotFoundError(task_id)
        await self._scheduler.cancel(task_id)

    async def get_run(self, task_id: str) -> TaskRunRow | None:
        return await self.store.get_run(task_id)

    async def replay(self, task_id: str, after_seq: int) -> list[TaskEvent]:
        return await self.store.replay_events(task_id, after_seq)

    async def record(self, event: TaskEvent) -> None:
        assigned_seq = await self.store.record_event(event)
        await self.bus.publish(event.model_copy(update={"seq": assigned_seq}))

    async def list_tasks(
        self,
        *,
        team_id: str | None = None,
        kind: str | None = None,
        state: str | None = None,
    ) -> TaskListResponse:
        summaries = await self.store.list_tasks(team_id=team_id, kind=kind, state=state)
        return TaskListResponse(tasks=summaries)
