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

from __future__ import annotations

from typing import Iterable

import pytest

from fred_core.common.team_id import personal_team_id
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.rebac.rebac_engine import (
    AgentPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
    TeamPermission,
)
from fred_core.security.structure import KeycloakUser


class _RecordingRebacEngine(RebacEngine):
    def __init__(self) -> None:
        self.added_relations: list[Relation] = []
        self.checked_permissions: list[tuple[RebacPermission, str, str | None]] = []

    async def _persist_relation(self, relation: Relation) -> str | None:
        self.added_relations.append(relation)
        return str(len(self.added_relations))

    async def delete_relation(self, relation: Relation) -> str | None:
        return None

    async def delete_all_relations_of_reference(
        self,
        reference: RebacReference,
    ) -> str | None:
        return None

    async def delete_all_relations_of_type(self, resource_type: Resource) -> int:
        return 0

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject: RebacReference,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        return []

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        return []

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        return []

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        return True

    async def check_user_permission_or_raise(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        resource_id: str,
        *,
        consistency_token: str | None = None,
    ) -> None:
        self.checked_permissions.append((permission, resource_id, consistency_token))


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="user-123",
        username="alice",
        roles=["admin"],
        email="alice@example.com",
    )


class _ContextualRelationsSpyEngine(RebacEngine):
    """Records the `contextual_relations` argument received by the low-level
    OpenFGA-facing methods, so tests can prove the removed Keycloak-groups
    fallback (AUTHZ-05 item 8b) no longer injects anything automatically.
    `KeycloakUser` no longer carries a `groups` field at all (AUTHZ-05 final
    sweep), so this is now a plain regression guard against any future
    contextual-relations auto-injection, not a groups-specific proof."""

    def __init__(self) -> None:
        self.received_contextual_relations: list[object] = []

    async def _persist_relation(self, relation: Relation) -> str | None:
        return None

    async def delete_relation(self, relation: Relation) -> str | None:
        return None

    async def delete_all_relations_of_reference(
        self,
        reference: RebacReference,
    ) -> str | None:
        return None

    async def delete_all_relations_of_type(self, resource_type: Resource) -> int:
        return 0

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject: RebacReference,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        return []

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        self.received_contextual_relations.append(contextual_relations)
        return []

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        return []

    async def has_direct_relation(
        self,
        subject: RebacReference,
        relation: RelationType,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        # Pretend the tuple already exists so `lookup_user_resources`'s
        # personal-team self-heal (AUTHZ-08 follow-up) is a no-op here — this
        # class exists to spy on `contextual_relations`, not to exercise
        # self-heal (see `_PersonalTeamAwareEngine` for that).
        return True

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        self.received_contextual_relations.append(contextual_relations)
        return True


@pytest.mark.asyncio
async def test_lookup_user_resources_sends_no_contextual_relations() -> None:
    engine = _ContextualRelationsSpyEngine()

    await engine.lookup_user_resources(_user(), TeamPermission.CAN_READ)

    assert engine.received_contextual_relations == [None]


@pytest.mark.asyncio
async def test_has_user_permission_sends_no_contextual_relations() -> None:
    engine = _ContextualRelationsSpyEngine()

    await engine.has_user_permission(_user(), TeamPermission.CAN_READ, "team-a")

    assert engine.received_contextual_relations == [None]


@pytest.mark.asyncio
async def test_check_user_permission_or_raise_sends_no_contextual_relations() -> None:
    engine = _ContextualRelationsSpyEngine()

    await engine.check_user_permission_or_raise(
        _user(), TeamPermission.CAN_READ, "team-a"
    )

    assert engine.received_contextual_relations == [None]


@pytest.mark.asyncio
async def test_ensure_team_organization_relations_creates_unique_edges() -> None:
    engine = _RecordingRebacEngine()

    token = await engine.ensure_team_organization_relations(
        ["team-a", "team-a", "", "team-b"]
    )

    assert token is not None
    assert int(token) == 2
    assert len(engine.added_relations) == 2

    expected_resources = {"team-a", "team-b"}
    for relation in engine.added_relations:
        assert relation.subject == RebacReference(Resource.ORGANIZATION, "fred")
        assert relation.relation == RelationType.ORGANIZATION
        assert relation.resource.type == Resource.TEAM
        assert relation.resource.id in expected_resources


@pytest.mark.asyncio
async def test_check_user_team_permissions_or_raise_no_longer_touches_organization_edge() -> (
    None
):
    """#2065: this helper no longer ensures `organization -> team` first —
    zero writes, zero `list_relations` reads, and no consistency token to
    propagate (there is nothing written in this call to need one for)."""
    engine = _RecordingRebacEngine()

    token = await engine.check_user_team_permissions_or_raise(
        user=_user(),
        team_id="team-a",
        permissions=[TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_RESOURCES],
    )

    assert token is None
    assert engine.added_relations == []
    assert len(engine.checked_permissions) == 2
    assert engine.checked_permissions == [
        (TeamPermission.CAN_READ, "team-a", None),
        (TeamPermission.CAN_UPDATE_RESOURCES, "team-a", None),
    ]


@pytest.mark.asyncio
async def test_check_user_team_permissions_or_raise_is_pure_io_free_when_empty() -> (
    None
):
    """#2065: with zero permissions requested, this must be a pure no-op —
    not even the organization-edge write the old contract performed
    unconditionally."""
    engine = _RecordingRebacEngine()

    token = await engine.check_user_team_permissions_or_raise(
        user=_user(), team_id="team-a", permissions=[]
    )

    assert token is None
    assert engine.added_relations == []
    assert engine.checked_permissions == []


@pytest.mark.asyncio
async def test_check_user_team_permission_or_raise_single_permission() -> None:
    engine = _RecordingRebacEngine()

    token = await engine.check_user_team_permission_or_raise(
        user=_user(),
        permission=TeamPermission.CAN_UPDATE_AGENTS,
        team_id="team-42",
    )

    assert token is None
    assert engine.added_relations == []
    assert engine.checked_permissions == [
        (TeamPermission.CAN_UPDATE_AGENTS, "team-42", None)
    ]


class _PersonalTeamAwareEngine(RebacEngine):
    """Exercises the real base-class self-heal (`_ensure_personal_team_editor`)
    and write-guard (`_reject_unsanctioned_personal_team_write`) logic directly.

    Unlike `_RecordingRebacEngine`, this does NOT override
    `check_user_permission_or_raise`/`has_user_permission`, so calls flow through
    the actual `RebacEngine` implementation being tested (AUTHZ-08).
    """

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self.added_relations: list[Relation] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def _persist_relation(self, relation: Relation) -> str | None:
        self.added_relations.append(relation)
        return str(len(self.added_relations))

    async def delete_relation(self, relation: Relation) -> str | None:
        return None

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        return None

    async def delete_all_relations_of_type(self, resource_type: Resource) -> int:
        return 0

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject: RebacReference,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        return []

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        return []

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        return []

    async def has_direct_relation(
        self,
        subject: RebacReference,
        relation: RelationType,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        return any(
            r.subject == subject and r.relation == relation and r.resource == resource
            for r in self.added_relations
        )

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        # Narrow stand-in sufficient for these tests: authorized iff a direct
        # tuple was persisted for this exact subject/resource pair.
        return any(
            r.subject == subject and r.resource == resource
            for r in self.added_relations
        )


@pytest.mark.asyncio
async def test_ensure_personal_team_editor_self_heals_on_first_check() -> None:
    engine = _PersonalTeamAwareEngine()
    user = _user()
    team_id = personal_team_id(user.uid)

    await engine.check_user_permission_or_raise(user, TeamPermission.CAN_READ, team_id)

    assert engine.added_relations == [
        Relation(
            subject=RebacReference(Resource.USER, user.uid),
            relation=RelationType.TEAM_EDITOR,
            resource=RebacReference(Resource.TEAM, team_id),
        )
    ]


@pytest.mark.asyncio
async def test_ensure_personal_team_editor_is_idempotent() -> None:
    engine = _PersonalTeamAwareEngine()
    user = _user()
    team_id = personal_team_id(user.uid)

    await engine.check_user_permission_or_raise(user, TeamPermission.CAN_READ, team_id)
    await engine.check_user_permission_or_raise(user, TeamPermission.CAN_READ, team_id)

    assert len(engine.added_relations) == 1


@pytest.mark.asyncio
async def test_ensure_personal_team_editor_never_provisions_another_users_space() -> (
    None
):
    engine = _PersonalTeamAwareEngine()
    alice = _user()
    bobs_team = personal_team_id("bob")

    with pytest.raises(AuthorizationError):
        await engine.check_user_permission_or_raise(
            alice, TeamPermission.CAN_READ, bobs_team
        )

    assert engine.added_relations == []


@pytest.mark.asyncio
async def test_ensure_personal_team_editor_skips_when_rebac_disabled() -> None:
    engine = _PersonalTeamAwareEngine(enabled=False)
    user = _user()
    team_id = personal_team_id(user.uid)

    with pytest.raises(AuthorizationError):
        await engine.check_user_permission_or_raise(
            user, TeamPermission.CAN_READ, team_id
        )

    assert engine.added_relations == []


@pytest.mark.asyncio
async def test_lookup_user_resources_self_heals_personal_team_on_first_enumeration() -> (
    None
):
    """Regression for the enumeration gap found in the AUTHZ-08 review: a
    first-touch user whose very first ReBAC-touching call is "list my teams"
    (e.g. the `/fs` virtual `/teams` directory) must still get their own
    personal-team tuple self-healed — `lookup_resources`/OpenFGA `ListObjects`
    never went through `has_user_permission`/`check_user_team_permission_or_raise`,
    so without wiring self-heal into `lookup_user_resources` too, the owner's
    own personal team was silently absent from every "list my teams" result
    until some unrelated check-triggering call happened to provision it first.
    """
    engine = _PersonalTeamAwareEngine()
    user = _user()
    team_id = personal_team_id(user.uid)

    await engine.lookup_user_resources(user, TeamPermission.CAN_READ)

    assert engine.added_relations == [
        Relation(
            subject=RebacReference(Resource.USER, user.uid),
            relation=RelationType.TEAM_EDITOR,
            resource=RebacReference(Resource.TEAM, team_id),
        )
    ]


@pytest.mark.asyncio
async def test_lookup_user_resources_self_heal_is_idempotent() -> None:
    engine = _PersonalTeamAwareEngine()
    user = _user()

    await engine.lookup_user_resources(user, TeamPermission.CAN_READ)
    await engine.lookup_user_resources(user, TeamPermission.CAN_READ)

    assert len(engine.added_relations) == 1


@pytest.mark.asyncio
async def test_lookup_user_resources_skips_self_heal_for_non_team_permission() -> None:
    """Enumerating a non-team resource type (e.g. "list my agents") must never
    trigger the personal-team self-heal — it is scoped to `Resource.TEAM`
    enumeration only, same as the existing check-path self-heal."""
    engine = _PersonalTeamAwareEngine()
    user = _user()

    await engine.lookup_user_resources(user, AgentPermission.READ)

    assert engine.added_relations == []


@pytest.mark.asyncio
async def test_add_relation_rejects_elevated_role_on_personal_team() -> None:
    engine = _PersonalTeamAwareEngine()
    team_id = personal_team_id("alice")

    with pytest.raises(ValueError):
        await engine.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, "alice"),
                relation=RelationType.TEAM_ADMIN,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        )
    assert engine.added_relations == []


@pytest.mark.asyncio
async def test_add_relation_rejects_grant_to_a_different_user_on_personal_team() -> (
    None
):
    engine = _PersonalTeamAwareEngine()
    team_id = personal_team_id("alice")

    with pytest.raises(ValueError):
        await engine.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, "mallory"),
                relation=RelationType.TEAM_EDITOR,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        )
    assert engine.added_relations == []


@pytest.mark.asyncio
async def test_add_relation_allows_owner_editor_grant_on_personal_team() -> None:
    engine = _PersonalTeamAwareEngine()
    team_id = personal_team_id("alice")

    await engine.add_relation(
        Relation(
            subject=RebacReference(Resource.USER, "alice"),
            relation=RelationType.TEAM_EDITOR,
            resource=RebacReference(Resource.TEAM, team_id),
        )
    )

    assert len(engine.added_relations) == 1


@pytest.mark.asyncio
async def test_add_relation_allows_organization_edge_on_personal_team() -> None:
    engine = _PersonalTeamAwareEngine()
    team_id = personal_team_id("alice")

    await engine.ensure_team_organization_relations([team_id])

    assert len(engine.added_relations) == 1
    assert engine.added_relations[0].relation == RelationType.ORGANIZATION


@pytest.mark.asyncio
async def test_check_user_team_permission_or_raise_never_persists_organization_edge_for_personal_space() -> (
    None
):
    """#2065 / personal-space isolation: the real per-request team-permission
    check path (`check_user_team_permission_or_raise`) never touches the
    `organization -> team` structural edge for ANY team, collaborative or
    personal — it was removed from this hot path entirely, not just guarded
    against for personal spaces. The only write a personal space's first
    touch produces is its own `team_editor` self-heal."""
    engine = _PersonalTeamAwareEngine()
    user = _user()
    team_id = personal_team_id(user.uid)

    await engine.check_user_team_permission_or_raise(
        user, TeamPermission.CAN_READ, team_id
    )

    assert engine.added_relations == [
        Relation(
            subject=RebacReference(Resource.USER, user.uid),
            relation=RelationType.TEAM_EDITOR,
            resource=RebacReference(Resource.TEAM, team_id),
        )
    ]


class _InMemoryCountingRebacEngine(RebacEngine):
    """Real, filterable `list_relations` against an in-memory tuple set.

    #2065 regression coverage: `_RecordingRebacEngine`/`_PersonalTeamAwareEngine`
    above both stub `list_relations` to `return []` unconditionally, which
    can't distinguish "no existing edges" from "existing edges I forgot to
    return" — it would pass even if `ensure_team_organization_relations`
    stopped calling `list_relations` at all. This fake actually stores what
    was written/deleted and answers `list_relations` from that state, so
    tests can assert the *skip* behavior (no write for an edge that already
    exists, no delete for one that's already absent), not just the write
    behavior already covered above.

    `disabled=True` makes `list_relations` return `RebacDisabledResult()`,
    covering the fallback branch (`_teams_with_relation` returning `None`)
    that preserves today's unconditional-write behavior for engines (like
    `NoopRebacEngine`) that don't support bulk listing.
    """

    def __init__(self, *, disabled: bool = False) -> None:
        self._disabled = disabled
        self.tuples: list[Relation] = []
        self.added_relations: list[Relation] = []
        self.deleted_relations: list[Relation] = []
        self.list_relations_call_count = 0
        self.list_relations_consistency_tokens: list[str | None] = []

    async def _persist_relation(self, relation: Relation) -> str | None:
        self.added_relations.append(relation)
        if relation not in self.tuples:
            self.tuples.append(relation)
        return str(len(self.added_relations))

    async def delete_relation(self, relation: Relation) -> str | None:
        self.deleted_relations.append(relation)
        if relation in self.tuples:
            self.tuples.remove(relation)
        return str(len(self.deleted_relations))

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        return None

    async def delete_all_relations_of_type(self, resource_type: Resource) -> int:
        return 0

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject: RebacReference,
        consistency_token: str | None = None,
    ) -> list[Relation] | RebacDisabledResult:
        self.list_relations_call_count += 1
        self.list_relations_consistency_tokens.append(consistency_token)
        if self._disabled:
            return RebacDisabledResult()
        return [
            rel
            for rel in self.tuples
            if rel.resource.type == resource_type
            and rel.relation == relation
            and rel.subject == subject
        ]

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        return []

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        return []

    async def has_direct_relation(
        self,
        subject: RebacReference,
        relation: RelationType,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        return any(
            r.subject == subject and r.relation == relation and r.resource == resource
            for r in self.tuples
        )

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        return any(r.subject == subject and r.resource == resource for r in self.tuples)


@pytest.mark.asyncio
async def test_ensure_team_organization_relations_skips_already_granted_edges() -> None:
    engine = _InMemoryCountingRebacEngine()

    await engine.ensure_team_organization_relations(["team-a", "team-b"])
    assert len(engine.added_relations) == 2

    await engine.ensure_team_organization_relations(["team-a", "team-b"])
    assert len(engine.added_relations) == 2, "steady-state call must write nothing"

    await engine.ensure_team_organization_relations(["team-a", "team-b", "team-c"])
    assert len(engine.added_relations) == 3, "only the genuinely new team is written"
    assert engine.added_relations[-1].resource.id == "team-c"


@pytest.mark.asyncio
async def test_ensure_team_organization_relations_writes_everything_when_disabled() -> (
    None
):
    engine = _InMemoryCountingRebacEngine(disabled=True)

    await engine.ensure_team_organization_relations(["team-a", "team-b"])
    await engine.ensure_team_organization_relations(["team-a", "team-b"])

    assert len(engine.added_relations) == 4, (
        "an engine that can't bulk-list relations must fall back to "
        "unconditional writes, unchanged from before #2065"
    )


@pytest.mark.asyncio
async def test_ensure_team_public_relations_skips_already_granted_edges() -> None:
    engine = _InMemoryCountingRebacEngine()

    await engine.ensure_team_public_relations(["team-a", "team-b"])
    assert len(engine.added_relations) == 2

    await engine.ensure_team_public_relations(["team-a", "team-b"])
    assert len(engine.added_relations) == 2, "steady-state call must write nothing"


@pytest.mark.asyncio
async def test_revoke_team_public_relations_skips_already_absent_edges() -> None:
    engine = _InMemoryCountingRebacEngine()

    # Nothing granted yet: revoking must not issue a single delete call.
    await engine.revoke_team_public_relations(["team-a", "team-b"])
    assert engine.deleted_relations == []

    await engine.ensure_team_public_relations(["team-a", "team-b"])
    assert len(engine.added_relations) == 2

    # Now both are granted: revoking deletes exactly those, once.
    await engine.revoke_team_public_relations(["team-a", "team-b"])
    assert len(engine.deleted_relations) == 2

    # Already revoked: calling again must not re-issue the deletes.
    await engine.revoke_team_public_relations(["team-a", "team-b"])
    assert len(engine.deleted_relations) == 2, "steady-state revoke must delete nothing"


@pytest.mark.asyncio
async def test_ensure_and_revoke_team_public_relations_propagate_consistency_token() -> (
    None
):
    """#2145 review: a team flipped public then immediately private again
    must have `revoke_team_public_relations`'s existence-check read see that
    just-written `public` grant, or the revoke is wrongly skipped and the
    team stays publicly readable until a later reconciliation. The
    direct-mutation caller (`update_team`) asks for that by passing
    `consistency_token=HIGHER_CONSISTENCY` through to the underlying
    `list_relations` read; the lazy listing call sites keep the default
    eventually-consistent read (asserted last, below)."""
    engine = _InMemoryCountingRebacEngine()

    await engine.ensure_team_public_relations(
        ["team-a"], consistency_token=RebacEngine.HIGHER_CONSISTENCY
    )
    assert (
        engine.list_relations_consistency_tokens[-1] == RebacEngine.HIGHER_CONSISTENCY
    )

    await engine.revoke_team_public_relations(
        ["team-a"], consistency_token=RebacEngine.HIGHER_CONSISTENCY
    )
    assert (
        engine.list_relations_consistency_tokens[-1] == RebacEngine.HIGHER_CONSISTENCY
    )

    await engine.ensure_team_public_relations(["team-b"])
    assert engine.list_relations_consistency_tokens[-1] is None
