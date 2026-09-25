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

"""Migration-task concurrency guard (CONTROL-PLANE-PRODUCT-CONTRACT.md §27).

`POST /import` and `POST /reset` must both refuse to start while another
migration task (import / reset) is still running or pending — two concurrent
migration-affecting calls on the same instance is exactly the scenario an
operator cannot safely reason about.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import pytest
from control_plane_backend.import_export.api import _reject_if_migration_task_active
from fastapi import HTTPException
from fred_core.tasks.models import TaskListResponse, TaskState, TaskSummary
from fred_core.tasks.service import TaskService


class FakeTaskService:
    def __init__(self, tasks: list[TaskSummary]) -> None:
        self._tasks = tasks

    async def list_tasks(self, **_kwargs: Any) -> TaskListResponse:
        return TaskListResponse(tasks=self._tasks)


def _running_migration_task(task_id: str = "task-1") -> TaskSummary:
    now = datetime.now(timezone.utc)
    return TaskSummary(
        task_id=task_id,
        kind="migration",
        state=TaskState.running,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_rejects_when_a_migration_task_is_active() -> None:
    fake = FakeTaskService([_running_migration_task()])
    with pytest.raises(HTTPException) as exc_info:
        await _reject_if_migration_task_active(cast(TaskService, fake))
    assert exc_info.value.status_code == 409
    assert "task-1" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_allows_when_no_migration_task_is_active() -> None:
    fake = FakeTaskService([])
    await _reject_if_migration_task_active(cast(TaskService, fake))  # no raise
