from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fred_core.common import PostgresStoreConfig, TemporalSchedulerConfig
from fred_core.security.structure import KeycloakUser
from fred_core.sql import create_async_engine_from_config
from fred_core.tasks.agent_run import (
    AgentRunAdmissionRecord,
    AgentRunBudget,
    AgentRunWorkflowInputV1,
)
from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import AgentRunTaskEvent, StartAgentRunRequest, TaskState
from fred_core.tasks.service import TaskService
from fred_core.tasks.store import TaskStore
from fred_core.tasks.workflow_control import TemporalWorkflowControl
from fred_runtime.background import activities as activity_module
from fred_runtime.background.activities import AgentRunActivities
from fred_runtime.runtime_support.run_budget import (
    RunLimits,
    RunScope,
    register_run_child,
)

# This is intentionally a monorepo integration test: it crosses the runtime
# activity and the control-plane task API without adding a production dependency
# in either direction.
_CONTROL_PLANE_ROOT = Path(__file__).parents[3] / "apps" / "control-plane-backend"
sys.path.insert(0, str(_CONTROL_PLANE_ROOT))

from control_plane_backend.models.base import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    Base as ControlPlaneBase,
)
from control_plane_backend.models.task_models import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    TASK_TABLES,
)
from control_plane_backend.tasks import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    api as task_api,
)

sys.path.remove(str(_CONTROL_PLANE_ROOT))


class _Reporter:
    def __init__(self) -> None:
        self.events: list[AgentRunTaskEvent] = []

    async def record(self, task_id: str, event: AgentRunTaskEvent) -> None:
        self.events.append(event)

    async def create_occurrence(self, schedule_id: str, request: Any) -> Any:
        raise AssertionError("schedule occurrence is not expected")


class _Rebac:
    def __init__(self) -> None:
        self.standing_checks: list[str] = []

    async def require_user_standing(self, user_id: str) -> None:
        self.standing_checks.append(user_id)

    async def check_user_team_permission_or_raise(
        self, *args: Any, **kwargs: Any
    ) -> None:
        return None


class _Handle:
    def __init__(self, activity_task: asyncio.Task[None]) -> None:
        self._activity_task = activity_task
        self._cancelled = False

    async def cancel(self, *, rpc_timeout: timedelta | None = None) -> None:
        self._activity_task.cancel()
        await asyncio.gather(self._activity_task, return_exceptions=True)
        self._cancelled = True

    async def describe(self, *, rpc_timeout: timedelta | None = None) -> Any:
        return SimpleNamespace(
            status=SimpleNamespace(name="CANCELED" if self._cancelled else "RUNNING")
        )


class _Client:
    def __init__(self, handle: _Handle) -> None:
        self._handle = handle

    def get_workflow_handle(self, workflow_id: str) -> _Handle:
        assert workflow_id == "workflow-1"
        return self._handle


class _Provider:
    config = TemporalSchedulerConfig(rpc_timeout_seconds=7)

    def __init__(self, client: _Client) -> None:
        self._client = client

    async def get_client(self) -> _Client:
        return self._client


def _cancel_endpoint():
    return next(
        route.endpoint
        for route in task_api.build_tasks_router().routes
        if route.path == "/tasks/{task_id}/cancel"
    )


@pytest.mark.asyncio
async def test_cancel_api_reaches_activity_children_and_reconciles_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = asyncio.Event()
    child_cleaned = asyncio.Event()
    executor_calls = 0
    reporter = _Reporter()
    rebac = _Rebac()

    async def child() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            child_cleaned.set()

    async def execute(record: AgentRunAdmissionRecord):
        nonlocal executor_calls
        executor_calls += 1
        with RunScope.open(
            agent_id=record.agent_id,
            limits=RunLimits(wall_clock_seconds=30, max_concurrent_children=1),
        ):
            child_task = asyncio.create_task(child())
            assert register_run_child(cast(asyncio.Task[object], child_task))
            started.set()
            await asyncio.Event().wait()
            if False:
                yield {}

    monkeypatch.setattr(activity_module.activity, "heartbeat", lambda: None)
    activities = AgentRunActivities(
        rebac=cast(Any, rebac), executor=execute, reporter=reporter
    )
    value = AgentRunWorkflowInputV1(
        task_id="task-1",
        workflow_id="workflow-1",
        record=AgentRunAdmissionRecord(
            person_id="person-1",
            team_id="team-1",
            runtime_id="runtime-1",
            agent_instance_id="instance-1",
            agent_id="agent-1",
            prompt="synthetic prompt",
            created_by="person-1",
            created_at=datetime.now(UTC),
            run_id="run-1",
            budget=AgentRunBudget(wall_clock_seconds=30, max_concurrent_children=1),
        ),
    )
    activity_task = asyncio.create_task(activities.execute(value))
    await started.wait()

    handle = _Handle(activity_task)
    control = TemporalWorkflowControl(cast(Any, _Provider(_Client(handle))))
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.sqlite3"))
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(ControlPlaneBase.metadata.create_all)
        service = TaskService(
            store=TaskStore(engine, TASK_TABLES),
            bus=MemoryEventBus(),
            control=control,
        )
        await service.start(
            StartAgentRunRequest(),
            created_by="person-1",
            team_id="team-1",
            task_id="task-1",
        )
        await service.bind_execution("task-1", execution_id="workflow-1")

        owner = KeycloakUser(uid="person-1", username="person-1", roles=[])
        response = await _cancel_endpoint()("task-1", owner, service, cast(Any, rebac))
        assert response == {"task_id": "task-1"}
        await asyncio.wait_for(child_cleaned.wait(), timeout=1)
        assert await service.reconcile_task("task-1") is True

        run = await service.get_run("task-1")
        assert run is not None
        assert TaskState(run.state) == TaskState.cancelled
        assert executor_calls == 1
        assert rebac.standing_checks == ["person-1", "person-1"]
        assert [event.state for event in reporter.events].count(
            TaskState.cancelled
        ) == 1
    finally:
        await engine.dispose()
