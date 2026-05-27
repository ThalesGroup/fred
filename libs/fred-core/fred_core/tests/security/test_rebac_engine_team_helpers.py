from __future__ import annotations

from typing import Iterable

import pytest
from pydantic import AnyUrl

from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
    TeamPermission,
)
from fred_core.security.structure import KeycloakUser, M2MSecurity


class _RecordingRebacEngine(RebacEngine):
    def __init__(self) -> None:
        super().__init__(
            M2MSecurity(
                enabled=False,
                realm_url=AnyUrl("http://localhost:8080/realms/app"),
                client_id="test-client",
            )
        )
        self.added_relations: list[Relation] = []
        self.checked_permissions: list[tuple[RebacPermission, str, str | None]] = []

    async def add_relation(self, relation: Relation) -> str | None:
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
        groups=[],
    )


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
