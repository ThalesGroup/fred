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
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from fred_core import CapabilityPermission, KeycloakUser, RebacDisabledResult
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_sdk.contracts.capability import CapabilityCatalogEntry

logger = logging.getLogger(__name__)


async def usable_capability_ids(
    rebac: RebacEngine, user: KeycloakUser
) -> set[str] | None:
    """Capability ids a user may use (`ListObjects` — RFC §8.1).

    Returns None when ReBAC is disabled, signalling "no scoping" so the caller
    leaves the catalog unfiltered (everything is public in that mode).
    """

    refs = await rebac.lookup_user_resources(user, CapabilityPermission.CAN_USE)
    if isinstance(refs, RebacDisabledResult):
        return None
    return {ref.id for ref in refs}


async def can_use_capability(
    rebac: RebacEngine, user: KeycloakUser, capability_id: str
) -> bool:
    """`Check(user, can_use, capability:{id})` (agent save / session prep).

    Every capability — including MCP-backed ones (#1988) — is gated by this
    check. The noop engine returns True, so ReBAC-disabled deployments allow
    everything.
    """

    return await rebac.has_user_permission(
        user, CapabilityPermission.CAN_USE, capability_id
    )


def filter_entries_by_usable(
    entries: Sequence[CapabilityCatalogEntry],
    usable_ids: set[str] | None,
) -> list[CapabilityCatalogEntry]:
    """Drop admin-gated capabilities the user cannot use from a catalog list.

    `usable_ids=None` (ReBAC disabled) leaves the list untouched. MCP-backed
    entries are gated exactly like any other capability now (#1988).
    """

    if usable_ids is None:
        return list(entries)
    return [entry for entry in entries if entry.id in usable_ids]


def unusable_selected_ids(
    selected_ids: Iterable[str], usable_ids: set[str] | None
) -> list[str]:
    """Selected capabilities the user may NOT use (agent-save rejection).

    MCP-backed capabilities are gated like any other id now (#1988).
    """

    if usable_ids is None:
        return []
    return [cap_id for cap_id in selected_ids if cap_id not in usable_ids]
