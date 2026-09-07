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

import pytest

from fred_core.security.models import Resource
from fred_core.security.rebac.capability_authz import (
    can_team_use_capability,
    team_capability_subject_and_context,
    usable_capability_ids,
)
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    CapabilityPermission,
    RebacReference,
    Relation,
    RelationType,
)
from fred_core.tests.security.rebac_fakes import FakeRebacEngine


@pytest.mark.asyncio
async def test_usable_capability_ids_returns_ids_from_lookup() -> None:
    rebac = FakeRebacEngine(resource_ids=["model__openai__gpt-5", "mcp__search"])

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
    rebac = FakeRebacEngine(disabled=True)

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


@pytest.mark.asyncio
async def test_can_team_use_capability_is_a_single_check_with_team_context() -> None:
    rebac = FakeRebacEngine(permitted=True)

    assert (
        await can_team_use_capability(
            rebac, "team-1", capability_id="app__acme-forecast"
        )
        is True
    )
    assert rebac.checked == [
        (
            RebacReference(type=Resource.TEAM, id="team-1"),
            CapabilityPermission.CAN_USE,
            RebacReference(type=Resource.CAPABILITY, id="app__acme-forecast"),
        )
    ]
    assert [
        [c.relation for c in call] for call in rebac.checked_contextual_relations
    ] == [[RelationType.TEAM]]


@pytest.mark.asyncio
async def test_can_team_use_capability_reports_denial() -> None:
    rebac = FakeRebacEngine(permitted=False)

    assert (
        await can_team_use_capability(
            rebac, "team-1", capability_id="app__acme-forecast"
        )
        is False
    )


@pytest.mark.asyncio
async def test_can_team_use_capability_allows_when_rebac_is_disabled() -> None:
    assert (
        await can_team_use_capability(
            NoopRebacEngine(), "team-1", capability_id="app__acme-forecast"
        )
        is True
    )
