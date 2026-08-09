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

from fred_core import (
    AuthorizationError,
    KeycloakUser,
    RebacReference,
    Resource,
    TeamPermission,
)
from fred_core.common import TeamId, is_personal_team_id
from fred_sdk.contracts.context import TeamOperationRouteRule

from control_plane_backend.capabilities.authz import (
    can_use_capability,
    usable_capability_ids,
)
from control_plane_backend.capabilities.catalog import (
    aggregate_capability_catalog,
    universally_available_model_profile_ids,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.routing_policy.schemas import (
    AmbiguousOperationRuleError,
    AvailableModelProfile,
    AvailableModelProfileList,
    DuplicateOperationRuleError,
    DuplicateRuleIdError,
    ProfileNotUsableError,
    TeamRoutingPolicy,
    UnknownProfileError,
    UpdateTeamRoutingPolicyRequest,
)
from control_plane_backend.teams.service import require_team_access

# Read gate for routing policy (#2167 follow-up, explicit product decision):
# only team_admin, team_editor, or team_analyst may read a team's routing
# policy — a plain team_member must not. Each permission below is a proxy for
# exactly one team-role relation in schema.fga: CAN_UPDATE_INFO -> team_admin,
# CAN_UPDATE_RESOURCES -> team_editor, CAN_RUN_EVALUATIONS -> team_analyst or
# team_admin. Together their union is "holds an elevated team role", matching
# the frontend's `hasElevatedTeamRole` gate on the same "Routing" tab
# (`TeamSettingsPage.tsx`).
_ELEVATED_TEAM_ROLE_PERMISSIONS = (
    TeamPermission.CAN_UPDATE_INFO,
    TeamPermission.CAN_UPDATE_RESOURCES,
    TeamPermission.CAN_RUN_EVALUATIONS,
)


async def _require_elevated_team_role(
    user: KeycloakUser, team_id: TeamId, deps: ProductServiceDependencies
) -> None:
    """Narrower than the shared `can_read_members` permission
    (`schema.fga`: `can_read_members: team_member`) `require_team_access`
    already checked before this runs — that permission is wider on purpose
    because it also backs unrelated surfaces (KPI scope, task activity,
    corpus manager) this change must not touch. `require_team_access`'s
    `required_permissions` list is AND-only
    (`check_user_team_permissions_or_raise`), so it cannot express "holds any
    one of these three roles" — one `has_permissions` BatchCheck instead,
    OR'd locally.

    Skipped for personal spaces: the owner holds `team_editor`
    unconditionally (RFC §1) and `require_team_access` already let system
    teams through without touching ReBAC at all; a second, independent ReBAC
    round trip here could race the owner's lazily self-healed `team_editor`
    tuple (`platform/REBAC.md` "Personal teams") and wrongly deny them.
    `team_id` must be the canonical id `require_team_access` returned, not
    the raw path param — `is_personal_team_id` only matches
    `"personal-<uid>"`, never the `"personal"` alias.
    """

    if is_personal_team_id(team_id):
        return
    allowed = await deps.team_dependencies.rebac.has_permissions(
        RebacReference(Resource.USER, user.uid),
        list(_ELEVATED_TEAM_ROLE_PERMISSIONS),
        RebacReference(Resource.TEAM, team_id),
    )
    if not any(allowed):
        raise AuthorizationError(
            user_id=user.uid,
            action="read_routing_policy",
            resource=Resource.TEAM,
            message="You are not allowed to view this team's routing policy. Only team admins, editors, or analysts can.",
        )


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


def _specificity(rule: TeamOperationRouteRule) -> int:
    """How many of the three optional match criteria this rule pins down —
    mirrors the resolver's own tie-break scoring (`resolve_team_override`)."""

    return (
        (rule.operation is not None)
        + (rule.purpose is not None)
        + (rule.agent_id is not None)
    )


def _could_both_match_one_request(
    a: TeamOperationRouteRule, b: TeamOperationRouteRule
) -> bool:
    """True when some concrete request could satisfy both rules at once —
    every field where both rules pin a value agrees; a None (wildcard) on
    either side never blocks a match."""

    for value_a, value_b in (
        (a.operation, b.operation),
        (a.purpose, b.purpose),
        (a.agent_id, b.agent_id),
    ):
        if value_a is not None and value_b is not None and value_a != value_b:
            return False
    return True


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

    "Known to this deployment" (§9: profile ids are deployment-global, not
    pod-local) means present on *every* enabled, model-capable pod, not just
    one — `UnknownProfileError` also covers a profile a single pod's YAML
    still carries but the deployment as a whole no longer serves uniformly
    (2026-08-02, MDL#2 follow-up to #2191). Validating against anything
    looser would let a write succeed today and drift-fail at runtime on
    whichever pod actually lacks it (`TeamRoutingProfileDriftError`).
    """

    seen_rule_ids: set[str] = set()
    for rule in request.operation_rules:
        if rule.rule_id in seen_rule_ids:
            raise DuplicateRuleIdError(rule_id=rule.rule_id)
        seen_rule_ids.add(rule.rule_id)

    # Resolution is fixed and deterministic — never a scoring tie-break an
    # admin has to reason about (RFC §3.2). Two rules that share an exact
    # (operation, purpose, agent_id) triplet are rejected outright; two rules
    # that could both match one request with equal specificity but differ in
    # which criteria they pin (e.g. one keys on agent_id+operation, the other
    # on agent_id+purpose, for the same agent) are rejected too — the
    # resolver would otherwise break that tie by declaration order, an
    # outcome this UI never surfaces to the person editing it.
    rules = request.operation_rules
    for i, rule_a in enumerate(rules):
        for rule_b in rules[i + 1 :]:
            if not _could_both_match_one_request(rule_a, rule_b):
                continue
            if (
                rule_a.operation == rule_b.operation
                and rule_a.purpose == rule_b.purpose
                and rule_a.agent_id == rule_b.agent_id
            ):
                raise DuplicateOperationRuleError(
                    operation=rule_a.operation, purpose=rule_a.purpose, agent_id=rule_a.agent_id
                )
            if _specificity(rule_a) == _specificity(rule_b):
                raise AmbiguousOperationRuleError(
                    rule_id_a=rule_a.rule_id, rule_id_b=rule_b.rule_id
                )

    referenced = _referenced_profile_ids(
        chat_default_profile_id=request.chat_default_profile_id,
        operation_rules=request.operation_rules,
    )
    if not referenced:
        return

    # `_pod_catalog_fetch_scope` (product.service, lazy import to break the
    # product.service <-> routing_policy import cycle) de-dupes the pod
    # `/agents/models-catalog` fetch `_profile_to_capability_id_map` and
    # `universally_available_model_profile_ids` would otherwise each make
    # independently — the union and the intersection are two views over the
    # exact same per-pod snapshot, so there is no reason to fetch it twice.
    from control_plane_backend.product.service import _pod_catalog_fetch_scope

    with _pod_catalog_fetch_scope():
        profile_to_capability = await _profile_to_capability_id_map(deps)
        universal = await universally_available_model_profile_ids(deps)
    unknown = sorted(
        {p for p in referenced if p not in profile_to_capability or p not in universal}
    )
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
    """RFC §6 read gate: team_admin, team_editor, or team_analyst (elevated
    roles) — `can_read_members` alone (checked first, below) is wider
    (`team_member`) and shared with unrelated surfaces, so
    `_require_elevated_team_role` narrows it for this read specifically
    (#2167 follow-up). Personal-space owners pass through ungated, same as
    every other system-team read (`require_team_access`)."""

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_READ_MEMEBERS]
    )
    await _require_elevated_team_role(user, team_id, deps)
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


async def list_available_model_profiles(
    user: KeycloakUser,
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> AvailableModelProfileList:
    """RFC §13's picker option set: every `kind="model"` profile_id this team
    is `can_use`-enabled for. Same read gate as the routing policy itself
    (team_admin/team_editor/team_analyst, #2167 follow-up) — this reads the
    team's own enablement state, not the platform-admin aggregate list gated
    on `capability#can_manage`.

    Also filtered to `universally_available_model_profile_ids` (2026-08-02,
    MDL#2) so this picker never offers a choice `_validate_write` would then
    reject — the two must agree on what "available" means, or a team could
    pick an option here and have the save fail.
    """

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_READ_MEMEBERS]
    )
    await _require_elevated_team_role(user, team_id, deps)
    # `_pod_catalog_fetch_scope` (see `_validate_write` for why) de-dupes the
    # pod `/agents/models-catalog` fetch across these two catalog reads.
    from control_plane_backend.product.service import _pod_catalog_fetch_scope

    with _pod_catalog_fetch_scope():
        catalog = await aggregate_capability_catalog(deps)
        universal = await universally_available_model_profile_ids(deps)
    usable = await usable_capability_ids(deps.team_dependencies.rebac, team_id)
    profiles = [
        AvailableModelProfile(
            profile_id=profile_id, capability_id=entry.id, name=entry.name
        )
        for entry in catalog.values()
        if entry.kind == "model" and (usable is None or entry.id in usable)
        for profile_id in entry.model_profile_ids
        if profile_id in universal
    ]
    profiles.sort(key=lambda p: p.profile_id)
    return AvailableModelProfileList(profiles=profiles)


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
