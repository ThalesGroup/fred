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
    APPLICATION_CAPABILITY_NAMESPACE_PREFIX,
    CAPABILITY_ID_PATTERN,
    MODEL_CAPABILITY_NAMESPACE_PREFIX,
)

from control_plane_backend.app.feature_flags import is_feature_enabled
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
    with one exception: for `kind="model"` entries, `model_profile_ids`,
    `model_chat_profile_ids`, and `model_thinking_profile_ids` are unioned
    across pods rather than
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
        pod_models = await _model_capabilities_for_source(source.base_url)
        entries = entries + (pod_models.entries if pod_models is not None else [])
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
            if entry.kind == "app":
                # Product applications are projected only from the generated
                # control-plane artifact. A runtime pod must never inject an
                # application row into the product catalog.
                logger.error(
                    "[capability-catalog] refusing pod-advertised app capability "
                    "id %r from %s",
                    entry.id,
                    source.base_url,
                )
                continue
            if entry.id.startswith(APPLICATION_CAPABILITY_NAMESPACE_PREFIX):
                logger.error(
                    "[capability-catalog] refusing kind=%r capability id %r "
                    'from %s: the %r prefix is reserved for kind="app" '
                    "control-plane projections",
                    entry.kind,
                    entry.id,
                    source.base_url,
                    APPLICATION_CAPABILITY_NAMESPACE_PREFIX,
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
                        "model_chat_profile_ids": _union_profile_ids(
                            existing.model_chat_profile_ids,
                            entry.model_chat_profile_ids,
                        ),
                        "model_thinking_profile_ids": _union_profile_ids(
                            existing.model_thinking_profile_ids,
                            entry.model_thinking_profile_ids,
                        ),
                        # The union rule above applied to a scalar: a label
                        # authored on one pod survives another that serves the
                        # same model unnamed, so a partly rolled-out catalog
                        # edit does not flicker the composer label back to the
                        # heuristic. Both naming it: last wins, as elsewhere.
                        "model_display_name": (
                            entry.model_display_name or existing.model_display_name
                        ),
                    }
                )
            catalog[entry.id] = entry
    # Applications are control-plane projections generated from the same
    # manifests as the frontend loader registry. Inject them after the pod
    # loop so runtime outages cannot remove installed application rows from
    # the platform-admin entitlement surface. The Applications feature gate controls
    # only this projection; the pod-side app/app__ quarantine above remains
    # active even while Apps is disabled so runtimes can never claim the
    # reserved product-application namespace.
    if is_feature_enabled(deps.configuration, "enableApplications"):
        from control_plane_backend.applications.catalog import (
            load_generated_application_catalog,
        )

        for app in load_generated_application_catalog().items:
            catalog[app.capability_id] = app.capability_entry()
    return catalog


async def universally_available_chat_model_profile_ids(
    deps: ProductServiceDependencies,
    *,
    source_runtime_ids: set[str] | None = None,
) -> frozenset[str]:
    """Chat profile ids resolvable on every pod relevant to one team.

    This is the intersection dual of `aggregate_capability_catalog`'s union
    above (2026-08-02, `TEAM-ROUTING-POLICY-RFC.md` §7.2/§9). It deliberately
    consumes `model_chat_profile_ids`, not every model profile: the current
    team policy can select chat models only.

    "Available" also means semantically identical: a shared profile id must
    map to the same `(provider, name)` capability id on every pod. Otherwise
    the chosen model would depend on which pod serves the turn.

    `aggregate_capability_catalog`'s union answers "does at least one pod
    know this profile" — the right question for admission/enablement, where
    a capability just needs to exist somewhere to be toggled on. A team
    routing policy asks a different question: whichever pod ends up serving
    a given turn must be able to resolve the chosen profile. Validating a
    routing-policy write against this intersection instead of the union
    means a write is checked against the pods that can actually serve it.

    `source_runtime_ids` scopes the intersection to the pods that matter for
    one team — pass the `source_runtime_id`s of that team's own
    `AgentInstanceRecord`s (same input `capabilities.impact
    .resolve_availability_for_team` takes). Each `AgentInstance` is pinned to
    exactly one pod for its whole life (`source_runtime_id` is set once at
    enrollment and a turn is always prepared against that same pod), so a
    pod this team has no instance on has no opinion on what "available"
    means for this team. `None` or an empty set (a team with no agent
    instances yet, so no pod can be ruled out as irrelevant) falls back to
    every enabled source.

    Best-effort per relevant pod, not fail-closed platform-wide as an earlier
    revision did (PR #2204 review): an unreachable pod outside
    `source_runtime_ids` used to still zero the result for every team on the
    deployment, which is disproportionate — a pod a team does not use going
    down must not block that team's routing UI. A currently-unreachable pod
    the team DOES use is simply skipped here too; the write-time check only
    needs to catch a KNOWN mismatch on a pod it can currently see. Genuine
    drift — a pod resolving a turn for a profile it turns out not to carry —
    is still caught at the moment it would matter by
    `RoutedChatModelFactory.select` (fred-runtime) raising
    `TeamRoutingProfileDriftError`; that per-turn check is what has to stay
    airtight, not this one. A pod that answered but genuinely registers no
    model (`[]`, e.g. a non-agent pod) is excluded the same way — it never
    was model-capable, so it has no opinion to poison the intersection with.
    """

    # Lazy import for the same reason as `aggregate_capability_catalog` above
    # — breaks the product.service <-> capabilities import cycle.
    from control_plane_backend.product.service import _model_capabilities_for_source

    per_pod_profiles: list[dict[str, str]] = []
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        if source_runtime_ids and source.runtime_id not in source_runtime_ids:
            continue
        pod_models = await _model_capabilities_for_source(source.base_url)
        if pod_models is None:
            logger.warning(
                "[capability-catalog] %s unreachable while computing available "
                "chat model profiles (source_runtime_ids=%s) — skipping this "
                "pod (best-effort) rather than failing closed for the whole "
                "result",
                source.base_url,
                source_runtime_ids,
            )
            continue
        if not pod_models.entries:
            continue
        profile_models: dict[str, str] = {}
        conflicting_profile_ids: set[str] = set()
        for entry in pod_models.entries:
            for profile_id in entry.model_chat_profile_ids:
                existing_model_id = profile_models.get(profile_id)
                if existing_model_id is not None and existing_model_id != entry.id:
                    conflicting_profile_ids.add(profile_id)
                    continue
                profile_models[profile_id] = entry.id
        for profile_id in conflicting_profile_ids:
            profile_models.pop(profile_id, None)
        per_pod_profiles.append(profile_models)
    if not per_pod_profiles:
        return frozenset()
    shared_profile_ids = set.intersection(
        *(set(profiles) for profiles in per_pod_profiles)
    )
    return frozenset(
        profile_id
        for profile_id in shared_profile_ids
        if len({profiles[profile_id] for profiles in per_pod_profiles}) == 1
    )
