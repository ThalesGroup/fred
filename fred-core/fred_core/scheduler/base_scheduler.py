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

import threading
from abc import ABC, abstractmethod
from typing import Dict, Optional

from fred_core.scheduler.scheduler_structures import (
    SchedulerTask,
    SchedulerTaskProgress,
    WorkflowHandle,
)


class BaseScheduler(ABC):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handles_by_task_id: Dict[str, WorkflowHandle] = {}
        self._tasks_by_id: Dict[str, SchedulerTask] = {}
        self._last_handle_by_actor: Dict[str, WorkflowHandle] = {}
        self._last_task_by_actor: Dict[str, SchedulerTask] = {}

    @abstractmethod
    async def start_task(self, task: SchedulerTask) -> WorkflowHandle:
        raise NotImplementedError

    @abstractmethod
    async def get_progress(
        self,
        workflow_id: str,
        run_id: str | None = None,
        query_name: str = "get_progress",
    ) -> SchedulerTaskProgress:
        raise NotImplementedError

    def _register_task(self, task: SchedulerTask, handle: WorkflowHandle) -> None:
        with self._lock:
            self._handles_by_task_id[task.task_id] = handle
            self._tasks_by_id[task.task_id] = task
            actor_id = getattr(task, "caller_actor", None)
            if actor_id:
                self._last_handle_by_actor[actor_id] = handle
                self._last_task_by_actor[actor_id] = task

    def get_handle_for_task(self, task_id: str) -> Optional[WorkflowHandle]:
        with self._lock:
            return self._handles_by_task_id.get(task_id)

    def get_last_handle_for_actor(self, actor_id: str) -> Optional[WorkflowHandle]:
        with self._lock:
            return self._last_handle_by_actor.get(actor_id)

    async def get_progress_for_task(
        self,
        task_id: str,
        query_name: str | None = None,
    ) -> SchedulerTaskProgress:
        handle = self.get_handle_for_task(task_id)
        task = self._tasks_by_id.get(task_id)
        if not handle:
            return SchedulerTaskProgress(
                state="unknown", percent=0, message="unknown task"
            )
        if query_name is None:
            query_name = task.progress_query_name if task else "get_progress"
        return await self.get_progress(
            workflow_id=handle.workflow_id,
            run_id=handle.run_id,
            query_name=query_name,
        )

    async def get_progress_for_actor(
        self,
        actor_id: str,
        query_name: str | None = None,
    ) -> SchedulerTaskProgress:
        handle = self.get_last_handle_for_actor(actor_id)
        task = self._last_task_by_actor.get(actor_id)
        if not handle:
            return SchedulerTaskProgress(
                state="unknown", percent=0, message="unknown actor"
            )
        if query_name is None:
            query_name = task.progress_query_name if task else "get_progress"
        return await self.get_progress(
            workflow_id=handle.workflow_id,
            run_id=handle.run_id,
            query_name=query_name,
        )
