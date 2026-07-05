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

"""CTRLP-12: scheduled tasks + the erasure kind.

A scheduled erasure task must be visible with its due date the moment it is
created (before any worker runs), so a platform/team admin can see the pipeline
of upcoming erasures — not just what is running. These tests pin that:
- `scheduled_for` is persisted at creation and surfaced by `list_tasks`;
- it stays stable across state transitions (record_event never clobbers it);
- the `erasure` kind round-trips through the store.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fred_core.common import PostgresStoreConfig
from fred_core.models.base import Base
from fred_core.sql import create_async_engine_from_config
from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import (
    ErasureDetail,
    ErasureReason,
    ErasureTaskEvent,
    StartErasureRequest,
    TaskState,
    TaskTarget,
)
from fred_core.tasks.service import TaskService
from fred_core.tasks.store import TaskStore
from fred_core.tasks.workflow_control import NoopWorkflowControl


async def _service(tmp_path) -> TaskService:
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.sqlite3"))
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return TaskService(
        store=TaskStore(engine), bus=MemoryEventBus(), control=NoopWorkflowControl()
    )


@pytest.mark.asyncio
async def test_scheduled_erasure_task_is_visible_with_due_date(tmp_path) -> None:
    service = await _service(tmp_path)
    due = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=30)

    started = await service.start(
        StartErasureRequest(reason=ErasureReason.user_deleted),
        created_by="alice",
        team_id="northbridge",
        target=TaskTarget(type="conversation", id="session-1", label="Q3 pricing"),
        scheduled_for=due,
    )

    # Immediately listable as a pending, future-dated erasure — before any worker.
    tasks = (await service.list_tasks(kind="erasure", team_id="northbridge")).tasks
    assert len(tasks) == 1
    task = tasks[0]
    assert task.task_id == started.task_id
    assert task.kind == "erasure"
    assert task.state == TaskState.pending
    # SQLite returns tz-naive; compare the instant (real Postgres is tz-aware).
    assert task.scheduled_for is not None
    assert task.scheduled_for.replace(tzinfo=None) == due.replace(tzinfo=None)
    assert task.team_id == "northbridge"
    assert task.target is not None and task.target.id == "session-1"


@pytest.mark.asyncio
async def test_scheduled_for_survives_state_transitions(tmp_path) -> None:
    service = await _service(tmp_path)
    due = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=7)

    started = await service.start(
        StartErasureRequest(reason=ErasureReason.member_removed),
        created_by="system",
        team_id="northbridge",
        target=TaskTarget(type="conversation", id="session-2", label="onboarding"),
        scheduled_for=due,
    )
    tid = started.task_id

    # Worker picks it up: running, then succeeded — recorded as erasure events.
    await service.record(
        ErasureTaskEvent(
            task_id=tid,
            state=TaskState.running,
            seq=0,
            timestamp=datetime.now(timezone.utc),
            detail=ErasureDetail(
                reason=ErasureReason.member_removed, stores_ok=3, stores_total=5
            ),
        )
    )
    await service.record(
        ErasureTaskEvent(
            task_id=tid,
            state=TaskState.succeeded,
            seq=0,
            timestamp=datetime.now(timezone.utc),
            detail=ErasureDetail(
                reason=ErasureReason.member_removed, stores_ok=5, stores_total=5
            ),
        )
    )

    task = (await service.list_tasks(kind="erasure")).tasks[0]
    assert task.state == TaskState.succeeded
    # The due date set at creation is NOT clobbered by event recording.
    assert task.scheduled_for is not None
    assert task.scheduled_for.replace(tzinfo=None) == due.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_run_now_task_has_no_scheduled_for(tmp_path) -> None:
    """A task with no schedule leaves scheduled_for None (run-now default)."""
    from fred_core.tasks.models import StartMigrationRequest

    service = await _service(tmp_path)
    await service.start(StartMigrationRequest(), created_by="ops", team_id=None)

    task = (await service.list_tasks(kind="migration")).tasks[0]
    assert task.scheduled_for is None


@pytest.mark.asyncio
async def test_sparse_event_preserves_progress_step_detail(tmp_path) -> None:
    """A sparse running event (no progress/step/detail) must NOT wipe the last-known
    values — the bar can't flicker back to indeterminate mid-task, and the durable
    erasure attempt counter survives the detail-less ``mark_erasure_running`` tick
    (CTRLP-12, async#2)."""
    service = await _service(tmp_path)
    started = await service.start(
        StartErasureRequest(reason=ErasureReason.user_deleted),
        created_by="alice",
        team_id="nb",
        target=TaskTarget(type="conversation", id="s-1", label="chat"),
    )
    tid = started.task_id

    # A rich event sets progress/step/detail…
    await service.record(
        ErasureTaskEvent(
            task_id=tid,
            state=TaskState.running,
            seq=0,
            timestamp=datetime.now(timezone.utc),
            progress=0.5,
            step="partial — retrying",
            detail=ErasureDetail(stores_ok=1, stores_total=2, attempts=3),
        )
    )
    # …then a sparse running event omits them (like mark_erasure_running).
    await service.record(
        ErasureTaskEvent(
            task_id=tid,
            state=TaskState.running,
            seq=0,
            timestamp=datetime.now(timezone.utc),
            step="erasing",  # step changes, but progress + detail are absent
        )
    )

    run = await service.get_run(tid)
    assert run is not None
    assert run.progress == 0.5  # preserved (event carried none)
    assert run.step == "erasing"  # updated (event carried one)
    assert run.detail is not None and run.detail["attempts"] == 3  # counter survived
