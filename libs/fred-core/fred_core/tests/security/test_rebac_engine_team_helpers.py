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

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
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

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
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
async def test_check_user_team_permissions_or_raise_reuses_consistency_token() -> None:
    engine = _RecordingRebacEngine()

    token = await engine.check_user_team_permissions_or_raise(
        user=_user(),
        team_id="team-a",
        permissions=[TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_RESOURCES],
    )

    assert token is not None
    assert int(token) == 1
    assert len(engine.checked_permissions) == 2
    assert engine.checked_permissions == [
        (TeamPermission.CAN_READ, "team-a", token),
        (TeamPermission.CAN_UPDATE_RESOURCES, "team-a", token),
    ]


@pytest.mark.asyncio
async def test_check_user_team_permission_or_raise_single_permission() -> None:
    engine = _RecordingRebacEngine()

    token = await engine.check_user_team_permission_or_raise(
        user=_user(),
        permission=TeamPermission.CAN_UPDATE_AGENTS,
        team_id="team-42",
    )

    assert token is not None
    assert int(token) == 1
    assert engine.checked_permissions == [
        (TeamPermission.CAN_UPDATE_AGENTS, "team-42", token)
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

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
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
