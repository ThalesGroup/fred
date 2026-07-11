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
from typing import Any, Iterable, Mapping

from fred_core.common import TeamId
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
)
from fred_core.security.models import Resource
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import TeamScopePolicy
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
    re-enable restores prior settings). For a default-on capability, a
    `disabled` opt-out tuple is written so the team truly loses `can_use`.
    Every dependent agent instance is then suspended with
    `CAPABILITY_ACCESS_REVOKED`. Returns the number of instances suspended.
    """

    await rebac.delete_relation(
        Relation(
            subject=_team_ref(team_id),
            relation=RelationType.ENABLED,
            resource=_cap_ref(catalog_entry.id),
        )
    )
    if catalog_entry.team_scope is TeamScopePolicy.DEFAULT_ON:
        # Opt this team out of the platform-wide default so `can_use` is false.
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
