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

`_team_subject_and_context`/`usable_capability_ids` are re-exported from
`fred_core.security.rebac.capability_authz` (2026-08-03, RSK-B follow-up to
#2191) rather than defined here: fred-runtime's `model_routing/authz.py`
needs the exact same team-subject query for its own `can_use` check and used
to keep an independent, field-for-field-identical copy of both — moved into
`fred-core` (both packages already depend on it) so there is exactly one
copy. `can_use_capability` stays here — control-plane-only, no fred-runtime
caller.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from fred_core import CapabilityPermission
from fred_core.common import TeamId
from fred_core.security.models import Resource
from fred_core.security.rebac.capability_authz import (
    team_capability_subject_and_context as _team_subject_and_context,
)
from fred_core.security.rebac.capability_authz import (
    usable_capability_ids as usable_capability_ids,
)
from fred_core.security.rebac.rebac_engine import RebacEngine, RebacReference
from fred_sdk.contracts.capability import CapabilityCatalogEntry

__all__ = ["usable_capability_ids"]

logger = logging.getLogger(__name__)


async def can_use_capability(
    rebac: RebacEngine, team_id: TeamId, capability_id: str
) -> bool:
    """`Check(team:{id}, can_use, capability:{id})` (agent save / session prep).

    Every capability — including MCP-backed ones (#1988) — is gated by this
    check. The noop engine returns True, so ReBAC-disabled deployments allow
    everything.
    """

    team_ref, context = _team_subject_and_context(str(team_id))
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
