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

"""AUTHZ-06 (RFC Part 7 §33-39): cumulative team roles.

A member may hold `team_admin`, `team_editor`, and `team_analyst` on the same
team simultaneously — granted and revoked one role at a time, never a bulk
role-set replace, each independently permission-checked exactly like the
single-role model it replaces. These tests lock in the grant/revoke
primitives directly (no HTTP layer) so the invariants are unambiguous:
- granting adds without disturbing any role already held;
- revoking removes only the named role;
- revoking a role not held, or a member's only remaining role, is refused;
- the "team must keep at least one team_admin" guard fires exactly when
  `team_admin` is the role being taken away, whether by a single-role revoke
  or a full member removal.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from control_plane_backend.teams.schemas import (
    GrantTeamMemberRoleRequest,
    TeamAdminConstraintError,
    TeamMemberLastRoleError,
    TeamMemberRoleNotHeldError,
    UserTeamRelation,
)
from control_plane_backend.teams.service import (
    grant_team_member_role,
    list_team_members_unfiltered,
    remove_team_member,
    revoke_team_member_role,
)
from fred_core import (
    KeycloakUser,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
)
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata


class _FakeRebac:
    """In-memory role store: user_id -> the set of roles they hold on the one
    team these tests use. `add_relation`/`delete_relations` mutate it exactly
    like real OpenFGA tuple writes/deletes would."""

    def __init__(
        self, *, roles: dict[str, set[UserTeamRelation]] | None = None
    ) -> None:
        self.roles: dict[str, set[UserTeamRelation]] = {
            uid: set(held) for uid, held in (roles or {}).items()
        }
        self.team_permission_checks: list[tuple[str, tuple[TeamPermission, ...]]] = []
        self.added_relations: list[Relation] = []
        self.deleted_relations: list[Relation] = []

    async def check_user_team_permissions_or_raise(
        self, *, user, team_id, permissions
    ) -> str | None:
        self.team_permission_checks.append((str(team_id), tuple(permissions)))
        return "consistency-token"

    async def lookup_subjects(
        self, resource, relation: RelationType, subject_type, **kwargs
    ):
        # `team_member: [user] or team_admin or team_editor or team_analyst`
        # (schema.fga) — mirror the union so a `TEAM_MEMBER` lookup also
        # returns anyone holding an elevated role, exactly like real OpenFGA.
        if relation.value == RelationType.TEAM_MEMBER.value:
            return [
                RebacReference(Resource.USER, uid)
                for uid, held in self.roles.items()
                if held
            ]
        return [
            RebacReference(Resource.USER, uid)
            for uid, held in self.roles.items()
            if any(role.value == relation.value for role in held)
        ]

    async def add_relation(self, relation: Relation) -> None:
        uid = relation.subject.id
        self.roles.setdefault(uid, set()).add(UserTeamRelation(relation.relation.value))
        self.added_relations.append(relation)

    async def delete_relations(self, relations: list[Relation]) -> None:
        for rel in relations:
            uid = rel.subject.id
            self.roles.get(uid, set()).discard(UserTeamRelation(rel.relation.value))
            self.deleted_relations.append(rel)


class _FakeMetadataStore:
    def __init__(self, team_id: str, name: str = "Fredlab") -> None:
        self._metadata = TeamMetadata(id=TeamId(team_id), name=name)

    async def get_by_team_id(self, team_id, session=None):
        return self._metadata if str(team_id) == str(self._metadata.id) else None


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="caller", username="caller", roles=[], email=None, groups=[]
    )


async def _no_users_by_ids(*_a, **_k) -> dict:
    return {}


def _deps(
    rebac: _FakeRebac,
    team_id: str,
    *,
    get_session_store: Any = cast(Any, object),
    get_purge_queue_store: Any = cast(Any, object),
):
    from control_plane_backend.teams.dependencies import TeamServiceDependencies

    config = MagicMock()
    config.app.personal_max_resources_storage_size = 5368709120
    store = _FakeMetadataStore(team_id)
    return TeamServiceDependencies(
        configuration=config,
        rebac=cast(Any, rebac),
        scheduler_backend=cast(Any, object()),
        get_team_metadata_store=cast(Any, lambda: store),
        get_content_store=cast(Any, object),
        get_session_store=get_session_store,
        get_purge_queue_store=get_purge_queue_store,
        get_policy_catalog=cast(Any, object),
        get_users_by_ids=cast(Any, _no_users_by_ids),
        run_lifecycle_manager_once_in_memory=cast(Any, lambda _i: object()),
    )


# --------------------------- grant --------------------------------------


@pytest.mark.asyncio
async def test_grant_team_member_role_adds_without_removing_existing() -> None:
    rebac = _FakeRebac(roles={"bob": {UserTeamRelation.TEAM_ADMIN}})

    await grant_team_member_role(
        _user(),
        TeamId("fredlab"),
        "bob",
        GrantTeamMemberRoleRequest(relation=UserTeamRelation.TEAM_EDITOR),
        _deps(rebac, "fredlab"),
    )

    assert rebac.roles["bob"] == {
        UserTeamRelation.TEAM_ADMIN,
        UserTeamRelation.TEAM_EDITOR,
    }


@pytest.mark.asyncio
async def test_grant_team_member_role_checks_permission_for_granted_role() -> None:
    rebac = _FakeRebac(roles={"bob": {UserTeamRelation.TEAM_ADMIN}})

    await grant_team_member_role(
        _user(),
        TeamId("fredlab"),
        "bob",
        GrantTeamMemberRoleRequest(relation=UserTeamRelation.TEAM_ANALYST),
        _deps(rebac, "fredlab"),
    )

    assert rebac.team_permission_checks == [
        ("fredlab", (TeamPermission.CAN_ADMINISTER_ANALYSTS,))
    ]


# --------------------------- revoke --------------------------------------


@pytest.mark.asyncio
async def test_revoke_team_member_role_removes_only_that_role() -> None:
    rebac = _FakeRebac(
        roles={
            "bob": {
                UserTeamRelation.TEAM_ADMIN,
                UserTeamRelation.TEAM_EDITOR,
                UserTeamRelation.TEAM_ANALYST,
            }
        }
    )

    await revoke_team_member_role(
        _user(),
        TeamId("fredlab"),
        "bob",
        UserTeamRelation.TEAM_EDITOR,
        _deps(rebac, "fredlab"),
    )

    assert rebac.roles["bob"] == {
        UserTeamRelation.TEAM_ADMIN,
        UserTeamRelation.TEAM_ANALYST,
    }


@pytest.mark.asyncio
async def test_revoke_team_member_role_raises_when_not_held() -> None:
    rebac = _FakeRebac(roles={"bob": {UserTeamRelation.TEAM_ADMIN}})

    with pytest.raises(TeamMemberRoleNotHeldError):
        await revoke_team_member_role(
            _user(),
            TeamId("fredlab"),
            "bob",
            UserTeamRelation.TEAM_ANALYST,
            _deps(rebac, "fredlab"),
        )

    assert rebac.roles["bob"] == {UserTeamRelation.TEAM_ADMIN}
    assert rebac.deleted_relations == []


@pytest.mark.asyncio
async def test_revoke_team_member_role_raises_when_it_is_the_last_role() -> None:
    """AUTHZ-06 (RFC Part 7 §35): revoking a member's only role would silently
    remove them — that must go through `remove_team_member` instead."""
    rebac = _FakeRebac(
        roles={
            "bob": {UserTeamRelation.TEAM_EDITOR},
            "alice": {UserTeamRelation.TEAM_ADMIN},
        }
    )

    with pytest.raises(TeamMemberLastRoleError):
        await revoke_team_member_role(
            _user(),
            TeamId("fredlab"),
            "bob",
            UserTeamRelation.TEAM_EDITOR,
            _deps(rebac, "fredlab"),
        )

    assert rebac.roles["bob"] == {UserTeamRelation.TEAM_EDITOR}
    assert rebac.deleted_relations == []


@pytest.mark.asyncio
async def test_revoke_team_member_role_blocks_removing_the_last_admin() -> None:
    rebac = _FakeRebac(
        roles={"bob": {UserTeamRelation.TEAM_ADMIN, UserTeamRelation.TEAM_EDITOR}}
    )

    with pytest.raises(TeamAdminConstraintError):
        await revoke_team_member_role(
            _user(),
            TeamId("fredlab"),
            "bob",
            UserTeamRelation.TEAM_ADMIN,
            _deps(rebac, "fredlab"),
        )

    # Mechanically inert — nothing was revoked.
    assert rebac.roles["bob"] == {
        UserTeamRelation.TEAM_ADMIN,
        UserTeamRelation.TEAM_EDITOR,
    }


@pytest.mark.asyncio
async def test_revoke_team_member_role_allows_admin_revoke_when_another_admin_exists() -> (
    None
):
    rebac = _FakeRebac(
        roles={
            "bob": {UserTeamRelation.TEAM_ADMIN, UserTeamRelation.TEAM_EDITOR},
            "alice": {UserTeamRelation.TEAM_ADMIN},
        }
    )

    await revoke_team_member_role(
        _user(),
        TeamId("fredlab"),
        "bob",
        UserTeamRelation.TEAM_ADMIN,
        _deps(rebac, "fredlab"),
    )

    assert rebac.roles["bob"] == {UserTeamRelation.TEAM_EDITOR}


# --------------------------- roster / removal -----------------------------


@pytest.mark.asyncio
async def test_list_team_members_reports_every_held_role() -> None:
    rebac = _FakeRebac(
        roles={
            "bob": {
                UserTeamRelation.TEAM_ADMIN,
                UserTeamRelation.TEAM_EDITOR,
                UserTeamRelation.TEAM_ANALYST,
            },
            "phil": {UserTeamRelation.TEAM_EDITOR},
        }
    )

    members = await list_team_members_unfiltered(
        _user(), TeamId("fredlab"), _deps(rebac, "fredlab")
    )

    by_id = {m.user.id: m.relations for m in members}
    assert by_id["bob"] == [
        UserTeamRelation.TEAM_ADMIN,
        UserTeamRelation.TEAM_EDITOR,
        UserTeamRelation.TEAM_ANALYST,
    ]
    assert by_id["phil"] == [UserTeamRelation.TEAM_EDITOR]


@pytest.mark.asyncio
async def test_remove_team_member_checks_permission_for_every_held_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AUTHZ-06 (RFC Part 7 §35): a full removal must be checked against every
    role the member holds, not just one — otherwise someone administerable
    only via `can_administer_editors` could remove a `team_admin` who also
    happens to hold `team_editor`."""
    from control_plane_backend.scheduler.policies.policy_models import (
        PolicyEvaluationResult,
        PurgeMode,
    )

    rebac = _FakeRebac(
        roles={
            "bob": {UserTeamRelation.TEAM_ADMIN, UserTeamRelation.TEAM_EDITOR},
            "alice": {UserTeamRelation.TEAM_ADMIN},
        }
    )

    class _FakeSessionStore:
        async def get_for_user(self, _user_id, _team_id, db_session=None):
            return []

    class _FakePurgeQueueStore:
        async def enqueue(self, **_kwargs):
            pass

    monkeypatch.setattr(
        "control_plane_backend.teams.service.evaluate_policy_for_request",
        lambda *_a, **_k: PolicyEvaluationResult(
            mode=PurgeMode.IMMEDIATE_DELETE,
            retention="PT0S",
            retention_seconds=0,
            cancel_on_rejoin=True,
            matched_rule_id=None,
            matched_rule_specificity=0,
        ),
    )

    deps = _deps(
        rebac,
        "fredlab",
        get_session_store=lambda: _FakeSessionStore(),
        get_purge_queue_store=lambda: _FakePurgeQueueStore(),
    )

    await remove_team_member(_user(), TeamId("fredlab"), "bob", deps)

    checked_permissions = {
        permission
        for _, permissions in rebac.team_permission_checks
        for permission in permissions
    }
    assert checked_permissions == {
        TeamPermission.CAN_ADMINISTER_ADMINS,
        TeamPermission.CAN_ADMINISTER_EDITORS,
    }
    assert rebac.roles["bob"] == set()
