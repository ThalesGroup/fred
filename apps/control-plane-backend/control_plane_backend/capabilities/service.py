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
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacEngine,
    Relation,
    RelationType,
)
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import (
    MODEL_CAPABILITY_NAMESPACE_PREFIX,
    TeamScopePolicy,
)

from control_plane_backend.capabilities.catalog import aggregate_capability_catalog
from control_plane_backend.capabilities.enablement import (
    ORG_REF,
    CapabilityNotFound,
    ReasoningNotSupported,
    cap_ref,
    capability_relation_subjects,
    disable_capability_for_team,
    enable_capability_for_team,
    ensure_capability_anchor,
    get_capability_relations_cached,
    has_org_relation,
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
    ModelReasoningResult,
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


def _catalog_entry_for_revoke(
    catalog: Mapping[str, CapabilityCatalogEntry], capability_id: str
) -> CapabilityCatalogEntry:
    """Like `_catalog_entry`, but for a REVOKE-direction write only (disable,
    reset, or default-on turned OFF) — never for granting access.

    `disable_capability_for_team` / `reset_capability_for_team` /
    `set_capability_default_on(on=False)` only ever read `catalog_entry.id`
    off the entry they're given (they delete tuples and suspend dependents by
    id — they don't consult settings/team-scope). So for a `kind="model"` id
    a fresh catalog fetch failed to re-advertise, a full entry isn't actually
    needed to carry out the revoke; requiring one anyway means an admin
    cannot revoke a live model grant for exactly as long as the model pod's
    `/agents/models-catalog` endpoint is having trouble (2026-08-01, GitHub
    #2191) — fail-OPEN on an authorization-management surface. `kind="tool"`/
    `"agent"` ids are NOT given this fallback: their entries carry
    `team_settings_fields` other write paths (e.g. a subsequent enable) rely
    on, and their catalog absence already has other handling (health-unknown
    suspension) this stub would bypass silently.
    """

    entry = catalog.get(capability_id)
    if entry is not None:
        return entry
    if capability_id.startswith(MODEL_CAPABILITY_NAMESPACE_PREFIX):
        return CapabilityCatalogEntry(
            id=capability_id,
            version="0",
            name=capability_id,
            description=capability_id,
            icon="neurology",
            kind="model",
            team_scope=TeamScopePolicy.ADMIN_GATED,
        )
    raise CapabilityNotFound(
        f"Capability {capability_id!r} is not advertised by any runtime pod."
    )


def _fold_personal_scope(
    relations: list[Relation] | RebacDisabledResult,
) -> PersonalScope:
    """Derive the personal-space class tri-state from the two org-subject
    tuples (RFC §8.4), folded from an already-fetched relation set. `enabled`
    wins if both are somehow present (matches the FGA setter, which never
    leaves both)."""

    if ORGANIZATION_ID in capability_relation_subjects(
        relations, RelationType.PERSONAL_ON, Resource.ORGANIZATION
    ):
        return "enabled"
    if ORGANIZATION_ID in capability_relation_subjects(
        relations, RelationType.PERSONAL_DISABLED, Resource.ORGANIZATION
    ):
        return "disabled"
    return "default"


async def _read_personal_scope(rebac: RebacEngine, capability_id: str) -> PersonalScope:
    """Derive the personal-space class tri-state for one capability (RFC §8.4).

    #2181: its only caller left is `set_personal_scope`'s peek-before-mutate
    (`scope_before`, used to detect the access-transition that decides
    whether to revive suspended dependents) — a write-path decision, so this
    deliberately does NOT go through `get_capability_relations_cached` (see
    `has_org_relation`'s docstring for why: caching here would risk acting on
    up to 45s-stale state from another replica's write, for no benefit to the
    read-only listing path, which never calls this). Still `list_direct_
    relations` (a `Read`), not `lookup_subjects` (`ListUsers`) — cheaper per
    call even uncached.

    Codex review (#2181 PR): narrowed to `subject=ORG_REF`, same reasoning as
    `has_org_relation` — this only ever needs the org-subject tuples, not
    every team's grant on the capability.
    """

    relations = await rebac.list_direct_relations(
        cap_ref(capability_id), subject=ORG_REF
    )
    return _fold_personal_scope(relations)


async def _build_enablement_item(
    entry: CapabilityCatalogEntry,
    *,
    rebac: RebacEngine,
    total_team_count: int,
    total_personal_space_count: int,
    impact: Mapping[str, CapabilityImpact],
    reasoning_enabled_ids: frozenset[str],
) -> CapabilityEnablementItem:
    """Build one row's ReBAC-derived fields.

    #2089: originally 4 concurrent `lookup_subjects` reads per row. #2181
    follow-up: `enabled`/`disabled` team grants and `default_on`/personal-scope
    org markers all live on the SAME literal tuple set for this capability, so
    they no longer need 4 separate OpenFGA round-trips (5, counting
    `_read_personal_scope`'s own pair) — one cached `list_direct_relations`
    Read (`get_capability_relations_cached`) is fetched ONCE here and folded
    locally, the same "fetch once, derive many" shape `_bulk_team_membership`/
    `_fold_team_role_relations` already use for teams. Fetching once (instead
    of gathering several calls that would each independently race the same
    cache key) also avoids a per-row thundering herd on a cold cache.
    """

    relations = await get_capability_relations_cached(rebac, entry.id)
    default_on = ORGANIZATION_ID in capability_relation_subjects(
        relations, RelationType.DEFAULT_ON, Resource.ORGANIZATION
    )
    enabled_team_ids = sorted(
        capability_relation_subjects(relations, RelationType.ENABLED, Resource.TEAM)
    )
    disabled_team_ids = sorted(
        capability_relation_subjects(relations, RelationType.DISABLED, Resource.TEAM)
    )
    personal_scope = _fold_personal_scope(relations)
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
        # REASON-01 §5.3: derived pod-side, carried verbatim. Empty for every
        # kind but "model", and for models with no thinking-capable profile —
        # which is exactly when the admin row shows no reasoning control.
        thinking_profile_ids=list(entry.model_thinking_profile_ids),
        # §5.6 — no stored row means off. One pre-fetched set for the whole
        # list, not a per-row query.
        reasoning_enabled=entry.id in reasoning_enabled_ids,
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
    from control_plane_backend.product.service import _pod_catalog_fetch_scope

    # These 4 steps are mutually independent (none consumes another's result),
    # so run them concurrently instead of one after another (#2089). Platform-
    # wide denominators (collaborative teams for default-on inheritance §8.5,
    # personal spaces for personal-class access §8.4) and resting health
    # (#1975: one ReBAC `ListObjects` per team holding instances, `collect_instances`
    # names the broken agents inline so the health-column drill-down needs no
    # second endpoint) all fold into the same gather as the catalog fetch.
    # `_pod_catalog_fetch_scope()` de-dupes the pod `/agents/templates` fetch
    # that `aggregate_capability_catalog` and `compute_capability_impact`
    # would otherwise each make independently (#2089).
    with _pod_catalog_fetch_scope():
        (
            catalog,
            total_team_count,
            total_personal_space_count,
            impact,
            reasoning_enabled_ids,
        ) = await asyncio.gather(
            aggregate_capability_catalog(deps),
            count_all_collaborative_teams(deps.team_dependencies),
            count_all_personal_spaces(deps.team_dependencies),
            compute_capability_impact(deps, collect_instances=True),
            # REASON-01 §5: one table read for the whole list, joined per row
            # below — never a query per model.
            deps.get_model_reasoning_store().list_enabled_model_ids(),
        )
    reasoning_enabled_ids = frozenset(reasoning_enabled_ids)
    # Per-row ReBAC reads are independent across rows too (#2089) — gather
    # every row's build instead of awaiting them one at a time. #2181: each
    # row's build is now also a single cached `list_direct_relations` Read
    # (see `_build_enablement_item`) instead of several `lookup_subjects`
    # calls, so this outer gather now bounds ~87 concurrent Reads on a cold
    # cache (0 on a warm one) rather than ~175 concurrent ListUsers calls.
    items = list(
        await asyncio.gather(
            *(
                _build_enablement_item(
                    entry,
                    rebac=rebac,
                    total_team_count=total_team_count,
                    total_personal_space_count=total_personal_space_count,
                    impact=impact,
                    reasoning_enabled_ids=reasoning_enabled_ids,
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
    entry = _catalog_entry_for_revoke(catalog, capability_id)
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
    entry = _catalog_entry_for_revoke(catalog, capability_id)
    default_on = await has_org_relation(rebac, capability_id, RelationType.DEFAULT_ON)
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
    # Granting (on=True) needs the REAL entry — it reads `team_settings_fields`
    # to enforce `DefaultOnNotAllowed`, which a stub can't safely fake. Turning
    # default-on OFF is a revoke and only needs `.id` (see
    # `_catalog_entry_for_revoke`).
    entry = (
        _catalog_entry(catalog, capability_id)
        if default_on
        else _catalog_entry_for_revoke(catalog, capability_id)
    )
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
    # Switching a model OFF switches its reasoning off with it (REASON-01 §5.7).
    # The two axes are independent by design — access has a subject, reasoning
    # does not — but they are not independent in THIS direction: leaving a
    # stored `reasoning_enabled` behind on a model the admin just withdrew means
    # re-enabling the model later silently brings reasoning back, which nobody
    # asked for. Fail-closed, and one-directional on purpose: turning a model on
    # still does not turn its reasoning on.
    reasoning_disabled = False
    if not default_on and entry.kind == "model":
        store = deps.get_model_reasoning_store()
        # Read first so a model nobody ever toggled keeps NO row: an absent row
        # and a stored `false` mean the same thing (§5.6), and writing one here
        # would put a row on every model an admin ever switched off.
        if capability_id in await store.list_enabled_model_ids():
            await store.set_enabled(
                model_capability_id=capability_id,
                reasoning_enabled=False,
                updated_by=user.uid,
            )
            reasoning_disabled = True
            logger.info(
                "[capability-reasoning] model=%s reasoning switched off with the "
                "model itself by=%s",
                capability_id,
                user.uid,
            )
    return CapabilityDefaultOnResult(
        capability_id=capability_id,
        default_on=default_on,
        suspended_instances=suspended,
        revived_instances=revived,
        reasoning_disabled=reasoning_disabled,
    )


async def set_model_reasoning(
    *,
    user: KeycloakUser,
    capability_id: str,
    reasoning_enabled: bool,
    deps: ProductServiceDependencies,
) -> ModelReasoningResult:
    """Switch one model's reasoning on or off, platform-wide (REASON-01,
    `MODEL-REASONING-ENABLEMENT-RFC.md` §5).

    Sits in this service and behind the same `can_manage` gate as `default_on`
    because it is the same admin surface — but it writes a plain table row, not
    a ReBAC tuple, and that difference is the design (§5.1): reasoning has no
    subject. It is not "who may use this model" (that stays on `can_use`,
    untouched), it is "how the model runs" for whoever already may.

    Rejects a capability with no thinking-capable profile: aptitude is declared
    in `models_catalog.yaml` and no admin action can grant it (§5.3).

    Takes effect at the next session preparation — the flag rides the
    `ExecutionPreparation` snapshot (§5.5), so sessions already open keep the
    setting they started with. That is the intended lifecycle, the same one the
    team routing policy uses, and it is why this is a live *operational* lever
    (§9): switching a model's reasoning off stops the next session from
    reasoning without a redeploy.
    """

    rebac = _rebac(deps)
    await _require_can_manage(rebac, user, capability_id)
    catalog = await aggregate_capability_catalog(deps)
    entry = _catalog_entry(catalog, capability_id)
    if entry.kind != "model" or not entry.model_thinking_profile_ids:
        raise ReasoningNotSupported(
            f"Capability {capability_id!r} has no reasoning-capable model profile "
            "— its reasoning cannot be switched on. Aptitude is declared per "
            "profile in models_catalog.yaml (`supports_thinking`), not granted "
            "by an administrator."
        )
    await deps.get_model_reasoning_store().set_enabled(
        model_capability_id=capability_id,
        reasoning_enabled=reasoning_enabled,
        updated_by=user.uid,
    )
    logger.info(
        "[capability-reasoning] model=%s reasoning_enabled=%s by=%s",
        capability_id,
        reasoning_enabled,
        user.uid,
    )
    return ModelReasoningResult(
        capability_id=capability_id, reasoning_enabled=reasoning_enabled
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
    default_on = await has_org_relation(rebac, capability_id, RelationType.DEFAULT_ON)
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
