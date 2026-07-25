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

"""
Persisted task acknowledgement (OBSERV-02 v3, `TASK-EVENT-STREAM-RFC.md`
rev. 3 §2.10) — the `needs_attention()` predicate and `TaskService.acknowledge`.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from fred_core.common import PostgresStoreConfig
from fred_core.models.base import Base
from fred_core.sql import create_async_engine_from_config
from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import (
    StartIngestionParams,
    StartIngestionRequest,
    TaskState,
    needs_attention,
)
from fred_core.tasks.service import (
    TaskNotAcknowledgeableError,
    TaskService,
)
from fred_core.tasks.store import TaskNotFoundError, TaskStore
from fred_core.tasks.workflow_control import NoopWorkflowControl

# ── 1. needs_attention — pure predicate ──────────────────────────────────────


@pytest.mark.parametrize(
    "kind,state,step,expected",
    [
        ("ingestion", TaskState.failed, None, True),
        ("ingestion", TaskState.cancelled, None, True),
        ("ingestion", TaskState.succeeded, None, False),
        ("ingestion", TaskState.running, None, False),
        ("ingestion", TaskState.pending, None, False),
        # erasure never reaches failed by design (RGPD — retried forever),
        # but the predicate itself is state-driven first, kind-specific second.
        ("erasure", TaskState.failed, None, True),
        ("erasure", TaskState.running, "stalled", True),
        ("erasure", TaskState.running, "running", False),
        ("erasure", TaskState.running, None, False),
        ("migration", TaskState.failed, None, True),
    ],
)
def test_needs_attention(
    kind: str, state: TaskState, step: str | None, expected: bool
) -> None:
    assert needs_attention(kind, state, step) is expected


# ── 2. TaskService.acknowledge — integration against a real (SQLite) store ──


@pytest_asyncio.fixture
async def build_service():
    """Same pattern as test_reconcile.py's `build_service` — a fresh aiosqlite
    engine per test, disposed on teardown."""
    engines: list[Any] = []

    async def _build(tmp_path) -> TaskService:
        engine = create_async_engine_from_config(
            PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.sqlite3"))
        )
        engines.append(engine)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return TaskService(
            store=TaskStore(engine), bus=MemoryEventBus(), control=NoopWorkflowControl()
        )

    yield _build

    for engine in engines:
        await engine.dispose()


async def _new_task(service: TaskService) -> str:
    resp = await service.start(
        StartIngestionRequest(params=StartIngestionParams(resource_ids=["doc-1"])),
        created_by="u1",
    )
    return resp.task_id


@pytest.mark.asyncio
async def test_acknowledge_a_failed_task_succeeds(tmp_path, build_service) -> None:
    service = await build_service(tmp_path)
    task_id = await _new_task(service)
    await service.fail_task(task_id, "boom")

    result = await service.acknowledge(task_id, by="admin-1")

    assert result.task_id == task_id
    assert result.acknowledged_by == "admin-1"
    assert result.acknowledged_at is not None

    run = await service.get_run(task_id)
    assert run is not None
    assert run.acknowledged_by == "admin-1"
    assert run.acknowledged_at is not None


@pytest.mark.asyncio
async def test_acknowledge_a_non_terminal_task_raises_409_equivalent(
    tmp_path, build_service
) -> None:
    service = await build_service(tmp_path)
    task_id = await _new_task(service)  # still pending — never failed/cancelled

    with pytest.raises(TaskNotAcknowledgeableError):
        await service.acknowledge(task_id, by="admin-1")

    run = await service.get_run(task_id)
    assert run is not None
    assert run.acknowledged_at is None  # rejected write never persisted


@pytest.mark.asyncio
async def test_acknowledge_unknown_task_raises_not_found(
    tmp_path, build_service
) -> None:
    service = await build_service(tmp_path)

    with pytest.raises(TaskNotFoundError):
        await service.acknowledge("does-not-exist", by="admin-1")
