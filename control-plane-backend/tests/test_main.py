from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, cast

import pytest
from fred_core import RelationType, SessionSchema, TeamPermission
from fred_core.common import TeamId
from httpx import ASGITransport, AsyncClient
from keycloak.exceptions import KeycloakPutError

from control_plane_backend.main import create_app
from control_plane_backend.team_metadata_store import TeamMetadata
from control_plane_backend.teams_structures import KeycloakGroupSummary, Team


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


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
        "control_plane_backend.teams_service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service._add_team_member_relation",
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
        "control_plane_backend.teams_service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service._get_team_permissions_for_user",
        _fake_get_team_permissions_for_user,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service._enrich_groups_with_team_data",
        _fake_enrich_groups_with_team_data,
    )
    monkeypatch.setattr(
        "control_plane_backend.application_context.ApplicationContext.get_team_metadata_store",
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
    from control_plane_backend.teams_service import _enrich_groups_with_team_data

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
        "control_plane_backend.teams_service._get_team_users_by_relation",
        _fake_get_team_users_by_relation,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service.get_users_by_ids",
        _fake_get_users_by_ids,
    )
    monkeypatch.setattr(
        "control_plane_backend.application_context.ApplicationContext.get_team_metadata_store",
        lambda _self: _FakeMetadataStore(),
    )
    monkeypatch.setattr(
        "control_plane_backend.application_context.ApplicationContext.get_content_store",
        lambda _self: _FakeContentStore(),
    )

    app = create_app()
    _ = app  # keep app/context alive for this test

    teams = await _enrich_groups_with_team_data(
        cast(Any, _FakeAdmin()),
        rebac=cast(
            Any, object()
        ),  # unused due monkeypatching _get_team_users_by_relation
        user=cast(Any, type("User", (), {"uid": "user-1"})()),
        groups=[
            KeycloakGroupSummary(id=TeamId("team-1"), name="Team 1", member_count=0)
        ],
    )

    assert len(teams) == 1
    assert teams[0].description == "desc"
    assert teams[0].is_private is False
    assert teams[0].banner_image_url == "https://example.test/banner.png"


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
        "control_plane_backend.teams_service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.application_context.ApplicationContext.get_content_store",
        lambda _self: fake_content_store,
    )
    monkeypatch.setattr(
        "control_plane_backend.application_context.ApplicationContext.get_team_metadata_store",
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
        "control_plane_backend.teams_service._validate_team_and_check_permission",
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
        "control_plane_backend.teams_service._validate_team_and_check_permission",
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
        "control_plane_backend.teams_service._validate_team_and_check_permission",
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
        from control_plane_backend.teams_structures import UserTeamRelation

        return UserTeamRelation.MEMBER

    async def _fake_validate_team_and_check_permission(*_args, **_kwargs):
        return _FakeKeycloakAdmin(), {"id": "swiftpost", "name": "SwiftPost"}, None

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
    from control_plane_backend.scheduler.policies.policy_models import (
        PolicyEvaluationResult,
        PurgeMode,
    )
    from control_plane_backend.scheduler.temporal.structures import (
        LifecycleManagerResult,
    )

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

    class _FakeAppContext:
        def __init__(self) -> None:
            scheduler = type("SchedulerCfg", (), {"enabled": True})()
            app = type("AppCfg", (), {"gcu_version": None})()
            self.configuration = type("Cfg", (), {"scheduler": scheduler, "app": app})()
            self._rebac = _FakeRebac()
            self._session_store = _FakeSessionStore()
            self._queue_store = _FakeQueueStore()

        def get_rebac_engine(self):
            return self._rebac

        def get_session_store(self):
            return self._session_store

        def get_purge_queue_store(self):
            return self._queue_store

        def get_policy_catalog(self):
            return object()

        def get_scheduler_backend(self):
            from fred_core.scheduler import SchedulerBackend

            return SchedulerBackend.MEMORY

    lifecycle_calls: list[int] = []

    async def _fake_get_user_role_in_team(*_args, **_kwargs):
        from control_plane_backend.teams_structures import UserTeamRelation

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

    monkeypatch.setattr(
        "control_plane_backend.teams_service.ApplicationContext.get_instance",
        lambda: _FakeAppContext(),
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service._get_user_role_in_team",
        _fake_get_user_role_in_team,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service._validate_team_and_check_permission",
        _fake_validate_team_and_check_permission,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service.evaluate_policy_for_request",
        _fake_evaluate_policy_for_request,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service.run_lifecycle_manager_once_in_memory",
        _fake_run_lifecycle_manager_once_in_memory,
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

    from control_plane_backend.common.structures import Configuration
    from control_plane_backend.scheduler.temporal.structures import (
        LifecycleManagerResult,
    )

    payload = parse_yaml_mapping_file("./config/configuration.yaml")
    payload["scheduler"]["enabled"] = True
    payload["scheduler"]["backend"] = "memory"
    config = Configuration.model_validate(payload)

    async def _fake_run_lifecycle_manager_once_in_memory(_input_data):
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
    from control_plane_backend.teams_structures import UserTeamRelation

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
        "control_plane_backend.teams_service._get_user_role_in_team",
        _fake_get_user_role_in_team,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service._get_team_users_by_relation",
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
    from control_plane_backend.teams_structures import UserTeamRelation

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
        "control_plane_backend.teams_service._get_user_role_in_team",
        _fake_get_user_role_in_team,
    )
    monkeypatch.setattr(
        "control_plane_backend.teams_service._get_team_users_by_relation",
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
