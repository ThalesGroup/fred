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
Request-scoped service layer for team routing policy (TEAM-05, #2118,
`TEAM-ROUTING-POLICY-RFC.md`).

Mirrors `capabilities/service.py`'s shape: aggregate the pod catalog,
authorize, validate, delegate the write to the store. Kept as its own
package (not folded into `teams/`) for the same reason `capabilities/` is
its own package — a merge-isolated feature slice.
"""

from __future__ import annotations

from fred_core import KeycloakUser, TeamPermission
from fred_core.common import TeamId
from fred_sdk.contracts.context import TeamOperationRouteRule

from control_plane_backend.capabilities.authz import can_use_capability
from control_plane_backend.capabilities.catalog import aggregate_capability_catalog
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.routing_policy.schemas import (
    DuplicateOperationRuleError,
    ProfileNotUsableError,
    TeamRoutingPolicy,
    UnknownProfileError,
    UpdateTeamRoutingPolicyRequest,
)
from control_plane_backend.teams.service import require_team_access


async def _profile_to_capability_id_map(
    deps: ProductServiceDependencies,
) -> dict[str, str]:
    """Reverse-index the aggregated `kind="model"` catalog: every advertised
    `profile_id` -> its (provider, name)-keyed capability id
    (`TEAM-ROUTING-POLICY-RFC.md` §7.1's id-space translation).
    """

    catalog = await aggregate_capability_catalog(deps)
    mapping: dict[str, str] = {}
    for entry in catalog.values():
        if entry.kind != "model":
            continue
        for profile_id in entry.model_profile_ids:
            mapping[profile_id] = entry.id
    return mapping


def _referenced_profile_ids(
    *,
    chat_default_profile_id: str | None,
    operation_rules: list[TeamOperationRouteRule],
) -> list[str]:
    ids = [r.target_profile_id for r in operation_rules]
    if chat_default_profile_id is not None:
        ids.append(chat_default_profile_id)
    return ids


async def _validate_write(
    deps: ProductServiceDependencies,
    *,
    team_id: TeamId,
    request: UpdateTeamRoutingPolicyRequest,
) -> None:
    """RFC §3.2 + §7.2: unique rule_id / unique (operation, purpose), every
    referenced profile known to this deployment and `can_use`-enabled for
    `team_id`. Raises the first violation found rather than collecting all —
    matches `ModelRoutingPolicy`'s own fail-fast validators in fred-runtime.
    """

    rule_ids = [r.rule_id for r in request.operation_rules]
    if len(set(rule_ids)) != len(rule_ids):
        raise DuplicateOperationRuleError(operation="*", purpose=None)

    seen_op_purpose: set[tuple[str, str | None]] = set()
    for rule in request.operation_rules:
        key = (rule.operation, rule.purpose)
        if key in seen_op_purpose:
            raise DuplicateOperationRuleError(
                operation=rule.operation, purpose=rule.purpose
            )
        seen_op_purpose.add(key)

    referenced = _referenced_profile_ids(
        chat_default_profile_id=request.chat_default_profile_id,
        operation_rules=request.operation_rules,
    )
    if not referenced:
        return

    profile_to_capability = await _profile_to_capability_id_map(deps)
    unknown = sorted({p for p in referenced if p not in profile_to_capability})
    if unknown:
        raise UnknownProfileError(profile_ids=unknown)

    rebac = deps.team_dependencies.rebac
    not_usable: list[str] = []
    checked_capability_ids: set[str] = set()
    for profile_id in referenced:
        capability_id = profile_to_capability[profile_id]
        if capability_id in checked_capability_ids:
            continue
        checked_capability_ids.add(capability_id)
        if not await can_use_capability(rebac, team_id, capability_id):
            not_usable.append(profile_id)
    if not_usable:
        raise ProfileNotUsableError(team_id=team_id, profile_ids=sorted(not_usable))


async def get_team_routing_policy(
    user: KeycloakUser,
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> TeamRoutingPolicy:
    """RFC §6 read gate: team_admin or team_editor (elevated roles) — reusing
    `can_read_members`, the same permission Activity's `scope=team` view
    already requires, rather than inventing a new ReBAC relation for this one
    read. Personal-space owners pass through ungated, same as every other
    system-team read (`require_team_access`)."""

    await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_READ_MEMEBERS]
    )
    store = deps.get_team_routing_policy_store()
    stored = await store.get(team_id=team_id)
    if stored is None:
        return TeamRoutingPolicy(team_id=team_id, version=0)
    return TeamRoutingPolicy(
        team_id=stored.team_id,
        version=stored.version,
        chat_default_profile_id=stored.chat_default_profile_id,
        operation_rules=list(stored.operation_rules),
    )


async def update_team_routing_policy(
    user: KeycloakUser,
    team_id: TeamId,
    request: UpdateTeamRoutingPolicyRequest,
    deps: ProductServiceDependencies,
) -> TeamRoutingPolicy:
    """RFC §6 write gate: `team_editor` only (`CAN_UPDATE_RESOURCES`) —
    `team_admin` has zero write authority here, orthogonal not hierarchical
    (`platform/REBAC.md` "hard cross-write rule"). A personal-space owner
    holds `team_editor` unconditionally, so this is the same code path for
    both (RFC §1)."""

    await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_UPDATE_RESOURCES]
    )
    await _validate_write(deps, team_id=team_id, request=request)

    store = deps.get_team_routing_policy_store()
    stored = await store.upsert(
        team_id=team_id,
        chat_default_profile_id=request.chat_default_profile_id,
        operation_rules=request.operation_rules,
        updated_by=user.uid,
    )
    return TeamRoutingPolicy(
        team_id=stored.team_id,
        version=stored.version,
        chat_default_profile_id=stored.chat_default_profile_id,
        operation_rules=list(stored.operation_rules),
    )


async def resolve_execution_routing_snapshot(
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> tuple[str | None, list[TeamOperationRouteRule]]:
    """Resolve the `(chat_default_profile_id, operation_route_rules)` pair
    `ExecutionPreparation` threads to the runtime at prepare-execution
    (`TEAM-ROUTING-POLICY-RFC.md` §8.2) — session-prep snapshot, not a
    per-turn lookup (§8.1). No authz here: this runs as part of preparing a
    session the caller already owns/was granted, the same trust boundary
    `context_prompt_text` resolution already crosses.
    """

    store = deps.get_team_routing_policy_store()
    stored = await store.get(team_id=team_id)
    if stored is None:
        return None, []
    return stored.chat_default_profile_id, list(stored.operation_rules)
