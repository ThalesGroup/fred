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
from fred_sdk.contracts.capability.manifest import model_capability_id
from fred_sdk.contracts.context import ModelBinding, resolve_effective_chat_profile

from control_plane_backend.capabilities.authz import (
    can_use_capability,
    usable_capability_ids,
)
from control_plane_backend.capabilities.catalog import (
    aggregate_capability_catalog,
    universally_available_chat_model_profile_ids,
)
from control_plane_backend.organization_authz import require_manage_any
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.routing_policy.schemas import (
    AvailableModelProfile,
    AvailableModelProfileList,
    EffectiveChatModel,
    PlatformModelBinding,
    ProfileNotUsableError,
    TeamRoutingPolicy,
    UnknownProfileError,
    UpdateTeamRoutingPolicyRequest,
)
from control_plane_backend.routing_policy.store import StoredPlatformModelBinding
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
    chat profile id -> its (provider, name)-keyed capability id
    (`TEAM-ROUTING-POLICY-RFC.md` §7.1's id-space translation).
    """

    catalog = await aggregate_capability_catalog(deps)
    mapping: dict[str, str] = {}
    for entry in catalog.values():
        if entry.kind != "model":
            continue
        for profile_id in entry.model_chat_profile_ids:
            mapping[profile_id] = entry.id
    return mapping


def _referenced_profile_ids(
    *,
    chat_default_profile_id: str | None,
    agent_profile_overrides: dict[str, str],
) -> list[str]:
    ids = list(agent_profile_overrides.values())
    if chat_default_profile_id is not None:
        ids.append(chat_default_profile_id)
    return ids


async def _team_source_runtime_ids(
    deps: ProductServiceDependencies, team_id: TeamId
) -> set[str]:
    """The pods `team_id`'s own agent instances actually run on — the only
    pods a chosen routing profile needs to resolve on for this team (see
    `universally_available_chat_model_profile_ids`). Same derivation
    `capabilities.service._revive_after_grant` uses."""

    instances = await deps.get_agent_instance_store().list_by_team(team_id)
    return {instance.source_runtime_id for instance in instances}


async def _validate_write(
    deps: ProductServiceDependencies,
    *,
    team_id: TeamId,
    request: UpdateTeamRoutingPolicyRequest,
) -> None:
    """Every referenced profile must be chat-capable, deployment-global, and
    `can_use`-enabled for `team_id`. Raises the first violation found rather
    than collecting all — matches `ModelRoutingPolicy`'s own fail-fast
    validators in fred-runtime. Uniqueness of the override itself
    (one profile per `agent_id`) is structural: `agent_profile_overrides` is
    a `dict`, so a duplicate key simply cannot be represented.

    "Known to this deployment" (profile ids are deployment-global, not
    pod-local) means present on every pod `team_id`'s own agent instances
    actually run on, not just one — `UnknownProfileError` also covers a
    profile a single such pod's YAML still carries but the others this team
    uses no longer serve uniformly. Validating against anything looser would
    let a write succeed today and drift-fail at runtime on a pod this team
    is actually using (`TeamRoutingProfileDriftError`).
    """

    referenced = _referenced_profile_ids(
        chat_default_profile_id=request.chat_default_profile_id,
        agent_profile_overrides=request.agent_profile_overrides,
    )
    if not referenced:
        return

    source_runtime_ids = await _team_source_runtime_ids(deps, team_id)

    # `_pod_catalog_fetch_scope` (product.service, lazy import to break the
    # product.service <-> routing_policy import cycle) de-dupes the pod
    # `/agents/models-catalog` fetch `_profile_to_capability_id_map` and
    # `universally_available_chat_model_profile_ids` would otherwise each make
    # independently — the union and the intersection are two views over the
    # exact same per-pod snapshot, so there is no reason to fetch it twice.
    from control_plane_backend.product.service import _pod_catalog_fetch_scope

    with _pod_catalog_fetch_scope():
        profile_to_capability = await _profile_to_capability_id_map(deps)
        universal = await universally_available_chat_model_profile_ids(
            deps, source_runtime_ids=source_runtime_ids
        )
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
        agent_profile_overrides=dict(stored.agent_profile_overrides),
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

    Also filtered to `universally_available_chat_model_profile_ids`, scoped to
    this team's own agent-instance pods (MDL#2), so this picker never offers
    a choice `_validate_write` would then reject — the two must agree on
    what "available" means, or a team could pick an option here and have the
    save fail.
    """

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_READ_MEMEBERS]
    )
    await _require_elevated_team_role(user, team_id, deps)
    source_runtime_ids = await _team_source_runtime_ids(deps, team_id)
    # `_pod_catalog_fetch_scope` (see `_validate_write` for why) de-dupes the
    # pod `/agents/models-catalog` fetch across these two catalog reads.
    from control_plane_backend.product.service import _pod_catalog_fetch_scope

    with _pod_catalog_fetch_scope():
        catalog = await aggregate_capability_catalog(deps)
        universal = await universally_available_chat_model_profile_ids(
            deps, source_runtime_ids=source_runtime_ids
        )
    usable = await usable_capability_ids(deps.team_dependencies.rebac, team_id)
    profiles = [
        AvailableModelProfile(
            profile_id=profile_id, capability_id=entry.id, name=entry.name
        )
        for entry in catalog.values()
        if entry.kind == "model" and (usable is None or entry.id in usable)
        for profile_id in entry.model_chat_profile_ids
        if profile_id in universal
    ]
    profiles.sort(key=lambda p: p.profile_id)
    return AvailableModelProfileList(profiles=profiles)


async def resolve_effective_chat_model(
    user: KeycloakUser,
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
) -> EffectiveChatModel:
    """Which concrete model a chat turn with `agent_instance_id` will use
    (#2387) — the composer's model label.

    Read gate is plain team membership (`CAN_READ_MEMEBERS`), deliberately NOT
    the elevated-role gate the policy read uses: anyone who can hold a
    conversation with this agent is entitled to know which model answers them.
    That is safe precisely because the result names only the MODEL — never which
    precedence level or profile id chose it, which is policy detail #2167
    restricts to an elevated role.

    Resolution mirrors `RoutedChatModelFactory.select` level for level, sharing
    its one implementation of the precedence
    (`fred_sdk.contracts.context.resolve_effective_chat_profile`). The pod
    consulted is the instance's OWN `source_runtime_id`, not an aggregate: an
    `AgentInstance` is pinned to one pod for its whole life and a turn is always
    prepared against that same pod, so another pod's catalog has no say in what
    this agent will run.

    Best-effort on an unreachable pod: returns an all-`None` result rather than
    raising. A pod being down must not break the chat page — the composer simply
    shows no model label, and the turn's own failure (or success) remains the
    authoritative signal.
    """

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_READ_MEMEBERS]
    )
    empty = EffectiveChatModel()

    instance = await deps.get_agent_instance_store().get_for_team(
        agent_instance_id, team_id
    )
    if instance is None:
        return empty

    # Whether reasoning actually runs on the model we end up naming. Read once
    # here and applied to every return path below: the composer must not offer
    # an inert toggle for a model whose reasoning is off, because
    # `RoutedChatModelFactory` strips the reasoning settings in that case.
    reasoning_enabled_ids = (
        await deps.get_model_reasoning_store().list_enabled_model_ids()
    )

    # A platform binding outranks every profile-valued level and bypasses team
    # enablement by design, so it short-circuits before any pod fetch — the
    # cheap path is also the authoritative one.
    platform_binding = await resolve_platform_chat_model_binding(deps)
    if platform_binding is not None:
        binding_capability_id = model_capability_id(
            platform_binding.provider, platform_binding.name
        )
        return EffectiveChatModel(
            name=platform_binding.name,
            capability_id=binding_capability_id,
            reasoning_enabled=binding_capability_id in reasoning_enabled_ids,
            # No `display_name`: an operator binding may name a model absent
            # from every pod catalog, so there is no profile to read an
            # ops-authored label from. The prettifying fallback covers it.
        )

    from control_plane_backend.product.service import (
        _model_capabilities_for_source,
        _pod_catalog_fetch_scope,
    )

    source = next(
        (
            candidate
            for candidate in deps.configuration.platform.runtime_catalog_sources
            # `enabled` matters as much as the id match: a disabled source is one
            # `prepare_execution` will refuse to prepare against, so naming a
            # model from its catalog would promise a turn that then fails.
            if candidate.enabled and candidate.runtime_id == instance.source_runtime_id
        ),
        None,
    )
    if source is None:
        return empty
    with _pod_catalog_fetch_scope():
        pod_models = await _model_capabilities_for_source(source.base_url)
    if pod_models is None:
        return empty

    stored = await deps.get_team_routing_policy_store().get(team_id=team_id)
    resolution = resolve_effective_chat_profile(
        agent_id=instance.source_agent_id,
        pod_agent_chat_profile_overrides=pod_models.agent_chat_profile_overrides,
        pod_default_chat_profile_id=pod_models.default_chat_profile_id,
        team_agent_profile_overrides=(
            stored.agent_profile_overrides if stored is not None else None
        ),
        team_chat_default_profile_id=(
            stored.chat_default_profile_id if stored is not None else None
        ),
    )
    if resolution is None:
        return empty

    entry = next(
        (
            candidate
            for candidate in pod_models.entries
            if resolution.profile_id in candidate.model_chat_profile_ids
        ),
        None,
    )
    if entry is None:
        # The winning profile is not a chat profile this pod advertises. For a
        # team-origin id that is exactly the drift
        # `TeamRoutingProfileDriftError` raises at turn time; either way there
        # is no concrete model to name, and inventing one would be worse than
        # showing none.
        return empty

    usable = await usable_capability_ids(deps.team_dependencies.rebac, team_id)
    return EffectiveChatModel(
        # `CapabilityCatalogEntry.name` already IS the concrete model name for a
        # `kind="model"` entry.
        name=entry.name,
        display_name=entry.model_display_name,
        capability_id=entry.id,
        # `None` means unrestricted (every capability usable), matching
        # `usable_capability_ids`' own contract — not "nothing usable".
        enabled_for_team=usable is None or entry.id in usable,
        reasoning_enabled=entry.id in reasoning_enabled_ids,
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
        agent_profile_overrides=request.agent_profile_overrides,
        updated_by=user.uid,
    )
    return TeamRoutingPolicy(
        team_id=stored.team_id,
        version=stored.version,
        chat_default_profile_id=stored.chat_default_profile_id,
        agent_profile_overrides=dict(stored.agent_profile_overrides),
    )


async def resolve_execution_routing_snapshot(
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> tuple[str | None, dict[str, str]]:
    """Resolve the `(chat_default_profile_id, agent_profile_overrides)` pair
    `ExecutionPreparation` threads to the runtime at prepare-execution —
    session-prep snapshot, not a per-turn lookup. No authz here: this runs as
    part of preparing a session the caller already owns/was granted, the same
    trust boundary `context_prompt_text` resolution already crosses.
    """

    store = deps.get_team_routing_policy_store()
    stored = await store.get(team_id=team_id)
    if stored is None:
        return None, {}
    return stored.chat_default_profile_id, dict(stored.agent_profile_overrides)


def _to_platform_model_binding(
    stored: StoredPlatformModelBinding | None,
) -> PlatformModelBinding:
    if stored is None:
        return PlatformModelBinding(binding=None)
    return PlatformModelBinding(
        binding=stored.binding,
        updated_by=stored.updated_by,
        updated_at=stored.updated_at,
    )


async def get_platform_model_binding(
    *, user: KeycloakUser, deps: ProductServiceDependencies
) -> PlatformModelBinding:
    """Org-admin-gated read of the platform-wide `chat` binding state
    (chat-only)."""

    await require_manage_any(deps.team_dependencies.rebac, user)
    store = deps.get_platform_model_binding_store()
    stored = await store.get()
    return _to_platform_model_binding(stored)


async def set_platform_model_binding(
    *,
    user: KeycloakUser,
    binding: ModelBinding,
    deps: ProductServiceDependencies,
) -> PlatformModelBinding:
    """Org-admin-gated write of the platform-wide `chat` binding.

    `binding` arrives already validated by `ModelBinding` (provider
    restricted to `fred_core.model.models.ModelProvider`, settings
    type-checked and range-checked by `ModelBindingSettings`) at
    request-parsing time, before this function even runs. The store persists
    that same validated object — see `PlatformModelBindingStore.set`.
    """

    await require_manage_any(deps.team_dependencies.rebac, user)
    store = deps.get_platform_model_binding_store()
    stored = await store.set(binding=binding, updated_by=user.uid)
    return _to_platform_model_binding(stored)


async def delete_platform_model_binding(
    *,
    user: KeycloakUser,
    deps: ProductServiceDependencies,
) -> PlatformModelBinding:
    """Org-admin-gated unset of the platform-wide `chat` binding.

    Returns the now-unset state (`binding=None`) rather than nothing, so the
    caller can render the row without a second read — same result shape as
    a successful `set`, regardless of whether a row actually existed to
    delete.
    """

    await require_manage_any(deps.team_dependencies.rebac, user)
    store = deps.get_platform_model_binding_store()
    await store.delete()
    return PlatformModelBinding(binding=None)


async def resolve_platform_chat_model_binding(
    deps: ProductServiceDependencies,
) -> ModelBinding | None:
    """Resolve the platform-wide `chat` binding for the runtime's per-turn,
    server-to-server `ManagedAgentRuntimeBinding` lookup
    (`get_runtime_binding_for_team`) — TRUSTED and re-read on every managed
    turn, including HITL resume, never a session-open snapshot forwarded by
    the client. No authz here: this call is already gated by that endpoint's
    own team ReBAC check, the same trust boundary `reasoning_enabled_model_ids`
    resolution already crosses on the same call.

    `PlatformModelBindingStore.get()` validates every row it reads through
    `ModelBinding` (`_binding_row_to_record`): a row that somehow smuggled a
    credential-shaped or unknown key past write-time validation — or was
    inserted by bypassing the store entirely — fails loudly there, and that
    failure propagates out of this function; it is not swallowed.

    Returns `None` only for the one case that actually means "no platform
    chat binding set": a successful store lookup that found no row — the
    common case on every deployment that hasn't configured one. Any other
    failure (DB error, connection-pool exhaustion, this table not yet
    existing mid-rollout, or a malformed persisted row failing
    `ModelBinding` validation) is an unknown-state failure, not a confirmed
    absence, and must propagate rather than be silently treated as "unset" —
    silently falling through to pod/team routing here is exactly the
    unauthenticated-fallback failure mode this binding exists to close. That
    propagates out of the `asyncio.gather` in `get_runtime_binding_for_team`
    and fails the whole per-turn `GET .../runtime` call, which is correct:
    this app registers no catch-all `Exception` handler (only typed
    domain errors get one — see `main.py`'s `register_*_exception_handlers`
    calls), so the exception reaches Starlette's own `ServerErrorMiddleware`,
    which returns 500 and re-raises for the ASGI server to log — this
    function does not log again on the way out, to avoid double-logging the
    same traceback.
    """

    store = deps.get_platform_model_binding_store()
    stored = await store.get()
    if stored is None:
        return None
    return stored.binding
