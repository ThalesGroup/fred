from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, cast

import pytest
from fred_core import RelationType, SessionSchema, TeamPermission
from fred_core.common import TeamId
from httpx import ASGITransport, AsyncClient
from keycloak.exceptions import KeycloakPutError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.app.dependencies import get_application_container_from_app
from control_plane_backend.config.models import (
    ManagedAgentFieldSpec,
    ManagedMcpServerRef,
    ManagedAgentTuning,
    RuntimeCatalogSourceConfig,
)
from control_plane_backend.main import create_app
from control_plane_backend.product.service import _RuntimeTemplatePayload
from control_plane_backend.sessions.store import SessionMetadataRecord
from control_plane_backend.teams.metadata_store import TeamMetadata
from control_plane_backend.teams.schemas import (
    KeycloakGroupSummary,
    Team,
    TeamWithPermissions,
)
from control_plane_backend.users.schemas import UserSummary


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


def _make_record(
    *,
    agent_instance_id: str = "instance-1",
    team_id: str = "personal",
    template_id: str = "runtime-a:rags.sample.echo",
    source_runtime_id: str = "runtime-a",
    source_agent_id: str = "rags.sample.echo",
    display_name: str = "Echo Team Agent",
    description: str | None = "Managed echo agent",
    enabled: bool = True,
    created_by: str | None = "internal-admin",
) -> AgentInstanceRecord:
    return AgentInstanceRecord(
        agent_instance_id=agent_instance_id,
        team_id=TeamId(team_id),
        template_id=template_id,
        source_runtime_id=source_runtime_id,
        source_agent_id=source_agent_id,
        display_name=display_name,
        description=description,
        enabled=enabled,
        created_by=created_by,
        tuning=ManagedAgentTuning(
            role=display_name,
            description=description or display_name,
        ),
    )


class _FakeAgentInstanceStore:
    """In-memory stand-in for AgentInstanceStore used in offline tests."""

    def __init__(self, records: list[AgentInstanceRecord] | None = None) -> None:
        self._records: list[AgentInstanceRecord] = list(records or [])

    async def list_by_team(self, team_id: TeamId) -> list[AgentInstanceRecord]:
        return [r for r in self._records if r.team_id == team_id]

    async def get(self, agent_instance_id: str) -> AgentInstanceRecord | None:
        return next(
            (r for r in self._records if r.agent_instance_id == agent_instance_id),
            None,
        )

    async def get_for_team(
        self, agent_instance_id: str, team_id: TeamId
    ) -> AgentInstanceRecord | None:
        return next(
            (
                r
                for r in self._records
                if r.agent_instance_id == agent_instance_id and r.team_id == team_id
            ),
            None,
        )

    async def create(self, record: AgentInstanceRecord) -> AgentInstanceRecord:
        self._records.append(record)
        return record

    async def update(
        self,
        agent_instance_id: str,
        team_id: TeamId,
        *,
        display_name: str | None = None,
        description: str | None = None,
        tuning: ManagedAgentTuning | None = None,
    ) -> AgentInstanceRecord | None:
        record = next(
            (
                r
                for r in self._records
                if r.agent_instance_id == agent_instance_id and r.team_id == team_id
            ),
            None,
        )
        if record is None:
            return None
        if display_name is not None:
            record.display_name = display_name
        if description is not None:
            record.description = description
        if tuning is not None:
            record.tuning = tuning
        return record

    async def delete(self, agent_instance_id: str, team_id: TeamId) -> bool:
        before = len(self._records)
        self._records = [
            r
            for r in self._records
            if not (r.agent_instance_id == agent_instance_id and r.team_id == team_id)
        ]
        return len(self._records) < before


def _patch_store(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeAgentInstanceStore,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_agent_instance_store",
        lambda _self: store,
    )


class _FakeSessionMetadataStore:
    """In-memory stand-in for SessionMetadataStore used in offline tests."""

    def __init__(self, records: list[SessionMetadataRecord] | None = None) -> None:
        self._records: list[SessionMetadataRecord] = list(records or [])

    async def update_last_activity(
        self,
        session_id: str,
        team_id: TeamId,
        updated_at: datetime,
    ) -> SessionMetadataRecord | None:
        for record in self._records:
            if record.session_id == session_id and record.team_id == team_id:
                record.updated_at = updated_at
                return record
        return None


class _DuplicateSessionMetadataStore:
    """Offline stand-in that always reproduces one duplicate session conflict."""

    async def create(self, _record: SessionMetadataRecord) -> SessionMetadataRecord:
        """Raise the duplicate-session store error expected by the API layer."""
        from control_plane_backend.sessions.store import (
            SessionMetadataAlreadyExistsError,
        )

        raise SessionMetadataAlreadyExistsError("session-duplicate")


def _patch_session_store(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeSessionMetadataStore,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_session_metadata_store",
        lambda _self: store,
    )


async def _fake_get_team_by_id(
    _user: Any,
    _team_id: Any,
    _deps: Any | None = None,
) -> TeamWithPermissions:
    return TeamWithPermissions(
        id=TeamId("personal"),
        name="Personal",
        member_count=1,
        is_private=True,
        owners=[],
        permissions=[],
    )


@pytest.mark.asyncio
async def test_healthz_endpoint() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/healthz")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_app_initializes_application_container_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify the app factory builds and wires one application container.

    Why this test exists:
    - Slice 1 moves startup registration out of `ApplicationContext.__init__()`
      and into explicit composition-root wiring
    - the FastAPI factory should still build only one container and attach it to
      the app state for future DI-based dependencies

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_main.py -q`
    """

    created_configurations: list[object] = []
    initialized_containers: list[object] = []

    class _FakeContainer:
        def __init__(self, configuration: object) -> None:
            created_configurations.append(configuration)

        async def shutdown(self) -> None:
            return None

    def _build_application_container(configuration: object) -> _FakeContainer:
        return _FakeContainer(configuration)

    monkeypatch.setattr(
        "control_plane_backend.main.build_application_container",
        _build_application_container,
    )
    monkeypatch.setattr(
        "control_plane_backend.main.initialize_shared_stores",
        lambda container: initialized_containers.append(container),
    )

    app = create_app()

    assert len(created_configurations) == 1
    assert len(initialized_containers) == 1
    assert get_application_container_from_app(app) is initialized_containers[0]


@pytest.mark.asyncio
async def test_resolve_purge_policy_team_override() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/policies/purge/resolve",
            json={"team_id": "swiftpost", "trigger": "member_removed"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["retention"] == "PT60S"
    assert payload["matched_rule_id"] == "purge.team.swiftpost"


@pytest.mark.asyncio
async def test_list_users_returns_empty_without_keycloak_m2m() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/users")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_user_requires_keycloak_m2m() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/users",
            json={
                "username": "test-user",
                "email": "test-user@app.local",
                "password": "Password123!",  # pragma: allowlist secret
            },
        )

    assert resp.status_code == 503
    assert (
        resp.json()["detail"]
        == "Keycloak M2M is disabled; cannot perform user operations."
    )


@pytest.mark.asyncio
async def test_delete_user_requires_keycloak_m2m() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete("/control-plane/v1/users/user-001")

    assert resp.status_code == 503
    assert (
        resp.json()["detail"]
        == "Keycloak M2M is disabled; cannot perform user operations."
    )


@pytest.mark.asyncio
async def test_list_teams_returns_personal_without_keycloak_m2m() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams")

    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": "personal",
            "name": "Equipe personnelle",
            "member_count": 1,
            "owners": [],
            "is_member": False,
            "is_private": True,
        }
    ]


@pytest.mark.asyncio
async def test_frontend_bootstrap_returns_typed_phase_3a_surface() -> None:
    app = create_app()
    container = get_application_container_from_app(app)
    container.configuration.app.gcu_version = "V1"
    container.configuration.platform.frontend.ui_settings.siteDisplayName = (
        "Fred Control Plane"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/frontend/bootstrap")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["current_user"]["id"] == "admin"
    assert payload["active_team"]["id"] == "personal"
    assert payload["available_teams"][0]["id"] == "personal"
    assert payload["gcu_version"] == "V1"
    assert payload["feature_flags"]["enableK8Features"] is False
    assert payload["ui_settings"]["siteDisplayName"] == "Fred Control Plane"
    assert "agents:read" in payload["permissions"]["items"]
    assert payload["permissions"]["can_manage_team_agents"] is True


@pytest.mark.asyncio
async def test_get_personal_team_returns_shared_system_team_contract() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/personal")

    assert resp.status_code == 200
    assert resp.json() == {
        "id": "personal",
        "name": "Equipe personnelle",
        "member_count": 1,
        "owners": [],
        "is_member": False,
        "is_private": True,
        "permissions": [
            "can_read",
            "can_update_resources",
            "can_update_agents",
        ],
    }


@pytest.mark.asyncio
async def test_user_details_reuses_shared_personal_team_contract() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/user")

    assert resp.status_code == 200
    assert resp.json()["personalTeam"]["id"] == "personal"
    assert resp.json()["personalTeam"]["permissions"] == [
        "can_read",
        "can_update_resources",
        "can_update_agents",
    ]


@pytest.mark.asyncio
async def test_team_agent_templates_returns_empty_without_runtime_sources() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/personal/agent-templates")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_team_agent_templates_aggregates_runtime_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch_runtime_templates(_base_url: str):
        return [
            _RuntimeTemplatePayload(
                template_agent_id="rags.sample.echo",
                title="Echo Agent",
                description="Echo test agent",
                kind="assistant",
            )
        ]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_runtime_templates,
    )

    app = create_app()
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-a",
            base_url="http://runtime-a/pod/v1",
            enabled=True,
        )
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/personal/agent-templates")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload == [
        {
            "template_id": "runtime-a:rags.sample.echo",
            "source_runtime_id": "runtime-a",
            "source_agent_id": "rags.sample.echo",
            "display_name": "Echo Agent",
            "description": "Echo test agent",
            "category": "assistant",
            "tags": [],
            "capabilities": ["assistant"],
            "team_instantiable": True,
            "status": "available",
            "default_tuning_fields": [],
        }
    ]


@pytest.mark.asyncio
async def test_team_agent_instances_returns_managed_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAgentInstanceStore([_make_record()])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        list_resp = await client.get("/control-plane/v1/teams/personal/agent-instances")

    assert list_resp.status_code == 200
    assert list_resp.json() == [
        {
            "agent_instance_id": "instance-1",
            "team_id": "personal",
            "template_id": "runtime-a:rags.sample.echo",
            "display_name": "Echo Team Agent",
            "description": "Managed echo agent",
            "status": "enabled",
            "created_by": "internal-admin",
            "tuning_field_values": {},
        }
    ]


@pytest.mark.asyncio
async def test_runtime_binding_endpoint_requires_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAgentInstanceStore([_make_record()])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        runtime_resp = await client.get(
            "/control-plane/v1/agent-instances/instance-1/runtime"
        )

    assert runtime_resp.status_code == 200
    assert runtime_resp.json()["agent_instance_id"] == "instance-1"
    assert runtime_resp.json()["template_agent_id"] == "rags.sample.echo"
    assert runtime_resp.json()["owner_team_id"] == "personal"


@pytest.mark.asyncio
async def test_prepare_execution_returns_ingress_relative_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore(
        [
            _make_record(
                agent_instance_id="inst-42",
                source_runtime_id="agents-v2",
                template_id="agents-v2:rags.sample.echo",
                source_agent_id="rags.sample.echo",
                display_name="Echo Agent",
                description="Test",
            )
        ]
    )
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="agents-v2",
            base_url="http://agents-v2-svc.fred.svc.cluster.local/api/v1",
            enabled=True,
            ingress_prefix="/runtime/agents-v2",
        )
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/inst-42/prepare-execution"
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["agent_instance_id"] == "inst-42"
    assert payload["team_id"] == "personal"
    assert payload["runtime_id"] == "agents-v2"
    assert payload["execution_transport"] == "sse"
    assert payload["execute_url"] == "/runtime/agents-v2/agents/execute"
    assert payload["execute_stream_url"] == "/runtime/agents-v2/agents/execute/stream"
    assert (
        payload["messages_url_template"]
        == "/runtime/agents-v2/agents/sessions/{session_id}/messages"
    )
    assert payload["supports_streaming"] is True
    assert payload["supports_hitl"] is True
    assert "execution_grant" in payload
    grant = payload["execution_grant"]
    assert grant["user_id"] == "admin"
    assert grant["team_id"] == "personal"
    assert grant["agent_instance_id"] == "inst-42"
    assert grant["action"] == "execute"
    assert grant["audience"] == "/runtime/agents-v2"
    assert grant["expires_at"] > grant["issued_at"]
    for url_field in ("execute_url", "execute_stream_url", "messages_url_template"):
        assert "svc.cluster.local" not in payload[url_field]
        assert payload[url_field].startswith("/")


@pytest.mark.asyncio
async def test_prepare_execution_returns_404_for_unknown_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/no-such/prepare-execution"
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_prepare_execution_returns_409_for_disabled_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore(
        [_make_record(agent_instance_id="inst-disabled", enabled=False)]
    )
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/inst-disabled/prepare-execution"
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_prepare_execution_returns_503_when_ingress_prefix_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore(
        [
            _make_record(
                agent_instance_id="inst-no-prefix",
                source_runtime_id="agents-v2",
                template_id="agents-v2:rags.sample.echo",
            )
        ]
    )
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="agents-v2",
            base_url="http://agents-v2-svc.fred.svc.cluster.local/api/v1",
            enabled=True,
        )
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/inst-no-prefix/prepare-execution"
        )

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_prepare_execution_team_mismatch_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore(
        [
            _make_record(
                agent_instance_id="inst-other-team",
                team_id="team-b",
                source_runtime_id="agents-v2",
                template_id="agents-v2:rags.sample.echo",
            )
        ]
    )
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="agents-v2",
            base_url="http://agents-v2-svc/api/v1",
            enabled=True,
            ingress_prefix="/runtime/agents-v2",
        )
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/inst-other-team/prepare-execution"
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enroll_agent_instance_creates_db_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([])
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-a",
            base_url="http://runtime-a/pod/v1",
            enabled=True,
            ingress_prefix="/runtime/runtime-a",
        )
    ]

    async def _fake_fetch_runtime_templates(_base_url: str):
        return [
            _RuntimeTemplatePayload(
                template_agent_id="rags.sample.echo",
                title="Echo Agent",
                description="Echo template description",
                kind="assistant",
                default_tuning=ManagedAgentTuning(
                    role="Echo Agent",
                    description="Echo template description",
                    tags=["ops"],
                    mcp_servers=[
                        ManagedMcpServerRef(id="mcp-knowledge-flow-opensearch-ops")
                    ],
                ),
            )
        ]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_runtime_templates,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "My Echo Agent",
                "description": "A test echo agent",
            },
        )

    assert resp.status_code == 201
    payload = resp.json()
    assert payload["team_id"] == "personal"
    assert payload["template_id"] == "runtime-a:rags.sample.echo"
    assert payload["display_name"] == "My Echo Agent"
    assert payload["description"] == "A test echo agent"
    assert payload["status"] == "enabled"
    assert payload["created_by"] == "admin"
    assert "agent_instance_id" in payload
    assert len(store._records) == 1
    assert store._records[0].source_runtime_id == "runtime-a"
    assert store._records[0].source_agent_id == "rags.sample.echo"
    assert store._records[0].tuning.tags == ["ops"]
    assert [server.id for server in store._records[0].tuning.mcp_servers] == [
        "mcp-knowledge-flow-opensearch-ops"
    ]


@pytest.mark.asyncio
async def test_agent_instance_store_create_overrides_sqlite_now_default(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "agent-instance.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE agent_instance (
                    agent_instance_id VARCHAR NOT NULL PRIMARY KEY,
                    team_id VARCHAR NOT NULL,
                    template_id VARCHAR NOT NULL,
                    source_runtime_id VARCHAR NOT NULL,
                    source_agent_id VARCHAR NOT NULL,
                    display_name VARCHAR(255) NOT NULL,
                    description VARCHAR(500),
                    enabled BOOLEAN NOT NULL,
                    created_by VARCHAR,
                    tuning_json TEXT,
                    created_at DATETIME NOT NULL DEFAULT (now()),
                    updated_at DATETIME NOT NULL DEFAULT (now())
                )
                """
            )
        )

    try:
        store = AgentInstanceStore(engine)
        created = await store.create(
            AgentInstanceRecord(
                agent_instance_id="inst-sqlite-now",
                team_id=TeamId("personal"),
                template_id="runtime-a:rags.sample.echo",
                source_runtime_id="runtime-a",
                source_agent_id="rags.sample.echo",
                display_name="SQLite-safe agent",
                description="Created with Python timestamps",
                enabled=True,
                created_by="admin",
                tuning=ManagedAgentTuning(
                    role="SQLite-safe agent",
                    description="Created with Python timestamps",
                ),
            )
        )

        assert created is not None
        assert created.agent_instance_id == "inst-sqlite-now"
        assert created.created_at is not None
        assert created.updated_at is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_patch_team_session_updates_last_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    initial = datetime.fromisoformat("2026-04-23T08:00:00+00:00")
    refreshed = datetime.fromisoformat("2026-04-23T08:05:00+00:00")
    store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="First turn",
                created_at=initial,
                updated_at=initial,
            )
        ]
    )
    _patch_session_store(monkeypatch, store)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/sessions/session-1",
            json={"updated_at": refreshed.isoformat()},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["session_id"] == "session-1"
    assert payload["team_id"] == "personal"
    assert payload["updated_at"] == "2026-04-23T08:05:00Z"
    assert store._records[0].updated_at == refreshed


@pytest.mark.asyncio
async def test_patch_team_session_returns_404_for_other_team_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("other-team"),
                agent_instance_id="instance-1",
                user_id="admin",
                title=None,
            )
        ]
    )
    _patch_session_store(monkeypatch, store)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/sessions/session-1",
            json={"updated_at": "2026-04-23T08:05:00+00:00"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_team_session_returns_conflict_for_duplicate_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify duplicate control-plane session creation returns HTTP 409.

    Why this test exists:
    - API conflict handling should rely on explicit store/domain errors instead
      of brittle string parsing of SQL exceptions

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_main.py -q`
    """

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    _patch_session_store(
        monkeypatch,
        cast(Any, _DuplicateSessionMetadataStore()),
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/sessions",
            json={
                "session_id": "session-duplicate",
                "agent_instance_id": "instance-1",
                "title": "Existing session",
            },
        )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Session 'session-duplicate' already exists."


@pytest.mark.asyncio
async def test_enroll_agent_instance_returns_404_for_unknown_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([])
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = []

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "unknown-runtime:some-agent",
                "display_name": "Agent",
            },
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enroll_agent_instance_returns_400_for_malformed_template_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={"template_id": "no-colon-here", "display_name": "Agent"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_agent_instance_removes_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([_make_record()])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/personal/agent-instances/instance-1"
        )

    assert resp.status_code == 204
    assert len(store._records) == 0


@pytest.mark.asyncio
async def test_delete_agent_instance_returns_404_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/personal/agent-instances/no-such"
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_agent_instance_enforces_team_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([_make_record(team_id="other-team")])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/personal/agent-instances/instance-1"
        )

    assert resp.status_code == 404
    assert len(store._records) == 1  # record belonging to other-team is untouched


@pytest.mark.asyncio
async def test_teams_preflight_options_is_handled_by_cors() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.options(
            "/control-plane/v1/teams",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("relation", "expected_permission"),
    [
        ("member", TeamPermission.CAN_ADMINISTER_MEMBERS),
        ("manager", TeamPermission.CAN_ADMINISTER_MANAGERS),
        ("owner", TeamPermission.CAN_ADMINISTER_OWNERS),
    ],
)
async def test_add_team_member_checks_permission_for_target_relation(
    monkeypatch: pytest.MonkeyPatch,
    relation: str,
    expected_permission: TeamPermission,
) -> None:
    class _FakeKeycloakAdmin:
        async def a_group_user_add(self, _user_id: str, _group_id: str) -> None:
            return None

    captured_permissions: list[list[TeamPermission]] = []

    async def _fake_validate_team_and_check_permission(
        *_args,
        **_kwargs,
    ):
        permissions = _args[3]
        captured_permissions.append(permissions)
        return _FakeKeycloakAdmin(), {"id": "thales", "name": "Thales"}, None

    async def _fake_add_team_member_relation(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._add_team_member_relation",
        _fake_add_team_member_relation,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/thales/members",
            json={"user_id": "user-001", "relation": relation},
        )

    assert resp.status_code == 204
    assert captured_permissions == [[expected_permission]]


@pytest.mark.asyncio
async def test_update_team_checks_can_update_info_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeMetadataStore:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def upsert(self, team_id: str, patch, session=None) -> TeamMetadata:
            self.calls.append((team_id, patch.model_dump(exclude_unset=True)))
            return TeamMetadata(id=TeamId(team_id))

    class _FakeKeycloakAdmin:
        async def a_get_group_members(self, _team_id: str, _query: dict) -> list[dict]:
            return []

    fake_metadata_store = _FakeMetadataStore()
    captured_permissions: list[list[TeamPermission]] = []

    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        permissions = _args[3]
        captured_permissions.append(permissions)
        return _FakeKeycloakAdmin(), {"id": "thales", "name": "Thales"}, "token"

    async def _fake_get_team_permissions_for_user(*_args, **_kwargs):
        return [TeamPermission.CAN_UPDATE_INFO]

    async def _fake_enrich_groups_with_team_data(*_args, **_kwargs):
        return [Team(id=TeamId("thales"), name="Thales")]

    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_team_permissions_for_user",
        _fake_get_team_permissions_for_user,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._enrich_groups_with_team_data",
        _fake_enrich_groups_with_team_data,
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_team_metadata_store",
        lambda _self: fake_metadata_store,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/thales",
            json={
                "description": "Updated description",
                "is_private": False,
                "banner_image_url": "https://example.test/banner.webp",
            },
        )

    assert resp.status_code == 200
    assert captured_permissions == [[TeamPermission.CAN_UPDATE_INFO]]
    assert fake_metadata_store.calls == [
        (
            "thales",
            {
                "description": "Updated description",
                "is_private": False,
                "banner_image_url": "https://example.test/banner.webp",
            },
        )
    ]


@pytest.mark.asyncio
async def test_enrich_groups_uses_team_metadata_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.teams.dependencies import TeamServiceDependencies
    from control_plane_backend.teams.service import _enrich_groups_with_team_data

    class _FakeMetadataStore:
        async def get_by_team_ids(
            self, _team_ids: list[TeamId], session=None
        ) -> dict[TeamId, TeamMetadata]:
            return {
                TeamId("team-1"): TeamMetadata(
                    id=TeamId("team-1"),
                    description="desc",
                    is_private=False,
                    banner_object_storage_key="teams/team-1/banner-1.png",
                )
            }

    class _FakeContentStore:
        def get_presigned_url(self, key: str, expires=None) -> str:
            _ = expires
            assert key == "teams/team-1/banner-1.png"
            return "https://example.test/banner.png"

    class _FakeAdmin:
        async def a_get_group_members(self, _group_id: str, _query: dict) -> list[dict]:
            return [{"id": "user-1"}]

    async def _fake_get_team_users_by_relation(*_args, **_kwargs):
        return set()

    async def _fake_get_users_by_ids(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_team_users_by_relation",
        _fake_get_team_users_by_relation,
    )
    fake_deps = TeamServiceDependencies(
        configuration=cast(Any, object()),
        rebac=cast(Any, object()),
        scheduler_backend=cast(Any, object()),
        create_keycloak_admin_client=cast(Any, lambda: object()),
        get_team_metadata_store=lambda: cast(Any, _FakeMetadataStore()),
        get_content_store=lambda: cast(Any, _FakeContentStore()),
        get_session_store=cast(Any, lambda: object()),
        get_purge_queue_store=cast(Any, lambda: object()),
        get_policy_catalog=cast(Any, lambda: object()),
        get_users_by_ids=_fake_get_users_by_ids,
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _input: object()),
    )

    teams = await _enrich_groups_with_team_data(
        cast(Any, _FakeAdmin()),
        rebac=cast(
            Any, object()
        ),  # unused due monkeypatching _get_team_users_by_relation
        user=cast(Any, type("User", (), {"uid": "user-1"})()),
        groups=[
            KeycloakGroupSummary(id=TeamId("team-1"), name="Team 1", member_count=0)
        ],
        deps=fake_deps,
    )

    assert len(teams) == 1
    assert teams[0].description == "desc"
    assert teams[0].is_private is False
    assert teams[0].banner_image_url == "https://example.test/banner.png"


@pytest.mark.asyncio
async def test_enrich_groups_dedupes_owner_alias_and_canonical_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.teams.dependencies import TeamServiceDependencies
    from control_plane_backend.teams.service import _enrich_groups_with_team_data

    class _FakeMetadataStore:
        async def get_by_team_ids(
            self, _team_ids: list[TeamId], session=None
        ) -> dict[TeamId, TeamMetadata]:
            return {}

    class _FakeContentStore:
        def get_presigned_url(self, key: str, expires=None) -> str:
            _ = key
            _ = expires
            raise AssertionError("No banner lookup expected in this test.")

    class _FakeAdmin:
        async def a_get_group_members(self, _group_id: str, _query: dict) -> list[dict]:
            return [{"id": "user-1"}]

    async def _fake_get_team_users_by_relation(*_args, **_kwargs):
        return {"user-1", "marc"}

    async def _fake_get_users_by_ids(*_args, **_kwargs):
        return {
            "user-1": UserSummary(id="user-1", username="marc"),
            "marc": UserSummary(id="marc"),
        }

    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_team_users_by_relation",
        _fake_get_team_users_by_relation,
    )
    fake_deps = TeamServiceDependencies(
        configuration=cast(Any, object()),
        rebac=cast(Any, object()),
        scheduler_backend=cast(Any, object()),
        create_keycloak_admin_client=cast(Any, lambda: object()),
        get_team_metadata_store=lambda: cast(Any, _FakeMetadataStore()),
        get_content_store=lambda: cast(Any, _FakeContentStore()),
        get_session_store=cast(Any, lambda: object()),
        get_purge_queue_store=cast(Any, lambda: object()),
        get_policy_catalog=cast(Any, lambda: object()),
        get_users_by_ids=_fake_get_users_by_ids,
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _input: object()),
    )

    teams = await _enrich_groups_with_team_data(
        cast(Any, _FakeAdmin()),
        rebac=cast(Any, object()),
        user=cast(Any, type("User", (), {"uid": "user-1"})()),
        groups=[
            KeycloakGroupSummary(id=TeamId("team-1"), name="fredlab", member_count=0)
        ],
        deps=fake_deps,
    )

    assert len(teams) == 1
    assert [owner.username or owner.id for owner in teams[0].owners] == ["marc"]


@pytest.mark.asyncio
async def test_upload_team_banner_checks_can_update_info_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeContentStore:
        def __init__(self) -> None:
            self.calls: list[tuple[str, bytes, str]] = []

        def put_object(self, key: str, stream, *, content_type: str) -> None:
            self.calls.append((key, stream.read(), content_type))

    class _FakeMetadataStore:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        async def upsert(self, team_id: str, patch, session=None) -> TeamMetadata:
            self.calls.append((team_id, patch.model_dump(exclude_unset=True)))
            return TeamMetadata(id=TeamId(team_id))

    fake_content_store = _FakeContentStore()
    fake_metadata_store = _FakeMetadataStore()
    captured_permissions: list[list[TeamPermission]] = []

    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        permissions = _args[3]
        captured_permissions.append(permissions)
        return object(), {"id": "thales", "name": "Thales"}, None

    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_content_store",
        lambda _self: fake_content_store,
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_team_metadata_store",
        lambda _self: fake_metadata_store,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/thales/banner",
            files={"file": ("banner.png", b"\x89PNG\r\n\x1a\nbanner", "image/png")},
        )

    assert resp.status_code == 204
    assert captured_permissions == [[TeamPermission.CAN_UPDATE_INFO]]
    assert len(fake_content_store.calls) == 1
    object_key, uploaded_payload, uploaded_content_type = fake_content_store.calls[0]
    assert object_key.startswith("teams/thales/banner-")
    assert object_key.endswith(".png")
    assert uploaded_content_type == "image/png"
    assert uploaded_payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert fake_metadata_store.calls == [
        ("thales", {"banner_object_storage_key": object_key})
    ]


@pytest.mark.asyncio
async def test_upload_team_banner_rejects_invalid_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        return object(), {"id": "thales", "name": "Thales"}, None

    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/thales/banner",
            files={"file": ("banner.txt", b"not-an-image", "text/plain")},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid content type: text/plain"


@pytest.mark.asyncio
async def test_upload_team_banner_rejects_file_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        return object(), {"id": "thales", "name": "Thales"}, None

    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )

    app = create_app()
    too_large_payload = b"\x89PNG\r\n\x1a\n" + b"a" * (5 * 1024 * 1024)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/thales/banner",
            files={"file": ("banner.png", too_large_payload, "image/png")},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("File too large:")


@pytest.mark.asyncio
async def test_add_team_member_returns_clear_error_when_keycloak_forbids_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeKeycloakAdmin:
        async def a_group_user_add(self, _user_id: str, _group_id: str) -> None:
            raise KeycloakPutError(
                error_message="HTTP 403 Forbidden",
                response_code=403,
                response_body=b'{"error":"HTTP 403 Forbidden"}',
            )

    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        return _FakeKeycloakAdmin(), {"id": "thales", "name": "Thales"}, None

    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/thales/members",
            json={"user_id": "user-001", "relation": "member"},
        )

    assert resp.status_code == 403
    assert (
        resp.json()["detail"]
        == "Control Plane is not allowed to manage team membership in Keycloak. "
        "Ask platform admin to grant realm-management/manage-users "
        "to the 'control-plane' client service account."
    )


@pytest.mark.asyncio
async def test_delete_team_member_requires_keycloak_m2m() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/contractors/members/user-001",
        )

    assert resp.status_code == 503
    payload = resp.json()
    assert (
        payload["detail"] == "Keycloak M2M is disabled; cannot perform team operations."
    )


@pytest.mark.asyncio
async def test_delete_team_member_enqueues_matching_team_sessions(monkeypatch) -> None:
    class _FakeKeycloakAdmin:
        async def a_get_group(self, _group_id: str) -> dict[str, str]:
            return {"id": "swiftpost", "name": "SwiftPost"}

        async def a_group_user_remove(self, _user_id: str, _group_id: str) -> None:
            return None

    class _FakeRebac:
        def __init__(self) -> None:
            self.delete_relations_calls = 0

        async def delete_relations(self, _relations) -> None:
            self.delete_relations_calls += 1

    class _FakeSessionStore:
        async def get_for_user(
            self, _user_id: str, team_id: Optional[str], db_session=None
        ) -> list[SessionSchema]:
            return [
                SessionSchema(
                    id="s-1",
                    user_id=_user_id,
                    team_id=team_id,
                    title="",
                    updated_at=datetime.now(),
                ),
                SessionSchema(
                    id="s-3",
                    user_id=_user_id,
                    team_id=team_id,
                    title="",
                    updated_at=datetime.now(),
                ),
            ]

    class _FakeQueueStore:
        def __init__(self) -> None:
            self.enqueued: list[tuple[str, str, str, datetime]] = []

        async def enqueue(
            self,
            *,
            session_id: str,
            team_id: str,
            user_id: str,
            due_at: datetime,
            session=None,
        ) -> None:
            self.enqueued.append((session_id, team_id, user_id, due_at))

    fake_rebac = _FakeRebac()
    fake_queue = _FakeQueueStore()

    async def _fake_get_user_role_in_team(*_args, **_kwargs):
        from control_plane_backend.teams.schemas import UserTeamRelation

        return UserTeamRelation.MEMBER

    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        return _FakeKeycloakAdmin(), {"id": "swiftpost", "name": "SwiftPost"}, None

    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_user_role_in_team",
        _fake_get_user_role_in_team,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_rebac_engine",
        lambda _self: fake_rebac,
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_session_store",
        lambda _self: _FakeSessionStore(),
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_purge_queue_store",
        lambda _self: fake_queue,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/swiftpost/members/user-002",
        )

    assert resp.status_code == 202
    payload = resp.json()
    assert payload["status"] == "accepted"
    assert payload["team_id"] == "swiftpost"
    assert payload["user_id"] == "user-002"
    assert payload["sessions_enqueued"] == 2
    assert payload["policy_mode"] == "deferred_delete"
    assert payload["retention_seconds"] == 60
    assert payload["matched_rule_id"] == "purge.team.swiftpost"
    assert len(fake_queue.enqueued) == 2
    assert fake_queue.enqueued[0][0] == "s-1"
    assert fake_queue.enqueued[1][0] == "s-3"
    assert fake_rebac.delete_relations_calls == 1


@pytest.mark.asyncio
async def test_delete_team_member_runs_in_memory_lifecycle_pass_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_core.scheduler import SchedulerBackend
    from control_plane_backend.scheduler.policies.policy_models import (
        PolicyEvaluationResult,
        PurgeMode,
    )
    from control_plane_backend.scheduler.temporal.structures import (
        LifecycleManagerResult,
    )
    from control_plane_backend.teams.dependencies import TeamServiceDependencies

    class _FakeKeycloakAdmin:
        async def a_group_user_remove(self, _user_id: str, _group_id: str) -> None:
            return None

    class _FakeRebac:
        async def delete_relations(self, _relations) -> None:
            return None

    class _FakeSessionStore:
        async def get_for_user(
            self, _user_id: str, db_session=None
        ) -> list[SessionSchema]:
            return [
                SessionSchema(
                    id="s-1",
                    user_id=_user_id,
                    team_id="temp-lab",
                    title="",
                    updated_at=datetime.now(),
                )
            ]

    class _FakeQueueStore:
        async def enqueue(
            self,
            *,
            session_id: str,
            team_id: str,
            user_id: str,
            due_at: datetime,
            session=None,
        ) -> None:
            _ = (session_id, team_id, user_id, due_at)

    lifecycle_calls: list[int] = []
    fake_rebac = _FakeRebac()
    fake_session_store = _FakeSessionStore()
    fake_queue_store = _FakeQueueStore()

    async def _fake_get_user_role_in_team(*_args, **_kwargs):
        from control_plane_backend.teams.schemas import UserTeamRelation

        return UserTeamRelation.MEMBER

    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        return _FakeKeycloakAdmin(), {"id": "temp-lab", "name": "Temp Lab"}, None

    async def _fake_run_lifecycle_manager_once_in_memory(_input_data):
        lifecycle_calls.append(1)
        return LifecycleManagerResult(scanned=1, deleted=1, dry_run_actions=0)

    def _fake_evaluate_policy_for_request(*_args, **_kwargs):
        return PolicyEvaluationResult(
            mode=PurgeMode.IMMEDIATE_DELETE,
            retention="PT0S",
            retention_seconds=0,
            cancel_on_rejoin=True,
            matched_rule_id="purge.team.temp-lab",
            matched_rule_specificity=2,
        )

    async def _fake_get_users_by_ids(_user_ids):
        return {}

    fake_scheduler = type("SchedulerCfg", (), {"enabled": True})()
    fake_configuration = type("Cfg", (), {"scheduler": fake_scheduler})()
    fake_team_deps = TeamServiceDependencies(
        configuration=cast(Any, fake_configuration),
        rebac=cast(Any, fake_rebac),
        scheduler_backend=SchedulerBackend.MEMORY,
        create_keycloak_admin_client=cast(Any, lambda: _FakeKeycloakAdmin()),
        get_team_metadata_store=lambda: cast(Any, object()),
        get_content_store=lambda: cast(Any, object()),
        get_session_store=cast(Any, lambda: fake_session_store),
        get_purge_queue_store=cast(Any, lambda: fake_queue_store),
        get_policy_catalog=cast(Any, lambda: object()),
        get_users_by_ids=_fake_get_users_by_ids,
        run_lifecycle_manager_once_in_memory=_fake_run_lifecycle_manager_once_in_memory,
    )

    monkeypatch.setattr(
        "control_plane_backend.teams.dependencies.build_team_service_dependencies",
        lambda *_args, **_kwargs: fake_team_deps,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_user_role_in_team",
        _fake_get_user_role_in_team,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service.evaluate_policy_for_request",
        _fake_evaluate_policy_for_request,
    )
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/temp-lab/members/user-002",
        )

    assert resp.status_code == 202
    assert lifecycle_calls == [1]


@pytest.mark.asyncio
async def test_lifecycle_run_once_executes_in_memory_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fred_core.common import parse_yaml_mapping_file

    from control_plane_backend.config.models import Configuration
    from control_plane_backend.scheduler.temporal.structures import (
        LifecycleManagerResult,
    )

    payload = parse_yaml_mapping_file("./config/configuration.yaml")
    payload["scheduler"]["enabled"] = True
    payload["scheduler"]["backend"] = "memory"
    config = Configuration.model_validate(payload)

    async def _fake_run_lifecycle_manager_once_in_memory(_input_data, *, deps=None):
        _ = deps
        return LifecycleManagerResult(scanned=2, deleted=2, dry_run_actions=0)

    monkeypatch.setattr(
        "control_plane_backend.main.load_configuration",
        lambda: config,
    )
    monkeypatch.setattr(
        "control_plane_backend.main.run_lifecycle_manager_once_in_memory",
        _fake_run_lifecycle_manager_once_in_memory,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/lifecycle/run-once",
            json={"dry_run": False, "batch_size": 50},
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "completed",
        "backend": "memory",
        "workflow_id": None,
        "run_id": None,
        "result": {"scanned": 2, "deleted": 2, "dry_run_actions": 0},
    }


@pytest.mark.asyncio
async def test_update_team_member_blocks_last_owner_demotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.teams.schemas import UserTeamRelation

    async def _fake_get_user_role_in_team(*_args, **_kwargs):
        return UserTeamRelation.OWNER

    async def _fake_get_team_users_by_relation(
        _rebac,
        _team_id: TeamId,
        relation: RelationType,
    ) -> set[str]:
        if relation == RelationType.OWNER:
            return {"user-001"}
        return set()

    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_user_role_in_team",
        _fake_get_user_role_in_team,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_team_users_by_relation",
        _fake_get_team_users_by_relation,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/thales/members/user-001",
            json={"relation": "manager"},
        )

    assert resp.status_code == 409
    assert (
        resp.json()["detail"]
        == "Operation denied: a team must keep at least one owner."
    )


@pytest.mark.asyncio
async def test_remove_team_member_blocks_removing_last_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.teams.schemas import UserTeamRelation

    async def _fake_get_user_role_in_team(*_args, **_kwargs):
        return UserTeamRelation.OWNER

    async def _fake_get_team_users_by_relation(
        _rebac,
        _team_id: TeamId,
        relation: RelationType,
    ) -> set[str]:
        if relation == RelationType.OWNER:
            return {"user-001"}
        return set()

    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_user_role_in_team",
        _fake_get_user_role_in_team,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_team_users_by_relation",
        _fake_get_team_users_by_relation,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete("/control-plane/v1/teams/thales/members/user-001")

    assert resp.status_code == 409
    assert (
        resp.json()["detail"]
        == "Operation denied: a team must keep at least one owner."
    )


def _make_template_with_fields() -> "_RuntimeTemplatePayload":
    """Return a fake template payload that declares one tunable field."""
    return _RuntimeTemplatePayload(
        template_agent_id="rags.sample.echo",
        title="Echo Agent",
        description="Echo with fields",
        kind="assistant",
        default_tuning=ManagedAgentTuning(
            role="Echo Agent",
            description="Echo with fields",
            fields=[
                ManagedAgentFieldSpec(
                    key="persona",
                    type="string",
                    title="Persona",
                    description="Agent persona prompt",
                )
            ],
        ),
    )


@pytest.mark.asyncio
async def test_team_agent_templates_exposes_non_empty_tuning_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch_runtime_templates(_base_url: str):
        return [_make_template_with_fields()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_runtime_templates,
    )
    app = create_app()
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-a",
            base_url="http://runtime-a/pod/v1",
            enabled=True,
        )
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/personal/agent-templates")

    assert resp.status_code == 200
    fields = resp.json()[0]["default_tuning_fields"]
    assert len(fields) == 1
    assert fields[0]["key"] == "persona"
    assert fields[0]["type"] == "string"
    assert fields[0]["title"] == "Persona"


@pytest.mark.asyncio
async def test_enroll_agent_instance_stores_provided_field_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch_runtime_templates(_base_url: str):
        return [_make_template_with_fields()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_runtime_templates,
    )
    store = _FakeAgentInstanceStore([])
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-a",
            base_url="http://runtime-a/pod/v1",
            enabled=True,
        )
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "My Echo",
                "tuning_field_values": {"persona": "You are a helpful assistant."},
            },
        )

    assert resp.status_code == 201
    assert resp.json()["tuning_field_values"] == {
        "persona": "You are a helpful assistant."
    }
    assert store._records[0].tuning.values == {
        "persona": "You are a helpful assistant."
    }


@pytest.mark.asyncio
async def test_enroll_agent_instance_silently_drops_unknown_field_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch_runtime_templates(_base_url: str):
        return [_make_template_with_fields()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_runtime_templates,
    )
    store = _FakeAgentInstanceStore([])
    app = create_app()
    _patch_store(monkeypatch, store)
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-a",
            base_url="http://runtime-a/pod/v1",
            enabled=True,
        )
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances",
            json={
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "My Echo",
                "tuning_field_values": {
                    "persona": "valid",
                    "unknown_key": "should be dropped",
                },
            },
        )

    assert resp.status_code == 201
    assert resp.json()["tuning_field_values"] == {"persona": "valid"}
    assert "unknown_key" not in store._records[0].tuning.values


@pytest.mark.asyncio
async def test_patch_agent_instance_updates_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([_make_record()])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-1",
            json={"display_name": "Renamed Echo Agent"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["display_name"] == "Renamed Echo Agent"
    assert payload["agent_instance_id"] == "instance-1"
    assert payload["status"] == "enabled"


@pytest.mark.asyncio
async def test_patch_agent_instance_updates_tuning_field_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="instance-fields",
        team_id=TeamId("personal"),
        template_id="runtime-a:rags.sample.echo",
        source_runtime_id="runtime-a",
        source_agent_id="rags.sample.echo",
        display_name="Echo",
        description=None,
        enabled=True,
        created_by="admin",
        tuning=ManagedAgentTuning(
            role="Echo",
            description="Echo",
            fields=[
                ManagedAgentFieldSpec(key="persona", type="string", title="Persona")
            ],
            values={"persona": "old value"},
        ),
    )
    store = _FakeAgentInstanceStore([record])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-fields",
            json={"tuning_field_values": {"persona": "new persona value"}},
        )

    assert resp.status_code == 200
    assert resp.json()["tuning_field_values"] == {"persona": "new persona value"}
    assert store._records[0].tuning.values == {"persona": "new persona value"}


@pytest.mark.asyncio
async def test_patch_agent_instance_returns_404_for_unknown_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakeAgentInstanceStore([])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/no-such",
            json={"display_name": "Whatever"},
        )

    assert resp.status_code == 404
