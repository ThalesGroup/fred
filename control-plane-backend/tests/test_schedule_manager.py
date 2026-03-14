from __future__ import annotations

import pytest
from fred_core.common import TemporalSchedulerConfig
from temporalio.client import (
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
)

from control_plane_backend.scheduler.temporal.schedule_manager import (
    ensure_lifecycle_schedule,
)
from control_plane_backend.scheduler.temporal.structures import LifecycleManagerInput


class _FakeClientCreateOk:
    def __init__(self) -> None:
        self.created_id: str | None = None
        self.created_schedule: Schedule | None = None

    async def create_schedule(self, schedule_id: str, schedule: Schedule) -> None:
        self.created_id = schedule_id
        self.created_schedule = schedule

    def get_schedule_handle(self, schedule_id: str) -> object:  # pragma: no cover
        raise AssertionError(
            "Should not request schedule handle on successful creation"
        )


class _FakeHandle:
    def __init__(self) -> None:
        self.describe_calls = 0

    async def describe(self) -> None:
        self.describe_calls += 1


class _FakeClientAlreadyExists:
    def __init__(self) -> None:
        self.handle = _FakeHandle()

    async def create_schedule(self, schedule_id: str, schedule: object) -> None:
        raise ScheduleAlreadyRunningError()

    def get_schedule_handle(self, schedule_id: str) -> _FakeHandle:
        return self.handle


@pytest.mark.asyncio
async def test_ensure_schedule_sets_required_workflow_id() -> None:
    client = _FakeClientCreateOk()
    config = TemporalSchedulerConfig(
        host="localhost:7233",
        namespace="default",
        task_queue="control-plane-lifecycle",
        workflow_id_prefix="control-plane",
    )

    schedule_id = await ensure_lifecycle_schedule(
        client,  # type: ignore[arg-type]
        config,
        LifecycleManagerInput(),
    )

    assert schedule_id == "control-plane-lifecycle-manager"
    assert client.created_id == schedule_id
    assert client.created_schedule is not None
    assert isinstance(client.created_schedule.action, ScheduleActionStartWorkflow)
    assert client.created_schedule.action.id == "control-plane-lifecycle-manager-run"


@pytest.mark.asyncio
async def test_ensure_schedule_is_idempotent_when_already_exists() -> None:
    client = _FakeClientAlreadyExists()
    config = TemporalSchedulerConfig(
        host="localhost:7233",
        namespace="default",
        task_queue="control-plane-lifecycle",
        workflow_id_prefix="control-plane",
    )

    schedule_id = await ensure_lifecycle_schedule(
        client,  # type: ignore[arg-type]
        config,
        LifecycleManagerInput(),
    )

    assert schedule_id == "control-plane-lifecycle-manager"
    assert client.handle.describe_calls == 1
