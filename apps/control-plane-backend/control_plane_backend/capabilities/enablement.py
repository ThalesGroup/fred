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
from typing import Any, Iterable, Literal, Mapping

from fred_core.common import TeamId, is_personal_team_id
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

from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.agent_instances.suspension import (
    SuspensionReason,
    reconcile_instance_suspension,
)
from control_plane_backend.capabilities.settings_store import (
    TeamCapabilitySettingsStore,
)

logger = logging.getLogger(__name__)

_ORG_REF = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)


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


def _cap_ref(capability_id: str) -> RebacReference:
    return RebacReference(type=Resource.CAPABILITY, id=capability_id)


def _team_ref(team_id: TeamId) -> RebacReference:
    return RebacReference(type=Resource.TEAM, id=str(team_id))


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
            subject=_ORG_REF,
            relation=RelationType.ORGANIZATION,
            resource=_cap_ref(capability_id),
        )
    )


async def enable_capability_for_team(
    *,
    rebac: RebacEngine,
    settings_store: TeamCapabilitySettingsStore,
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

    validated = validate_team_settings(
        list(catalog_entry.team_settings_fields), settings
    )
    # 1. Settings row first (configuration half).
    await settings_store.upsert(
        team_id=team_id,
        capability_id=catalog_entry.id,
        settings=validated,
        updated_by=updated_by,
    )
    # 2. Authorization half: anchor, clear any opt-out, then grant.
    await ensure_capability_anchor(rebac, catalog_entry.id)
    await rebac.delete_relation(
        Relation(
            subject=_team_ref(team_id),
            relation=RelationType.DISABLED,
            resource=_cap_ref(catalog_entry.id),
        )
    )
    await rebac.add_relation(
        Relation(
            subject=_team_ref(team_id),
            relation=RelationType.ENABLED,
            resource=_cap_ref(catalog_entry.id),
        )
    )
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
    settings_store: TeamCapabilitySettingsStore,
    agent_instance_store: AgentInstanceStore,
    catalog_entry: CapabilityCatalogEntry,
    team_id: TeamId,
    kpi_writer: BaseKPIWriter | None = None,
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

    await rebac.delete_relation(
        Relation(
            subject=_team_ref(team_id),
            relation=RelationType.ENABLED,
            resource=_cap_ref(catalog_entry.id),
        )
    )
    await rebac.add_relation(
        Relation(
            subject=_team_ref(team_id),
            relation=RelationType.DISABLED,
            resource=_cap_ref(catalog_entry.id),
        )
    )
    del settings_store  # settings row is intentionally retained (re-enable restores)
    return await suspend_dependent_instances(
        agent_instance_store=agent_instance_store,
        team_id=team_id,
        capability_id=catalog_entry.id,
        kpi_writer=kpi_writer,
    )


async def reset_capability_for_team(
    *,
    rebac: RebacEngine,
    agent_instance_store: AgentInstanceStore,
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

    await rebac.delete_relation(
        Relation(
            subject=_team_ref(team_id),
            relation=RelationType.ENABLED,
            resource=_cap_ref(catalog_entry.id),
        )
    )
    await rebac.delete_relation(
        Relation(
            subject=_team_ref(team_id),
            relation=RelationType.DISABLED,
            resource=_cap_ref(catalog_entry.id),
        )
    )
    if default_on:
        return 0
    return await suspend_dependent_instances(
        agent_instance_store=agent_instance_store,
        team_id=team_id,
        capability_id=catalog_entry.id,
        kpi_writer=kpi_writer,
    )


async def suspend_dependent_instances(
    *,
    agent_instance_store: AgentInstanceStore,
    team_id: TeamId,
    capability_id: str,
    kpi_writer: BaseKPIWriter | None = None,
) -> int:
    """Suspend every one of a team's instances that selected `capability_id`
    (the #1980 revocation → #1975 suspension seam).

    Only instances that actually select the revoked capability are touched, so
    an unrelated availability suspension is never clobbered. For each, the
    reduced available set is exactly `selected - {capability_id}`, which the
    reconcile reads as "this capability is gone" and suspends with
    `CAPABILITY_ACCESS_REVOKED`.
    """

    suspended = 0
    for instance in await agent_instance_store.list_by_team(team_id):
        selected = set(instance.tuning.selected_capability_ids or [])
        if capability_id not in selected:
            continue
        reason = await reconcile_instance_suspension(
            instance=instance,
            store=agent_instance_store,
            available_capability_ids=selected - {capability_id},
            revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED,
            kpi_writer=kpi_writer,
        )
        if reason is not None:
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
    """

    instances = (
        await agent_instance_store.list_by_team(team_id)
        if team_id is not None
        else await agent_instance_store.list_all()
    )
    revived = 0
    for instance in instances:
        selected = set(instance.tuning.selected_capability_ids or [])
        # Only instances that selected the granted capability can be revived by
        # this grant; an unrelated suspension is never touched.
        if capability_id not in selected:
            continue
        if not instance.is_suspended:
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
    agent_instance_store: AgentInstanceStore,
    catalog_entry: CapabilityCatalogEntry,
    on: bool,
    kpi_writer: BaseKPIWriter | None = None,
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
        await rebac.add_relation(
            Relation(
                subject=_ORG_REF,
                relation=RelationType.DEFAULT_ON,
                resource=_cap_ref(catalog_entry.id),
            )
        )
        return 0

    await rebac.delete_relation(
        Relation(
            subject=_ORG_REF,
            relation=RelationType.DEFAULT_ON,
            resource=_cap_ref(catalog_entry.id),
        )
    )
    # Teams with an explicit grant keep access; everyone else loses inherited use.
    enabled_teams = await _explicitly_enabled_team_ids(rebac, catalog_entry.id)
    suspended = 0
    for instance in await agent_instance_store.list_all():
        selected = set(instance.tuning.selected_capability_ids or [])
        if catalog_entry.id not in selected:
            continue
        if str(instance.team_id) in enabled_teams:
            continue
        reason = await reconcile_instance_suspension(
            instance=instance,
            store=agent_instance_store,
            available_capability_ids=selected - {catalog_entry.id},
            revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED,
            kpi_writer=kpi_writer,
        )
        if reason is not None:
            suspended += 1
    return suspended


async def set_capability_personal_scope(
    *,
    rebac: RebacEngine,
    agent_instance_store: AgentInstanceStore,
    catalog_entry: CapabilityCatalogEntry,
    scope: Literal["enabled", "disabled", "default"],
    kpi_writer: BaseKPIWriter | None = None,
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

    if scope == "enabled" and team_settings_has_required_fields(
        catalog_entry.team_settings_fields
    ):
        raise PersonalScopeNotAllowed(
            f"Capability {catalog_entry.id!r} has required team settings and "
            "cannot be class-enabled for all personal spaces."
        )

    await ensure_capability_anchor(rebac, catalog_entry.id)

    # Whether a personal space carrying NO explicit per-team tuple has inherited
    # access, before and after the write. Inheritance for such a space is
    # `(personal_on OR default_on) AND NOT personal_disabled` — the FGA
    # `inherited` relation evaluated for a personal subject. `default_on` is a
    # constant across the write; only the two class tuples move.
    was_on_class = await _has_org_relation(
        rebac, catalog_entry.id, RelationType.PERSONAL_ON
    )
    was_off_class = await _has_org_relation(
        rebac, catalog_entry.id, RelationType.PERSONAL_DISABLED
    )
    default_on = await _has_org_relation(
        rebac, catalog_entry.id, RelationType.DEFAULT_ON
    )
    had_access = (was_on_class or default_on) and not was_off_class

    want_on = scope == "enabled"
    want_disabled = scope == "disabled"
    await _apply_personal_scope_tuples(
        rebac, catalog_entry.id, want_on=want_on, want_disabled=want_disabled
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
    rebac: RebacEngine, capability_id: str, *, want_on: bool, want_disabled: bool
) -> None:
    """Write/delete the two org-subject class tuples so exactly the requested
    state holds (at most one present). Idempotent."""

    on_relation = Relation(
        subject=_ORG_REF,
        relation=RelationType.PERSONAL_ON,
        resource=_cap_ref(capability_id),
    )
    disabled_relation = Relation(
        subject=_ORG_REF,
        relation=RelationType.PERSONAL_DISABLED,
        resource=_cap_ref(capability_id),
    )
    if want_on:
        await rebac.add_relation(on_relation)
        await rebac.delete_relation(disabled_relation)
    elif want_disabled:
        await rebac.add_relation(disabled_relation)
        await rebac.delete_relation(on_relation)
    else:  # default → clear both
        await rebac.delete_relation(on_relation)
        await rebac.delete_relation(disabled_relation)


async def _has_org_relation(
    rebac: RebacEngine, capability_id: str, relation: RelationType
) -> bool:
    """True when the singleton org holds `relation` on the capability (used to
    read back the class/default-on org-subject markers)."""

    from fred_core import RebacDisabledResult

    subjects = await rebac.lookup_subjects(
        _cap_ref(capability_id),
        relation,
        Resource.ORGANIZATION,
    )
    if isinstance(subjects, RebacDisabledResult):
        return False
    return any(ref.id == ORGANIZATION_ID for ref in subjects)


async def _suspend_personal_dependents(
    *,
    rebac: RebacEngine,
    agent_instance_store: AgentInstanceStore,
    capability_id: str,
    kpi_writer: BaseKPIWriter | None = None,
) -> int:
    """Suspend PERSONAL-space instances selecting `capability_id` whose team
    lacks an explicit `enabled` grant (the personal-class revocation sweep).

    A per-space explicit `enabled` grant survives the class change (it keeps
    `can_use`), so those instances are never touched."""

    enabled_teams = await _explicitly_enabled_team_ids(rebac, capability_id)
    suspended = 0
    for instance in await agent_instance_store.list_all():
        if not is_personal_team_id(str(instance.team_id)):
            continue
        selected = set(instance.tuning.selected_capability_ids or [])
        if capability_id not in selected:
            continue
        if str(instance.team_id) in enabled_teams:
            continue
        reason = await reconcile_instance_suspension(
            instance=instance,
            store=agent_instance_store,
            available_capability_ids=selected - {capability_id},
            revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED,
            kpi_writer=kpi_writer,
        )
        if reason is not None:
            suspended += 1
    return suspended


async def _explicitly_enabled_team_ids(
    rebac: RebacEngine, capability_id: str
) -> set[str]:
    """Team ids carrying an explicit `enabled` tuple on the capability.

    Returns an empty set when ReBAC is disabled (the lookup is unavailable), so
    the default-on-off path suspends nothing rather than guessing.
    """

    from fred_core import RebacDisabledResult

    subjects = await rebac.lookup_subjects(
        _cap_ref(capability_id),
        RelationType.ENABLED,
        Resource.TEAM,
    )
    if isinstance(subjects, RebacDisabledResult):
        return set()
    return {ref.id for ref in subjects}
