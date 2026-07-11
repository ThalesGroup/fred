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
Capability default seeding (CAPAB-01 / #1980, RFC AGENT-CAPABILITY §8.3–§8.4).

Two seed points, both idempotent:

- **Registration seeding** — a `manifest.team_scope: default_on` capability gets
  its `default_on` tuple written the FIRST time it is registered (detected by
  the absence of its organization anchor). Afterwards the tuple is runtime state
  owned by admins, so seeding never re-writes it. The `default_policy: explicit`
  deployment flag skips all seeds; a capability with required team settings can
  never be default-on (§8.2).
- **Personal-space seeding** — each capability id in
  `capabilities.personal_defaults` is enabled for a personal space the first
  time it is materialized (guarded by the absence of a settings row so repeated
  bootstraps do not re-write tuples).
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping

from fred_core import RebacDisabledResult
from fred_core.common import TeamId
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacEngine,
    RelationType,
)
from fred_core.security.models import Resource
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import TeamScopePolicy

from control_plane_backend.capabilities.enablement import (
    _ORG_REF,
    _cap_ref,
    enable_capability_for_team,
    ensure_capability_anchor,
    team_settings_has_required_fields,
)
from control_plane_backend.capabilities.settings_store import (
    TeamCapabilitySettingsStore,
)

logger = logging.getLogger(__name__)


async def _is_capability_registered(rebac: RebacEngine, capability_id: str) -> bool:
    """True once a capability has been anchored to the org (already seeded)."""

    subjects = await rebac.lookup_subjects(
        _cap_ref(capability_id),
        RelationType.ORGANIZATION,
        Resource.ORGANIZATION,
    )
    if isinstance(subjects, RebacDisabledResult):
        # ReBAC disabled: no state to track, treat as unregistered (no-op writes).
        return False
    return any(ref.id == ORGANIZATION_ID for ref in subjects)


async def seed_registration_defaults(
    *,
    rebac: RebacEngine,
    catalog: Iterable[CapabilityCatalogEntry],
    default_policy: str = "seed",
) -> list[str]:
    """Seed `default_on` tuples for newly-registered default-on capabilities.

    Returns the ids seeded this pass. Idempotent and first-registration-only:
    an already-anchored capability is left untouched so an admin's later toggle
    is never overwritten (RFC §8.3).
    """

    if default_policy == "explicit":
        return []

    seeded: list[str] = []
    for entry in catalog:
        if entry.team_scope is not TeamScopePolicy.DEFAULT_ON:
            continue
        if team_settings_has_required_fields(entry.team_settings_fields):
            # Required team settings ⇒ admin-gated by construction (§8.2).
            continue
        if await _is_capability_registered(rebac, entry.id):
            continue
        await ensure_capability_anchor(rebac, entry.id)
        await rebac.add_relation(
            _default_on_relation(entry.id),
        )
        seeded.append(entry.id)
        logger.info("[capability-seeding] seeded default_on capability=%s", entry.id)
    return seeded


def _default_on_relation(capability_id: str):
    from fred_core.security.rebac.rebac_engine import Relation

    return Relation(
        subject=_ORG_REF,
        relation=RelationType.DEFAULT_ON,
        resource=_cap_ref(capability_id),
    )


async def seed_personal_team_capabilities(
    *,
    rebac: RebacEngine,
    settings_store: TeamCapabilitySettingsStore,
    catalog: Mapping[str, CapabilityCatalogEntry],
    personal_defaults: Iterable[str],
    team_id: TeamId,
    updated_by: str | None = "system",
) -> list[str]:
    """Enable the configured personal-space default capabilities for one personal
    team (RFC §8.4). Idempotent: a capability already carrying a settings row for
    the team is skipped, so repeated personal-space bootstraps do not re-write.

    Returns the ids seeded this pass. Best-effort per capability: an unknown id
    or a validation failure is logged and skipped, never fatal to bootstrap.
    """

    seeded: list[str] = []
    for cap_id in personal_defaults:
        entry = catalog.get(cap_id)
        if entry is None:
            logger.warning(
                "[capability-seeding] personal default %s not in catalog; skipped",
                cap_id,
            )
            continue
        existing = await settings_store.get(team_id=team_id, capability_id=cap_id)
        if existing is not None:
            continue
        try:
            await enable_capability_for_team(
                rebac=rebac,
                settings_store=settings_store,
                catalog_entry=entry,
                team_id=team_id,
                settings={},
                updated_by=updated_by,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort per capability
            logger.warning(
                "[capability-seeding] failed to seed personal default %s for %s: %s",
                cap_id,
                team_id,
                exc,
            )
            continue
        seeded.append(cap_id)
    return seeded
