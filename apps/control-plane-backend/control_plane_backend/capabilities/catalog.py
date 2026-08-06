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
from fred_sdk.contracts.capability.manifest import (
    CAPABILITY_ID_PATTERN,
    MODEL_CAPABILITY_NAMESPACE_PREFIX,
)

from control_plane_backend.product.dependencies import ProductServiceDependencies

logger = logging.getLogger(__name__)

_CAPABILITY_ID_RE = re.compile(CAPABILITY_ID_PATTERN)


def _union_profile_ids(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for group in groups:
        for profile_id in group:
            seen[profile_id] = None
    return tuple(seen)


async def aggregate_capability_catalog(
    deps: ProductServiceDependencies,
) -> dict[str, CapabilityCatalogEntry]:
    """Union the capability catalogs advertised by every enabled runtime pod.

    Best-effort: an unreachable pod is logged and skipped (its capabilities are
    simply absent this pass), never fatal. Later-registration wins on id
    collision, matching the aggregation the product catalog already performs —
    with one exception: for `kind="model"` entries, `model_profile_ids` and
    `model_thinking_profile_ids` are unioned across pods rather than
    overwritten (2026-08-01, GitHub #2191). A `(provider, name)` pair routed
    by more than one pod, each with its own `profile_id` namespace, would
    otherwise have the earlier pod's profile ids silently dropped —
    `model_profile_ids`' own contract ("every profile_id sharing this entry's
    (provider, name)") requires the union, and `routing_policy` validates a
    team's chosen profile against exactly this map, so a dropped profile id
    reads there as an unknown one even though it is still live.
    """

    # Lazy import breaks the product.service ↔ capabilities import cycle: the
    # pod-catalog fetch protocol lives with the rest of the runtime-source code.
    from control_plane_backend.product.service import (
        AGENT_CAPABILITY_NAMESPACE_PREFIX,
        _agent_capabilities_for_source,
        _available_capabilities_for_source,
        _model_capabilities_for_source,
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
        # `kind="model"` projections (OBSERV-02 v3, RFC §8.7) — a third,
        # separate fetch, same best-effort contract as the agent fetch above:
        # `None` on an unreachable pod, treated as empty here.
        entries = entries + (
            await _model_capabilities_for_source(source.base_url) or []
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
            if entry.kind != "agent" and entry.id.startswith(
                AGENT_CAPABILITY_NAMESPACE_PREFIX
            ):
                # `AGENT_CAPABILITY_NAMESPACE_PREFIX` is reserved exclusively
                # for kind="agent" template projections (GitHub #2004 item 4)
                # so the two kinds can never collide in this flat dict —
                # admitting a same-prefixed tool id would defeat that
                # guarantee and silently shadow (or be shadowed by) the real
                # agent-template entry. Quarantine at the same chokepoint as
                # the invalid-id check above, rather than letting it overwrite.
                logger.error(
                    "[capability-catalog] refusing kind=%r capability id %r "
                    'from %s: the %r prefix is reserved for kind="agent" '
                    "template projections — rename this tool/MCP-server id",
                    entry.kind,
                    entry.id,
                    source.base_url,
                    AGENT_CAPABILITY_NAMESPACE_PREFIX,
                )
                continue
            if entry.kind != "model" and entry.id.startswith(
                MODEL_CAPABILITY_NAMESPACE_PREFIX
            ):
                # Same guarantee as the agent-prefix check above, for
                # kind="model" projections (OBSERV-02 v3, RFC §8.7) — a
                # same-prefixed tool/MCP-server id would silently shadow (or
                # be shadowed by) the real model entry.
                logger.error(
                    "[capability-catalog] refusing kind=%r capability id %r "
                    'from %s: the %r prefix is reserved for kind="model" '
                    "projections — rename this tool/MCP-server id",
                    entry.kind,
                    entry.id,
                    source.base_url,
                    MODEL_CAPABILITY_NAMESPACE_PREFIX,
                )
                continue
            existing = catalog.get(entry.id)
            if (
                existing is not None
                and existing.kind == "model"
                and entry.kind == "model"
            ):
                entry = entry.model_copy(
                    update={
                        "model_profile_ids": _union_profile_ids(
                            existing.model_profile_ids, entry.model_profile_ids
                        ),
                        "model_thinking_profile_ids": _union_profile_ids(
                            existing.model_thinking_profile_ids,
                            entry.model_thinking_profile_ids,
                        ),
                    }
                )
            catalog[entry.id] = entry
    return catalog


async def universally_available_model_profile_ids(
    deps: ProductServiceDependencies,
) -> frozenset[str]:
    """`model_profile_ids` present on every enabled, model-capable pod — the
    intersection dual of `aggregate_capability_catalog`'s union above
    (2026-08-02, `TEAM-ROUTING-POLICY-RFC.md` §7.2/§9).

    `aggregate_capability_catalog`'s union answers "does at least one pod
    know this profile" — the right question for admission/enablement, where
    a capability just needs to exist somewhere to be toggled on. A team
    routing policy asks a different question: whichever pod ends up serving
    a given turn must be able to resolve the chosen profile, or
    `RoutedChatModelFactory.select` (fred-runtime) fails closed with
    `TeamRoutingProfileDriftError`. Validating a routing-policy write against
    this intersection instead of the union means a write that succeeds can
    never drift-fail at runtime on some other pod.

    Fails closed, unlike `aggregate_capability_catalog`'s best-effort skip: an
    enabled pod that is genuinely unreachable (`_model_capabilities_for_source`
    returns `None`) makes the whole result `frozenset()` rather than being
    silently excluded — excluding it would let the *other* pods' common
    profiles look "universal" while this one is down, which is exactly the
    write-now-drift-later gap this function exists to close (2026-08-04,
    PR #2204 review). A pod that answered but genuinely registers no model
    (`[]`, e.g. a non-agent pod) is not the same thing and is excluded as
    before — it never was model-capable, so it has no opinion to poison the
    intersection with.
    """

    # Lazy import for the same reason as `aggregate_capability_catalog` above
    # — breaks the product.service <-> capabilities import cycle.
    from control_plane_backend.product.service import _model_capabilities_for_source

    per_pod_profile_ids: list[set[str]] = []
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        entries = await _model_capabilities_for_source(source.base_url)
        if entries is None:
            logger.warning(
                "[capability-catalog] %s unreachable while computing universally "
                "available model profiles — failing closed (no profile is "
                "certified available this pass) rather than risk approving a "
                "routing-policy write this pod cannot actually serve",
                source.base_url,
            )
            return frozenset()
        if not entries:
            continue
        per_pod_profile_ids.append(
            {profile_id for entry in entries for profile_id in entry.model_profile_ids}
        )
    if not per_pod_profile_ids:
        return frozenset()
    return frozenset(set.intersection(*per_pod_profile_ids))


async def has_unreachable_enabled_model_source(
    deps: ProductServiceDependencies,
) -> bool:
    """Whether any enabled runtime source was unreachable while checking model
    availability for routing-policy pickers.

    This distinguishes the "no models are granted" empty state from the
    fail-closed "some enabled pod is unreachable, so no profile is certified
    universal right now" case. Kept separate from
    `universally_available_model_profile_ids` so callers can surface the cause
    without weakening the fail-closed intersection contract.
    """

    # Lazy import for the same reason as `aggregate_capability_catalog` above
    # — breaks the product.service <-> capabilities import cycle.
    from control_plane_backend.product.service import _model_capabilities_for_source

    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        if await _model_capabilities_for_source(source.base_url) is None:
            return True
    return False
