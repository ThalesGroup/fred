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

"""
`fred_core.security.rebac.capability_authz` (CAPAB-01 / #1980, 2026-08-03
RSK-B follow-up to #2191): the one shared `usable_capability_ids` query both
control-plane's `capabilities/authz.py` and fred-runtime's
`model_routing/authz.py` now delegate to instead of each keeping its own
field-for-field copy.
"""

from __future__ import annotations

from typing import Iterable

import pytest

from fred_core.security.models import Resource
from fred_core.security.rebac.capability_authz import (
    team_capability_subject_and_context,
    usable_capability_ids,
)
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    CapabilityPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
)


class _FakeRebacEngine(RebacEngine):
    """Minimal `RebacEngine` stand-in — only `lookup_resources` is exercised
    by `usable_capability_ids`; every other abstract method is a stub."""

    def __init__(
        self,
        *,
        resource_ids: list[str] | None = None,
        disabled: bool = False,
    ) -> None:
        self._resource_ids = resource_ids or []
        self._disabled = disabled
        self.received_subject: RebacReference | None = None
        self.received_permission: RebacPermission | None = None
        self.received_resource_type: Resource | None = None
        self.received_contextual_relations: list[Relation] = []

    async def _persist_relation(self, relation: Relation) -> str | None:
        return None

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
    ) -> list[RebacReference] | RebacDisabledResult:
        self.received_subject = subject
        self.received_permission = permission
        self.received_resource_type = resource_type
        self.received_contextual_relations = list(contextual_relations or [])
        if self._disabled:
            return RebacDisabledResult()
        return [
            RebacReference(type=resource_type, id=rid) for rid in self._resource_ids
        ]

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


@pytest.mark.asyncio
async def test_usable_capability_ids_returns_ids_from_lookup() -> None:
    rebac = _FakeRebacEngine(resource_ids=["model__openai__gpt-5", "mcp__search"])

    result = await usable_capability_ids(rebac, "team-1")

    assert result == {"model__openai__gpt-5", "mcp__search"}
    assert rebac.received_subject == RebacReference(type=Resource.TEAM, id="team-1")
    assert rebac.received_permission == CapabilityPermission.CAN_USE
    assert rebac.received_resource_type == Resource.CAPABILITY
    assert rebac.received_contextual_relations == [
        Relation(
            subject=RebacReference(type=Resource.TEAM, id="team-1"),
            relation=RelationType.TEAM,
            resource=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
        )
    ]


@pytest.mark.asyncio
async def test_usable_capability_ids_returns_none_when_rebac_disabled() -> None:
    rebac = _FakeRebacEngine(disabled=True)

    result = await usable_capability_ids(rebac, "team-1")

    assert result is None


def test_team_capability_subject_and_context_omits_personal_edge_for_regular_team() -> (
    None
):
    _subject, context = team_capability_subject_and_context("team-1")
    assert [c.relation for c in context] == [RelationType.TEAM]


def test_team_capability_subject_and_context_includes_personal_edge_for_personal_team() -> (
    None
):
    _subject, context = team_capability_subject_and_context("personal-alice")
    assert {c.relation for c in context} == {
        RelationType.TEAM,
        RelationType.PERSONAL_TEAM,
    }
