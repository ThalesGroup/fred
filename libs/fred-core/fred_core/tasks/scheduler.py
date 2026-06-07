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

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Protocol

if TYPE_CHECKING:
    from fred_core.scheduler import TemporalClientProvider

from pydantic import BaseModel

from fred_core.tasks.bus import IEventBus
from fred_core.tasks.models import ActivityContext

logger = logging.getLogger(__name__)

ActivityFn = Callable[..., Coroutine[Any, Any, None]]


class IScheduler(Protocol):
    async def submit(
        self,
        task_id: str,
        activity: ActivityFn,
        params: BaseModel,
        bus: IEventBus,
    ) -> None: ...

    async def cancel(self, task_id: str) -> None: ...


class MemoryScheduler:
    """
    Runs activities as asyncio tasks. No external services required.
    cancel() calls Task.cancel() for cooperative shutdown.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def submit(
        self,
        task_id: str,
        activity: ActivityFn,
        params: BaseModel,
        bus: IEventBus,
    ) -> None:
        ctx = ActivityContext(
            task_id=task_id,
            emit=bus.publish,
            heartbeat=lambda: None,
        )
        task = asyncio.create_task(
            activity(ctx, params),
            name=f"task-{task_id}",
        )
        self._tasks[task_id] = task

        def _cleanup(t: asyncio.Task[None]) -> None:
            self._tasks.pop(task_id, None)
            if exc := t.exception() if not t.cancelled() else None:
                logger.error("[MemoryScheduler] task %s failed: %s", task_id, exc)

        task.add_done_callback(_cleanup)

    async def cancel(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and not task.done():
            task.cancel()


class TemporalScheduler:
    """
    Submits a thin Temporal workflow that wraps a single activity.
    The workflow wrapper (not the activity) owns Temporal determinism constraints.
    """

    def __init__(
        self,
        client_provider: TemporalClientProvider,
        task_queue: str,
    ) -> None:
        self._client_provider = client_provider
        self._task_queue = task_queue

    async def submit(
        self,
        task_id: str,
        activity: ActivityFn,
        params: BaseModel,
        bus: IEventBus,
    ) -> None:
        from fred_core.tasks.temporal_workflow import (  # type: ignore[import]
            SingleActivityWorkflow,
        )

        client = await self._client_provider.get_client()
        await client.start_workflow(
            SingleActivityWorkflow.run,
            args=[task_id, activity.__name__, params.model_dump()],
            id=f"task-{task_id}",
            task_queue=self._task_queue,
        )

    async def cancel(self, task_id: str) -> None:
        from temporalio.client import WorkflowHandle  # type: ignore[import]

        client = await self._client_provider.get_client()
        handle: WorkflowHandle = client.get_workflow_handle(f"task-{task_id}")
        await handle.cancel()
