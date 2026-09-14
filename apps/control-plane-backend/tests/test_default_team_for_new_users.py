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

"""Default team for new users: one platform-wide team, joined on first GCU acceptance.

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
    get_default_team_for_new_users,
    join_default_team_for_new_user,
    set_default_team_for_new_users,
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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_ONBOARDING = TeamMetadata(id=TeamId("team-onboarding"), name="Onboarding")


async def _sqlite_store(tmp_path: Path) -> tuple[AsyncEngine, PlatformDefaultTeamStore]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'default-team.sqlite3'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.tables["platform_default_team"].create)
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
    def __init__(self, team_id: str | None = None) -> None:
        self.team_id = team_id
        self.set_calls: list[tuple[str | None, str | None]] = []

    async def get_team_id(self) -> str | None:
        return self.team_id

    async def set(self, team_id: str | None, *, updated_by: str | None) -> None:
        self.set_calls.append((team_id, updated_by))
        self.team_id = team_id


class _FakeTeamMetadataStore:
    def __init__(self, teams: list[TeamMetadata]) -> None:
        self._teams = {str(team.id): team for team in teams}

    async def get_by_team_id(self, team_id) -> TeamMetadata | None:
        return self._teams.get(str(team_id))


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


def _team_deps(
    rebac: _FakeRebac,
    default_store: _FakeDefaultTeamStore,
    teams: list[TeamMetadata] | None = None,
) -> Any:
    metadata_store = _FakeTeamMetadataStore([_ONBOARDING] if teams is None else teams)
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


# --------------------------- store ---------------------------


@pytest.mark.asyncio
async def test_store_replaces_and_clears_the_default_team(tmp_path: Path) -> None:
    engine, store = await _sqlite_store(tmp_path)
    try:
        assert await store.get_team_id() is None

        await store.set("alpha", updated_by="admin-1")
        await store.set("beta", updated_by="admin-2")
        assert await store.get_team_id() == "beta"

        await store.set(None, updated_by="admin-2")
        assert await store.get_team_id() is None
        await store.set(None, updated_by="admin-2")
        assert await store.get_team_id() is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_refuses_a_second_row(tmp_path: Path) -> None:
    engine, _ = await _sqlite_store(tmp_path)
    try:
        table = Base.metadata.tables["platform_default_team"]
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(table.insert().values(id="other", team_id="alpha"))
    finally:
        await engine.dispose()


# --------------------------- get / set ---------------------------


@pytest.mark.asyncio
async def test_default_team_is_read_with_its_name() -> None:
    rebac = _FakeRebac()

    result = await get_default_team_for_new_users(
        _user(), _team_deps(rebac, _FakeDefaultTeamStore("team-onboarding"))
    )

    assert result == DefaultTeamForNewUsers(
        team_id=TeamId("team-onboarding"), name="Onboarding"
    )
    assert rebac.permission_checks == [OrganizationPermission.CAN_MANAGE_PLATFORM]


@pytest.mark.asyncio
async def test_deleted_default_team_reads_as_unset() -> None:
    deps = _team_deps(_FakeRebac(), _FakeDefaultTeamStore("team-gone"))

    assert await get_default_team_for_new_users(_user(), deps) is None


@pytest.mark.asyncio
async def test_reading_the_default_team_requires_manage_platform() -> None:
    with pytest.raises(AuthorizationError):
        await get_default_team_for_new_users(
            _user(),
            _team_deps(
                _FakeRebac(granted=False), _FakeDefaultTeamStore("team-onboarding")
            ),
        )


@pytest.mark.asyncio
async def test_setting_the_default_team_requires_manage_platform() -> None:
    store = _FakeDefaultTeamStore()

    with pytest.raises(AuthorizationError):
        await set_default_team_for_new_users(
            _user(),
            TeamId("team-onboarding"),
            _team_deps(_FakeRebac(granted=False), store),
        )

    assert store.set_calls == []


@pytest.mark.asyncio
async def test_setting_an_unregistered_team_is_not_found() -> None:
    """Personal spaces land here too: they never have a registry row."""
    store = _FakeDefaultTeamStore()

    with pytest.raises(TeamNotFoundError):
        await set_default_team_for_new_users(
            _user(), TeamId("personal-someone"), _team_deps(_FakeRebac(), store)
        )

    assert store.set_calls == []


@pytest.mark.asyncio
async def test_setting_and_clearing_record_the_admin() -> None:
    store = _FakeDefaultTeamStore()
    deps = _team_deps(_FakeRebac(), store)

    await set_default_team_for_new_users(
        _user("admin-1"), TeamId("team-onboarding"), deps
    )
    await set_default_team_for_new_users(_user("admin-1"), None, deps)

    assert store.set_calls == [("team-onboarding", "admin-1"), (None, "admin-1")]


# --------------------------- join_default_team_for_new_user ---------------------------


@pytest.mark.asyncio
async def test_new_user_joins_the_default_team_as_member() -> None:
    rebac = _FakeRebac()

    await join_default_team_for_new_user(
        "new-user-1", _team_deps(rebac, _FakeDefaultTeamStore("team-onboarding"))
    )

    assert [(r.subject.id, r.relation, r.resource.id) for r in rebac.added] == [
        ("new-user-1", RelationType.TEAM_MEMBER, "team-onboarding")
    ]


@pytest.mark.asyncio
async def test_user_already_holding_a_role_is_left_untouched() -> None:
    existing = Relation(
        subject=RebacReference(Resource.USER, "new-user-1"),
        relation=RelationType.TEAM_ADMIN,
        resource=RebacReference(Resource.TEAM, "team-onboarding"),
    )
    rebac = _FakeRebac(relations=[existing])

    await join_default_team_for_new_user(
        "new-user-1", _team_deps(rebac, _FakeDefaultTeamStore("team-onboarding"))
    )

    assert rebac.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_team_id", [None, "team-gone"])
async def test_no_usable_default_team_grants_nothing(
    stored_team_id: str | None,
) -> None:
    rebac = _FakeRebac()

    await join_default_team_for_new_user(
        "new-user-1", _team_deps(rebac, _FakeDefaultTeamStore(stored_team_id))
    )

    assert rebac.added == []


# --------------------------- POST /gcu ---------------------------


async def _accept_gcu(
    rebac: _FakeRebac, user_store: _FakeUserStore, *, gcu_version: str | None = "v1"
) -> None:
    await validate_gcu(
        deps=_user_deps(gcu_version),
        team_deps=_team_deps(rebac, _FakeDefaultTeamStore("team-onboarding")),
        user=_user(),
        user_store=cast(Any, user_store),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("row_exists", [False, True])
async def test_first_gcu_acceptance_joins_the_default_team(row_exists: bool) -> None:
    """A users row can exist before any acceptance (storage accounting creates one)."""
    rebac = _FakeRebac()
    user_store = _FakeUserStore(row_exists=row_exists, accepted=None)

    await _accept_gcu(rebac, user_store)

    assert len(rebac.added) == 1
    assert user_store.recorded == [GcuVersionsType.V1]


@pytest.mark.asyncio
async def test_accepting_a_newer_gcu_does_not_rejoin_the_default_team() -> None:
    rebac = _FakeRebac()
    user_store = _FakeUserStore(row_exists=True, accepted=GcuVersionsType.V1)

    await _accept_gcu(rebac, user_store)

    assert rebac.added == []
    assert user_store.recorded == [GcuVersionsType.V1]


@pytest.mark.asyncio
async def test_deployment_without_gcu_never_joins_the_default_team() -> None:
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
