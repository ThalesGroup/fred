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
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fred_core.common import TeamId

from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.capabilities.authz import usable_capability_ids
from control_plane_backend.product.dependencies import ProductServiceDependencies

logger = logging.getLogger(__name__)


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


async def _usable_ids_by_team(
    deps: ProductServiceDependencies,
    team_ids: set[TeamId],
) -> dict[TeamId, set[str] | None]:
    """`can_use` capability ids per team — ONE `ListObjects` per team.

    `can_use` is a TEAM-subject check (RFC §8.1), so authorization is a property
    of (capability, space) and never fans out per agent instance: a team with 50
    agents still costs one lookup. `None` means ReBAC is disabled — "no scoping",
    every capability usable (matching `usable_capability_ids`).
    """

    rebac = deps.team_dependencies.rebac
    return {
        team_id: await usable_capability_ids(rebac, team_id) for team_id in team_ids
    }


def _broken_capability_ids(
    instance: AgentInstanceRecord,
    usable_ids: set[str] | None,
    available_ids: frozenset[str] | None,
) -> list[str]:
    """The instance's selected capabilities that are NOT currently usable.

    A capability is broken for this instance when the team lacks `can_use` on it
    OR its pod no longer advertises it — the two independent failure modes
    behind `capability_access_revoked` and `capability_unavailable`.

    `usable_ids=None` (ReBAC disabled) skips the authorization half;
    `available_ids=None` (unreachable pod) must be handled by the CALLER, which
    reports the instance as unknown rather than broken — this function is only
    reached with a known pod set.
    """

    selected = instance.tuning.selected_capability_ids or []
    broken: list[str] = []
    for cap_id in selected:
        denied = usable_ids is not None and cap_id not in usable_ids
        missing = available_ids is not None and cap_id not in available_ids
        if denied or missing:
            broken.append(cap_id)
    return broken


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

    Cost is bounded by design: one `ListObjects` per team with instances (NOT
    per instance) plus one template fetch per runtime pod. With the handful of
    pods this platform runs, that is a few round-trips for an admin-only screen.

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
    usable_by_team = await _usable_ids_by_team(
        deps, {instance.team_id for instance in instances}
    )

    impact: dict[str, CapabilityImpact] = {}
    for instance in instances:
        available_ids = available_by_source.get(instance.source_runtime_id)
        if available_ids is None:
            # Pod unreachable — the sweep would skip this instance rather than
            # suspend it, so its impact is UNKNOWN. Attribute the skip to each
            # selected capability so the caller can say "unknown", not "fine".
            for cap_id in instance.tuning.selected_capability_ids or []:
                impact.setdefault(cap_id, CapabilityImpact()).skipped_unreachable += 1
            continue

        broken = _broken_capability_ids(
            instance, usable_by_team.get(instance.team_id), available_ids
        )
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
    """

    from control_plane_backend.product.service import (
        _available_capability_ids_by_source,
    )

    instance_store = store or deps.get_agent_instance_store()
    instances = (
        await instance_store.list_by_team(team_id)
        if team_id is not None
        else await instance_store.list_all()
    )
    # Only instances that actually selected the capability can be affected.
    instances = [
        instance
        for instance in instances
        if capability_id in (instance.tuning.selected_capability_ids or [])
    ]
    if not instances:
        return CapabilityImpact()

    available_by_source = await _available_capability_ids_by_source(deps)
    usable_by_team = await _usable_ids_by_team(
        deps, {instance.team_id for instance in instances}
    )

    result = CapabilityImpact()
    for instance in instances:
        available_ids = available_by_source.get(instance.source_runtime_id)
        if available_ids is None:
            result.skipped_unreachable += 1
            continue
        already_broken = capability_id in _broken_capability_ids(
            instance, usable_by_team.get(instance.team_id), available_ids
        )
        if already_broken:
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
