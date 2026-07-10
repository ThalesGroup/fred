# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""AUTHZ-05 review item 9 (RFC Part 6 §32): team-registry governance capabilities.

`can_list_all_teams`, `can_delete_team`, `can_rescue_team_admin` let
`platform_admin` govern the *existence* of teams — they must never reach into
team data. `can_rescue_team_admin` must be mechanically inert against any team
that already has a `team_admin`: that guard is what makes it structurally
different from the `§24.7` escalation that was tried on this branch and
reverted (a standing grant reachable on every team, forever, through ordinary
membership endpoints). These tests lock in that a rescue only ever succeeds on
a genuinely orphaned team.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from control_plane_backend.teams.schemas import (
    TeamNotFoundError,
    TeamRescueNotOrphanedError,
)
from control_plane_backend.teams.service import (
    delete_team,
    list_all_teams_for_registry,
    rescue_team_admin,
)
from fred_core import (
    KeycloakUser,
    OrganizationPermission,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata
from httpx import ASGITransport, AsyncClient


class _FakeRebac:
    """Records org-permission checks and relation writes/deletes for assertions."""

    def __init__(self, *, team_admin_ids: set[str] | None = None) -> None:
        self.permission_checks: list[OrganizationPermission] = []
        self.team_admin_ids = team_admin_ids or set()
        self.added_relations: list[Relation] = []
        self.deleted_references: list[RebacReference] = []

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        self.permission_checks.append(permission)

    async def lookup_subjects(self, resource, relation, subject_type, **kwargs):
        if relation == RelationType.TEAM_ADMIN:
            return [RebacReference(Resource.USER, uid) for uid in self.team_admin_ids]
        return []

    async def add_relation(self, relation: Relation):
        self.added_relations.append(relation)
        return None

    async def delete_all_relations_of_reference(self, reference: RebacReference):
        self.deleted_references.append(reference)
        return None


class _FakeMetadataStore:
    def __init__(self, teams: dict[str, TeamMetadata] | None = None) -> None:
        self.teams = dict(teams or {})
        self.deleted_ids: list[str] = []

    async def get_by_team_id(self, team_id, session=None):
        return self.teams.get(str(team_id))

    async def delete(self, team_id, session=None) -> None:
        self.deleted_ids.append(str(team_id))
        self.teams.pop(str(team_id), None)


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="platform-admin-1", username="admin", roles=[], email=None, groups=[]
    )


def _deps(rebac: _FakeRebac, store: _FakeMetadataStore):
    from control_plane_backend.teams.dependencies import TeamServiceDependencies

    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=cast(Any, lambda: store),
        get_content_store=cast(Any, object),
        get_session_store=cast(Any, object),
        get_purge_queue_store=cast(Any, object),
        get_policy_catalog=cast(Any, object),
        get_users_by_ids=cast(Any, lambda *_a, **_k: {}),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


# --------------------------- can_rescue_team_admin ---------------------------


@pytest.mark.asyncio
async def test_rescue_team_admin_grants_admin_when_team_has_zero_admins() -> None:
    rebac = _FakeRebac(team_admin_ids=set())
    store = _FakeMetadataStore(
        {"orphan-team": TeamMetadata(id=TeamId("orphan-team"), name="Orphan")}
    )

    await rescue_team_admin(
        _user(), TeamId("orphan-team"), "rescued-user", _deps(rebac, store)
    )

    assert rebac.permission_checks == [OrganizationPermission.CAN_RESCUE_TEAM_ADMIN]
    assert len(rebac.added_relations) == 1
    written = rebac.added_relations[0]
    assert written.subject == RebacReference(Resource.USER, "rescued-user")
    assert written.relation == RelationType.TEAM_ADMIN
    assert written.resource == RebacReference(Resource.TEAM, "orphan-team")


@pytest.mark.asyncio
async def test_rescue_team_admin_rejects_when_team_already_has_an_admin() -> None:
    """The load-bearing guard: never a standing grant, only ever inert-unless-orphaned."""
    rebac = _FakeRebac(team_admin_ids={"existing-admin"})
    store = _FakeMetadataStore(
        {"staffed-team": TeamMetadata(id=TeamId("staffed-team"), name="Staffed")}
    )

    with pytest.raises(TeamRescueNotOrphanedError) as excinfo:
        await rescue_team_admin(
            _user(), TeamId("staffed-team"), "wannabe-admin", _deps(rebac, store)
        )

    assert excinfo.value.existing_admin_ids == {"existing-admin"}
    assert rebac.added_relations == []  # no relation written — mechanically inert


@pytest.mark.asyncio
async def test_rescue_team_admin_raises_not_found_for_unknown_team() -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore({})

    with pytest.raises(TeamNotFoundError):
        await rescue_team_admin(
            _user(), TeamId("ghost-team"), "someone", _deps(rebac, store)
        )

    assert rebac.added_relations == []


# --------------------------- can_delete_team ---------------------------


@pytest.mark.asyncio
async def test_delete_team_removes_metadata_and_all_relations() -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore(
        {"gone-team": TeamMetadata(id=TeamId("gone-team"), name="Gone")}
    )

    await delete_team(_user(), TeamId("gone-team"), _deps(rebac, store))

    assert rebac.permission_checks == [OrganizationPermission.CAN_DELETE_TEAM]
    assert rebac.deleted_references == [RebacReference(Resource.TEAM, "gone-team")]
    assert store.deleted_ids == ["gone-team"]


@pytest.mark.asyncio
async def test_delete_team_raises_not_found_for_unknown_team() -> None:
    rebac = _FakeRebac()
    store = _FakeMetadataStore({})

    with pytest.raises(TeamNotFoundError):
        await delete_team(_user(), TeamId("ghost-team"), _deps(rebac, store))

    assert rebac.deleted_references == []
    assert store.deleted_ids == []


# --------------------------- can_list_all_teams ---------------------------


@pytest.mark.asyncio
async def test_list_all_teams_for_registry_checks_permission_before_delegating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct capability from `can_manage_platform` (`compute_platform_stats`'s
    caller, item 3) — narrower intent, its own gate, same underlying listing."""
    rebac = _FakeRebac()
    store = _FakeMetadataStore({})
    captured: list[object] = []

    async def _fake_list_all_teams_unfiltered(user, deps):
        captured.append((user, deps))
        return []

    monkeypatch.setattr(
        "control_plane_backend.teams.service.list_all_teams_unfiltered",
        _fake_list_all_teams_unfiltered,
    )

    result = await list_all_teams_for_registry(_user(), _deps(rebac, store))

    assert result == []
    assert rebac.permission_checks == [OrganizationPermission.CAN_LIST_ALL_TEAMS]
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_get_teams_all_route_is_not_swallowed_by_team_id_path_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`GET /teams/all` must be registered before `GET /teams/{team_id}` — otherwise
    the literal `all` segment is captured as a team id and routed to `get_team`
    instead of the registry listing."""
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")

    sentinel_call_count = 0

    async def _fake_list_all_teams_for_registry(user, deps):
        nonlocal sentinel_call_count
        sentinel_call_count += 1
        return []

    monkeypatch.setattr(
        "control_plane_backend.teams.api.list_all_teams_from_service",
        _fake_list_all_teams_for_registry,
    )

    from control_plane_backend.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/teams/all")

    assert resp.status_code == 200
    assert resp.json() == []
    assert sentinel_call_count == 1
