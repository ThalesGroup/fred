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

"""Platform admin edit of a team's registry entry (`PATCH /teams/{id}/registry`)."""

from __future__ import annotations

from typing import Any, cast

import pytest
from control_plane_backend.teams.schemas import (
    EditTeamRegistryRequest,
    TeamAdminConstraintError,
    TeamAlreadyExistsError,
    TeamNotFoundError,
    TeamWithPermissions,
)
from control_plane_backend.teams.service import (
    _bulk_team_membership,
    edit_team_registry,
)
from fred_core import (
    AuthorizationError,
    OrganizationPermission,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from test_team_registry_governance import (
    _TEAM_MANAGER_GRANTS,
    _deps,
    _FakeMetadataStore,
    _FakeRebac,
    _stub_team_projection,
    _team_manager,
    _user,
)

DESCRIPTION = "Builds the internal tooling of the platform team."


class _RosterRebac(_FakeRebac):
    """Keeps one team's role tuples so admin diffs can be asserted end to end."""

    def __init__(self, roles: dict[str, set[RelationType]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.roles = roles

    async def lookup_subjects(self, resource, relation, subject_type, **kwargs):
        return [
            RebacReference(Resource.USER, uid)
            for uid, held in self.roles.items()
            if relation in held
        ]

    async def list_direct_relations(self, resource, subject=None, **kwargs):
        return [
            Relation(
                subject=RebacReference(Resource.USER, uid),
                relation=r,
                resource=resource,
            )
            for uid, held in self.roles.items()
            if subject is None or subject.id == uid
            for r in held
        ]

    async def add_relation(self, relation: Relation, **kwargs: object):
        await super().add_relation(relation)
        self.roles.setdefault(relation.subject.id, set()).add(relation.relation)

    async def delete_relations(self, relations, **kwargs: object):
        for relation in relations:
            self.roles.get(relation.subject.id, set()).discard(relation.relation)


class _CharterStore:
    def __init__(self, accepted: set[str]) -> None:
        self.accepted = accepted

    async def get_accepted_at(self, user_id: str, version: str):
        return "2026-10-16" if user_id in self.accepted else None


def _store(**kwargs: Any) -> _FakeMetadataStore:
    return _FakeMetadataStore(
        {
            "t1": TeamMetadata(
                id=TeamId("t1"), name="Northbridge", description=DESCRIPTION
            ),
            "t2": TeamMetadata(
                id=TeamId("t2"), name="Southbridge", description=DESCRIPTION
            ),
        },
        **kwargs,
    )


def _charter_deps(rebac: _FakeRebac, store: _FakeMetadataStore, accepted: set[str]):
    deps = _deps(rebac, store)
    deps.configuration.app.team_admin_charter_version = "v1"
    object.__setattr__(
        deps, "get_team_admin_charter_store", lambda: _CharterStore(accepted)
    )
    return deps


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "control_plane_backend.teams.service.emit_audit_log",
        lambda name, **fields: events.append((name, fields)),
    )
    return events


@pytest.mark.asyncio
async def test_platform_admin_edits_name_description_and_admins(
    monkeypatch: pytest.MonkeyPatch, audit: list
) -> None:
    rebac = _RosterRebac(
        {"alice": {RelationType.TEAM_ADMIN}, "bob": {RelationType.TEAM_ADMIN}}
    )
    store = _store()
    _stub_team_projection(monkeypatch)

    team = await edit_team_registry(
        _user(),
        TeamId("t1"),
        EditTeamRegistryRequest(
            name=" Eastbridge ",
            description="  Runs the evaluation campaigns of every product.  ",
            add_admin_ids=["carol"],
            remove_admin_ids=["bob"],
        ),
        _deps(rebac, store),
    )

    assert team.name == "Eastbridge"
    assert (
        store.teams["t1"].description
        == "Runs the evaluation campaigns of every product."
    )
    assert rebac.permission_checks == [OrganizationPermission.CAN_EDIT_TEAM_REGISTRY]
    assert rebac.roles["carol"] == {RelationType.TEAM_ADMIN}
    # A removed admin stays in the team as a plain member.
    assert rebac.roles["bob"] == {RelationType.TEAM_MEMBER}
    assert store.advisory_lock_keys == ["team_member_roles:t1"]
    assert audit == [
        (
            "team.registry.edited",
            {
                "actor_uid": "platform-admin-1",
                "team_id": "t1",
                "changed_fields": ["description", "name"],
                "admins_added": ["carol"],
                "admins_removed": ["bob"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_removed_admin_keeps_their_other_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _RosterRebac(
        {
            "alice": {RelationType.TEAM_ADMIN},
            "bob": {RelationType.TEAM_ADMIN, RelationType.TEAM_EDITOR},
        }
    )
    _stub_team_projection(monkeypatch)

    await edit_team_registry(
        _user(),
        TeamId("t1"),
        EditTeamRegistryRequest(remove_admin_ids=["bob"]),
        _deps(rebac, _store()),
    )

    assert rebac.roles["bob"] == {RelationType.TEAM_EDITOR}


@pytest.mark.asyncio
async def test_team_manager_cannot_edit_a_team(audit: list) -> None:
    rebac = _RosterRebac(
        {"alice": {RelationType.TEAM_ADMIN}}, granted=_TEAM_MANAGER_GRANTS
    )
    store = _store()

    with pytest.raises(AuthorizationError):
        await edit_team_registry(
            _team_manager(),
            TeamId("t1"),
            EditTeamRegistryRequest(name="Mine", add_admin_ids=["team-manager-1"]),
            _deps(rebac, store),
        )

    with pytest.raises(AuthorizationError):
        await edit_team_registry(
            _team_manager(),
            TeamId("t1"),
            EditTeamRegistryRequest(name="Mine"),
            _deps(rebac, store),
        )

    assert store.teams["t1"].name == "Northbridge"
    assert rebac.added_relations == []
    assert audit == []


@pytest.mark.asyncio
async def test_unknown_team_or_personal_space_is_not_found() -> None:
    rebac = _RosterRebac({})

    with pytest.raises(TeamNotFoundError):
        await edit_team_registry(
            _user(),
            TeamId("personal-alice"),
            EditTeamRegistryRequest(name="X"),
            _deps(rebac, _store()),
        )


@pytest.mark.asyncio
async def test_name_taken_changes_nothing(audit: list) -> None:
    rebac = _RosterRebac({"alice": {RelationType.TEAM_ADMIN}})
    store = _store()

    with pytest.raises(TeamAlreadyExistsError) as refused:
        await edit_team_registry(
            _user(),
            TeamId("t1"),
            EditTeamRegistryRequest(name="Southbridge", add_admin_ids=["carol"]),
            _deps(rebac, store),
        )

    assert refused.value.code == "team_name_taken"

    assert store.teams["t1"].name == "Northbridge"
    assert rebac.added_relations == []
    assert audit == []


@pytest.mark.asyncio
async def test_rename_race_is_a_conflict() -> None:
    rebac = _RosterRebac({"alice": {RelationType.TEAM_ADMIN}})
    store = _store(
        upsert_raises=IntegrityError("UPDATE", {}, Exception("duplicate key"))
    )

    with pytest.raises(TeamAlreadyExistsError):
        await edit_team_registry(
            _user(),
            TeamId("t1"),
            EditTeamRegistryRequest(name="Westbridge"),
            _deps(rebac, store),
        )


@pytest.mark.asyncio
async def test_rename_race_still_audits_the_admin_changes(audit: list) -> None:
    rebac = _RosterRebac({"alice": {RelationType.TEAM_ADMIN}})
    store = _store(
        upsert_raises=IntegrityError("UPDATE", {}, Exception("duplicate key"))
    )

    with pytest.raises(TeamAlreadyExistsError):
        await edit_team_registry(
            _user(),
            TeamId("t1"),
            EditTeamRegistryRequest(name="Westbridge", add_admin_ids=["carol"]),
            _deps(rebac, store),
        )

    assert rebac.roles["carol"] == {RelationType.TEAM_ADMIN}
    assert audit == [
        (
            "team.registry.edited",
            {
                "actor_uid": "platform-admin-1",
                "team_id": "t1",
                "changed_fields": [],
                "admins_added": ["carol"],
                "admins_removed": [],
            },
        )
    ]


@pytest.mark.asyncio
async def test_removing_the_last_admin_is_refused(audit: list) -> None:
    rebac = _RosterRebac({"alice": {RelationType.TEAM_ADMIN}})
    store = _store()

    with pytest.raises(
        TeamAdminConstraintError, match="at least one team_admin"
    ) as refused:
        await edit_team_registry(
            _user(),
            TeamId("t1"),
            EditTeamRegistryRequest(description="A" * 30, remove_admin_ids=["alice"]),
            _deps(rebac, store),
        )

    assert refused.value.code == "team_last_admin"

    assert rebac.roles == {"alice": {RelationType.TEAM_ADMIN}}
    assert store.teams["t1"].description == DESCRIPTION
    assert audit == []


@pytest.mark.asyncio
async def test_replacing_the_only_admin_by_a_pending_nominee_is_refused() -> None:
    rebac = _RosterRebac({"alice": {RelationType.TEAM_ADMIN}})

    with pytest.raises(TeamAdminConstraintError, match="charter") as refused:
        await edit_team_registry(
            _user(),
            TeamId("t1"),
            EditTeamRegistryRequest(
                add_admin_ids=["carol"], remove_admin_ids=["alice"]
            ),
            _charter_deps(rebac, _store(), accepted=set()),
        )

    assert refused.value.code == "team_admin_pending_charter"
    assert rebac.roles == {"alice": {RelationType.TEAM_ADMIN}}


@pytest.mark.asyncio
async def test_added_admin_waits_for_the_charter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _RosterRebac({"alice": {RelationType.TEAM_ADMIN}})
    _stub_team_projection(monkeypatch)

    await edit_team_registry(
        _user(),
        TeamId("t1"),
        EditTeamRegistryRequest(add_admin_ids=["carol", "dave"]),
        _charter_deps(rebac, _store(), accepted={"dave"}),
    )

    assert rebac.roles["carol"] == {RelationType.PENDING_TEAM_ADMIN}
    assert rebac.roles["dave"] == {RelationType.TEAM_ADMIN}


@pytest.mark.asyncio
async def test_a_platform_admin_may_remove_themselves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _RosterRebac(
        {
            "platform-admin-1": {RelationType.TEAM_ADMIN},
            "alice": {RelationType.TEAM_ADMIN},
        }
    )
    _stub_team_projection(monkeypatch)

    await edit_team_registry(
        _user(),
        TeamId("t1"),
        EditTeamRegistryRequest(remove_admin_ids=["platform-admin-1"]),
        _deps(rebac, _store()),
    )

    assert rebac.roles["platform-admin-1"] == {RelationType.TEAM_MEMBER}


@pytest.mark.asyncio
async def test_unchanged_fields_write_nothing(
    monkeypatch: pytest.MonkeyPatch, audit: list
) -> None:
    rebac = _RosterRebac({"alice": {RelationType.TEAM_ADMIN}})
    _stub_team_projection(monkeypatch)

    await edit_team_registry(
        _user(),
        TeamId("t1"),
        EditTeamRegistryRequest(name="Northbridge", description=DESCRIPTION),
        _deps(rebac, _store()),
    )

    assert audit == []


@pytest.mark.parametrize(
    "body",
    [
        {"description": None},
        {"description": "Too short"},
        {"name": "   "},
        {"add_admin_ids": ["bob"], "remove_admin_ids": ["bob"]},
    ],
)
def test_request_refuses_invalid_bodies(body: dict) -> None:
    with pytest.raises(ValidationError):
        EditTeamRegistryRequest.model_validate(body)


@pytest.mark.asyncio
async def test_route_returns_the_updated_team(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    seen: list[EditTeamRegistryRequest] = []

    async def _edit(_user, team_id, request, _deps) -> TeamWithPermissions:
        seen.append(request)
        return TeamWithPermissions(id=team_id, name="Eastbridge")

    monkeypatch.setattr(
        "control_plane_backend.teams.api.edit_team_registry_from_service", _edit
    )
    from control_plane_backend.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/control-plane/v1/teams/t1/registry",
            json={"name": "Eastbridge", "add_admin_ids": ["carol"]},
        )
        refused = await client.patch(
            "/control-plane/v1/teams/t1/registry", json={"description": "Too short"}
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Eastbridge"
    assert seen[0].add_admin_ids == ["carol"]
    assert refused.status_code == 422
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_refusals_carry_a_stable_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    refusals = iter(
        [
            TeamAlreadyExistsError("Southbridge"),
            TeamAdminConstraintError("No admin left."),
            TeamAdminConstraintError("Pending.", code="team_admin_pending_charter"),
        ]
    )

    async def _edit(*_args) -> TeamWithPermissions:
        raise next(refusals)

    monkeypatch.setattr(
        "control_plane_backend.teams.api.edit_team_registry_from_service", _edit
    )
    from control_plane_backend.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        responses = [
            await client.patch("/control-plane/v1/teams/t1/registry", json={})
            for _ in range(3)
        ]

    assert [r.status_code for r in responses] == [409, 409, 409]
    assert [r.json()["code"] for r in responses] == [
        "team_name_taken",
        "team_last_admin",
        "team_admin_pending_charter",
    ]
    assert responses[0].json()["detail"] == "Team 'Southbridge' already exists."


@pytest.mark.asyncio
async def test_listing_flags_admins_awaiting_the_charter() -> None:
    rebac = _RosterRebac(
        {
            "alice": {RelationType.TEAM_ADMIN},
            "carol": {RelationType.PENDING_TEAM_ADMIN},
            "bob": {RelationType.TEAM_MEMBER},
        }
    )

    admins, _members, _mine, pending = await _bulk_team_membership(
        cast(Any, rebac), [TeamId("t-pending")], "alice"
    )

    assert admins[TeamId("t-pending")] == {"alice", "carol"}
    assert pending[TeamId("t-pending")] == {"carol"}
