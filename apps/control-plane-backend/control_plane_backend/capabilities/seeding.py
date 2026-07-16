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
Capability default seeding (CAPAB-01 / #1980, RFC AGENT-CAPABILITY §8.3).

One seed point, idempotent:

- **Registration seeding** — a `manifest.team_scope: default_on` capability gets
  its `default_on` tuple written the FIRST time it is registered (detected by
  the absence of its organization anchor). Afterwards the tuple is runtime state
  owned by admins, so seeding never re-writes it. The `default_policy: explicit`
  deployment flag skips all seeds; a capability with required team settings can
  never be default-on (§8.2).

Personal-space seeding (formerly `seed_personal_team_capabilities`, driven by
`capabilities.personal_defaults`) was withdrawn by the 2026-07-16 §8.4
amendment: the personal-space class is now pure FGA runtime state
(`personal_on`/`personal_disabled`), admin-toggleable via
`PUT /admin/capabilities/{id}/personal-scope`. No seeding, no backfill.
"""

from __future__ import annotations

import logging
from typing import Iterable

from fred_core import RebacDisabledResult
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
    ensure_capability_anchor,
    team_settings_has_required_fields,
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
        try:
            if await _is_capability_registered(rebac, entry.id):
                continue
            await ensure_capability_anchor(rebac, entry.id)
            await rebac.add_relation(
                _default_on_relation(entry.id),
            )
        except Exception as exc:  # noqa: BLE001 — best-effort per capability
            # One bad entry (e.g. an id OpenFGA rejects) must not starve the
            # rest of the catalog of their first-registration seed.
            logger.warning(
                "[capability-seeding] failed to seed default_on capability=%s: %s",
                entry.id,
                exc,
            )
            continue
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
