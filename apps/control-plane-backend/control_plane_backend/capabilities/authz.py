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
MCP (`mcp:<id>`) capabilities are not part of the FGA `capability` type (they are
governed by the pod MCP catalog / team policy) and are therefore never filtered
here — only real capabilities are scoped.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

from fred_core import CapabilityPermission, KeycloakUser, RebacDisabledResult
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.mcp_ids import is_mcp_capability_id

logger = logging.getLogger(__name__)


async def usable_capability_ids(
    rebac: RebacEngine, user: KeycloakUser
) -> set[str] | None:
    """Real (non-MCP) capability ids a user may use (`ListObjects` — RFC §8.1).

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

    MCP capabilities are always allowed here (out of the FGA type's scope). The
    noop engine returns True, so ReBAC-disabled deployments allow everything.
    """

    if is_mcp_capability_id(capability_id):
        return True
    return await rebac.has_user_permission(
        user, CapabilityPermission.CAN_USE, capability_id
    )


def filter_entries_by_usable(
    entries: Sequence[CapabilityCatalogEntry],
    usable_ids: set[str] | None,
) -> list[CapabilityCatalogEntry]:
    """Drop admin-gated capabilities the user cannot use from a catalog list.

    `usable_ids=None` (ReBAC disabled) leaves the list untouched. MCP entries
    always pass through.
    """

    if usable_ids is None:
        return list(entries)
    return [
        entry
        for entry in entries
        if is_mcp_capability_id(entry.id) or entry.id in usable_ids
    ]


def unusable_selected_ids(
    selected_ids: Iterable[str], usable_ids: set[str] | None
) -> list[str]:
    """Selected real capabilities the user may NOT use (agent-save rejection)."""

    if usable_ids is None:
        return []
    return [
        cap_id
        for cap_id in selected_ids
        if not is_mcp_capability_id(cap_id) and cap_id not in usable_ids
    ]
