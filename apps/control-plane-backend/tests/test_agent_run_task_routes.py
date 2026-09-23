from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

import pytest
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.models.agent_run_task_models import (
    AgentRunAdmissionRow,
    AgentRunScheduleRow,
)
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.models.task_models import TASK_TABLES
from control_plane_backend.product.agent_run_task_store import AgentRunTaskStore
from control_plane_backend.product.schemas import (
    CreateAgentRunScheduleRequest,
    ManagedAgentRuntimeBinding,
    StartAgentRunTaskRequest,
)
from control_plane_backend.tasks import api
from control_plane_backend.users import api as users_api
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_core.scheduler.schedule_spec import IntervalSchedule
from fred_core.security.delegation import (
    CallerPolicy,
    DelegationConfig,
    initialize_delegation,
)
from fred_core.tasks.agent_run import (
    AgentRunAdmissionRecord,
    AgentRunBudget,
    AgentRunScope,
)
from fred_core.tasks.bus import MemoryEventBus
from fred_core.tasks.models import StartAgentRunRequest, TaskState
from fred_core.tasks.service import TaskService
from fred_core.tasks.store import TaskStore
from fred_core.tasks.workflow_control import NoopWorkflowControl
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _endpoint(operation_id: str):
    return next(
        cast(APIRoute, route).endpoint
        for route in api.build_tasks_router().routes
        if getattr(route, "operation_id", None) == operation_id
    )


def _caller(
    *, uid: str = "runtime-subject", client_id: str = "runtime-client"
) -> KeycloakUser:
    return KeycloakUser(
        uid=uid,
        username=uid,
        roles=[],
        client_id=client_id,
        token_issuer="https://id.invalid/realms/fred",
        token_audiences=frozenset({"control-plane"}),
        token_type="Bearer",
    )


@pytest.mark.asyncio
async def test_person_purge_deletes_temporal_schedules_before_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Store:
        async def list_schedules_by_creator(self, person_id: str, **kwargs: Any):
            assert person_id == "person-1"
            return [SimpleNamespace(schedule_id="schedule-1")]

        async def purge_person(self, person_id: str, **kwargs: Any) -> None:
            calls.append(f"purge:{person_id}")

    class Provider:
        async def get_client(self):
            return object()

    container = SimpleNamespace(
        get_agent_run_task_store=lambda: Store(),
        get_temporal_client_provider=lambda: Provider(),
    )

    async def delete_schedule(client: object, schedule_id: str) -> bool:
        calls.append(f"delete:{schedule_id}")
        return True

    monkeypatch.setattr(users_api, "delete_schedule_if_exists", delete_schedule)

    await users_api._purge_agent_run_work_for_person(container, "person-1")

    assert calls == ["delete:schedule-1", "purge:person-1"]


@pytest.mark.asyncio
async def test_person_purge_keeps_schedule_metadata_when_temporal_delete_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purged = False

    class Store:
        async def list_schedules_by_creator(self, person_id: str, **kwargs: Any):
            return [SimpleNamespace(schedule_id="schedule-1")]

        async def purge_person(self, person_id: str, **kwargs: Any) -> None:
            nonlocal purged
            purged = True

    class Provider:
        async def get_client(self):
            return object()

    container = SimpleNamespace(
        get_agent_run_task_store=lambda: Store(),
        get_temporal_client_provider=lambda: Provider(),
    )

    async def fail_delete(client: object, schedule_id: str) -> bool:
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(users_api, "delete_schedule_if_exists", fail_delete)

    with pytest.raises(RuntimeError, match="scheduler unavailable"):
        await users_api._purge_agent_run_work_for_person(container, "person-1")

    assert purged is False


def _enable_workload_policy() -> None:
    initialize_delegation(
        DelegationConfig(
            enabled=True,
            caller_policies=[
                CallerPolicy(
                    client_id="runtime-client",
                    subject="runtime-subject",
                )
            ],
        ),
        issuer="https://id.invalid/realms/fred",
        audience="control-plane",
    )


def _record(*, run_id: str = "run-1") -> AgentRunAdmissionRecord:
    return AgentRunAdmissionRecord(
        person_id="person-1",
        team_id="team-1",
        runtime_id="runtime-1",
        agent_instance_id="instance-1",
        agent_id="agent-1",
        prompt="do work",
        scope=AgentRunScope(),
        created_by="person-1",
        created_at=datetime(2026, 9, 17, tzinfo=UTC),
        run_id=run_id,
        budget=AgentRunBudget(wall_clock_seconds=30, max_concurrent_children=2),
    )


class _EventService:
    def __init__(self) -> None:
        self.run = SimpleNamespace(state=TaskState.running, detail=None)
        self.events: list[Any] = []

    async def get_run(self, task_id: str):
        return self.run if task_id == "task-1" else None

    async def record(self, event: Any) -> None:
        self.events.append(event)
        self.run.state = event.state
        self.run.detail = event.detail.model_dump()


class _AdmissionStore:
    def __init__(self) -> None:
        self.admission: SimpleNamespace | None = SimpleNamespace(
            task_id="task-1",
            runtime_client_id="runtime-client",
            runtime_subject="runtime-subject",
            workflow_id="workflow-1",
            payload_json=_record().model_dump_json(),
        )

    async def get(self, task_id: str):
        return (
            self.admission
            if self.admission and task_id == self.admission.task_id
            else None
        )


@pytest.mark.asyncio
async def test_event_report_requires_stored_pair_assigns_sequence_and_is_terminal_idempotent() -> (
    None
):
    _enable_workload_policy()
    endpoint = _endpoint("record_agent_run_task_event")
    service = _EventService()
    store = _AdmissionStore()

    with pytest.raises(HTTPException, match="workload_caller_not_allowed"):
        await endpoint(
            "task-1",
            api.AgentRunEventReport(state=TaskState.running, seq=99),
            _caller(uid="wrong"),
            service,
            store,
        )
    assert service.events == []

    report = api.AgentRunEventReport(
        state=TaskState.failed, seq=0, reason="child_limit_reached"
    )
    await endpoint("task-1", report, _caller(), service, store)
    await endpoint("task-1", report, _caller(), service, store)
    assert len(service.events) == 1
    assert service.events[0].seq == 0  # storage owns the durable sequence

    with pytest.raises(HTTPException) as raised:
        await endpoint(
            "task-1",
            api.AgentRunEventReport(state=TaskState.failed, reason="execution_failed"),
            _caller(),
            service,
            store,
        )
    assert raised.value.status_code == 409


@pytest.mark.asyncio
async def test_event_report_after_admission_purge_is_404_and_does_not_recreate() -> (
    None
):
    _enable_workload_policy()
    endpoint = _endpoint("record_agent_run_task_event")
    service = _EventService()
    store = _AdmissionStore()
    store.admission = None

    with pytest.raises(HTTPException) as raised:
        await endpoint(
            "task-1",
            api.AgentRunEventReport(
                state=TaskState.cancelled, seq=0, reason="cancelled"
            ),
            _caller(),
            service,
            store,
        )

    assert raised.value.status_code == 404
    assert store.admission is None
    assert service.events == []


class _TaskService:
    def __init__(self, *, cancel_dispatch: bool = False) -> None:
        self.started: list[str] = []
        self.bound: list[tuple[str, str]] = []
        self.failed: list[str] = []
        self.runs: dict[str, Any] = {}
        self.cancel_dispatch = cancel_dispatch

    async def start(self, request: Any, **kwargs: Any):
        self.started.append(kwargs["task_id"])
        self.runs[kwargs["task_id"]] = SimpleNamespace(
            state=TaskState.pending, execution_id=None
        )
        return SimpleNamespace(task_id=kwargs["task_id"])

    async def get_run(self, task_id: str, **kwargs: Any):
        return self.runs.get(task_id)

    async def bind_execution(
        self, task_id: str, *, execution_id: str, **kwargs: Any
    ) -> None:
        self.bound.append((task_id, execution_id))
        self.runs[task_id].execution_id = execution_id

    async def fail_task(self, task_id: str, message: str) -> bool:
        self.failed.append(task_id)
        return True


class _TemporalClient:
    def __init__(self, outcome: BaseException | None = None) -> None:
        self.outcome = outcome
        self.started: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    async def start_workflow(self, *args: Any, **kwargs: Any) -> None:
        if self.outcome is not None:
            raise self.outcome
        self.started.append((args[0], args[1:], kwargs))


class _TaskStore(_AdmissionStore):
    def __init__(self) -> None:
        self.admission = None

    async def create(self, **kwargs: Any) -> None:
        record = kwargs["record"]
        self.admission = SimpleNamespace(
            task_id=kwargs["task_id"],
            workflow_id=kwargs["workflow_id"],
            runtime_client_id=kwargs["runtime_client_id"],
            runtime_subject=kwargs["runtime_subject"],
            payload_json=record.model_dump_json(),
        )

    async def create_schedule(self, row: AgentRunScheduleRow, **kwargs: Any) -> None:
        self.schedule = row

    async def list_schedules(self, team_id: str):
        return [self.schedule] if getattr(self, "schedule", None) is not None else []

    async def get_schedule(self, schedule_id: str):
        row = getattr(self, "schedule", None)
        return row if row is not None and row.schedule_id == schedule_id else None

    async def delete_schedule(self, schedule_id: str, **kwargs: Any) -> bool:
        if await self.get_schedule(schedule_id) is None:
            return False
        self.schedule = None
        return True


class _Container:
    def __init__(
        self, service: _TaskService, store: _TaskStore, temporal: _TemporalClient
    ):
        self.service = service
        self.store = store
        self.temporal = temporal

    def get_agent_run_task_store(self):
        return self.store

    def get_temporal_client_provider(self):
        return SimpleNamespace(get_client=self._get_client)

    def get_team_metadata_store(self):
        return SimpleNamespace(advisory_lock=self._advisory_lock)

    @asynccontextmanager
    async def _advisory_lock(self, key: str, **kwargs: Any):
        yield kwargs.get("session")

    async def _get_client(self):
        return self.temporal


def _deps() -> Any:
    source = SimpleNamespace(
        enabled=True,
        runtime_id="runtime-1",
        workload_client_id="runtime-client",
        workload_subject="runtime-subject",
        agent_task_queue="agent-queue",
    )

    class _Instances:
        async def get_for_team(self, instance_id: str, team_id: str):
            return SimpleNamespace(
                enabled=True,
                source_runtime_id="runtime-1",
                source_agent_id="agent-1",
            )

    return SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(runtime_catalog_sources=[source]),
            app=SimpleNamespace(
                agent_run_default_ceiling_seconds=90,
                agent_run_max_concurrent_children=2,
            ),
        ),
        team_dependencies=SimpleNamespace(rebac=_Rebac()),
        get_agent_instance_store=lambda: _Instances(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [RuntimeError("down"), asyncio.CancelledError()])
async def test_start_dispatch_failure_and_cancellation_leave_a_terminal_task(
    monkeypatch: pytest.MonkeyPatch, outcome: BaseException
) -> None:
    endpoint = _endpoint("start_agent_run_task")
    service = _TaskService()
    store = _TaskStore()
    temporal = _TemporalClient(outcome)
    container = _Container(service, store, temporal)
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: _deps()
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    monkeypatch.setattr(api, "get_runtime_binding_for_team", _binding)

    call = endpoint(
        "team-1",
        "instance-1",
        StartAgentRunTaskRequest(prompt="do work"),
        SimpleNamespace(),
        KeycloakUser(uid="person-1", username="person-1", roles=[]),
        service,
    )
    if isinstance(outcome, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await call
    else:
        with pytest.raises(HTTPException) as raised:
            await call
        assert raised.value.status_code == 503
    assert len(service.started) == 1
    assert service.failed == service.started
    assert store.admission is not None
    assert temporal.started == []


@pytest.mark.asyncio
async def test_denied_start_creates_no_task_admission_or_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = _endpoint("start_agent_run_task")
    service = _TaskService()
    store = _TaskStore()
    temporal = _TemporalClient()
    container = _Container(service, store, temporal)

    async def denied(*args: Any, **kwargs: Any):
        raise HTTPException(status_code=403, detail="not_allowed")

    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: _deps()
    )
    monkeypatch.setattr(api, "require_team_access", denied)
    with pytest.raises(HTTPException) as raised:
        await endpoint(
            "team-1",
            "instance-1",
            StartAgentRunTaskRequest(prompt="do work"),
            SimpleNamespace(),
            KeycloakUser(uid="person-1", username="person-1", roles=[]),
            service,
        )
    assert raised.value.status_code == 403
    assert service.started == []
    assert store.admission is None
    assert temporal.started == []


@pytest.mark.asyncio
async def test_start_rechecks_person_standing_inside_lifecycle_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = _endpoint("start_agent_run_task")
    service = _TaskService()
    store = _TaskStore()
    temporal = _TemporalClient()
    container = _Container(service, store, temporal)
    deps = _deps()

    async def denied_standing(person_id: str) -> None:
        raise HTTPException(status_code=403, detail="standing_required")

    deps.team_dependencies.rebac.require_user_standing = denied_standing
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: deps
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    monkeypatch.setattr(api, "get_runtime_binding_for_team", _binding)

    with pytest.raises(HTTPException) as raised:
        await endpoint(
            "team-1",
            "instance-1",
            StartAgentRunTaskRequest(prompt="do work"),
            SimpleNamespace(),
            KeycloakUser(uid="person-1", username="person-1", roles=[]),
            service,
        )

    assert raised.value.status_code == 403
    assert service.started == []
    assert store.admission is None
    assert temporal.started == []


@pytest.mark.asyncio
async def test_successful_dispatch_keeps_queued_cancel_retryable_when_delivery_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    endpoint = _endpoint("start_agent_run_task")
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'dispatch-cancel-retry.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(CPBase.metadata.create_all)

    class FailOnceControl:
        def __init__(self) -> None:
            self.attempts = 0
            self.cancelled: list[str] = []

        async def cancel(self, workflow_id: str) -> None:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("synthetic cancellation transport failure")
            self.cancelled.append(workflow_id)

        async def get_status(
            self, workflow_id: str, *, identifier_free: bool = False
        ) -> None:
            return None

    control = FailOnceControl()
    service = TaskService(
        TaskStore(engine, TASK_TABLES), MemoryEventBus(), cast(Any, control)
    )
    store = AgentRunTaskStore(engine)

    class CancelDuringDispatchClient(_TemporalClient):
        async def start_workflow(self, *args: Any, **kwargs: Any) -> None:
            await super().start_workflow(*args, **kwargs)
            await service.cancel(args[1].task_id)

    temporal = CancelDuringDispatchClient()
    container = _Container(cast(Any, service), cast(Any, store), temporal)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifecycle_lock(key: str, **kwargs: Any):
        if kwargs.get("session") is not None:
            yield kwargs["session"]
        else:
            async with sessions.begin() as session:
                yield session

    container._advisory_lock = lifecycle_lock
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: _deps()
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    monkeypatch.setattr(api, "get_runtime_binding_for_team", _binding)

    try:
        with pytest.raises(
            RuntimeError, match="synthetic cancellation transport failure"
        ):
            await endpoint(
                "team-1",
                "instance-1",
                StartAgentRunTaskRequest(prompt="do work"),
                SimpleNamespace(),
                KeycloakUser(uid="person-1", username="person-1", roles=[]),
                service,
            )

        assert len(temporal.started) == 1
        workflow_id = temporal.started[0][2]["id"]
        admission = await store.get_by_workflow(workflow_id)
        assert admission is not None
        run = await service.get_run(admission.task_id)
        assert run is not None
        assert TaskState(run.state) == TaskState.cancelling
        assert run.execution_id == workflow_id

        await service.cancel(admission.task_id)
        assert control.attempts == 2
        assert control.cancelled == [workflow_id]
    finally:
        await engine.dispose()


async def _allow_team(
    user: Any, team_id: Any, dependencies: Any, permissions: Any = None
):
    return team_id


async def _binding(*args: Any, **kwargs: Any) -> ManagedAgentRuntimeBinding:
    return ManagedAgentRuntimeBinding(
        agent_instance_id="instance-1",
        template_agent_id="agent-1",
        display_name="Agent",
        owner_team_id=TeamId("team-1"),
        tuning=ManagedAgentTuning(
            role="assistant", description="Runs background work", run_ceiling_seconds=30
        ),
    )


class _Rebac:
    is_admin = False

    async def has_permission(self, *args: Any, **kwargs: Any) -> bool:
        return self.is_admin

    async def require_user_standing(self, person_id: str) -> None:
        return None


def test_schedule_creation_requires_explicit_opt_in() -> None:
    with pytest.raises(ValueError):
        CreateAgentRunScheduleRequest.model_validate(
            {
                "prompt": "work",
                "schedule": {"type": "interval", "every_seconds": 60},
            }
        )


@pytest.mark.asyncio
async def test_schedule_owner_visibility_and_admin_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = _endpoint("create_agent_run_schedule")
    list_ = _endpoint("list_agent_run_schedules")
    delete = _endpoint("delete_agent_run_schedule")
    store = _TaskStore()
    container = _Container(_TaskService(), store, _TemporalClient())
    deps = _deps()
    scheduled: list[str] = []
    deleted: list[str] = []

    async def fake_ensure(client: Any, schedule_id: str, **kwargs: Any) -> str:
        scheduled.append(schedule_id)
        action = kwargs
        assert action["workflow_id"] == f"agent-run-schedule-{schedule_id}"
        assert action["args"][0].schedule_id == schedule_id
        return schedule_id

    async def fake_delete(client: Any, schedule_id: str) -> bool:
        deleted.append(schedule_id)
        return True

    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: deps
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    monkeypatch.setattr(api, "get_runtime_binding_for_team", _binding)
    monkeypatch.setattr(api, "ensure_schedule", fake_ensure)
    monkeypatch.setattr(api, "delete_schedule_if_exists", fake_delete)
    owner = KeycloakUser(uid="person-1", username="person-1", roles=[])
    body = CreateAgentRunScheduleRequest(
        prompt="work",
        schedule=IntervalSchedule(every_seconds=60),
        enabled=True,
    )
    created = await create("team-1", "instance-1", body, SimpleNamespace(), owner)
    assert scheduled == [created.schedule_id]
    assert [
        item.schedule_id
        for item in await list_("team-1", "instance-1", SimpleNamespace(), owner)
    ] == [created.schedule_id]

    other = KeycloakUser(uid="person-2", username="person-2", roles=[])
    assert await list_("team-1", "instance-1", SimpleNamespace(), other) == []
    with pytest.raises(HTTPException) as hidden:
        await delete(
            "team-1", "instance-1", created.schedule_id, SimpleNamespace(), other
        )
    assert hidden.value.status_code == 404

    deps.team_dependencies.rebac.is_admin = True
    await delete("team-1", "instance-1", created.schedule_id, SimpleNamespace(), other)
    assert deleted == [created.schedule_id]
    assert store.schedule is None


@pytest.mark.asyncio
async def test_schedule_creation_rechecks_person_standing_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = _endpoint("create_agent_run_schedule")
    store = _TaskStore()
    temporal = _TemporalClient()
    container = _Container(_TaskService(), store, temporal)
    deps = _deps()
    dispatched = False

    async def denied_standing(person_id: str) -> None:
        raise HTTPException(status_code=403, detail="standing_required")

    async def unexpected_dispatch(*args: Any, **kwargs: Any) -> None:
        nonlocal dispatched
        dispatched = True

    deps.team_dependencies.rebac.require_user_standing = denied_standing
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: deps
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    monkeypatch.setattr(api, "get_runtime_binding_for_team", _binding)
    monkeypatch.setattr(api, "ensure_schedule", unexpected_dispatch)

    with pytest.raises(HTTPException) as raised:
        await endpoint(
            "team-1",
            "instance-1",
            CreateAgentRunScheduleRequest(
                prompt="work",
                schedule=IntervalSchedule(every_seconds=60),
                enabled=True,
            ),
            SimpleNamespace(),
            KeycloakUser(uid="person-1", username="person-1", roles=[]),
        )

    assert raised.value.status_code == 403
    assert getattr(store, "schedule", None) is None
    assert dispatched is False


class _OccurrenceStore(_TaskStore):
    def __init__(self) -> None:
        super().__init__()
        template = api._StoredScheduleTemplate(
            person_id="person-1",
            roles=(),
            team_id="team-1",
            runtime_id="runtime-1",
            runtime_client_id="runtime-client",
            runtime_subject="runtime-subject",
            task_queue="agent-queue",
            agent_instance_id="instance-1",
            agent_id="agent-1",
            prompt="scheduled work",
            scope=AgentRunScope(),
            budget=AgentRunBudget(wall_clock_seconds=30, max_concurrent_children=2),
            schedule=IntervalSchedule(every_seconds=3600),
        )
        self.schedule: AgentRunScheduleRow | None = AgentRunScheduleRow(
            schedule_id="schedule-1",
            team_id="team-1",
            agent_instance_id="instance-1",
            runtime_id="runtime-1",
            created_by="person-1",
            template_json=template.model_dump_json(),
            created_at=datetime(2026, 9, 17, tzinfo=UTC),
        )
        self.admissions: dict[str, Any] = {}
        self.lock = asyncio.Lock()

    async def get_schedule(self, schedule_id: str):
        return self.schedule if self.schedule and schedule_id == "schedule-1" else None

    async def get_by_occurrence(self, occurrence_key: str, **kwargs: Any):
        return self.admissions.get(occurrence_key)

    @asynccontextmanager
    async def lock_occurrence(self, occurrence_key: str):
        async with self.lock:
            yield None

    async def create(self, **kwargs: Any) -> None:
        await super().create(**kwargs)
        admission = self.admission
        assert admission is not None
        admission.occurrence_key = kwargs["occurrence_key"]
        self.admissions[kwargs["occurrence_key"]] = admission


@pytest.mark.asyncio
async def test_schedule_occurrence_is_deterministic_and_rechecks_current_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_workload_policy()
    endpoint = _endpoint("create_agent_run_schedule_occurrence")
    service = _TaskService()
    store = _OccurrenceStore()
    container = _Container(service, store, _TemporalClient())
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: _deps()
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    request = api.ScheduledAgentRunOccurrenceRequest(
        workflow_id="occurrence-workflow-1", run_id="run-1"
    )

    first = await endpoint(
        "schedule-1", request, SimpleNamespace(), _caller(), service, store
    )
    repeated = await endpoint(
        "schedule-1", request, SimpleNamespace(), _caller(), service, store
    )
    assert repeated == first
    assert service.started == [first.task_id]

    assert first.workflow_id != request.workflow_id

    store.admission = None

    async def denied(*args: Any, **kwargs: Any):
        raise HTTPException(status_code=403, detail="standing_required")

    monkeypatch.setattr(api, "require_team_access", denied)
    with pytest.raises(HTTPException) as revoked:
        await endpoint(
            "schedule-1",
            api.ScheduledAgentRunOccurrenceRequest(
                workflow_id="occurrence-workflow-2", run_id="run-2"
            ),
            SimpleNamespace(),
            _caller(),
            service,
            store,
        )
    assert revoked.value.status_code == 403
    assert len(service.started) == 1

    store.schedule = None
    with pytest.raises(HTTPException) as deleted:
        await endpoint(
            "schedule-1",
            api.ScheduledAgentRunOccurrenceRequest(
                workflow_id="occurrence-workflow-3", run_id="run-3"
            ),
            SimpleNamespace(),
            _caller(),
            service,
            store,
        )
    assert deleted.value.status_code == 404
    assert len(service.started) == 1


@pytest.mark.asyncio
async def test_schedule_occurrence_rechecks_person_standing_before_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_workload_policy()
    endpoint = _endpoint("create_agent_run_schedule_occurrence")
    service = _TaskService()
    store = _OccurrenceStore()
    container = _Container(service, store, _TemporalClient())
    deps = _deps()

    async def denied_standing(person_id: str) -> None:
        raise HTTPException(status_code=403, detail="standing_required")

    deps.team_dependencies.rebac.require_user_standing = denied_standing
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: deps
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)

    with pytest.raises(HTTPException) as raised:
        await endpoint(
            "schedule-1",
            api.ScheduledAgentRunOccurrenceRequest(
                workflow_id="scheduled-parent-workflow", run_id="run-1"
            ),
            SimpleNamespace(),
            _caller(),
            service,
            store,
        )

    assert raised.value.status_code == 403
    assert service.started == []
    assert store.admission is None


@pytest.mark.asyncio
async def test_concurrent_schedule_occurrence_creates_one_task_and_child_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_workload_policy()
    endpoint = _endpoint("create_agent_run_schedule_occurrence")
    service = _TaskService()
    store = _OccurrenceStore()
    container = _Container(service, store, _TemporalClient())
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: _deps()
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    request = api.ScheduledAgentRunOccurrenceRequest(
        workflow_id="scheduled-parent-workflow", run_id="run-1"
    )

    first, second = await asyncio.gather(
        endpoint("schedule-1", request, SimpleNamespace(), _caller(), service, store),
        endpoint("schedule-1", request, SimpleNamespace(), _caller(), service, store),
    )

    assert first == second
    assert first.workflow_id != request.workflow_id
    assert service.started == [first.task_id]
    assert service.bound == [(first.task_id, request.workflow_id)]


@pytest.mark.asyncio
async def test_occurrence_retry_repairs_binding_after_first_bind_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_workload_policy()
    endpoint = _endpoint("create_agent_run_schedule_occurrence")

    class FailFirstBindService(_TaskService):
        def __init__(self) -> None:
            super().__init__()
            self.bind_attempts = 0

        async def bind_execution(
            self, task_id: str, *, execution_id: str, **kwargs: Any
        ) -> None:
            self.bind_attempts += 1
            if self.bind_attempts == 1:
                raise RuntimeError("synthetic bind failure")
            await super().bind_execution(task_id, execution_id=execution_id, **kwargs)

    service = FailFirstBindService()
    store = _OccurrenceStore()
    container = _Container(service, store, _TemporalClient())
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: _deps()
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    request = api.ScheduledAgentRunOccurrenceRequest(
        workflow_id="scheduled-parent-workflow", run_id="run-1"
    )

    with pytest.raises(RuntimeError, match="synthetic bind failure"):
        await endpoint(
            "schedule-1", request, SimpleNamespace(), _caller(), service, store
        )

    repaired = await endpoint(
        "schedule-1", request, SimpleNamespace(), _caller(), service, store
    )
    assert service.started == [repaired.task_id]
    assert service.bind_attempts == 2
    assert service.bound == [(repaired.task_id, request.workflow_id)]
    assert service.runs[repaired.task_id].execution_id == request.workflow_id


@pytest.mark.asyncio
async def test_occurrence_retry_does_not_rebind_terminal_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_workload_policy()
    endpoint = _endpoint("create_agent_run_schedule_occurrence")
    service = _TaskService()
    store = _OccurrenceStore()
    container = _Container(service, store, _TemporalClient())
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: _deps()
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    request = api.ScheduledAgentRunOccurrenceRequest(
        workflow_id="scheduled-parent-workflow", run_id="run-1"
    )
    created = await endpoint(
        "schedule-1", request, SimpleNamespace(), _caller(), service, store
    )
    service.bound.clear()
    service.runs[created.task_id].execution_id = None
    service.runs[created.task_id].state = TaskState.failed

    repeated = await endpoint(
        "schedule-1", request, SimpleNamespace(), _caller(), service, store
    )

    assert repeated == created
    assert service.bound == []
    assert service.runs[created.task_id].execution_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [False, True])
async def test_occurrence_recovers_existing_matching_task_with_real_stores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    terminal: bool,
) -> None:
    _enable_workload_policy()
    endpoint = _endpoint("create_agent_run_schedule_occurrence")
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'occurrence-recovery.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(CPBase.metadata.create_all)
    store = AgentRunTaskStore(engine)
    service = TaskService(
        TaskStore(engine, TASK_TABLES), MemoryEventBus(), NoopWorkflowControl()
    )
    container = _Container(cast(Any, service), cast(Any, store), _TemporalClient())
    deps = _deps()
    monkeypatch.setattr(api, "get_application_container", lambda request: container)
    monkeypatch.setattr(
        api, "build_product_service_dependencies", lambda container: deps
    )
    monkeypatch.setattr(api, "require_team_access", _allow_team)
    request = api.ScheduledAgentRunOccurrenceRequest(
        workflow_id="scheduled-parent-workflow", run_id="run-1"
    )
    occurrence_key = str(
        uuid5(
            NAMESPACE_URL,
            "fred:agent-run-occurrence:schedule-1:scheduled-parent-workflow:run-1",
        )
    )
    task_id = str(uuid5(NAMESPACE_URL, f"fred:agent-run-task:{occurrence_key}"))
    template = _OccurrenceStore().schedule
    assert template is not None

    try:
        await store.create_schedule(template)
        await service.start(
            StartAgentRunRequest(),
            created_by="person-1",
            team_id="team-1",
            task_id=task_id,
        )
        if terminal:
            assert await service.fail_task(task_id, "synthetic terminal task") is True
        async with engine.begin() as connection:
            await connection.execute(
                delete(AgentRunAdmissionRow).where(
                    AgentRunAdmissionRow.task_id == task_id
                )
            )

        if terminal:
            with pytest.raises(HTTPException) as conflict:
                await endpoint(
                    "schedule-1", request, SimpleNamespace(), _caller(), service, store
                )
            assert conflict.value.status_code == 409
            assert await store.get(task_id) is None
            run = await service.get_run(task_id)
            assert run is not None
            assert TaskState(run.state).is_terminal
            assert run.execution_id is None
        else:
            occurrence = await endpoint(
                "schedule-1", request, SimpleNamespace(), _caller(), service, store
            )

            assert occurrence.task_id == task_id
            assert await store.get(task_id) is not None
            run = await service.get_run(task_id)
            assert run is not None
            assert run.execution_id == request.workflow_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_occurrence_lock_entries_are_released_after_waiters_finish() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(CPBase.metadata.create_all)
    store = AgentRunTaskStore(engine)
    entered: list[int] = []

    async def contender(number: int) -> None:
        async with store.lock_occurrence("same-occurrence"):
            entered.append(number)
            await asyncio.sleep(0)

    try:
        await asyncio.gather(contender(1), contender(2))
        assert sorted(entered) == [1, 2]
        assert store._occurrence_locks == {}
    finally:
        await engine.dispose()
