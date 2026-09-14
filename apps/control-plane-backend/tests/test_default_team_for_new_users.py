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

"""Default team for new users: at most one team, joined on first GCU acceptance.

Contract: CONTROL-PLANE-PRODUCT-CONTRACT.md §52.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from control_plane_backend.teams.schemas import TeamNotFoundError
from control_plane_backend.teams.service import (
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
from fred_core.models import Base as CoreBase
from fred_core.teams.metadata_store import TeamMetadata, TeamMetadataStore
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_DEFAULT_TEAM = TeamMetadata(
    id=TeamId("team-onboarding"), name="Onboarding", is_default_for_new_users=True
)


async def _sqlite_store(tmp_path: Path) -> tuple[AsyncEngine, TeamMetadataStore]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'teams.sqlite3'}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
    return engine, TeamMetadataStore(engine)


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


class _FakeTeamStore:
    def __init__(
        self,
        *,
        default: TeamMetadata | None = None,
        known_ids: set[str] | None = None,
    ) -> None:
        self.default = default
        self.known_ids = known_ids or set()
        self.set_calls: list[TeamId | None] = []

    async def get_default_for_new_users(self) -> TeamMetadata | None:
        return self.default

    async def set_default_for_new_users(self, team_id: TeamId | None) -> bool:
        if team_id is not None and str(team_id) not in self.known_ids:
            return False
        self.set_calls.append(team_id)
        return True


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


def _team_deps(rebac: _FakeRebac, store: _FakeTeamStore) -> Any:
    return cast(
        Any, SimpleNamespace(rebac=rebac, get_team_metadata_store=lambda: store)
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
async def test_store_keeps_at_most_one_default_team(tmp_path: Path) -> None:
    engine, store = await _sqlite_store(tmp_path)
    try:
        await store.create(TeamId("alpha"), "Alpha")
        await store.create(TeamId("beta"), "Beta")
        assert await store.get_default_for_new_users() is None

        assert await store.set_default_for_new_users(TeamId("alpha"))
        assert await store.set_default_for_new_users(TeamId("beta"))
        flagged = [t.id for t in await store.list_all() if t.is_default_for_new_users]
        assert flagged == ["beta"]

        assert await store.set_default_for_new_users(None)
        assert await store.get_default_for_new_users() is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_store_unknown_team_keeps_the_current_default(tmp_path: Path) -> None:
    engine, store = await _sqlite_store(tmp_path)
    try:
        await store.create(TeamId("alpha"), "Alpha")
        await store.set_default_for_new_users(TeamId("alpha"))

        assert not await store.set_default_for_new_users(TeamId("missing"))
        default = await store.get_default_for_new_users()
        assert default is not None and default.id == "alpha"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleting_the_default_team_clears_the_setting(tmp_path: Path) -> None:
    engine, store = await _sqlite_store(tmp_path)
    try:
        await store.create(TeamId("alpha"), "Alpha")
        await store.set_default_for_new_users(TeamId("alpha"))
        await store.delete(TeamId("alpha"))
        assert await store.get_default_for_new_users() is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_database_refuses_a_second_default_team(tmp_path: Path) -> None:
    engine, store = await _sqlite_store(tmp_path)
    try:
        await store.create(TeamId("alpha"), "Alpha")
        await store.create(TeamId("beta"), "Beta")
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    update(TeamMetadataRow).values(is_default_for_new_users=True)
                )
    finally:
        await engine.dispose()


# --------------------------- set_default_team_for_new_users ---------------------------


@pytest.mark.asyncio
async def test_setting_the_default_team_requires_manage_platform() -> None:
    rebac = _FakeRebac(granted=False)
    store = _FakeTeamStore(known_ids={"alpha"})

    with pytest.raises(AuthorizationError):
        await set_default_team_for_new_users(
            _user(), TeamId("alpha"), _team_deps(rebac, store)
        )

    assert rebac.permission_checks == [OrganizationPermission.CAN_MANAGE_PLATFORM]
    assert store.set_calls == []


@pytest.mark.asyncio
async def test_setting_an_unregistered_team_is_not_found() -> None:
    """Personal spaces land here too: they never have a registry row."""
    store = _FakeTeamStore(known_ids={"alpha"})

    with pytest.raises(TeamNotFoundError):
        await set_default_team_for_new_users(
            _user(), TeamId("personal-someone"), _team_deps(_FakeRebac(), store)
        )


@pytest.mark.asyncio
async def test_clearing_the_default_team() -> None:
    store = _FakeTeamStore()

    await set_default_team_for_new_users(_user(), None, _team_deps(_FakeRebac(), store))

    assert store.set_calls == [None]


# --------------------------- join_default_team_for_new_user ---------------------------


@pytest.mark.asyncio
async def test_new_user_joins_the_default_team_as_member() -> None:
    rebac = _FakeRebac()

    await join_default_team_for_new_user(
        "new-user-1", _team_deps(rebac, _FakeTeamStore(default=_DEFAULT_TEAM))
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
        "new-user-1", _team_deps(rebac, _FakeTeamStore(default=_DEFAULT_TEAM))
    )

    assert rebac.added == []


@pytest.mark.asyncio
async def test_no_default_team_grants_nothing() -> None:
    rebac = _FakeRebac()

    await join_default_team_for_new_user(
        "new-user-1", _team_deps(rebac, _FakeTeamStore())
    )

    assert rebac.added == []


# --------------------------- POST /gcu ---------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("row_exists", [False, True])
async def test_first_gcu_acceptance_joins_the_default_team(row_exists: bool) -> None:
    """A users row can exist before any acceptance (storage accounting creates one)."""
    rebac = _FakeRebac()
    user_store = _FakeUserStore(row_exists=row_exists, accepted=None)

    await validate_gcu(
        deps=_user_deps("v1"),
        team_deps=_team_deps(rebac, _FakeTeamStore(default=_DEFAULT_TEAM)),
        user=_user(),
        user_store=cast(Any, user_store),
    )

    assert len(rebac.added) == 1
    assert user_store.recorded == [GcuVersionsType.V1]


@pytest.mark.asyncio
async def test_accepting_a_newer_gcu_does_not_rejoin_the_default_team() -> None:
    rebac = _FakeRebac()
    user_store = _FakeUserStore(row_exists=True, accepted=GcuVersionsType.V1)

    await validate_gcu(
        deps=_user_deps("v1"),
        team_deps=_team_deps(rebac, _FakeTeamStore(default=_DEFAULT_TEAM)),
        user=_user(),
        user_store=cast(Any, user_store),
    )

    assert rebac.added == []
    assert user_store.recorded == [GcuVersionsType.V1]


@pytest.mark.asyncio
async def test_deployment_without_gcu_never_joins_the_default_team() -> None:
    rebac = _FakeRebac()
    user_store = _FakeUserStore(row_exists=False, accepted=None)

    await validate_gcu(
        deps=_user_deps(None),
        team_deps=_team_deps(rebac, _FakeTeamStore(default=_DEFAULT_TEAM)),
        user=_user(),
        user_store=cast(Any, user_store),
    )

    assert rebac.added == []
    assert user_store.recorded == []


@pytest.mark.asyncio
async def test_failed_grant_does_not_record_the_acceptance() -> None:
    """The retry must still count as a first acceptance."""
    rebac = _FakeRebac(add_raises=RuntimeError("openfga unavailable"))
    user_store = _FakeUserStore(row_exists=False, accepted=None)

    with pytest.raises(RuntimeError, match="openfga unavailable"):
        await validate_gcu(
            deps=_user_deps("v1"),
            team_deps=_team_deps(rebac, _FakeTeamStore(default=_DEFAULT_TEAM)),
            user=_user(),
            user_store=cast(Any, user_store),
        )

    assert user_store.recorded == []
