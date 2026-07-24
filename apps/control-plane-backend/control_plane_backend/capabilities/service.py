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

import asyncio
import logging
from typing import Any, Mapping

from fred_core import CapabilityPermission, KeycloakUser, RebacDisabledResult
from fred_core.common import TeamId, is_personal_team_id
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
    is_template_capability_instance,
    reset_capability_for_team,
    revive_dependent_instances,
    set_capability_default_on,
    set_capability_personal_scope,
)
from control_plane_backend.capabilities.impact import (
    CapabilityImpact,
    compute_capability_impact,
    preview_revoke_impact,
    resolve_availability_for_team,
)
from control_plane_backend.capabilities.schemas import (
    CapabilityDefaultOnResult,
    CapabilityEnablementItem,
    CapabilityEnablementList,
    CapabilityImpactPreview,
    CapabilityPersonalScopeResult,
    ImpactedInstanceSummary,
    PersonalScope,
    TeamCapabilityEnablementResult,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.teams.service import (
    count_all_collaborative_teams,
    count_all_personal_spaces,
)

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


async def _has_org_relation(
    rebac: RebacEngine, capability_id: str, relation: RelationType
) -> bool:
    from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID

    subjects = await rebac.lookup_subjects(
        _cap_ref(capability_id), relation, Resource.ORGANIZATION
    )
    if isinstance(subjects, RebacDisabledResult):
        return False
    return any(ref.id == ORGANIZATION_ID for ref in subjects)


async def _read_personal_scope(rebac: RebacEngine, capability_id: str) -> PersonalScope:
    """Derive the personal-space class tri-state from the two org-subject tuples
    (RFC §8.4). `enabled` wins if both are somehow present (matches the FGA
    setter, which never leaves both)."""

    if await _has_org_relation(rebac, capability_id, RelationType.PERSONAL_ON):
        return "enabled"
    if await _has_org_relation(rebac, capability_id, RelationType.PERSONAL_DISABLED):
        return "disabled"
    return "default"


async def _build_enablement_item(
    entry: CapabilityCatalogEntry,
    *,
    rebac: RebacEngine,
    total_team_count: int,
    total_personal_space_count: int,
    impact: Mapping[str, CapabilityImpact],
) -> CapabilityEnablementItem:
    """Build one row's ReBAC-derived fields (#2089).

    The 4 lookups below are independent `lookup_subjects` reads on different
    relations of the same capability — gathering them turns 4 sequential
    OpenFGA round-trips per row into 1.
    """

    (
        default_on,
        enabled_team_ids,
        disabled_team_ids,
        personal_scope,
    ) = await asyncio.gather(
        _is_default_on(rebac, entry.id),
        _teams_with_relation(rebac, entry.id, RelationType.ENABLED),
        _teams_with_relation(rebac, entry.id, RelationType.DISABLED),
        _read_personal_scope(rebac, entry.id),
    )
    entry_impact = impact.get(entry.id)
    return CapabilityEnablementItem(
        id=entry.id,
        name=entry.name,
        version=entry.version,
        icon=entry.icon,
        team_scope=entry.team_scope,
        default_on=default_on,
        enabled_team_ids=enabled_team_ids,
        disabled_team_ids=disabled_team_ids,
        total_team_count=total_team_count,
        total_personal_space_count=total_personal_space_count,
        personal_scope=personal_scope,
        team_settings_fields=list(entry.team_settings_fields),
        kind=entry.kind,
        suspended_instances=entry_impact.suspended_instances if entry_impact else 0,
        health_unknown_instances=(
            entry_impact.skipped_unreachable if entry_impact else 0
        ),
        suspended_instance_details=(
            [
                ImpactedInstanceSummary(
                    agent_instance_id=item.agent_instance_id,
                    team_id=item.team_id,
                    display_name=item.display_name,
                )
                for item in entry_impact.instances
            ]
            if entry_impact
            else []
        ),
    )


async def list_capability_enablement(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> CapabilityEnablementList:
    """List every advertised capability with its scope + enablement state (§8.5)."""

    rebac = _rebac(deps)
    # Aggregate-list read gate: `can_manage` is org-admin, so probe it on the
    # organization singleton via the same admin relation. Kept before every
    # other step below — authorization must resolve before any of this
    # request's work runs.
    await _require_manage_any(rebac, user)

    # Lazy import breaks the product.service ↔ capabilities import cycle, same
    # reason `catalog.py`/`impact.py` defer their own product.service imports.
    from control_plane_backend.product.service import _template_fetch_scope

    # These 4 steps are mutually independent (none consumes another's result),
    # so run them concurrently instead of one after another (#2089). Platform-
    # wide denominators (collaborative teams for default-on inheritance §8.5,
    # personal spaces for personal-class access §8.4) and resting health
    # (#1975: one ReBAC `ListObjects` per team holding instances, `collect_instances`
    # names the broken agents inline so the health-column drill-down needs no
    # second endpoint) all fold into the same gather as the catalog fetch.
    # `_template_fetch_scope()` de-dupes the pod `/agents/templates` fetch that
    # `aggregate_capability_catalog` and `compute_capability_impact` would
    # otherwise each make independently (#2089).
    with _template_fetch_scope():
        (
            catalog,
            total_team_count,
            total_personal_space_count,
            impact,
        ) = await asyncio.gather(
            aggregate_capability_catalog(deps),
            count_all_collaborative_teams(deps.team_dependencies),
            count_all_personal_spaces(deps.team_dependencies),
            compute_capability_impact(deps, collect_instances=True),
        )
    # Per-row ReBAC reads are independent across rows too (#2089) — gather
    # every row's build instead of awaiting them one at a time.
    items = list(
        await asyncio.gather(
            *(
                _build_enablement_item(
                    entry,
                    rebac=rebac,
                    total_team_count=total_team_count,
                    total_personal_space_count=total_personal_space_count,
                    impact=impact,
                )
                for entry in catalog.values()
            )
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
        updated_by=user.uid,
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
        updated_by=user.uid,
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
        # A team is a revive candidate whether its dependent selected
        # `capability_id` as a TOOL, or IS an instance of it as a
        # `kind="agent"` template (2026-07-19, GitHub #2004 item 2) — the
        # gathering must match `_suspend_instance_for_revoked_capability`'s
        # two suspension conditions, or a team suspended only via the
        # template condition is never revived.
        team_ids = {
            instance.team_id
            for instance in await agent_instance_store.list_all()
            if capability_id in (instance.tuning.selected_capability_ids or [])
            or is_template_capability_instance(instance, capability_id)
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


async def _revive_personal_after_grant(
    *, capability_id: str, deps: ProductServiceDependencies
) -> int:
    """Clear the personal-space suspensions a personal-scope GRANT resolves —
    the personal-class counterpart of `_revive_after_grant` above (#1975 seam).

    Runs AFTER the class tuple write. Scoped to PERSONAL-space teams that hold
    a suspended dependent selecting the capability, revived one team at a time
    through `_revive_after_grant` so the real per-team availability facts
    (ReBAC `can_use` + pod manifest) decide each instance, never a synthetic
    set — the same guarantee that leaves a `capability_config_invalid`
    suspension or an unreachable-pod instance untouched.
    """

    agent_instance_store = deps.get_agent_instance_store()
    # Same broadened match as `set_default_on` above: a suspended personal-space
    # dependent qualifies whether it selected `capability_id` as a TOOL or IS an
    # instance of it as a `kind="agent"` template (GitHub #2004 item 2).
    personal_team_ids = {
        instance.team_id
        for instance in await agent_instance_store.list_all()
        if instance.is_suspended
        and is_personal_team_id(str(instance.team_id))
        and (
            capability_id in (instance.tuning.selected_capability_ids or [])
            or is_template_capability_instance(instance, capability_id)
        )
    }
    revived = 0
    for team_id in personal_team_ids:
        revived += await _revive_after_grant(
            capability_id=capability_id, team_id=team_id, deps=deps
        )
    return revived


async def set_personal_scope(
    *,
    user: KeycloakUser,
    capability_id: str,
    scope: PersonalScope,
    deps: ProductServiceDependencies,
) -> CapabilityPersonalScopeResult:
    """Set the personal-space class tri-state for a capability (RFC §8.4)."""

    rebac = _rebac(deps)
    await _require_can_manage(rebac, user, capability_id)
    catalog = await aggregate_capability_catalog(deps)
    entry = _catalog_entry(catalog, capability_id)

    # Peeked BEFORE the write (same "peek, mutate, decide" shape as
    # `reset_team_capability`'s `default_on` read above) so the grant/revoke
    # transition can be told apart afterward. `default_on` does not move
    # during this call — only the two personal-class tuples do — so one read
    # covers both the before and after side of the access formula.
    scope_before = await _read_personal_scope(rebac, capability_id)
    default_on = await _is_default_on(rebac, capability_id)
    had_access = scope_before == "enabled" or (scope_before == "default" and default_on)

    suspended = await set_capability_personal_scope(
        rebac=rebac,
        agent_instance_store=deps.get_agent_instance_store(),
        catalog_entry=entry,
        scope=scope,
        kpi_writer=deps.get_kpi_writer(),
        updated_by=user.uid,
    )

    # Mirrors the team/default-on grant paths above: a transition that GRANTS
    # personal-space access must revive the suspensions it resolves, or an
    # agent suspended by an earlier scope loss stays suspended until an
    # unrelated reconciliation or manual save.
    has_access = scope == "enabled" or (scope == "default" and default_on)
    revived = (
        await _revive_personal_after_grant(capability_id=capability_id, deps=deps)
        if not had_access and has_access
        else 0
    )

    return CapabilityPersonalScopeResult(
        capability_id=capability_id,
        scope=scope,
        suspended_instances=suspended,
        revived_instances=revived,
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
    "set_personal_scope",
]
