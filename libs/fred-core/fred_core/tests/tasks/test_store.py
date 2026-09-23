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

"""`TaskStore.get_task` — one task's summary, projected exactly as `list_tasks`."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio

from fred_core.common import PostgresStoreConfig
from fred_core.sql import create_async_engine_from_config
from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import IngestionTaskEvent, TaskState
from fred_core.tasks.service import TaskService
from fred_core.tasks.store import TaskStore
from fred_core.tasks.workflow_control import NoopWorkflowControl
from fred_core.tests.tasks.task_tables import TASK_TABLES, Base


@pytest_asyncio.fixture
async def build_store():
    """Same pattern as test_reconcile.py's `build_service` — a fresh aiosqlite
    engine per test, disposed on teardown."""
    engines: list[Any] = []

    async def _build(tmp_path) -> TaskStore:
        engine = create_async_engine_from_config(
            PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.sqlite3"))
        )
        engines.append(engine)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return TaskStore(engine, TASK_TABLES)

    yield _build

    for engine in engines:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_task_projects_like_list_tasks(tmp_path, build_store) -> None:
    store = await build_store(tmp_path)
    await store.create(task_id="t1", kind="ingestion", created_by="u1")

    (listed,) = await store.list_tasks()

    assert await store.get_task("t1") == listed


@pytest.mark.asyncio
async def test_get_task_of_unknown_id_is_none(tmp_path, build_store) -> None:
    store = await build_store(tmp_path)

    assert await store.get_task("missing") is None


def _event(state: TaskState, error: str | None = None) -> IngestionTaskEvent:
    return IngestionTaskEvent(
        task_id="t1",
        state=state,
        error=error,
        seq=0,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [TaskState.failed, TaskState.succeeded])
async def test_ingestion_terminal_outcome_cannot_be_overwritten(
    tmp_path, build_store, terminal
):
    store = await build_store(tmp_path)
    await store.create(task_id="t1", kind="ingestion", created_by="u1")
    assert await store.record_event(_event(terminal, "original")) == (1, terminal)
    assert await store.record_event(_event(TaskState.running)) is None
    assert await store.record_event(_event(TaskState.failed, "late failure")) is None
    summary = await store.get_task("t1")
    assert summary.state == terminal
    assert summary.error == "original"
    assert len(await store.replay_events("t1", after_seq=0)) == 1


@pytest.mark.asyncio
async def test_concurrent_events_receive_distinct_sequences(tmp_path, build_store):
    store = await build_store(tmp_path)
    await store.create(task_id="t1", kind="ingestion", created_by="u1")
    recorded = await asyncio.gather(
        *(store.record_event(_event(TaskState.running)) for _ in range(4))
    )
    assert sorted(result[0] for result in recorded if result is not None) == [
        1,
        2,
        3,
        4,
    ]
    assert [event.seq for event in await store.replay_events("t1", after_seq=0)] == [
        1,
        2,
        3,
        4,
    ]


@pytest.mark.asyncio
async def test_notification_failure_does_not_change_durable_success(
    tmp_path, build_store
):
    class UnavailableBus(MemoryEventBus):
        async def publish(self, event):
            raise RuntimeError("notification unavailable")

    store = await build_store(tmp_path)
    await store.create(task_id="t1", kind="ingestion", created_by="u1")
    service = TaskService(store, UnavailableBus(), NoopWorkflowControl())
    assert await service.record(_event(TaskState.succeeded)) is True
    assert await service.record(_event(TaskState.failed)) is False
    task = await service.get_task("t1")
    assert task is not None
    assert task.state == TaskState.succeeded
