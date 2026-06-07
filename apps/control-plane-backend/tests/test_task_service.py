from __future__ import annotations

from pathlib import Path

import pytest
from fred_core.models import Base as CoreBase
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
    import fred_core.tasks.orm_models  # noqa: F401

    db_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
    return engine


@pytest.mark.asyncio
@pytest.mark.parametrize("created_by", ["user-1", None])
async def test_task_service_start_creates_task_run(
    tmp_path: Path, created_by: str | None
) -> None:
    engine = await _make_engine(tmp_path, f"svc_start_{created_by}.sqlite3")
    try:
        service = TaskService.build(engine=engine, backend=SchedulerBackend.MEMORY)
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
        service = TaskService.build(engine=engine, backend=SchedulerBackend.MEMORY)
        with pytest.raises(TaskNotFoundError):
            await service.cancel("nonexistent-id")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_service_replay_empty_before_any_events(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "svc_replay.sqlite3")
    try:
        service = TaskService.build(engine=engine, backend=SchedulerBackend.MEMORY)
        req = StartIngestionRequest(params=StartIngestionParams(resource_ids=["doc1"]))
        response = await service.start(req, created_by=None)

        events = await service.replay(response.task_id, after_seq=-1)
        assert events == []
    finally:
        await engine.dispose()
