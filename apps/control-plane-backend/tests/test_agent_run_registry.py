from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import AsyncIterator

import pytest
import pytest_asyncio
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.models.agent_run_models import AgentRunRow
from control_plane_backend.product import api as product_api
from control_plane_backend.product.agent_run_store import AgentRunRecord, AgentRunStore
from control_plane_backend.product.api import end_agent_run, register_agent_run
from control_plane_backend.product.dependencies import get_product_service_dependencies
from control_plane_backend.product.schemas import (
    EndAgentRunRequest,
    ManagedAgentRuntimeBinding,
    RegisterAgentRunRequest,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core import AssertedUser, KeycloakUser, PrincipalContext, get_config
from fred_core.common import TeamId
from fred_core.security import oidc
from fred_core.security.delegation import (
    GRANT_PARAM_NAMES,
    CallerPolicy,
    DelegationConfig,
    initialize_delegation,
)
from fred_core.users.store.postgres_user_store import get_user_store
from fred_sdk.contracts import RuntimeStopReason
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _record(**updates: object) -> AgentRunRecord:
    values = {
        "run_id": "run-1",
        "person_id": "person-1",
        "team_id": "team-1",
        "agent_id": "agent-1",
        "agent_instance_id": "agent-1",
        "reporter_client_id": "runtime",
        "reporter_subject": "service-account",
        "origin_caller": None,
        "mode": "attended",
        "started_at": datetime(2026, 9, 17, 12, tzinfo=UTC),
        "run_ceiling_seconds": 900.0,
    }
    values.update(updates)
    return AgentRunRecord(**values)  # type: ignore[arg-type]


@pytest_asyncio.fixture
async def store() -> AsyncIterator[AgentRunStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(AgentRunRow.metadata.create_all)
    yield AgentRunStore(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_registry_records_and_idempotently_ends_a_run(
    store: AgentRunStore,
) -> None:
    await store.create(_record())

    ended = await store.end(run_id="run-1", outcome="failed", reason="authority_lost")
    repeated = await store.end(
        run_id="run-1", outcome="failed", reason="authority_lost"
    )

    assert ended is not None and ended.ended_at is not None
    assert repeated is not None and repeated.outcome == "failed"
    assert repeated.stop_reason == "authority_lost"


@pytest.mark.asyncio
async def test_registry_rejects_a_conflicting_terminal_report(
    store: AgentRunStore,
) -> None:
    await store.create(_record())
    await store.end(run_id="run-1", outcome="failed", reason="authority_lost")

    with pytest.raises(ValueError, match="agent_run_terminal_conflict"):
        await store.end(run_id="run-1", outcome="succeeded", reason=None)


@pytest.mark.asyncio
async def test_account_purge_removes_the_record_and_late_end_cannot_recreate_it(
    store: AgentRunStore,
) -> None:
    await store.create(_record())

    assert await store.purge_person("person-1") == 1
    assert await store.end(run_id="run-1", outcome="cancelled", reason=None) is None
    assert await store.get("run-1") is None


def test_registration_requires_exactly_one_target_and_aware_start_time() -> None:
    request = RegisterAgentRunRequest(
        agent_id="agent-1",
        started_at=datetime(2026, 9, 17, 15, tzinfo=UTC),
    )

    assert request.mode == "attended"
    assert request.run_ceiling_seconds == 900.0
    assert request.started_at.tzinfo is UTC


def test_principal_context_keeps_lifecycle_reporter_separate_from_person() -> None:
    caller = KeycloakUser(uid="service-account", username="runtime", roles=[])
    subject = AssertedUser(
        uid="person-1", client_id="runtime", run_id="run-1", agent_id="agent-1"
    )

    context = PrincipalContext(caller=caller, subject=subject)

    assert context.caller.uid == "service-account"
    assert context.subject.uid == "person-1"


class _FakeRunStore:
    def __init__(self, record: AgentRunRecord | None = None) -> None:
        self.record = record

    async def create(self, record: AgentRunRecord, **kwargs: object) -> AgentRunRecord:
        self.record = record
        return record

    async def get(self, run_id: str) -> AgentRunRecord | None:
        return self.record if self.record and self.record.run_id == run_id else None

    async def end(
        self, *, run_id: str, outcome: str, reason: str | None
    ) -> AgentRunRecord | None:
        assert self.record is not None
        self.record = replace(self.record, outcome=outcome, stop_reason=reason)
        return self.record


def _caller(*, uid: str = "service-account") -> KeycloakUser:
    return KeycloakUser(
        uid=uid,
        username="runtime",
        roles=[],
        client_id="runtime",
        token_issuer="https://id.invalid/realms/fred",
        token_audiences=frozenset({"control-plane"}),
        token_type="Bearer",
    )


class _LifecycleStore:
    @asynccontextmanager
    async def advisory_lock(self, key: str):
        yield None


async def _require_person_standing(self, user_id: str) -> None:
    assert user_id == "person-1"


def _enable_lifecycle_policy() -> None:
    initialize_delegation(
        DelegationConfig(
            enabled=True,
            caller_policies=[
                CallerPolicy(
                    client_id="runtime",
                    subject="service-account",
                )
            ],
        ),
        issuer="https://id.invalid/realms/fred",
        audience="control-plane",
    )


@pytest.mark.asyncio
async def test_terminal_report_requires_the_registered_caller_pair() -> None:
    _enable_lifecycle_policy()
    store = _FakeRunStore(_record(reporter_subject="other-service-account"))

    with pytest.raises(HTTPException) as raised:
        await end_agent_run(
            "run-1",
            EndAgentRunRequest(outcome="failed"),
            store,  # type: ignore[arg-type]
            _caller(),
        )

    assert raised.value.status_code == 403
    assert store.record is not None and store.record.outcome is None


@pytest.mark.asyncio
async def test_terminal_report_succeeds_without_resolving_subject_standing() -> None:
    _enable_lifecycle_policy()
    store = _FakeRunStore(_record())

    await end_agent_run(
        "run-1",
        EndAgentRunRequest(outcome="failed", reason=RuntimeStopReason.AUTHORITY_LOST),
        store,  # type: ignore[arg-type]
        _caller(),
    )

    assert store.record is not None
    assert store.record.outcome == "failed"
    assert store.record.stop_reason == "authority_lost"


@pytest.mark.asyncio
async def test_terminal_report_after_account_purge_is_404_and_does_not_recreate() -> (
    None
):
    _enable_lifecycle_policy()
    store = _FakeRunStore()

    with pytest.raises(HTTPException) as raised:
        await end_agent_run(
            "purged-run",
            EndAgentRunRequest(outcome="cancelled"),
            store,  # type: ignore[arg-type]
            _caller(),
        )

    assert raised.value.status_code == 404
    assert store.record is None


@pytest.mark.asyncio
async def test_terminal_report_returns_404_when_purge_wins_after_initial_read() -> None:
    _enable_lifecycle_policy()

    class PurgedDuringEndStore(_FakeRunStore):
        async def end(self, *, run_id: str, outcome: str, reason: str | None):
            self.record = None
            return None

    store = PurgedDuringEndStore(_record())

    with pytest.raises(HTTPException) as raised:
        await end_agent_run(
            "run-1",
            EndAgentRunRequest(outcome="cancelled"),
            store,  # type: ignore[arg-type]
            _caller(),
        )

    assert raised.value.status_code == 404
    assert store.record is None


@pytest.mark.asyncio
async def test_registration_and_purge_are_serialized_in_both_race_orders(
    tmp_path,
) -> None:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'registration-race.sqlite3'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(AgentRunRow.metadata.create_all)
    store = AgentRunStore(engine)

    class GateLifecycleStore:
        def __init__(self) -> None:
            self.lock = asyncio.Lock()
            self.waiting = asyncio.Event()
            self.sessions = async_sessionmaker(engine, expire_on_commit=False)

        @asynccontextmanager
        async def advisory_lock(self, key: str):
            self.waiting.set()
            async with self.lock:
                async with self.sessions.begin() as session:
                    yield session

    lifecycle = GateLifecycleStore()
    standing = True
    standing_entered = asyncio.Event()
    allow_standing = asyncio.Event()
    allow_standing.set()

    class Rebac:
        async def require_user_standing(self, user_id: str) -> None:
            standing_entered.set()
            await allow_standing.wait()
            if not standing:
                raise HTTPException(status_code=403, detail="standing_required")

    deps = type(
        "Deps",
        (),
        {
            "configuration": type(
                "Configuration",
                (),
                {"security": type("Security", (), {"profile": None})()},
            )(),
            "team_dependencies": type("TeamDeps", (), {"rebac": Rebac()})(),
            "get_team_metadata_store": staticmethod(lambda: lifecycle),
        },
    )()

    def principals(run_id: str) -> PrincipalContext:
        return PrincipalContext(
            caller=_caller(),
            subject=AssertedUser(
                uid="person-1",
                client_id="runtime",
                run_id=run_id,
                agent_id="agent-1",
            ),
        )

    request = RegisterAgentRunRequest(
        agent_id="agent-1", started_at=datetime(2026, 9, 17, 12, tzinfo=UTC)
    )

    try:
        # Deletion/revocation first: registration waits for the lifecycle lock,
        # then observes fresh standing and cannot recreate the purged record.
        await lifecycle.lock.acquire()
        registration = asyncio.create_task(
            register_agent_run(
                request,
                deps,  # type: ignore[arg-type]
                store,
                principals("run-after-delete"),
            )
        )
        await lifecycle.waiting.wait()
        standing = False
        lifecycle.lock.release()
        with pytest.raises(HTTPException) as rejected:
            await registration
        assert rejected.value.status_code == 403
        assert await store.get("run-after-delete") is None

        # Registration first: deletion waits for the same lock/session, then
        # purges the committed registration before it can survive the delete.
        lifecycle.waiting.clear()
        standing_entered.clear()
        allow_standing.clear()
        standing = True
        registration = asyncio.create_task(
            register_agent_run(
                request,
                deps,  # type: ignore[arg-type]
                store,
                principals("run-before-delete"),
            )
        )
        await standing_entered.wait()

        async def purge() -> None:
            async with lifecycle.advisory_lock(
                "agent_run_registration_and_account_deletion"
            ) as session:
                await store.purge_person(
                    "person-1", acquire_lock=False, session=session
                )

        deletion = asyncio.create_task(purge())
        allow_standing.set()
        await registration
        await deletion
        assert await store.get("run-before-delete") is None
    finally:
        if lifecycle.lock.locked():
            lifecycle.lock.release()
        await engine.dispose()


@pytest.mark.asyncio
async def test_direct_registration_uses_only_the_grant_identity_and_target() -> None:
    class _Rebac:
        async def require_user_standing(self, user_id: str) -> None:
            assert user_id == "person-1"

    deps = type(
        "Deps",
        (),
        {
            "configuration": type(
                "Configuration",
                (),
                {"security": type("Security", (), {"profile": None})()},
            )(),
            "team_dependencies": type("TeamDeps", (), {"rebac": _Rebac()})(),
            "get_team_metadata_store": staticmethod(lambda: _LifecycleStore()),
        },
    )()
    store = _FakeRunStore()
    subject = AssertedUser(
        uid="person-1", client_id="runtime", run_id="run-1", agent_id="agent-1"
    )

    response = await register_agent_run(
        RegisterAgentRunRequest(
            agent_id="agent-1", started_at=datetime(2026, 9, 17, 12, tzinfo=UTC)
        ),
        deps,  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        PrincipalContext(caller=_caller(), subject=subject),
    )

    assert response.run_id == "run-1"
    assert response.binding is None
    assert store.record is not None
    assert store.record.person_id == "person-1"
    assert store.record.reporter_subject == "service-account"


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [False, True])
async def test_team_registration_branches_recheck_person_standing(
    monkeypatch: pytest.MonkeyPatch, managed: bool
) -> None:
    async def allow_team(*args, **kwargs):
        return TeamId("team-1")

    async def binding(*args, **kwargs):
        return ManagedAgentRuntimeBinding(
            agent_instance_id="instance-1",
            template_agent_id="template-1",
            display_name="Agent",
            owner_team_id=TeamId("team-1"),
            tuning=ManagedAgentTuning(role="Agent", description="Agent"),
        )

    class Rebac:
        async def require_user_standing(self, user_id: str) -> None:
            raise HTTPException(status_code=403, detail="standing_required")

    monkeypatch.setattr(product_api, "require_team_access", allow_team)
    monkeypatch.setattr(product_api, "get_runtime_binding_for_team", binding)
    deps = type(
        "Deps",
        (),
        {
            "configuration": type(
                "Configuration",
                (),
                {"security": type("Security", (), {"profile": None})()},
            )(),
            "team_dependencies": type("TeamDeps", (), {"rebac": Rebac()})(),
            "get_team_metadata_store": staticmethod(lambda: _LifecycleStore()),
        },
    )()
    store = _FakeRunStore()
    target = "instance-1" if managed else "agent-1"
    body = RegisterAgentRunRequest(
        agent_instance_id=target if managed else None,
        agent_id=None if managed else target,
        team_id=TeamId("team-1"),
        started_at=datetime(2026, 9, 17, 12, tzinfo=UTC),
    )
    subject = AssertedUser(
        uid="person-1", client_id="runtime", run_id="run-1", agent_id=target
    )

    with pytest.raises(HTTPException) as raised:
        await register_agent_run(
            body,
            deps,  # type: ignore[arg-type]
            store,  # type: ignore[arg-type]
            PrincipalContext(caller=_caller(), subject=subject),
        )

    assert raised.value.status_code == 403
    assert store.record is None


def _registration_client(store: _FakeRunStore) -> TestClient:
    """The route with its product dependencies stubbed, so what reaches the
    store is decided by the verified grant and the request body alone."""
    deps = type(
        "Deps",
        (),
        {
            "configuration": type(
                "Configuration",
                (),
                {"security": type("Security", (), {"profile": None})()},
            )(),
            "team_dependencies": type(
                "TeamDeps",
                (),
                {
                    "rebac": type(
                        "Rebac",
                        (),
                        {"require_user_standing": _require_person_standing},
                    )()
                },
            )(),
            "get_team_metadata_store": staticmethod(lambda: _LifecycleStore()),
        },
    )()
    app = FastAPI()
    app.include_router(product_api.router)
    app.dependency_overrides[get_product_service_dependencies] = lambda: deps
    app.dependency_overrides[product_api._get_agent_run_store] = lambda: store
    app.dependency_overrides[get_user_store] = lambda: None
    app.dependency_overrides[get_config] = lambda: type(
        "Config", (), {"app": type("App", (), {"gcu_version": None})()}
    )()
    return TestClient(app)


def test_http_registration_uses_the_verified_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_lifecycle_policy()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda _: _caller())
    store = _FakeRunStore()

    response = _registration_client(store).post(
        "/agent-runs",
        params={"person": "person-1", "run": "run-1", "agent": "agent-1"},
        headers={"Authorization": "Bearer synthetic"},
        json={
            "agent_id": "agent-1",
            "started_at": "2026-09-17T12:00:00Z",
            "mode": "attended",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "run_id": "run-1",
        "run_ceiling_seconds": 900.0,
        "binding": None,
    }
    assert store.record is not None and store.record.person_id == "person-1"


def test_a_background_registration_keeps_origin_caller_and_reporter_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three identities reach the record separately and stay separate: the person
    the run acts for, the workload whose admission started it, and the runtime
    that registered it and will report its end.

    The body and grant are the managed shape a background run actually emits, so
    this meets the runtime's own registration test on the branch it takes."""

    async def allow_team(*args, **kwargs):
        return TeamId("team-1")

    async def binding(*args, **kwargs):
        return ManagedAgentRuntimeBinding(
            agent_instance_id="instance-1",
            template_agent_id="template-1",
            display_name="Agent",
            owner_team_id=TeamId("team-1"),
            tuning=ManagedAgentTuning(role="Agent", description="Agent"),
        )

    _enable_lifecycle_policy()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    monkeypatch.setattr(oidc, "decode_jwt", lambda _: _caller())
    monkeypatch.setattr(product_api, "require_team_access", allow_team)
    monkeypatch.setattr(product_api, "get_runtime_binding_for_team", binding)
    store = _FakeRunStore()

    response = _registration_client(store).post(
        "/agent-runs",
        params={"person": "person-1", "run": "run-1", "agent": "instance-1"},
        headers={"Authorization": "Bearer synthetic"},
        json={
            "agent_instance_id": "instance-1",
            "agent_id": None,
            "team_id": "team-1",
            "started_at": "2026-09-17T12:00:00Z",
            "run_ceiling_seconds": 900.0,
            "mode": "background",
            "origin_caller": "campaign-worker",
        },
    )

    assert response.status_code == 201
    assert store.record is not None
    assert store.record.person_id == "person-1"
    assert store.record.origin_caller == "campaign-worker"
    assert store.record.mode == "background"
    assert store.record.reporter_client_id == "runtime"
    assert store.record.reporter_subject == "service-account"


def test_registration_openapi_declares_the_query_only_delegation_grant() -> None:
    app = FastAPI()
    app.include_router(product_api.router)

    operation = app.openapi()["paths"]["/agent-runs"]["post"]
    query_parameters = {
        parameter["name"]: parameter
        for parameter in operation["parameters"]
        if parameter["in"] == "query"
    }

    assert set(query_parameters) == {"person", "run", "agent"}
    assert all(parameter["required"] for parameter in query_parameters.values())


def _declared_grant_parameters(path: str) -> dict[str, dict]:
    app = FastAPI()
    app.include_router(product_api.router)
    operation = app.openapi()["paths"][path]["post"]
    return {
        parameter["name"]: parameter
        for parameter in operation.get("parameters", [])
        if parameter["in"] == "query" and parameter["name"] in GRANT_PARAM_NAMES
    }


@pytest.mark.parametrize(
    "path",
    [
        "/teams/{team_id}/runtimes/{runtime_id}/agents/{agent_id}/prepare-execution",
        "/teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution",
    ],
)
def test_prepare_execution_declares_the_grant_without_requiring_it(path: str) -> None:
    """A workload names the person it prepares for; an interactive caller names
    nobody. Both reach these routes, so the grant is declared but not required."""
    declared = _declared_grant_parameters(path)

    assert set(declared) == set(GRANT_PARAM_NAMES)
    assert not any(parameter.get("required") for parameter in declared.values())


def test_every_declared_grant_uses_the_shared_parameter_names() -> None:
    """One source for the wire names: a rename that misses a declaration site
    leaves that route advertising a grant no caller can satisfy."""
    app = FastAPI()
    app.include_router(product_api.router)
    paths = app.openapi()["paths"]

    declaring = {
        path: {
            parameter["name"]
            for parameter in operation.get("parameters", [])
            if parameter["in"] == "query" and parameter["name"] in GRANT_PARAM_NAMES
        }
        for path, methods in paths.items()
        for operation in methods.values()
        if isinstance(operation, dict)
    }
    declaring = {path: names for path, names in declaring.items() if names}

    assert declaring, "no route declares the delegation grant"
    assert all(names == set(GRANT_PARAM_NAMES) for names in declaring.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("override, expected", [(1200.0, 900.0), (600.0, 600.0)])
async def test_background_registration_never_widens_the_server_owned_budget(
    monkeypatch: pytest.MonkeyPatch, override: float, expected: float
) -> None:
    async def allow_team(*args, **kwargs):
        return TeamId("team-1")

    async def binding(*args, **kwargs):
        return ManagedAgentRuntimeBinding(
            agent_instance_id="instance-1",
            template_agent_id="template-1",
            display_name="Agent",
            owner_team_id=TeamId("team-1"),
            tuning=ManagedAgentTuning(
                role="Agent", description="Agent", run_ceiling_seconds=override
            ),
        )

    monkeypatch.setattr(product_api, "require_team_access", allow_team)
    monkeypatch.setattr(product_api, "get_runtime_binding_for_team", binding)
    deps = type(
        "Deps",
        (),
        {
            "configuration": type(
                "Configuration",
                (),
                {"security": type("Security", (), {"profile": None})()},
            )(),
            "team_dependencies": type(
                "TeamDeps",
                (),
                {
                    "rebac": type(
                        "Rebac",
                        (),
                        {"require_user_standing": _require_person_standing},
                    )()
                },
            )(),
            "get_team_metadata_store": staticmethod(lambda: _LifecycleStore()),
        },
    )()
    store = _FakeRunStore()
    subject = AssertedUser(
        uid="person-1",
        client_id="runtime",
        run_id="run-1",
        agent_id="instance-1",
    )

    response = await register_agent_run(
        RegisterAgentRunRequest(
            agent_instance_id="instance-1",
            team_id=TeamId("team-1"),
            started_at=datetime(2026, 9, 17, 12, tzinfo=UTC),
            run_ceiling_seconds=900.0,
            mode="background",
        ),
        deps,  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        PrincipalContext(caller=_caller(), subject=subject),
    )

    assert response.run_ceiling_seconds == expected
    assert store.record is not None and store.record.run_ceiling_seconds == expected
