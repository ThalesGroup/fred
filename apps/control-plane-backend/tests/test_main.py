"""
Offline integration tests for the control-plane-backend product API.

Ref: docs/backlog/BACKLOG.md §3d — managed agent CRUD, enrollment, update, tuning
     field validation (type/enum/min-max/pattern), MCP server selection (C1),
     mcp_config_values per-server config;
     §3d.9 (P1) — prompt template validation at persistence boundary (unknown tokens → 422);
     §6.4.D — PATCH session endpoint (updated_at, title).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, cast

import pytest
from fred_core import RelationType, SessionSchema, TeamPermission
from fred_core.common import TeamId, personal_team_id
from fred_core.teams.metadata_store import TeamMetadata
from httpx import ASGITransport, AsyncClient
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
from control_plane_backend.product.service import _RuntimeTemplatePayload
from control_plane_backend.prompts.store import PromptRecord
from control_plane_backend.sessions.store import SessionMetadataRecord
from control_plane_backend.teams.schemas import (
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
        context_prompt_id: str | None = None,
        clear_context_prompt: bool = False,
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
                if context_prompt_id is not None:
                    record.context_prompt_id = context_prompt_id
                elif clear_context_prompt:
                    record.context_prompt_id = None
                return record
        return None

    async def get(self, session_id: str) -> SessionMetadataRecord | None:
        return next((r for r in self._records if r.session_id == session_id), None)

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
async def test_create_user_accepts_payload_without_password() -> None:
    """POST /users no longer requires a password field (auth stays in Keycloak)."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/users",
            json={
                "username": "test-user",
                "email": "test-user@app.local",
            },
        )

    # 201 on first run, 409 if the SQLite fixture already has this username.
    assert resp.status_code in (201, 409)


@pytest.mark.asyncio
async def test_delete_nonexistent_user_returns_404() -> None:
    """DELETE /users/{id} returns 404 for unknown UUIDs (no longer 503)."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/users/00000000-0000-0000-0000-000000000000"
        )

    assert resp.status_code == 404


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
    assert payload["active_team"]["id"] == _PERSONAL_TEAM_ID
    assert payload["available_teams"][0]["id"] == _PERSONAL_TEAM_ID
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
                "search_policy_selection": False,
                "default_search_policy": "hybrid",
                "rag_scope_selection": False,
                "default_search_rag_scope": "hybrid",
            },
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
    assert payload["effective_chat_options"] == {
        "attach_files": False,
        "libraries_selection": False,
        "search_policy_selection": False,
        "default_search_policy": "hybrid",
        "rag_scope_selection": False,
        "default_search_rag_scope": "hybrid",
    }
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
async def test_delete_team_session_does_not_delete_other_user_session(
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

    assert resp.status_code == 204
    assert len(store._records) == 1
    assert store._records[0].session_id == "session-1"


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
    captured_permissions: list[list[TeamPermission]] = []

    async def _fake_validate_team_and_check_permission(
        *_args,
        **_kwargs,
    ):
        permissions = _args[3]
        captured_permissions.append(permissions)
        return None

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

        async def get_by_team_id(
            self, team_id: str, session=None
        ) -> TeamMetadata | None:
            return TeamMetadata(id=TeamId(team_id))

        async def upsert(self, team_id: str, patch, session=None) -> TeamMetadata:
            self.calls.append((team_id, patch.model_dump(exclude_unset=True)))
            return TeamMetadata(id=TeamId(team_id))

    class _FakeRebac:
        def __init__(self) -> None:
            self.checked_permissions: list[list[TeamPermission]] = []

        async def check_user_team_permissions_or_raise(
            self, *, user, team_id, permissions
        ) -> str | None:
            self.checked_permissions.append(list(permissions))
            return "token"

        async def add_relation(self, _relation) -> None:
            return None

        async def delete_relations(self, _relations) -> None:
            return None

    fake_metadata_store = _FakeMetadataStore()
    fake_rebac = _FakeRebac()

    async def _fake_get_team_users_by_relation(*_args, **_kwargs):
        return set()

    async def _fake_get_team_permissions_for_user(*_args, **_kwargs):
        return [TeamPermission.CAN_UPDATE_INFO]

    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_team_users_by_relation",
        _fake_get_team_users_by_relation,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams.service._get_team_permissions_for_user",
        _fake_get_team_permissions_for_user,
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_team_metadata_store",
        lambda _self: fake_metadata_store,
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_rebac_engine",
        lambda _self: fake_rebac,
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
    assert fake_rebac.checked_permissions == [[TeamPermission.CAN_UPDATE_INFO]]
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


def test_team_from_metadata_resolves_presigned_banner_url() -> None:
    from unittest.mock import MagicMock

    from control_plane_backend.teams.service import _team_from_metadata

    metadata = TeamMetadata(
        id=TeamId("team-1"),
        description="desc",
        is_private=False,
        banner_object_storage_key="teams/team-1/banner-1.png",
    )

    class _FakeContentStore:
        def get_presigned_url(self, key: str, expires=None) -> str:
            _ = expires
            assert key == "teams/team-1/banner-1.png"
            return "https://example.test/banner.png"

    mock_config = MagicMock()
    mock_config.app.default_team_max_resources_storage_size = 5368709120

    team = _team_from_metadata(
        metadata,
        owners=[],
        configuration=mock_config,
        content_store=cast(Any, _FakeContentStore()),
        is_member=True,
    )

    assert team.description == "desc"
    assert team.is_private is False
    assert team.banner_image_url == "https://example.test/banner.png"


def test_dedupe_user_summaries_by_display_key_collapses_owner_alias() -> None:
    from control_plane_backend.teams.service import (
        _dedupe_user_summaries_by_display_key,
    )

    owners = [
        UserSummary(id="user-1", username="marc"),
        UserSummary(id="marc"),
    ]

    deduped = _dedupe_user_summaries_by_display_key(owners)

    assert [owner.username or owner.id for owner in deduped] == ["marc"]


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
async def test_enroll_agent_instance_rejects_invalid_tuning_value_type_and_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch_runtime_templates(_base_url: str):
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


def _make_template_with_mcp_servers() -> "_RuntimeTemplatePayload":
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
                            key="chat_options.libraries_selection",
                            type="boolean",
                            title="Libraries",
                            default=False,
                        ),
                        ManagedAgentFieldSpec(
                            key="chat_options.search_policy",
                            type="string",
                            title="Search policy",
                            enum=["strict", "hybrid", "semantic"],
                            default="hybrid",
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

    async def _fake_fetch(_base_url: str):
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
async def test_enroll_agent_instance_stores_mcp_config_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.product.api.get_team_by_id_from_service",
        _fake_get_team_by_id,
    )

    async def _fake_fetch(_base_url: str):
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
                        "chat_options.libraries_selection": True,
                        "chat_options.search_policy": "semantic",
                    }
                },
            },
        )

    assert resp.status_code == 201
    assert resp.json()["mcp_config_values"] == {
        "mcp-search": {
            "chat_options.libraries_selection": True,
            "chat_options.search_policy": "semantic",
        }
    }
    assert store._records[0].tuning.mcp_config_values == {
        "mcp-search": {
            "chat_options.libraries_selection": True,
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

    async def _fake_fetch(_base_url: str):
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

    async def _fake_fetch(_base_url: str):
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

    async def _fake_fetch(_base_url: str):
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
            values={"chat_options.attach_files": True},
            mcp_servers=_make_template_with_mcp_servers().default_tuning.mcp_servers,
            selected_mcp_server_ids=["mcp-search"],
            mcp_config_values={
                "mcp-search": {
                    "chat_options.libraries_selection": True,
                    "chat_options.search_policy": "semantic",
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
        "libraries_selection": True,
        "search_policy_selection": True,
        "default_search_policy": "semantic",
        "rag_scope_selection": True,
        "default_search_rag_scope": "corpus_only",
    }


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

    async def _fake_fetch_runtime_templates(_base_url: str):
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

    async def _fake_fetch_runtime_templates(_base_url: str):
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

    async def _fake_fetch_runtime_templates(_base_url: str):
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


@pytest.mark.asyncio
async def test_patch_session_sets_context_prompt_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH /sessions/{id} with context_prompt_id stores and returns the reference."""

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
        context_prompt_id=None,
    )
    session_store = _FakeSessionMetadataStore([session_record])
    prompt_record = _make_prompt_record(prompt_id="ctx-prompt", team_id="personal")
    prompt_store = _FakePromptStore([prompt_record])
    app = create_app()
    _patch_session_store(monkeypatch, session_store)
    _patch_prompt_store(monkeypatch, prompt_store)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            "/control-plane/v1/teams/personal/sessions/sess-1",
            json={"context_prompt_id": "ctx-prompt"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["context_prompt_id"] == "ctx-prompt"
    # session_count should be incremented
    assert prompt_store._records[0].session_count == 1
