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

Every team-subject `can_use` query lives in
`fred_core.security.rebac.capability_authz` and is re-exported here: the
control-plane, fred-runtime and first-party application backends all need the
identical subject and contextual edges, and fred-core is the one package they
all depend on. What stays in this module is the catalog-shaped filtering the
control plane alone performs on the answer.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from fred_core.security.rebac.capability_authz import (
    can_team_use_capability as can_team_use_capability,
)
from fred_core.security.rebac.capability_authz import (
    usable_capability_ids as usable_capability_ids,
)
from fred_sdk.contracts.capability import CapabilityCatalogEntry

__all__ = ["can_team_use_capability", "usable_capability_ids"]


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
