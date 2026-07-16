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
Admin capability-enablement service (CAPAB-01 / #1980, RFC §8.5).

The request-scoped layer over `enablement.py`: aggregates the pod catalog,
enforces the `capability#can_manage` gate, and delegates the writes. Kept out of
`product/service.py` so this whole feature is one merge-isolated package.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from fred_core import CapabilityPermission, KeycloakUser, RebacDisabledResult
from fred_core.common import TeamId
from fred_core.security.rebac.rebac_engine import RebacEngine, RelationType
from fred_core.security.models import Resource
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import TeamScopePolicy

from control_plane_backend.capabilities.catalog import aggregate_capability_catalog
from control_plane_backend.capabilities.enablement import (
    CapabilityNotFound,
    _cap_ref,
    disable_capability_for_team,
    enable_capability_for_team,
    ensure_capability_anchor,
    reset_capability_for_team,
    set_capability_default_on,
)
from control_plane_backend.capabilities.schemas import (
    CapabilityDefaultOnResult,
    CapabilityEnablementItem,
    CapabilityEnablementList,
    TeamCapabilityEnablementResult,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.teams.service import count_all_collaborative_teams

logger = logging.getLogger(__name__)


def _rebac(deps: ProductServiceDependencies) -> RebacEngine:
    return deps.team_dependencies.rebac


async def _require_can_manage(
    rebac: RebacEngine, user: KeycloakUser, capability_id: str
) -> None:
    """Gate a mutation on `capability#can_manage` (org admin, RFC §8.1/§8.5).

    The capability is anchored first (idempotent) so `can_manage` resolves even
    for a brand-new capability an admin has never touched.
    """

    await ensure_capability_anchor(rebac, capability_id)
    await rebac.check_user_permission_or_raise(
        user, CapabilityPermission.CAN_MANAGE, capability_id
    )


def _catalog_entry(
    catalog: Mapping[str, CapabilityCatalogEntry], capability_id: str
) -> CapabilityCatalogEntry:
    entry = catalog.get(capability_id)
    if entry is None:
        raise CapabilityNotFound(
            f"Capability {capability_id!r} is not advertised by any runtime pod."
        )
    return entry


async def _teams_with_relation(
    rebac: RebacEngine, capability_id: str, relation: RelationType
) -> list[str]:
    subjects = await rebac.lookup_subjects(
        _cap_ref(capability_id), relation, Resource.TEAM
    )
    if isinstance(subjects, RebacDisabledResult):
        return []
    return sorted(ref.id for ref in subjects)


async def _is_default_on(rebac: RebacEngine, capability_id: str) -> bool:
    from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID

    subjects = await rebac.lookup_subjects(
        _cap_ref(capability_id), RelationType.DEFAULT_ON, Resource.ORGANIZATION
    )
    if isinstance(subjects, RebacDisabledResult):
        return False
    return any(ref.id == ORGANIZATION_ID for ref in subjects)


async def list_capability_enablement(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> CapabilityEnablementList:
    """List every advertised capability with its scope + enablement state (§8.5)."""

    rebac = _rebac(deps)
    # Aggregate-list read gate: `can_manage` is org-admin, so probe it on the
    # organization singleton via the same admin relation.
    await _require_manage_any(rebac, user)

    catalog = await aggregate_capability_catalog(deps)
    # Platform-wide denominator for default-on inheritance (§8.5). Fetched once
    # for the whole list — it is the same for every capability.
    total_team_count = await count_all_collaborative_teams(deps.team_dependencies)
    items: list[CapabilityEnablementItem] = []
    for entry in catalog.values():
        items.append(
            CapabilityEnablementItem(
                id=entry.id,
                name=entry.name,
                version=entry.version,
                icon=entry.icon,
                team_scope=entry.team_scope,
                default_on=await _is_default_on(rebac, entry.id),
                enabled_team_ids=await _teams_with_relation(
                    rebac, entry.id, RelationType.ENABLED
                ),
                disabled_team_ids=await _teams_with_relation(
                    rebac, entry.id, RelationType.DISABLED
                ),
                total_team_count=total_team_count,
                team_settings_fields=list(entry.team_settings_fields),
            )
        )
    items.sort(key=lambda item: item.id)
    return CapabilityEnablementList(items=items)


async def _require_manage_any(rebac: RebacEngine, user: KeycloakUser) -> None:
    """Org-admin gate for the aggregate list (equivalent to `can_manage`)."""

    from fred_core import OrganizationPermission
    from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID

    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    )


async def enable_team_capability(
    *,
    user: KeycloakUser,
    capability_id: str,
    team_id: TeamId,
    settings: Mapping[str, Any],
    deps: ProductServiceDependencies,
) -> TeamCapabilityEnablementResult:
    rebac = _rebac(deps)
    await _require_can_manage(rebac, user, capability_id)
    catalog = await aggregate_capability_catalog(deps)
    entry = _catalog_entry(catalog, capability_id)
    validated = await enable_capability_for_team(
        rebac=rebac,
        settings_store=deps.get_team_capability_settings_store(),
        catalog_entry=entry,
        team_id=team_id,
        settings=settings,
        updated_by=user.uid,
    )
    return TeamCapabilityEnablementResult(
        capability_id=capability_id,
        team_id=str(team_id),
        enabled=True,
        settings=validated,
    )


async def disable_team_capability(
    *,
    user: KeycloakUser,
    capability_id: str,
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> TeamCapabilityEnablementResult:
    rebac = _rebac(deps)
    await _require_can_manage(rebac, user, capability_id)
    catalog = await aggregate_capability_catalog(deps)
    entry = _catalog_entry(catalog, capability_id)
    suspended = await disable_capability_for_team(
        rebac=rebac,
        settings_store=deps.get_team_capability_settings_store(),
        agent_instance_store=deps.get_agent_instance_store(),
        catalog_entry=entry,
        team_id=team_id,
        kpi_writer=deps.get_kpi_writer(),
    )
    return TeamCapabilityEnablementResult(
        capability_id=capability_id,
        team_id=str(team_id),
        enabled=False,
        suspended_instances=suspended,
    )


async def reset_team_capability(
    *,
    user: KeycloakUser,
    capability_id: str,
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> TeamCapabilityEnablementResult:
    """Drop the team's explicit grant/opt-out so the platform default applies
    (the "default" segment of the admin tri-state matrix, RFC §8.5)."""

    rebac = _rebac(deps)
    await _require_can_manage(rebac, user, capability_id)
    catalog = await aggregate_capability_catalog(deps)
    entry = _catalog_entry(catalog, capability_id)
    default_on = await _is_default_on(rebac, capability_id)
    suspended = await reset_capability_for_team(
        rebac=rebac,
        agent_instance_store=deps.get_agent_instance_store(),
        catalog_entry=entry,
        team_id=team_id,
        default_on=default_on,
        kpi_writer=deps.get_kpi_writer(),
    )
    return TeamCapabilityEnablementResult(
        capability_id=capability_id,
        team_id=str(team_id),
        enabled=default_on,
        suspended_instances=suspended,
    )


async def set_default_on(
    *,
    user: KeycloakUser,
    capability_id: str,
    default_on: bool,
    deps: ProductServiceDependencies,
) -> CapabilityDefaultOnResult:
    rebac = _rebac(deps)
    await _require_can_manage(rebac, user, capability_id)
    catalog = await aggregate_capability_catalog(deps)
    entry = _catalog_entry(catalog, capability_id)
    suspended = await set_capability_default_on(
        rebac=rebac,
        agent_instance_store=deps.get_agent_instance_store(),
        catalog_entry=entry,
        on=default_on,
        kpi_writer=deps.get_kpi_writer(),
    )
    return CapabilityDefaultOnResult(
        capability_id=capability_id,
        default_on=default_on,
        suspended_instances=suspended,
    )


# `TeamScopePolicy` re-exported for callers that build items without importing
# from fred_sdk directly.
__all__ = [
    "TeamScopePolicy",
    "list_capability_enablement",
    "enable_team_capability",
    "disable_team_capability",
    "reset_team_capability",
    "set_default_on",
]
