"""`DELETE /users/{user_id}`: the only Fred operation that removes a person's standing.

Order: identity administration is resolved before anything changes; under the
agent-run lifecycle lock the ban is written, the person's other relations are
removed and their runs, task rows and schedules are purged; the identity-provider
account is deleted after that transaction has committed.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from _standing_test_doubles import EVERYONE_ACTIVE, StandingRebacEngine, ban
from control_plane_backend.app.dependencies import attach_application_container
from control_plane_backend.models.agent_run_models import AgentRunRow
from control_plane_backend.models.agent_run_task_models import AgentRunScheduleRow
from control_plane_backend.product.agent_run_store import (
    AGENT_RUN_LIFECYCLE_LOCK,
    AgentRunRecord,
    AgentRunStore,
)
from control_plane_backend.product.agent_run_task_store import AgentRunTaskStore
from control_plane_backend.product.api import register_agent_run
from control_plane_backend.product.schemas import RegisterAgentRunRequest
from control_plane_backend.users import api as users_api
from control_plane_backend.users.dependencies import get_user_service_dependencies
from fastapi import FastAPI
from fred_core import (
    AssertedUser,
    KeycloackDisabled,
    KeycloakUser,
    PrincipalContext,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    StandingAuthorizationError,
    get_current_user,
)
from fred_core.sql import use_session
from fred_core.teams.metadata_store import TeamMetadataStore
from httpx import ASGITransport, AsyncClient, Response
from keycloak.exceptions import KeycloakDeleteError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from temporalio.service import RPCError, RPCStatusCode

_PERSON = "synthetic-person"
_BYSTANDER = "synthetic-bystander"
_ROOT = "synthetic-root"
_RUN = "synthetic-run"
_SCHEDULE = "synthetic-schedule"
_MEMBERSHIP = Relation(
    subject=RebacReference(Resource.USER, _PERSON),
    relation=RelationType.TEAM_MEMBER,
    resource=RebacReference(Resource.TEAM, "synthetic-team"),
)
_DELETE = f"/users/{_PERSON}"


class _IdentityProvider:
    """`KeycloakAdmin.a_delete_user`: a 204 removes the account; any other status
    raises `KeycloakDeleteError` with that code (404 when the account is missing)."""

    def __init__(self, calls: list[str], accounts: set[str]) -> None:
        self.calls = calls
        self.accounts = accounts
        self.failure_code: int | None = None

    async def a_delete_user(self, user_id: str) -> dict:
        self.calls.append("delete_identity_account")
        if self.failure_code is not None:
            raise KeycloakDeleteError("synthetic failure", self.failure_code)
        if user_id not in self.accounts:
            raise KeycloakDeleteError("User not found", 404)
        self.accounts.discard(user_id)
        return {}


class _Temporal:
    """Schedule handles whose `delete` removes the schedule or raises NOT_FOUND;
    `failure_status` makes every delete raise that status instead."""

    def __init__(self, calls: list[str], schedules: set[str]) -> None:
        self.calls = calls
        self.schedules = schedules
        self.failure_status: RPCStatusCode | None = None

    async def get_client(self) -> _Temporal:
        return self

    def get_schedule_handle(self, schedule_id: str) -> SimpleNamespace:
        async def delete() -> None:
            self.calls.append("delete_schedule")
            if self.failure_status is not None:
                raise RPCError("synthetic failure", self.failure_status, b"")
            if schedule_id not in self.schedules:
                raise RPCError("not found", RPCStatusCode.NOT_FOUND, b"")
            self.schedules.discard(schedule_id)

        return SimpleNamespace(delete=delete)


class _SerialLifecycleStore:
    """`TeamMetadataStore.advisory_lock` as Postgres gives it: one holder per key
    across replicas, released only once the holder's transaction has ended."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._locks: dict[str, asyncio.Lock] = {}
        self.contended_keys: list[str] = []
        self.contended = asyncio.Event()

    @asynccontextmanager
    async def advisory_lock(self, key: str, *, session=None):
        lock = self._locks.setdefault(key, asyncio.Lock())
        if lock.locked():
            self.contended_keys.append(key)
            self.contended.set()
        async with lock:
            async with use_session(self._sessions, session) as active:
                yield active


@dataclass
class _Deployment:
    client: AsyncClient
    rebac: StandingRebacEngine
    identity: _IdentityProvider
    temporal: _Temporal
    runs: AgentRunStore
    tasks: AgentRunTaskStore
    lifecycle: TeamMetadataStore | _SerialLifecycleStore
    calls: list[str]


def _run_record(run_id: str = _RUN) -> AgentRunRecord:
    return AgentRunRecord(
        run_id=run_id,
        person_id=_PERSON,
        team_id=None,
        agent_id="synthetic-agent",
        agent_instance_id=None,
        reporter_client_id="synthetic-runtime",
        reporter_subject="synthetic-service-account",
        origin_caller=None,
        mode="attended",
        started_at=datetime(2026, 9, 17, 12, tzinfo=UTC),
        run_ceiling_seconds=60,
    )


@asynccontextmanager
async def _deployment(
    tmp_path: Path,
    *,
    rebac: StandingRebacEngine | None = None,
    identity_administration: bool = True,
    serial_lock: bool = False,
) -> AsyncIterator[_Deployment]:
    # One pooled connection: the purge must run on the lock's own transaction.
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'delete.db'}",
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.1,
    )
    async with engine.begin() as connection:
        await connection.run_sync(AgentRunRow.metadata.create_all)
    calls: list[str] = []
    engine_under_test = rebac if rebac is not None else StandingRebacEngine()
    engine_under_test.calls = calls
    # Startup state: everyone in good standing, plus one team membership.
    engine_under_test.relations |= {EVERYONE_ACTIVE, _MEMBERSHIP}
    identity = _IdentityProvider(calls, {_PERSON, _BYSTANDER})
    temporal = _Temporal(calls, {_SCHEDULE})
    runs = AgentRunStore(engine)
    tasks = AgentRunTaskStore(engine)
    lifecycle = (
        _SerialLifecycleStore(engine) if serial_lock else TeamMetadataStore(engine)
    )
    await runs.create(_run_record())
    await tasks.create_schedule(
        AgentRunScheduleRow(
            schedule_id=_SCHEDULE,
            team_id="synthetic-team",
            agent_instance_id="synthetic-instance",
            runtime_id="synthetic-runtime",
            created_by=_PERSON,
            template_json="{}",
        )
    )

    async def root() -> str:
        return _ROOT

    container = SimpleNamespace(
        get_rebac_engine=lambda: engine_under_test,
        get_team_metadata_store=lambda: lifecycle,
        get_agent_run_store=lambda: runs,
        get_agent_run_task_store=lambda: tasks,
        get_temporal_client_provider=lambda: temporal,
        get_platform_bootstrap_store=lambda: SimpleNamespace(get_completed_by=root),
    )
    app = FastAPI()
    app.include_router(users_api.router)
    users_api.register_exception_handlers(app)
    attach_application_container(app, container)  # type: ignore[arg-type]
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="synthetic-admin", username="synthetic-admin", roles=[]
    )
    app.dependency_overrides[get_user_service_dependencies] = lambda: SimpleNamespace(
        create_keycloak_admin_client=lambda: (
            identity if identity_administration else KeycloackDisabled()
        )
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield _Deployment(
                client,
                engine_under_test,
                identity,
                temporal,
                runs,
                tasks,
                lifecycle,
                calls,
            )
    finally:
        await engine.dispose()


async def _assert_banned(rebac: StandingRebacEngine) -> None:
    with pytest.raises(StandingAuthorizationError):
        await rebac.require_user_standing(_PERSON)
    await rebac.require_user_standing(_BYSTANDER)


async def _assert_purged(deployment: _Deployment) -> None:
    # Fresh sessions: only committed state is visible here.
    assert await deployment.runs.get(_RUN) is None
    assert await deployment.tasks.get_schedule(_SCHEDULE) is None
    assert deployment.temporal.schedules == set()


async def _assert_person_untouched(deployment: _Deployment) -> None:
    await deployment.rebac.require_user_standing(_PERSON)
    assert _MEMBERSHIP in deployment.rebac.relations
    assert await deployment.runs.get(_RUN) is not None
    assert await deployment.tasks.get_schedule(_SCHEDULE) is not None
    assert deployment.temporal.schedules == {_SCHEDULE}
    assert deployment.identity.accounts == {_PERSON, _BYSTANDER}


@pytest.mark.asyncio
async def test_delete_bans_before_relation_cleanup_and_identity_deletion(
    tmp_path: Path,
) -> None:
    async with _deployment(tmp_path) as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 204
        assert deployment.calls == [
            "remove_user_standing",
            "delete_all_relations_of_reference",
            "delete_schedule",
            "delete_identity_account",
        ]
        await _assert_banned(deployment.rebac)
        assert ban(_PERSON) in deployment.rebac.relations
        assert _MEMBERSHIP not in deployment.rebac.relations
        await _assert_purged(deployment)
        assert deployment.identity.accounts == {_BYSTANDER}


@pytest.mark.asyncio
async def test_identity_failure_after_the_ban_errors_with_person_banned_and_purged(
    tmp_path: Path,
) -> None:
    async with _deployment(tmp_path) as deployment:
        deployment.identity.failure_code = 500

        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 500
        assert deployment.calls[-1] == "delete_identity_account"
        await _assert_banned(deployment.rebac)
        await _assert_purged(deployment)
        assert _PERSON in deployment.identity.accounts

        # A retry repeats the idempotent cleanup and removes the account.
        deployment.identity.failure_code = None
        deployment.calls.clear()
        retried = await deployment.client.delete(_DELETE)

        assert retried.status_code == 204
        assert deployment.calls == [
            "remove_user_standing",
            "delete_all_relations_of_reference",
            "delete_identity_account",
        ]
        assert deployment.identity.accounts == {_BYSTANDER}


@pytest.mark.asyncio
async def test_missing_identity_retry_commits_purge_before_returning_not_found(
    tmp_path: Path,
) -> None:
    async with _deployment(tmp_path) as deployment:
        deployment.identity.accounts.discard(_PERSON)

        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 404
        assert deployment.calls == [
            "remove_user_standing",
            "delete_all_relations_of_reference",
            "delete_schedule",
            "delete_identity_account",
        ]
        await _assert_banned(deployment.rebac)
        await _assert_purged(deployment)


@pytest.mark.asyncio
async def test_disabled_identity_administration_refuses_before_any_change(
    tmp_path: Path,
) -> None:
    async with _deployment(tmp_path, identity_administration=False) as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 503
        assert response.json() == {
            "detail": "Keycloak M2M is disabled; cannot perform user operations."
        }
        assert deployment.calls == []
        await deployment.rebac.require_user_standing(_PERSON)
        assert _MEMBERSHIP in deployment.rebac.relations
        assert await deployment.runs.get(_RUN) is not None
        assert await deployment.tasks.get_schedule(_SCHEDULE) is not None
        assert deployment.temporal.schedules == {_SCHEDULE}


@pytest.mark.asyncio
async def test_without_standing_enforcement_delete_writes_no_ban_but_cleans_up(
    tmp_path: Path,
) -> None:
    rebac = StandingRebacEngine(enforces_standing=False)
    async with _deployment(tmp_path, rebac=rebac) as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 204
        assert deployment.calls == [
            "delete_all_relations_of_reference",
            "delete_schedule",
            "delete_identity_account",
        ]
        assert ban(_PERSON) not in rebac.relations
        assert _MEMBERSHIP not in rebac.relations
        await _assert_purged(deployment)
        assert deployment.identity.accounts == {_BYSTANDER}


@pytest.mark.asyncio
@pytest.mark.parametrize("enforced", [True, False])
@pytest.mark.parametrize("path_id", ["%2A", "%23x", "team%23member"])
async def test_an_id_naming_no_person_is_refused_as_not_found_before_any_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enforced: bool, path_id: str
) -> None:
    rebac = StandingRebacEngine(enforces_standing=enforced)
    async with _deployment(tmp_path, rebac=rebac) as deployment:
        # A purge of "*" matches no stored row, so only a recorded call reveals it.
        for store in (deployment.runs, deployment.tasks):

            async def purge(*args, store_purge=store.purge_person, **kwargs):
                deployment.calls.append("purge_person")
                return await store_purge(*args, **kwargs)

            monkeypatch.setattr(store, "purge_person", purge)

        response = await deployment.client.delete(f"/users/{path_id}")

        assert response.status_code == 404
        assert deployment.calls == []
        assert deployment.rebac.relations == {EVERYONE_ACTIVE, _MEMBERSHIP}
        await _assert_person_untouched(deployment)


@pytest.mark.asyncio
async def test_deleting_the_bootstrap_root_is_refused_before_any_change(
    tmp_path: Path,
) -> None:
    async with _deployment(tmp_path) as deployment:
        response = await deployment.client.delete(f"/users/{_ROOT}")

        assert response.status_code == 403
        assert deployment.calls == []
        assert ban(_ROOT) not in deployment.rebac.relations
        await _assert_person_untouched(deployment)


class _BanWriteFails(StandingRebacEngine):
    async def remove_user_standing(self, user_id: str) -> str | None:
        self.calls.append("remove_user_standing")
        raise RuntimeError("synthetic store failure")


@pytest.mark.asyncio
async def test_a_failed_ban_write_stops_the_delete_before_any_cleanup(
    tmp_path: Path,
) -> None:
    async with _deployment(tmp_path, rebac=_BanWriteFails()) as deployment:
        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 500
        assert deployment.calls == ["remove_user_standing"]
        await _assert_person_untouched(deployment)


@pytest.mark.asyncio
async def test_schedule_failure_after_the_ban_rolls_back_the_purge_and_keeps_the_account(
    tmp_path: Path,
) -> None:
    async with _deployment(tmp_path) as deployment:
        deployment.temporal.failure_status = RPCStatusCode.UNAVAILABLE

        response = await deployment.client.delete(_DELETE)

        assert response.status_code == 500
        assert deployment.calls == [
            "remove_user_standing",
            "delete_all_relations_of_reference",
            "delete_schedule",
        ]
        await _assert_banned(deployment.rebac)
        # The run and schedule rows share the failed transaction.
        assert await deployment.runs.get(_RUN) is not None
        assert await deployment.tasks.get_schedule(_SCHEDULE) is not None
        assert deployment.temporal.schedules == {_SCHEDULE}
        assert deployment.identity.accounts == {_PERSON, _BYSTANDER}

        deployment.temporal.failure_status = None
        deployment.calls.clear()
        retried = await deployment.client.delete(_DELETE)

        assert retried.status_code == 204
        assert deployment.calls == [
            "remove_user_standing",
            "delete_all_relations_of_reference",
            "delete_schedule",
            "delete_identity_account",
        ]
        await _assert_banned(deployment.rebac)
        await _assert_purged(deployment)
        assert deployment.identity.accounts == {_BYSTANDER}


class _GatedStandingEngine(StandingRebacEngine):
    """Holds one step open so the other request can be started against the lock."""

    gate_step: str = ""

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def _hold(self, step: str) -> None:
        if step == self.gate_step and not self.entered.is_set():
            self.entered.set()
            await self.release.wait()

    async def delete_all_relations_of_reference(self, reference: RebacReference):
        await self._hold("cleanup")
        return await super().delete_all_relations_of_reference(reference)

    async def _has_permission_raw(self, subject, permission, resource, **kwargs):
        allowed = await super()._has_permission_raw(
            subject, permission, resource, **kwargs
        )
        if permission == RelationType.ACTIVE and subject.id == _PERSON:
            await self._hold("admission")
        return allowed


async def _admit(deployment: _Deployment, run_id: str) -> None:
    deps = SimpleNamespace(
        configuration=SimpleNamespace(security=SimpleNamespace(profile=None)),
        team_dependencies=SimpleNamespace(rebac=deployment.rebac),
        get_team_metadata_store=lambda: deployment.lifecycle,
    )
    principals = PrincipalContext(
        caller=KeycloakUser(
            uid="synthetic-service-account",
            username="synthetic-runtime",
            roles=[],
            client_id="synthetic-runtime",
        ),
        subject=AssertedUser(
            uid=_PERSON,
            client_id="synthetic-runtime",
            run_id=run_id,
            agent_id="synthetic-agent",
        ),
    )
    await register_agent_run(
        RegisterAgentRunRequest(
            agent_id="synthetic-agent", started_at=datetime(2026, 9, 17, tzinfo=UTC)
        ),
        deps,  # type: ignore[arg-type]
        deployment.runs,
        principals,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("deletion_first", [True, False])
async def test_admission_after_a_delete_is_refused(
    tmp_path: Path, deletion_first: bool
) -> None:
    rebac = _GatedStandingEngine()
    rebac.gate_step = "cleanup" if deletion_first else "admission"
    async with _deployment(tmp_path, rebac=rebac, serial_lock=True) as deployment:
        lifecycle = deployment.lifecycle
        assert isinstance(lifecycle, _SerialLifecycleStore)
        first = asyncio.create_task(
            deployment.client.delete(_DELETE)
            if deletion_first
            else _admit(deployment, "synthetic-concurrent-run")
        )
        second: asyncio.Task | None = None
        try:
            await asyncio.wait_for(rebac.entered.wait(), timeout=1)
            second = asyncio.create_task(
                _admit(deployment, "synthetic-concurrent-run")
                if deletion_first
                else deployment.client.delete(_DELETE)
            )
            # The other request waits on the lifecycle lock; a waiting delete has
            # not banned anyone yet.
            await asyncio.wait_for(lifecycle.contended.wait(), timeout=1)
            assert lifecycle.contended_keys == [AGENT_RUN_LIFECYCLE_LOCK]
            assert not second.done()
            assert (ban(_PERSON) in rebac.relations) is deletion_first
            rebac.release.set()
            results = await asyncio.wait_for(
                asyncio.gather(first, second, return_exceptions=True), timeout=2
            )
        finally:
            rebac.release.set()
            for task in (first, second):
                if task is not None and not task.done():
                    task.cancel()

        deletion, admission = results if deletion_first else results[::-1]
        assert isinstance(deletion, Response) and deletion.status_code == 204
        if deletion_first:
            assert isinstance(admission, StandingAuthorizationError)
        else:
            assert admission is None
        # Whichever came first, no admitted run survives the delete.
        assert await deployment.runs.get("synthetic-concurrent-run") is None
        await _assert_banned(rebac)

        with pytest.raises(StandingAuthorizationError):
            await _admit(deployment, "synthetic-later-run")
        assert await deployment.runs.get("synthetic-later-run") is None
