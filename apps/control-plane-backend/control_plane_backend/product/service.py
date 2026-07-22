from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping, Sequence
from uuid import uuid4

import httpx
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    RebacEngine,
)
from fred_core.common import TeamId, personal_team_id
from fred_core.common.team_id import is_personal_team_id
from fred_core.kpi.kpi_writer import to_kpi_actor
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import RebacReference, Relation, RelationType
from fred_core.tasks import ErasureReason
from fred_sdk.contracts.capability import (
    CapabilityCatalogEntry,
    ChatControlDescriptor,
    ChatControlItem,
    ChatControlsRequest,
    ChatControlsRequestItem,
    ChatControlsResponse,
    StoredCapabilityConfig,
)
from fred_sdk.contracts.models import TeamScopePolicy
from fred_sdk.contracts.prompt_utils import validate_prompt_template
from pydantic import ValidationError

from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.agent_instances.suspension import (
    SliceInvalid,
    SuspensionReason,
    clear_suspension,
    reconcile_instance_config_health,
    reconcile_instance_suspension,
)
from control_plane_backend.capabilities.authz import (
    can_use_capability,
    filter_entries_by_usable,
    usable_capability_ids,
)
from control_plane_backend.config.models import (
    ManagedAgentFieldSpec,
    ManagedAgentTuning,
)
from control_plane_backend.product.default_prompts import (
    DEFAULT_PROMPTS,
    DefaultPromptSpec,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.prompt_category import PromptCategory
from control_plane_backend.product.schemas import (
    AgentTemplateSummary,
    ContextPromptSummary,
    CreateAgentInstanceRequest,
    CreatePromptRequest,
    CreateSessionAttachmentRequest,
    CreateSessionRequest,
    ExecutionPreparation,
    FrontendBootstrap,
    FrontendConfig,
    FrontendUserAuthConfig,
    ManagedAgentInstanceSummary,
    ManagedAgentRuntimeBinding,
    PermissionSummary,
    PromptDetail,
    PromptPromoteRequest,
    PromptScoreUpdateRequest,
    PromptSummary,
    RuntimeAgentExecutionPreparation,
    SessionAttachmentSummary,
    SessionListItem,
    UpdateAgentInstanceRequest,
    UpdatePromptRequest,
    UpdateSessionRequest,
)
from control_plane_backend.prompts.store import (
    PromptAlreadyExistsError,
    PromptRecord,
)
from control_plane_backend.scheduler.policies.policy_models import (
    duration_to_seconds,
)
from control_plane_backend.scheduler.policies.retention_resolver import (
    resolve_team_retention_view,
)
from control_plane_backend.sessions.attachment_store import SessionAttachmentRecord
from control_plane_backend.sessions.erasure_tasks import (
    find_active_erasure_task_id,
    schedule_erasure_task,
)
from control_plane_backend.sessions.store import (
    SessionMetadataAlreadyExistsError,
    SessionMetadataRecord,
)
from control_plane_backend.teams.service import (
    get_team_by_id as get_team_by_id_from_service,
)
from control_plane_backend.teams.service import list_teams as list_teams_from_service
from control_plane_backend.users.schemas import UserSummary

logger = logging.getLogger(__name__)

_VALID_DEFAULT_CATEGORIES: frozenset[str] = frozenset(
    spec.category for spec in DEFAULT_PROMPTS
)
_DEFAULT_PROMPT_BY_CATEGORY = {spec.category: spec for spec in DEFAULT_PROMPTS}

# Chat-controls cache (#1976, RFC §3.7): computed chat controls are NEVER
# persisted. Control-plane may cache the pod's per-capability evaluation
# cache-aside only, keyed `(capability_id, manifest.version, config_hash)`. A
# pod deploy bumps `manifest.version` → old entries miss and recompute; a config
# edit changes `config_hash` → same. In-process bounded LRU per replica: a miss
# is one pod call, never a migration. No TTL — the key already captures every
# axis that invalidates an entry, as long as prep reads the pod's current
# version at lookup (it does, via the catalog fetch below).
_CHAT_CONTROLS_CACHE_MAXSIZE = 512
_chat_controls_cache: "OrderedDict[tuple[str, str, str], list[ChatControlItem]]" = (
    OrderedDict()
)


def _capability_config_hash(envelope: Mapping[str, Any] | None) -> str:
    """Stable hash of one stored `capability_config` envelope (schema+config)."""

    return hashlib.sha256(
        json.dumps(
            dict(envelope) if envelope else {},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _chat_controls_cache_get(
    key: tuple[str, str, str],
) -> list[ChatControlItem] | None:
    cached = _chat_controls_cache.get(key)
    if cached is not None:
        _chat_controls_cache.move_to_end(key)
    return cached


def _chat_controls_cache_put(
    key: tuple[str, str, str], controls: list[ChatControlItem]
) -> None:
    _chat_controls_cache[key] = controls
    _chat_controls_cache.move_to_end(key)
    while len(_chat_controls_cache) > _CHAT_CONTROLS_CACHE_MAXSIZE:
        _chat_controls_cache.popitem(last=False)


class _RuntimeTemplatePayload:
    """Runtime `/agents/templates` payload consumed by control-plane aggregation."""

    def __init__(
        self,
        *,
        template_agent_id: str,
        title: str,
        description: str,
        description_by_lang: dict[str, str] | None = None,
        kind: str,
        default_tuning: ManagedAgentTuning | None = None,
        available_capabilities: list[CapabilityCatalogEntry] | None = None,
        default_capability_ids: list[str] | None = None,
    ) -> None:
        self.template_agent_id = template_agent_id
        self.title = title
        self.description = description
        self.description_by_lang = description_by_lang
        self.kind = kind
        self.default_tuning = default_tuning or ManagedAgentTuning(
            role=title,
            description=description,
        )
        self.available_capabilities = available_capabilities or []
        # The capability ids activated when an instance's `selected_capability_ids`
        # is None (CAPAB-01 / #1980, RFC §8.1 amendment): the plain catalog ids of
        # `definition.default_mcp_servers`, mirrored on the wire as
        # `available_mcp_servers` (`agent_app.py` `_AgentTemplateSummary`). Needed
        # so `_apply_capability_selection` can ReBAC-check the None case instead of
        # skipping it.
        self.default_capability_ids = default_capability_ids or []

    @classmethod
    def model_validate(cls, data: dict) -> "_RuntimeTemplatePayload":
        """
        Build one control-plane template payload from the runtime response shape.

        Why this function exists:
        - control-plane keeps its own typed managed-agent models, so runtime
          template payloads need one normalization step before aggregation
        - MCP servers surface as ordinary capabilities keyed by their plain
          catalog server id in `available_capabilities` (#1988), so no
          MCP-specific enrichment happens here anymore

        How to use it:
        - call with one raw `/agents/templates` item returned by a runtime pod
        - the method returns a `_RuntimeTemplatePayload` ready for
          `AgentTemplateSummary` projection

        Example:
        - `template = _RuntimeTemplatePayload.model_validate(raw_template)`
        """
        tuning = ManagedAgentTuning.model_validate(
            data.get("default_tuning")
            or {
                "role": data["title"],
                "description": data["description"],
            }
        )
        return cls(
            template_agent_id=data["template_agent_id"],
            title=data["title"],
            description=data["description"],
            description_by_lang=data.get("description_by_lang") or None,
            kind=data["kind"],
            default_tuning=tuning,
            # Pod-installed capabilities (#1974) — the same SDK wire model the
            # pod serializes, never a hand-declared parallel copy.
            available_capabilities=[
                CapabilityCatalogEntry.model_validate(entry)
                for entry in data.get("available_capabilities", [])
                if isinstance(entry, dict)
            ],
            # Ids of `definition.default_mcp_servers` (the servers activated when
            # `selected_capability_ids is None`) — MCP-derived and native ids
            # alike (RFC §2), read verbatim off the pod's own wire field rather
            # than derived from `available_mcp_servers`, which is MCP-only and
            # silently omits native capability ids.
            default_capability_ids=[
                cid
                for cid in data.get("default_capability_ids", [])
                if isinstance(cid, str) and cid
            ],
        )


async def _build_permission_summary(
    user: KeycloakUser, rebac: RebacEngine
) -> PermissionSummary:
    """Build the frontend permission projection.

    `is_platform_admin`/`is_platform_observer` are derived from OpenFGA via the
    same `RebacEngine.has_user_permission` used to gate the platform-level
    endpoints themselves, so the frontend never re-derives admin access from
    Keycloak roles independently (AUTHZ-05 review item 4). `is_platform_observer`
    checks the raw `platform_observer` relation directly (`IS_PLATFORM_OBSERVER`)
    rather than a capability, since the "any connected user" capability tier it
    used to piggyback on (`can_read_kpi`) was removed entirely in review item 8a.

    Team-scoped gating (agents, resources, MCP servers, feedback, sessions...)
    does not belong here at all — it goes through
    `TeamWithPermissions.permissions` (`_get_team_permissions_for_user`), which
    is already OpenFGA-derived per team. This function used to also carry a
    Keycloak-role-derived `items` list plus six always-empty `can_*` booleans
    computed from it; both were removed in review item 11 once Keycloak app
    roles disappeared platform-wide and left them permanently unpopulated.
    """
    is_platform_admin, is_platform_observer = await asyncio.gather(
        rebac.has_user_permission(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        ),
        rebac.has_user_permission(
            user, OrganizationPermission.IS_PLATFORM_OBSERVER, ORGANIZATION_ID
        ),
    )
    return PermissionSummary(
        is_platform_admin=is_platform_admin,
        is_platform_observer=is_platform_observer,
    )


async def build_frontend_bootstrap(
    user: KeycloakUser,
    deps: ProductServiceDependencies,
) -> FrontendBootstrap:
    """Build the frontend bootstrap from the shared selectable-team services.

    Why this function exists:
    - bootstrap should consume the same team resolution contract as `/teams` and
      `/teams/{team_id}` so `personal` is not shaped differently per endpoint

    How to use it:
    - call from the frontend bootstrap controller after authentication

    Example:
    - `payload = await build_frontend_bootstrap(user, deps)`
    """
    active_team, available_teams, permissions = await asyncio.gather(
        get_team_by_id_from_service(
            user,
            personal_team_id(user.uid),
            deps.team_dependencies,
        ),
        list_teams_from_service(user, deps.team_dependencies),
        _build_permission_summary(user, deps.team_dependencies.rebac),
    )
    return FrontendBootstrap(
        current_user=UserSummary.from_keycloak_user(user),
        active_team=active_team,
        available_teams=available_teams,
        gcu_version=deps.configuration.app.gcu_version,
        feature_flags=deps.configuration.platform.frontend.feature_flags,
        permissions=permissions,
    )


async def build_frontend_config(deps: ProductServiceDependencies) -> FrontendConfig:
    """Build the public pre-auth frontend config from `security.user`.

    Why this function exists:
    - the frontend must decide whether to initialize Keycloak before any login,
      so the auth flag is derived from the backend `security.user` config rather
      than a hand-edited `config.json`

    How to use it:
    - call from the public `/frontend/config` endpoint at Stage 0 of startup

    Example:
    - `config = await build_frontend_config(deps)`
    """
    user_security = deps.configuration.security.user
    # Mirror the enforcement predicate in `fred_core` `get_current_user`: CGU
    # gating is effectively off when user auth is disabled, regardless of any
    # configured `app.gcu_version`. Reporting the effective value here keeps the
    # frontend guard from showing an acceptance screen the backend never
    # enforces (e.g. standalone / dev deployments without Keycloak).
    gcu_version = deps.configuration.app.gcu_version if user_security.enabled else None
    root_bootstrap_completed = await deps.get_platform_bootstrap_store().is_completed()
    # Mirrors the refusal predicate `POST /bootstrap/platform-admin` enforces
    # (auth disabled or ReBAC disabled -> 503): `root_bootstrap_completed`
    # alone is not "must show BootstrapGuard" on those deployments, since the
    # durable marker stays False forever there while the endpoint can never
    # succeed. `root_bootstrap_completed` itself stays untouched and truthful.
    root_bootstrap_required = (
        user_security.enabled
        and deps.team_dependencies.rebac.enabled
        and not root_bootstrap_completed
    )
    if user_security.enabled:
        return FrontendConfig(
            user_auth=FrontendUserAuthConfig(
                enabled=True,
                realm_url=str(user_security.realm_url),
                client_id=user_security.client_id,
            ),
            gcu_version=gcu_version,
            root_bootstrap_completed=root_bootstrap_completed,
            root_bootstrap_required=root_bootstrap_required,
        )
    return FrontendConfig(
        user_auth=FrontendUserAuthConfig(enabled=False),
        gcu_version=gcu_version,
        root_bootstrap_completed=root_bootstrap_completed,
        root_bootstrap_required=root_bootstrap_required,
    )


async def _fetch_runtime_templates(
    base_url: str, include_non_public: bool = False
) -> list[_RuntimeTemplatePayload]:
    url = f"{base_url.rstrip('/')}/agents/templates"
    params = {"include_non_public": "true"} if include_non_public else None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise EnrollmentError(
            f"Agent runtime service at {base_url} returned "
            f"{exc.response.status_code} while listing templates. "
            "The runtime may be misconfigured or unavailable.",
            http_status=502,
        ) from exc
    except httpx.RequestError as exc:
        raise EnrollmentError(
            f"Agent runtime service at {base_url} is not reachable. "
            "Start the corresponding agent runtime, or check its configured "
            "base_url, then try again.",
            http_status=503,
        ) from exc
    payload = response.json()
    return [_RuntimeTemplatePayload.model_validate(item) for item in payload]


async def _refresh_tuning_contract_from_runtime(
    tuning: ManagedAgentTuning,
    *,
    source_runtime_id: str,
    source_agent_id: str,
    deps: ProductServiceDependencies,
) -> ManagedAgentTuning:
    """
    Refresh mutable tuning contracts from the current runtime template catalog.

    Why this function exists:
    - MCP config fields and tunable chat options can evolve while a managed
      agent instance already exists
    - editing an agent should validate against the current template contract
      instead of getting stuck on a stale snapshot

    How to use it:
    - call before validating update payloads that touch tuning or MCP config
    - on lookup failure, the function falls back to the stored snapshot so the
      update path stays resilient when the runtime is temporarily unavailable

    Example:
    - `base = await _refresh_tuning_contract_from_runtime(record.tuning, ...)`
    """

    source = next(
        (
            item
            for item in deps.configuration.platform.runtime_catalog_sources
            if item.enabled and item.runtime_id == source_runtime_id
        ),
        None,
    )
    if source is None:
        return tuning

    try:
        # Resolving a specific known agent by id — include internal agents so
        # non-public templates (e.g. the self-test agent) remain enrollable.
        runtime_templates = await _fetch_runtime_templates(
            source.base_url, include_non_public=True
        )
    except Exception as exc:
        logger.warning(
            "Failed to refresh runtime template contract for %s:%s: %s",
            source_runtime_id,
            source_agent_id,
            exc,
        )
        return tuning

    template = next(
        (
            item
            for item in runtime_templates
            if item.template_agent_id == source_agent_id
        ),
        None,
    )
    if template is None:
        return tuning

    return tuning.model_copy(
        update={
            "fields": template.default_tuning.fields,
        }
    )


async def _fetch_mcp_catalog(base_url: str) -> dict[str, bool] | None:
    """
    Fetch the live MCP catalog from one runtime pod.

    Returns a mapping of {server_id: enabled} for all declared servers.
    Returns None when the pod is unreachable — callers must distinguish this
    from an empty catalog (pod reachable but no servers configured).
    """
    url = f"{base_url.rstrip('/')}/agents/mcp-catalog"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        return {
            entry["id"]: bool(entry.get("enabled", True))
            for entry in payload.get("servers", [])
            if isinstance(entry, dict) and "id" in entry
        }
    except Exception as exc:
        logger.warning("Failed to fetch MCP catalog from %s: %s", base_url, exc)
        return None


async def _available_capabilities_for_source(
    base_url: str,
) -> list[CapabilityCatalogEntry]:
    """
    Fetch the pod's installed capability catalog (#1976, RFC §3.7).

    Capabilities are pod-scoped, so every template from one pod advertises the
    same set — merge across templates by id, first occurrence wins, preserving
    the pod's registration order. This is the authoritative source of each
    capability's `version`, which keys the chat-controls cache. Best-effort: an
    unreachable pod yields an empty list (no chat controls this prep).
    """

    try:
        templates = await _fetch_runtime_templates(base_url, include_non_public=True)
    except Exception as exc:
        logger.warning("Failed to fetch capability catalog from %s: %s", base_url, exc)
        return []
    merged: OrderedDict[str, CapabilityCatalogEntry] = OrderedDict()
    for template in templates:
        for entry in template.available_capabilities:
            merged.setdefault(entry.id, entry)
    return list(merged.values())


AGENT_CAPABILITY_NAMESPACE_PREFIX = "agent__"
"""Reserved id prefix for every `kind="agent"` catalog entry (GitHub #2004
item 4). `kind="tool"` entries share the SAME flat capability catalog dict
(`capabilities/catalog.py::aggregate_capability_catalog`) and the same FGA
object type — nothing stopped a tool/MCP-server id from coincidentally
matching an (unprefixed) template id, which silently overwrote one or the
other (later-registration-wins). Reserving this prefix for agent projections
and rejecting any `kind="tool"` entry that lands in it (enforced in
`aggregate_capability_catalog`) makes the collision structurally impossible
rather than merely unlikely. See `rename_agent_capability_ids_to_namespaced_form`
below for the one-time tuple-rename migration this prefix required."""


def template_capability_id(runtime_id: str, agent_id: str) -> str:
    """
    Colon-free FGA-safe capability id for one agent template (CAPAB-01, RFC
    §8.6). `template_id` (`f"{runtime_id}:{agent_id}"`, used for routing/lookup
    e.g. at line ~1012 below and in `enroll_agent_instance`) contains `:`,
    which `CAPABILITY_ID_PATTERN` forbids — OpenFGA rejects `:` in object ids,
    the same crash class `#1988` fixed for `mcp:<id>` capabilities. This is a
    parallel identifier used ONLY for ReBAC checks and the admin catalog —
    never for routing, which keeps using `template_id`.

    2026-07-20 (GitHub #2004 item 4): prefixed with `AGENT_CAPABILITY_NAMESPACE_PREFIX`
    so this id can never collide with a `kind="tool"` id (see that constant).
    """

    return f"{AGENT_CAPABILITY_NAMESPACE_PREFIX}{runtime_id}__{agent_id}"


async def _agent_capabilities_for_source(
    base_url: str, runtime_id: str
) -> list[CapabilityCatalogEntry] | None:
    """
    Project this pod's registered agent templates into `kind="agent"` catalog
    entries (CAPAB-01, RFC §8.6) — control-plane side ONLY.

    Why control-plane side, not the runtime's own capability registry:
    every template's `available_capabilities` (the tool-picker list in the
    Create-Agent modal) is built ONCE from the runtime's `capability_registry`
    and reused IDENTICALLY for every template (`agent_app.py:2777-2797`).
    Adding agent entries to that registry would make every other template's
    tool-picker show every agent as a "selectable capability" (e.g. Sentinel
    offered as a tool when creating a SQL Expert agent) — a pure accidental
    side effect, not the deliberate `context.invoke_agent()` agent-as-sub-tool
    composition (unrelated, unstarted idea). This function instead re-uses the
    template list already fetched for `list_agent_templates`, so the runtime's
    per-template tool catalog is never touched.

    `team_scope` is HARDCODED to `ADMIN_GATED` — there is no parameter or code
    path to override it. Every team's access to every agent is an explicit
    admin grant, exactly like every tool (platform policy, 2026-07-17: this
    platform never uses `team_scope: DEFAULT_ON`, see
    `docs/swift/rfc/AGENT-CAPABILITY-RFC.md` §8.3).

    Best-effort: returns `None` when the pod is unreachable, distinguishable
    from a reachable pod that simply registers no templates (`[]`) — callers
    that need to tell the two apart (the compatibility migration) can; callers
    that don't (the admin catalog aggregation) just treat `None` as empty.
    """

    try:
        # Non-public templates (e.g. the internal self-test harness agent,
        # `AgentDefinition.public=False`) must never surface as a selectable
        # `kind="agent"` capability — same policy as the tool-picker they are
        # already hidden from (AGENT-VISIBILITY-RFC). Unlike other callers of
        # `_fetch_runtime_templates`, this one intentionally does NOT pass
        # `include_non_public=True`.
        templates = await _fetch_runtime_templates(base_url)
    except Exception as exc:
        logger.warning(
            "[capability-catalog] failed to fetch agent templates from %s: %s",
            base_url,
            exc,
        )
        return None
    return [
        CapabilityCatalogEntry(
            id=template_capability_id(runtime_id, template.template_agent_id),
            version="1",
            name=template.title,
            description=template.description,
            icon="smart_toy",
            kind="agent",
            team_scope=TeamScopePolicy.ADMIN_GATED,
            default_capability_ids=tuple(template.default_capability_ids),
        )
        for template in templates
    ]


async def _fetch_chat_controls(
    base_url: str,
    request: ChatControlsRequest,
    authorization: str | None = None,
) -> ChatControlsResponse | None:
    """
    Ask one pod to evaluate a batch of capabilities' chat controls (#1976).

    POST `/agents/capabilities/chat-controls` — forwards the acting user's
    bearer: the pod route requires authentication ("reuses the same bearer
    the pod validates for `/agents/*`"), so on auth-enabled deployments a
    bearer-less call 401s and silently kills every composer control.
    Returns None when the pod is unreachable: the missed capabilities'
    controls are then simply ABSENT from this prep (logged, best-effort — the
    same silent-degrade contract as the catalog fetch), never served from a
    stale entry, since a cache MISS by construction has no entry to fall back
    to.
    """

    if not request.items:
        return ChatControlsResponse(results=[])
    url = f"{base_url.rstrip('/')}/agents/capabilities/chat-controls"
    headers = {"Authorization": authorization} if authorization else None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url, json=request.model_dump(mode="json"), headers=headers
            )
        response.raise_for_status()
        return ChatControlsResponse.model_validate(response.json())
    except Exception as exc:
        logger.warning("Failed to fetch chat controls from %s: %s", base_url, exc)
        return None


async def _resolve_chat_controls(
    tuning: ManagedAgentTuning,
    available_capabilities: Sequence[CapabilityCatalogEntry],
    base_url: str,
    authorization: str | None = None,
) -> list[ChatControlDescriptor]:
    """
    Resolve one instance's chat controls at session prep, cache-aside (#1976).

    For each selected capability the pod advertises (in catalog = registration
    order), form the cache key `(capability_id, catalog version, config_hash)`;
    serve hits from the in-process LRU and batch-evaluate only the misses on the
    pod. Per-capability pod errors (RFC §3.9) skip that capability with a
    warning. The result is flattened in catalog order — the composer host then
    groups by `capability_id` and orders by plugin-registration order (RFC §9).
    Nothing computed here is ever persisted.
    """

    versions = {entry.id: entry.version for entry in available_capabilities}
    catalog_order = [entry.id for entry in available_capabilities]
    selected = set(tuning.selected_capability_ids or [])
    ordered_ids = [cid for cid in catalog_order if cid in selected]

    per_capability: dict[str, list[ChatControlItem]] = {}
    keys_by_id: dict[str, tuple[str, str, str]] = {}
    misses: list[ChatControlsRequestItem] = []
    for cap_id in ordered_ids:
        version = versions[cap_id]
        envelope = tuning.capability_config.get(cap_id)
        key = (cap_id, version, _capability_config_hash(envelope))
        cached = _chat_controls_cache_get(key)
        if cached is not None:
            # Copy cached items so a downstream mutation of a returned
            # descriptor can never poison the shared cache entry.
            per_capability[cap_id] = [item.model_copy(deep=True) for item in cached]
            continue
        try:
            config_envelope = (
                StoredCapabilityConfig.model_validate(envelope)
                if isinstance(envelope, Mapping)
                else None
            )
        except ValidationError as exc:
            # A malformed stored envelope (RFC §3.9 `capability_config_invalid`)
            # skips ONLY this capability's chat controls — it never fails the
            # whole prep, matching the pod-side per-capability error contract.
            logger.warning(
                "Capability %s has an unreadable stored config envelope; "
                "skipping its chat controls: %s",
                cap_id,
                exc,
            )
            continue
        keys_by_id[cap_id] = key
        misses.append(
            ChatControlsRequestItem(
                capability_id=cap_id,
                config_envelope=config_envelope,
            )
        )

    if misses:
        response = await _fetch_chat_controls(
            base_url, ChatControlsRequest(items=misses), authorization=authorization
        )
        if response is not None:
            for result in response.results:
                if result.error:
                    logger.warning(
                        "Capability %s could not compute chat controls: %s",
                        result.capability_id,
                        result.error,
                    )
                    continue
                per_capability[result.capability_id] = result.controls
                key = keys_by_id.get(result.capability_id)
                # Only cache when the pod's installed version matches the catalog
                # version the key was formed from (defends against a mid-deploy
                # version skew between the two pod reads).
                if key is not None and key[1] == result.manifest_version:
                    _chat_controls_cache_put(key, result.controls)

    descriptors: list[ChatControlDescriptor] = []
    for cap_id in ordered_ids:
        for item in per_capability.get(cap_id, []):
            descriptors.append(ChatControlDescriptor.from_item(cap_id, item))
    return descriptors


def _validate_tuning_field_values(
    *,
    field_specs: Sequence[ManagedAgentFieldSpec],
    submitted_values: dict[str, Any],
    context_label: str,
    reject_unknown_keys: bool = False,
) -> dict[str, Any]:
    """
    Filter and validate submitted tuning values against one frozen field-spec list.

    Why this function exists:
    - managed-agent writes already constrain values to declared field keys, but
      they also need one shared validator so prompt/settings/chat-option values
      respect the authored field contract before control-plane persists them

    How to use it:
    - pass the frozen `ManagedAgentFieldSpec` list from the template or stored
      instance together with the submitted values dict
    - unknown keys are ignored by default to preserve current write
      compatibility; pass `reject_unknown_keys=True` for dedicated typed
      contracts
    - invalid values raise `EnrollmentError(http_status=422)`

    Example:
    - `values = _validate_tuning_field_values(field_specs=tuning.fields, submitted_values={"settings.verbose": True}, context_label="agent enrollment")`
    """
    specs_by_key: dict[str, ManagedAgentFieldSpec] = {
        field.key: field for field in field_specs
    }
    validated: dict[str, Any] = {}
    scalar_string_types = {
        "string",
        "text",
        "text-multiline",
        "prompt",
        "secret",
        "url",
    }

    def _fail(field_key: str, reason: str) -> None:
        raise EnrollmentError(
            f"Invalid value for tuning field {field_key!r} during {context_label}: {reason}.",
            http_status=422,
        )

    def _is_numeric(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _validate_array_item(
        *, field_key: str, item_type: str | None, value: object
    ) -> None:
        if item_type is None:
            if isinstance(value, (str, int, float, bool)):
                return
            _fail(field_key, "array items must be scalar values")
        if item_type in scalar_string_types or item_type == "select":
            if not isinstance(value, str):
                _fail(field_key, f"array items for type {item_type!r} must be strings")
            return
        if item_type == "boolean":
            if not isinstance(value, bool):
                _fail(field_key, "array items for type 'boolean' must be booleans")
            return
        if item_type == "integer":
            if not (isinstance(value, int) and not isinstance(value, bool)):
                _fail(field_key, "array items for type 'integer' must be integers")
            return
        if item_type == "number":
            if not _is_numeric(value):
                _fail(field_key, "array items for type 'number' must be numeric")
            return
        _fail(field_key, f"unsupported array item_type {item_type!r}")

    for key, value in submitted_values.items():
        field = specs_by_key.get(key)
        if field is None:
            if reject_unknown_keys:
                _fail(key, "unknown key")
            continue
        if value is None:
            continue
        numeric_value: float | None = None

        if field.type in scalar_string_types:
            if not isinstance(value, str):
                _fail(key, f"expected a string for type {field.type!r}")
            if field.pattern is not None and re.fullmatch(field.pattern, value) is None:
                _fail(key, f"value does not match pattern {field.pattern!r}")
            if field.type == "prompt":
                prompt_errors = validate_prompt_template(value)
                if prompt_errors:
                    details = "; ".join(
                        f"'{e.pattern}': {e.reason}" for e in prompt_errors
                    )
                    _fail(key, f"invalid template syntax — {details}")
        elif field.type == "select":
            if not isinstance(value, str):
                _fail(key, "expected a string for type 'select'")
        elif field.type == "boolean":
            if not isinstance(value, bool):
                _fail(key, "expected a boolean")
        elif field.type == "integer":
            if not (isinstance(value, int) and not isinstance(value, bool)):
                _fail(key, "expected an integer")
            numeric_value = float(value)
        elif field.type == "number":
            if not _is_numeric(value):
                _fail(key, "expected a number")
            numeric_value = float(value)
        elif field.type == "array":
            if not isinstance(value, list):
                _fail(key, "expected an array")
            for item in value:
                _validate_array_item(
                    field_key=key, item_type=field.item_type, value=item
                )
        elif field.type == "object":
            if not isinstance(value, dict):
                _fail(key, "expected an object")
            if not all(
                isinstance(obj_key, str)
                and isinstance(obj_value, (str, int, float, bool))
                for obj_key, obj_value in value.items()
            ):
                _fail(key, "object keys must be strings and values must be scalars")
        else:
            _fail(key, f"unsupported field type {field.type!r}")

        if field.enum is not None and value not in field.enum:
            _fail(key, f"value must be one of {field.enum!r}")
        if numeric_value is not None:
            if field.min is not None and numeric_value < field.min:
                _fail(key, f"value must be >= {field.min}")
            if field.max is not None and numeric_value > field.max:
                _fail(key, f"value must be <= {field.max}")

        validated[key] = value
    return validated


def _validate_capability_ids(
    *,
    submitted_ids: list[str],
    available_ids: frozenset[str],
    context_label: str,
) -> list[str]:
    """
    Validate submitted capability IDs against the pod-advertised catalog
    (#1974, RFC AGENT-CAPABILITY §3.8 save-time availability check).

    Unknown IDs raise EnrollmentError(422); known IDs are returned as-is.
    An instance may never reference a capability its pod does not advertise.
    """
    unknown = [cid for cid in submitted_ids if cid not in available_ids]
    if unknown:
        raise EnrollmentError(
            f"Unknown capability ID(s) in {context_label}: {unknown!r}. "
            "Only capabilities advertised by the template's source pod are "
            "allowed.",
            http_status=422,
        )
    return submitted_ids


@dataclass(frozen=True)
class CapabilityAssetFile:
    """
    One uploaded capability asset relayed to the pod at agent save
    (#1903, RFC AGENT-CAPABILITY §3.4).

    Control-plane never opens the bytes: it is a pure multipart relay between
    the browser and the pod's `validate-config` endpoint, which enforces the
    declared `AssetSlot` (cardinality, extension) before capability code runs.
    """

    slot_key: str
    filename: str
    content: bytes
    content_type: str | None = None


async def _validate_capability_config_via_pod(
    *,
    base_url: str,
    capability_id: str,
    config_values: dict[str, Any],
    team_id: TeamId,
    agent_instance_id: str | None,
    authorization: str | None,
    asset_files: Sequence[CapabilityAssetFile] = (),
) -> dict[str, Any]:
    """
    Round-trip one capability's config to its pod for validation (#1974,
    RFC AGENT-CAPABILITY §3.7–§3.8).

    Why this function exists:
    - capability code lives in the pod (RFC §7); control-plane cannot hold the
      typed StoredConfigModels and does not need to — the pod's
      `validate_config` is the schema authority and what it returns
      (the {"schema_version", "config"} envelope) is persisted VERBATIM
    - pod-side 422s (asset-slot violations, content validation) propagate to
      the caller as EnrollmentError(422) with the pod's wording
    - `asset_files` are the save's uploaded asset binaries for THIS capability
      (#1903): forwarded as multipart file fields keyed by slot key, exactly
      the shape the pod endpoint reads into `validate_config`'s uploads
    """
    url = f"{base_url.rstrip('/')}/agents/capabilities/{capability_id}/validate-config"
    data: dict[str, str] = {
        "config": json.dumps(config_values),
        "team_id": str(team_id),
    }
    if agent_instance_id:
        data["agent_instance_id"] = agent_instance_id
    files = [
        (
            upload.slot_key,
            (
                upload.filename,
                upload.content,
                upload.content_type or "application/octet-stream",
            ),
        )
        for upload in asset_files
    ]
    headers = {"Authorization": authorization} if authorization else None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url, data=data, files=files or None, headers=headers
            )
    except httpx.RequestError as exc:
        raise EnrollmentError(
            f"Agent runtime service at {base_url} is not reachable to "
            f"validate capability '{capability_id}' configuration. Start the "
            "corresponding agent runtime, then try again.",
            http_status=503,
        ) from exc
    if response.status_code in (400, 404, 422):
        try:
            detail = response.json().get("detail") or response.text
        except ValueError:
            detail = response.text
        raise EnrollmentError(str(detail), http_status=422)
    if response.status_code >= 400:
        raise EnrollmentError(
            f"Agent runtime service at {base_url} returned "
            f"{response.status_code} while validating capability "
            f"'{capability_id}' configuration.",
            http_status=502,
        )
    envelope = response.json()
    if (
        not isinstance(envelope, dict)
        or "schema_version" not in envelope
        or "config" not in envelope
    ):
        raise EnrollmentError(
            f"Agent runtime service at {base_url} returned a malformed "
            f"stored-config envelope for capability '{capability_id}'.",
            http_status=502,
        )
    return envelope


async def _apply_capability_selection(
    tuning: ManagedAgentTuning,
    *,
    selected_ids: list[str] | None,
    submitted_values: dict[str, dict[str, Any]] | None,
    reset_values: bool,
    available: Sequence[CapabilityCatalogEntry],
    default_capability_ids: Sequence[str],
    base_url: str,
    team_id: TeamId,
    agent_instance_id: str | None,
    authorization: str | None,
    context_label: str,
    deps: ProductServiceDependencies | None = None,
    asset_uploads: Mapping[str, Sequence[CapabilityAssetFile]] | None = None,
) -> ManagedAgentTuning:
    """
    Resolve one save's capability selection into pod-validated tuning slices
    (#1974, RFC AGENT-CAPABILITY §3.8).

    Semantics:
    - `selected_ids`: None = the template's default MCP-server selection
      (`default_capability_ids`, RFC §8.1 amendment), narrowed to the subset
      the team `can_use` — silently, no 403, since this is an implicit
      default rather than a deliberate team request; [] = none; else exact
      set, validated against the pod-advertised catalog (unknown → 422)
    - the resolved effective selection is ALWAYS persisted as an explicit
      list — `selected_capability_ids` is never left `None` after this
      function runs. This closes the gap where a `None` row skipped every
      ReBAC check (both here and in the capability-revocation sweeps, which
      scan `selected_capability_ids` and silently ignored `None` rows) and
      lets a team obtain an admin-gated capability for free by submitting no
      selection. See `docs/swift/rfc/AGENT-CAPABILITY-RFC.md` §8.1.
    - every ACTIVE capability's effective config is round-tripped through the
      pod: the submitted values when provided, else the previously stored
      config (`reset_values=True` forces defaults), else {}; the returned
      envelope is persisted verbatim
    - values for unselected capabilities are ignored (same policy as the MCP
      config path)
    - when `deps` is supplied, every EXPLICITLY selected capability is gated
      on ReBAC `can_use` checked with the TARGET TEAM as subject (CAPAB-01 /
      #1980, RFC §8.1): a team may not save an agent using an admin-gated
      capability it is not enabled for (→ 403). The team subject — not the
      acting user — is what keeps a capability enabled for one of the user's
      other teams from being saved here.
    """
    if selected_ids is not None:
        _validate_capability_ids(
            submitted_ids=selected_ids,
            available_ids=frozenset(entry.id for entry in available),
            context_label=context_label,
        )
        if deps is not None:
            rebac = deps.team_dependencies.rebac
            denied = [
                cap_id
                for cap_id in selected_ids
                if not await can_use_capability(rebac, team_id, cap_id)
            ]
            if denied:
                raise EnrollmentError(
                    f"Not authorized to use capability {denied!r} during "
                    f"{context_label}: the team is not enabled for it "
                    "(CAPAB-01 / RFC §8.1).",
                    http_status=403,
                )
        effective_ids = list(selected_ids)
    else:
        # Template-default path: narrow to what the pod actually advertises
        # for this template, then to what the team is currently authorized to
        # use. No 403 — an implicit default silently degrades to "whatever
        # this team already has" rather than blocking every fresh team's
        # first save.
        available_ids = frozenset(entry.id for entry in available)
        candidate_ids = [
            cap_id for cap_id in default_capability_ids if cap_id in available_ids
        ]
        if deps is not None and candidate_ids:
            usable_ids = await usable_capability_ids(
                deps.team_dependencies.rebac, team_id
            )
            effective_ids = (
                candidate_ids
                if usable_ids is None
                else [cap_id for cap_id in candidate_ids if cap_id in usable_ids]
            )
        else:
            effective_ids = candidate_ids
        # 2026-07-19 fix B (GitHub #2004 item 5, depends_on fast-follow
        # defense-in-depth): the template declared defaults, but every one of
        # them got filtered out by the team's ReBAC grants — persisting `[]`
        # here would silently create/save a working-looking instance with
        # zero tools. This is the residual case Fix A (the enable-time gate
        # in `capabilities/enablement.py`) cannot catch: a dependency
        # capability disabled for this team AFTER the agent capability was
        # already granted. Reject instead of degrading silently.
        if candidate_ids and not effective_ids:
            raise EnrollmentError(
                f"Cannot complete {context_label}: none of this template's "
                f"default capabilities ({sorted(candidate_ids)!r}) are usable "
                "by this team. Ask an admin to enable at least one of them "
                "for this team, or select capabilities explicitly.",
                http_status=422,
            )

    async def _build_envelope(cap_id: str) -> tuple[str, dict[str, Any]]:
        if submitted_values is not None and cap_id in submitted_values:
            values = submitted_values[cap_id]
        elif reset_values:
            values = {}
        else:
            stored = tuning.capability_config.get(cap_id)
            values = (
                dict(stored.get("config") or {}) if isinstance(stored, dict) else {}
            )
        envelope = await _validate_capability_config_via_pod(
            base_url=base_url,
            capability_id=cap_id,
            config_values=values,
            team_id=team_id,
            agent_instance_id=agent_instance_id,
            authorization=authorization,
            asset_files=(asset_uploads or {}).get(cap_id, ()),
        )
        return cap_id, envelope

    envelope_pairs = await asyncio.gather(
        *(_build_envelope(cap_id) for cap_id in effective_ids)
    )
    envelopes: dict[str, dict[str, Any]] = dict(envelope_pairs)
    return tuning.model_copy(
        update={
            "selected_capability_ids": effective_ids,
            "capability_config": envelopes,
        }
    )


async def list_agent_templates(
    team_id: TeamId,
    deps: ProductServiceDependencies,
    include_non_public: bool = False,
) -> list[AgentTemplateSummary]:
    """
    Aggregate template summaries from all enabled configured runtime pods.

    Why this function exists:
    - template discovery is a control-plane product concern that must merge the
      live catalogs exposed by configured runtime pods

    How to use it:
    - call from the team template-listing route for one team context
    - pass request-scoped product dependencies when available
    - each template's advertised `available_capabilities` is filtered to the
      ones the TEAM CONTEXT `can_use` (CAPAB-01 / #1980, RFC §8.1): admin-gated
      capabilities this team is not enabled for are hidden — including ones
      enabled for OTHER teams the browsing user belongs to. ReBAC disabled
      leaves the list unfiltered.
    - the TEMPLATE ITSELF is also gated on `can_use(team, template_capability_id)`
      (CAPAB-01, RFC §8.6): a team not granted a template does not see it at
      all, same tri-state (enabled/disabled/inherited-on) as any other
      capability — reuses the SAME `usable_ids` batch call as the nested
      filter above, no second `ListObjects`.

    Example:
    - `templates = await list_agent_templates(team_id, deps)`
    """
    # One ListObjects per request drives the whole catalog filter (RFC §8.1),
    # checked with the team as subject — the route already verified the user
    # belongs to `team_id`.
    usable_ids = await usable_capability_ids(deps.team_dependencies.rebac, team_id)

    templates: list[AgentTemplateSummary] = []
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        try:
            runtime_templates = await _fetch_runtime_templates(
                source.base_url, include_non_public=include_non_public
            )
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(
                "Failed to fetch runtime templates from %s for team %s: %s",
                source.base_url,
                team_id,
                exc,
            )
            continue

        for template in runtime_templates:
            template_cap_id = template_capability_id(
                source.runtime_id, template.template_agent_id
            )
            if usable_ids is not None and template_cap_id not in usable_ids:
                continue
            templates.append(
                AgentTemplateSummary(
                    template_id=f"{source.runtime_id}:{template.template_agent_id}",
                    source_runtime_id=source.runtime_id,
                    source_agent_id=template.template_agent_id,
                    display_name=template.title,
                    description=template.description,
                    description_by_lang=template.description_by_lang,
                    category=template.kind,
                    capabilities=[template.kind],
                    default_tuning_fields=template.default_tuning.fields,
                    available_capabilities=filter_entries_by_usable(
                        template.available_capabilities, usable_ids
                    ),
                )
            )
    return templates


async def list_managed_agent_instances(
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> list[ManagedAgentInstanceSummary]:
    """
    Return the enrolled managed agent instances for one team, with drift detection.

    Why this function exists:
    - the product surface must expose managed agent instances by stable
      `agent_instance_id`, separate from live runtime catalog discovery
    - drift detection surfaces MCP server selection mismatches to the admin
      before they cause silent execution failures

    How to use it:
    - call from the team agent-instances route
    - pass request-scoped product dependencies when available

    Example:
    - `instances = await list_managed_agent_instances(team_id, deps)`
    """
    store = deps.get_agent_instance_store()
    records = await store.list_by_team(team_id)

    # Build a catalog-per-source map for drift detection; failures → "unavailable".
    catalog_by_source: dict[str, dict[str, bool] | None] = {}
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        catalog_by_source[source.runtime_id] = await _fetch_mcp_catalog(source.base_url)

    summaries: list[ManagedAgentInstanceSummary] = []
    for record in records:
        catalog = catalog_by_source.get(record.source_runtime_id)
        if catalog is None:
            summaries.append(_record_to_summary(record, runtime_status="unavailable"))
            continue

        warnings: list[str] = []
        # An MCP-backed capability's id is the plain catalog server id now
        # (#1988). Drift for those is checked against the pod's MCP catalog map
        # ({server_id -> enabled}, disabled servers included). A selected id that
        # IS a known-but-DISABLED catalog server is warning-only (the live tool
        # provider skips it at assembly). A server REMOVED from the catalog is
        # indistinguishable from a package capability id here, so its "gone"
        # warning is dropped — removal is now covered by availability suspension.
        for cid in record.tuning.selected_capability_ids or []:
            if cid in catalog and not catalog[cid]:
                warnings.append(f"MCP server '{cid}' is disabled in the pod catalog.")
        summaries.append(_record_to_summary(record, catalog_warnings=warnings))

    return summaries


@dataclass
class ReconciliationSweepSummary:
    """Outcome of one capability reconciliation sweep (#1975, RFC §3.9)."""

    checked: int = 0
    newly_suspended: int = 0
    cleared: int = 0
    skipped_unreachable: int = 0
    suspended_reasons: dict[str, int] = field(default_factory=dict)


async def _available_capability_ids_by_source(
    deps: ProductServiceDependencies,
) -> dict[str, frozenset[str] | None]:
    """
    Map each enabled runtime source to the set of capability ids its pod
    currently advertises (union across the pod's templates), or None when the
    pod is unreachable so the sweep can skip its instances rather than suspend
    them on a transient outage (#1975, RFC §3.9).
    """

    available: dict[str, frozenset[str] | None] = {}
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        try:
            templates = await _fetch_runtime_templates(
                source.base_url, include_non_public=True
            )
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(
                "[capability-suspension] sweep could not fetch templates from %s: %s",
                source.base_url,
                exc,
            )
            available[source.runtime_id] = None
            continue
        ids: set[str] = set()
        for template in templates:
            ids.update(entry.id for entry in template.available_capabilities)
        available[source.runtime_id] = frozenset(ids)
    return available


async def _mcp_catalog_sets_by_source(
    deps: ProductServiceDependencies,
) -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    """
    Map each enabled runtime source to `(disabled_ids, all_ids)` from its pod
    MCP catalog (#1988).

    - `disabled_ids` — servers declared but DISABLED in the pod catalog. The
      sweep tolerates these (they are never an availability suspension because
      the live tool provider skips a disabled server at assembly).
    - `all_ids` — every declared server id (enabled or not). The sweep skips
      pod config-revalidation for these MCP-backed slices.

    An unreachable pod (None catalog) yields two empty sets: with no catalog
    signal the sweep tolerates nothing extra (availability already skips an
    unreachable source entirely, so this only matters for config health, where
    "skip nothing" is the safe default).
    """

    sets: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        catalog = await _fetch_mcp_catalog(source.base_url)
        if catalog is None:
            sets[source.runtime_id] = (frozenset(), frozenset())
            continue
        disabled = frozenset(sid for sid, enabled in catalog.items() if not enabled)
        all_ids = frozenset(catalog)
        sets[source.runtime_id] = (disabled, all_ids)
    return sets


async def run_capability_reconciliation_sweep(
    deps: ProductServiceDependencies,
    *,
    dry_run: bool = False,
) -> ReconciliationSweepSummary:
    """
    Reconcile every managed instance's capabilities against the live pod
    manifests, suspending or clearing as needed (#1975, RFC §3.9).

    This is the PROACTIVE detection mechanism: run it whenever the aggregated
    manifests change (pod deploy/registration) so agents leave the catalog
    before anyone hits an assembly error. The control-plane lifecycle Temporal
    queue is the intended host — an activity wraps this call; #1980's ReBAC
    revocation path reuses the finer-grained `reconcile_instance_suspension`
    entry point directly (see `agent_instances/suspension.py`).

    For each instance:
    1. availability — a selected non-MCP capability absent from the pod's
       advertised set → suspend `capability_unavailable` (and clearing when it
       returns), via `reconcile_instance_suspension`.
    2. config health — an active stored slice that no longer validates through
       the pod (incl. a failing `upgrade_config`) → suspend
       `capability_config_invalid`, via `reconcile_instance_config_health`.

    `dry_run=True` computes the outcome without writing (reporting only).
    """

    store = deps.get_agent_instance_store()
    kpi_writer = None if dry_run else deps.get_kpi_writer()
    available_by_source = await _available_capability_ids_by_source(deps)
    base_url_by_source = {
        source.runtime_id: source.base_url
        for source in deps.configuration.platform.runtime_catalog_sources
        if source.enabled
    }
    # Per-source pod MCP catalog: an MCP-backed capability's id IS its plain
    # catalog server id now (#1988). `tolerated` = servers present-but-DISABLED
    # in the pod catalog — never an availability suspension (the live tool
    # provider skips them at assembly); a REMOVED server suspends like any
    # vanished capability. `all_mcp` = every declared server id, used to skip
    # pod config-revalidation of MCP-backed slices (their config lives in the
    # permissive pod bag, not a pod `validate-config` verdict).
    mcp_catalog_by_source = await _mcp_catalog_sets_by_source(deps)

    summary = ReconciliationSweepSummary()
    for record in await store.list_all():
        available = available_by_source.get(record.source_runtime_id)
        if available is None:
            summary.skipped_unreachable += 1
            continue
        summary.checked += 1
        was_suspended = record.suspension_reason is not None
        tolerated_mcp, all_mcp = mcp_catalog_by_source.get(
            record.source_runtime_id, (frozenset(), frozenset())
        )

        if dry_run:
            # Report-only: compute the availability verdict without writing.
            # A disabled catalog MCP server is tolerated, never "missing" (#1988).
            missing = [
                cap_id
                for cap_id in (record.tuning.selected_capability_ids or [])
                if cap_id not in available and cap_id not in tolerated_mcp
            ]
            if missing:
                summary.newly_suspended += 0 if was_suspended else 1
                key = SuspensionReason.CAPABILITY_UNAVAILABLE.value
                summary.suspended_reasons[key] = (
                    summary.suspended_reasons.get(key, 0) + 1
                )
            continue

        reason = await reconcile_instance_suspension(
            instance=record,
            store=store,
            available_capability_ids=available,
            tolerated_ids=tolerated_mcp,
            kpi_writer=kpi_writer,
        )
        if reason is None:
            base_url = base_url_by_source.get(record.source_runtime_id)
            if base_url is not None:
                # Availability reconcile may have just cleared a suspension;
                # re-read so config health sees the current state.
                fresh = await store.get(record.agent_instance_id) or record
                reason = await reconcile_instance_config_health(
                    instance=fresh,
                    store=store,
                    validate_slice=_make_slice_validator(
                        base_url=base_url, team_id=record.team_id
                    ),
                    skip_ids=all_mcp,
                    kpi_writer=kpi_writer,
                )

        if reason is not None and not was_suspended:
            summary.newly_suspended += 1
            summary.suspended_reasons[reason.value] = (
                summary.suspended_reasons.get(reason.value, 0) + 1
            )
        elif was_suspended and reason is None:
            summary.cleared += 1

    logger.info(
        "[capability-suspension] sweep done dry_run=%s checked=%d "
        "newly_suspended=%d cleared=%d skipped_unreachable=%d",
        dry_run,
        summary.checked,
        summary.newly_suspended,
        summary.cleared,
        summary.skipped_unreachable,
    )
    return summary


@dataclass
class CapabilityMaterializationSummary:
    checked: int = 0
    materialized: int = 0
    skipped_unreachable: int = 0
    skipped_unknown_template: int = 0


async def _default_capability_ids_by_source_and_template(
    deps: ProductServiceDependencies,
) -> dict[str, dict[str, list[str]] | None]:
    """
    Map each enabled runtime source to {template_agent_id: default_capability_ids}.

    A `None` value for a source signals it was unreachable, so the caller can
    skip its instances rather than wrongly materialize an empty selection.
    """

    result: dict[str, dict[str, list[str]] | None] = {}
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        try:
            templates = await _fetch_runtime_templates(
                source.base_url, include_non_public=True
            )
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(
                "[capability-materialization] sweep could not fetch templates "
                "from %s: %s",
                source.base_url,
                exc,
            )
            result[source.runtime_id] = None
            continue
        result[source.runtime_id] = {
            template.template_agent_id: template.default_capability_ids
            for template in templates
        }
    return result


async def materialize_default_capability_selections(
    deps: ProductServiceDependencies,
    *,
    dry_run: bool = False,
    team_ids: set[TeamId] | None = None,
) -> CapabilityMaterializationSummary:
    """
    One-off backfill: resolve every already-persisted instance whose
    `selected_capability_ids` is still `None` into an explicit, ReBAC-filtered
    list (CAPAB-01 / #1980, RFC §8.1 amendment).

    Why this function exists:
    - `_apply_capability_selection` now materializes `None` at every future
      save, but rows created BEFORE that fix shipped are still exploitable —
      `get_runtime_binding_for_team` and the runtime pod both still trust a
      `None` selection as "activate every template default," and the
      capability-revocation sweeps (`suspend_dependent_instances`,
      `set_capability_default_on`, `capabilities/enablement.py`) silently skip
      `None` rows. This sweep is what closes the gap for already-existing
      data, not just new writes.

    How to use it:
    - run once, deploy-time, before/alongside the code fix goes live (same
      standalone-bootstrap pattern as `main_worker.py`: load configuration,
      build the application container, then call this with the resulting
      `ProductServiceDependencies`)
    - `dry_run=True` reports what WOULD be materialized without writing
    - `team_ids`, when given, restricts the sweep to those teams' instances
      only — used by `import_export/importer.py::run_import` (#2004 item 3)
      to fix up just the rows an import just wrote, instead of re-scanning
      every instance on the platform on every restore/backup-copy
    - treat "0 remaining NULL `selected_capability_ids` rows" as the proof of
      closure, not "the sweep ran" — an unreachable pod during the sweep
      leaves its instances untouched (`skipped_unreachable`), so re-run until
      every runtime source is reachable and the count is zero
    """

    store = deps.get_agent_instance_store()
    defaults_by_source = await _default_capability_ids_by_source_and_template(deps)
    usable_ids_by_team: dict[TeamId, set[str] | None] = {}

    summary = CapabilityMaterializationSummary()
    for record in await store.list_all():
        if team_ids is not None and record.team_id not in team_ids:
            continue
        if record.tuning.selected_capability_ids is not None:
            continue
        summary.checked += 1

        templates = defaults_by_source.get(record.source_runtime_id)
        if templates is None:
            summary.skipped_unreachable += 1
            continue
        default_ids = templates.get(record.source_agent_id)
        if default_ids is None:
            summary.skipped_unknown_template += 1
            continue

        if record.team_id not in usable_ids_by_team:
            usable_ids_by_team[record.team_id] = await usable_capability_ids(
                deps.team_dependencies.rebac, record.team_id
            )
        usable_ids = usable_ids_by_team[record.team_id]
        effective_ids = (
            list(default_ids)
            if usable_ids is None
            else [cap_id for cap_id in default_ids if cap_id in usable_ids]
        )

        summary.materialized += 1
        if not dry_run:
            await store.update(
                agent_instance_id=record.agent_instance_id,
                team_id=record.team_id,
                tuning=record.tuning.model_copy(
                    update={"selected_capability_ids": effective_ids}
                ),
            )

    logger.info(
        "[capability-materialization] sweep done dry_run=%s checked=%d "
        "materialized=%d skipped_unreachable=%d skipped_unknown_template=%d",
        dry_run,
        summary.checked,
        summary.materialized,
        summary.skipped_unreachable,
        summary.skipped_unknown_template,
    )
    return summary


@dataclass
class TemplateGrantMigrationSummary:
    teams_checked: int = 0
    templates_checked: int = 0
    grants_written: int = 0
    already_granted: int = 0
    skipped_unreachable_sources: int = 0
    # 2026-07-19, GitHub #2004 item 5: a grant this sweep WOULD have written is
    # instead skipped (not raised) when the template's default tool
    # capabilities aren't usable by the team yet (the `depends_on` gate,
    # `enable_capability_for_team`) — granting anyway would just reproduce the
    # exact "agent enabled, zero working tools" bug this fast-follow closes.
    # Re-run this sweep after enabling the missing tool capability(ies).
    skipped_dependency_not_satisfied: int = 0


async def grant_existing_teams_served_templates(
    deps: ProductServiceDependencies,
    *,
    dry_run: bool = False,
    team_ids: set[TeamId] | None = None,
) -> TemplateGrantMigrationSummary:
    """
    Required compatibility migration (CAPAB-01, RFC §8.6) — a companion to
    `materialize_default_capability_selections` above, for a DIFFERENT gate:
    `kind="agent"` capabilities default `ADMIN_GATED` like everything else
    (platform policy — this deployment never uses `team_scope: DEFAULT_ON`,
    see the dated note in `AGENT-CAPABILITY-RFC.md` §8.3), so without this
    sweep every existing team loses access to every agent template the
    instant `list_agent_templates`'s `can_use` gate goes live.

    Writes an explicit `enabled` tuple (via `enable_capability_for_team` —
    NEVER `default_on`) for every (existing team x currently-served template)
    pair not already granted. Idempotent and safe to re-run: only ever adds a
    missing grant, never touches one that's already explicit (enabled OR
    disabled) — an admin who has already dialed a specific agent down for a
    specific team is not overridden by this sweep.

    2026-07-19 fix (GitHub #2004 item 2): "already explicit" is checked via
    `has_direct_relation` (a literal-tuple read) for BOTH `enabled` and
    `disabled`, never via `usable_capability_ids` (the effective, computed
    `can_use`) — the two are not the same test. `can_use` is false for a team
    with an explicit `disabled` tuple, so the previous usable-based check
    treated "explicitly disabled" identically to "never granted" and
    re-enabled it on every re-run.

    How to use it:
    - run once, at/before deploy, alongside `materialize_default_capability_selections`
      — see the CAPAB-01 plan's deploy-sequencing note: each sweep must
      complete before its corresponding `can_use` gate goes live, and both
      should be rehearsed against a copy of real data before the actual
      go-live, not attempted for the first time in production
    - `dry_run=True` reports what WOULD be granted without writing
    - `team_ids`, when given, restricts the sweep to those teams only — used
      by `import_export/importer.py::run_import` (#2004 item 3) to grant just
      the teams an import just touched, instead of re-granting the whole
      platform on every restore/backup-copy
    """

    from control_plane_backend.capabilities.enablement import (
        agent_capability_missing_dependencies,
        enable_capability_for_team,
    )

    rebac = deps.team_dependencies.rebac
    settings_store = deps.get_team_capability_settings_store()

    template_entries: dict[str, CapabilityCatalogEntry] = {}
    unreachable_sources = 0
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        entries = await _agent_capabilities_for_source(
            source.base_url, source.runtime_id
        )
        if entries is None:
            unreachable_sources += 1
            continue
        for entry in entries:
            template_entries[entry.id] = entry
    summary = TemplateGrantMigrationSummary(
        templates_checked=len(template_entries),
        skipped_unreachable_sources=unreachable_sources,
    )

    teams = await deps.team_dependencies.get_team_metadata_store().list_all()
    for team in teams:
        if team_ids is not None and team.id not in team_ids:
            continue
        summary.teams_checked += 1
        team_ref = RebacReference(type=Resource.TEAM, id=str(team.id))
        for template_id, entry in template_entries.items():
            cap_ref = RebacReference(type=Resource.CAPABILITY, id=template_id)
            has_explicit_decision = await rebac.has_direct_relation(
                team_ref, RelationType.ENABLED, cap_ref
            ) or await rebac.has_direct_relation(
                team_ref, RelationType.DISABLED, cap_ref
            )
            if has_explicit_decision:
                summary.already_granted += 1
                continue
            missing_deps = await agent_capability_missing_dependencies(
                rebac, entry, team.id
            )
            if missing_deps:
                # Granting anyway would just reproduce the "agent enabled,
                # zero working tools" bug this depends_on gate closes (#2004
                # item 5) — skip and let an operator re-run after enabling
                # the missing tool capability(ies) for this team.
                summary.skipped_dependency_not_satisfied += 1
                logger.warning(
                    "[template-grant-migration] skipped team=%s template=%s: "
                    "missing dependency capability id(s) %r",
                    team.id,
                    template_id,
                    missing_deps,
                )
                continue
            summary.grants_written += 1
            if not dry_run:
                await enable_capability_for_team(
                    rebac=rebac,
                    settings_store=settings_store,
                    catalog_entry=entry,
                    team_id=team.id,
                    settings={},
                    updated_by=None,
                )

    logger.info(
        "[template-grant-migration] sweep done dry_run=%s teams_checked=%d "
        "templates_checked=%d grants_written=%d already_granted=%d "
        "skipped_unreachable_sources=%d skipped_dependency_not_satisfied=%d",
        dry_run,
        summary.teams_checked,
        summary.templates_checked,
        summary.grants_written,
        summary.already_granted,
        summary.skipped_unreachable_sources,
        summary.skipped_dependency_not_satisfied,
    )
    return summary


_ORG_REF = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)


@dataclass
class TemplateIdNamespaceMigrationSummary:
    templates_checked: int = 0
    skipped_unreachable_sources: int = 0
    tuples_renamed: int = 0


async def rename_agent_capability_ids_to_namespaced_form(
    deps: ProductServiceDependencies,
    *,
    dry_run: bool = False,
) -> TemplateIdNamespaceMigrationSummary:
    """
    One-time compatibility migration for the `AGENT_CAPABILITY_NAMESPACE_PREFIX`
    fix (GitHub #2004 item 4, RFC §8.6 2026-07-20 dated entry).

    `template_capability_id` used to return the un-prefixed
    `f"{runtime_id}__{agent_id}"`. Any FGA tuple written before this migration
    ships (anchor, `enabled`/`disabled` per team, `default_on`,
    `personal_on`/`personal_disabled`) is keyed on that old id. Simply
    changing the id-generating function would silently orphan every one of
    those tuples — teams that already had a template enabled would
    instantly lose access the moment this code deploys.

    Renames each such tuple in place: writes the identical
    (subject, relation) pair under the new `agent__`-prefixed resource id,
    then deletes the old one. Idempotent and safe to re-run — a tuple already
    renamed (or never granted) has nothing to move under the old id and is
    silently skipped, exactly like `grant_existing_teams_served_templates`.

    How to use it: run once, before this code deploys, the same
    deploy-sequencing rule as `grant_existing_teams_served_templates` (both
    rehearsed against a copy of real data first, never attempted for the
    first time in production). `dry_run=True` reports what WOULD be renamed
    without writing.
    """

    rebac = deps.team_dependencies.rebac
    template_entries: dict[str, CapabilityCatalogEntry] = {}
    unreachable_sources = 0
    for source in deps.configuration.platform.runtime_catalog_sources:
        if not source.enabled:
            continue
        entries = await _agent_capabilities_for_source(
            source.base_url, source.runtime_id
        )
        if entries is None:
            unreachable_sources += 1
            continue
        for entry in entries:
            template_entries[entry.id] = entry
    summary = TemplateIdNamespaceMigrationSummary(
        templates_checked=len(template_entries),
        skipped_unreachable_sources=unreachable_sources,
    )

    teams = await deps.team_dependencies.get_team_metadata_store().list_all()

    for new_id in template_entries:
        old_id = new_id.removeprefix(AGENT_CAPABILITY_NAMESPACE_PREFIX)
        if old_id == new_id:
            # Defensive: template_capability_id always applies the prefix, so
            # a catalog entry without it would mean a non-agent-projection id
            # ended up in `template_entries` — never move a tuple in that case.
            continue
        old_ref = RebacReference(type=Resource.CAPABILITY, id=old_id)
        new_ref = RebacReference(type=Resource.CAPABILITY, id=new_id)

        # Org-subject tuples: anchor + the three platform-wide class markers.
        for relation in (
            RelationType.ORGANIZATION,
            RelationType.DEFAULT_ON,
            RelationType.PERSONAL_ON,
            RelationType.PERSONAL_DISABLED,
        ):
            if await rebac.has_direct_relation(_ORG_REF, relation, old_ref):
                summary.tuples_renamed += 1
                if not dry_run:
                    await rebac.add_relation(
                        Relation(subject=_ORG_REF, relation=relation, resource=new_ref)
                    )
                    await rebac.delete_relation(
                        Relation(subject=_ORG_REF, relation=relation, resource=old_ref)
                    )

        # Team-subject tuples: the per-team enable/disable grant.
        for team in teams:
            team_ref = RebacReference(type=Resource.TEAM, id=str(team.id))
            for relation in (RelationType.ENABLED, RelationType.DISABLED):
                if await rebac.has_direct_relation(team_ref, relation, old_ref):
                    summary.tuples_renamed += 1
                    if not dry_run:
                        await rebac.add_relation(
                            Relation(
                                subject=team_ref, relation=relation, resource=new_ref
                            )
                        )
                        await rebac.delete_relation(
                            Relation(
                                subject=team_ref, relation=relation, resource=old_ref
                            )
                        )

    logger.info(
        "[template-id-namespace-migration] sweep done dry_run=%s "
        "templates_checked=%d tuples_renamed=%d skipped_unreachable_sources=%d",
        dry_run,
        summary.templates_checked,
        summary.tuples_renamed,
        summary.skipped_unreachable_sources,
    )
    return summary


def _make_slice_validator(*, base_url: str, team_id: TeamId):
    """
    Build the `validate_slice` callable the config-health reconcile uses: it
    round-trips one stored slice's inner config through the pod's
    `validate-config` endpoint and raises `SliceInvalid` on a 422 (the slice no
    longer validates / `upgrade_config` failed), swallowing transport errors so
    a pod hiccup never suspends an instance (#1975, RFC §3.9).
    """

    async def _validate(capability_id: str, config: dict[str, Any]) -> None:
        try:
            await _validate_capability_config_via_pod(
                base_url=base_url,
                capability_id=capability_id,
                config_values=config,
                team_id=team_id,
                agent_instance_id=None,
                authorization=None,
            )
        except EnrollmentError as exc:
            if exc.http_status == 422:
                raise SliceInvalid(capability_id, str(exc)) from exc
            # 503/502: pod unreachable or malformed — not a config verdict.
            logger.warning(
                "[capability-suspension] slice re-validation for '%s' could "
                "not reach a verdict (%s); leaving suspension unchanged.",
                capability_id,
                exc,
            )

    return _validate


def _record_to_summary(
    record: AgentInstanceRecord,
    *,
    runtime_status: Literal["ok", "unavailable"] = "ok",
    catalog_warnings: list[str] | None = None,
) -> ManagedAgentInstanceSummary:
    """
    Build one frontend-facing summary from a DB-backed agent instance record.

    Why this function exists:
    - the product listing surface needs one canonical projection from stored
      managed-agent records to the summary contract returned to the UI

    How to use it:
    - pass one store record plus optional runtime-status/warning annotations
      computed by the caller

    Chat controls (#1976, RFC §3.7) are intentionally NOT resolved here: they
    are a session-prep projection shipped on `ExecutionPreparation`, not a
    listing-surface field. The retired `effective_chat_options` hint is gone;
    the composer fetches controls via an eager prepare-execution at chat open.

    Example:
    - `_record_to_summary(record, runtime_status="unavailable")`
    """
    return ManagedAgentInstanceSummary(
        agent_instance_id=record.agent_instance_id,
        team_id=record.team_id,
        template_id=record.template_id,
        display_name=record.display_name,
        description=record.description,
        status="enabled" if record.enabled else "disabled",
        suspension_reason=(
            SuspensionReason(record.suspension_reason)
            if record.suspension_reason is not None
            else None
        ),
        created_at=record.created_at,
        updated_at=record.updated_at,
        created_by=record.created_by,
        updated_by=record.updated_by,
        tuning_field_values=record.tuning.values,
        selected_capability_ids=(
            list(record.tuning.selected_capability_ids)
            if record.tuning.selected_capability_ids is not None
            else None
        ),
        capability_config=dict(record.tuning.capability_config),
        runtime_status=runtime_status,
        catalog_warnings=catalog_warnings or [],
    )


_TEXT_PREVIEW_MAX = 140


class ExecutionPreparationError(Exception):
    """Raised when execution preparation cannot be completed."""

    def __init__(self, message: str, *, http_status: int = 404) -> None:
        super().__init__(message)
        self.http_status = http_status


class EnrollmentError(Exception):
    """Raised when agent instance enrollment fails."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status


class PromptRequestError(Exception):
    """Raised when prompt-library CRUD cannot be completed as requested."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status


class SessionAlreadyExistsError(Exception):
    """Raised when control-plane session metadata already exists."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session {session_id!r} already exists.")
        self.session_id = session_id


class SessionAttachmentRequestError(Exception):
    """Raised when a session attachment CRUD operation cannot be completed."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status


def _to_session_attachment_summary(
    record: SessionAttachmentRecord,
) -> SessionAttachmentSummary:
    return SessionAttachmentSummary(
        attachment_id=record.attachment_id,
        name=record.name,
        mime=record.mime,
        size_bytes=record.size_bytes,
        summary_md=record.summary_md,
        document_uid=record.document_uid,
        storage_key=record.storage_key,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def _get_owned_session_record(
    *,
    deps: ProductServiceDependencies,
    team_id: TeamId,
    session_id: str,
    user_id: str,
) -> SessionMetadataRecord:
    """
    Resolve one session metadata row and enforce team + ownership checks.

    Why this function exists:
    - persisted conversation attachments must stay scoped to the same
      team/user session ownership model as the rest of the control-plane
    - centralizing the check keeps the attachment CRUD handlers aligned

    How to use it:
    - call before listing, creating, or deleting session attachments
    - the helper raises `SessionAttachmentRequestError` on not-found or
      ownership mismatches
    """

    record = await deps.get_session_metadata_store().get(session_id)
    if record is None or record.team_id != team_id:
        raise SessionAttachmentRequestError(
            f"Session {session_id!r} not found for team {team_id!r}.",
            http_status=404,
        )
    if record.user_id is not None and record.user_id != user_id:
        raise SessionAttachmentRequestError(
            f"Session {session_id!r} is not owned by user {user_id!r}.",
            http_status=404,
        )
    return record


async def _delete_knowledge_flow_attachment(
    *,
    deps: ProductServiceDependencies,
    authorization: str,
    document_uid: str | None,
    storage_key: str | None,
    session_id: str,
) -> None:
    """
    Orchestrate the Knowledge Flow cleanup path for one persisted attachment.

    Why this function exists:
    - control-plane owns session attachment metadata, but Knowledge Flow owns
      the vectors, metadata artifacts, and uploaded file bytes
    - deleting one attachment must clean both systems in one operation

    How to use it:
    - pass the caller's bearer token through `authorization`
    - the helper returns silently when there is nothing to clean up
    """

    if document_uid is None and storage_key is None:
        return

    if not authorization.strip():
        raise SessionAttachmentRequestError(
            "Missing Authorization header for attachment cleanup.",
            http_status=401,
        )

    if document_uid is None:
        return

    url = (
        f"{deps.configuration.platform.knowledge_flow_base_url.rstrip('/')}"
        f"/fast/delete/{document_uid}"
    )
    params = {"session_id": session_id}
    if storage_key is not None:
        params["storage_key"] = storage_key

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                url,
                params=params,
                headers={"Authorization": authorization},
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or str(exc)
        raise SessionAttachmentRequestError(
            f"Knowledge Flow cleanup failed for attachment document {document_uid!r}: {detail}",
            http_status=502,
        ) from exc
    except httpx.RequestError as exc:
        raise SessionAttachmentRequestError(
            f"Knowledge Flow cleanup request failed for attachment document {document_uid!r}: {exc}",
            http_status=502,
        ) from exc


async def enroll_agent_instance(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    request: CreateAgentInstanceRequest,
    deps: ProductServiceDependencies,
    authorization: str | None = None,
    asset_uploads: Mapping[str, Sequence[CapabilityAssetFile]] | None = None,
) -> ManagedAgentInstanceSummary:
    """
    Enroll one discovered template for a team, creating a DB-backed managed instance.

    Why this function exists:
    - enrollment turns one live template into a DB-backed managed instance that
      can later be prepared for team-scoped execution

    How to use it:
    - pass a validated team, the authenticated user, and the typed enrollment
      request
    - pass request-scoped product dependencies when available
    - `tuning_field_values` configures agent-authored fields only
    - `capability_ids` and `capability_config_values` configure tool activation
      (including MCP servers, which are capabilities keyed by their plain
      catalog server id — #1988) and per-tool options

    Example:
    - `item = await enroll_agent_instance(user=user, team_id=team_id, request=body, deps=deps)`
    """
    parts = request.template_id.split(":", 1)
    if len(parts) != 2:
        raise EnrollmentError(
            f"Invalid template_id {request.template_id!r}. "
            "Expected format: '{source_runtime_id}:{source_agent_id}'."
        )
    source_runtime_id, source_agent_id = parts

    source = next(
        (
            s
            for s in deps.configuration.platform.runtime_catalog_sources
            if s.runtime_id == source_runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise EnrollmentError(
            f"Runtime source {source_runtime_id!r} is not available or not enabled.",
            http_status=404,
        )

    agent_instance_id = str(uuid4())
    # Internal (non-public) templates are admin-only to enroll: resolve with the
    # caller's OpenFGA platform_admin privilege (same check as the read-side
    # `get_team_agent_templates`'s `include_non_public`, api.py) so a Keycloak
    # `admin` role alone is not sufficient and a non-admin who guesses a hidden
    # template_id simply gets "template not found" (404) below, exactly as if
    # it did not exist.
    can_see_non_public_templates = (
        await deps.team_dependencies.rebac.has_user_permission(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        )
    )
    runtime_templates = await _fetch_runtime_templates(
        source.base_url, include_non_public=can_see_non_public_templates
    )
    template = next(
        (
            item
            for item in runtime_templates
            if item.template_agent_id == source_agent_id
        ),
        None,
    )
    if template is None:
        raise EnrollmentError(
            f"Template {request.template_id!r} was not found on runtime source "
            f"{source_runtime_id!r}.",
            http_status=404,
        )
    # Defense in depth (CAPAB-01, RFC §8.6): `list_agent_templates` already
    # hides a template the team isn't granted, but never trust the frontend
    # filter alone — re-check here too, same pattern as every other ReBAC gate
    # in this codebase. 404, not 403: a team that guesses a hidden
    # `template_id` gets exactly the same response as a nonexistent one (RFC
    # §7.2/§10 anti-guessing rule, matching the non-public-template check
    # above).
    if not await can_use_capability(
        deps.team_dependencies.rebac,
        team_id,
        template_capability_id(source_runtime_id, source_agent_id),
    ):
        raise EnrollmentError(
            f"Template {request.template_id!r} was not found on runtime source "
            f"{source_runtime_id!r}.",
            http_status=404,
        )

    tuning = template.default_tuning.model_copy(
        update={
            "role": request.display_name,
            "description": request.description or request.display_name,
        }
    )
    if request.tuning_field_values:
        tuning = tuning.model_copy(
            update={
                "values": _validate_tuning_field_values(
                    field_specs=tuning.fields,
                    submitted_values=request.tuning_field_values,
                    context_label="agent enrollment",
                )
            }
        )
    # MCP activation/config flows through the capability path (#1978): an MCP
    # server is a capability keyed by its plain catalog server id (#1988),
    # validated and stored via the same pod round-trip as every other
    # capability below. This ALWAYS runs, even with no explicit
    # `capability_ids` — the default (no-selection) path is exactly what must
    # be ReBAC-checked and materialized (CAPAB-01 / #1980, RFC §8.1 amendment;
    # a `None` selection previously skipped this check entirely).
    tuning = await _apply_capability_selection(
        tuning,
        selected_ids=request.capability_ids,
        submitted_values=request.capability_config_values,
        reset_values=False,
        available=template.available_capabilities,
        default_capability_ids=template.default_capability_ids,
        base_url=source.base_url,
        team_id=team_id,
        agent_instance_id=agent_instance_id,
        authorization=authorization,
        context_label="agent enrollment",
        deps=deps,
        asset_uploads=asset_uploads,
    )
    record = AgentInstanceRecord(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        template_id=request.template_id,
        source_runtime_id=source_runtime_id,
        source_agent_id=source_agent_id,
        display_name=request.display_name,
        description=request.description,
        enabled=True,
        created_by=user.uid,
        tuning=tuning,
    )

    store = deps.get_agent_instance_store()
    created = await store.create(record)
    try:
        system_prompt = tuning.values.get("prompts.system")
        system_prompt_chars = len(str(system_prompt)) if system_prompt else 0
        deps.get_kpi_writer().count(
            "agent.created_total",
            dims={
                "team_id": str(team_id),
                "template_id": request.template_id,
                "source_runtime_id": source_runtime_id,
                "agent_instance_id": agent_instance_id,
                "system_prompt_chars": str(system_prompt_chars),
            },
            actor=to_kpi_actor(user),
        )
    except Exception:
        logger.exception("[control-plane][kpi] Failed to emit agent.created_total")
    return _record_to_summary(created)


async def update_agent_instance(
    *,
    team_id: TeamId,
    agent_instance_id: str,
    request: UpdateAgentInstanceRequest,
    deps: ProductServiceDependencies,
    user: KeycloakUser,
    authorization: str | None = None,
    asset_uploads: Mapping[str, Sequence[CapabilityAssetFile]] | None = None,
) -> ManagedAgentInstanceSummary | None:
    """
    Update display_name, description, or tuning field values for one managed instance.

    Why this function exists:
    - teams need to be able to customise display metadata and per-instance field
      values after enrollment without re-enrolling from scratch

    How to use it:
    - pass only the fields to change
    - omitted fields are left unchanged
    - `tuning_field_values=None` clears stored agent tuning values
    - `capability_ids=None` resets the instance to the template default
      capability selection; `capability_ids=[]` activates no capabilities
      (MCP servers are capabilities keyed by their plain catalog server id,
      #1988)
    - `capability_config_values=None` resets every selected capability to its
      defaults

    Policy — current template contract:
    - update validation uses the latest field specs exposed by the source
      runtime template
    - stored values and selected capabilities are preserved, but the editable
      contract follows the current template catalog

    Example:
    - `result = await update_agent_instance(team_id=team_id, agent_instance_id=id, request=req, deps=deps, user=user)`
    """
    store = deps.get_agent_instance_store()
    record = await store.get_for_team(agent_instance_id, team_id)
    if record is None:
        return None

    # 2026-07-19 fix (GitHub #2004 item 1): re-check the team's `can_use` on
    # this instance's own `kind="agent"` template capability, the same gate
    # `enroll_agent_instance` already applies at creation time. Without this,
    # a team whose template grant was revoked (or a `default_on`/personal-
    # scope withdrawal) could keep freely reconfiguring an instance that
    # `suspend_dependent_instances`/`set_capability_default_on` already
    # suspended for exactly that reason — unenroll (delete) is still always
    # allowed, only editing is blocked.
    if not await can_use_capability(
        deps.team_dependencies.rebac,
        team_id,
        template_capability_id(record.source_runtime_id, record.source_agent_id),
    ):
        raise EnrollmentError(
            "This agent's template access has been revoked for your team; it "
            "can no longer be edited (unenroll is still allowed).",
            http_status=403,
        )

    tuning_fields_set = request.model_fields_set
    new_tuning: ManagedAgentTuning | None = None
    if {
        "tuning_field_values",
        "capability_ids",
        "capability_config_values",
    } & tuning_fields_set:
        base = await _refresh_tuning_contract_from_runtime(
            record.tuning,
            source_runtime_id=record.source_runtime_id,
            source_agent_id=record.source_agent_id,
            deps=deps,
        )
        if "tuning_field_values" in tuning_fields_set:
            if request.tuning_field_values is None:
                base = base.model_copy(update={"values": {}})
            else:
                base = base.model_copy(
                    update={
                        "values": _validate_tuning_field_values(
                            field_specs=base.fields,
                            submitted_values=request.tuning_field_values,
                            context_label="agent update",
                        )
                    }
                )
        # MCP activation/config is part of the capability selection now (#1978):
        # an MCP-backed capability (keyed by its plain catalog server id, #1988)
        # is validated and stored through the same pod round-trip as every other
        # capability below.
        if {"capability_ids", "capability_config_values"} & tuning_fields_set:
            # Capability writes REQUIRE the live pod: the availability check
            # runs against what the pod advertises and every active slice is
            # re-validated through the pod round-trip (RFC §3.8). A successful
            # save is what clears a config-invalid state (RFC §3.9), so no
            # stale-snapshot fallback here.
            source = next(
                (
                    s
                    for s in deps.configuration.platform.runtime_catalog_sources
                    if s.runtime_id == record.source_runtime_id and s.enabled
                ),
                None,
            )
            if source is None:
                raise EnrollmentError(
                    f"Runtime source {record.source_runtime_id!r} is not "
                    "available or not enabled; capability settings cannot be "
                    "changed.",
                    http_status=503,
                )
            runtime_templates = await _fetch_runtime_templates(
                source.base_url, include_non_public=True
            )
            template = next(
                (
                    item
                    for item in runtime_templates
                    if item.template_agent_id == record.source_agent_id
                ),
                None,
            )
            if template is None:
                raise EnrollmentError(
                    f"Template {record.template_id!r} was not found on runtime "
                    f"source {record.source_runtime_id!r}; capability settings "
                    "cannot be changed.",
                    http_status=503,
                )
            selected = (
                request.capability_ids
                if "capability_ids" in tuning_fields_set
                else base.selected_capability_ids
            )
            base = await _apply_capability_selection(
                base,
                selected_ids=selected,
                submitted_values=(
                    request.capability_config_values
                    if "capability_config_values" in tuning_fields_set
                    else None
                ),
                reset_values=(
                    "capability_config_values" in tuning_fields_set
                    and request.capability_config_values is None
                ),
                available=template.available_capabilities,
                default_capability_ids=template.default_capability_ids,
                base_url=source.base_url,
                team_id=team_id,
                agent_instance_id=agent_instance_id,
                authorization=authorization,
                context_label="agent update",
                deps=deps,
                asset_uploads=asset_uploads,
            )
        new_tuning = base

    updated = await store.update(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        display_name=request.display_name,
        description=request.description,
        enabled=request.status == "enabled" if request.status is not None else None,
        tuning=new_tuning,
        updated_by=user.uid,
    )
    # A save that re-validated every ACTIVE capability slice through the pod
    # clears any suspension — the single clearing mechanism (#1975, RFC §3.9).
    # Reaching here means `_apply_capability_selection` accepted the selection
    # (unknown/unavailable ids already 422'd; every active slice round-tripped),
    # so the broken state the agent was suspended for is resolved. Untick +
    # re-save therefore clears both availability and config-invalid suspensions.
    if (
        updated is not None
        and updated.suspension_reason is not None
        and {"capability_ids", "capability_config_values"} & tuning_fields_set
    ):
        cleared = await clear_suspension(
            store, updated, kpi_writer=deps.get_kpi_writer()
        )
        updated = cleared if cleared is not None else updated
    if updated is not None:
        try:
            effective_tuning = new_tuning if new_tuning is not None else record.tuning
            system_prompt = effective_tuning.values.get("prompts.system")
            system_prompt_chars = len(str(system_prompt)) if system_prompt else 0
            deps.get_kpi_writer().count(
                "agent.updated",
                dims={
                    "team_id": str(team_id),
                    "agent_instance_id": agent_instance_id,
                    "system_prompt_chars": str(system_prompt_chars),
                },
                actor=to_kpi_actor(user),
            )
        except Exception:
            logger.exception("[control-plane][kpi] Failed to emit agent.updated")
    return _record_to_summary(updated) if updated is not None else None


async def unenroll_agent_instance(
    *,
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
    user: KeycloakUser | None = None,
) -> bool:
    """
    Unenroll (delete) one managed agent instance for a team.

    Why this function exists:
    - managed agent lifecycle stays in control-plane, so unbinding is a local
      metadata deletion rather than a runtime call

    How to use it:
    - call after team authorization has already been checked
    - pass request-scoped product dependencies when available

    Example:
    - `deleted = await unenroll_agent_instance(team_id=team_id, agent_instance_id="inst-1", deps=deps)`
    """
    store = deps.get_agent_instance_store()
    deleted = await store.delete(agent_instance_id, team_id)
    if deleted:
        try:
            deps.get_kpi_writer().count(
                "agent.deleted_total",
                dims={
                    "team_id": str(team_id),
                    "agent_instance_id": agent_instance_id,
                },
                actor=to_kpi_actor(user) if user else KPIActor(type="system"),
            )
        except Exception:
            logger.exception("[control-plane][kpi] Failed to emit agent.deleted_total")
    return deleted


async def prepare_runtime_agent_execution(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    runtime_id: str,
    agent_id: str,
    deps: ProductServiceDependencies,
) -> "RuntimeAgentExecutionPreparation":
    """
    Prepare an execution grant for a direct runtime agent target.

    Used by the evaluation worker to call POST /agents/evaluate on a
    configured runtime without exposing cluster-internal URLs.
    """

    source = next(
        (
            s
            for s in deps.configuration.platform.runtime_catalog_sources
            if s.runtime_id == runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise ExecutionPreparationError(
            f"Runtime '{runtime_id}' is not available or not enabled.",
            http_status=422,
        )
    if not source.ingress_prefix:
        raise ExecutionPreparationError(
            f"Runtime '{runtime_id}' has no ingress_prefix configured.",
            http_status=503,
        )

    # Non-public agents are NOT available via the direct agent_id path for anyone —
    # not even admins. The runtime is the enforcement point: it refuses direct
    # execution of a non-public agent_id with 404 before execution
    # (agent_app.py _resolve_agent_instance, AGENT-VISIBILITY-RFC §3.1). So minting
    # a direct grant for a hidden agent would only hand back an UNUSABLE grant.
    # We therefore resolve with include_non_public=False unconditionally: a hidden
    # agent_id resolves to "not found" here too, keeping control-plane and runtime
    # consistent. Internal agents remain reachable only via the managed path
    # (enrollment, which IS admin-gated) — never the direct path.
    try:
        runtime_templates = await _fetch_runtime_templates(
            source.base_url, include_non_public=False
        )
    except EnrollmentError as exc:
        raise ExecutionPreparationError(str(exc), http_status=exc.http_status) from exc
    if not any(t.template_agent_id == agent_id for t in runtime_templates):
        raise ExecutionPreparationError(
            f"Agent '{agent_id}' is not available on runtime '{runtime_id}'.",
            http_status=404,
        )

    # RUNTIME-07 rev. 2: no signed grant — just the ingress-relative evaluate URL.
    prefix = source.ingress_prefix.rstrip("/")

    return RuntimeAgentExecutionPreparation(
        runtime_id=runtime_id,
        agent_id=agent_id,
        team_id=team_id,
        evaluate_url=f"{prefix}/agents/evaluate",
    )


async def _resolve_context_prompt_text(
    prompt_id: str,
    deps: ProductServiceDependencies,
    *,
    team_ids: Sequence[TeamId],
    lang: str = "en",
) -> str | None:
    """Resolve one attached chat-context prompt id to its current text.

    Library prompts resolve via ``PromptStore`` scoped to ``team_ids`` — the
    caller's authorized teams (active team plus personal team), matching the
    prompts the context picker can surface (PROMPTS.md §4/§6). A team-scoped
    lookup is used instead of a raw ``get(prompt_id)`` by primary key so a
    session cannot resolve a prompt owned by an unrelated team. Synthetic
    ``default:{category}`` ids resolve from the in-memory platform defaults.
    Unknown / deleted / out-of-scope ids resolve to ``None`` and are skipped by
    the caller, so a stale id never breaks an open conversation (PROMPTS.md §5).
    """

    if prompt_id.startswith("default:"):
        category = prompt_id.removeprefix("default:")
        spec = _DEFAULT_PROMPT_BY_CATEGORY.get(category)
        if spec is None:
            return None
        return spec.text("fr" if lang == "fr" else "en")
    store = deps.get_prompt_store()
    for team_id in team_ids:
        prompt = await store.get_for_team(prompt_id, team_id)
        if prompt is not None:
            return prompt.text
    return None


async def prepare_execution(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    agent_instance_id: str,
    session_id: str | None = None,
    lang: str = "en",
    deps: ProductServiceDependencies,
    authorization: str | None = None,
) -> ExecutionPreparation:
    """
    Prepare one authorized runtime execution context for one managed agent instance.

    Why this function exists:
    - control-plane must issue team-scoped execution context and ingress-safe
      runtime URLs without taking over runtime execution itself

    How to use it:
    - call after team membership has already been validated
    - pass request-scoped product dependencies when available
    - the returned payload now includes `effective_chat_options`, the typed
      chat-affordance surface resolved from the stored managed-agent config

    Example:
    - `prep = await prepare_execution(user=user, team_id=team_id, agent_instance_id="inst-1", deps=deps)`
    """
    store = deps.get_agent_instance_store()

    instance = await store.get_for_team(agent_instance_id, team_id)
    if instance is None:
        raise ExecutionPreparationError(
            f"Unknown agent instance {agent_instance_id!r} for team {team_id!r}."
        )
    if not instance.enabled:
        raise ExecutionPreparationError(
            f"Agent instance {agent_instance_id!r} is disabled.",
            http_status=409,
        )
    # --- #1975 suspension guard (RFC §3.9) — BEGIN -------------------------
    # A suspended instance has a broken/unavailable capability; execution must
    # fail loudly and typed rather than silently degrade (an agent missing its
    # tools would answer from priors). This early guard is intentionally
    # self-contained so it hand-merges cleanly with #1976's chat-control work
    # below. Touches ONLY these lines.
    if instance.suspension_reason is not None:
        raise ExecutionPreparationError(
            f"Agent instance {agent_instance_id!r} is suspended "
            f"({instance.suspension_reason}): a capability it uses is broken or "
            "unavailable. An editor must fix it in the agent settings before it "
            "can run.",
            http_status=409,
        )
    # --- #1975 suspension guard — END -------------------------------------

    source = next(
        (
            s
            for s in deps.configuration.platform.runtime_catalog_sources
            if s.runtime_id == instance.source_runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise ExecutionPreparationError(
            f"Runtime source {instance.source_runtime_id!r} is not available.",
            http_status=503,
        )
    if not source.ingress_prefix:
        raise ExecutionPreparationError(
            f"Runtime source {instance.source_runtime_id!r} has no ingress_prefix "
            "configured. Set ingress_prefix in platform.runtime_catalog_sources.",
            http_status=503,
        )

    # RUNTIME-07 rev. 2: the control-plane issues NO signed grant. It returns
    # ingress-relative URLs (+ resolved context prompt). The runtime authenticates
    # the user (Keycloak JWT), authorizes via OpenFGA, and resolves this instance's
    # template + tuning through the team-scoped resolution endpoint.
    prefix = source.ingress_prefix.rstrip("/")

    context_prompt_text: str | None = None
    if session_id is not None:
        session_record = await deps.get_session_metadata_store().get(session_id)
        if session_record is not None and session_record.context_prompt_ids:
            # Resolve library prompts only within the caller's authorized scope:
            # the active team plus the caller's personal team (the same union the
            # context picker draws from — PROMPTS.md §4/§6).
            allowed_team_ids: list[TeamId] = [team_id]
            personal_tid = personal_team_id(user.uid)
            if personal_tid != team_id:
                allowed_team_ids.append(personal_tid)
            resolved: list[str] = []
            for prompt_id in session_record.context_prompt_ids:
                text = await _resolve_context_prompt_text(
                    prompt_id, deps, team_ids=allowed_team_ids, lang=lang
                )
                if text:
                    resolved.append(text)
            # PROMPTS.md §5: concatenate control-plane-side so the runtime
            # contract stays a single scalar (fred-sdk/fred-runtime untouched).
            context_prompt_text = "\n\n".join(resolved) or None

    # Instance-bound capability route base URLs (#1979, RFC §9.1): the same
    # ingress-relative pattern the pod advertises on the template catalog
    # (`{prefix}/capabilities/{id}`), resolved here for the capabilities this
    # instance actually selected so the in-session UI calls them directly.
    selected_capability_ids = instance.tuning.selected_capability_ids or []
    capability_base_urls = {
        cap_id: f"{prefix}/capabilities/{cap_id}" for cap_id in selected_capability_ids
    }

    # Chat-time composer controls (#1976, RFC §3.3/§3.7): computed per capability
    # on the pod at session prep, version-keyed cache-aside, never persisted.
    # Descriptors ship on ExecutionPreparation — the slot the retired
    # `effective_chat_options` occupied. Best-effort: an unreachable pod yields
    # no controls this prep (logged), never a failed prep.
    available_capabilities = await _available_capabilities_for_source(source.base_url)
    chat_controls = await _resolve_chat_controls(
        instance.tuning,
        available_capabilities,
        source.base_url,
        # The pod's chat-controls route authenticates the caller; forward the
        # acting user's bearer like the validate-config round-trip.
        authorization=authorization,
    )

    return ExecutionPreparation(
        agent_instance_id=agent_instance_id,
        team_id=team_id,
        runtime_id=source.runtime_id,
        execute_url=f"{prefix}/agents/execute",
        execute_stream_url=f"{prefix}/agents/execute/stream",
        messages_url_template=f"{prefix}/agents/sessions/{{session_id}}/messages",
        chat_controls=chat_controls,
        runtime_display_name=source.runtime_id,
        context_prompt_text=context_prompt_text,
        capability_base_urls=capability_base_urls,
    )


async def get_runtime_binding_for_team(
    agent_instance_id: str,
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> ManagedAgentRuntimeBinding | None:
    """
    Resolve one managed instance into its runtime binding, scoped to one team.

    Why this function exists (RUNTIME-07 rev. 2):
    - The runtime pod resolves an `agent_instance_id` into its template + tuning
      at execution time. This is the team-scoped, ReBAC-gated path that replaced
      the removed admin-only unscoped `store.get` lookup (finding F2).
    - It returns config only (logical ids + tuning snapshot) — never a secret,
      connection string, or a signed capability. Authorization of the end user is
      enforced by the runtime pod (Keycloak JWT + OpenFGA) AND by the caller of
      this function (team ReBAC at the endpoint), so the binding it returns is
      tenant-isolated by construction.

    How to use it:
    - call from the team-scoped resolution endpoint after a team ReBAC check
    - returns None when no instance with that id exists in that team
    """
    store = deps.get_agent_instance_store()
    instance = await store.get_for_team(agent_instance_id, team_id)
    if instance is None:
        return None
    # Resolve this team's per-capability enablement settings and ship only the
    # slices for the capabilities this instance actually selected (CAPAB-01 /
    # #1980, RFC §8.2). The pod carries each to `CapabilityContext.team_settings`.
    selected = set(instance.tuning.selected_capability_ids or [])
    all_team_settings = await deps.get_team_capability_settings_store().list_for_team(
        team_id
    )
    team_capability_settings = {
        cap_id: settings
        for cap_id, settings in all_team_settings.items()
        if cap_id in selected
    }
    return ManagedAgentRuntimeBinding(
        agent_instance_id=instance.agent_instance_id,
        template_agent_id=instance.source_agent_id,
        display_name=instance.display_name,
        owner_team_id=instance.team_id,
        enabled=instance.enabled,
        tuning=instance.tuning,
        team_capability_settings=team_capability_settings,
    )


# ---------------------------------------------------------------------------
# Prompt library
# ---------------------------------------------------------------------------


def _validate_prompt_library_text(
    *,
    text: str,
    context_label: str,
) -> None:
    """
    Validate one saved prompt-library text payload before persistence.

    Why this function exists:
    - managed-agent tuning validation already protects inline `prompts.*`
      values, but the prompt library needs the same persistence-time safety at
      its own CRUD boundary

    How to use it:
    - call before creating or updating one `Prompt` record
    - invalid template syntax raises `PromptRequestError(http_status=422)`

    Example:
    - `_validate_prompt_library_text(text=request.text, context_label="prompt create")`
    """

    prompt_errors = validate_prompt_template(text)
    if not prompt_errors:
        return
    details = "; ".join(f"'{error.pattern}': {error.reason}" for error in prompt_errors)
    raise PromptRequestError(
        f"Invalid prompt template during {context_label}: {details}.",
        http_status=422,
    )


def _prompt_record_to_summary(record: PromptRecord) -> PromptSummary:
    """Project one stored prompt record into the list/command summary shape.

    Why this function exists:
    - prompt list surfaces should hide the full prompt text by default while
      keeping one consistent typed projection

    How to use it:
    - call after reading prompt records from the store for list/create/update
      responses

    Example:
    - `summary = _prompt_record_to_summary(record)`
    """

    text = record.text or ""
    preview = (
        text
        if len(text) <= _TEXT_PREVIEW_MAX
        else text[:_TEXT_PREVIEW_MAX].rsplit(" ", 1)[0] + "…"
    )
    return PromptSummary(
        id=record.prompt_id,
        name=record.name,
        description=record.description,
        category=PromptCategory(record.category) if record.category else None,
        emoji=record.emoji,
        tags=record.tags,
        text_preview=preview or None,
        created_by=record.created_by,
        version=record.version,
        import_count=record.import_count,
        session_count=record.session_count,
        score=record.score,
        avg_input_tokens=record.avg_input_tokens,
        avg_output_tokens=record.avg_output_tokens,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _prompt_record_to_detail(record: PromptRecord) -> PromptDetail:
    """Project one stored prompt record into the full detail response shape.

    Why this function exists:
    - prompt inspection flows need the saved text, team scope, and metadata in
      one stable outward-facing contract

    How to use it:
    - call after reading one prompt record for the detail endpoint or CLI
      inspection flows

    Example:
    - `detail = _prompt_record_to_detail(record)`
    """

    return PromptDetail(
        id=record.prompt_id,
        team_id=record.team_id,
        name=record.name,
        description=record.description,
        text=record.text,
        created_by=record.created_by,
        version=record.version,
        import_count=record.import_count,
        session_count=record.session_count,
        score=record.score,
        avg_input_tokens=record.avg_input_tokens,
        avg_output_tokens=record.avg_output_tokens,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def create_prompt(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    request: CreatePromptRequest,
    deps: ProductServiceDependencies,
) -> PromptSummary:
    """
    Create one team-scoped prompt-library record.

    Why this function exists:
    - prompt authoring must become a first-class control-plane product surface
      instead of staying buried inside managed-agent instance forms

    How to use it:
    - call from the prompt-library POST route after team membership is checked
    - invalid template syntax raises `PromptRequestError(422)`
    - duplicate prompt names inside the same team raise `PromptRequestError(409)`

    Example:
    - `summary = await create_prompt(user=user, team_id=team_id, request=body, deps=deps)`
    """

    _validate_prompt_library_text(
        text=request.text,
        context_label=f"prompt create for team {team_id!r}",
    )
    record = PromptRecord(
        prompt_id=str(uuid4()),
        team_id=team_id,
        name=request.name,
        description=request.description,
        category=request.category.value,
        emoji=request.emoji,
        tags=request.tags,
        text=request.text,
        created_by=user.uid,
    )
    try:
        created = await deps.get_prompt_store().create(record)
    except PromptAlreadyExistsError as exc:
        raise PromptRequestError(
            f"Prompt name {request.name!r} already exists for team {team_id!r}.",
            http_status=409,
        ) from exc
    return _prompt_record_to_summary(created)


def _system_default_to_summary(
    spec: DefaultPromptSpec, lang: str, session_count: int = 0
) -> PromptSummary:
    """Project one system-default spec into a read-only PromptSummary.

    For defaults, text_preview carries the FULL prompt text (no truncation)
    so the frontend can show the complete content in a read-only modal without
    a separate API call. The text is in-memory so there is no storage cost.
    session_count is supplied by the caller from the default_prompt_usage table.
    """
    effective = "fr" if lang == "fr" else "en"
    return PromptSummary(
        id=f"default:{spec.category}",
        name=spec.name(effective),
        description=spec.description(effective),
        category=PromptCategory(spec.category),
        text_preview=spec.text(effective),
        is_default=True,
        created_by="Fred",
        session_count=session_count,
    )


async def list_prompts(
    team_id: TeamId,
    deps: ProductServiceDependencies,
    *,
    lang: str = "en",
    limit: int = 100,
) -> list[PromptSummary]:
    """
    List prompt-library records for one team, merging personal prompts with
    the 9 platform system defaults.

    Why this function exists:
    - prompt management needs a stable control-plane listing surface separate
      from managed-agent CRUD
    - system defaults are injected at query time (not stored per-user) so they
      are always present, always translated, and never lost

    How to use it:
    - call from the team prompts route after team membership is checked
    - pass `lang` from the frontend Accept-Language / UI preference

    Sort order:
    - session_count DESC (most-used first)
    - on equal session_count: personal prompts float above system defaults

    Example:
    - `prompts = await list_prompts(team_id, deps, lang="fr")`
    """

    store = deps.get_prompt_store()
    records = await store.list_by_team(team_id, limit=limit)
    personal = [_prompt_record_to_summary(r) for r in records]
    categories = [spec.category for spec in DEFAULT_PROMPTS]
    usage = await store.get_default_usage(team_id, categories)
    defaults = [
        _system_default_to_summary(spec, lang, usage.get(spec.category, 0))
        for spec in DEFAULT_PROMPTS
    ]
    combined = sorted(
        personal + defaults, key=lambda p: (-p.session_count, p.is_default)
    )
    return combined


async def get_prompt(
    team_id: TeamId,
    prompt_id: str,
    deps: ProductServiceDependencies,
) -> PromptDetail | None:
    """
    Return one full prompt-library record for one team.

    Why this function exists:
    - operators need to inspect saved prompt text independently from agent
      bindings

    How to use it:
    - call from the prompt detail route with the resolved team scope

    Example:
    - `detail = await get_prompt(team_id, prompt_id, deps)`
    """

    record = await deps.get_prompt_store().get_for_team(prompt_id, team_id)
    if record is None:
        return None
    return _prompt_record_to_detail(record)


async def record_prompt_use(
    prompt_id: str,
    team_id: TeamId,
    user: KeycloakUser,
    deps: ProductServiceDependencies,
) -> None:
    """Increment usage counter for any prompt selected from a picker.

    Covers both the chat context picker and the agent-form prompt picker.
    For default prompts (id starts with "default:") the counter lives in
    default_prompt_usage; for DB prompts it lives in PromptRow.session_count.
    Silently skips if the prompt has been deleted.
    """

    store = deps.get_prompt_store()
    if prompt_id.startswith("default:"):
        category = prompt_id.removeprefix("default:")
        if category in _VALID_DEFAULT_CATEGORIES:
            await store.increment_default_usage(category, team_id)
    else:
        prompt = await store.get_for_team(prompt_id, team_id)
        if prompt is None:
            prompt = await store.get_for_team(prompt_id, personal_team_id(user.uid))
        if prompt is not None:
            await store.increment_session_count(prompt_id, prompt.team_id)


async def update_prompt(
    team_id: TeamId,
    prompt_id: str,
    request: UpdatePromptRequest,
    deps: ProductServiceDependencies,
) -> PromptSummary | None:
    """
    Replace one team-scoped prompt-library record.

    Why this function exists:
    - the initial prompt-library slice intentionally keeps one simple mutable
      record model instead of version graphs or per-field patch semantics

    How to use it:
    - call from the prompt PUT route after team membership is checked
    - returns `None` when the prompt does not belong to `team_id`
    - invalid template syntax raises `PromptRequestError(422)`
    - duplicate names raise `PromptRequestError(409)`

    Example:
    - `summary = await update_prompt(team_id, prompt_id, request, deps)`
    """

    _validate_prompt_library_text(
        text=request.text,
        context_label=f"prompt update for team {team_id!r}",
    )
    try:
        updated = await deps.get_prompt_store().update(
            prompt_id,
            team_id,
            name=request.name,
            description=request.description,
            category=request.category.value,
            emoji=request.emoji,
            tags=request.tags,
            text=request.text,
        )
    except PromptAlreadyExistsError as exc:
        raise PromptRequestError(
            f"Prompt name {request.name!r} already exists for team {team_id!r}.",
            http_status=409,
        ) from exc
    if updated is None:
        return None
    return _prompt_record_to_summary(updated)


async def delete_prompt(
    team_id: TeamId,
    prompt_id: str,
    deps: ProductServiceDependencies,
) -> bool:
    """
    Delete one team-scoped prompt-library record.

    Why this function exists:
    - prompt-library cleanup belongs to control-plane product lifecycle, not to
      managed-agent instance writes

    How to use it:
    - call from the prompt DELETE route after team membership is checked

    Example:
    - `deleted = await delete_prompt(team_id, prompt_id, deps)`
    """

    return await deps.get_prompt_store().delete(prompt_id, team_id)


async def list_context_prompts(
    user: KeycloakUser,
    team_id: TeamId,
    deps: ProductServiceDependencies,
    *,
    lang: str = "en",
) -> list[ContextPromptSummary]:
    """Return the space's own prompts + platform defaults for the context picker.

    Personal prompts appear only in the personal space — a team context
    exposes the team's prompts, never the caller's personal ones. DB records are
    ordered by session_count DESC; defaults are appended at the end so
    frequently-used custom prompts appear first.
    """

    store = deps.get_prompt_store()
    records = await store.list_context_prompts(personal_team_id(user.uid), team_id)
    effective_lang = "fr" if lang == "fr" else "en"
    results: list[ContextPromptSummary] = [
        ContextPromptSummary(
            id=r.prompt_id,
            name=r.name,
            description=r.description,
            scope=r.scope,  # type: ignore[arg-type]
            category=PromptCategory(r.category) if r.category else None,
            version=r.version,
            session_count=r.session_count,
            score=r.score,
        )
        for r in records
    ]
    categories = [spec.category for spec in DEFAULT_PROMPTS]
    usage = await store.get_default_usage(team_id, categories)
    for spec in DEFAULT_PROMPTS:
        results.append(
            ContextPromptSummary(
                id=f"default:{spec.category}",
                name=spec.name(effective_lang),
                description=spec.description(effective_lang),
                scope="default",
                category=PromptCategory(spec.category),
                version=1,
                session_count=usage.get(spec.category, 0),
                text=spec.text(effective_lang),
            )
        )
    return results


async def promote_prompt(
    user: KeycloakUser,
    team_id: TeamId,
    prompt_id: str,
    request: PromptPromoteRequest,
    deps: ProductServiceDependencies,
) -> PromptSummary:
    """Copy one prompt from team_id to request.target_team_id. Returns the new copy."""

    store = deps.get_prompt_store()
    source = await store.get_for_team(prompt_id, team_id)
    if source is None:
        raise PromptRequestError(
            f"Prompt {prompt_id!r} not found for team {team_id!r}.", http_status=404
        )
    target_team_id = TeamId(request.target_team_id)
    record = PromptRecord(
        prompt_id=str(uuid4()),
        team_id=target_team_id,
        name=source.name,
        description=source.description,
        text=source.text,
        created_by=user.uid,
    )
    try:
        created = await store.create(record)
    except PromptAlreadyExistsError:
        raise PromptRequestError(
            f"Prompt name {source.name!r} already exists in team {request.target_team_id!r}. "
            "Rename the existing prompt or the source before promoting.",
            http_status=409,
        )
    return _prompt_record_to_summary(created)


async def update_prompt_score(
    team_id: TeamId,
    prompt_id: str,
    request: PromptScoreUpdateRequest,
    deps: ProductServiceDependencies,
) -> PromptSummary | None:
    """Set the explicit quality score (0.0–5.0) for one team-scoped prompt."""

    updated = await deps.get_prompt_store().update_score(
        prompt_id, team_id, request.score
    )
    if updated is None:
        return None
    return _prompt_record_to_summary(updated)


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------


async def create_session(
    user: KeycloakUser,
    team_id: TeamId,
    request: CreateSessionRequest,
    deps: ProductServiceDependencies,
) -> SessionListItem:
    """
    Register one new control-plane-owned session metadata record.

    Why this function exists:
    - the frontend needs a lightweight control-plane row as soon as a team
      session starts, before later activity refreshes
    - duplicate `session_id` creation should surface as a domain conflict
      rather than a storage-specific exception

    How to use it:
    - call once when a team starts a brand-new session id
    - catch `SessionAlreadyExistsError` when a duplicate should map to HTTP 409

    Example:
    - `item = await create_session(user, team_id, request, deps)`
    """
    record = SessionMetadataRecord(
        session_id=request.session_id,
        team_id=team_id,
        agent_instance_id=request.agent_instance_id,
        user_id=user.uid,
        title=request.title,
    )
    try:
        created = await deps.get_session_metadata_store().create(record)
    except SessionMetadataAlreadyExistsError as exc:
        raise SessionAlreadyExistsError(request.session_id) from exc
    try:
        deps.get_kpi_writer().count(
            "session.created_total",
            dims={
                "team_id": team_id,
                "scope_type": "personal" if is_personal_team_id(team_id) else "team",
                "agent_instance_id": request.agent_instance_id,
            },
            actor=to_kpi_actor(user),
        )
    except Exception:
        logger.exception("[control-plane][kpi] Failed to emit session.created_total")
    return _record_to_item(created)


async def list_sessions(
    team_id: TeamId,
    deps: ProductServiceDependencies,
    user_id: str | None = None,
    limit: int = 50,
) -> list[SessionListItem]:
    """
    List session metadata records for one team, newest first.

    Why this function exists:
    - the frontend sidebar needs a lightweight control-plane list, separate from
      runtime-owned message history

    How to use it:
    - call from the team sessions route
    - pass request-scoped product dependencies when available
    - pass user_id to restrict results to sessions owned by that user

    Example:
    - `sessions = await list_sessions(team_id, user_id=user.uid, deps=deps)`
    """
    records = await deps.get_session_metadata_store().list_by_team(
        team_id,
        user_id=user_id,
        limit=limit,
    )
    return [_record_to_item(r) for r in records]


async def update_session_activity(
    team_id: TeamId,
    session_id: str,
    request: UpdateSessionRequest,
    deps: ProductServiceDependencies,
    user: KeycloakUser | None = None,
) -> SessionListItem | None:
    """
    Refresh control-plane metadata for one completed managed turn.

    Why this function exists:
    - The sidebar sorts sessions by control-plane-owned `updated_at`, while
      runtime remains the only owner of message content.

    How to use it:
    - call from the PATCH session metadata endpoint after runtime reports a
      completed turn.

    Example:
    - `await update_session_activity(team_id, session_id, request, deps)`
    """
    store = deps.get_session_metadata_store()
    if user is None:
        # Fail closed: metadata updates are user-owned operations.
        return None

    record: SessionMetadataRecord | None = None

    if request.title is not None or request.updated_at is not None:
        record = await store.update_metadata(
            session_id=session_id,
            team_id=team_id,
            user_id=user.uid,
            title=request.title,
            updated_at=request.updated_at,
        )
        if record is None:
            return None

    # A present `context_prompt_ids` (even null/[]) replaces the full set; an
    # absent field leaves the context untouched — so freshness-only PATCHes do
    # not wipe a conversation's attached prompts (PROMPTS.md §5).
    if "context_prompt_ids" in request.model_fields_set:
        prompt_ids = request.context_prompt_ids or []
        result = await store.replace_context_prompts(
            session_id, team_id, user.uid, prompt_ids
        )
        if result is None:
            return None
        record, newly_attached = result
        # session_count increments on first attach only (PROMPTS.md §5).
        for prompt_id in newly_attached:
            await record_prompt_use(prompt_id, team_id, user, deps)

    if record is None:
        # Neither metadata nor context changed (e.g. an empty PATCH): fetch the
        # current record, enforcing team + owner scoping ourselves.
        record = await store.get(session_id)
        if (
            record is None
            or str(record.team_id) != str(team_id)
            or record.user_id != user.uid
        ):
            return None

    return _record_to_item(record)


async def get_session(
    team_id: TeamId,
    session_id: str,
    deps: ProductServiceDependencies,
) -> SessionListItem | None:
    """
    Fetch one control-plane session metadata record by ID, scoped to a team.

    Why this function exists:
    - the chat header needs the session title without loading the full session list

    How to use it:
    - call from the GET session-by-id route
    - returns None when the session does not exist or belongs to a different team

    Example:
    - `item = await get_session(team_id, session_id, deps)`
    """
    record = await deps.get_session_metadata_store().get(session_id)
    if record is None or str(record.team_id) != str(team_id):
        return None
    return _record_to_item(record)


async def list_session_attachments(
    *,
    team_id: TeamId,
    session_id: str,
    user_id: str,
    deps: ProductServiceDependencies,
) -> list[SessionAttachmentSummary]:
    """
    List persisted conversation attachments for one owned session.

    Why this function exists:
    - the chat drawer needs a reload-safe source of truth for session-level
      attachments after transient composer chips have cleared

    How to use it:
    - call after team authorization has already succeeded
    - the function enforces that the session belongs to the given user
    """

    await _get_owned_session_record(
        deps=deps,
        team_id=team_id,
        session_id=session_id,
        user_id=user_id,
    )
    records = await deps.get_session_attachment_store().list_for_session(session_id)
    return [_to_session_attachment_summary(record) for record in records]


async def create_session_attachment(
    *,
    team_id: TeamId,
    session_id: str,
    user_id: str,
    request: CreateSessionAttachmentRequest,
    deps: ProductServiceDependencies,
) -> SessionAttachmentSummary:
    """
    Persist one attachment summary for a conversation after fast-ingest.

    Why this function exists:
    - upload/ingest is handled by Knowledge Flow, but the chat product surface
      needs durable session-scoped metadata for reload, preview, and deletion

    How to use it:
    - call once the frontend has both the storage upload result and the
      fast-ingest response
    - repeated calls with the same `attachment_id` update the stored row
    """

    await _get_owned_session_record(
        deps=deps,
        team_id=team_id,
        session_id=session_id,
        user_id=user_id,
    )
    store = deps.get_session_attachment_store()
    await store.save(
        SessionAttachmentRecord(
            session_id=session_id,
            attachment_id=request.attachment_id,
            name=request.name,
            mime=request.mime,
            size_bytes=request.size_bytes,
            summary_md=request.summary_md,
            document_uid=request.document_uid,
            storage_key=request.storage_key,
        )
    )
    saved = await store.list_for_session(session_id)
    created = next(
        (item for item in saved if item.attachment_id == request.attachment_id), None
    )
    if created is None:
        raise SessionAttachmentRequestError(
            f"Failed to persist attachment {request.attachment_id!r} for session {session_id!r}.",
            http_status=500,
        )
    return _to_session_attachment_summary(created)


async def delete_session_attachment(
    *,
    team_id: TeamId,
    session_id: str,
    attachment_id: str,
    user_id: str,
    authorization: str,
    deps: ProductServiceDependencies,
) -> bool:
    """
    Delete one persisted attachment and its Knowledge Flow artifacts.

    Why this function exists:
    - the drawer delete action must remove both control-plane metadata and the
      underlying vectors/content owned by Knowledge Flow

    How to use it:
    - call after team authorization has already succeeded
    - pass the caller's `Authorization` header so cleanup can run with the
      same user identity in Knowledge Flow
    """

    await _get_owned_session_record(
        deps=deps,
        team_id=team_id,
        session_id=session_id,
        user_id=user_id,
    )
    store = deps.get_session_attachment_store()
    records = await store.list_for_session(session_id)
    record = next(
        (item for item in records if item.attachment_id == attachment_id), None
    )
    if record is None:
        return False

    await _delete_knowledge_flow_attachment(
        deps=deps,
        authorization=authorization,
        document_uid=record.document_uid,
        storage_key=record.storage_key,
        session_id=session_id,
    )
    await store.delete(session_id, attachment_id)
    return True


async def delete_session(
    team_id: TeamId,
    session_id: str,
    user_id: str,
    authorization: str,
    deps: ProductServiceDependencies,
) -> bool:
    """
    Remove one control-plane session metadata record and cleanup attachments.

    Thin wrapper over `ConversationErasureService.erase_session` (CTRLP-12 A1):
    the erasure logic now lives in the service, which returns an auditable
    `ErasureReceipt`. This function keeps its historical bool contract —
    True when the metadata row was deleted, False when it did not exist.

    Returns True when a row was deleted, False when the session did not exist.
    """
    # Local import avoids an import cycle: erasure_service reaches back into
    # this module for `_get_owned_session_record` / `_delete_knowledge_flow_attachment`.
    from control_plane_backend.sessions.erasure_service import (
        STORE_SESSION_METADATA,
        ConversationErasureService,
    )

    receipt = await ConversationErasureService(deps).erase_session(
        team_id=team_id,
        session_id=session_id,
        user_id=user_id,
        authorization=authorization,
    )
    logger.info(
        "[CTRLP-12] erase_session receipt session_id=%s ok=%s stores=%s",
        session_id,
        receipt.ok,
        receipt.model_dump()["stores"],
    )
    metadata_result = next(
        (r for r in receipt.stores if r.store == STORE_SESSION_METADATA), None
    )
    return bool(metadata_result and metadata_result.deleted_count)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_delete_window(
    *,
    team_id: TeamId,
    deps: ProductServiceDependencies,
) -> str | None:
    """Resolve the governed delete window (ISO-8601) for a conversation's space.

    The window *source* is the only thing that differs between the two spaces
    (CTRLP-12 A5, RFC §3.A DoD#2):

    - **personal** (`is_personal_team_id`) → the platform `personal_delete_grace`
      read straight off the policy catalog. It is platform-only and never
      overridable, so a user cannot shorten a post-incident retention window.
    - **team** → the effective `team_delete_grace` from the B3 resolver: the
      owner-set value clamped to the platform cap.

    Returns None when no window is configured for that space → the caller erases
    immediately (the default).

    **Immediate by default (CTRLP-12 D1, RFC §1.2 / §3.B):** the platform cap is a
    *ceiling* for what a team MAY set, never an implicit default window. A team
    that has set **no** value erases immediately — it does not inherit the cap as
    a deferral window. Deferral (now real: erase-at-expiry via C1+C2+E1) applies
    only when the team owner has explicitly set `team_delete_grace`, and is
    clamped to the platform cap.
    """
    purge = deps.get_policy_catalog().conversation_policies.purge
    if is_personal_team_id(team_id):
        return purge.personal_delete_grace

    # CTRLP-12 (RFC §3.B): per-team retention lives on team_metadata, read off the
    # already-fetched record — no separate override store.
    metadata = await deps.get_team_metadata_store().get_by_team_id(team_id)
    team_grace = metadata.team_delete_grace if metadata else None
    if team_grace is None:
        # Unset ⇒ immediate delete. Do NOT inherit the cap as a default window.
        return None
    # The team opted in: clamp its value to the platform cap (team may only
    # tighten). PATCH already rejects > cap (422), so this returns the team value.
    resolution = resolve_team_retention_view(
        policy=purge,
        team_id=team_id,
        team_delete_grace_override=team_grace,
        max_idle_override=metadata.max_idle if metadata else None,
    )
    return resolution.team_delete_grace.effective


async def _defer_erasure(
    *,
    session: SessionMetadataRecord,
    team_id: TeamId,
    session_id: str,
    user_id: str,
    deleted_at: datetime,
    due_at: datetime,
    reason: ErasureReason,
    deps: ProductServiceDependencies,
) -> None:
    """Hide the conversation now and register a *converging* erasure at `due_at`.

    Marks the metadata row `deleted_at` (hidden from the sidebar, history
    retained), enqueues an idempotent `USER_DELETED` purge-queue entry, and
    surfaces an observable scheduled erasure task. The lifecycle worker runs
    `erase_session` at `due_at` and marks the queue entry done only on
    `receipt.ok`, so a partial fan-out keeps retrying until it converges — the
    reason this is reused by both the deferred path and the immediate-erase
    failure fallback (CTRLP-12).
    """
    await deps.get_session_metadata_store().mark_deleted(
        session_id=session_id,
        team_id=team_id,
        user_id=user_id,
        deleted_at=deleted_at,
    )
    inserted = await deps.get_purge_queue_store().enqueue(
        session_id=session_id,
        team_id=str(team_id),
        user_id=user_id,
        due_at=due_at,
    )
    # CTRLP-12 (P2): the enqueue above is idempotent for an already-pending
    # session, so a retried / double-clicked deferred delete keeps the original
    # queue row. Only mint the observable scheduled erasure task alongside a NEW
    # row — the lifecycle worker advances just the first active task per session,
    # so a second task would sit pending in the admin schedule forever.
    task_service = deps.get_task_service()
    create_task = inserted
    if not inserted:
        # The pending queue row was kept, so its scheduled task normally already
        # exists. But schedule_erasure_task is best-effort (it swallows failures):
        # if the original creation failed, the queue would still converge while
        # the admin schedule stayed blind. Heal that by recreating the task only
        # when none is active — preserving the anti-duplication guarantee. Task
        # bookkeeping is best-effort and must never block the durable erasure.
        try:
            create_task = (
                await find_active_erasure_task_id(
                    task_service, session_id=session_id, team_id=str(team_id)
                )
                is None
            )
        except Exception:
            logger.exception(
                "[CTRLP-12] erasure-task existence check failed for session %s; "
                "skipping task creation (erasure still converges via the queue)",
                session_id,
            )
            create_task = False
    if create_task:
        await schedule_erasure_task(
            task_service,
            session_id=session_id,
            team_id=str(team_id),
            user_id=user_id,
            title=getattr(session, "title", None),
            due_at=due_at,
            reason=reason,
        )


async def delete_or_defer_session(
    *,
    team_id: TeamId,
    session_id: str,
    user_id: str,
    authorization: str,
    deps: ProductServiceDependencies,
) -> None:
    """The conversation delete button: hide now, erase after a governed window.

    CTRLP-12 A5 (RFC §3.A DoD#2). Both spaces behave identically — hide the
    conversation immediately and defer the full `erase_session` — and differ
    only in the window *source* (see `_resolve_delete_window`):

    - window resolved (team `team_delete_grace` / personal `personal_delete_grace`)
      → mark the row `deleted_at` (hidden from the sidebar, history retained) and
      enqueue a `USER_DELETED` purge-queue entry due at `now + window`; the
      lifecycle runs `erase_session` at expiry (A6).
    - window unset/None → erase immediately (back-compat), via `erase_session`.
      If that immediate erase is *incomplete* (a store/runtime failure retains
      the metadata row), it does not silently return 204 — it falls back to the
      same queue path (due now) so the lifecycle worker retries until the erasure
      converges (CTRLP-12).

    Ownership is enforced up front (`_get_owned_session_record` raises 404 for a
    missing / non-owned session), identical to the immediate-erase path.
    """
    # Enforce team + ownership before either branch (raises 404 on a miss).
    session = await _get_owned_session_record(
        deps=deps,
        team_id=team_id,
        session_id=session_id,
        user_id=user_id,
    )

    window = await _resolve_delete_window(team_id=team_id, deps=deps)
    if window is None:
        # No governed window for this space → erase now (back-compat). The
        # session provably exists here (ownership was enforced above), so a
        # False return means the fan-out was INCOMPLETE and the metadata row was
        # RETAINED. Do not silently drop it (CTRLP-12): the endpoint would return
        # 204 while the conversation stays visible and never converges. Instead,
        # fall back to the queue — hide it now and let the lifecycle worker retry
        # the erase (due immediately) until `receipt.ok`.
        deleted = await delete_session(
            team_id=team_id,
            session_id=session_id,
            user_id=user_id,
            authorization=authorization,
            deps=deps,
        )
        if deleted:
            return
        now = _utcnow()
        logger.warning(
            "[CTRLP-12] immediate erase incomplete session_id=%s space=%s → "
            "deferring retry via purge queue (due now)",
            session_id,
            "personal" if is_personal_team_id(team_id) else "team",
        )
        await _defer_erasure(
            session=session,
            team_id=team_id,
            session_id=session_id,
            user_id=user_id,
            deleted_at=now,
            due_at=now,
            reason=ErasureReason.user_deleted,
            deps=deps,
        )
        return

    now = _utcnow()
    due_at = now + timedelta(seconds=duration_to_seconds(window))
    # CTRLP-12: hide the conversation now and make the scheduled erasure observable
    # to platform/team admins the instant it is deferred — with its due date.
    await _defer_erasure(
        session=session,
        team_id=team_id,
        session_id=session_id,
        user_id=user_id,
        deleted_at=now,
        due_at=due_at,
        reason=ErasureReason.user_deleted,
        deps=deps,
    )
    logger.info(
        "[CTRLP-12] deferred delete session_id=%s space=%s window=%s due=%s",
        session_id,
        "personal" if is_personal_team_id(team_id) else "team",
        window,
        now + timedelta(seconds=duration_to_seconds(window)),
    )


def _record_to_item(record: SessionMetadataRecord) -> SessionListItem:
    return SessionListItem(
        session_id=record.session_id,
        team_id=record.team_id,
        agent_instance_id=record.agent_instance_id,
        title=record.title,
        context_prompt_ids=record.context_prompt_ids,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
