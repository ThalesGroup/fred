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
Per-team capability enablement — the write path (CAPAB-01 / #1980, RFC §8.1–§8.4).

The one place that mutates capability authorization. Every write goes through
here so the RFC invariants hold in exactly one spot:

- **Write ordering (RFC §8.2):** enable = settings row THEN the `enabled` tuple
  (a half-failure leaves the capability *disabled*, never
  enabled-without-settings); disable = delete the tuple, KEEP the row.
- **Revocation → suspension (#1975 seam):** when a team loses `can_use` on a
  capability, its dependent agent instances are suspended
  (`CAPABILITY_ACCESS_REVOKED`) through `reconcile_instance_suspension` — the
  entry point #1975 exposed for exactly this.
- **Callers check only `can_use`/`can_manage`** — this module writes the
  structural tuples (`organization` anchor / `enabled` / `disabled` /
  `default_on`) they never touch directly.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Iterable, Literal, Mapping

from fred_core.common import TeamId, ThreadSafeLRUCache, is_personal_team_id
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
)
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.models import FieldSpec

from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.agent_instances.suspension import (
    SuspensionReason,
    clear_suspension,
    reconcile_instance_suspension,
    suspend_instance,
)
from control_plane_backend.capabilities.authz import usable_capability_ids
from control_plane_backend.capabilities.settings_store import (
    TeamCapabilitySettingsStore,
)

if TYPE_CHECKING:
    # Only ever imported lazily at runtime (see `has_org_relation`/
    # `capability_relation_subjects` below) to avoid a `fred_core` import
    # cycle; a `TYPE_CHECKING`-guarded import is enough for the type
    # annotations that reference it (`__future__` annotations mean the
    # annotation is never evaluated at runtime either way).
    from fred_core import RebacDisabledResult

logger = logging.getLogger(__name__)

ORG_REF = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)


class CapabilityNotFound(Exception):
    """A capability id that the aggregated pod catalog does not advertise."""

    http_status = 404


class CapabilitySettingsInvalid(Exception):
    """Submitted team settings do not validate against `team_settings_fields`."""

    http_status = 422


class DefaultOnNotAllowed(Exception):
    """A capability with required team settings cannot be seeded/toggled default-on."""

    http_status = 409


class PersonalScopeNotAllowed(Exception):
    """A capability with required team settings cannot be class-enabled for all
    personal spaces — nobody has filled the settings (RFC §8.4, mirrors §8.2)."""

    http_status = 409


class ApplicationTeamScopeNotAllowed(Exception):
    """V1 applications may be enabled only for collaborative teams."""

    http_status = 409


class AgentCapabilityDependencyNotSatisfied(Exception):
    """A `kind="agent"` capability's default tool capabilities are not all
    usable yet by the team/personal-scope being granted (RFC §8.6, 2026-07-19
    `depends_on` fast-follow, GitHub #2004 item 5)."""

    http_status = 409


class ReasoningNotSupported(Exception):
    """A reasoning toggle was written against a capability that is not a model,
    or is a model with no thinking-capable profile (REASON-01,
    `MODEL-REASONING-ENABLEMENT-RFC.md` §5.3).

    Rejected rather than stored: aptitude is declared in `models_catalog.yaml`
    and an administrator cannot grant it. Silently accepting the row would
    persist an activation that can never have an effect, and would put a
    control in the admin UI that lies about what it does — precisely the
    "decorative flag" failure §5.6.2 exists to prevent.
    """

    http_status = 409


async def agent_capability_missing_dependencies(
    rebac: RebacEngine, catalog_entry: CapabilityCatalogEntry, team_id: TeamId
) -> list[str]:
    """Ids in `catalog_entry.default_capability_ids` NOT yet `can_use` for
    `team_id` — the `depends_on` fast-follow's pure predicate (RFC §8.6,
    2026-07-19, GitHub #2004 item 5).

    Reuses `default_capability_ids` — the template's own declared MCP-server
    defaults, projected onto the catalog entry by `_agent_capabilities_for_source`
    — as the sole source of truth for "what this agent needs." Always empty
    for `kind="tool"` entries (no defaults by construction) and when ReBAC is
    disabled (`usable_capability_ids` returns `None`, meaning no scoping
    applies). Exposed as a public, non-raising predicate so a caller that
    needs to SKIP-AND-REPORT rather than reject (e.g. the
    `grant_existing_teams_served_templates` compatibility sweep, which must
    stay best-effort even in `dry_run`) doesn't have to catch an exception to
    get the same answer `enable_capability_for_team` rejects on below.
    """

    if catalog_entry.kind != "agent" or not catalog_entry.default_capability_ids:
        return []
    usable = await usable_capability_ids(rebac, team_id)
    if usable is None:
        return []
    return [cid for cid in catalog_entry.default_capability_ids if cid not in usable]


async def _require_agent_capability_dependencies_usable_by_team(
    rebac: RebacEngine, catalog_entry: CapabilityCatalogEntry, team_id: TeamId
) -> None:
    """Fix A of the `depends_on` fast-follow: refuse to grant a `kind="agent"`
    capability to one team unless every id in its `default_capability_ids` is
    already `can_use` for that same team."""

    missing = await agent_capability_missing_dependencies(rebac, catalog_entry, team_id)
    if missing:
        raise AgentCapabilityDependencyNotSatisfied(
            f"Cannot enable agent capability {catalog_entry.id!r} for team "
            f"{team_id!r}: its default tool capability id(s) {missing!r} are "
            "not usable by this team yet. Enable them for this team first."
        )


async def _require_agent_capability_dependencies_usable_by_all_personal_spaces(
    rebac: RebacEngine, catalog_entry: CapabilityCatalogEntry
) -> None:
    """Personal-scope counterpart of the check above: refuse to class-enable a
    `kind="agent"` capability for every personal space unless each of its
    `default_capability_ids` already has org-level personal access — i.e. is
    itself `personal_on` or `default_on` (and not `personal_disabled`).

    There is no single concrete team to run `usable_capability_ids` against
    here (the grant applies to every personal space at once), so this reads
    the same org-subject markers `set_capability_personal_scope` itself reads
    to decide `had_access`/`has_access` for the capability being toggled.
    """

    if catalog_entry.kind != "agent" or not catalog_entry.default_capability_ids:
        return
    missing: list[str] = []
    for cap_id in catalog_entry.default_capability_ids:
        personal_on = await has_org_relation(rebac, cap_id, RelationType.PERSONAL_ON)
        default_on = await has_org_relation(rebac, cap_id, RelationType.DEFAULT_ON)
        personal_disabled = await has_org_relation(
            rebac, cap_id, RelationType.PERSONAL_DISABLED
        )
        if not ((personal_on or default_on) and not personal_disabled):
            missing.append(cap_id)
    if missing:
        raise AgentCapabilityDependencyNotSatisfied(
            f"Cannot class-enable agent capability {catalog_entry.id!r} for all "
            f"personal spaces: its default tool capability id(s) {missing!r} "
            "are not usable by every personal space yet. Enable them for "
            "personal spaces (or default-on) first."
        )


def cap_ref(capability_id: str) -> RebacReference:
    return RebacReference(type=Resource.CAPABILITY, id=capability_id)


def _team_ref(team_id: TeamId) -> RebacReference:
    return RebacReference(type=Resource.TEAM, id=str(team_id))


def _is_personal_application_team(team_id: TeamId) -> bool:
    # The admin API accepts the same reserved alias as other team routes. It
    # cannot canonicalize it without the target user's identity, but it can
    # still fail closed before writing any application grant.
    return str(team_id) == "personal" or is_personal_team_id(str(team_id))


def _reject_personal_team_application_grant(
    catalog_entry: CapabilityCatalogEntry, team_id: TeamId
) -> None:
    if catalog_entry.kind == "app" and _is_personal_application_team(team_id):
        raise ApplicationTeamScopeNotAllowed(
            f"Application {catalog_entry.id!r} cannot be enabled for personal "
            "teams; V1 applications are collaborative-team-only."
        )


def _type_of(field: FieldSpec) -> str:
    # `FieldSpec.type` is a `FieldType` Literal (a plain str at runtime).
    return str(field.type)


def team_settings_has_required_fields(field_specs: Iterable[FieldSpec]) -> bool:
    """True when any team-settings field is required (fences default-on, §8.2)."""

    return any(getattr(field, "required", False) for field in field_specs)


def validate_team_settings(
    field_specs: list[FieldSpec], submitted: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate submitted enablement settings against the capability's
    `team_settings_fields` (RFC §8.2 typed enablement).

    Rejects unknown keys, enforces `required`, and checks scalar type coherence.
    Returns the cleaned settings dict (declared keys only). Raises
    `CapabilitySettingsInvalid` (HTTP 422) on any violation.
    """

    specs_by_key = {field.key: field for field in field_specs}
    unknown = set(submitted) - set(specs_by_key)
    if unknown:
        raise CapabilitySettingsInvalid(
            f"Unknown team-settings key(s): {sorted(unknown)!r}."
        )

    cleaned: dict[str, Any] = {}
    for key, field in specs_by_key.items():
        if key not in submitted or submitted[key] is None:
            if getattr(field, "required", False):
                raise CapabilitySettingsInvalid(
                    f"Required team-settings field {key!r} is missing."
                )
            continue
        value = submitted[key]
        ftype = _type_of(field)
        if ftype in {"string", "text", "text-multiline", "prompt", "secret", "url"}:
            if not isinstance(value, str):
                raise CapabilitySettingsInvalid(f"Field {key!r} must be a string.")
        elif ftype == "select":
            if not isinstance(value, str):
                raise CapabilitySettingsInvalid(f"Field {key!r} must be a string.")
            if field.enum is not None and value not in field.enum:
                raise CapabilitySettingsInvalid(
                    f"Field {key!r} must be one of {field.enum!r}."
                )
        elif ftype == "boolean":
            if not isinstance(value, bool):
                raise CapabilitySettingsInvalid(f"Field {key!r} must be a boolean.")
        elif ftype == "integer":
            if not (isinstance(value, int) and not isinstance(value, bool)):
                raise CapabilitySettingsInvalid(f"Field {key!r} must be an integer.")
        elif ftype == "number":
            if not (isinstance(value, (int, float)) and not isinstance(value, bool)):
                raise CapabilitySettingsInvalid(f"Field {key!r} must be a number.")
        else:
            raise CapabilitySettingsInvalid(
                f"Field {key!r} has unsupported team-settings type {ftype!r}."
            )
        cleaned[key] = value
    return cleaned


async def ensure_capability_anchor(rebac: RebacEngine, capability_id: str) -> None:
    """Idempotently anchor a capability to the singleton organization so its
    `can_manage` / `can_use` permissions resolve (RFC §8.1)."""

    await rebac.add_relation(
        Relation(
            subject=ORG_REF,
            relation=RelationType.ORGANIZATION,
            resource=cap_ref(capability_id),
        )
    )


async def enable_capability_for_team(
    *,
    rebac: RebacEngine,
    settings_store: TeamCapabilitySettingsStore | None,
    catalog_entry: CapabilityCatalogEntry,
    team_id: TeamId,
    settings: Mapping[str, Any],
    updated_by: str | None,
) -> dict[str, Any]:
    """Enable one capability for one team with validated settings (RFC §8.2).

    Write ordering: the settings row is persisted FIRST, then the `enabled`
    tuple — so a crash between the two leaves the capability disabled, never
    enabled-without-settings.

    Reviving the instances this grant unblocks is the CALLER's second step (see
    `revive_dependent_instances`): it needs the live ReBAC + pod facts, which
    this module deliberately does not fetch, and it must run AFTER the tuple
    write below so the `can_use` lookup observes the new grant.
    """

    _reject_personal_team_application_grant(catalog_entry, team_id)
    validated = validate_team_settings(
        list(catalog_entry.team_settings_fields), settings
    )
    await _require_agent_capability_dependencies_usable_by_team(
        rebac, catalog_entry, team_id
    )
    # 1. Settings row first (configuration half). V1 applications deliberately
    # have no generic team-settings payload: this store is also consumed by
    # agent-runtime paths that applications do not use.
    if catalog_entry.kind != "app":
        if settings_store is None:
            raise RuntimeError("settings_store is required for non-app capabilities")
        await settings_store.upsert(
            team_id=team_id,
            capability_id=catalog_entry.id,
            settings=validated,
            updated_by=updated_by,
        )
    # 2. Authorization half: anchor, clear any opt-out, then grant.
    await ensure_capability_anchor(rebac, catalog_entry.id)
    try:
        await rebac.delete_relation(
            Relation(
                subject=_team_ref(team_id),
                relation=RelationType.DISABLED,
                resource=cap_ref(catalog_entry.id),
            )
        )
        await rebac.add_relation(
            Relation(
                subject=_team_ref(team_id),
                relation=RelationType.ENABLED,
                resource=cap_ref(catalog_entry.id),
            ),
            actor_uid=updated_by,
        )
    finally:
        # Codex review (#2181 PR): the `delete` above can succeed and the
        # `add` still raise — invalidating only after both means a cached
        # reader keeps reporting the pre-write (disabled) state for a full
        # TTL despite OpenFGA's state having already changed. `finally`
        # covers that half-failure the same way a full success does; an
        # extra invalidate on the (rarer) all-writes-failed path just costs
        # one avoidable refetch, never a correctness problem.
        invalidate_capability_relations_cache(catalog_entry.id)
    logger.info(
        "[capability-enablement] enabled capability=%s team=%s by=%s",
        catalog_entry.id,
        team_id,
        updated_by,
    )
    return validated


async def disable_capability_for_team(
    *,
    rebac: RebacEngine,
    settings_store: TeamCapabilitySettingsStore | None,
    agent_instance_store: AgentInstanceStore | None,
    catalog_entry: CapabilityCatalogEntry,
    team_id: TeamId,
    kpi_writer: BaseKPIWriter | None = None,
    updated_by: str | None = None,
) -> int:
    """Disable one capability for one team and suspend its dependents (§8.2, #1975).

    The `enabled` tuple is deleted (the settings row is KEPT so a later
    re-enable restores prior settings) and a `disabled` opt-out tuple is
    written — always, not only for default-on capabilities, so the explicit
    disable survives a later default-on flip and reads back as the "disabled"
    position in the admin tri-state matrix. Every dependent agent instance is
    then suspended with `CAPABILITY_ACCESS_REVOKED`. Returns the number of
    instances suspended.
    """

    try:
        await rebac.delete_relation(
            Relation(
                subject=_team_ref(team_id),
                relation=RelationType.ENABLED,
                resource=cap_ref(catalog_entry.id),
            )
        )
        await rebac.add_relation(
            Relation(
                subject=_team_ref(team_id),
                relation=RelationType.DISABLED,
                resource=cap_ref(catalog_entry.id),
            ),
            actor_uid=updated_by,
        )
    finally:
        # See `enable_capability_for_team`'s matching comment (Codex review,
        # #2181 PR): a half-failure between the two writes must not leave a
        # cached reader reporting the pre-write (enabled) state for a TTL.
        invalidate_capability_relations_cache(catalog_entry.id)
    del settings_store  # settings row is intentionally retained (re-enable restores)
    if catalog_entry.kind == "app":
        return 0
    if agent_instance_store is None:
        raise RuntimeError("agent_instance_store is required for non-app capabilities")
    return await suspend_dependent_instances(
        agent_instance_store=agent_instance_store,
        team_id=team_id,
        capability_id=catalog_entry.id,
        kpi_writer=kpi_writer,
    )


async def reset_capability_for_team(
    *,
    rebac: RebacEngine,
    agent_instance_store: AgentInstanceStore | None,
    catalog_entry: CapabilityCatalogEntry,
    team_id: TeamId,
    default_on: bool,
    kpi_writer: BaseKPIWriter | None = None,
) -> int:
    """Clear a team's explicit position so it falls back to the platform
    default (the "default" segment of the admin tri-state matrix).

    Both the `enabled` grant and the `disabled` opt-out are deleted; the
    settings row is kept, like disable, so a later re-enable restores prior
    settings. When the platform default is off the team loses `can_use`, so
    dependents are suspended exactly as an explicit disable would; when it is
    on, access continues by inheritance and nothing is suspended. Returns the
    number of instances suspended.
    """

    if (
        catalog_entry.kind == "app"
        and default_on
        and _is_personal_application_team(team_id)
    ):
        # Resetting a personal-team opt-out while default-on is active would
        # recreate inherited access. Cleanup is still allowed when default-on
        # is off, and explicit disable always remains available.
        raise ApplicationTeamScopeNotAllowed(
            f"Application {catalog_entry.id!r} cannot reset personal team "
            f"{str(team_id)!r} to an enabled platform default."
        )
    try:
        await rebac.delete_relation(
            Relation(
                subject=_team_ref(team_id),
                relation=RelationType.ENABLED,
                resource=cap_ref(catalog_entry.id),
            )
        )
        await rebac.delete_relation(
            Relation(
                subject=_team_ref(team_id),
                relation=RelationType.DISABLED,
                resource=cap_ref(catalog_entry.id),
            )
        )
    finally:
        # See `enable_capability_for_team`'s matching comment (Codex review,
        # #2181 PR): a half-failure between the two deletes must not leave a
        # cached reader reporting the pre-write state for a TTL.
        invalidate_capability_relations_cache(catalog_entry.id)
    if default_on or catalog_entry.kind == "app":
        return 0
    if agent_instance_store is None:
        raise RuntimeError("agent_instance_store is required for non-app capabilities")
    return await suspend_dependent_instances(
        agent_instance_store=agent_instance_store,
        team_id=team_id,
        capability_id=catalog_entry.id,
        kpi_writer=kpi_writer,
    )


def is_template_capability_instance(
    instance: AgentInstanceRecord, capability_id: str
) -> bool:
    """True when `instance` IS an instance of `capability_id`'s `kind="agent"`
    template — i.e. `capability_id` is the template's own id
    (`template_capability_id(instance.source_runtime_id,
    instance.source_agent_id)`), never a selected TOOL capability.

    The single predicate the suspend side
    (`_suspend_instance_for_revoked_capability`) and every revive-side path
    (`revive_dependent_instances` here, and the team-gathering filters in
    `capabilities/service.py`'s `set_default_on` and
    `_revive_personal_after_grant`) must agree on — otherwise a
    template-capability instance suspended one way can never be found the
    other way (2026-07-19, GitHub #2004 item 2).
    """

    from control_plane_backend.product.service import template_capability_id

    return capability_id == template_capability_id(
        instance.source_runtime_id, instance.source_agent_id
    )


async def _suspend_instance_for_revoked_capability(
    *,
    agent_instance_store: AgentInstanceStore,
    instance: AgentInstanceRecord,
    capability_id: str,
    kpi_writer: BaseKPIWriter | None,
) -> bool:
    """Suspend one instance for a revoked capability, whichever way it
    depends on it: as a selected TOOL, or — since 2026-07-19, GitHub #2004
    item 1 — by BEING an instance of `capability_id` when it is a
    `kind="agent"` template capability.

    Why the agent-template case cannot reuse `reconcile_instance_suspension`
    as-is: that entry point (and the `unavailable_capabilities` diff it
    calls) only ever looks at `instance.tuning.selected_capability_ids` — an
    agent template's own id is never added there (only *tool* capabilities an
    instance activated are), so removing it from `available_capability_ids`
    is a no-op the diff would never notice. This suspends directly instead,
    with the same idempotent-on-reason guard `reconcile_instance_suspension`
    applies internally.

    Returns True on a fresh transition into `capability_access_revoked`
    (False if unmatched, or already suspended for that exact reason).
    """

    if is_template_capability_instance(instance, capability_id):
        if (
            instance.suspension_reason
            == SuspensionReason.CAPABILITY_ACCESS_REVOKED.value
        ):
            return False
        await suspend_instance(
            agent_instance_store,
            instance,
            SuspensionReason.CAPABILITY_ACCESS_REVOKED,
            capabilities=[capability_id],
            kpi_writer=kpi_writer,
        )
        return True

    selected = set(instance.tuning.selected_capability_ids or [])
    if capability_id not in selected:
        return False
    reason = await reconcile_instance_suspension(
        instance=instance,
        store=agent_instance_store,
        available_capability_ids=selected - {capability_id},
        revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED,
        kpi_writer=kpi_writer,
    )
    return reason is not None


async def suspend_dependent_instances(
    *,
    agent_instance_store: AgentInstanceStore,
    team_id: TeamId,
    capability_id: str,
    kpi_writer: BaseKPIWriter | None = None,
) -> int:
    """Suspend every one of a team's instances that depends on `capability_id`
    — selected it as a tool, or ARE an instance of it as a `kind="agent"`
    template (the #1980 revocation → #1975 suspension seam; agent-template
    half added 2026-07-19, GitHub #2004 item 1).

    Only dependent instances are touched, so an unrelated availability
    suspension is never clobbered.
    """

    suspended = 0
    for instance in await agent_instance_store.list_by_team(team_id):
        if await _suspend_instance_for_revoked_capability(
            agent_instance_store=agent_instance_store,
            instance=instance,
            capability_id=capability_id,
            kpi_writer=kpi_writer,
        ):
            suspended += 1
    return suspended


async def revive_dependent_instances(
    *,
    agent_instance_store: AgentInstanceStore,
    capability_id: str,
    usable_capability_ids: set[str] | None,
    available_by_source: Mapping[str, frozenset[str] | None],
    team_id: TeamId | None = None,
    kpi_writer: BaseKPIWriter | None = None,
) -> int:
    """Clear the suspensions a capability GRANT resolves — the inverse of
    `suspend_dependent_instances` (the missing half of the #1980 → #1975 seam).

    Why this cannot mirror the revoke path's shortcut: `suspend_dependent_
    instances` fakes the available set as `selected - {capability_id}` because a
    revoke knows exactly what it removed. A grant knows only what it ADDED — it
    cannot conclude the instance is healthy, because a SECOND capability may
    still be revoked or missing from the pod. So the caller must supply the real
    availability facts and let `reconcile_instance_suspension` decide: it clears
    only when NOTHING is missing, and re-suspends otherwise.

    Safe on the reasons it must not touch: the reconcile clears only
    `AVAILABILITY_REASONS`, so a `capability_config_invalid` suspension survives
    untouched — only a successful save clears that (RFC §3.9). Passing the real
    sets rather than a synthetic one is what makes that guarantee hold here.

    `usable_capability_ids=None` means ReBAC is disabled (no scoping). An
    instance whose runtime is absent from `available_by_source` (or maps to
    None) has an unreachable pod and is SKIPPED rather than revived — the same
    fail-to-unknown rule the reconciliation sweep applies (#1975). Returns the
    number of instances whose suspension was cleared.

    A `kind="agent"` template instance (`is_template_capability_instance`,
    2026-07-19, GitHub #2004 item 2) is revived on its own branch: it was never
    suspended via `selected_capability_ids` (the template's own id is never in
    that list — see `_suspend_instance_for_revoked_capability`), so
    `reconcile_instance_suspension`'s selected-capability diff would never see
    it either. It is cleared directly once the team can `can_use` the template
    again, mirroring the direct-suspend branch this reverses.
    """

    instances = (
        await agent_instance_store.list_by_team(team_id)
        if team_id is not None
        else await agent_instance_store.list_all()
    )
    revived = 0
    for instance in instances:
        if not instance.is_suspended:
            continue

        if is_template_capability_instance(instance, capability_id):
            if (
                instance.suspension_reason
                != SuspensionReason.CAPABILITY_ACCESS_REVOKED.value
            ):
                continue
            still_revoked = (
                usable_capability_ids is not None
                and capability_id not in usable_capability_ids
            )
            if still_revoked:
                continue
            await clear_suspension(
                agent_instance_store, instance, kpi_writer=kpi_writer
            )
            revived += 1
            continue

        selected = set(instance.tuning.selected_capability_ids or [])
        # Only instances that selected the granted capability can be revived by
        # this grant; an unrelated suspension is never touched.
        if capability_id not in selected:
            continue
        available_ids = available_by_source.get(instance.source_runtime_id)
        if available_ids is None:
            continue
        # The real available set: what the team may use AND the pod ships. The
        # reconcile clears only if EVERY selected capability is in it.
        effective = (
            selected & available_ids
            if usable_capability_ids is None
            else selected & usable_capability_ids & available_ids
        )
        updated = await reconcile_instance_suspension(
            instance=instance,
            store=agent_instance_store,
            available_capability_ids=effective,
            revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED,
            kpi_writer=kpi_writer,
        )
        # A None return means "no AVAILABILITY reason" — NOT necessarily
        # cleared: a `capability_config_invalid` instance also returns None
        # while `clear_suspension` deliberately leaves its reason intact
        # (RFC §3.9). Re-read the record and count only a real transition to
        # unsuspended, so config-invalid instances are never miscounted.
        if updated is not None:
            continue
        fresh = await agent_instance_store.get(instance.agent_instance_id)
        if fresh is not None and not fresh.is_suspended:
            revived += 1
    return revived


async def set_capability_default_on(
    *,
    rebac: RebacEngine,
    agent_instance_store: AgentInstanceStore | None,
    catalog_entry: CapabilityCatalogEntry,
    on: bool,
    kpi_writer: BaseKPIWriter | None = None,
    updated_by: str | None = None,
) -> int:
    """Toggle a capability's platform-wide `default_on` marker (RFC §8.3).

    Turning it ON is a pure anchor + tuple write. Turning it OFF revokes
    inherited access: every instance selecting the capability whose team lacks
    an explicit `enabled` grant is suspended (`CAPABILITY_ACCESS_REVOKED`).
    A capability with a REQUIRED team-settings field can never be default-on
    (§8.2) — nobody has filled the settings.
    """

    if on:
        if team_settings_has_required_fields(catalog_entry.team_settings_fields):
            raise DefaultOnNotAllowed(
                f"Capability {catalog_entry.id!r} has required team settings and "
                "cannot be default-on."
            )
        await ensure_capability_anchor(rebac, catalog_entry.id)
        try:
            await rebac.add_relation(
                Relation(
                    subject=ORG_REF,
                    relation=RelationType.DEFAULT_ON,
                    resource=cap_ref(catalog_entry.id),
                ),
                actor_uid=updated_by,
            )
        finally:
            invalidate_capability_relations_cache(catalog_entry.id)
        return 0

    try:
        await rebac.delete_relation(
            Relation(
                subject=ORG_REF,
                relation=RelationType.DEFAULT_ON,
                resource=cap_ref(catalog_entry.id),
            )
        )
    finally:
        invalidate_capability_relations_cache(catalog_entry.id)
    # Applications reuse only the authorization tuple. They have no agent
    # instances to suspend or revive when that tuple changes.
    if catalog_entry.kind == "app":
        return 0
    if agent_instance_store is None:
        raise RuntimeError("agent_instance_store is required for non-app capabilities")

    # Teams with an explicit grant keep access; everyone else loses inherited
    # use — whether they used it as a tool or as a `kind="agent"` template
    # (2026-07-19, GitHub #2004 item 1).
    enabled_teams = await explicitly_enabled_team_ids(rebac, catalog_entry.id)
    suspended = 0
    for instance in await agent_instance_store.list_all():
        if str(instance.team_id) in enabled_teams:
            continue
        if await _suspend_instance_for_revoked_capability(
            agent_instance_store=agent_instance_store,
            instance=instance,
            capability_id=catalog_entry.id,
            kpi_writer=kpi_writer,
        ):
            suspended += 1
    return suspended


async def set_capability_personal_scope(
    *,
    rebac: RebacEngine,
    agent_instance_store: AgentInstanceStore,
    catalog_entry: CapabilityCatalogEntry,
    scope: Literal["enabled", "disabled", "default"],
    kpi_writer: BaseKPIWriter | None = None,
    updated_by: str | None = None,
) -> int:
    """Set the personal-space class position for a capability (RFC §8.4).

    The class is a tri-state, written as at most one org-subject tuple:

    - ``enabled``  → `personal_on`  present, `personal_disabled` absent;
    - ``disabled`` → `personal_disabled` present, `personal_on` absent;
    - ``default``  → neither present (personal spaces follow `default_on`).

    Idempotent: it writes/deletes so exactly the requested state holds. Applies
    instantly to ALL personal spaces via the contextual `personal_team` edge —
    no per-space tuple, no seeding, no backfill.

    A capability with a REQUIRED team-settings field can never be class-enabled
    (§8.2) — nobody has filled the settings (raises `PersonalScopeNotAllowed`).

    When the transition loses access for personal spaces — ``enabled`` →
    ``disabled``; ``enabled`` → ``default`` while NOT default-on; ``default`` →
    ``disabled`` while default-on — every dependent PERSONAL-space instance whose
    team lacks an explicit `enabled` grant is suspended
    (`CAPABILITY_ACCESS_REVOKED`), the same #1975 sweep as
    `set_capability_default_on(False)` but filtered to personal spaces. Returns
    the number of instances suspended.
    """

    if catalog_entry.kind == "app":
        raise PersonalScopeNotAllowed(
            f"Application {catalog_entry.id!r} has no personal-space scope; "
            "V1 applications are collaborative-team-only."
        )
    if scope == "enabled" and team_settings_has_required_fields(
        catalog_entry.team_settings_fields
    ):
        raise PersonalScopeNotAllowed(
            f"Capability {catalog_entry.id!r} has required team settings and "
            "cannot be class-enabled for all personal spaces."
        )
    if scope == "enabled":
        await _require_agent_capability_dependencies_usable_by_all_personal_spaces(
            rebac, catalog_entry
        )

    await ensure_capability_anchor(rebac, catalog_entry.id)

    # Whether a personal space carrying NO explicit per-team tuple has inherited
    # access, before and after the write. Inheritance for such a space is
    # `(personal_on OR default_on) AND NOT personal_disabled` — the FGA
    # `inherited` relation evaluated for a personal subject. `default_on` is a
    # constant across the write; only the two class tuples move.
    was_on_class = await has_org_relation(
        rebac, catalog_entry.id, RelationType.PERSONAL_ON
    )
    was_off_class = await has_org_relation(
        rebac, catalog_entry.id, RelationType.PERSONAL_DISABLED
    )
    default_on = await has_org_relation(
        rebac, catalog_entry.id, RelationType.DEFAULT_ON
    )
    had_access = (was_on_class or default_on) and not was_off_class

    want_on = scope == "enabled"
    want_disabled = scope == "disabled"
    await _apply_personal_scope_tuples(
        rebac,
        catalog_entry.id,
        want_on=want_on,
        want_disabled=want_disabled,
        updated_by=updated_by,
    )
    has_access = (want_on or default_on) and not want_disabled

    if had_access and not has_access:
        return await _suspend_personal_dependents(
            rebac=rebac,
            agent_instance_store=agent_instance_store,
            capability_id=catalog_entry.id,
            kpi_writer=kpi_writer,
        )
    return 0


async def _apply_personal_scope_tuples(
    rebac: RebacEngine,
    capability_id: str,
    *,
    want_on: bool,
    want_disabled: bool,
    updated_by: str | None = None,
) -> None:
    """Write/delete the two org-subject class tuples so exactly the requested
    state holds (at most one present). Idempotent."""

    on_relation = Relation(
        subject=ORG_REF,
        relation=RelationType.PERSONAL_ON,
        resource=cap_ref(capability_id),
    )
    disabled_relation = Relation(
        subject=ORG_REF,
        relation=RelationType.PERSONAL_DISABLED,
        resource=cap_ref(capability_id),
    )
    try:
        if want_on:
            await rebac.add_relation(on_relation, actor_uid=updated_by)
            await rebac.delete_relation(disabled_relation)
        elif want_disabled:
            await rebac.add_relation(disabled_relation, actor_uid=updated_by)
            await rebac.delete_relation(on_relation)
        else:  # default → clear both
            await rebac.delete_relation(on_relation)
            await rebac.delete_relation(disabled_relation)
    finally:
        # See `enable_capability_for_team`'s matching comment (Codex review,
        # #2181 PR): each branch here is two writes — a half-failure between
        # them must not leave a cached reader reporting the pre-write
        # personal-scope state for a TTL.
        invalidate_capability_relations_cache(capability_id)


_CAPABILITY_RELATIONS_CACHE_TTL_SECONDS = 45
_CAPABILITY_RELATIONS_CACHE: ThreadSafeLRUCache[
    str, tuple[float, list[Relation] | RebacDisabledResult]
] = ThreadSafeLRUCache(max_size=2000)
# Mirrors `teams/service.py`'s `_TEAM_RELATIONS_LAST_INVALIDATED` (#2160
# review): a read in flight when a write invalidates must not resurrect the
# pre-write snapshot it already had in hand — see the race-guard comment in
# `get_capability_relations_cached` below.
_CAPABILITY_RELATIONS_LAST_INVALIDATED: ThreadSafeLRUCache[str, float] = (
    ThreadSafeLRUCache(max_size=2000)
)


def invalidate_capability_relations_cache(capability_id: str) -> None:
    """Drop the cached `list_direct_relations` result for one capability
    (#2181).

    Every relation-mutating call in this module (enable/disable/reset a
    team's grant, the default-on toggle, the personal-scope toggle) calls
    this right after its write succeeds, mirroring `teams/service.py`'s
    `invalidate_team_relations_cache`.
    """

    _CAPABILITY_RELATIONS_CACHE.delete(capability_id)
    _CAPABILITY_RELATIONS_LAST_INVALIDATED.set(capability_id, time.time())


async def get_capability_relations_cached(
    rebac: RebacEngine, capability_id: str
) -> "list[Relation] | RebacDisabledResult":
    """Cached `list_direct_relations(capability:<capability_id>)`, TTL-bounded
    (#2181, follow-up to #2089).

    #2089 made `GET /admin/capabilities`'s per-row ReBAC reads concurrent but
    did not reduce their count: each row still fired up to 5 individual
    `lookup_subjects` (OpenFGA `ListUsers`) round-trips — `enabled`/`disabled`
    team grants plus `default_on`/`personal_on`/`personal_disabled` org
    markers — for ~87 catalog capabilities, ~175 calls per page load. All 5
    answers live on the SAME literal tuple set (this one capability as
    object, no relation filter), so — mirroring `_bulk_team_membership`'s
    #2065/#2148 fix for the equivalent team-membership fan-out — one exact
    `list_direct_relations` `Read` per capability replaces them all; callers
    fold the returned tuples locally (`capability_relation_subjects`) instead
    of letting OpenFGA filter server-side. Layered with the same short TTL
    (45s) write-invalidated cache shape as `_get_team_relations_cached`.

    Race guard, identical to `_get_team_relations_cached`: `read_started_at`
    is captured before the `await`; if `invalidate_capability_relations_cache`
    ran for this capability at or after that moment, the freshly fetched
    result is provably stale and is returned without being published into the
    cache, so a concurrent write's invalidation is never silently undone for
    a full TTL.
    """

    read_started_at = time.time()
    cached = _CAPABILITY_RELATIONS_CACHE.get(capability_id)
    if cached is not None:
        expires_at, relations = cached
        if expires_at > read_started_at:
            return relations
        _CAPABILITY_RELATIONS_CACHE.delete(capability_id)

    relations = await rebac.list_direct_relations(cap_ref(capability_id))

    last_invalidated = _CAPABILITY_RELATIONS_LAST_INVALIDATED.get(capability_id)
    if last_invalidated is not None and last_invalidated >= read_started_at:
        return relations

    _CAPABILITY_RELATIONS_CACHE.set(
        capability_id,
        (read_started_at + _CAPABILITY_RELATIONS_CACHE_TTL_SECONDS, relations),
    )
    return relations


def capability_relation_subjects(
    relations: "list[Relation] | RebacDisabledResult",
    relation: RelationType,
    subject_type: Resource,
) -> set[str]:
    """Fold one capability's already-fetched relation set down to the subject
    ids holding `relation`, filtered to `subject_type` (#2181) — the
    local-filter counterpart of a `lookup_subjects` call, over a
    `list_direct_relations` result. Empty when ReBAC is disabled."""

    from fred_core import RebacDisabledResult

    if isinstance(relations, RebacDisabledResult):
        return set()
    return {
        rel.subject.id
        for rel in relations
        if rel.relation == relation and rel.subject.type == subject_type
    }


async def has_org_relation(
    rebac: RebacEngine, capability_id: str, relation: RelationType
) -> bool:
    """True when the singleton org holds `relation` on the capability (used to
    read back the class/default-on org-subject markers).

    #2181: every remaining caller of this function is a write-path
    peek-before-mutate decision (`reset_team_capability`'s suspend/revive
    branch, `set_personal_scope`'s access-transition detection, the
    `depends_on` dependency gate, `set_capability_personal_scope`'s
    had_access/has_access peek) — the read-only listing path
    (`_build_enablement_item`) fetches and folds the relation set directly and
    never calls this. Deliberately NOT routed through
    `get_capability_relations_cached`: those decisions must see the current
    OpenFGA state, not a state up to 45s stale from another replica's write —
    caching here would buy the listing endpoint nothing (it doesn't call this)
    while risking a wrong suspend/revive/reject call under concurrent
    multi-replica admin actions. Still backed by `list_direct_relations`
    (a `Read`) rather than `lookup_subjects` (`ListUsers`) — cheaper per call
    even uncached (#2065's finding: `Read` is the cheaper primitive).

    Codex review (#2181 PR): narrowed to `subject=ORG_REF` so OpenFGA filters
    server-side to the handful of org-subject tuples instead of transferring
    and paginating through every team's `enabled`/`disabled` grant merely to
    answer one org-marker question — matters once a capability has grants
    across many teams.
    """

    relations = await rebac.list_direct_relations(
        cap_ref(capability_id), subject=ORG_REF
    )
    return ORGANIZATION_ID in capability_relation_subjects(
        relations, relation, Resource.ORGANIZATION
    )


async def _suspend_personal_dependents(
    *,
    rebac: RebacEngine,
    agent_instance_store: AgentInstanceStore,
    capability_id: str,
    kpi_writer: BaseKPIWriter | None = None,
) -> int:
    """Suspend PERSONAL-space instances that depend on `capability_id` —
    selected it as a tool, or ARE an instance of it as a `kind="agent"`
    template (2026-07-19, GitHub #2004 item 1) — whose team lacks an explicit
    `enabled` grant (the personal-class revocation sweep).

    A per-space explicit `enabled` grant survives the class change (it keeps
    `can_use`), so those instances are never touched."""

    enabled_teams = await explicitly_enabled_team_ids(rebac, capability_id)
    suspended = 0
    for instance in await agent_instance_store.list_all():
        if not is_personal_team_id(str(instance.team_id)):
            continue
        if str(instance.team_id) in enabled_teams:
            continue
        if await _suspend_instance_for_revoked_capability(
            agent_instance_store=agent_instance_store,
            instance=instance,
            capability_id=capability_id,
            kpi_writer=kpi_writer,
        ):
            suspended += 1
    return suspended


async def explicitly_enabled_team_ids(
    rebac: RebacEngine, capability_id: str
) -> set[str]:
    """Team ids carrying an explicit `enabled` tuple on the capability.

    Returns an empty set when ReBAC is disabled (the lookup is unavailable), so
    the default-on-off path suspends nothing rather than guessing.
    """

    from fred_core import RebacDisabledResult

    subjects = await rebac.lookup_subjects(
        cap_ref(capability_id),
        RelationType.ENABLED,
        Resource.TEAM,
    )
    if isinstance(subjects, RebacDisabledResult):
        return set()
    return {ref.id for ref in subjects}
