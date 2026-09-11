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
    APPLICATION_CAPABILITY_NAMESPACE_PREFIX,
    CapabilityEnablementFacts,
    can_team_use_capability,
    can_team_use_from_facts,
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


def test_legacy_application_catalog_prefix_remains_compatible() -> None:
    assert APPLICATION_CAPABILITY_NAMESPACE_PREFIX == "app__"


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
        await can_team_use_capability(rebac, "team-1", capability_id="report_export")
        is True
    )
    assert rebac.checked == [
        (
            RebacReference(type=Resource.TEAM, id="team-1"),
            CapabilityPermission.CAN_USE,
            RebacReference(type=Resource.CAPABILITY, id="report_export"),
        )
    ]
    assert [
        [c.relation for c in call] for call in rebac.checked_contextual_relations
    ] == [[RelationType.TEAM]]


@pytest.mark.asyncio
async def test_can_team_use_capability_reports_denial() -> None:
    rebac = FakeRebacEngine(permitted=False)

    assert (
        await can_team_use_capability(rebac, "team-1", capability_id="report_export")
        is False
    )


@pytest.mark.asyncio
async def test_can_team_use_capability_allows_when_rebac_is_disabled() -> None:
    assert (
        await can_team_use_capability(
            NoopRebacEngine(), "team-1", capability_id="report_export"
        )
        is True
    )


# ---------------------------------------------------------------------------
# The local fold: `can_use` derived from a capability's direct tuples, used by
# the admin health column instead of one `ListObjects` per team.
# ---------------------------------------------------------------------------

_CAPABILITY = RebacReference(type=Resource.CAPABILITY, id="corp_drive")
ORG = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)
TEAM_A = RebacReference(type=Resource.TEAM, id="team-a")
PERSONAL_U1 = RebacReference(type=Resource.TEAM, id="personal-u1")


def _team_relation(team_id: str, relation: RelationType) -> Relation:
    return Relation(
        subject=RebacReference(type=Resource.TEAM, id=team_id),
        relation=relation,
        resource=_CAPABILITY,
    )


def _org_relation(relation: RelationType) -> Relation:
    return Relation(subject=ORG, relation=relation, resource=_CAPABILITY)


# Each row is one branch of `capability#can_use`, with the expected value
# written by hand from `schema.fga` - never derived from the production formula.
_CAN_USE_CASES = [
    ("explicit grant", "team-a", [(TEAM_A, RelationType.ENABLED)], True),
    (
        "explicit disabled beats an explicit grant",
        "team-a",
        [(TEAM_A, RelationType.ENABLED), (TEAM_A, RelationType.DISABLED)],
        False,
    ),
    (
        "default_on inherits for a team",
        "team-a",
        [(ORG, RelationType.DEFAULT_ON)],
        True,
    ),
    (
        "default_on inherits for a personal space",
        "personal-u1",
        [(ORG, RelationType.DEFAULT_ON)],
        True,
    ),
    (
        "personal_on grants the personal class",
        "personal-u1",
        [(ORG, RelationType.PERSONAL_ON)],
        True,
    ),
    (
        "personal_on does not reach a collaborative team",
        "team-a",
        [(ORG, RelationType.PERSONAL_ON)],
        False,
    ),
    (
        "personal_disabled blocks default_on for the personal class",
        "personal-u1",
        [(ORG, RelationType.DEFAULT_ON), (ORG, RelationType.PERSONAL_DISABLED)],
        False,
    ),
    (
        "personal_disabled leaves a collaborative team alone",
        "team-a",
        [(ORG, RelationType.DEFAULT_ON), (ORG, RelationType.PERSONAL_DISABLED)],
        True,
    ),
    (
        "an explicit grant survives personal_disabled",
        "personal-u1",
        [
            (ORG, RelationType.DEFAULT_ON),
            (ORG, RelationType.PERSONAL_DISABLED),
            (PERSONAL_U1, RelationType.ENABLED),
        ],
        True,
    ),
    (
        "another team's grant does not leak",
        "team-b",
        [(TEAM_A, RelationType.ENABLED)],
        False,
    ),
]


@pytest.mark.parametrize(
    "team_id,tuples,expected",
    [(case[1], case[2], case[3]) for case in _CAN_USE_CASES],
    ids=[case[0] for case in _CAN_USE_CASES],
)
def test_can_team_use_from_facts_matches_the_schema(
    team_id: str,
    tuples: list[tuple[RebacReference, RelationType]],
    expected: bool,
) -> None:
    """One row per branch of `capability#can_use`. The fold stands in for an
    OpenFGA `Check`, so a divergence here is a wrong admin health column."""

    relations = [_org_relation(RelationType.ORGANIZATION)] + [
        Relation(subject=subject, relation=relation, resource=_CAPABILITY)
        for subject, relation in tuples
    ]

    facts = CapabilityEnablementFacts.from_relations(relations)

    assert can_team_use_from_facts(team_id, facts) is expected


def test_from_relations_ignores_the_organization_anchor_and_foreign_subjects() -> None:
    """The anchor tuple and any non-team `enabled`/`disabled` subject carry no
    `can_use` weight - folding them in would grant a team that holds neither."""

    facts = CapabilityEnablementFacts.from_relations(
        [
            _org_relation(RelationType.ORGANIZATION),
            _org_relation(RelationType.ENABLED),
            Relation(
                subject=RebacReference(type=Resource.USER, id="alice"),
                relation=RelationType.DISABLED,
                resource=_CAPABILITY,
            ),
            _team_relation("team-a", RelationType.ENABLED),
        ]
    )

    assert facts == CapabilityEnablementFacts(
        enabled=frozenset({"team-a"}),
        disabled=frozenset(),
        default_on=False,
        personal_on=False,
        personal_disabled=False,
    )


def test_from_relations_keeps_other_teams_grants_separate() -> None:
    """One fold answers for every team, so a grant held by another team must
    never leak into the asking team's verdict."""

    facts = CapabilityEnablementFacts.from_relations(
        [_team_relation("team-a", RelationType.ENABLED)]
    )

    assert can_team_use_from_facts("team-a", facts) is True
    assert can_team_use_from_facts("team-b", facts) is False
    assert can_team_use_from_facts("personal-u1", facts) is False
