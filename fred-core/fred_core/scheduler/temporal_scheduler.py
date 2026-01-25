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

from fred_core.scheduler.base_scheduler import BaseScheduler
from fred_core.scheduler.scheduler_structures import (
    SchedulerTask,
    SchedulerTaskProgress,
    TemporalSchedulerConfig,
    WorkflowHandle,
)
from fred_core.scheduler.temporal_service import TemporalSchedulerService


class TemporalScheduler(BaseScheduler):
    def __init__(
        self,
        config: TemporalSchedulerConfig,
        service: TemporalSchedulerService | None = None,
    ) -> None:
        super().__init__()
        self._service = service or TemporalSchedulerService(config)

    async def start_task(self, task: SchedulerTask) -> WorkflowHandle:
        handle = await self._service.start_task(task)
        self._register_task(task, handle)
        return handle

    async def get_progress(
        self,
        workflow_id: str,
        run_id: str | None = None,
        query_name: str = "get_progress",
    ) -> SchedulerTaskProgress:
        return await self._service.query_progress(
            workflow_id=workflow_id,
            run_id=run_id,
            query_name=query_name,
        )
