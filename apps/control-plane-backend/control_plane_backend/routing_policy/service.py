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

import asyncio

from fred_core import (
    AuthorizationError,
    KeycloakUser,
    RebacReference,
    Resource,
    TeamPermission,
)
from fred_core.common import TeamId, is_personal_team_id
from fred_sdk.contracts.capability.manifest import model_capability_id
from fred_sdk.contracts.context import (
    ChatProfileOrigin,
    ModelBinding,
    resolve_effective_chat_profile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane_backend.capabilities.authz import (
    can_team_use_capability,
    usable_capability_ids,
)
from control_plane_backend.capabilities.catalog import (
    aggregate_capability_catalog,
    universally_available_chat_model_profile_ids,
)
from control_plane_backend.organization_authz import require_manage_capabilities
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.routing_policy.schemas import (
    AvailableModelProfile,
    AvailableModelProfileList,
    DefaultModelNotDisableableError,
    DisableImpact,
    DisableImpactAgent,
    EffectiveChatModel,
    ModelCatalogUnavailableError,
    ModelDisabledForTeamError,
    PlatformModelBinding,
    ProfileNotUsableError,
    SelectableChatModel,
    TeamRoutingPolicy,
    UnknownProfileError,
    UpdateTeamRoutingPolicyRequest,
)
from control_plane_backend.routing_policy.store import (
    StoredPlatformModelBinding,
    StoredTeamRoutingPolicy,
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


async def _team_source_runtime_ids(
    deps: ProductServiceDependencies, team_id: TeamId
) -> set[str]:
    """The pods `team_id`'s own agent instances actually run on — the only
    pods a chosen routing profile needs to resolve on for this team (see
    `universally_available_chat_model_profile_ids`). Same derivation
    `capabilities.service._revive_after_grant` uses."""

    instances = await deps.get_agent_instance_store().list_by_team(team_id)
    return {instance.source_runtime_id for instance in instances}


def _team_sources(deps: ProductServiceDependencies, source_runtime_ids: set[str]):
    return [
        source
        for source in deps.configuration.platform.runtime_catalog_sources
        if source.enabled
        and (not source_runtime_ids or source.runtime_id in source_runtime_ids)
    ]


async def _team_pod_default_profiles(
    deps: ProductServiceDependencies, source_runtime_ids: set[str]
) -> list[tuple[str, str]]:
    """`(profile_id, capability_id)` of each relevant pod's chat default: the
    team's effective default when it stores none. Call inside
    `_pod_catalog_fetch_scope` so the pod fetch is shared."""

    from control_plane_backend.product.service import _model_capabilities_for_source

    catalogs = await asyncio.gather(
        *(
            _model_capabilities_for_source(source.base_url)
            for source in _team_sources(deps, source_runtime_ids)
        )
    )
    defaults: list[tuple[str, str]] = []
    for catalog in catalogs:
        if catalog is None or catalog.default_chat_profile_id is None:
            continue
        entry = next(
            (
                candidate
                for candidate in catalog.entries
                if catalog.default_chat_profile_id in candidate.model_chat_profile_ids
            ),
            None,
        )
        if entry is not None:
            defaults.append((catalog.default_chat_profile_id, entry.id))
    return defaults


async def _unreachable_team_pods(
    deps: ProductServiceDependencies, source_runtime_ids: set[str]
) -> list[str]:
    """Runtime ids of the team's pods whose model catalog could not be read.
    Call inside `_pod_catalog_fetch_scope`: it reuses the same fetches."""

    from control_plane_backend.product.service import _model_capabilities_for_source

    sources = _team_sources(deps, source_runtime_ids)
    catalogs = await asyncio.gather(
        *(_model_capabilities_for_source(source.base_url) for source in sources)
    )
    return sorted(
        source.runtime_id
        for source, catalog in zip(sources, catalogs)
        if catalog is None
    )


def _stored_lists(
    stored: StoredTeamRoutingPolicy | None,
) -> tuple[frozenset[str], frozenset[str]]:
    if stored is None:
        return frozenset(), frozenset()
    return frozenset(stored.disabled_model_ids), frozenset(
        stored.reasoning_default_off_model_ids
    )


async def check_profile_usable_for_team(
    deps: ProductServiceDependencies,
    *,
    team_id: TeamId,
    profile_id: str,
    source_runtime_ids: set[str],
) -> str:
    """One profile must be a chat profile served across `source_runtime_ids`,
    `can_use`-enabled for `team_id` and not disabled by the team. Used for an
    instance's recommended model and the evaluator's `agent_model_override`.
    Returns the profile's model capability id.

    Raises `UnknownProfileError`, `ProfileNotUsableError` or
    `ModelDisabledForTeamError` rather than a bool, so a bad value is
    diagnosable.
    """

    # Lazy import: breaks the product.service <-> routing_policy import cycle.
    from control_plane_backend.product.service import _pod_catalog_fetch_scope

    with _pod_catalog_fetch_scope():
        profile_to_capability = await _profile_to_capability_id_map(deps)
        universal = await universally_available_chat_model_profile_ids(
            deps, source_runtime_ids=source_runtime_ids
        )
    if profile_id not in profile_to_capability or profile_id not in universal:
        raise UnknownProfileError(profile_ids=[profile_id])
    capability_id = profile_to_capability[profile_id]
    if not await can_team_use_capability(
        deps.team_dependencies.rebac, team_id, capability_id=capability_id
    ):
        raise ProfileNotUsableError(team_id=team_id, profile_ids=[profile_id])
    stored = await deps.get_team_routing_policy_store().get(team_id=team_id)
    if stored is not None and capability_id in stored.disabled_model_ids:
        raise ModelDisabledForTeamError(team_id=team_id, profile_ids=[profile_id])
    return capability_id


def _to_team_routing_policy(
    team_id: TeamId, stored: StoredTeamRoutingPolicy | None
) -> TeamRoutingPolicy:
    if stored is None:
        return TeamRoutingPolicy(team_id=team_id, version=0)
    return TeamRoutingPolicy(
        team_id=stored.team_id,
        version=stored.version,
        chat_default_profile_id=stored.chat_default_profile_id,
        disabled_model_ids=list(stored.disabled_model_ids),
        reasoning_default_off_model_ids=list(stored.reasoning_default_off_model_ids),
    )


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
    stored = await deps.get_team_routing_policy_store().get(team_id=team_id)
    return _to_team_routing_policy(team_id, stored)


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
    a choice `update_team_routing_policy` would then reject — the two must agree on
    what "available" means, or a team could pick an option here and have the
    save fail.
    """

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_READ_MEMEBERS]
    )
    await _require_elevated_team_role(user, team_id, deps)
    source_runtime_ids = await _team_source_runtime_ids(deps, team_id)
    stored, reasoning_enabled_ids = await asyncio.gather(
        deps.get_team_routing_policy_store().get(team_id=team_id),
        deps.get_model_reasoning_store().list_enabled_model_ids(),
    )
    # `_pod_catalog_fetch_scope` de-dupes the pod `/agents/models-catalog`
    # fetch across these catalog reads: they are views of one snapshot.
    from control_plane_backend.product.service import _pod_catalog_fetch_scope

    with _pod_catalog_fetch_scope():
        catalog = await aggregate_capability_catalog(deps)
        universal = await universally_available_chat_model_profile_ids(
            deps, source_runtime_ids=source_runtime_ids
        )
        pod_defaults = (
            await _team_pod_default_profiles(deps, source_runtime_ids)
            if stored is None or stored.chat_default_profile_id is None
            else []
        )
    usable = await usable_capability_ids(deps.team_dependencies.rebac, team_id)
    profiles = [
        AvailableModelProfile(
            profile_id=profile_id,
            capability_id=entry.id,
            name=entry.name,
            display_name=entry.model_display_name,
            reasoning_available=entry.id in reasoning_enabled_ids,
        )
        for entry in catalog.values()
        if entry.kind == "model" and (usable is None or entry.id in usable)
        for profile_id in entry.model_chat_profile_ids
        if profile_id in universal
    ]
    profiles.sort(key=lambda p: p.profile_id)
    if stored is not None and stored.chat_default_profile_id is not None:
        effective_default = stored.chat_default_profile_id
    elif pod_defaults and len({cap for _, cap in pod_defaults}) == 1:
        # Pods that disagree have no single default to show; every one of
        # their defaults stays non-disableable on write.
        effective_default = pod_defaults[0][0]
    else:
        effective_default = None
    return AvailableModelProfileList(
        profiles=profiles, effective_default_profile_id=effective_default
    )


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
            choice_locked=True,
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

    stored, usable = await asyncio.gather(
        deps.get_team_routing_policy_store().get(team_id=team_id),
        usable_capability_ids(deps.team_dependencies.rebac, team_id),
    )
    disabled, reasoning_off = _stored_lists(stored)
    # Chat profile -> its pod entry, for this pod only.
    entry_by_profile = {
        profile_id: entry
        for entry in pod_models.entries
        for profile_id in entry.model_chat_profile_ids
    }

    def _selectable(capability_id: str) -> bool:
        return (usable is None or capability_id in usable) and (
            capability_id not in disabled
        )

    # Same validation the pod applies before trusting the recommendation.
    recommended = instance.tuning.recommended_chat_profile_id
    recommended_entry = entry_by_profile.get(recommended) if recommended else None
    resolution = resolve_effective_chat_profile(
        agent_id=instance.source_agent_id,
        pod_agent_chat_profile_overrides=pod_models.agent_chat_profile_overrides,
        pod_default_chat_profile_id=pod_models.default_chat_profile_id,
        # No user level: this read names what a NEW conversation starts on.
        user_chat_profile_id=None,
        instance_chat_profile_id=(
            recommended
            if recommended_entry is not None and _selectable(recommended_entry.id)
            else None
        ),
        team_chat_default_profile_id=(
            stored.chat_default_profile_id if stored is not None else None
        ),
    )
    if resolution is None:
        return empty

    entry = entry_by_profile.get(resolution.profile_id)
    if entry is None:
        # The winning profile is not a chat profile this pod advertises. For a
        # team-origin id that is exactly the drift
        # `TeamRoutingProfileDriftError` raises at turn time; either way there
        # is no concrete model to name, and inventing one would be worse than
        # showing none.
        return empty

    choice_locked = resolution.origin is ChatProfileOrigin.POD_AGENT_OVERRIDE
    selectable: dict[str, SelectableChatModel] = {}
    if not choice_locked:
        # One row per model; the resolved profile keys its own model's row so
        # picking the recommended model sends the same profile.
        for candidate in pod_models.entries:
            if candidate.id in selectable or not _selectable(candidate.id):
                continue
            if not candidate.model_chat_profile_ids:
                continue
            reasoning_enabled = candidate.id in reasoning_enabled_ids
            selectable[candidate.id] = SelectableChatModel(
                profile_id=(
                    resolution.profile_id
                    if candidate.id == entry.id
                    else candidate.model_chat_profile_ids[0]
                ),
                capability_id=candidate.id,
                name=candidate.name,
                display_name=candidate.model_display_name,
                reasoning_enabled=reasoning_enabled,
                reasoning_default_on=reasoning_enabled
                and candidate.id not in reasoning_off,
            )
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
        selectable_models=list(selectable.values()),
        choice_locked=choice_locked,
    )


async def update_team_routing_policy(
    user: KeycloakUser,
    team_id: TeamId,
    request: UpdateTeamRoutingPolicyRequest,
    deps: ProductServiceDependencies,
) -> TeamRoutingPolicy:
    """Write gate: team_admin only (`CAN_UPDATE_INFO`). A personal space's
    owner passes through `require_team_access`'s system-team bypass.

    The default must be a usable chat profile served by the team's pods, and
    its model (or, with no stored default, every pod default) cannot be
    disabled. Exception ids the team can no longer use are pruned. Newly
    disabled models clear the team's recommendations naming them, in the
    same transaction as the policy write.
    """

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_UPDATE_INFO]
    )
    store = deps.get_team_routing_policy_store()
    previous = await store.get(team_id=team_id)
    disabled = set(request.disabled_model_ids)
    reasoning_off = set(request.reasoning_default_off_model_ids)
    default_profile_id = request.chat_default_profile_id
    rebac = deps.team_dependencies.rebac

    profile_to_capability: dict[str, str] = {}
    unreachable: list[str] = []
    if default_profile_id is not None or disabled:
        source_runtime_ids = await _team_source_runtime_ids(deps, team_id)
        from control_plane_backend.product.service import _pod_catalog_fetch_scope

        with _pod_catalog_fetch_scope():
            profile_to_capability = await _profile_to_capability_id_map(deps)
            universal = await universally_available_chat_model_profile_ids(
                deps, source_runtime_ids=source_runtime_ids
            )
            pod_defaults = (
                await _team_pod_default_profiles(deps, source_runtime_ids)
                if default_profile_id is None and disabled
                else []
            )
            if disabled:
                unreachable = await _unreachable_team_pods(deps, source_runtime_ids)
        protected: set[str] = {capability for _, capability in pod_defaults}
        if default_profile_id is not None:
            if (
                default_profile_id not in profile_to_capability
                or default_profile_id not in universal
            ):
                raise UnknownProfileError(profile_ids=[default_profile_id])
            default_capability = profile_to_capability[default_profile_id]
            if not await can_team_use_capability(
                rebac, team_id, capability_id=default_capability
            ):
                raise ProfileNotUsableError(
                    team_id=team_id, profile_ids=[default_profile_id]
                )
            protected = {default_capability}
        blocked = sorted(protected & disabled)
        if blocked:
            raise DefaultModelNotDisableableError(capability_ids=blocked)

    if disabled or reasoning_off:
        usable = await usable_capability_ids(rebac, team_id)
        if usable is not None:
            disabled &= usable
            reasoning_off &= usable

    previously_disabled, _ = _stored_lists(previous)
    newly_disabled = disabled - previously_disabled
    # A missing pod catalog hides its default (which must stay enabled) and its
    # profiles (whose recommendations must clear): refuse instead of guessing.
    if unreachable and ((default_profile_id is None and disabled) or newly_disabled):
        raise ModelCatalogUnavailableError(runtime_ids=unreachable)
    stored = await store.upsert(
        team_id=team_id,
        chat_default_profile_id=default_profile_id,
        disabled_model_ids=sorted(disabled),
        reasoning_default_off_model_ids=sorted(reasoning_off),
        updated_by=user.uid,
        expected_version=request.expected_version,
        cleared_recommendation_profile_ids=frozenset(
            profile_id
            for profile_id, capability in profile_to_capability.items()
            if capability in newly_disabled
        ),
    )
    return _to_team_routing_policy(team_id, stored)


async def get_disable_impact(
    user: KeycloakUser,
    team_id: TeamId,
    capability_id: str,
    deps: ProductServiceDependencies,
) -> DisableImpact:
    """Agents whose recommendation names `capability_id`, i.e. those that
    would follow the team default once it is disabled. Team_admin only: it
    exposes agent names. One instance query plus the shared catalog fetch."""

    team_id = await require_team_access(
        user, team_id, deps.team_dependencies, [TeamPermission.CAN_UPDATE_INFO]
    )
    instances = await deps.get_agent_instance_store().list_by_team(team_id)
    recommending = [
        instance
        for instance in instances
        if instance.tuning.recommended_chat_profile_id is not None
    ]
    if not recommending:
        return DisableImpact()
    from control_plane_backend.product.service import _pod_catalog_fetch_scope

    with _pod_catalog_fetch_scope():
        profile_to_capability = await _profile_to_capability_id_map(deps)
    agents = [
        DisableImpactAgent(
            agent_instance_id=instance.agent_instance_id,
            display_name=instance.display_name,
        )
        for instance in recommending
        if profile_to_capability.get(instance.tuning.recommended_chat_profile_id or "")
        == capability_id
    ]
    agents.sort(key=lambda agent: (agent.display_name, agent.agent_instance_id))
    return DisableImpact(agents=agents)


async def apply_model_revocation(
    deps: ProductServiceDependencies,
    *,
    capability_id: str,
    profile_ids: frozenset[str],
    team_ids: set[TeamId] | None,
) -> int:
    """After the platform withdrew `capability_id`, clear recommendations and
    team defaults naming one of its `profile_ids` (the pod default takes
    over, so turns keep working) and prune it from team exception lists.
    `team_ids` are teams known to have lost it (team revoke); `None` scans
    every team and keeps those still granted another way (platform-wide
    revoke). Returns how many recommendations were cleared."""

    store = deps.get_team_routing_policy_store()
    if team_ids is None:
        candidates: set[TeamId] = set(
            await store.list_team_ids_referencing_model(capability_id, profile_ids)
        )
        if profile_ids:
            candidates.update(
                instance.team_id
                for instance in await deps.get_agent_instance_store().list_all()
                if instance.tuning.recommended_chat_profile_id in profile_ids
            )
    else:
        candidates = set(team_ids)
    cleared = 0
    rebac = deps.team_dependencies.rebac
    for team_id in sorted(candidates):
        if team_ids is None and await can_team_use_capability(
            rebac, team_id, capability_id=capability_id
        ):
            continue
        cleared += len(
            await store.apply_model_revocation(
                team_id=team_id,
                capability_id=capability_id,
                recommendation_profile_ids=profile_ids,
            )
        )
    return cleared


async def resolve_execution_routing_snapshot(
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> str | None:
    """The team's default chat profile `ExecutionPreparation` threads to the
    runtime at prepare-execution — session-prep snapshot, not a per-turn
    lookup. No authz here: this runs as part of preparing a session the
    caller already owns/was granted, the same trust boundary
    `context_prompt_text` resolution already crosses.
    """

    stored = await deps.get_team_routing_policy_store().get(team_id=team_id)
    return stored.chat_default_profile_id if stored is not None else None


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
    """Feature-governance-gated read of the platform-wide `chat` binding state
    (chat-only)."""

    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    store = deps.get_platform_model_binding_store()
    stored = await store.get()
    return _to_platform_model_binding(stored)


async def set_platform_model_binding(
    *,
    user: KeycloakUser,
    binding: ModelBinding,
    deps: ProductServiceDependencies,
) -> PlatformModelBinding:
    """Feature-governance-gated write of the platform-wide `chat` binding.

    `binding` arrives already validated by `ModelBinding` (provider
    restricted to `fred_core.model.models.ModelProvider`, settings
    type-checked and range-checked by `ModelBindingSettings`) at
    request-parsing time, before this function even runs. The store persists
    that same validated object — see `PlatformModelBindingStore.set`.
    """

    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    store = deps.get_platform_model_binding_store()
    stored = await store.set(binding=binding, updated_by=user.uid)
    return _to_platform_model_binding(stored)


async def delete_platform_model_binding(
    *,
    user: KeycloakUser,
    deps: ProductServiceDependencies,
) -> PlatformModelBinding:
    """Feature-governance-gated unset of the platform-wide `chat` binding.

    Returns the now-unset state (`binding=None`) rather than nothing, so the
    caller can render the row without a second read — same result shape as
    a successful `set`, regardless of whether a row actually existed to
    delete.
    """

    await require_manage_capabilities(deps.team_dependencies.rebac, user)
    store = deps.get_platform_model_binding_store()
    await store.delete()
    return PlatformModelBinding(binding=None)


async def resolve_platform_chat_model_binding(
    deps: ProductServiceDependencies,
    *,
    session: AsyncSession | None = None,
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
    stored = await store.get(session=session)
    if stored is None:
        return None
    return stored.binding
