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

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from fred_core.common import PostgresStoreConfig
from fred_core.models.base import Base
from fred_core.sql import create_async_engine_from_config
from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import (
    StartIngestionParams,
    StartIngestionRequest,
    TaskState,
)
from fred_core.tasks.orm_models import TaskRunRow
from fred_core.tasks.service import TaskService
from fred_core.tasks.store import TaskStore
from fred_core.tasks.sse import task_event_stream
from fred_core.tasks.workflow_control import (
    ExecutionStatus,
    NoopWorkflowControl,
    TemporalWorkflowControl,
)

_NOW = datetime(2026, 6, 17, tzinfo=timezone.utc)


# ── 1. reconcile decision matrix (pure) ──────────────────────────────────────


@pytest.mark.parametrize(
    "status,expected",
    [
        (None, None),  # unreachable → never false-fail
        (ExecutionStatus.running, None),  # still running → leave
        (ExecutionStatus.failed, "Execution failed"),
        (ExecutionStatus.timed_out, "Execution timed_out"),
        (ExecutionStatus.canceled, "Execution canceled"),
        (ExecutionStatus.terminated, "Execution terminated"),
        (ExecutionStatus.completed, "Execution finished without completing the task"),
    ],
)
def test_reconciled_failure_message(status, expected):
    assert TaskService._reconciled_failure_message(status) == expected


# ── 2. WorkflowControl implementations ───────────────────────────────────────


@pytest.mark.asyncio
async def test_noop_workflow_control_is_inert():
    control = NoopWorkflowControl()
    assert await control.get_status("anything") is None
    assert await control.cancel("anything") is None  # no raise


@pytest.mark.asyncio
async def test_temporal_workflow_control_maps_describe_status():
    class _Handle:
        def __init__(self, name: str) -> None:
            self._name = name

        async def describe(self):
            return SimpleNamespace(status=SimpleNamespace(name=self._name))

    class _Client:
        def __init__(self, name: str) -> None:
            self._name = name

        def get_workflow_handle(self, workflow_id: str):
            return _Handle(self._name)

    class _Provider:
        def __init__(self, name: str | None, raises: bool = False) -> None:
            self._name = name
            self._raises = raises

        async def get_client(self):
            if self._raises:
                raise RuntimeError("temporal unreachable")
            return _Client(self._name or "RUNNING")

    control = TemporalWorkflowControl(cast(Any, _Provider("TIMED_OUT")))
    assert await control.get_status("wf-1") == ExecutionStatus.timed_out
    control = TemporalWorkflowControl(cast(Any, _Provider("COMPLETED")))
    assert await control.get_status("wf-1") == ExecutionStatus.completed
    # unreachable → None (never false-fail)
    control = TemporalWorkflowControl(cast(Any, _Provider(None, raises=True)))
    assert await control.get_status("wf-1") is None


# ── 3. end-to-end service reconciliation on SQLite ───────────────────────────


class _StubControl:
    """WorkflowControl stub: get_status returns a per-workflow-id status, records calls."""

    def __init__(self, status_by_eid: dict[str, ExecutionStatus | None]) -> None:
        self.status_by_eid = status_by_eid
        self.calls: list[str] = []

    async def get_status(self, workflow_id: str) -> ExecutionStatus | None:
        self.calls.append(workflow_id)
        return self.status_by_eid.get(workflow_id)

    async def cancel(self, workflow_id: str) -> None:  # pragma: no cover - unused
        return None


async def _build_service(tmp_path, status_by_eid) -> tuple[TaskService, _StubControl]:
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.sqlite3"))
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    control = _StubControl(status_by_eid)
    service = TaskService(
        store=TaskStore(engine), bus=MemoryEventBus(), control=control
    )
    return service, control


async def _new_task(service: TaskService, *, execution_id: str | None) -> str:
    resp = await service.start(
        StartIngestionRequest(params=StartIngestionParams(resource_ids=["doc-1"])),
        created_by="u1",
    )
    if execution_id is not None:
        await service.bind_execution(resp.task_id, execution_id=execution_id)
    return resp.task_id


@pytest.mark.asyncio
async def test_bind_execution_persists(tmp_path):
    service, _ = await _build_service(tmp_path, {})
    task_id = await _new_task(service, execution_id="wf-1")
    run = await service.get_run(task_id)
    assert run is not None
    assert run.execution_id == "wf-1"


@pytest.mark.asyncio
async def test_reconcile_fails_task_when_workflow_failed(tmp_path):
    service, control = await _build_service(
        tmp_path, {"wf-1": ExecutionStatus.timed_out}
    )
    task_id = await _new_task(service, execution_id="wf-1")

    failed = await service.reconcile_task(task_id)

    assert failed is True
    run = await service.get_run(task_id)
    assert run is not None
    assert TaskState(run.state) == TaskState.failed
    assert run.error == "Execution timed_out"
    assert control.calls == ["wf-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [ExecutionStatus.running, None])
async def test_reconcile_leaves_running_or_unreachable(tmp_path, status):
    service, _ = await _build_service(tmp_path, {"wf-1": status})
    task_id = await _new_task(service, execution_id="wf-1")

    failed = await service.reconcile_task(task_id)

    assert failed is False
    run = await service.get_run(task_id)
    assert run is not None
    assert TaskState(run.state) == TaskState.pending


@pytest.mark.asyncio
async def test_reconcile_skips_linkless_and_terminal(tmp_path):
    service, control = await _build_service(tmp_path, {"wf-1": ExecutionStatus.failed})

    # linkless: no execution binding → never queried
    linkless = await _new_task(service, execution_id=None)
    assert await service.reconcile_task(linkless) is False

    # terminal: already failed by the worker → never queried, never re-touched
    terminal = await _new_task(service, execution_id="wf-1")
    run = await service.get_run(terminal)
    await service.record(service._build_failed_event(run, "real worker failure"))
    control.calls.clear()
    assert await service.reconcile_task(terminal) is False
    assert control.calls == []


@pytest.mark.asyncio
async def test_reconcile_stale_respects_grace_and_dedupes(tmp_path):
    service, control = await _build_service(tmp_path, {"wf-1": ExecutionStatus.failed})
    # Two tasks share one parent workflow id.
    t1 = await _new_task(service, execution_id="wf-1")
    t2 = await _new_task(service, execution_id="wf-1")

    # Fresh tasks (huge grace) are skipped — nothing queried, nothing failed.
    assert await service.reconcile_stale(grace_seconds=3600, limit=100) == 0
    assert control.calls == []

    # Negative grace makes everything stale: both fail, but only ONE describe call.
    failed = await service.reconcile_stale(grace_seconds=-1, limit=100)
    assert failed == 2
    assert control.calls == ["wf-1"]
    for tid in (t1, t2):
        run = await service.get_run(tid)
        assert TaskState(run.state) == TaskState.failed


@pytest.mark.asyncio
async def test_fail_task_marks_pending_failed_then_noops(tmp_path):
    service, _ = await _build_service(tmp_path, {})
    task_id = await _new_task(service, execution_id=None)

    assert await service.fail_task(task_id, "Scheduling failed: boom") is True
    run = await service.get_run(task_id)
    assert TaskState(run.state) == TaskState.failed
    assert run.error == "Scheduling failed: boom"

    # already terminal → no-op
    assert await service.fail_task(task_id, "again") is False


# ── 3b. shared SSE body (read-time reconcile → replay → terminal close) ───────


@pytest.mark.asyncio
async def test_task_event_stream_reconciles_then_closes_on_dead_workflow(tmp_path):
    service, _ = await _build_service(tmp_path, {"wf-1": ExecutionStatus.failed})
    task_id = await _new_task(service, execution_id="wf-1")

    async def _connected() -> bool:
        return False

    frames = [
        frame
        async for frame in task_event_stream(
            service, task_id, after_seq=-1, is_disconnected=_connected
        )
    ]

    # The read-time reconcile failed the dead-workflow task; the stream replayed
    # that terminal event and closed (no hang on the live bus).
    assert len(frames) == 1
    assert '"state":"failed"' in frames[0]
    assert frames[0].startswith("id: 1\n")
    run = await service.get_run(task_id)
    assert TaskState(run.state) == TaskState.failed


# ── 4. _build_failed_event covers both event kinds ───────────────────────────


def test_build_failed_event_per_kind():
    service = TaskService(store=None, bus=None, control=None)  # type: ignore[arg-type]

    ingestion_run = TaskRunRow(
        task_id="t-i",
        kind="ingestion",
        state="running",
        seq=1,
        created_at=_NOW,
        updated_at=_NOW,
    )
    ev = service._build_failed_event(ingestion_run, "boom")
    assert ev.kind == "ingestion"
    assert ev.state == TaskState.failed and ev.error == "boom"

    log_run = TaskRunRow(
        task_id="t-l",
        kind="log",
        state="running",
        seq=1,
        created_at=_NOW,
        updated_at=_NOW,
    )
    ev = service._build_failed_event(log_run, "boom")
    assert ev.kind == "log"
    assert ev.detail.level == "error" and ev.detail.message == "boom"


# ── 5. background sweeper ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_reconcile_sweeper_invokes_reconcile_and_is_cancellable():
    from fred_core.tasks.service import run_reconcile_sweeper

    calls: list[tuple[float, int]] = []
    called = asyncio.Event()

    class _Svc:
        async def reconcile_stale(self, *, grace_seconds, limit):
            calls.append((grace_seconds, limit))
            called.set()
            return 0

    task = asyncio.create_task(
        run_reconcile_sweeper(
            _Svc(),  # type: ignore[arg-type]
            interval_seconds=0.01,
            grace_seconds=5,
            limit=7,
        )
    )
    await asyncio.wait_for(called.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls[0] == (5, 7)
