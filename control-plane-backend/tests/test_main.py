from __future__ import annotations

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from control_plane_backend.main import create_app


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration.yaml")


@pytest.mark.asyncio
async def test_healthz_endpoint() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/healthz")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_resolve_purge_policy_team_override() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/policies/purge/resolve",
            json={"team_id": "contractors", "trigger": "member_removed"},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["retention"] == "PT12H"
    assert payload["matched_rule_id"] == "purge.team.contractors"


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
async def test_list_teams_returns_empty_without_keycloak_m2m() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams")

    assert resp.status_code == 200
    assert resp.json() == []


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
            return {"id": "contractors", "name": "Contractors"}

        async def a_group_user_remove(self, _user_id: str, _group_id: str) -> None:
            return None

    class _FakeRebac:
        def __init__(self) -> None:
            self.delete_relations_calls = 0

        async def delete_relations(self, _relations) -> None:
            self.delete_relations_calls += 1

    class _FakeSessionStore:
        async def get_payloads_for_user(self, _user_id: str) -> list[dict]:
            return [
                {"id": "s-1", "team_id": "contractors"},
                {"id": "s-2", "team_id": "temp-lab"},
                {"id": "s-3", "team_id": "contractors"},
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
        ) -> None:
            self.enqueued.append((session_id, team_id, user_id, due_at))

    fake_rebac = _FakeRebac()
    fake_queue = _FakeQueueStore()

    async def _fake_get_user_role_in_team(*_args, **_kwargs):
        from control_plane_backend.teams_structures import UserTeamRelation

        return UserTeamRelation.MEMBER

    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        return _FakeKeycloakAdmin(), {"id": "contractors", "name": "Contractors"}, None

    monkeypatch.setattr(
        "control_plane_backend.teams_service._get_user_role_in_team",
        _fake_get_user_role_in_team,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.application_context.ApplicationContext.get_rebac_engine",
        lambda _self: fake_rebac,
    )
    monkeypatch.setattr(
        "control_plane_backend.application_context.ApplicationContext.get_session_store",
        lambda _self: _FakeSessionStore(),
    )
    monkeypatch.setattr(
        "control_plane_backend.application_context.ApplicationContext.get_purge_queue_store",
        lambda _self: fake_queue,
    )

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(
            "/control-plane/v1/teams/contractors/members/user-002",
        )

    assert resp.status_code == 202
    payload = resp.json()
    assert payload["status"] == "accepted"
    assert payload["team_id"] == "contractors"
    assert payload["user_id"] == "user-002"
    assert payload["sessions_enqueued"] == 2
    assert payload["policy_mode"] == "deferred_delete"
    assert payload["retention_seconds"] == 43200
    assert payload["matched_rule_id"] == "purge.team.contractors"
    assert len(fake_queue.enqueued) == 2
    assert fake_queue.enqueued[0][0] == "s-1"
    assert fake_queue.enqueued[1][0] == "s-3"
    assert fake_rebac.delete_relations_calls == 1
