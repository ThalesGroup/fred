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
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import RebacEngine, RelationType
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
    revive_dependent_instances,
    set_capability_default_on,
)
from control_plane_backend.capabilities.impact import (
    compute_capability_impact,
    preview_revoke_impact,
    resolve_availability_for_team,
)
from control_plane_backend.capabilities.schemas import (
    CapabilityDefaultOnResult,
    CapabilityEnablementItem,
    CapabilityEnablementList,
    CapabilityImpactPreview,
    ImpactedInstanceSummary,
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
    # Resting health for the WHOLE catalog in one pass (#1975): one ReBAC
    # `ListObjects` per team holding instances plus one template fetch per pod,
    # rather than a lookup per row. Admin-only screen, so the extra round-trips
    # buy the most accurate answer available.
    impact = await compute_capability_impact(deps)
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
                kind=entry.kind,
                suspended_instances=(
                    impact[entry.id].suspended_instances if entry.id in impact else 0
                ),
                health_unknown_instances=(
                    impact[entry.id].skipped_unreachable if entry.id in impact else 0
                ),
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


async def _revive_after_grant(
    *,
    capability_id: str,
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> int:
    """Clear the suspensions a fresh grant resolves (the #1980 → #1975 seam).

    Runs AFTER the enabling tuple write so the `can_use` lookup observes the new
    grant. Every grant path funnels through here: without it a revoked-then-
    re-enabled capability leaves its agents suspended forever, because the only
    other clear path is the reconciliation sweep — which has no scheduled host
    yet (#1975 names the Temporal lifecycle queue as the intended one).
    """

    agent_instance_store = deps.get_agent_instance_store()
    instances = await agent_instance_store.list_by_team(team_id)
    source_runtime_ids = {instance.source_runtime_id for instance in instances}
    if not source_runtime_ids:
        return 0
    usable_ids, available_by_source = await resolve_availability_for_team(
        deps, team_id=team_id, source_runtime_ids=source_runtime_ids
    )
    return await revive_dependent_instances(
        agent_instance_store=agent_instance_store,
        capability_id=capability_id,
        usable_capability_ids=usable_ids,
        available_by_source=available_by_source,
        team_id=team_id,
        kpi_writer=deps.get_kpi_writer(),
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
    revived = await _revive_after_grant(
        capability_id=capability_id, team_id=team_id, deps=deps
    )
    return TeamCapabilityEnablementResult(
        capability_id=capability_id,
        team_id=str(team_id),
        enabled=True,
        settings=validated,
        revived_instances=revived,
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
    # Reset onto a default-ON platform is a GRANT (the team keeps access by
    # inheritance), so it must revive exactly like an explicit enable — the
    # reset path previously bare-returned 0 here and stranded its dependents.
    revived = (
        await _revive_after_grant(
            capability_id=capability_id, team_id=team_id, deps=deps
        )
        if default_on
        else 0
    )
    return TeamCapabilityEnablementResult(
        capability_id=capability_id,
        team_id=str(team_id),
        enabled=default_on,
        suspended_instances=suspended,
        revived_instances=revived,
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
    # Turning default-on ON grants inherited access platform-wide, so it revives
    # across EVERY team holding dependents — not one team like the enable path.
    # Teams with an explicit `disabled` opt-out keep their suspension: the
    # per-team `can_use` lookup below still answers False for them, so the
    # reconcile re-suspends rather than clears. That is the tri-state working,
    # not a special case.
    revived = 0
    if default_on:
        agent_instance_store = deps.get_agent_instance_store()
        team_ids = {
            instance.team_id
            for instance in await agent_instance_store.list_all()
            if capability_id in (instance.tuning.selected_capability_ids or [])
        }
        for team_id in team_ids:
            revived += await _revive_after_grant(
                capability_id=capability_id, team_id=team_id, deps=deps
            )
    return CapabilityDefaultOnResult(
        capability_id=capability_id,
        default_on=default_on,
        suspended_instances=suspended,
        revived_instances=revived,
    )


async def preview_capability_revoke(
    *,
    user: KeycloakUser,
    capability_id: str,
    team_id: TeamId | None,
    deps: ProductServiceDependencies,
) -> CapabilityImpactPreview:
    """Preview what revoking a capability would break (the confirm dialog).

    `team_id=None` previews a platform-wide default-off; a team id previews that
    one team's disable. Read-only — same `can_manage` gate as the mutation it
    precedes, so the preview never reveals more than the admin may already do.
    """

    rebac = _rebac(deps)
    await _require_can_manage(rebac, user, capability_id)
    impact = await preview_revoke_impact(
        deps, capability_id=capability_id, team_id=team_id
    )
    return CapabilityImpactPreview(
        capability_id=capability_id,
        suspended_instances=impact.suspended_instances,
        health_unknown_instances=impact.skipped_unreachable,
        instances=[
            ImpactedInstanceSummary(
                agent_instance_id=item.agent_instance_id,
                team_id=item.team_id,
                display_name=item.display_name,
            )
            for item in impact.instances
        ],
    )


# `TeamScopePolicy` re-exported for callers that build items without importing
# from fred_sdk directly.
__all__ = [
    "TeamScopePolicy",
    "list_capability_enablement",
    "enable_team_capability",
    "disable_team_capability",
    "reset_team_capability",
    "preview_capability_revoke",
    "set_default_on",
]
