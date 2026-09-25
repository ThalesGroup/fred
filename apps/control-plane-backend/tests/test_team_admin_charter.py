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

"""Team administrator charter: a nominated admin holds `pending_team_admin`
until they accept the configured charter version, then `team_admin`."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import fred_core
import pytest
from control_plane_backend.models.base import Base
from control_plane_backend.models.team_admin_charter_models import (
    TeamAdminCharterAcceptanceRow,
    TeamAdminCharterStateRow,
)
from control_plane_backend.teams import service as team_service
from control_plane_backend.teams.admin_charter_store import TeamAdminCharterStore
from control_plane_backend.teams.api import register_exception_handlers
from control_plane_backend.teams.schemas import (
    AddTeamMemberRequest,
    GrantTeamMemberRoleRequest,
    TeamAdminCharterDisabledError,
    UserTeamRelation,
)
from control_plane_backend.teams.service import (
    _fold_team_role_relations,
    _get_administer_permission_for_team_role_relation,
    _remove_all_team_member_relations,
    accept_team_admin_charter,
    add_team_member,
    get_team_admin_charter_acceptance,
    grant_team_member_role,
    reconcile_team_admin_charter_roles,
    resolve_granted_team_relation,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_core import (
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
)
from fred_core.common import TeamId
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

_VERSION = "2026-09"
_ADMIN = RelationType.TEAM_ADMIN.value
_PENDING = RelationType.PENDING_TEAM_ADMIN.value


class _FakeRebac:
    """Direct tuples only: (user_id, relation, team_id). The acting user is
    authorized for every administer permission."""

    enabled = True

    def __init__(self, tuples: set[tuple[str, str, str]] | None = None) -> None:
        self.tuples = set(tuples or set())

    @staticmethod
    def _key(rel: Relation) -> tuple[str, str, str]:
        return (rel.subject.id, rel.relation.value, rel.resource.id)

    async def add_relation(self, relation: Relation, **_kwargs: object) -> None:
        self.tuples.add(self._key(relation))

    async def delete_relation(self, relation: Relation) -> None:
        self.tuples.discard(self._key(relation))

    async def delete_relations(self, relations) -> None:
        for relation in relations:
            self.tuples.discard(self._key(relation))

    async def check_permission_or_raise(self, subject, permission, resource, **kwargs):
        # Existing role/charter cases operate on previously admitted organization members.
        assert resource.type == Resource.ORGANIZATION

    async def check_user_team_permissions_or_raise(self, **_kwargs: object) -> str:
        return "token"

    async def lookup_resources(self, subject, permission, resource_type, **_kwargs):
        return [
            RebacReference(Resource.TEAM, team)
            for user, relation, team in sorted(self.tuples)
            if user == subject.id and relation == permission.value
        ]

    async def list_direct_relations(self, resource, **_kwargs):
        return [
            Relation(
                subject=RebacReference(Resource.USER, user),
                relation=RelationType(relation),
                resource=RebacReference(Resource.TEAM, team),
            )
            for user, relation, team in sorted(self.tuples)
            if team == resource.id
        ]


class _FakeCharterStore:
    def __init__(
        self,
        accepted: set[tuple[str, str]] | None = None,
        applied: str | None = None,
    ) -> None:
        self.accepted = {key: datetime.now(timezone.utc) for key in accepted or set()}
        self.applied = applied

    async def get_accepted_at(self, user_id: str, version: str) -> datetime | None:
        return self.accepted.get((user_id, version))

    async def list_accepting_user_ids(self, version: str) -> set[str]:
        return {user for user, accepted in self.accepted if accepted == version}

    async def accept(self, user_id: str, version: str) -> tuple[datetime, bool]:
        existing = self.accepted.get((user_id, version))
        if existing is not None:
            return existing, False
        self.accepted[(user_id, version)] = datetime.now(timezone.utc)
        return self.accepted[(user_id, version)], True

    async def get_applied_version(self) -> str | None:
        return self.applied

    async def set_applied_version(self, version: str) -> None:
        self.applied = version


class _FakeMetadataStore:
    def __init__(self, team_ids: list[str]) -> None:
        self.team_ids = team_ids
        self.listed = 0

    async def get_by_team_id(self, team_id):
        return SimpleNamespace(id=team_id, organization_id="fred")

    async def list_all(self):
        self.listed += 1
        return [SimpleNamespace(id=TeamId(team_id)) for team_id in self.team_ids]

    @asynccontextmanager
    async def advisory_lock(self, _key: str):
        yield


def _deps(
    rebac: _FakeRebac,
    store: _FakeCharterStore,
    *,
    version: str | None = _VERSION,
    teams: list[str] | None = None,
) -> Any:
    metadata_store = _FakeMetadataStore(teams or ["team-a", "team-b"])
    return cast(
        Any,
        SimpleNamespace(
            configuration=SimpleNamespace(
                app=SimpleNamespace(team_admin_charter_version=version)
            ),
            rebac=rebac,
            get_team_metadata_store=lambda: metadata_store,
            get_team_admin_charter_store=lambda: store,
        ),
    )


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[], email=None)


# --------------------------- nomination ---------------------------


@pytest.mark.asyncio
async def test_nominating_an_admin_who_has_not_accepted_writes_pending() -> None:
    rebac = _FakeRebac()
    deps = _deps(rebac, _FakeCharterStore())

    await add_team_member(
        _user("owner"),
        TeamId("team-a"),
        AddTeamMemberRequest(user_id="nominee", relation=UserTeamRelation.TEAM_ADMIN),
        deps,
    )

    assert rebac.tuples == {("nominee", _PENDING, "team-a")}


@pytest.mark.asyncio
async def test_nominating_an_admin_who_accepted_writes_team_admin() -> None:
    rebac = _FakeRebac()
    deps = _deps(rebac, _FakeCharterStore({("nominee", _VERSION)}))

    await grant_team_member_role(
        _user("owner"),
        TeamId("team-a"),
        "nominee",
        GrantTeamMemberRoleRequest(relation=UserTeamRelation.TEAM_ADMIN),
        deps,
    )

    assert rebac.tuples == {("nominee", _ADMIN, "team-a")}


@pytest.mark.asyncio
async def test_without_a_charter_nominations_write_team_admin() -> None:
    rebac = _FakeRebac()
    deps = _deps(rebac, _FakeCharterStore(), version=None)

    await grant_team_member_role(
        _user("owner"),
        TeamId("team-a"),
        "nominee",
        GrantTeamMemberRoleRequest(relation=UserTeamRelation.TEAM_ADMIN),
        deps,
    )

    assert rebac.tuples == {("nominee", _ADMIN, "team-a")}


@pytest.mark.asyncio
async def test_other_roles_are_written_as_requested() -> None:
    rebac = _FakeRebac()
    deps = _deps(rebac, _FakeCharterStore())

    await grant_team_member_role(
        _user("owner"),
        TeamId("team-a"),
        "editor",
        GrantTeamMemberRoleRequest(relation=UserTeamRelation.TEAM_EDITOR),
        deps,
    )

    assert rebac.tuples == {("editor", RelationType.TEAM_EDITOR.value, "team-a")}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accepted", "version", "expected"),
    [
        (set(), _VERSION, UserTeamRelation.PENDING_TEAM_ADMIN),
        ({("nominee", _VERSION)}, _VERSION, UserTeamRelation.TEAM_ADMIN),
        (set(), None, UserTeamRelation.TEAM_ADMIN),
    ],
)
async def test_an_imported_pending_nomination_is_resolved_again(
    accepted: set[tuple[str, str]],
    version: str | None,
    expected: UserTeamRelation,
) -> None:
    deps = _deps(_FakeRebac(), _FakeCharterStore(accepted), version=version)

    resolved = await resolve_granted_team_relation(
        "nominee", UserTeamRelation.PENDING_TEAM_ADMIN, deps
    )

    assert resolved == expected


def test_pending_team_admin_cannot_be_granted_directly() -> None:
    with pytest.raises(ValidationError):
        GrantTeamMemberRoleRequest(relation=UserTeamRelation.PENDING_TEAM_ADMIN)
    with pytest.raises(ValidationError):
        AddTeamMemberRequest(
            user_id="nominee", relation=UserTeamRelation.PENDING_TEAM_ADMIN
        )


def test_cancelling_a_nomination_needs_can_administer_admins() -> None:
    assert (
        _get_administer_permission_for_team_role_relation(
            UserTeamRelation.PENDING_TEAM_ADMIN
        )
        == TeamPermission.CAN_ADMINISTER_ADMINS
    )


@pytest.mark.asyncio
async def test_removing_a_member_also_removes_a_pending_nomination() -> None:
    rebac = _FakeRebac(
        {("nominee", _PENDING, "team-a"), ("nominee", "team_member", "team-a")}
    )

    await _remove_all_team_member_relations(
        cast(Any, rebac), TeamId("team-a"), "nominee"
    )

    assert rebac.tuples == set()


@pytest.mark.asyncio
async def test_pending_nominations_are_part_of_the_folded_roles() -> None:
    rebac = _FakeRebac({("nominee", _PENDING, "team-a")})

    relations = await rebac.list_direct_relations(
        RebacReference(Resource.TEAM, "team-a")
    )

    assert _fold_team_role_relations(relations) == {
        "nominee": {UserTeamRelation.PENDING_TEAM_ADMIN}
    }


# --------------------------- acceptance ---------------------------


@pytest.mark.asyncio
async def test_accepting_promotes_every_pending_team_and_audits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audited: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        team_service,
        "emit_audit_log",
        lambda event, **fields: audited.append((event, fields)),
    )
    rebac = _FakeRebac(
        {
            ("nominee", _PENDING, "team-a"),
            ("nominee", _PENDING, "team-b"),
            ("other", _PENDING, "team-a"),
        }
    )
    deps = _deps(rebac, _FakeCharterStore())

    first = await accept_team_admin_charter(_user("nominee"), deps)
    second = await accept_team_admin_charter(_user("nominee"), deps)

    assert rebac.tuples == {
        ("nominee", _ADMIN, "team-a"),
        ("nominee", _ADMIN, "team-b"),
        ("other", _PENDING, "team-a"),
    }
    assert second.accepted_at == first.accepted_at
    assert audited == [
        (
            "team_admin.charter.accepted",
            {"actor_uid": "nominee", "charter_version": _VERSION},
        )
    ]


@pytest.mark.asyncio
async def test_reading_the_acceptance_returns_its_time_for_the_configured_version() -> (
    None
):
    store = _FakeCharterStore({("admin", _VERSION), ("former", "2025-01")})
    deps = _deps(_FakeRebac(), store)

    accepted = await get_team_admin_charter_acceptance(_user("admin"), deps)

    assert accepted is not None
    assert accepted.accepted_at == store.accepted[("admin", _VERSION)]
    assert await get_team_admin_charter_acceptance(_user("former"), deps) is None
    charter_off = _deps(_FakeRebac(), store, version=None)
    assert await get_team_admin_charter_acceptance(_user("admin"), charter_off) is None


@pytest.mark.asyncio
async def test_accepting_without_a_version_is_refused() -> None:
    store = _FakeCharterStore()
    deps = _deps(_FakeRebac(), store, version=None)

    with pytest.raises(TeamAdminCharterDisabledError):
        await accept_team_admin_charter(_user("nominee"), deps)
    assert store.accepted == {}


def test_accepting_without_a_version_maps_to_409() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/disabled")
    async def _disabled() -> None:
        raise TeamAdminCharterDisabledError()

    response = TestClient(app).get("/disabled")

    assert (response.status_code, response.json()) == (
        409,
        {"detail": "team_admin_charter_disabled"},
    )


# --------------------------- reconciliation ---------------------------


@pytest.mark.asyncio
async def test_enabling_the_charter_demotes_admins_who_have_not_accepted() -> None:
    rebac = _FakeRebac({("accepted", _ADMIN, "team-a"), ("unaware", _ADMIN, "team-a")})
    store = _FakeCharterStore({("accepted", _VERSION)})

    moved = await reconcile_team_admin_charter_roles(_deps(rebac, store))

    assert moved == 1
    assert rebac.tuples == {
        ("accepted", _ADMIN, "team-a"),
        ("unaware", _PENDING, "team-a"),
    }
    assert store.applied == _VERSION


@pytest.mark.asyncio
async def test_a_new_version_promotes_pending_admins_who_already_accepted_it() -> None:
    rebac = _FakeRebac({("ready", _PENDING, "team-b")})
    store = _FakeCharterStore({("ready", "2027-01")}, applied=_VERSION)

    await reconcile_team_admin_charter_roles(_deps(rebac, store, version="2027-01"))

    assert rebac.tuples == {("ready", _ADMIN, "team-b")}


@pytest.mark.asyncio
async def test_turning_the_charter_off_promotes_every_pending_admin() -> None:
    rebac = _FakeRebac({("nominee", _PENDING, "team-a")})
    store = _FakeCharterStore(applied=_VERSION)

    await reconcile_team_admin_charter_roles(_deps(rebac, store, version=None))

    assert rebac.tuples == {("nominee", _ADMIN, "team-a")}
    assert store.applied == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("applied", "version"), [(_VERSION, _VERSION), (None, None), ("", None)]
)
async def test_reconciliation_does_nothing_when_the_version_is_unchanged(
    applied: str | None, version: str | None
) -> None:
    rebac = _FakeRebac({("unaware", _ADMIN, "team-a")})
    deps = _deps(rebac, _FakeCharterStore(applied=applied), version=version)

    assert await reconcile_team_admin_charter_roles(deps) == 0
    assert rebac.tuples == {("unaware", _ADMIN, "team-a")}
    assert deps.get_team_metadata_store().listed == 0


# --------------------------- model ---------------------------


def test_a_pending_admin_is_a_member_and_nothing_more() -> None:
    schema = (
        Path(fred_core.__file__).parent / "security" / "rebac" / "schema.fga"
    ).read_text()
    team_block = schema.split("type team", 1)[1].split("\ntype ", 1)[0]
    definitions = re.findall(r"^\s*define (\w+): (.+)$", team_block, re.M)

    uses = [name for name, rule in definitions if "pending_team_admin" in rule]

    assert uses == ["team_member"]


# --------------------------- store ---------------------------


@pytest.mark.asyncio
async def test_store_records_acceptances_and_the_applied_version(
    tmp_path: Path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'charter.db'}")
    try:
        async with engine.begin() as connection:
            for row in (TeamAdminCharterAcceptanceRow, TeamAdminCharterStateRow):
                await connection.run_sync(
                    Base.metadata.tables[row.__tablename__].create
                )
        store = TeamAdminCharterStore(engine)

        first_at, first_inserted = await store.accept("admin", _VERSION)
        again_at, again_inserted = await store.accept("admin", _VERSION)
        await store.accept("other", "2027-01")

        assert (first_inserted, again_inserted) == (True, False)
        assert again_at == await store.get_accepted_at("admin", _VERSION)
        assert await store.list_accepting_user_ids(_VERSION) == {"admin"}
        assert first_at is not None

        assert await store.get_applied_version() is None
        await store.set_applied_version(_VERSION)
        await store.set_applied_version("")
        assert await store.get_applied_version() == ""
    finally:
        await engine.dispose()
