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
Resting capability impact — who is broken RIGHT NOW, and by what (CAPAB-01).

Why this module exists:
- `agent_instance.suspension_reason` records WHY an instance is suspended, never
  WHICH capability did it. An instance broken by `capa1` while also selecting
  `capa2` would be miscounted against `capa2` by any `suspension_reason IS NOT
  NULL AND capa2 IN selected` query. Attribution is therefore DERIVED, never
  stored: `selected_capability_ids` minus what the instance's space may
  currently use, minus what its pod currently advertises.
- the same derivation answers two questions the admin surface asks, so it lives
  in exactly one place (both callers below):
    1. resting health  — "how many instances does capability X break today?"
    2. impact preview  — "how many WOULD X break if I revoked it now?"

Why not reuse the write path's shortcut: `suspend_dependent_instances` fakes the
available set as `selected - {capability_id}` because a revoke KNOWS what it
just took away. A resting read has no such luxury — it must ask ReBAC and the
pods what is true now. That asymmetry is exactly why this module exists.

Availability is the CONJUNCTION of two independent facts (both required):
- ReBAC `can_use` — the space is authorized for the capability
- pod manifest — the capability is actually shipped by the instance's runtime

Unreachable pod = UNKNOWN, never "broken": the reconciliation sweep skips such
instances (`skipped_unreachable`) rather than suspending them on a transient
outage (#1975, RFC §3.9), and this read reports the same way. Telling an admin
"12 agents broken" because a pod is restarting would be a lie with consequences.

Where `can_use` comes from: the health column folds it from the cached
per-capability tuple sets, the revoke preview from one fresh read of the single
capability it is about. `resolve_availability_for_team` (the grant revive path)
keeps the live `usable_capability_ids` - it feeds a write, not a display.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Sequence

from fred_core import RebacDisabledResult, RebacEngine
from fred_core.common import TeamId
from fred_core.security.rebac.capability_authz import (
    CapabilityEnablementFacts,
    can_team_use_from_facts,
)

from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.capabilities.authz import usable_capability_ids
from control_plane_backend.capabilities.enablement import (
    cap_ref,
    get_enablement_relations_cached,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies


@dataclass(frozen=True)
class ImpactedInstance:
    """One agent instance a capability currently breaks (or would break)."""

    agent_instance_id: str
    team_id: str
    display_name: str


@dataclass
class CapabilityImpact:
    """Per-capability resting impact across every team."""

    suspended_instances: int = 0
    instances: list[ImpactedInstance] = field(default_factory=list)
    #: Instances skipped because their pod was unreachable — impact UNKNOWN for
    #: them, deliberately not folded into `suspended_instances`.
    skipped_unreachable: int = 0


async def _referenced_facts(
    rebac: RebacEngine,
    instances: Sequence[AgentInstanceRecord],
) -> dict[str, CapabilityEnablementFacts] | None:
    """Fold every capability the instances depend on, one cached tuple read each.

    A `ListObjects` per team cost OpenFGA a `Check` per catalog capability, and
    every personal space is a team. `None` means ReBAC is disabled ("no
    scoping", matching `usable_capability_ids`).
    """

    # Materialized once: `gather` and the `zip` below must walk the same order.
    referenced_ids = list(
        {
            cap_id
            for instance in instances
            for cap_id in _instance_dependency_ids(instance)
        }
    )
    relation_sets = await asyncio.gather(
        *(
            get_enablement_relations_cached(rebac, cap_ref(cap_id))
            for cap_id in referenced_ids
        )
    )
    facts_by_id: dict[str, CapabilityEnablementFacts] = {}
    for cap_id, relations in zip(referenced_ids, relation_sets):
        if isinstance(relations, RebacDisabledResult):
            return None
        facts_by_id[cap_id] = CapabilityEnablementFacts.from_relations(relations)
    return facts_by_id


def _instance_template_capability_id(instance: AgentInstanceRecord) -> str | None:
    """The `kind="agent"` template capability id `instance` is itself an
    instance of, or `None` when its template is gate-exempt (2026-08-01,
    GitHub #2191).

    Mirrors the write-side predicate `enablement.is_template_capability_instance`
    — this module previously derived impact/health from
    `selected_capability_ids` alone, which never contains a template's own id
    (only tool capabilities an instance activated are selected), so an admin
    revoking a `kind="agent"` capability saw "0 agents affected" while its
    instances were, in fact, about to be suspended.
    """

    from control_plane_backend.product.service import (
        capability_gate_exempt,
        template_capability_id,
    )

    if capability_gate_exempt(instance.source_agent_id):
        return None
    return template_capability_id(instance.source_runtime_id, instance.source_agent_id)


def _instance_dependency_ids(instance: AgentInstanceRecord) -> list[str]:
    """Every capability the instance depends on: the tool capabilities it
    selected, plus - unless gate-exempt - the `kind="agent"` template it is
    itself an instance of."""

    dependency_ids = list(instance.tuning.selected_capability_ids or [])
    template_cap_id = _instance_template_capability_id(instance)
    if template_cap_id is not None:
        dependency_ids.append(template_cap_id)
    return dependency_ids


def _dependency_is_broken(
    instance: AgentInstanceRecord,
    cap_id: str,
    facts_by_id: dict[str, CapabilityEnablementFacts] | None,
    available_ids: frozenset[str] | None,
) -> bool:
    """Is this ONE dependency currently unusable by the instance's space?

    A selected TOOL capability breaks when the team lacks `can_use` OR its pod
    no longer advertises it - the two failure modes behind
    `capability_access_revoked` and `capability_unavailable`. The instance's OWN
    template id is checked on the `can_use` axis only: `available_ids` is the
    pod's advertised SELECTABLE set, which never contains a template's own id,
    so checking it there would always read "missing" - matching
    `enablement.revive_dependent_instances`'s template branch.

    `facts_by_id=None` (ReBAC disabled) skips the authorization half;
    `available_ids=None` (unreachable pod) must be handled by the CALLER, which
    reports the instance as unknown rather than broken.
    """

    denied = facts_by_id is not None and not can_team_use_from_facts(
        str(instance.team_id), facts_by_id[cap_id]
    )
    selected = cap_id in (instance.tuning.selected_capability_ids or [])
    missing = selected and available_ids is not None and cap_id not in available_ids
    return denied or missing


def _broken_capability_ids(
    instance: AgentInstanceRecord,
    facts_by_id: dict[str, CapabilityEnablementFacts] | None,
    available_ids: frozenset[str] | None,
) -> list[str]:
    """The instance's dependencies that are NOT currently usable."""

    return [
        cap_id
        for cap_id in _instance_dependency_ids(instance)
        if _dependency_is_broken(instance, cap_id, facts_by_id, available_ids)
    ]


async def compute_capability_impact(
    deps: ProductServiceDependencies,
    *,
    store: AgentInstanceStore | None = None,
    collect_instances: bool = False,
) -> dict[str, CapabilityImpact]:
    """Resting impact for EVERY capability, keyed by capability id (CAPAB-01).

    The number an admin sees in the dashboard's health column: how many agent
    instances each capability breaks at rest. Derived, never read from
    `suspension_reason` — see the module docstring for why that column cannot
    answer this.

    Cost is bounded by design: one cached tuple read per REFERENCED capability
    (never one per team or per instance) plus one template fetch per runtime pod.

    `collect_instances=True` additionally names the impacted instances (the
    drill-down "which agents, in which space"); the count alone skips that work.
    """

    # Lazy import: `product.service` imports the capabilities package, so a
    # module-level import here would close the cycle (same reason
    # `catalog.py` defers its pod-fetch imports).
    from control_plane_backend.product.service import (
        _available_capability_ids_by_source,
    )

    instance_store = store or deps.get_agent_instance_store()
    instances = await instance_store.list_all()
    if not instances:
        return {}

    available_by_source = await _available_capability_ids_by_source(deps)
    facts_by_id = await _referenced_facts(deps.team_dependencies.rebac, instances)

    impact: dict[str, CapabilityImpact] = {}
    for instance in instances:
        available_ids = available_by_source.get(instance.source_runtime_id)
        if available_ids is None:
            # Pod unreachable — the sweep would skip this instance rather than
            # suspend it, so its impact is UNKNOWN. Attribute the skip to every
            # dependency so the caller says "unknown", not "fine", for each.
            for cap_id in _instance_dependency_ids(instance):
                impact.setdefault(cap_id, CapabilityImpact()).skipped_unreachable += 1
            continue

        broken = _broken_capability_ids(instance, facts_by_id, available_ids)
        for cap_id in broken:
            entry = impact.setdefault(cap_id, CapabilityImpact())
            entry.suspended_instances += 1
            if collect_instances:
                entry.instances.append(
                    ImpactedInstance(
                        agent_instance_id=instance.agent_instance_id,
                        team_id=str(instance.team_id),
                        display_name=instance.display_name,
                    )
                )
    return impact


async def resolve_availability_for_team(
    deps: ProductServiceDependencies,
    *,
    team_id: TeamId,
    source_runtime_ids: set[str],
) -> tuple[set[str] | None, dict[str, frozenset[str] | None]]:
    """The real availability facts a GRANT needs to revive instances.

    Returns `(usable_ids, available_by_source)` — the team's `can_use` set (None
    when ReBAC is disabled) and each runtime's advertised capability set (None
    per source when that pod is unreachable). The revoke path can synthesize
    `selected - {id}` instead; a grant cannot, because it does not know whether
    the instance's OTHER capabilities are healthy. See
    `revive_dependent_instances`.
    """

    from control_plane_backend.product.service import (
        _available_capability_ids_by_source,
    )

    usable_ids = await usable_capability_ids(deps.team_dependencies.rebac, team_id)
    available_by_source = await _available_capability_ids_by_source(deps)
    return usable_ids, {
        runtime_id: available_by_source.get(runtime_id)
        for runtime_id in source_runtime_ids
    }


async def preview_revoke_impact(
    deps: ProductServiceDependencies,
    *,
    capability_id: str,
    team_id: TeamId | None = None,
    store: AgentInstanceStore | None = None,
) -> CapabilityImpact:
    """What revoking `capability_id` WOULD break — the pre-disable preview.

    Forward-looking, so it cannot read the world as-is: it counts instances that
    select the capability and are NOT ALREADY broken by it. An instance already
    suspended for this capability is not "newly suspended" by revoking it again,
    which keeps the dialog's number honest ("this will suspend N agents" means N
    agents that work today will stop working).

    `team_id=None` previews a platform-wide default-off; a team id previews that
    one team's disable. Instances whose pod is unreachable are reported via
    `skipped_unreachable` rather than counted — same fail-open-to-unknown rule
    as `compute_capability_impact`.

    A platform-wide preview (`team_id=None`) must converge with what
    `set_capability_default_on(False)` actually does: that mutation skips teams
    that already carry an explicit `enabled` grant (they keep `can_use` by
    their own tuple, not by inheritance), so this preview excludes them too —
    otherwise the confirmation dialog overstates impact by counting agents that
    will not actually be suspended.

    An admin confirms a mutation against this number, so it reads the one
    capability's tuples FRESH (never the 45s cache, which another replica's
    write does not invalidate) and answers both questions it asks - who holds
    an explicit grant, and who is already broken - from that single read.
    """

    from control_plane_backend.capabilities.enablement import (
        is_template_capability_instance,
    )
    from control_plane_backend.product.service import (
        _available_capability_ids_by_source,
    )

    instance_store = store or deps.get_agent_instance_store()
    instances = (
        await instance_store.list_by_team(team_id)
        if team_id is not None
        else await instance_store.list_all()
    )
    # Only instances that actually depend on the capability can be affected:
    # selected it as a tool, or ARE an instance of it as a `kind="agent"`
    # template (2026-08-01, GitHub #2191 — previously only the former was
    # checked, so revoking a `kind="agent"` capability always previewed as
    # "0 agents affected" even though its instances were about to be
    # suspended).
    instances = [
        instance
        for instance in instances
        if capability_id in (instance.tuning.selected_capability_ids or [])
        or is_template_capability_instance(instance, capability_id)
    ]
    if not instances:
        return CapabilityImpact()

    relations = await deps.team_dependencies.rebac.list_direct_relations(
        cap_ref(capability_id)
    )
    facts = (
        None
        if isinstance(relations, RebacDisabledResult)
        else CapabilityEnablementFacts.from_relations(relations)
    )
    if team_id is None and facts is not None:
        instances = [
            instance
            for instance in instances
            if str(instance.team_id) not in facts.enabled
        ]
    if not instances:
        return CapabilityImpact()

    facts_by_id = None if facts is None else {capability_id: facts}
    available_by_source = await _available_capability_ids_by_source(deps)

    result = CapabilityImpact()
    for instance in instances:
        available_ids = available_by_source.get(instance.source_runtime_id)
        if available_ids is None:
            result.skipped_unreachable += 1
            continue
        if _dependency_is_broken(instance, capability_id, facts_by_id, available_ids):
            continue
        result.suspended_instances += 1
        result.instances.append(
            ImpactedInstance(
                agent_instance_id=instance.agent_instance_id,
                team_id=str(instance.team_id),
                display_name=instance.display_name,
            )
        )
    return result


__all__ = [
    "CapabilityImpact",
    "ImpactedInstance",
    "compute_capability_impact",
    "preview_revoke_impact",
]
