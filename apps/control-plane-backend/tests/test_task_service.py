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

from pathlib import Path

import pytest
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.models.task_models import TASK_TABLES
from fred_core.scheduler import SchedulerBackend
from fred_core.tasks.models import (
    StartIngestionParams,
    StartIngestionRequest,
    TaskState,
)
from fred_core.tasks.service import TaskService
from fred_core.tasks.store import TaskNotFoundError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    db_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)
    return engine


@pytest.mark.asyncio
@pytest.mark.parametrize("created_by", ["user-1", None])
async def test_task_service_start_creates_task_run(
    tmp_path: Path, created_by: str | None
) -> None:
    engine = await _make_engine(tmp_path, f"svc_start_{created_by}.sqlite3")
    try:
        service = TaskService.build(
            engine=engine, tables=TASK_TABLES, backend=SchedulerBackend.MEMORY
        )
        req = StartIngestionRequest(params=StartIngestionParams(resource_ids=["doc1"]))
        response = await service.start(req, created_by=created_by)

        assert response.task_id
        row = await service.get_run(response.task_id)
        assert row is not None
        assert row.kind == "ingestion"
        assert row.state == TaskState.pending
        assert row.created_by == created_by
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_service_cancel_unknown_task_raises(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "svc_cancel.sqlite3")
    try:
        service = TaskService.build(
            engine=engine, tables=TASK_TABLES, backend=SchedulerBackend.MEMORY
        )
        with pytest.raises(TaskNotFoundError):
            await service.cancel("nonexistent-id")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_service_replay_empty_before_any_events(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "svc_replay.sqlite3")
    try:
        service = TaskService.build(
            engine=engine, tables=TASK_TABLES, backend=SchedulerBackend.MEMORY
        )
        req = StartIngestionRequest(params=StartIngestionParams(resource_ids=["doc1"]))
        response = await service.start(req, created_by=None)

        events = await service.replay(response.task_id, after_seq=-1)
        assert events == []
    finally:
        await engine.dispose()
