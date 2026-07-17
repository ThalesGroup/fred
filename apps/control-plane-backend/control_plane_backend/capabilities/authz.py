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
Read-side capability authorization (CAPAB-01 / #1980, RFC §8.1).

The `can_use` half consumed by the catalog listing and the agent-save check.
Callers here NEVER touch the structural tuples — they only ask `can_use`.
Every capability id is FGA-gated the same way — an MCP-backed capability's id
is the plain catalog server id now (#1988, supersedes the `mcp:<id>` bypass),
so it is an ordinary `capability` object in the FGA type and is scoped here
like any other.

The check SUBJECT IS THE TEAM the agent belongs to, never the browsing user:
enablement is a per-team fact, and a user-subject check would answer "is this
user in ANY enabled team", leaking a capability enabled for one of the user's
teams into every team context they browse (and letting them save it there).
The user's membership in the team is enforced by the route (`get_team_by_id`)
before these helpers run. Each check injects the derived
`organization:fred#team@team:<id>` reverse edge as a CONTEXTUAL tuple so the
`default_on` path resolves for team subjects — every team belongs to the
singleton organization, so the edge is never persisted.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from fred_core import CapabilityPermission, RebacDisabledResult
from fred_core.common import TeamId
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
)
from fred_sdk.contracts.capability import CapabilityCatalogEntry

logger = logging.getLogger(__name__)


def _team_subject_and_context(
    team_id: TeamId,
) -> tuple[RebacReference, list[Relation]]:
    """Team check subject + the contextual `organization#team` reverse edge."""

    team_ref = RebacReference(type=Resource.TEAM, id=str(team_id))
    context = [
        Relation(
            subject=team_ref,
            relation=RelationType.TEAM,
            resource=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
        )
    ]
    return team_ref, context


async def usable_capability_ids(rebac: RebacEngine, team_id: TeamId) -> set[str] | None:
    """Capability ids one team's agents may use (`ListObjects` — RFC §8.1).

    Returns None when ReBAC is disabled, signalling "no scoping" so the caller
    leaves the catalog unfiltered (everything is public in that mode).
    """

    team_ref, context = _team_subject_and_context(team_id)
    refs = await rebac.lookup_resources(
        team_ref,
        CapabilityPermission.CAN_USE,
        Resource.CAPABILITY,
        contextual_relations=context,
    )
    if isinstance(refs, RebacDisabledResult):
        return None
    return {ref.id for ref in refs}


async def can_use_capability(
    rebac: RebacEngine, team_id: TeamId, capability_id: str
) -> bool:
    """`Check(team:{id}, can_use, capability:{id})` (agent save / session prep).

    Every capability — including MCP-backed ones (#1988) — is gated by this
    check. The noop engine returns True, so ReBAC-disabled deployments allow
    everything.
    """

    team_ref, context = _team_subject_and_context(team_id)
    return await rebac.has_permission(
        team_ref,
        CapabilityPermission.CAN_USE,
        RebacReference(type=Resource.CAPABILITY, id=capability_id),
        contextual_relations=context,
    )


def filter_entries_by_usable(
    entries: Sequence[CapabilityCatalogEntry],
    usable_ids: set[str] | None,
) -> list[CapabilityCatalogEntry]:
    """Drop admin-gated capabilities the team cannot use from a catalog list.

    `usable_ids=None` (ReBAC disabled) leaves the list untouched. MCP-backed
    entries are gated exactly like any other capability now (#1988).
    """

    if usable_ids is None:
        return list(entries)
    return [entry for entry in entries if entry.id in usable_ids]


def unusable_selected_ids(
    selected_ids: Iterable[str], usable_ids: set[str] | None
) -> list[str]:
    """Selected capabilities the team may NOT use (agent-save rejection).

    MCP-backed capabilities are gated like any other id now (#1988).
    """

    if usable_ids is None:
        return []
    return [cap_id for cap_id in selected_ids if cap_id not in usable_ids]
