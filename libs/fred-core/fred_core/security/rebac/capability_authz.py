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
Team-subject `can_use` capability queries (CAPAB-01 / #1980, RFC §8.1).

The one shared query control-plane (catalog listing, agent-save check) and
fred-runtime (per-turn model authorization, `AGENT-CAPABILITY-RFC.md` §8.7)
both need: "which capability ids may this team's agents use?" — same OpenFGA
relations, same personal-team contextual-edge handling, in both callers
(2026-08-03, GitHub #2191 follow-up item RSK-B/#16 in
`NOTES-OBSERV-02-FOLLOWUPS.md`). Control-plane and fred-runtime are separate
deployables with no shared import path for either one's own code, but both
already depend on `fred-core` — this is that one shared copy, replacing what
used to be two independently-maintained, field-for-field-identical copies.

The check SUBJECT IS THE TEAM the agent belongs to, never the browsing user:
enablement is a per-team fact, and a user-subject check would answer "is this
user in ANY enabled team", leaking a capability enabled for one of the user's
teams into every team context they browse.
"""

from __future__ import annotations

from dataclasses import dataclass

from fred_core.common.team_id import is_personal_team_id
from fred_core.security.models import Resource
from fred_core.security.rebac.application_authz import (
    APPLICATION_CAPABILITY_NAMESPACE_PREFIX as APPLICATION_CAPABILITY_NAMESPACE_PREFIX,
)
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    CapabilityPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    team_subject_and_context,
)

__all__ = [
    "APPLICATION_CAPABILITY_NAMESPACE_PREFIX",
    "CapabilityEnablementFacts",
    "can_team_use_capability",
    "can_team_use_from_facts",
    "team_capability_subject_and_context",
    "usable_capability_ids",
]


def team_capability_subject_and_context(
    team_id: str,
) -> tuple[RebacReference, list[Relation]]:
    """Team check subject + the contextual `organization#team` reverse edge.

    For a PERSONAL space (`personal-{uid}`) the personal-only
    `organization#personal_team` edge is injected too, so the personal-space
    capability class (`personal_on`/`personal_disabled`, RFC §8.4) resolves for
    that subject and no regular team ever picks up the class position. Both
    edges are CONTEXTUAL tuples, supplied at check time, never persisted —
    every team belongs to the singleton organization by construction.
    """

    return team_subject_and_context(team_id)


@dataclass(frozen=True)
class CapabilityEnablementFacts:
    """One capability's direct tuples, folded into the five facts `can_use`
    needs: the teams holding an explicit grant or opt-out, plus the three
    org-subject markers."""

    enabled: frozenset[str]
    disabled: frozenset[str]
    default_on: bool
    personal_on: bool
    personal_disabled: bool

    @classmethod
    def from_relations(cls, relations: list[Relation]) -> "CapabilityEnablementFacts":
        """Fold the direct tuple set of ONE capability object.

        Anything else on the object (the `organization` anchor, a non-team
        subject on `enabled`/`disabled`) carries no `can_use` weight and is
        dropped.
        """

        enabled: set[str] = set()
        disabled: set[str] = set()
        org_markers: set[RelationType] = set()
        for rel in relations:
            if rel.subject.type == Resource.TEAM:
                if rel.relation == RelationType.ENABLED:
                    enabled.add(rel.subject.id)
                elif rel.relation == RelationType.DISABLED:
                    disabled.add(rel.subject.id)
            elif (
                rel.subject.type == Resource.ORGANIZATION
                and rel.subject.id == ORGANIZATION_ID
            ):
                org_markers.add(rel.relation)
        return cls(
            enabled=frozenset(enabled),
            disabled=frozenset(disabled),
            default_on=RelationType.DEFAULT_ON in org_markers,
            personal_on=RelationType.PERSONAL_ON in org_markers,
            personal_disabled=RelationType.PERSONAL_DISABLED in org_markers,
        )


def can_team_use_from_facts(team_id: str, facts: CapabilityEnablementFacts) -> bool:
    """`can_use` derived locally, without asking OpenFGA.

    Mirrors `schema.fga`'s `capability#can_use` line for line and MUST change
    with it; the `organization#team` / `organization#personal_team` edges are
    contextual, so they are always true here. Display-only - never an
    admission decision (`docs/swift/platform/REBAC.md`).
    """

    personal = is_personal_team_id(team_id)
    inherited = (facts.default_on or (personal and facts.personal_on)) and not (
        personal and facts.personal_disabled
    )
    return (team_id in facts.enabled or inherited) and team_id not in facts.disabled


async def usable_capability_ids(rebac: RebacEngine, team_id: str) -> set[str] | None:
    """Capability ids one team's agents may use (`ListObjects` — RFC §8.1).

    Returns `None` when ReBAC is disabled, signalling "no scoping" so the
    caller leaves the catalog/authorization unfiltered (everything is public
    in that mode).
    """

    team_ref, context = team_capability_subject_and_context(team_id)
    refs = await rebac.lookup_resources(
        team_ref,
        CapabilityPermission.CAN_USE,
        Resource.CAPABILITY,
        contextual_relations=context,
    )
    if isinstance(refs, RebacDisabledResult):
        return None
    return {ref.id for ref in refs}


async def can_team_use_capability(
    rebac: RebacEngine, team_id: str, *, capability_id: str
) -> bool:
    """One team, one capability: a single `Check` instead of a `ListObjects`.

    Same subject and contextual edges as `usable_capability_ids`. With ReBAC
    disabled the engine answers `True`, matching the unfiltered catalog.
    """

    team_ref, context = team_capability_subject_and_context(team_id)
    return await rebac.has_permission(
        team_ref,
        CapabilityPermission.CAN_USE,
        RebacReference(type=Resource.CAPABILITY, id=capability_id),
        contextual_relations=context,
    )
