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

from typing import Dict

from fred_core.scheduler.base_scheduler import BaseScheduler
from fred_core.scheduler.scheduler_structures import (
    SchedulerTask,
    SchedulerTaskProgress,
    WorkflowHandle,
)


class InMemoryScheduler(BaseScheduler):
    def __init__(self) -> None:
        super().__init__()
        self._progress_by_workflow: Dict[str, SchedulerTaskProgress] = {}

    async def start_task(self, task: SchedulerTask) -> WorkflowHandle:
        handle = WorkflowHandle(workflow_id=f"in-memory-{task.task_id}")
        self._register_task(task, handle)
        self._progress_by_workflow[handle.workflow_id] = SchedulerTaskProgress(
            state="completed",
            percent=100,
            message="completed locally",
        )
        return handle

    async def get_progress(
        self,
        workflow_id: str,
        run_id: str | None = None,
        query_name: str = "get_progress",
    ) -> SchedulerTaskProgress:
        return self._progress_by_workflow.get(
            workflow_id,
            SchedulerTaskProgress(state="unknown", percent=0),
        )
