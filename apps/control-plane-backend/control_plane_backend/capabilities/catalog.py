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
Aggregated capability catalog for the enablement surface (CAPAB-01 / #1980).

One place that unions every enabled runtime pod's advertised capabilities into a
`{id: CapabilityCatalogEntry}` map. The enablement API and both seed paths read
their `team_settings_fields` / `team_scope` from here — never a second copy.
"""

from __future__ import annotations

import logging
import re

from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import CAPABILITY_ID_PATTERN

from control_plane_backend.product.dependencies import ProductServiceDependencies

logger = logging.getLogger(__name__)

_CAPABILITY_ID_RE = re.compile(CAPABILITY_ID_PATTERN)


async def aggregate_capability_catalog(
    deps: ProductServiceDependencies,
) -> dict[str, CapabilityCatalogEntry]:
    """Union the capability catalogs advertised by every enabled runtime pod.

    Best-effort: an unreachable pod is logged and skipped (its capabilities are
    simply absent this pass), never fatal. Later-registration wins on id
    collision, matching the aggregation the product catalog already performs.
    """

    # Lazy import breaks the product.service ↔ capabilities import cycle: the
    # pod-catalog fetch protocol lives with the rest of the runtime-source code.
    from control_plane_backend.product.service import (
        _agent_capabilities_for_source,
        _available_capabilities_for_source,
    )

    catalog: dict[str, CapabilityCatalogEntry] = {}
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        try:
            entries = await _available_capabilities_for_source(source.base_url)
        except Exception as exc:  # noqa: BLE001 — best-effort aggregation
            logger.warning(
                "[capability-catalog] could not fetch capabilities from %s: %s",
                source.base_url,
                exc,
            )
            continue
        # `kind="agent"` projections (CAPAB-01, RFC §8.6) — a SEPARATE fetch
        # from the tool catalog above, deliberately not merged into the
        # runtime's own capability registry (see `_agent_capabilities_for_source`
        # docstring for why that would leak agents into every template's tool
        # picker). `_agent_capabilities_for_source` is itself best-effort
        # (`None` on an unreachable pod, treated as empty here).
        entries = entries + (
            await _agent_capabilities_for_source(source.base_url, source.runtime_id)
            or []
        )
        for entry in entries:
            if not _CAPABILITY_ID_RE.fullmatch(entry.id):
                # A pod on pre-#1988 code (or a third-party pod) can advertise
                # an id OpenFGA rejects (e.g. legacy `mcp:<server>`); admitting
                # it would crash every downstream FGA tuple write. Quarantine
                # here — the single ingest chokepoint — instead.
                logger.warning(
                    "[capability-catalog] skipping capability with invalid id %r "
                    "from %s (must match %s — pod likely runs outdated code)",
                    entry.id,
                    source.base_url,
                    CAPABILITY_ID_PATTERN,
                )
                continue
            catalog[entry.id] = entry
    return catalog
