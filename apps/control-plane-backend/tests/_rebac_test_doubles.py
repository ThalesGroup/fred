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

"""Shared call-counting `RebacEngine` test double for #2065-family budget
tests (`test_teams_bulk_membership_call_count.py`, `test_require_team_
access.py`, `test_get_team_by_id_projection_budget.py`) — one real engine
answering `list_relations`/`list_direct_relations`/`has_permission`/
`has_permissions`/`add_relations` from seeded state and recording every call,
so tests assert the exact OpenFGA call budget instead of trusting a stubbed
permission check.

Not named `test_*` so pytest never collects it as a test module — it is
imported like any other helper.
"""

from __future__ import annotations

from typing import Iterable

from fred_core import (
    ORGANIZATION_ID,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from fred_core.security.rebac.noop_engine import NoopRebacEngine


class CountingRebacEngine(NoopRebacEngine):
    """Test-only strict `RebacEngine` double.

    Subclasses `NoopRebacEngine` rather than `RebacEngine` directly, so a
    method a given test never exercises (`delete_relation`,
    `delete_all_relations_of_type`, ...) falls back to a real no-op instead
    of every test file re-implementing every abstract method. `enabled` is
    forced back to `True` (unlike the real no-op engine) so `add_relation`'s
    audit trail and `RebacEngine._ensure_personal_team_editor`'s self-heal
    still run the same as production; `_persist_relation`/`delete_relation`
    return a sentinel token (mirrors `OpenFgaRebacEngine`, which always
    returns the same `HIGHER_CONSISTENCY` marker — OpenFGA has no per-write
    snapshot token) so consistency-token propagation is observable in tests
    instead of silently reading as `None` either way.

    Still strict where it matters: `lookup_resources`/`lookup_subjects`
    (ListObjects/ListUsers) always raise — every code path under test here
    must resolve teams/permissions from bulk `list_relations` or exact
    `list_direct_relations` reads, never a per-team/per-user fan-out. A
    forbidden call must fail loudly, not be silently absorbed into an empty
    result.
    """

    def __init__(
        self,
        *,
        org_linked_team_ids: Iterable[str] = (),
        public_team_ids: Iterable[str] = (),
        granted_permissions: Iterable[RebacPermission] = (),
        direct_relations: Iterable[Relation] = (),
        membership_relations: Iterable[Relation] = (),
    ) -> None:
        self.org_linked_team_ids = set(org_linked_team_ids)
        self.public_team_ids = set(public_team_ids)
        self.granted_permissions = set(granted_permissions)
        self.direct_relations = list(direct_relations)
        self.membership_relations = list(membership_relations)
        self.list_relations_calls: list[tuple[Resource, RelationType]] = []
        self.list_direct_relations_calls: list[
            tuple[RebacReference, RebacReference | None]
        ] = []
        self.list_direct_relations_tokens: list[str | None] = []
        self.has_permission_calls: list[tuple[str, RebacPermission, str]] = []
        self.has_permissions_calls: list[tuple[RebacPermission, ...]] = []
        self.has_permissions_tokens: list[str | None] = []
        self.add_relations_calls: list[list[Relation]] = []
        self.lookup_resources_calls = 0
        self.lookup_subjects_calls = 0

    @property
    def enabled(self) -> bool:
        return True

    def _record_write(self, relation: Relation) -> None:
        """Mirror one written tuple into the seeded read-state, so a write
        followed by a read (`list_direct_relations`/`list_relations`) inside
        the same test observes it — needed to prove write-then-read
        propagation (e.g. `create_team` seeing its own `initial_team_admin_ids`
        immediately), not just that a token value was threaded through
        unused."""
        self.direct_relations.append(relation)
        self.membership_relations.append(relation)
        if relation.resource.type == Resource.TEAM:
            if relation.relation == RelationType.ORGANIZATION:
                self.org_linked_team_ids.add(relation.resource.id)
            elif relation.relation == RelationType.PUBLIC:
                self.public_team_ids.add(relation.resource.id)

    async def _persist_relation(self, relation: Relation) -> str | None:
        self._record_write(relation)
        return "consistency-token"  # nosec B106 — fake test token, not a credential

    async def delete_relation(self, relation: Relation) -> str | None:
        return "consistency-token"  # nosec B106 — fake test token, not a credential

    async def add_relations(
        self, relations: Iterable[Relation], *, actor_uid: str | None = None
    ) -> str | None:
        relations = list(relations)
        self.add_relations_calls.append(relations)
        for relation in relations:
            self._record_write(relation)
        return "consistency-token"  # nosec B106 — fake test token, not a credential

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        self.list_relations_calls.append((resource_type, relation))
        if resource_type == Resource.TEAM and relation == RelationType.ORGANIZATION:
            return [
                Relation(
                    subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
                    relation=RelationType.ORGANIZATION,
                    resource=RebacReference(Resource.TEAM, team_id),
                )
                for team_id in self.org_linked_team_ids
            ]
        if resource_type == Resource.TEAM and relation == RelationType.PUBLIC:
            return [
                Relation(
                    subject=RebacReference(Resource.USER, "*"),
                    relation=RelationType.PUBLIC,
                    resource=RebacReference(Resource.TEAM, team_id),
                )
                for team_id in self.public_team_ids
            ]
        return [
            rel
            for rel in self.membership_relations
            if rel.resource.type == resource_type
            and rel.relation == relation
            and (subject_type is None or rel.subject.type == subject_type)
        ]

    async def list_direct_relations(
        self,
        resource: RebacReference,
        *,
        subject: RebacReference | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        self.list_direct_relations_calls.append((resource, subject))
        self.list_direct_relations_tokens.append(consistency_token)
        return [
            rel
            for rel in self.direct_relations
            if rel.resource == resource and (subject is None or rel.subject == subject)
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
        self.lookup_resources_calls += 1
        raise AssertionError("ListObjects must not be called by this code path")

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        self.lookup_subjects_calls += 1
        raise AssertionError("ListUsers must not be called by this code path")

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        self.has_permission_calls.append((subject.id, permission, resource.id))
        return permission in self.granted_permissions

    async def has_permissions(
        self,
        subject: RebacReference,
        permissions: Iterable[RebacPermission],
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[bool]:
        # Real BatchCheck-shaped override (like `OpenFgaRebacEngine`) so
        # budget tests prove exactly one logical batch call, not one Check
        # per permission via the generic `RebacEngine.has_permissions`
        # gather-fallback.
        permissions_list = list(permissions)
        self.has_permissions_calls.append(tuple(permissions_list))
        self.has_permissions_tokens.append(consistency_token)
        return [p in self.granted_permissions for p in permissions_list]


def assert_no_openfga_calls(engine: CountingRebacEngine) -> None:
    """Shared assertion for "this code path must be zero-OpenFGA-calls"
    scenarios (e.g. the caller's own personal space)."""
    assert engine.list_relations_calls == []
    assert engine.list_direct_relations_calls == []
    assert engine.has_permission_calls == []
    assert engine.has_permissions_calls == []
    assert engine.add_relations_calls == []
    assert engine.lookup_resources_calls == 0
    assert engine.lookup_subjects_calls == 0
