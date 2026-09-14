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

"""Default teams for new users: platform-wide teams joined on first GCU acceptance.

Contract: CONTROL-PLANE-PRODUCT-CONTRACT.md §52.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from control_plane_backend.models.base import Base
from control_plane_backend.teams.default_team_store import PlatformDefaultTeamStore
from control_plane_backend.teams.schemas import (
    DefaultTeamForNewUsers,
    TeamNotFoundError,
)
from control_plane_backend.teams.service import (
    get_default_teams_for_new_users,
    join_default_teams_for_new_user,
    set_default_teams_for_new_users,
)
from control_plane_backend.users.api import validate_gcu
from fred_core import (
    AuthorizationError,
    GcuVersionsType,
    KeycloakUser,
    OrganizationPermission,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_ONBOARDING = TeamMetadata(id=TeamId("team-onboarding"), name="Onboarding")
_SUPPORT = TeamMetadata(id=TeamId("team-support"), name="support")
_BOTH = ["team-support", "team-onboarding"]


async def _sqlite_store(tmp_path: Path) -> tuple[AsyncEngine, PlatformDefaultTeamStore]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'default-teams.sqlite3'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.tables["platform_default_teams"].create)
    return engine, PlatformDefaultTeamStore(engine)


class _FakeRebac:
    def __init__(
        self,
        *,
        granted: bool = True,
        relations: list[Relation] | None = None,
        add_raises: Exception | None = None,
    ) -> None:
        self.permission_checks: list[OrganizationPermission] = []
        self.added: list[Relation] = []
        self._granted = granted
        self._relations = relations or []
        self._add_raises = add_raises

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        self.permission_checks.append(permission)
        if not self._granted:
            raise AuthorizationError(user.uid, permission.value, Resource.ORGANIZATION)

    async def list_direct_relations(self, resource, *, subject=None, **kwargs):
        return [
            r
            for r in self._relations
            if r.resource.id == resource.id
            and (subject is None or r.subject.id == subject.id)
        ]

    async def add_relation(self, relation: Relation, **kwargs: object):
        if self._add_raises is not None:
            raise self._add_raises
        self.added.append(relation)
        return None


class _FakeDefaultTeamStore:
    def __init__(self, team_ids: list[str] | None = None) -> None:
        self.team_ids = list(team_ids or [])
        self.replace_calls: list[tuple[list[str], str | None]] = []

    async def list_team_ids(self) -> list[str]:
        return list(self.team_ids)

    async def replace(self, team_ids: list[str], *, updated_by: str | None) -> None:
        self.replace_calls.append((list(team_ids), updated_by))
        self.team_ids = list(team_ids)


class _FakeTeamMetadataStore:
    def __init__(self, teams: list[TeamMetadata]) -> None:
        self._teams = {str(team.id): team for team in teams}

    async def get_by_team_ids(self, team_ids) -> dict[TeamId, TeamMetadata]:
        return {
            TeamId(str(team_id)): self._teams[str(team_id)]
            for team_id in team_ids
            if str(team_id) in self._teams
        }


class _FakeUserStore:
    def __init__(self, *, row_exists: bool, accepted: GcuVersionsType | None) -> None:
        self._row_exists = row_exists
        self._accepted = accepted
        self.recorded: list[GcuVersionsType] = []

    async def find_user_by_id(self, user_id, session=None):
        if not self._row_exists:
            return None
        return SimpleNamespace(gcuVersionAccepted=self._accepted)

    async def update_gcu_version(self, user_id, gcu_version, session=None) -> None:
        self.recorded.append(gcu_version)


def _team_deps(rebac: _FakeRebac, default_store: _FakeDefaultTeamStore) -> Any:
    metadata_store = _FakeTeamMetadataStore([_ONBOARDING, _SUPPORT])
    return cast(
        Any,
        SimpleNamespace(
            rebac=rebac,
            get_default_team_store=lambda: default_store,
            get_team_metadata_store=lambda: metadata_store,
        ),
    )


def _user_deps(gcu_version: str | None) -> Any:
    return cast(
        Any,
        SimpleNamespace(
            configuration=SimpleNamespace(app=SimpleNamespace(gcu_version=gcu_version))
        ),
    )


def _user(uid: str = "new-user-1") -> KeycloakUser:
    return KeycloakUser(uid=uid, username="newcomer", roles=[], email=None)


def _grants(rebac: _FakeRebac) -> set[tuple[str, RelationType, str]]:
    return {(r.subject.id, r.relation, r.resource.id) for r in rebac.added}


# --------------------------- store ---------------------------


@pytest.mark.asyncio
async def test_store_replaces_and_clears_the_default_teams(tmp_path: Path) -> None:
    engine, store = await _sqlite_store(tmp_path)
    try:
        assert await store.list_team_ids() == []

        await store.replace(["beta", "alpha"], updated_by="admin-1")
        assert await store.list_team_ids() == ["alpha", "beta"]

        await store.replace(["gamma"], updated_by="admin-2")
        assert await store.list_team_ids() == ["gamma"]

        await store.replace([], updated_by="admin-2")
        assert await store.list_team_ids() == []
    finally:
        await engine.dispose()


# --------------------------- get / set ---------------------------


@pytest.mark.asyncio
async def test_default_teams_are_read_with_their_names_sorted_by_name() -> None:
    rebac = _FakeRebac()

    result = await get_default_teams_for_new_users(
        _user(), _team_deps(rebac, _FakeDefaultTeamStore(_BOTH))
    )

    assert result == [
        DefaultTeamForNewUsers(team_id=TeamId("team-onboarding"), name="Onboarding"),
        DefaultTeamForNewUsers(team_id=TeamId("team-support"), name="support"),
    ]
    assert rebac.permission_checks == [OrganizationPermission.CAN_MANAGE_PLATFORM]


@pytest.mark.asyncio
async def test_deleted_default_team_is_skipped() -> None:
    deps = _team_deps(
        _FakeRebac(), _FakeDefaultTeamStore(["team-gone", "team-support"])
    )

    result = await get_default_teams_for_new_users(_user(), deps)

    assert [team.team_id for team in result] == ["team-support"]


@pytest.mark.asyncio
async def test_reading_the_default_teams_requires_manage_platform() -> None:
    with pytest.raises(AuthorizationError):
        await get_default_teams_for_new_users(
            _user(), _team_deps(_FakeRebac(granted=False), _FakeDefaultTeamStore(_BOTH))
        )


@pytest.mark.asyncio
async def test_setting_the_default_teams_requires_manage_platform() -> None:
    store = _FakeDefaultTeamStore()

    with pytest.raises(AuthorizationError):
        await set_default_teams_for_new_users(
            _user(),
            [TeamId("team-onboarding")],
            _team_deps(_FakeRebac(granted=False), store),
        )

    assert store.replace_calls == []


@pytest.mark.asyncio
async def test_one_unregistered_team_rejects_the_whole_list() -> None:
    """Personal spaces land here too: they never have a registry row."""
    store = _FakeDefaultTeamStore(["team-support"])

    with pytest.raises(TeamNotFoundError):
        await set_default_teams_for_new_users(
            _user(),
            [TeamId("team-onboarding"), TeamId("personal-someone")],
            _team_deps(_FakeRebac(), store),
        )

    assert store.replace_calls == []
    assert store.team_ids == ["team-support"]


@pytest.mark.asyncio
async def test_setting_deduplicates_records_the_admin_and_clears() -> None:
    store = _FakeDefaultTeamStore()
    deps = _team_deps(_FakeRebac(), store)
    ids = [TeamId("team-onboarding"), TeamId("team-support"), TeamId("team-onboarding")]

    await set_default_teams_for_new_users(_user("admin-1"), ids, deps)
    await set_default_teams_for_new_users(_user("admin-1"), [], deps)

    assert store.replace_calls == [
        (["team-onboarding", "team-support"], "admin-1"),
        ([], "admin-1"),
    ]


# --------------------------- join_default_teams_for_new_user ---------------------------


@pytest.mark.asyncio
async def test_new_user_joins_every_default_team_as_member() -> None:
    rebac = _FakeRebac()

    await join_default_teams_for_new_user(
        "new-user-1", _team_deps(rebac, _FakeDefaultTeamStore(_BOTH))
    )

    assert _grants(rebac) == {
        ("new-user-1", RelationType.TEAM_MEMBER, "team-onboarding"),
        ("new-user-1", RelationType.TEAM_MEMBER, "team-support"),
    }


@pytest.mark.asyncio
async def test_team_where_the_user_already_holds_a_role_is_skipped() -> None:
    existing = Relation(
        subject=RebacReference(Resource.USER, "new-user-1"),
        relation=RelationType.TEAM_ADMIN,
        resource=RebacReference(Resource.TEAM, "team-onboarding"),
    )
    rebac = _FakeRebac(relations=[existing])

    await join_default_teams_for_new_user(
        "new-user-1", _team_deps(rebac, _FakeDefaultTeamStore(_BOTH))
    )

    assert _grants(rebac) == {("new-user-1", RelationType.TEAM_MEMBER, "team-support")}


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_team_ids", [[], ["team-gone"]])
async def test_no_usable_default_team_grants_nothing(
    stored_team_ids: list[str],
) -> None:
    rebac = _FakeRebac()

    await join_default_teams_for_new_user(
        "new-user-1", _team_deps(rebac, _FakeDefaultTeamStore(stored_team_ids))
    )

    assert rebac.added == []


# --------------------------- POST /gcu ---------------------------


async def _accept_gcu(
    rebac: _FakeRebac, user_store: _FakeUserStore, *, gcu_version: str | None = "v1"
) -> None:
    await validate_gcu(
        deps=_user_deps(gcu_version),
        team_deps=_team_deps(rebac, _FakeDefaultTeamStore(_BOTH)),
        user=_user(),
        user_store=cast(Any, user_store),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("row_exists", [False, True])
async def test_first_gcu_acceptance_joins_the_default_teams(row_exists: bool) -> None:
    """A users row can exist before any acceptance (storage accounting creates one)."""
    rebac = _FakeRebac()
    user_store = _FakeUserStore(row_exists=row_exists, accepted=None)

    await _accept_gcu(rebac, user_store)

    assert len(rebac.added) == 2
    assert user_store.recorded == [GcuVersionsType.V1]


@pytest.mark.asyncio
async def test_accepting_a_newer_gcu_does_not_rejoin_the_default_teams() -> None:
    rebac = _FakeRebac()
    user_store = _FakeUserStore(row_exists=True, accepted=GcuVersionsType.V1)

    await _accept_gcu(rebac, user_store)

    assert rebac.added == []
    assert user_store.recorded == [GcuVersionsType.V1]


@pytest.mark.asyncio
async def test_deployment_without_gcu_never_joins_the_default_teams() -> None:
    rebac = _FakeRebac()
    user_store = _FakeUserStore(row_exists=False, accepted=None)

    await _accept_gcu(rebac, user_store, gcu_version=None)

    assert rebac.added == []
    assert user_store.recorded == []


@pytest.mark.asyncio
async def test_failed_grant_does_not_record_the_acceptance() -> None:
    """The retry must still count as a first acceptance."""
    rebac = _FakeRebac(add_raises=RuntimeError("openfga unavailable"))
    user_store = _FakeUserStore(row_exists=False, accepted=None)

    with pytest.raises(RuntimeError, match="openfga unavailable"):
        await _accept_gcu(rebac, user_store)

    assert user_store.recorded == []
