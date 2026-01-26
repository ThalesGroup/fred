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
from datetime import timedelta
from typing import Any

from temporalio.client import Client

from fred_core.scheduler.scheduler_structures import (
    SchedulerTask,
    SchedulerTaskProgress,
    TemporalSchedulerConfig,
    WorkflowHandle,
)
from fred_core.scheduler.temporal_codec import build_temporal_data_converter_from_env


class TemporalSchedulerService:
    def __init__(self, config: TemporalSchedulerConfig) -> None:
        self._config = config
        self._client: Client | None = None

    async def connect(self) -> Client:
        if self._client is not None:
            return self._client

        timeout = None
        if self._config.connect_timeout_seconds is not None:
            timeout = timedelta(seconds=self._config.connect_timeout_seconds)

        data_converter = build_temporal_data_converter_from_env()
        connect_kwargs: dict[str, Any] = {
            "target_host": self._config.host,
            "namespace": self._config.namespace,
        }
        if data_converter is not None:
            connect_kwargs["data_converter"] = data_converter

        connect_coro = Client.connect(**connect_kwargs)
        if timeout is not None:
            self._client = await asyncio.wait_for(
                connect_coro, timeout=timeout.total_seconds()
            )
        else:
            self._client = await connect_coro
        return self._client

    async def start_task(self, task: SchedulerTask) -> WorkflowHandle:
        client = await self.connect()
        workflow_id = (
            task.workflow_id or f"{self._config.workflow_id_prefix}-{task.task_id}"
        )
        task_queue = task.task_queue or self._config.task_queue
        workflow_input = task.get_workflow_input()
        start_args = [] if workflow_input is None else [workflow_input]

        start_kwargs: dict[str, Any] = {
            "id": workflow_id,
            "task_queue": task_queue,
            "memo": task.memo or None,
            "search_attributes": task.search_attributes or None,
        }
        if task.workflow_id_reuse_policy is not None:
            start_kwargs["id_reuse_policy"] = task.workflow_id_reuse_policy

        workflow_handle = await client.start_workflow(
            task.workflow_type,
            *start_args,
            **start_kwargs,
        )
        return WorkflowHandle(
            workflow_id=workflow_handle.id,
            run_id=workflow_handle.first_execution_run_id,
        )

    async def query_progress(
        self,
        workflow_id: str,
        run_id: str | None = None,
        query_name: str = "get_progress",
    ) -> SchedulerTaskProgress:
        client = await self.connect()
        handle = client.get_workflow_handle(workflow_id, run_id=run_id)
        progress = await handle.query(query_name)
        if isinstance(progress, SchedulerTaskProgress):
            return progress
        if isinstance(progress, dict):
            return SchedulerTaskProgress(**progress)
        return SchedulerTaskProgress(state="unknown", percent=0, message=str(progress))
