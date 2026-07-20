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
    search_candidate_team_members,
)
from control_plane_backend.users.schemas import UserSummary
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

    async def has_direct_relation(
        self, subject, relation: RelationType, resource, **kwargs
    ) -> bool:
        # Literal-tuple read: unlike `lookup_subjects`, this must NOT treat
        # an elevated role (admin/editor/analyst) as satisfying a
        # `TEAM_MEMBER` query — it only reports what was actually written to
        # `self.roles`, mirroring OpenFGA's raw `Read` API (no userset
        # rewrite), exactly like `_add_team_member_relation`/
        # `_remove_team_member_relation` writing/deleting one literal tuple.
        uid = subject.id
        held = self.roles.get(uid, set())
        return any(role.value == relation.value for role in held)

    async def add_relation(self, relation: Relation, **kwargs: object) -> None:
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
    return KeycloakUser(uid="caller", username="caller", roles=[], email=None)


async def _no_users_by_ids(*_a, **_k) -> dict:
    return {}


async def _no_search_users(*_a, **_k) -> list:
    return []


def _deps(
    rebac: _FakeRebac,
    team_id: str,
    *,
    get_session_store: Any = cast(Any, object),
    get_purge_queue_store: Any = cast(Any, object),
    search_users: Any = cast(Any, _no_search_users),
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
        search_users=search_users,
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


# --------------------------- base-role preservation (PR #1957 review) -----
#
# `_FakeRebac.lookup_subjects` mirrors OpenFGA's computed `team_member`
# relation (schema.fga: `[user] or team_admin or team_editor or
# team_analyst`) exactly — a TEAM_MEMBER lookup also returns elevated-role
# holders, whether or not they hold a direct `team_member` tuple. This lets
# these tests reproduce the bug (and pin the fix) without a live OpenFGA
# server: `_get_user_roles_in_team` must recover the base role from
# `has_direct_relation` (a literal-tuple read), never from that computed set.


@pytest.mark.asyncio
async def test_member_promoted_to_editor_can_be_demoted_back_to_member() -> None:
    """Regression for PR #1957 discussion_r3568344074: a base member granted
    an elevated role must be demotable back to base member — revoking the
    elevated role must not be mistaken for revoking their only role."""
    rebac = _FakeRebac(roles={"bob": {UserTeamRelation.TEAM_MEMBER}})

    await grant_team_member_role(
        _user(),
        TeamId("fredlab"),
        "bob",
        GrantTeamMemberRoleRequest(relation=UserTeamRelation.TEAM_EDITOR),
        _deps(rebac, "fredlab"),
    )
    assert rebac.roles["bob"] == {
        UserTeamRelation.TEAM_MEMBER,
        UserTeamRelation.TEAM_EDITOR,
    }

    await revoke_team_member_role(
        _user(),
        TeamId("fredlab"),
        "bob",
        UserTeamRelation.TEAM_EDITOR,
        _deps(rebac, "fredlab"),
    )

    assert rebac.roles["bob"] == {UserTeamRelation.TEAM_MEMBER}


@pytest.mark.asyncio
async def test_member_editor_analyst_revoke_editor_keeps_member_and_analyst() -> None:
    rebac = _FakeRebac(
        roles={
            "bob": {
                UserTeamRelation.TEAM_MEMBER,
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
        UserTeamRelation.TEAM_MEMBER,
        UserTeamRelation.TEAM_ANALYST,
    }


@pytest.mark.asyncio
async def test_editor_and_analyst_without_direct_member_tuple_revoke_editor_leaves_analyst() -> (
    None
):
    """No direct `team_member` tuple was ever written for bob — only the
    computed relation would show one. The base role must NOT be fabricated:
    after revoking editor, bob is analyst only, not analyst + member."""
    rebac = _FakeRebac(
        roles={"bob": {UserTeamRelation.TEAM_EDITOR, UserTeamRelation.TEAM_ANALYST}}
    )

    await revoke_team_member_role(
        _user(),
        TeamId("fredlab"),
        "bob",
        UserTeamRelation.TEAM_EDITOR,
        _deps(rebac, "fredlab"),
    )

    assert rebac.roles["bob"] == {UserTeamRelation.TEAM_ANALYST}


@pytest.mark.asyncio
async def test_editor_alone_without_direct_member_tuple_revoke_editor_stays_refused() -> (
    None
):
    """bob holds team_editor only, with no direct team_member tuple (and no
    other elevated role) — revoking editor is still refused as a last-role
    revoke; the fix must not incorrectly grant a fabricated base role that
    would let this succeed."""
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


# --------------------------- search_candidate_team_members ---------------


@pytest.mark.asyncio
async def test_search_candidate_team_members_checks_permission_and_excludes_existing_members() -> (
    None
):
    rebac = _FakeRebac(roles={"existing-member": {UserTeamRelation.TEAM_MEMBER}})
    search_calls: list[str] = []

    async def _search_users(query: str) -> list[UserSummary]:
        search_calls.append(query)
        return [
            UserSummary(id="existing-member", username="already-in-team"),
            UserSummary(id="new-user", username="cohen.odelia"),
        ]

    deps = _deps(rebac, "fredlab", search_users=_search_users)

    matches = await search_candidate_team_members(
        _user(), TeamId("fredlab"), "cohen", deps
    )

    assert search_calls == ["cohen"]
    assert [m.id for m in matches] == ["new-user"]
    assert rebac.team_permission_checks == [
        ("fredlab", (TeamPermission.CAN_ADMINISTER_MEMBERS,))
    ]


@pytest.mark.asyncio
async def test_search_candidate_team_members_rejects_whitespace_only_query() -> None:
    """`min_length=2` at the API layer validates the raw string, so "  " (two
    spaces) would otherwise pass through and reach Keycloak's search
    un-widened. The service must strip and re-check before searching — but
    still authorize first, regardless of whether the query turns out valid.
    """
    rebac = _FakeRebac(roles={})
    search_calls: list[str] = []

    async def _search_users(query: str) -> list[UserSummary]:
        search_calls.append(query)
        return [UserSummary(id="new-user", username="cohen.odelia")]

    deps = _deps(rebac, "fredlab", search_users=_search_users)

    matches = await search_candidate_team_members(
        _user(), TeamId("fredlab"), "  ", deps
    )

    assert matches == []
    assert search_calls == []  # never reached the search
    assert rebac.team_permission_checks == [
        ("fredlab", (TeamPermission.CAN_ADMINISTER_MEMBERS,))
    ]  # still authorized before the empty-query short-circuit


@pytest.mark.asyncio
async def test_search_candidate_team_members_strips_surrounding_whitespace() -> None:
    rebac = _FakeRebac(roles={})
    search_calls: list[str] = []

    async def _search_users(query: str) -> list[UserSummary]:
        search_calls.append(query)
        return [UserSummary(id="new-user", username="cohen.odelia")]

    deps = _deps(rebac, "fredlab", search_users=_search_users)

    await search_candidate_team_members(_user(), TeamId("fredlab"), "  cohen  ", deps)

    assert search_calls == ["cohen"]
