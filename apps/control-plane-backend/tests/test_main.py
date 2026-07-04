"""
Offline integration tests for the control-plane-backend product API.

Ref: docs/backlog/BACKLOG.md §3d — managed agent CRUD, enrollment, update, tuning
     field validation (type/enum/min-max/pattern), MCP server selection (C1),
     mcp_config_values per-server config;
     §3d.9 (P1) — prompt template validation at persistence boundary (unknown tokens → 422);
     §6.4.D — PATCH session endpoint (updated_at, title).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional, cast

import httpx
import pytest
from fred_core import (
    KeycloakUser,
    RelationType,
    SessionSchema,
    TeamPermission,
    get_current_user,
)
from fred_core.common import TeamId, personal_team_id
from fred_core.teams.metadata_store import TeamMetadata
from httpx import ASGITransport, AsyncClient
from keycloak.exceptions import KeycloakPutError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.app.dependencies import get_application_container_from_app
from control_plane_backend.config.models import (
    ManagedAgentFieldSpec,
    ManagedAgentTuning,
    ManagedMcpServerRef,
    RuntimeCatalogSourceConfig,
)
from control_plane_backend.main import create_app
from control_plane_backend.product.default_prompts import DEFAULT_PROMPTS
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    build_product_service_dependencies,
)
from control_plane_backend.product.service import (
    _delete_knowledge_flow_attachment,
    _RuntimeTemplatePayload,
)
from control_plane_backend.prompts.store import PromptRecord
from control_plane_backend.sessions.attachment_store import SessionAttachmentRecord
from control_plane_backend.sessions.store import SessionMetadataRecord
from control_plane_backend.teams.schemas import (
    KeycloakGroupSummary,
    Team,
    TeamWithPermissions,
)
from control_plane_backend.users.schemas import UserSummary


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


_PERSONAL_TEAM_ID = personal_team_id("admin")


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


def _make_prompt_record(
    *,
    prompt_id: str = "prompt-1",
    team_id: str = "personal",
    name: str = "Daily brief",
    description: str | None = "Ops baseline",
    text: str = "Today is {today}.",
    created_by: str | None = "internal-admin",
) -> PromptRecord:
    return PromptRecord(
        prompt_id=prompt_id,
        team_id=TeamId(team_id),
        name=name,
        description=description,
        text=text,
        created_by=created_by,
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
        enabled: bool | None = None,
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
        if enabled is not None:
            record.enabled = enabled
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

    async def update_metadata(
        self,
        session_id: str,
        team_id: TeamId,
        user_id: str,
        *,
        title: str | None = None,
        updated_at: datetime | None = None,
    ) -> SessionMetadataRecord | None:
        for record in self._records:
            if (
                record.session_id == session_id
                and record.team_id == team_id
                and record.user_id == user_id
            ):
                if title is not None:
                    record.title = title
                if updated_at is not None:
                    record.updated_at = updated_at
                return record
        return None

    async def replace_context_prompts(
        self,
        session_id: str,
        team_id: TeamId,
        user_id: str,
        prompt_ids: list[str],
    ) -> tuple[SessionMetadataRecord, list[str]] | None:
        ordered_ids: list[str] = []
        for prompt_id in prompt_ids:
            if prompt_id not in ordered_ids:
                ordered_ids.append(prompt_id)
        for record in self._records:
            if (
                record.session_id == session_id
                and record.team_id == team_id
                and record.user_id == user_id
            ):
                previous = set(record.context_prompt_ids)
                newly_attached = [pid for pid in ordered_ids if pid not in previous]
                record.context_prompt_ids = ordered_ids
                return record, newly_attached
        return None

    async def get(self, session_id: str) -> SessionMetadataRecord | None:
        return next((r for r in self._records if r.session_id == session_id), None)

    async def mark_deleted(
        self,
        session_id: str,
        team_id: TeamId,
        user_id: str,
        deleted_at: datetime,
    ) -> bool:
        for record in self._records:
            if (
                record.session_id == session_id
                and record.team_id == team_id
                and record.user_id == user_id
            ):
                record.deleted_at = deleted_at  # type: ignore[attr-defined]
                return True
        return False

    async def delete(self, session_id: str, team_id: TeamId, user_id: str) -> bool:
        before = len(self._records)
        self._records = [
            r
            for r in self._records
            if not (
                r.session_id == session_id
                and r.team_id == team_id
                and r.user_id == user_id
            )
        ]
        return len(self._records) < before


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


class _FakeSessionAttachmentStore:
    """In-memory stand-in for SessionAttachmentStore used in offline tests."""

    def __init__(self, records: list[SessionAttachmentRecord] | None = None) -> None:
        self._records: list[SessionAttachmentRecord] = list(records or [])

    async def save(self, record: SessionAttachmentRecord) -> None:
        self._records = [
            existing
            for existing in self._records
            if not (
                existing.session_id == record.session_id
                and existing.attachment_id == record.attachment_id
            )
        ]
        self._records.append(record)

    async def list_for_session(self, session_id: str) -> list[SessionAttachmentRecord]:
        return [record for record in self._records if record.session_id == session_id]

    async def delete(self, session_id: str, attachment_id: str) -> None:
        self._records = [
            record
            for record in self._records
            if not (
                record.session_id == session_id
                and record.attachment_id == attachment_id
            )
        ]

    async def delete_for_session(self, session_id: str) -> None:
        self._records = [
            record for record in self._records if record.session_id != session_id
        ]

    async def count_for_sessions(self, session_ids: list[str]) -> int:
        return len([r for r in self._records if r.session_id in session_ids])


def _patch_session_attachment_store(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakeSessionAttachmentStore,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_session_attachment_store",
        lambda _self: store,
    )


class _FakePromptStore:
    """In-memory stand-in for PromptStore used in offline tests."""

    def __init__(self, records: list[PromptRecord] | None = None) -> None:
        self._records: list[PromptRecord] = list(records or [])
        self._default_usage: dict[tuple[str, str], int] = {}

    async def create(self, record: PromptRecord) -> PromptRecord:
        if any(
            existing.team_id == record.team_id and existing.name == record.name
            for existing in self._records
        ):
            from control_plane_backend.prompts.store import PromptAlreadyExistsError

            raise PromptAlreadyExistsError(record.name)
        self._records.append(record)
        return record

    async def list_by_team(
        self,
        team_id: TeamId,
        *,
        limit: int = 100,
    ) -> list[PromptRecord]:
        records = [record for record in self._records if record.team_id == team_id]
        return records[:limit]

    async def get(self, prompt_id: str) -> PromptRecord | None:
        return next((r for r in self._records if r.prompt_id == prompt_id), None)

    async def get_for_team(
        self,
        prompt_id: str,
        team_id: TeamId,
    ) -> PromptRecord | None:
        return next(
            (
                r
                for r in self._records
                if r.prompt_id == prompt_id and r.team_id == team_id
            ),
            None,
        )

    async def update(
        self,
        prompt_id: str,
        team_id: TeamId,
        *,
        name: str,
        description: str | None,
        category: str | None = None,
        emoji: str | None = None,
        tags: list[str] | None = None,
        text: str,
    ) -> PromptRecord | None:
        record = await self.get_for_team(prompt_id, team_id)
        if record is None:
            return None
        if any(
            existing.prompt_id != prompt_id
            and existing.team_id == team_id
            and existing.name == name
            for existing in self._records
        ):
            from control_plane_backend.prompts.store import PromptAlreadyExistsError

            raise PromptAlreadyExistsError(name)
        record.name = name
        record.description = description
        record.text = text
        record.version += 1
        return record

    async def delete(self, prompt_id: str, team_id: TeamId) -> bool:
        before = len(self._records)
        self._records = [
            r
            for r in self._records
            if not (r.prompt_id == prompt_id and r.team_id == team_id)
        ]
        return len(self._records) < before

    async def increment_import_count(self, prompt_id: str, team_id: TeamId) -> None:
        for r in self._records:
            if r.prompt_id == prompt_id and r.team_id == team_id:
                r.import_count += 1

    async def increment_session_count(self, prompt_id: str, team_id: TeamId) -> None:
        for r in self._records:
            if r.prompt_id == prompt_id and r.team_id == team_id:
                r.session_count += 1

    async def increment_default_usage(self, category: str, team_id: TeamId) -> None:
        key = (str(team_id), category)
        self._default_usage[key] = self._default_usage.get(key, 0) + 1

    async def get_default_usage(
        self, team_id: TeamId, categories: list[str]
    ) -> dict[str, int]:
        return {
            cat: self._default_usage.get((str(team_id), cat), 0)
            for cat in categories
            if (str(team_id), cat) in self._default_usage
        }

    async def update_score(
        self, prompt_id: str, team_id: TeamId, score: float
    ) -> PromptRecord | None:
        record = await self.get_for_team(prompt_id, team_id)
        if record is None:
            return None
        record.score = score
        return record

    async def list_context_prompts(
        self,
        personal_team_id: TeamId,
        team_id: TeamId,
    ) -> list:
        from control_plane_backend.prompts.store import ContextPromptRecord

        seen_ids: set[str] = set()
        results = []
        for r in self._records:
            if r.team_id in (personal_team_id, team_id) and r.prompt_id not in seen_ids:
                seen_ids.add(r.prompt_id)
                scope = "personal" if r.team_id == personal_team_id else "team"
                results.append(
                    ContextPromptRecord(
                        prompt_id=r.prompt_id,
                        name=r.name,
                        description=r.description,
                        scope=scope,
                        category=r.category,
                        version=r.version,
                        session_count=r.session_count,
                        score=r.score,
                    )
                )
        results.sort(key=lambda r: (-r.session_count, r.name))
        return results


def _patch_prompt_store(
    monkeypatch: pytest.MonkeyPatch,
    store: _FakePromptStore,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_prompt_store",
        lambda _self: store,
    )


async def _fake_get_team_by_id(
    _user: Any,
    _team_id: Any,
    _deps: Any | None = None,
    required_permissions: Any = None,
    **_kwargs: Any,
) -> TeamWithPermissions:
    return TeamWithPermissions(
        id=TeamId(_team_id),
        name="Personal" if str(_team_id) == str(_PERSONAL_TEAM_ID) else str(_team_id),
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

        def get_kpi_writer(self):
            from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter

            return NoOpKPIWriter()

        def start_metrics_exporter(self) -> None:
            return None

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
            "id": _PERSONAL_TEAM_ID,
            "name": "Equipe personnelle",
            "member_count": 1,
            "owners": [],
            "is_member": False,
            "is_private": True,
            "max_resources_storage_size": 5368709120,
            "current_resources_storage_size": 0,
        }
    ]


@pytest.mark.asyncio
async def test_frontend_bootstrap_returns_typed_phase_3a_surface() -> None:
    app = create_app()
    container = get_application_container_from_app(app)
    container.configuration.app.gcu_version = "V1"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/frontend/bootstrap")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["current_user"]["id"] == "admin"
    assert payload["active_team"]["id"] == _PERSONAL_TEAM_ID
    assert payload["available_teams"][0]["id"] == _PERSONAL_TEAM_ID
    assert payload["gcu_version"] == "V1"
    assert payload["feature_flags"]["enableK8Features"] is False
    assert "ui_settings" not in payload
    assert "agents:read" in payload["permissions"]["items"]
    assert payload["permissions"]["can_manage_team_agents"] is True


@pytest.mark.asyncio
async def test_frontend_config_disabled_omits_oidc_client() -> None:
    """Public pre-auth config reports disabled user auth and hides OIDC client."""
    app = create_app()
    container = get_application_container_from_app(app)
    container.configuration.security.user.enabled = False
    # Even with a configured version, gating is effectively off when user auth is
    # disabled — the public surface must report `None` so the frontend never
    # routes a standalone/dev deployment to the acceptance screen.
    container.configuration.app.gcu_version = "V1"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/frontend/config")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["user_auth"]["enabled"] is False
    assert "realm_url" not in payload["user_auth"]
    assert "client_id" not in payload["user_auth"]
    # `response_model_exclude_none=True` omits the key entirely when gating is off.
    assert payload.get("gcu_version") is None


@pytest.mark.asyncio
async def test_frontend_config_enabled_returns_oidc_client() -> None:
    """When user auth is enabled, the public config exposes realm and client id."""
    app = create_app()
    container = get_application_container_from_app(app)
    container.configuration.security.user.enabled = True

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/frontend/config")

    assert resp.status_code == 200
    user_auth = resp.json()["user_auth"]
    assert user_auth["enabled"] is True
    assert user_auth["realm_url"] == str(
        container.configuration.security.user.realm_url
    )
    assert user_auth["client_id"] == container.configuration.security.user.client_id


@pytest.mark.asyncio
async def test_frontend_config_exposes_gcu_version_when_gating_enabled() -> None:
    """The public pre-auth config carries the active CGU version so the frontend
    guard can render the acceptance page without first calling the GCU-gated
    authenticated bootstrap (chicken-and-egg fix, FRONT-10)."""
    app = create_app()
    container = get_application_container_from_app(app)
    container.configuration.security.user.enabled = True
    container.configuration.app.gcu_version = "V1"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/frontend/config")

    assert resp.status_code == 200
    assert resp.json()["gcu_version"] == "V1"


@pytest.mark.asyncio
async def test_get_personal_team_returns_shared_system_team_contract() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(f"/control-plane/v1/teams/{_PERSONAL_TEAM_ID}")

    assert resp.status_code == 200
    assert resp.json() == {
        "id": _PERSONAL_TEAM_ID,
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
        "max_resources_storage_size": 5368709120,
        "current_resources_storage_size": 0,
    }


@pytest.mark.asyncio
async def test_user_details_reuses_shared_personal_team_contract() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/user")

    assert resp.status_code == 200
    assert resp.json()["personalTeam"]["id"] == _PERSONAL_TEAM_ID
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
        resp = await client.get(
            f"/control-plane/v1/teams/{_PERSONAL_TEAM_ID}/agent-templates"
        )

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_team_agent_templates_aggregates_runtime_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
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
        resp = await client.get(
            f"/control-plane/v1/teams/{_PERSONAL_TEAM_ID}/agent-templates"
        )

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
            "mcp_servers": [],
        }
    ]


@pytest.mark.asyncio
async def test_team_agent_instances_returns_managed_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _FakeAgentInstanceStore([_make_record(team_id=_PERSONAL_TEAM_ID)])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        list_resp = await client.get(
            f"/control-plane/v1/teams/{_PERSONAL_TEAM_ID}/agent-instances"
        )

    assert list_resp.status_code == 200
    assert list_resp.json() == [
        {
            "agent_instance_id": "instance-1",
            "team_id": _PERSONAL_TEAM_ID,
            "template_id": "runtime-a:rags.sample.echo",
            "display_name": "Echo Team Agent",
            "description": "Managed echo agent",
            "status": "enabled",
            "created_by": "internal-admin",
            "tuning_field_values": {},
            "mcp_config_values": {},
            "runtime_status": "unavailable",
            "catalog_warnings": [],
            "effective_chat_options": {
                "attach_files": False,
                "libraries_selection": False,
                "documents_selection": False,
                "search_policy_selection": False,
                "default_search_policy": "hybrid",
                "rag_scope_selection": False,
                "default_search_rag_scope": "hybrid",
            },
        }
    ]


@pytest.mark.asyncio
async def test_team_runtime_binding_endpoint_resolves_for_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RUNTIME-07 rev. 2: the team-scoped resolution endpoint returns the runtime
    binding for a team member (ReBAC CAN_READ), replacing the admin-only path (F2)."""
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
        runtime_resp = await client.get(
            "/control-plane/v1/teams/personal/agent-instances/instance-1/runtime"
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
    assert payload["effective_chat_options"] == {
        "attach_files": False,
        "libraries_selection": False,
        "documents_selection": False,
        "search_policy_selection": False,
        "default_search_policy": "hybrid",
        "rag_scope_selection": False,
        "default_search_rag_scope": "hybrid",
    }
    # RUNTIME-07 rev. 2: no signed grant in the response — the control-plane issues
    # no capability; the pod authenticates via Keycloak and authorizes via OpenFGA.
    assert "execution_grant" not in payload
    for url_field in ("execute_url", "execute_stream_url", "messages_url_template"):
        assert "svc.cluster.local" not in payload[url_field]
        assert payload[url_field].startswith("/")


@pytest.mark.asyncio
async def test_agent_instance_mutations_require_can_update_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RUNTIME-07 (bundled): enroll/patch/delete of agent instances must authorize
    on CAN_UPDATE_AGENTS (manager/owner), not CAN_READ — so a plain team member is
    refused in a collaborative team (REBAC.md). We assert each endpoint asks the
    team service for that exact permission."""
    from fred_core import TeamPermission

    from control_plane_backend.product.schemas import TeamWithPermissions

    captured: dict[str, object] = {}

    async def _spy(user, team_id, deps=None, required_permissions=None, **_kw):
        captured["perms"] = required_permissions
        return TeamWithPermissions(
            id=TeamId(str(team_id)),
            name=str(team_id),
            member_count=1,
            is_private=False,
            owners=[],
            permissions=[],
        )

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service", _spy
    )
    app = create_app()
    _patch_store(monkeypatch, _FakeAgentInstanceStore([]))

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # enroll
        await client.post(
            "/control-plane/v1/teams/fredlab/agent-instances",
            json={"template_id": "runtime-a:foo", "display_name": "x"},
        )
        assert captured["perms"] == [TeamPermission.CAN_UPDATE_AGENTS]
        # delete
        captured.clear()
        await client.delete("/control-plane/v1/teams/fredlab/agent-instances/inst-1")
        assert captured["perms"] == [TeamPermission.CAN_UPDATE_AGENTS]


@pytest.mark.asyncio
async def test_prepare_execution_concatenates_attached_context_prompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attached prompts resolve in position order and concatenate with '\\n\\n'."""

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
    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="sess-1",
                team_id=TeamId("personal"),
                agent_instance_id="inst-42",
                user_id="admin",
                title=None,
                context_prompt_ids=["p1", "p2"],
            )
        ]
    )
    prompt_store = _FakePromptStore(
        [
            _make_prompt_record(prompt_id="p1", team_id="personal", text="First."),
            _make_prompt_record(prompt_id="p2", team_id="personal", text="Second."),
        ]
    )
    app = create_app()
    _patch_store(monkeypatch, store)
    _patch_session_store(monkeypatch, session_store)
    _patch_prompt_store(monkeypatch, prompt_store)
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
            "/control-plane/v1/teams/personal/agent-instances/inst-42/prepare-execution",
            params={"session_id": "sess-1"},
        )

    assert resp.status_code == 200
    assert resp.json()["context_prompt_text"] == "First.\n\nSecond."


@pytest.mark.asyncio
async def test_prepare_execution_resolves_default_prompt_in_request_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `default:` prompt resolves in the `lang` threaded from the request, so a
    French user gets the French default text (matching the localized picker), and
    omitting `lang` falls back to English (back-compatible)."""

    spec = next(s for s in DEFAULT_PROMPTS if s.category == "conversational")
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
    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="sess-1",
                team_id=TeamId("personal"),
                agent_instance_id="inst-42",
                user_id="admin",
                title=None,
                context_prompt_ids=["default:conversational"],
            )
        ]
    )
    app = create_app()
    _patch_store(monkeypatch, store)
    _patch_session_store(monkeypatch, session_store)
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
        fr_resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/inst-42/prepare-execution",
            params={"session_id": "sess-1", "lang": "fr"},
        )
        default_resp = await client.post(
            "/control-plane/v1/teams/personal/agent-instances/inst-42/prepare-execution",
            params={"session_id": "sess-1"},
        )

    assert fr_resp.status_code == 200
    assert fr_resp.json()["context_prompt_text"] == spec.text("fr")
    # No lang param → English (back-compatible default).
    assert default_resp.status_code == 200
    assert default_resp.json()["context_prompt_text"] == spec.text("en")


@pytest.mark.asyncio
async def test_prepare_execution_skips_stale_context_prompt_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deleted/unknown attached id is skipped, not surfaced as an error."""

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
    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="sess-1",
                team_id=TeamId("personal"),
                agent_instance_id="inst-42",
                user_id="admin",
                title=None,
                context_prompt_ids=["gone", "p2"],
            )
        ]
    )
    prompt_store = _FakePromptStore(
        [_make_prompt_record(prompt_id="p2", team_id="personal", text="Second.")]
    )
    app = create_app()
    _patch_store(monkeypatch, store)
    _patch_session_store(monkeypatch, session_store)
    _patch_prompt_store(monkeypatch, prompt_store)
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
            "/control-plane/v1/teams/personal/agent-instances/inst-42/prepare-execution",
            params={"session_id": "sess-1"},
        )

    assert resp.status_code == 200
    assert resp.json()["context_prompt_text"] == "Second."


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

    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
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
async def test_enroll_agent_instance_unreachable_runtime_returns_503(
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

    async def _raise_connect_error(self, url, params=None):  # noqa: ANN001
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(httpx.AsyncClient, "get", _raise_connect_error)

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

    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "runtime-a" in detail
    assert "not reachable" in detail
    assert len(store._records) == 0


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
                    prompt_refs_json TEXT,
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
async def test_patch_team_session_returns_404_for_other_user_session(
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
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="alice",
                title="Owned by Alice",
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
            json={"title": "Should fail"},
        )

    assert resp.status_code == 404
    assert store._records[0].title == "Owned by Alice"


@pytest.mark.asyncio
async def test_patch_team_session_updates_title(
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
                team_id=TeamId("personal"),
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
            json={"title": "Analysis of Q1 report"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["title"] == "Analysis of Q1 report"
    assert store._records[0].title == "Analysis of Q1 report"


@pytest.mark.asyncio
async def test_patch_team_session_updates_title_and_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    initial = datetime.fromisoformat("2026-04-23T08:00:00+00:00")
    refreshed = datetime.fromisoformat("2026-04-23T08:10:00+00:00")
    store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title=None,
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
            json={"title": "My analysis", "updated_at": refreshed.isoformat()},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["title"] == "My analysis"
    assert payload["updated_at"] == "2026-04-23T08:10:00Z"
    assert store._records[0].title == "My analysis"
    assert store._records[0].updated_at == refreshed


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
async def test_delete_team_session_returns_404_for_other_user_session(
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
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="alice",
                title="Owned by Alice",
            )
        ]
    )
    _patch_session_store(monkeypatch, store)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/personal/sessions/session-1"
        )

    assert resp.status_code == 404
    assert len(store._records) == 1
    assert store._records[0].session_id == "session-1"
    assert store._records[0].user_id == "alice"
    assert store._records[0].title == "Owned by Alice"


def _patch_runtime_erase_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make erase_session's runtime step succeed for HTTP delete tests.

    These tests build the app from the test config, which declares no runtime
    catalog sources — so the runtime erase can't resolve, and under the retry-safe
    ordering (RFC §2.1) the metadata row is correctly RETAINED on a partial
    failure. To exercise the intended *happy path* (delete fully erases and
    removes the session), stub the runtime resolution + calls to succeed.
    """

    async def _resolve(
        self: Any, *, team_id: Any, agent_instance_id: Any
    ) -> tuple[str, None]:
        return "http://runtime-a.internal", None

    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service."
        "ConversationErasureService._resolve_runtime_base_url",
        _resolve,
    )
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client([]),
    )


@pytest.mark.asyncio
async def test_delete_team_session_deletes_owned_session(
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
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )
    _patch_session_store(monkeypatch, store)
    _patch_runtime_erase_ok(monkeypatch)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/personal/sessions/session-1"
        )

    assert resp.status_code == 204
    assert store._records == []


@pytest.mark.asyncio
async def test_delete_team_session_cleans_up_all_session_attachments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )
    attachment_store = _FakeSessionAttachmentStore(
        [
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-1",
                name="notes.md",
                summary_md="# Notes",
                document_uid="doc-1",
                storage_key="uploads/notes.md",
            ),
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-2",
                name="diagram.png",
                summary_md="![diagram](diagram.png)",
                document_uid="doc-2",
                storage_key="uploads/diagram.png",
            ),
        ]
    )
    cleanup_calls: list[dict[str, str | None]] = []

    async def _fake_cleanup(**kwargs: Any) -> None:
        cleanup_calls.append(
            {
                "document_uid": kwargs["document_uid"],
                "storage_key": kwargs["storage_key"],
                "session_id": kwargs["session_id"],
            }
        )

    monkeypatch.setattr(
        "control_plane_backend.product.service._delete_knowledge_flow_attachment",
        _fake_cleanup,
    )
    _patch_session_store(monkeypatch, session_store)
    _patch_session_attachment_store(monkeypatch, attachment_store)
    _patch_runtime_erase_ok(monkeypatch)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/personal/sessions/session-1",
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 204
    assert session_store._records == []
    assert attachment_store._records == []
    assert cleanup_calls == [
        {
            "document_uid": "doc-1",
            "storage_key": "uploads/notes.md",
            "session_id": "session-1",
        },
        {
            "document_uid": "doc-2",
            "storage_key": "uploads/diagram.png",
            "session_id": "session-1",
        },
    ]


class _FakeKPIStore:
    """In-memory stand-in for the OpenSearch KPI store (A3).

    `anonymise_for_session` records the calls and returns a fixed count, or
    raises when `fail` is set (to exercise per-store isolation).
    """

    def __init__(self, *, updated: int = 4, fail: bool = False) -> None:
        self.updated = updated
        self.fail = fail
        self.calls: list[str] = []

    def anonymise_for_session(self, session_id: str) -> int:
        self.calls.append(session_id)
        if self.fail:
            raise RuntimeError("opensearch down")
        return self.updated


def _build_erasure_deps(
    session_store: _FakeSessionMetadataStore,
    attachment_store: _FakeSessionAttachmentStore,
    *,
    agent_instance_store: _FakeAgentInstanceStore | None = None,
    configuration: Any = None,
    kpi_store: _FakeKPIStore | None = None,
    policy_catalog: Any = None,
    team_metadata_store: Any = None,
    purge_queue_store: Any = None,
) -> ProductServiceDependencies:
    """Minimal deps bundle wiring only the collaborators erase_session uses.

    `agent_instance_store` + `configuration` are the A2 additions used to
    resolve a session's runtime; A1 callers omit them (runtime stays
    unresolved, recorded ok=false). `kpi_store` is the A3 addition; when omitted
    the KPI store is absent (a no-op ok entry, nothing to anonymise).
    """
    return ProductServiceDependencies(
        configuration=configuration,  # type: ignore[arg-type]
        team_dependencies=None,  # type: ignore[arg-type]
        get_agent_instance_store=lambda: agent_instance_store,  # type: ignore[arg-type,return-value]
        get_session_metadata_store=lambda: session_store,  # type: ignore[arg-type,return-value]
        get_team_metadata_store=lambda: team_metadata_store,  # type: ignore[arg-type,return-value]
        get_session_attachment_store=lambda: attachment_store,  # type: ignore[arg-type,return-value]
        get_prompt_store=lambda: None,  # type: ignore[arg-type,return-value]
        get_kpi_writer=lambda: None,  # type: ignore[arg-type,return-value]
        get_kpi_store=lambda: kpi_store,  # type: ignore[arg-type,return-value]
        get_policy_catalog=lambda: policy_catalog,  # type: ignore[arg-type,return-value]
        get_purge_queue_store=lambda: purge_queue_store,  # type: ignore[arg-type,return-value]
    )


def _runtime_config(
    *, runtime_id: str = "runtime-a", base_url: str = "http://runtime-a.internal"
) -> Any:
    """A stub configuration exposing one enabled runtime catalog source."""
    from control_plane_backend.config.models import RuntimeCatalogSourceConfig

    return SimpleNamespace(
        platform=SimpleNamespace(
            runtime_catalog_sources=[
                RuntimeCatalogSourceConfig(
                    runtime_id=runtime_id, base_url=base_url, enabled=True
                )
            ]
        )
    )


def _make_runtime_client(
    calls: list[tuple[str, dict[str, str]]],
    *,
    history_deleted: int = 3,
    history_error: bool = False,
    checkpoint_error: bool = False,
) -> type:
    """Build a fake httpx.AsyncClient recording runtime DELETEs into `calls`.

    Checkpoint DELETE → 204 (or 502 when `checkpoint_error` is set, to exercise
    the orphan fix); transcript DELETE → 200 `{"deleted": history_deleted}`, or a
    502 failure when `history_error` is set (to exercise per-store isolation).
    """

    class _RuntimeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self) -> "_RuntimeClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def delete(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
            calls.append((url, headers))
            request = httpx.Request("DELETE", url, headers=headers)
            if "/agents/checkpoints/" in url:
                if checkpoint_error:
                    return httpx.Response(502, text="boom", request=request)
                return httpx.Response(204, request=request)
            if history_error:
                return httpx.Response(502, text="boom", request=request)
            return httpx.Response(
                200, json={"deleted": history_deleted}, request=request
            )

    return _RuntimeClient


@pytest.mark.asyncio
async def test_erase_session_receipt_lists_attachment_and_metadata_stores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """erase_session returns a per-store receipt for the stores it erases (A1)."""
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )
    attachment_store = _FakeSessionAttachmentStore(
        [
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-1",
                name="notes.md",
                summary_md="# Notes",
                document_uid="doc-1",
                storage_key="uploads/notes.md",
            ),
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-2",
                name="diagram.png",
                summary_md="![diagram](diagram.png)",
                document_uid="doc-2",
                storage_key="uploads/diagram.png",
            ),
        ]
    )

    cleanup_calls: list[str | None] = []

    async def _fake_cleanup(**kwargs: Any) -> None:
        cleanup_calls.append(kwargs["document_uid"])

    monkeypatch.setattr(
        "control_plane_backend.product.service._delete_knowledge_flow_attachment",
        _fake_cleanup,
    )

    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls),
    )
    deps = _build_erasure_deps(
        session_store,
        attachment_store,
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(
            runtime_id="runtime-a", base_url="http://runtime-a.internal"
        ),
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    assert receipt.ok is True
    by_store = {r.store: r for r in receipt.stores}
    assert by_store["attachments"].deleted_count == 2
    assert by_store["attachments"].ok is True
    assert by_store["session_metadata"].deleted_count == 1
    assert by_store["session_metadata"].ok is True
    # Same deletes as the former delete_session — no more, no fewer, in order.
    assert cleanup_calls == ["doc-1", "doc-2"]
    assert attachment_store._records == []
    assert session_store._records == []


@pytest.mark.asyncio
async def test_erase_session_noop_session_yields_all_zero_ok_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session with nothing to erase yields an all-zero, still-ok receipt (A1).

    Under A2 the runtime is still reached — it returns `{"deleted": 0}` for an
    already-gone/non-owned session, so idempotent re-erase stays ok=True.
    """
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    # Legacy/unowned session (user_id=None): the ownership check passes but the
    # owner-scoped metadata delete matches no row, and there are no attachments,
    # so every store erases zero — erase of nothing still succeeds (ok=True).
    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id=None,
                title="Legacy session",
            )
        ]
    )
    attachment_store = _FakeSessionAttachmentStore([])

    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls, history_deleted=0),
    )
    deps = _build_erasure_deps(
        session_store,
        attachment_store,
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    assert receipt.ok is True
    by_store = {r.store: r for r in receipt.stores}
    assert by_store["attachments"].deleted_count == 0
    assert by_store["session_metadata"].deleted_count == 0
    assert by_store["runtime_history"].deleted_count == 0
    assert by_store["runtime_checkpoint"].ok is True


@pytest.mark.asyncio
async def test_erase_session_deletes_checkpoint_before_history_on_resolved_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A2: runtime erasure hits checkpoint BEFORE history, on the resolved
    base_url, with the caller's Authorization; the receipt gains both entries."""
    from control_plane_backend.config.models import RuntimeCatalogSourceConfig
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )
    attachment_store = _FakeSessionAttachmentStore([])

    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls, history_deleted=7),
    )
    # instance-1 lives on runtime-a; a decoy source proves per-session
    # resolution picks the right base_url rather than the first/only one.
    deps = _build_erasure_deps(
        session_store,
        attachment_store,
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    RuntimeCatalogSourceConfig(
                        runtime_id="runtime-z",
                        base_url="http://decoy.internal",
                        enabled=True,
                    ),
                    RuntimeCatalogSourceConfig(
                        runtime_id="runtime-a",
                        base_url="http://runtime-a.internal",
                        enabled=True,
                    ),
                ]
            )
        ),
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    # Ordering: checkpoint DELETE strictly precedes history DELETE.
    assert [url for url, _ in runtime_calls] == [
        "http://runtime-a.internal/agents/checkpoints/session-1",
        "http://runtime-a.internal/agents/sessions/session-1",
    ]
    # base_url resolved from agent_instance_id (runtime-a, not the decoy) and
    # the caller Authorization threaded through on every call.
    assert all(
        headers == {"Authorization": "Bearer test-token"}
        for _, headers in runtime_calls
    )

    by_store = {r.store: r for r in receipt.stores}
    assert by_store["runtime_checkpoint"].ok is True
    assert by_store["runtime_history"].ok is True
    assert by_store["runtime_history"].deleted_count == 7
    assert receipt.ok is True


@pytest.mark.asyncio
async def test_erase_session_history_failure_isolated_others_still_erased(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A2 + retry-safety (RFC §2.1): a failing history DELETE records ok=false for
    that store only; attachments and checkpoint still erase, but the session
    metadata row is RETAINED (not deleted) so a retry can re-resolve and converge.
    receipt.ok is False."""
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )
    attachment_store = _FakeSessionAttachmentStore(
        [
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-1",
                name="notes.md",
                summary_md="# Notes",
                document_uid="doc-1",
                storage_key="uploads/notes.md",
            )
        ]
    )
    cleanup_calls: list[str | None] = []

    async def _fake_cleanup(**kwargs: Any) -> None:
        cleanup_calls.append(kwargs["document_uid"])

    monkeypatch.setattr(
        "control_plane_backend.product.service._delete_knowledge_flow_attachment",
        _fake_cleanup,
    )
    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls, history_error=True),
    )
    deps = _build_erasure_deps(
        session_store,
        attachment_store,
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    by_store = {r.store: r for r in receipt.stores}
    # The failing store is isolated…
    assert by_store["runtime_history"].ok is False
    assert by_store["runtime_history"].error is not None
    # …the others still completed.
    assert cleanup_calls == ["doc-1"]
    assert attachment_store._records == []
    assert by_store["attachments"].ok is True
    assert by_store["runtime_checkpoint"].ok is True
    # Retry-safety: metadata is retained (deleted last, only on full success), so
    # the row survives and a re-run can re-resolve the runtime and finish.
    assert by_store["session_metadata"].ok is False
    assert session_store._records != []
    # Checkpoint was still attempted before the failing history call.
    assert [url for url, _ in runtime_calls] == [
        "http://runtime-a.internal/agents/checkpoints/session-1",
        "http://runtime-a.internal/agents/sessions/session-1",
    ]
    assert receipt.ok is False


@pytest.mark.asyncio
async def test_erase_session_partial_failure_converges_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RFC §2.1 (the retry-safety guarantee): a partial failure leaves the session
    metadata row intact; a re-run against a healthy runtime re-resolves, converges
    to a fully-ok receipt, and finally deletes the row. No orphaned store, no stuck
    queue entry — the defect C-1 fixes."""
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )

    async def _fake_cleanup(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "control_plane_backend.product.service._delete_knowledge_flow_attachment",
        _fake_cleanup,
    )
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
    )
    service = ConversationErasureService(deps)

    # Attempt 1 — the runtime's history DELETE is down → partial receipt. The
    # metadata row that anchors ownership + runtime resolution MUST survive.
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client([], history_error=True),
    )
    first = await service.erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )
    assert first.ok is False
    assert session_store._records != []  # retained for retry — not orphaned

    # Attempt 2 — the runtime is healthy again. Because the row survived, the
    # retry re-resolves the runtime, every store converges, and metadata is
    # finally deleted.
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client([]),
    )
    second = await service.erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )
    assert second.ok is True
    assert session_store._records == []  # converged — fully erased


@pytest.mark.asyncio
async def test_erase_session_unresolved_runtime_records_ok_false_no_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A2 edge case: a session with no agent_instance_id cannot resolve a
    runtime — checkpoint+history are recorded ok=false and NO HTTP is made."""
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id=None,
                user_id="admin",
                title="Orphan session",
            )
        ]
    )
    attachment_store = _FakeSessionAttachmentStore([])

    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls),
    )
    deps = _build_erasure_deps(
        session_store,
        attachment_store,
        agent_instance_store=_FakeAgentInstanceStore([]),
        configuration=_runtime_config(runtime_id="runtime-a"),
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    # No runtime to guess → no HTTP call at all.
    assert runtime_calls == []
    by_store = {r.store: r for r in receipt.stores}
    assert by_store["runtime_checkpoint"].ok is False
    assert "unresolved" in (by_store["runtime_checkpoint"].error or "")
    assert by_store["runtime_history"].ok is False
    assert "unresolved" in (by_store["runtime_history"].error or "")
    # Retry-safety: with the runtime unreachable, metadata is retained (deleted
    # last, only on full success) so a later retry can re-resolve and converge.
    assert by_store["session_metadata"].ok is False
    assert receipt.ok is False


@pytest.mark.asyncio
async def test_erase_session_runtime_instance_not_found_records_ok_false_no_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_runtime_base_url: the session names an agent instance, but it is
    not found for the team -> checkpoint+history recorded ok=false, no HTTP."""
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Session",
            )
        ]
    )
    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls),
    )
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        # Instance store is empty → get_for_team returns None for "instance-1".
        agent_instance_store=_FakeAgentInstanceStore([]),
        configuration=_runtime_config(runtime_id="runtime-a"),
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    assert runtime_calls == []
    by_store = {r.store: r for r in receipt.stores}
    assert by_store["runtime_checkpoint"].ok is False
    assert "not found for team" in (by_store["runtime_checkpoint"].error or "")
    assert by_store["runtime_history"].ok is False
    # Retry-safety: metadata retained (deleted last, only on full success).
    assert by_store["session_metadata"].ok is False
    assert receipt.ok is False


@pytest.mark.asyncio
async def test_erase_session_runtime_source_disabled_records_ok_false_no_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_runtime_base_url: the instance resolves but its runtime source is
    disabled/missing -> checkpoint+history recorded ok=false, no HTTP."""
    from control_plane_backend.config.models import RuntimeCatalogSourceConfig
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Session",
            )
        ]
    )
    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls),
    )
    # The instance points at runtime-a, but that catalog source is DISABLED.
    disabled_config = SimpleNamespace(
        platform=SimpleNamespace(
            runtime_catalog_sources=[
                RuntimeCatalogSourceConfig(
                    runtime_id="runtime-a",
                    base_url="http://runtime-a.internal",
                    enabled=False,
                )
            ]
        )
    )
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=disabled_config,
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    assert runtime_calls == []
    by_store = {r.store: r for r in receipt.stores}
    assert by_store["runtime_checkpoint"].ok is False
    assert "disabled or missing" in (by_store["runtime_checkpoint"].error or "")
    assert by_store["runtime_history"].ok is False
    # Retry-safety: metadata retained (deleted last, only on full success).
    assert by_store["session_metadata"].ok is False
    assert receipt.ok is False


def _kpi_session() -> "_FakeSessionMetadataStore":
    """A single owned session on a resolvable runtime, for the KPI tests."""
    return _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )


@pytest.mark.asyncio
async def test_erase_session_anonymises_kpi_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A3: erase_session anonymises the session's KPI rows and records a
    STORE_KPI receipt entry with the row count (anonymised, not deleted)."""
    from control_plane_backend.sessions.erasure_service import (
        STORE_KPI,
        ConversationErasureService,
    )

    kpi_store = _FakeKPIStore(updated=5)
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client([]),
    )
    deps = _build_erasure_deps(
        _kpi_session(),
        _FakeSessionAttachmentStore([]),
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
        kpi_store=kpi_store,
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    # The KPI store was asked to anonymise exactly this session…
    assert kpi_store.calls == ["session-1"]
    by_store = {r.store: r for r in receipt.stores}
    # …and the receipt records the anonymised (not deleted) row count.
    assert by_store[STORE_KPI].ok is True
    assert by_store[STORE_KPI].deleted_count == 5
    assert receipt.ok is True


@pytest.mark.asyncio
async def test_erase_session_absent_kpi_store_is_noop_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A3: a deployment without an OpenSearch KPI store yields a no-op ok KPI
    entry (nothing to anonymise), not an error."""
    from control_plane_backend.sessions.erasure_service import (
        STORE_KPI,
        ConversationErasureService,
    )

    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client([]),
    )
    deps = _build_erasure_deps(
        _kpi_session(),
        _FakeSessionAttachmentStore([]),
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
        kpi_store=None,  # no OpenSearch KPI store in this deployment
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    by_store = {r.store: r for r in receipt.stores}
    assert by_store[STORE_KPI].ok is True
    assert by_store[STORE_KPI].deleted_count == 0
    assert receipt.ok is True


@pytest.mark.asyncio
async def test_erase_session_kpi_failure_isolated_others_still_erased(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A3: a failing KPI anonymise records ok=false for that store only; the
    other stores are still erased, and receipt.ok is False."""
    from control_plane_backend.sessions.erasure_service import (
        STORE_KPI,
        ConversationErasureService,
    )

    kpi_store = _FakeKPIStore(fail=True)
    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls),
    )
    session_store = _kpi_session()
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
        kpi_store=kpi_store,
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    by_store = {r.store: r for r in receipt.stores}
    # The failing store is isolated…
    assert by_store[STORE_KPI].ok is False
    assert by_store[STORE_KPI].error is not None
    # …the others still completed, but metadata is retained (deleted last, only
    # on full success) so the erase stays retryable.
    assert by_store["session_metadata"].ok is False
    assert by_store["runtime_checkpoint"].ok is True
    assert by_store["runtime_history"].ok is True
    assert receipt.ok is False


@pytest.mark.asyncio
async def test_erase_session_attachment_failure_isolated_others_still_erased(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CTRLP-12: a failing Knowledge Flow attachment cleanup records ok=false for
    the attachments store only; session_metadata, KPI and the runtime
    checkpoint/history are still attempted and receipted (the fan-out is NOT
    aborted), and receipt.ok is False."""
    from control_plane_backend.sessions.erasure_service import (
        STORE_KPI,
        ConversationErasureService,
    )

    attachment_store = _FakeSessionAttachmentStore(
        [
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-1",
                name="notes.md",
                summary_md="# Notes",
                document_uid="doc-1",
                storage_key="uploads/notes.md",
            )
        ]
    )

    async def _failing_cleanup(**kwargs: Any) -> None:
        raise RuntimeError("knowledge flow down")

    monkeypatch.setattr(
        "control_plane_backend.product.service._delete_knowledge_flow_attachment",
        _failing_cleanup,
    )
    kpi_store = _FakeKPIStore(updated=5)
    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls),
    )
    session_store = _kpi_session()
    deps = _build_erasure_deps(
        session_store,
        attachment_store,
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
        kpi_store=kpi_store,
    )
    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    by_store = {r.store: r for r in receipt.stores}
    # The failing store is isolated…
    assert by_store["attachments"].ok is False
    assert by_store["attachments"].error is not None
    # …the fan-out was NOT aborted: every downstream store was still attempted,
    # but metadata is retained (deleted last, only on full success) for retry.
    assert by_store["session_metadata"].ok is False
    assert session_store._records != []
    assert kpi_store.calls == ["session-1"]
    assert by_store[STORE_KPI].ok is True
    assert by_store["runtime_checkpoint"].ok is True
    assert by_store["runtime_history"].ok is True
    # The runtime checkpoint+history DELETEs were still issued.
    assert [url for url, _ in runtime_calls] == [
        "http://runtime-a.internal/agents/checkpoints/session-1",
        "http://runtime-a.internal/agents/sessions/session-1",
    ]
    assert receipt.ok is False


# --- CTRLP-12 A5: delete = deferred erase (team + personal windows) -----------


def _delete_window_catalog(
    *,
    personal_delete_grace: str | None = None,
    team_delete_grace: str | None = None,
) -> Any:
    """Policy catalog exposing the two A5 delete windows (both platform-level)."""
    from control_plane_backend.scheduler.policies.policy_models import (
        ConversationPolicyCatalog,
    )

    purge: dict[str, Any] = {}
    if personal_delete_grace is not None:
        purge["personal_delete_grace"] = personal_delete_grace
    if team_delete_grace is not None:
        purge["default"] = {"team_delete_grace": team_delete_grace}
    return ConversationPolicyCatalog.model_validate(
        {"conversation_policies": {"purge": purge}}
    )


class _FakePurgeQueueStore:
    """In-memory stand-in recording deferred USER_DELETED enqueues (A5)."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def enqueue(
        self, *, session_id: str, team_id: str, user_id: str, due_at: datetime
    ) -> None:
        self.entries.append(
            {
                "session_id": session_id,
                "team_id": team_id,
                "user_id": user_id,
                "due_at": due_at,
            }
        )


class _FakeTeamMetadataStore:
    """In-memory stand-in exposing get_by_team_id for retention resolution.

    CTRLP-12 rev. 2 / Phase R: per-team retention lives on team_metadata now, so
    the delete-window resolver reads its `team_delete_grace`/`max_idle` off this
    record instead of a separate override store.
    """

    def __init__(self, record: Any) -> None:
        self.record = record

    async def get_by_team_id(self, *_args: Any, **_kwargs: Any) -> Any:
        return self.record


class _RaisingTeamMetadataStore:
    """Metadata store that fails if consulted — proves the personal delete path
    never reads a team retention value to size its window (A5)."""

    async def get_by_team_id(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(
            "personal delete must not consult the team metadata retention fields"
        )


@pytest.mark.asyncio
async def test_team_delete_defers_erase_and_enqueues_user_deleted() -> None:
    """Team that OPTED IN to retention: delete → hidden (`deleted_at`), history
    retained, USER_DELETED queue entry due at `now + team_delete_grace` (CTRLP-12
    D1: deferral applies only when the team has set its own value)."""
    from control_plane_backend.product.service import delete_or_defer_session
    from control_plane_backend.scheduler.policies.policy_models import (
        parse_iso8601_duration,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("northbridge"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Team chat",
            )
        ]
    )
    queue = _FakePurgeQueueStore()
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        policy_catalog=_delete_window_catalog(team_delete_grace="P30D"),
        # The team explicitly set a retention window (≤ the platform cap).
        team_metadata_store=_FakeTeamMetadataStore(
            TeamMetadata(id=TeamId("northbridge"), team_delete_grace="P30D")
        ),
        purge_queue_store=queue,
    )

    before = datetime.now(timezone.utc)
    await delete_or_defer_session(
        team_id=TeamId("northbridge"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
        deps=deps,
    )
    after = datetime.now(timezone.utc)

    # Hidden, not erased: the row survives (history stays readable for the window).
    assert len(session_store._records) == 1
    record = session_store._records[0]
    assert record.deleted_at is not None  # type: ignore[attr-defined]

    # Exactly one USER_DELETED queue entry due at now + team_delete_grace (P30D).
    assert len(queue.entries) == 1
    entry = queue.entries[0]
    assert entry["session_id"] == "session-1"
    assert entry["user_id"] == "admin"
    window = parse_iso8601_duration("P30D")
    assert before + window <= entry["due_at"] <= after + window


@pytest.mark.asyncio
async def test_personal_delete_defers_by_platform_window_not_overridable() -> None:
    """Personal delete → hidden + USER_DELETED entry due at
    `now + personal_delete_grace` (NOT immediate); the window is read straight
    off the platform catalog and never from a team/user override."""
    from control_plane_backend.product.service import delete_or_defer_session
    from control_plane_backend.scheduler.policies.policy_models import (
        parse_iso8601_duration,
    )

    personal_team = personal_team_id("alice")
    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=personal_team,
                agent_instance_id="instance-1",
                user_id="alice",
                title="Personal chat",
            )
        ]
    )
    queue = _FakePurgeQueueStore()
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        policy_catalog=_delete_window_catalog(personal_delete_grace="P3D"),
        # If the personal path ever read team retention, this store would raise.
        team_metadata_store=_RaisingTeamMetadataStore(),
        purge_queue_store=queue,
    )

    before = datetime.now(timezone.utc)
    await delete_or_defer_session(
        team_id=personal_team,
        session_id="session-1",
        user_id="alice",
        authorization="Bearer test-token",
        deps=deps,
    )
    after = datetime.now(timezone.utc)

    # Deferred, NOT immediate: row hidden and survives, queue entry due at +P3D.
    assert len(session_store._records) == 1
    assert session_store._records[0].deleted_at is not None  # type: ignore[attr-defined]
    assert len(queue.entries) == 1
    window = parse_iso8601_duration("P3D")
    assert before + window <= queue.entries[0]["due_at"] <= after + window

    # Structural guarantee: team_metadata retention cannot even express a
    # personal window — there is no field for a user/team to shorten it.
    assert "personal_delete_grace" not in TeamMetadata.model_fields


@pytest.mark.asyncio
async def test_delete_with_no_window_erases_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both windows unset → immediate `erase_session` (back-compat): the metadata
    row is deleted now and nothing is deferred onto the purge queue."""
    from control_plane_backend.product.service import delete_or_defer_session

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Team chat",
            )
        ]
    )
    queue = _FakePurgeQueueStore()
    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls),
    )

    async def _fake_cleanup(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "control_plane_backend.product.service._delete_knowledge_flow_attachment",
        _fake_cleanup,
    )
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
        policy_catalog=_delete_window_catalog(),  # no windows configured
        team_metadata_store=_FakeTeamMetadataStore(None),
        purge_queue_store=queue,
    )

    await delete_or_defer_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
        deps=deps,
    )

    # Immediate erase ran: metadata row gone, nothing deferred.
    assert session_store._records == []
    assert queue.entries == []
    # The full fan-out reached the runtime (history erased, not retained).
    assert any("/agents/sessions/" in url for url, _ in runtime_calls)


@pytest.mark.asyncio
async def test_team_delete_with_cap_but_unset_value_erases_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CTRLP-12 D1: a platform cap is a CEILING, not a default window. A team that
    has NOT set its own `team_delete_grace` erases immediately even when a cap is
    configured — it does not inherit the cap as a deferral window."""
    from control_plane_backend.product.service import delete_or_defer_session

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("northbridge"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Team chat",
            )
        ]
    )
    queue = _FakePurgeQueueStore()
    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls),
    )

    async def _fake_cleanup(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "control_plane_backend.product.service._delete_knowledge_flow_attachment",
        _fake_cleanup,
    )
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1",
                    source_runtime_id="runtime-a",
                    team_id="northbridge",
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
        # A platform cap IS configured…
        policy_catalog=_delete_window_catalog(team_delete_grace="P30D"),
        # …but the team set nothing → immediate delete, not defer-for-the-cap.
        team_metadata_store=_FakeTeamMetadataStore(None),
        purge_queue_store=queue,
    )

    await delete_or_defer_session(
        team_id=TeamId("northbridge"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
        deps=deps,
    )

    # Immediate erase ran despite the configured cap: nothing deferred.
    assert session_store._records == []
    assert queue.entries == []
    assert any("/agents/sessions/" in url for url, _ in runtime_calls)


@pytest.mark.asyncio
async def test_erase_session_skips_history_when_checkpoint_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orphan fix (A2/A5): a failed checkpoint erase SKIPS the history erase so
    the still-present checkpoint stays retryable (history is its ownership proof)."""
    from control_plane_backend.sessions.erasure_service import (
        ConversationErasureService,
    )

    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )
    runtime_calls: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        "control_plane_backend.sessions.erasure_service.httpx.AsyncClient",
        _make_runtime_client(runtime_calls, checkpoint_error=True),
    )
    deps = _build_erasure_deps(
        session_store,
        _FakeSessionAttachmentStore([]),
        agent_instance_store=_FakeAgentInstanceStore(
            [
                _make_record(
                    agent_instance_id="instance-1", source_runtime_id="runtime-a"
                )
            ]
        ),
        configuration=_runtime_config(runtime_id="runtime-a"),
    )

    receipt = await ConversationErasureService(deps).erase_session(
        team_id=TeamId("personal"),
        session_id="session-1",
        user_id="admin",
        authorization="Bearer test-token",
    )

    by_store = {r.store: r for r in receipt.stores}
    assert by_store["runtime_checkpoint"].ok is False
    # History was recorded as skipped, not attempted.
    assert by_store["runtime_history"].ok is False
    assert "skipped" in (by_store["runtime_history"].error or "")
    # The runtime only ever saw the checkpoint DELETE — history was never called.
    assert runtime_calls
    assert all("/agents/checkpoints/" in url for url, _ in runtime_calls)
    assert not any("/agents/sessions/" in url for url, _ in runtime_calls)


@pytest.mark.asyncio
async def test_session_attachment_endpoints_round_trip_for_owned_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )
    attachment_store = _FakeSessionAttachmentStore()
    _patch_session_store(monkeypatch, session_store)
    _patch_session_attachment_store(monkeypatch, attachment_store)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/control-plane/v1/teams/personal/sessions/session-1/attachments",
            json={
                "attachment_id": "attachment-1",
                "name": "notes.md",
                "mime": "text/markdown",
                "size_bytes": 321,
                "summary_md": "# Notes",
                "document_uid": "doc-1",
                "storage_key": "uploads/notes.md",
            },
        )
        list_resp = await client.get(
            "/control-plane/v1/teams/personal/sessions/session-1/attachments"
        )

    assert create_resp.status_code == 201
    assert create_resp.json()["attachment_id"] == "attachment-1"
    assert list_resp.status_code == 200
    assert [item["name"] for item in list_resp.json()] == ["notes.md"]


@pytest.mark.asyncio
async def test_delete_session_attachment_calls_cleanup_and_removes_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    session_store = _FakeSessionMetadataStore(
        [
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("personal"),
                agent_instance_id="instance-1",
                user_id="admin",
                title="Owned by admin",
            )
        ]
    )
    attachment_store = _FakeSessionAttachmentStore(
        [
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-1",
                name="notes.md",
                summary_md="# Notes",
                document_uid="doc-1",
                storage_key="uploads/notes.md",
            )
        ]
    )
    cleanup_calls: list[dict[str, str | None]] = []

    async def _fake_cleanup(**kwargs: Any) -> None:
        cleanup_calls.append(
            {
                "document_uid": kwargs["document_uid"],
                "storage_key": kwargs["storage_key"],
                "session_id": kwargs["session_id"],
            }
        )

    monkeypatch.setattr(
        "control_plane_backend.product.service._delete_knowledge_flow_attachment",
        _fake_cleanup,
    )
    _patch_session_store(monkeypatch, session_store)
    _patch_session_attachment_store(monkeypatch, attachment_store)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/personal/sessions/session-1/attachments/attachment-1",
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 204
    assert attachment_store._records == []
    assert cleanup_calls == [
        {
            "document_uid": "doc-1",
            "storage_key": "uploads/notes.md",
            "session_id": "session-1",
        }
    ]


@pytest.mark.asyncio
async def test_delete_knowledge_flow_attachment_uses_fast_delete_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

        async def delete(
            self, url: str, *, params: dict[str, str], headers: dict[str, str]
        ) -> httpx.Response:
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            request = httpx.Request("DELETE", url, params=params, headers=headers)
            return httpx.Response(200, request=request)

    monkeypatch.setattr(
        "control_plane_backend.product.service.httpx.AsyncClient", _FakeAsyncClient
    )
    app = create_app()
    container = get_application_container_from_app(app)
    deps = build_product_service_dependencies(container)

    await _delete_knowledge_flow_attachment(
        authorization="Bearer test-token",
        document_uid="doc-1",
        storage_key="uploads/notes.md",
        session_id="session-1",
        deps=deps,
    )

    assert captured["url"].endswith("/fast/delete/doc-1")
    assert captured["params"] == {
        "session_id": "session-1",
        "storage_key": "uploads/notes.md",
    }
    assert captured["headers"] == {"Authorization": "Bearer test-token"}


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

        async def get_by_team_id(self, team_id, session=None) -> TeamMetadata | None:
            return None

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
    from unittest.mock import MagicMock

    mock_config = MagicMock()
    mock_config.app.default_team_max_resources_storage_size = 5368709120
    mock_config.app.personal_max_resources_storage_size = 5368709120
    mock_config.scheduler.enabled = False

    fake_deps = TeamServiceDependencies(
        configuration=mock_config,
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
    from unittest.mock import MagicMock

    mock_config = MagicMock()
    mock_config.app.default_team_max_resources_storage_size = 5368709120
    mock_config.app.personal_max_resources_storage_size = 5368709120
    mock_config.scheduler.enabled = False

    fake_deps = TeamServiceDependencies(
        configuration=mock_config,
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


def _make_template_with_validated_fields() -> "_RuntimeTemplatePayload":
    """Return a fake template payload with typed field constraints for validation tests."""
    return _RuntimeTemplatePayload(
        template_agent_id="rags.sample.validated",
        title="Validated Agent",
        description="Echo with validated fields",
        kind="assistant",
        default_tuning=ManagedAgentTuning(
            role="Validated Agent",
            description="Echo with validated fields",
            fields=[
                ManagedAgentFieldSpec(
                    key="prompts.system",
                    type="prompt",
                    title="System prompt",
                    pattern=r"^.{3,}$",
                ),
                ManagedAgentFieldSpec(
                    key="settings.delay_ms",
                    type="integer",
                    title="Delay",
                    min=0,
                    max=1000,
                ),
                ManagedAgentFieldSpec(
                    key="settings.verbose",
                    type="boolean",
                    title="Verbose",
                ),
                ManagedAgentFieldSpec(
                    key="chat_options.mode",
                    type="select",
                    title="Mode",
                    enum=["compact", "full"],
                ),
            ],
        ),
    )


@pytest.mark.asyncio
async def test_team_agent_templates_exposes_non_empty_tuning_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
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
        resp = await client.get(
            f"/control-plane/v1/teams/{_PERSONAL_TEAM_ID}/agent-templates"
        )

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

    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
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

    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
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
async def test_enroll_agent_instance_rejects_invalid_tuning_value_type_and_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
        return [_make_template_with_validated_fields()]

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
                "template_id": "runtime-a:rags.sample.validated",
                "display_name": "Validated Echo",
                "tuning_field_values": {
                    "settings.delay_ms": "slow",
                    "settings.verbose": True,
                },
            },
        )

    assert resp.status_code == 422
    assert "settings.delay_ms" in resp.json()["detail"]
    assert store._records == []


@pytest.mark.asyncio
async def test_patch_agent_instance_rejects_invalid_tuning_enum_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="instance-validated",
        team_id=TeamId("personal"),
        template_id="runtime-a:rags.sample.validated",
        source_runtime_id="runtime-a",
        source_agent_id="rags.sample.validated",
        display_name="Validated",
        description=None,
        enabled=True,
        created_by="admin",
        tuning=_make_template_with_validated_fields().default_tuning,
    )
    store = _FakeAgentInstanceStore([record])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-validated",
            json={"tuning_field_values": {"chat_options.mode": "unsupported"}},
        )

    assert resp.status_code == 422
    assert "chat_options.mode" in resp.json()["detail"]
    assert store._records[0].tuning.values == {}


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
async def test_patch_agent_instance_refreshes_runtime_mcp_contract_before_validating_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="instance-mcp-refresh",
        team_id=TeamId("personal"),
        template_id="runtime-a:rags.sample.mcp",
        source_runtime_id="runtime-a",
        source_agent_id="rags.sample.mcp",
        display_name="MCP",
        description=None,
        enabled=True,
        created_by="admin",
        tuning=ManagedAgentTuning(
            role="MCP",
            description="MCP",
            mcp_servers=[
                ManagedMcpServerRef(
                    id="mcp-search",
                    display_name="Search",
                    config_fields=[
                        ManagedAgentFieldSpec(
                            key="chat_options.libraries_selection",
                            type="boolean",
                            title="Libraries",
                            default=False,
                        )
                    ],
                )
            ],
            selected_mcp_server_ids=["mcp-search"],
            mcp_config_values={
                "mcp-search": {"chat_options.libraries_selection": True}
            },
        ),
    )
    store = _FakeAgentInstanceStore([record])
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

    async def _fake_fetch(_base_url: str, include_non_public: bool = False):
        return [_make_template_with_mcp_servers()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-mcp-refresh",
            json={
                "mcp_config_values": {
                    "mcp-search": {
                        "chat_options.libraries_binding": True,
                        "chat_options.bound_library_ids": ["lib-a", "lib-b"],
                        "chat_options.libraries_selection": False,
                    }
                }
            },
        )

    assert resp.status_code == 200
    assert resp.json()["mcp_config_values"] == {
        "mcp-search": {
            "chat_options.libraries_binding": True,
            "chat_options.bound_library_ids": ["lib-a", "lib-b"],
            "chat_options.libraries_selection": False,
        }
    }


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


# ---------------------------------------------------------------------------
# MCP server selection — enrollment, validation, and drift detection
# ---------------------------------------------------------------------------


def _make_template_with_mcp_servers(
    *,
    libraries_selection_default: bool = False,
    documents_selection_default: bool = False,
    attach_files_default: bool = False,
) -> "_RuntimeTemplatePayload":
    """Return a fake template payload with two declared MCP server refs."""
    return _RuntimeTemplatePayload(
        template_agent_id="rags.sample.mcp",
        title="MCP Agent",
        description="Agent with MCP servers",
        kind="assistant",
        default_tuning=ManagedAgentTuning(
            role="MCP Agent",
            description="Agent with MCP servers",
            mcp_servers=[
                ManagedMcpServerRef(
                    id="mcp-search",
                    display_name="Search",
                    config_fields=[
                        ManagedAgentFieldSpec(
                            key="chat_options.libraries_binding",
                            type="boolean",
                            title="Libraries binding",
                            default=False,
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.libraries_selection",
                            type="boolean",
                            title="Libraries",
                            default=libraries_selection_default,
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.documents_selection",
                            type="boolean",
                            title="Documents",
                            default=documents_selection_default,
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.attach_files",
                            type="boolean",
                            title="File attachments",
                            default=attach_files_default,
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.bound_library_ids",
                            type="array",
                            title="Bound libraries",
                            item_type="string",
                            default=[],
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.search_policy_enabled",
                            type="boolean",
                            title="Search policy picker",
                            default=documents_selection_default,
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.search_policy",
                            type="string",
                            title="Search policy",
                            enum=["strict", "hybrid", "semantic"],
                            default="hybrid",
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.search_rag_scope_enabled",
                            type="boolean",
                            title="RAG scope picker",
                            default=documents_selection_default,
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.search_rag_scope",
                            type="string",
                            title="RAG scope",
                            enum=["corpus_only", "hybrid", "general_only"],
                            default="hybrid",
                        ),
                    ],
                ),
                ManagedMcpServerRef(id="mcp-storage", display_name="Storage"),
            ],
        ),
    )


@pytest.mark.asyncio
async def test_enroll_agent_instance_stores_mcp_server_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch(_base_url: str, include_non_public: bool = False):
        return [_make_template_with_mcp_servers()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
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
                "template_id": "runtime-a:rags.sample.mcp",
                "display_name": "MCP Instance",
                "mcp_server_ids": ["mcp-search"],
            },
        )

    assert resp.status_code == 201
    assert store._records[0].tuning.selected_mcp_server_ids == ["mcp-search"]


@pytest.mark.asyncio
async def test_enrolling_internal_template_is_admin_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-public template (AGENT-VISIBILITY-RFC) must not be enrollable by a
    non-admin who guesses its id; admins can enroll it."""
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch_internal(_base_url: str, include_non_public: bool = False):
        # Simulate an internal template: only resolvable when non-public is included.
        return [_make_template_with_mcp_servers()] if include_non_public else []

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_internal,
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
    body = {"template_id": "runtime-a:rags.sample.mcp", "display_name": "x"}

    # Non-admin: the hidden template resolves to nothing -> 404 (as if it did not exist).
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="bob", username="bob", roles=[]
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        denied = await client.post(
            "/control-plane/v1/teams/personal/agent-instances", json=body
        )
    assert denied.status_code == 404

    # Admin: the hidden template resolves and enrollment succeeds.
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="alice", username="alice", roles=["admin"]
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        allowed = await client.post(
            "/control-plane/v1/teams/personal/agent-instances", json=body
        )
    assert allowed.status_code == 201
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_direct_execution_of_internal_agent_is_refused_for_everyone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The direct (evaluation) prepare-execution route must NOT mint a grant for a
    non-public agent for ANYONE — not even admins. The runtime refuses direct
    execution of a non-public agent_id (agent_app._resolve_agent_instance), so a
    direct grant would be unusable; control-plane stays consistent by resolving
    with include_non_public=False unconditionally. Internal agents are reachable
    only via the managed (enrollment) path. See AGENT-VISIBILITY-RFC §3.1."""
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    # The hidden agent is only ever returned when include_non_public=True; the
    # service must never request that on this route, so the agent stays invisible.
    async def _fake_fetch_internal(_base_url: str, include_non_public: bool = False):
        return [_make_template_with_mcp_servers()] if include_non_public else []

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch_internal,
    )
    app = create_app()
    container = get_application_container_from_app(app)
    container.configuration.platform.runtime_catalog_sources = [
        RuntimeCatalogSourceConfig(
            runtime_id="runtime-a",
            base_url="http://runtime-a/pod/v1",
            enabled=True,
            ingress_prefix="/runtime/runtime-a",
        )
    ]
    url = "/control-plane/v1/teams/personal/runtimes/runtime-a/agents/rags.sample.mcp/prepare-execution"

    # Both a non-admin AND an admin get 404 — the direct path never serves a
    # non-public agent (no unusable grant is ever minted).
    for roles in ([], ["admin"]):
        app.dependency_overrides[get_current_user] = lambda roles=roles: KeycloakUser(
            uid="u", username="u", roles=roles
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(url)
        assert resp.status_code == 404, f"roles={roles} should be refused"
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# RUNTIME-07 Phase 0 — characterization of CURRENT (pre-hardening) behavior.
#
# The runtime calls GET /agent-instances/{id}/runtime to resolve a managed
# instance, forwarding the END USER's token. That endpoint today gates on the
# GLOBAL `admin` role (require_admin) and resolves via an UNSCOPED store.get —
# the wrong check (F2). This test PINS that behavior so Phase 2 (per-user team
# ReBAC + store.get_for_team) has a red->green signal. Update in place when
# Phase 2 lands; do not delete.
# See docs/swift/rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md (F2).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_f2_team_scoped_resolution_is_tenant_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F2 fixed (RUNTIME-07 rev. 2): resolution is team-scoped + ReBAC-gated.

    (a) a team member resolves their own team's instance (200) — no admin gate;
    (b) the same instance is NOT reachable through a different team's path
        (404 via store.get_for_team), so no cross-tenant binding leaks."""
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = _make_record(agent_instance_id="instance-1", team_id="team-x")
    store = _FakeAgentInstanceStore([record])
    app = create_app()
    _patch_store(monkeypatch, store)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="member-bob", username="member-bob", roles=[]
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # (a) resolved within the owning team.
        allowed = await client.get(
            "/control-plane/v1/teams/team-x/agent-instances/instance-1/runtime"
        )
        # (b) not reachable through another team's path (team-scoped lookup).
        cross = await client.get(
            "/control-plane/v1/teams/team-y/agent-instances/instance-1/runtime"
        )

    assert allowed.status_code == 200
    assert allowed.json()["owner_team_id"] == "team-x"
    assert cross.status_code == 404
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_enroll_agent_instance_stores_mcp_config_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch(_base_url: str, include_non_public: bool = False):
        return [_make_template_with_mcp_servers()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
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
                "template_id": "runtime-a:rags.sample.mcp",
                "display_name": "MCP Instance",
                "mcp_server_ids": ["mcp-search"],
                "mcp_config_values": {
                    "mcp-search": {
                        "chat_options.libraries_binding": True,
                        "chat_options.bound_library_ids": ["lib-a", "lib-b"],
                        "chat_options.libraries_selection": False,
                        "chat_options.search_policy_enabled": True,
                        "chat_options.search_policy": "semantic",
                    }
                },
            },
        )

    assert resp.status_code == 201
    assert resp.json()["mcp_config_values"] == {
        "mcp-search": {
            "chat_options.libraries_binding": True,
            "chat_options.bound_library_ids": ["lib-a", "lib-b"],
            "chat_options.libraries_selection": False,
            "chat_options.search_policy_enabled": True,
            "chat_options.search_policy": "semantic",
        }
    }
    assert store._records[0].tuning.mcp_config_values == {
        "mcp-search": {
            "chat_options.libraries_binding": True,
            "chat_options.bound_library_ids": ["lib-a", "lib-b"],
            "chat_options.libraries_selection": False,
            "chat_options.search_policy_enabled": True,
            "chat_options.search_policy": "semantic",
        }
    }


@pytest.mark.asyncio
async def test_enroll_agent_instance_rejects_unknown_mcp_server_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch(_base_url: str, include_non_public: bool = False):
        return [_make_template_with_mcp_servers()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
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
                "template_id": "runtime-a:rags.sample.mcp",
                "display_name": "MCP Instance",
                "mcp_server_ids": ["mcp-unknown"],
            },
        )

    assert resp.status_code == 422
    assert "mcp-unknown" in resp.json()["detail"]
    assert store._records == []


@pytest.mark.asyncio
async def test_enroll_agent_instance_rejects_unknown_mcp_config_server_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch(_base_url: str, include_non_public: bool = False):
        return [_make_template_with_mcp_servers()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
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
                "template_id": "runtime-a:rags.sample.mcp",
                "display_name": "MCP Instance",
                "mcp_config_values": {
                    "mcp-unknown": {"chat_options.search_policy": "semantic"}
                },
            },
        )

    assert resp.status_code == 422
    assert "mcp-unknown" in resp.json()["detail"]
    assert store._records == []


@pytest.mark.asyncio
async def test_enroll_agent_instance_rejects_unknown_mcp_config_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch(_base_url: str, include_non_public: bool = False):
        return [_make_template_with_mcp_servers()]

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _fake_fetch,
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
                "template_id": "runtime-a:rags.sample.mcp",
                "display_name": "MCP Instance",
                "mcp_config_values": {"mcp-search": {"chat_options.unsupported": True}},
            },
        )

    assert resp.status_code == 422
    assert "chat_options.unsupported" in resp.json()["detail"]
    assert store._records == []


@pytest.mark.asyncio
async def test_patch_agent_instance_can_clear_mcp_config_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="instance-mcp-config",
        team_id=TeamId("personal"),
        template_id="runtime-a:rags.sample.mcp",
        source_runtime_id="runtime-a",
        source_agent_id="rags.sample.mcp",
        display_name="MCP",
        description=None,
        enabled=True,
        created_by="admin",
        tuning=ManagedAgentTuning(
            role="MCP",
            description="MCP",
            mcp_servers=_make_template_with_mcp_servers().default_tuning.mcp_servers,
            mcp_config_values={
                "mcp-search": {"chat_options.search_policy": "semantic"}
            },
        ),
    )
    store = _FakeAgentInstanceStore([record])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-mcp-config",
            json={"mcp_config_values": None},
        )

    assert resp.status_code == 200
    assert resp.json()["mcp_config_values"] == {}
    assert store._records[0].tuning.mcp_config_values == {}


@pytest.mark.asyncio
async def test_patch_agent_instance_can_activate_no_mcp_servers_and_prunes_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="instance-mcp-none",
        team_id=TeamId("personal"),
        template_id="runtime-a:rags.sample.mcp",
        source_runtime_id="runtime-a",
        source_agent_id="rags.sample.mcp",
        display_name="MCP",
        description=None,
        enabled=True,
        created_by="admin",
        tuning=ManagedAgentTuning(
            role="MCP",
            description="MCP",
            mcp_servers=_make_template_with_mcp_servers().default_tuning.mcp_servers,
            selected_mcp_server_ids=None,
            mcp_config_values={
                "mcp-search": {"chat_options.search_policy": "semantic"}
            },
        ),
    )
    store = _FakeAgentInstanceStore([record])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-mcp-none",
            json={"mcp_server_ids": []},
        )

    assert resp.status_code == 200
    assert resp.json()["selected_mcp_server_ids"] == []
    assert resp.json()["mcp_config_values"] == {}
    assert store._records[0].tuning.selected_mcp_server_ids == []
    assert store._records[0].tuning.mcp_config_values == {}


@pytest.mark.asyncio
async def test_prepare_execution_resolves_effective_chat_options_from_tuning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="inst-chat-options",
        team_id=TeamId("personal"),
        template_id="agents-v2:rags.sample.mcp",
        source_runtime_id="agents-v2",
        source_agent_id="rags.sample.mcp",
        display_name="MCP Chat Agent",
        description="Chat options",
        enabled=True,
        created_by="admin",
        tuning=ManagedAgentTuning(
            role="MCP Chat Agent",
            description="Chat options",
            mcp_servers=_make_template_with_mcp_servers().default_tuning.mcp_servers,
            selected_mcp_server_ids=["mcp-search"],
            mcp_config_values={
                "mcp-search": {
                    "chat_options.libraries_binding": True,
                    "chat_options.bound_library_ids": ["lib-a", "lib-b"],
                    "chat_options.libraries_selection": False,
                    "chat_options.documents_selection": True,
                    "chat_options.attach_files": True,
                    "chat_options.search_policy_enabled": True,
                    "chat_options.search_policy": "semantic",
                    "chat_options.search_rag_scope_enabled": True,
                    "chat_options.search_rag_scope": "corpus_only",
                }
            },
        ),
    )
    store = _FakeAgentInstanceStore([record])
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
            "/control-plane/v1/teams/personal/agent-instances/inst-chat-options/prepare-execution"
        )

    assert resp.status_code == 200
    assert resp.json()["effective_chat_options"] == {
        "attach_files": True,
        "bound_library_ids": ["lib-a", "lib-b"],
        "libraries_selection": False,
        "documents_selection": True,
        "search_policy_selection": True,
        "default_search_policy": "semantic",
        "rag_scope_selection": True,
        "default_search_rag_scope": "corpus_only",
    }


@pytest.mark.asyncio
async def test_prepare_execution_resolves_document_scope_from_mcp_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="inst-doc-scope-defaults",
        team_id=TeamId("personal"),
        template_id="agents-v2:rags.sample.mcp",
        source_runtime_id="agents-v2",
        source_agent_id="rags.sample.mcp",
        display_name="MCP Chat Agent",
        description="Chat options",
        enabled=True,
        created_by="admin",
        tuning=ManagedAgentTuning(
            role="MCP Chat Agent",
            description="Chat options",
            values={},
            mcp_servers=_make_template_with_mcp_servers(
                libraries_selection_default=True,
                documents_selection_default=True,
            ).default_tuning.mcp_servers,
            selected_mcp_server_ids=["mcp-search"],
            mcp_config_values={},
        ),
    )
    store = _FakeAgentInstanceStore([record])
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
            "/control-plane/v1/teams/personal/agent-instances/inst-doc-scope-defaults/prepare-execution"
        )

    assert resp.status_code == 200
    assert resp.json()["effective_chat_options"] == {
        "attach_files": False,
        "libraries_selection": True,
        "documents_selection": True,
        "search_policy_selection": True,
        "default_search_policy": "hybrid",
        "rag_scope_selection": True,
        "default_search_rag_scope": "hybrid",
    }


@pytest.mark.asyncio
async def test_prepare_execution_defaults_attach_files_on_from_mcp_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """attach_files resolves on from the active server's config_field default.

    Mirrors how the search-documents catalog entry declares
    ``chat_options.attach_files`` with ``default: true`` — when the operator never
    overrides it, the resolved chat options must still expose attachments.
    """
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="inst-attach-default",
        team_id=TeamId("personal"),
        template_id="agents-v2:rags.sample.mcp",
        source_runtime_id="agents-v2",
        source_agent_id="rags.sample.mcp",
        display_name="MCP Chat Agent",
        description="Chat options",
        enabled=True,
        created_by="admin",
        tuning=ManagedAgentTuning(
            role="MCP Chat Agent",
            description="Chat options",
            values={},
            mcp_servers=_make_template_with_mcp_servers(
                attach_files_default=True,
            ).default_tuning.mcp_servers,
            selected_mcp_server_ids=["mcp-search"],
            mcp_config_values={},
        ),
    )
    store = _FakeAgentInstanceStore([record])
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
            "/control-plane/v1/teams/personal/agent-instances/inst-attach-default/prepare-execution"
        )

    assert resp.status_code == 200
    assert resp.json()["effective_chat_options"]["attach_files"] is True


@pytest.mark.asyncio
async def test_list_agent_instances_sets_unavailable_when_pod_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = _make_record(team_id=_PERSONAL_TEAM_ID)
    record = AgentInstanceRecord(
        agent_instance_id=base.agent_instance_id,
        team_id=base.team_id,
        template_id=base.template_id,
        source_runtime_id=base.source_runtime_id,
        source_agent_id=base.source_agent_id,
        display_name=base.display_name,
        description=base.description,
        enabled=base.enabled,
        created_by=base.created_by,
        tuning=ManagedAgentTuning(
            role=base.tuning.role,
            description=base.tuning.description,
            selected_mcp_server_ids=["mcp-search"],
        ),
    )
    store = _FakeAgentInstanceStore([record])
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
        resp = await client.get(
            f"/control-plane/v1/teams/{_PERSONAL_TEAM_ID}/agent-instances"
        )

    assert resp.status_code == 200
    item = resp.json()[0]
    assert item["runtime_status"] == "unavailable"
    assert item["catalog_warnings"] == []
    assert item["selected_mcp_server_ids"] == ["mcp-search"]
    assert item["mcp_config_values"] == {}


# ---------------------------------------------------------------------------
# Prompt library CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_prompts_returns_team_scoped_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt list returns team-scoped summaries without the prompt text body."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakePromptStore(
        [
            _make_prompt_record(prompt_id="prompt-1", team_id="personal"),
            _make_prompt_record(prompt_id="prompt-2", team_id="other-team"),
        ]
    )
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/personal/prompts")

    assert resp.status_code == 200
    body = resp.json()
    # 9 system defaults are always injected — filter them out to test personal prompts
    personal = [p for p in body if not p.get("is_default", False)]
    assert len(personal) == 1
    item = personal[0]
    assert item["id"] == "prompt-1"
    assert item["name"] == "Daily brief"
    assert item["description"] == "Ops baseline"
    assert item["created_by"] == "internal-admin"
    assert item["version"] == 1
    assert item["import_count"] == 0
    assert item["session_count"] == 0
    # score is null and response_model_exclude_none=True strips null fields
    assert item.get("score") is None


@pytest.mark.asyncio
async def test_create_prompt_persists_summary_and_rejects_duplicate_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt create stores one team-scoped record and later rejects duplicates."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakePromptStore([])
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/control-plane/v1/teams/personal/prompts",
            json={
                "name": "Daily brief",
                "description": "Ops baseline",
                "text": "Today is {today}.",
            },
        )
        duplicate = await client.post(
            "/control-plane/v1/teams/personal/prompts",
            json={
                "name": "Daily brief",
                "description": "Duplicate",
                "text": "Respond in {response_language}.",
            },
        )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["name"] == "Daily brief"
    assert created_body["description"] == "Ops baseline"
    assert "id" in created_body
    assert len(store._records) == 1
    assert store._records[0].text == "Today is {today}."
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


@pytest.mark.asyncio
async def test_get_update_and_delete_prompt_use_team_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt detail, replace, and delete operate strictly inside one team scope."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakePromptStore([_make_prompt_record()])
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        detail = await client.get("/control-plane/v1/teams/personal/prompts/prompt-1")
        updated = await client.put(
            "/control-plane/v1/teams/personal/prompts/prompt-1",
            json={
                "name": "Daily brief v2",
                "description": "Refined",
                "text": "Session is {session_id}.",
            },
        )
        deleted = await client.delete(
            "/control-plane/v1/teams/personal/prompts/prompt-1"
        )
        missing = await client.get("/control-plane/v1/teams/personal/prompts/prompt-1")

    assert detail.status_code == 200
    assert detail.json()["text"] == "Today is {today}."
    assert updated.status_code == 200
    assert updated.json()["name"] == "Daily brief v2"
    assert store._records == []
    assert deleted.status_code == 204
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_prompt_library_rejects_invalid_prompt_template_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt CRUD validates template text before any prompt row is written."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakePromptStore([])
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/prompts",
            json={
                "name": "Bad prompt",
                "description": None,
                "text": "Hello {unknown_token}.",
            },
        )

    assert resp.status_code == 422
    assert "{unknown_token}" in resp.json()["detail"]
    assert store._records == []


# ---------------------------------------------------------------------------
# Prompt template validation — enroll (create-then-reject)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enroll_agent_instance_rejects_unknown_prompt_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown {token} in prompts.system → 422 before any DB write."""
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
        return [_make_template_with_validated_fields()]

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
                "template_id": "runtime-a:rags.sample.validated",
                "display_name": "Bad Prompt Agent",
                "tuning_field_values": {
                    "prompts.system": "Hello {name}, today is {today}.",
                },
            },
        )

    assert resp.status_code == 422
    assert "{name}" in resp.json()["detail"]
    # Agent must not have been written to the store
    assert store._records == []


@pytest.mark.asyncio
async def test_enroll_agent_instance_accepts_valid_prompt_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All canonical {tokens} in prompts.system → 201, agent created."""
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
        return [_make_template_with_validated_fields()]

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
                "template_id": "runtime-a:rags.sample.validated",
                "display_name": "Good Prompt Agent",
                "tuning_field_values": {
                    "prompts.system": (
                        "You are a helpful assistant. Today is {today}. "
                        "Respond in {response_language}."
                    ),
                },
            },
        )

    assert resp.status_code == 201
    assert len(store._records) == 1


@pytest.mark.asyncio
async def test_enroll_agent_instance_accepts_prompt_with_code_braces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Curly braces from code snippets (non-simple patterns) are not flagged."""
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch_runtime_templates(
        _base_url: str, include_non_public: bool = False
    ):
        return [_make_template_with_validated_fields()]

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
                "template_id": "runtime-a:rags.sample.validated",
                "display_name": "Code Prompt Agent",
                "tuning_field_values": {
                    "prompts.system": (
                        "Help write code like: if (x > 0) { return x; } else { return 0; }"
                    ),
                },
            },
        )

    assert resp.status_code == 201
    assert len(store._records) == 1


@pytest.mark.asyncio
async def test_patch_agent_instance_rejects_unknown_prompt_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Updating prompts.system with an unknown {token} → 422, record unchanged."""
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = AgentInstanceRecord(
        agent_instance_id="instance-validated",
        team_id=TeamId("personal"),
        template_id="runtime-a:rags.sample.validated",
        source_runtime_id="runtime-a",
        source_agent_id="rags.sample.validated",
        display_name="Validated",
        description=None,
        enabled=True,
        created_by="admin",
        tuning=_make_template_with_validated_fields().default_tuning,
    )
    store = _FakeAgentInstanceStore([record])
    app = create_app()
    _patch_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/agent-instances/instance-validated",
            json={
                "tuning_field_values": {
                    "prompts.system": "Hi {unknown_var}, today is {today}.",
                }
            },
        )

    assert resp.status_code == 422
    assert "{unknown_var}" in resp.json()["detail"]
    # Stored record must be unchanged
    assert store._records[0].tuning.values.get("prompts.system") is None


# ---------------------------------------------------------------------------
# P1-D1b — versioning, analytics, context integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_update_increments_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT on an existing prompt auto-increments version in the summary response."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    record = _make_prompt_record()
    record.version = 1
    store = _FakePromptStore([record])
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.put(
            "/control-plane/v1/teams/personal/prompts/prompt-1",
            json={
                "name": "Daily brief v2",
                "description": "Refined",
                "text": "New {today}.",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2


@pytest.mark.asyncio
async def test_get_context_prompts_returns_personal_and_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /prompts/context returns the union of personal and team prompts with scope field."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    personal = _make_prompt_record(
        prompt_id="p-personal", team_id=_PERSONAL_TEAM_ID, name="My prompt"
    )
    team_p = _make_prompt_record(
        prompt_id="p-team", team_id="bid-team", name="Team prompt"
    )
    team_p.session_count = 5
    store = _FakePromptStore([personal, team_p])
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/bid-team/prompts/context")

    assert resp.status_code == 200
    body = resp.json()
    ids = [item["id"] for item in body]
    assert "p-personal" in ids
    assert "p-team" in ids
    # team prompt has higher session_count so should appear first
    assert body[0]["id"] == "p-team"
    assert body[0]["scope"] == "team"
    assert body[1]["scope"] == "personal"


@pytest.mark.asyncio
async def test_promote_prompt_copies_to_target_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /prompts/{id}/promote creates a copy in the target team."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakePromptStore([_make_prompt_record()])
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/prompts/prompt-1/promote",
            json={"target_team_id": "bid-team"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Daily brief"
    assert body["version"] == 1
    assert body["import_count"] == 0
    assert body["session_count"] == 0
    assert body["score"] is None
    # Two records now: original in personal, copy in bid-team
    assert len(store._records) == 2
    copy = next(r for r in store._records if str(r.team_id) == "bid-team")
    assert copy.text == "Today is {today}."


@pytest.mark.asyncio
async def test_promote_prompt_returns_409_on_name_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /prompts/{id}/promote → 409 when a same-name prompt already exists in target."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    source = _make_prompt_record(
        prompt_id="p-src", team_id="personal", name="Shared name"
    )
    conflict = _make_prompt_record(
        prompt_id="p-conflict", team_id="bid-team", name="Shared name"
    )
    store = _FakePromptStore([source, conflict])
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/personal/prompts/p-src/promote",
            json={"target_team_id": "bid-team"},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_patch_prompt_score_updates_and_returns_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH /prompts/{id} sets the quality score and returns the updated summary."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    store = _FakePromptStore([_make_prompt_record()])
    app = create_app()
    _patch_prompt_store(monkeypatch, store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/prompts/prompt-1",
            json={"score": 4.5},
        )

    assert resp.status_code == 200
    assert resp.json()["score"] == 4.5
    assert store._records[0].score == 4.5


def _make_context_session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    prompt_ids: list[str],
) -> tuple[Any, _FakeSessionMetadataStore, _FakePromptStore]:
    """Build an app + fakes for one owned session and the given library prompts."""

    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )
    session_record = SessionMetadataRecord(
        session_id="sess-1",
        team_id=TeamId("personal"),
        agent_instance_id=None,
        user_id="admin",
        title=None,
        context_prompt_ids=[],
    )
    session_store = _FakeSessionMetadataStore([session_record])
    prompt_store = _FakePromptStore(
        [_make_prompt_record(prompt_id=pid, team_id="personal") for pid in prompt_ids]
    )
    app = create_app()
    _patch_session_store(monkeypatch, session_store)
    _patch_prompt_store(monkeypatch, prompt_store)
    return app, session_store, prompt_store


@pytest.mark.asyncio
async def test_patch_session_sets_ordered_context_prompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH with context_prompt_ids stores the ordered set and counts first attach."""

    app, _session_store, prompt_store = _make_context_session(
        monkeypatch, prompt_ids=["p1", "p2"]
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/sessions/sess-1",
            json={"context_prompt_ids": ["p2", "p1"]},
        )

    assert resp.status_code == 200
    assert resp.json()["context_prompt_ids"] == ["p2", "p1"]
    # session_count incremented once per newly-attached prompt.
    counts = {r.prompt_id: r.session_count for r in prompt_store._records}
    assert counts == {"p1": 1, "p2": 1}


@pytest.mark.asyncio
async def test_patch_session_context_prompts_increment_first_attach_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-sending an already-attached id does not double-count; new ids do count."""

    app, _session_store, prompt_store = _make_context_session(
        monkeypatch, prompt_ids=["p1", "p2"]
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.patch(
            "/control-plane/v1/teams/personal/sessions/sess-1",
            json={"context_prompt_ids": ["p1"]},
        )
        resp = await client.patch(
            "/control-plane/v1/teams/personal/sessions/sess-1",
            json={"context_prompt_ids": ["p1", "p2"]},
        )

    assert resp.status_code == 200
    assert resp.json()["context_prompt_ids"] == ["p1", "p2"]
    counts = {r.prompt_id: r.session_count for r in prompt_store._records}
    # p1 counted once (first PATCH), p2 once (second PATCH) — p1 not re-counted.
    assert counts == {"p1": 1, "p2": 1}


@pytest.mark.asyncio
async def test_patch_session_empty_list_clears_context_prompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty context_prompt_ids list clears the attached set."""

    app, session_store, _prompt_store = _make_context_session(
        monkeypatch, prompt_ids=["p1"]
    )
    session_store._records[0].context_prompt_ids = ["p1"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/sessions/sess-1",
            json={"context_prompt_ids": []},
        )

    assert resp.status_code == 200
    assert resp.json()["context_prompt_ids"] == []
    assert session_store._records[0].context_prompt_ids == []


@pytest.mark.asyncio
async def test_patch_session_freshness_only_keeps_context_prompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A freshness-only PATCH (no context field) must not wipe attached prompts."""

    app, session_store, _prompt_store = _make_context_session(
        monkeypatch, prompt_ids=["p1"]
    )
    session_store._records[0].context_prompt_ids = ["p1"]

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/sessions/sess-1",
            json={"updated_at": "2026-06-19T10:00:00Z"},
        )

    assert resp.status_code == 200
    assert resp.json()["context_prompt_ids"] == ["p1"]
    assert session_store._records[0].context_prompt_ids == ["p1"]


# --- CTRLP-12 (rev. 2 / Phase R): retention on GET/PATCH /teams/{id} ----------
#
# Retention folded from the removed `team_policy_override` table + `/retention`
# endpoints into `team_metadata`, surfaced through the existing team API: GET
# embeds the resolved `retention` view; PATCH accepts the two governed fields
# (owner-only, clamped to the platform cap server-side).


def _retention_catalog() -> Any:
    """Policy catalog with platform caps for both governed retention fields."""
    from control_plane_backend.scheduler.policies.policy_models import (
        ConversationPolicyCatalog,
    )

    return ConversationPolicyCatalog.model_validate(
        {
            "conversation_policies": {
                "purge": {
                    "default": {
                        "team_delete_grace": "P30D",
                        "max_idle": "P60D",
                    }
                }
            }
        }
    )


class _FakeRetentionMetadataStore:
    """Stateful team_metadata stand-in: get_by_team_id + partial upsert.

    Mirrors the real store's partial semantics (``TeamMetadataPatch.to_store_values``)
    so retention resolution and PATCH overlay behave exactly like production.
    """

    def __init__(self, record: TeamMetadata | None = None) -> None:
        self.record = record

    async def get_by_team_id(
        self, team_id: Any, session: Any | None = None
    ) -> TeamMetadata | None:
        return self.record

    async def upsert(self, team_id: Any, patch: Any, session: Any | None = None) -> Any:
        values = patch.to_store_values()
        base = self.record.model_dump() if self.record is not None else {}
        base.update(values)
        base["id"] = TeamId(str(team_id))
        self.record = TeamMetadata(**base)
        return self.record


def _patch_team_retention(
    monkeypatch: pytest.MonkeyPatch,
    *,
    metadata_store: Any,
    permissions: list[TeamPermission],
    deny_permission: TeamPermission | None = None,
) -> list[list[TeamPermission]]:
    """Wire the team GET/PATCH path with fakes; return the captured permissions.

    Bypasses Keycloak/ReBAC exactly like the existing team-update test, but keeps
    the real retention resolution (metadata store + policy catalog) under test.
    """
    from fred_core import AuthorizationError
    from fred_core.security.models import Resource

    captured: list[list[TeamPermission]] = []

    class _FakeKeycloakAdmin:
        async def a_get_group_members(self, _team_id: str, _query: dict) -> list[dict]:
            return []

    async def _fake_validate(*_args: Any, **_kwargs: Any) -> Any:
        required = _args[3]
        captured.append(required)
        if deny_permission is not None and deny_permission in required:
            raise AuthorizationError(
                user_id="member-1",
                action=str(deny_permission.value),
                resource=Resource.TEAM,
            )
        return _FakeKeycloakAdmin(), {"id": "northbridge", "name": "Northbridge"}, "tok"

    async def _fake_permissions(*_args: Any, **_kwargs: Any) -> list[TeamPermission]:
        return permissions

    async def _fake_enrich(*_args: Any, **_kwargs: Any) -> list[Team]:
        return [Team(id=TeamId("northbridge"), name="Northbridge")]

    monkeypatch.setattr(
        "control_plane_backend.teams.service._validate_team_and_check_permission",
        _fake_validate,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_team_permissions_for_user",
        _fake_permissions,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._enrich_groups_with_team_data",
        _fake_enrich,
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_policy_catalog",
        lambda _self, **_kwargs: _retention_catalog(),
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_team_metadata_store",
        lambda _self: metadata_store,
    )
    return captured


@pytest.mark.asyncio
async def test_get_team_embeds_retention_without_value_uses_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /teams/{id}: with no team value the embedded view inherits the cap."""
    _patch_team_retention(
        monkeypatch,
        metadata_store=_FakeRetentionMetadataStore(None),
        permissions=[TeamPermission.CAN_READ],
    )
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/northbridge")

    assert resp.status_code == 200
    retention = resp.json()["retention"]
    # The team endpoint serializes with exclude_none, so None/False subfields are
    # omitted rather than emitted; assert the present fields.
    grace = retention["team_delete_grace"]
    assert grace["platform_max"] == "P30D"
    assert grace["effective"] == "P30D"
    assert grace["source"] == "platform"
    assert grace.get("team_value") is None
    assert grace.get("would_exceed", False) is False
    assert retention["max_idle"]["effective"] == "P60D"
    assert retention["max_idle"]["source"] == "platform"


@pytest.mark.asyncio
async def test_get_team_embeds_retention_with_value_flips_to_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /teams/{id}: a team value below the cap flips source to team; a value
    above the cap is clamped back to platform (would_exceed)."""
    from control_plane_backend.scheduler.policies.retention_resolver import (
        resolve_team_retention_view,
    )

    record = TeamMetadata(
        id=TeamId("northbridge"),
        team_delete_grace="P7D",
        max_idle="P90D",  # above the P60D cap -> clamped
        retention_updated_by="owner-1",
    )
    _patch_team_retention(
        monkeypatch,
        metadata_store=_FakeRetentionMetadataStore(record),
        permissions=[TeamPermission.CAN_READ],
    )
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/northbridge")

    assert resp.status_code == 200
    retention = resp.json()["retention"]

    # Endpoint output must match the pure resolver for the same inputs.
    expected = resolve_team_retention_view(
        policy=_retention_catalog().conversation_policies.purge,
        team_id="northbridge",
        team_delete_grace_override="P7D",
        max_idle_override="P90D",
    )
    assert (
        retention["team_delete_grace"]["effective"]
        == expected.team_delete_grace.effective
    )
    assert retention["team_delete_grace"]["source"] == "team"
    assert retention["team_delete_grace"]["team_value"] == "P7D"
    assert retention["max_idle"]["effective"] == "P60D"
    assert retention["max_idle"]["source"] == "platform"
    assert retention["max_idle"]["would_exceed"] is True


@pytest.mark.asyncio
async def test_patch_team_retention_owner_below_cap_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner PATCHes a value < cap -> 200, persisted, source=team, audit stamped."""
    store = _FakeRetentionMetadataStore(None)
    captured = _patch_team_retention(
        monkeypatch,
        metadata_store=store,
        permissions=[TeamPermission.CAN_UPDATE_INFO],
    )
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/northbridge",
            json={"team_delete_grace": "P7D"},  # < P30D cap
        )

    assert resp.status_code == 200
    # The team update surface authorized with CAN_UPDATE_INFO (owner-only).
    assert [TeamPermission.CAN_UPDATE_INFO] in captured

    retention = resp.json()["retention"]
    assert retention["team_delete_grace"]["team_value"] == "P7D"
    assert retention["team_delete_grace"]["effective"] == "P7D"
    assert retention["team_delete_grace"]["source"] == "team"
    # Omitted field inherits the platform cap.
    assert retention["max_idle"]["source"] == "platform"

    # Persisted with the caller stamped as the retention auditor.
    assert store.record is not None
    assert store.record.team_delete_grace == "P7D"
    assert store.record.retention_updated_by  # caller uid recorded


@pytest.mark.asyncio
async def test_patch_team_retention_partial_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH overlay over an existing record: an omitted field keeps its stored
    value; an explicit null clears it (partial semantics)."""
    existing = TeamMetadata(
        id=TeamId("northbridge"),
        team_delete_grace="P7D",
        max_idle="P30D",
        retention_updated_by="prior",
    )
    store = _FakeRetentionMetadataStore(existing)
    _patch_team_retention(
        monkeypatch,
        metadata_store=store,
        permissions=[TeamPermission.CAN_UPDATE_INFO],
    )
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Omit team_delete_grace (keep P7D); explicit null clears max_idle.
        resp = await client.patch(
            "/control-plane/v1/teams/northbridge",
            json={"max_idle": None},
        )

    assert resp.status_code == 200
    assert store.record is not None
    assert store.record.team_delete_grace == "P7D"  # omitted -> preserved
    assert store.record.max_idle is None  # explicit null -> cleared
    assert store.record.retention_updated_by  # re-stamped on the retention edit

    retention = resp.json()["retention"]
    assert retention["team_delete_grace"]["team_value"] == "P7D"
    assert retention["team_delete_grace"]["source"] == "team"
    # Cleared field falls back to the platform cap (None team_value stripped by
    # exclude_none serialization).
    assert retention["max_idle"].get("team_value") is None
    assert retention["max_idle"]["source"] == "platform"


@pytest.mark.asyncio
async def test_patch_team_retention_above_cap_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner PATCHes a value > cap -> 422; nothing is persisted."""
    store = _FakeRetentionMetadataStore(None)
    _patch_team_retention(
        monkeypatch,
        metadata_store=store,
        permissions=[TeamPermission.CAN_UPDATE_INFO],
    )
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/northbridge",
            json={"max_idle": "P90D"},  # > P60D cap
        )

    assert resp.status_code == 422
    assert "max_idle" in resp.json()["detail"]
    # Rejected before persistence.
    assert store.record is None


@pytest.mark.asyncio
async def test_patch_team_retention_non_owner_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-owner (no CAN_UPDATE_INFO) is refused with 403; nothing persisted."""
    store = _FakeRetentionMetadataStore(None)
    _patch_team_retention(
        monkeypatch,
        metadata_store=store,
        permissions=[TeamPermission.CAN_READ],
        deny_permission=TeamPermission.CAN_UPDATE_INFO,
    )
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/northbridge",
            json={"team_delete_grace": "P1D"},
        )

    assert resp.status_code == 403
    assert store.record is None
