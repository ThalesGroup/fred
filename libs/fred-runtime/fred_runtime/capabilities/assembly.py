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
Agent assembly: selected capabilities → the platform-frame block
(#1973, RFC AGENT-CAPABILITY-RFC.md §3.5, §3.8, §5.3, §5.4).

Why this module exists:
- the platform frame reserves ONE capability slot
  (`build_react_platform_middleware_frame(capability_middleware=...)`) and the
  frame does NOT sort — this module is where the deterministic order is
  produced: capability blocks sorted by capability id (a UI reorder must not
  change behavior), authored order preserved within one capability's stack
- capability `HitlSpec`s never become middleware; they are collected here
  into `CapabilityHitlBinding`s for the single `FredHitlMiddleware` gate

How to use:
- per selected capability, build its typed context with
  `build_capability_context(...)` (raw stored-config / turn-options slices
  are validated against the capability's own models — the RFC §3.5/§3.8
  slice-validation pattern)
- then `build_capability_agent_block(registry, contexts)` and pass
  `block.middleware` / `block.hitl` into the ReAct loop builder
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityIdentity,
    ChatControlItem,
    ChatControlsRequest,
    ChatControlsResponse,
    ChatControlsResult,
    StoredCapabilityConfig,
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain.agents.middleware import AgentMiddleware
from pydantic import BaseModel, ValidationError

from fred_runtime.react.middleware.hitl import CapabilityHitlBinding

from .errors import (
    CapabilityAssemblyError,
    CapabilityConfigInvalidError,
    TurnOptionsInvalidError,
)
from .registry import CapabilityRegistry


def _validated_slice(
    model: type[BaseModel], value: BaseModel | Mapping[str, Any] | None
) -> BaseModel:
    """Validate one raw config/options slice against a capability's typed model."""

    if isinstance(value, BaseModel):
        return model.model_validate(value.model_dump())
    return model.model_validate(dict(value) if value is not None else {})


def resolve_stored_config(
    capability: AgentCapability[Any, Any, Any],
    envelope: StoredCapabilityConfig | Mapping[str, Any],
) -> BaseModel:
    """
    Validate one persisted `capability_config` slice into the typed stored
    config (#1974, RFC §3.8, §3.9).

    Why this exists:
    - each slice is stored as `{"schema_version": manifest.version,
      "config": {...}}`; when the stored `schema_version` matches the
      installed capability, plain `StoredConfigModel` validation applies;
      on mismatch the capability's lazy `upgrade_config` hook runs — never a
      mass row migration
    - any failure raises the named `CapabilityConfigInvalidError` (the §3.9
      `capability_config_invalid` suspension reason) instead of degrading
      silently
    """

    cap_id = capability.manifest.id
    try:
        parsed = (
            envelope
            if isinstance(envelope, StoredCapabilityConfig)
            else StoredCapabilityConfig.model_validate(dict(envelope))
        )
    except ValidationError as exc:
        raise CapabilityConfigInvalidError(
            f"Capability '{cap_id}': persisted config slice is not the "
            f'{{"schema_version", "config"}} envelope (RFC §3.8): {exc}'
        ) from exc
    try:
        if parsed.schema_version == capability.manifest.version:
            return capability.StoredConfigModel.model_validate(parsed.config)
        return capability.upgrade_config(parsed.config, parsed.schema_version)
    except Exception as exc:
        raise CapabilityConfigInvalidError(
            f"Capability '{cap_id}': stored config (schema_version "
            f"{parsed.schema_version}, installed {capability.manifest.version}) "
            f"is no longer valid — reset its parameters and re-save the agent. "
            f"Cause: {exc}"
        ) from exc


def evaluate_capability_chat_controls(
    registry: CapabilityRegistry,
    *,
    capability_id: str,
    config_envelope: StoredCapabilityConfig | Mapping[str, Any] | None,
) -> ChatControlsResult:
    """
    Evaluate ONE capability's chat-time controls at session prep
    (#1976, RFC §3.3, §3.7).

    The stored slice is resolved (same version + `upgrade_config` path as
    execution) and `capability.chat_controls(config)` is called; the returned
    `ChatControlSpec`s are projected to JSON-safe `ChatControlItem`s in
    returned-list order (= display order within this capability). A capability
    the pod does not have installed, or a slice that cannot be resolved (RFC
    §3.9), yields a result whose `error` is set and whose `controls` is empty —
    control-plane skips it with a warning rather than failing the whole prep.
    """

    if capability_id not in registry:
        return ChatControlsResult(
            capability_id=capability_id,
            manifest_version="",
            controls=[],
            error=f"capability {capability_id!r} is not installed on this pod",
        )
    capability = registry.capability(capability_id)
    version = capability.manifest.version
    slice_ = config_envelope
    if slice_ is None:
        slice_ = StoredCapabilityConfig(schema_version=version, config={})
    try:
        config = resolve_stored_config(capability, slice_)
        controls = [
            ChatControlItem.from_spec(s) for s in capability.chat_controls(config)
        ]
    except CapabilityConfigInvalidError as exc:
        return ChatControlsResult(
            capability_id=capability_id,
            manifest_version=version,
            controls=[],
            error=str(exc),
        )
    return ChatControlsResult(
        capability_id=capability_id, manifest_version=version, controls=controls
    )


def evaluate_chat_controls_batch(
    registry: CapabilityRegistry, request: ChatControlsRequest
) -> ChatControlsResponse:
    """
    Evaluate a batch of capabilities' chat controls in one round-trip (#1976).

    One `ChatControlsResult` per requested item, order-preserving. This is the
    pod side of `POST /agents/capabilities/chat-controls`; control-plane sends
    only the cache-MISSED capabilities and merges the results with its cached
    entries (RFC §3.7 cache-aside).
    """

    return ChatControlsResponse(
        results=[
            evaluate_capability_chat_controls(
                registry,
                capability_id=item.capability_id,
                config_envelope=item.config_envelope,
            )
            for item in request.items
        ]
    )


def validate_turn_options(
    registry: CapabilityRegistry,
    *,
    selected_capability_ids: list[str] | None,
    turn_options: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    """
    Validate a request's `turn_options` envelope at turn start (#1976, RFC §3.5).

    Every key must be a capability the instance selected AND the pod has
    installed, and every slice must validate against that capability's
    `TurnOptionsModel`. A violation raises `TurnOptionsInvalidError`, mapped by
    the HTTP layer to a typed 422 before streaming — the same style as
    `validate_config`. An empty / absent envelope is valid (no chat controls
    engaged this turn).
    """

    if not turn_options:
        return
    selected = set(selected_capability_ids or [])
    for cap_id, slice_ in turn_options.items():
        if cap_id not in selected or cap_id not in registry:
            raise TurnOptionsInvalidError(
                f"turn_options references capability {cap_id!r}, which this "
                "agent instance did not select or this pod does not have "
                "installed."
            )
        capability = registry.capability(cap_id)
        try:
            _validated_slice(capability.TurnOptionsModel, slice_)
        except ValidationError as exc:
            raise TurnOptionsInvalidError(
                f"turn_options[{cap_id!r}] is not valid for capability "
                f"{cap_id!r} (RFC §3.5): {exc}"
            ) from exc


def build_capability_contexts(
    registry: CapabilityRegistry,
    *,
    selected_capability_ids: list[str] | None,
    capability_config: Mapping[str, StoredCapabilityConfig | Mapping[str, Any]],
    identity: CapabilityIdentity,
    services: RuntimeServices,
    turn_options: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, CapabilityContext[Any, Any]]:
    """
    Turn one agent's tuning-level capability selection into the typed
    per-capability contexts the agent block consumes (#1974, RFC §3.8).

    Selection semantics mirror the tuning contract: `None` means template
    default (no template declares default capabilities yet, so none), `[]`
    means none, a non-empty list means exactly that set. Unknown ids raise
    `UnknownCapabilityError`; a selected capability without a persisted slice
    gets its `StoredConfigModel` defaults.
    """

    contexts: dict[str, CapabilityContext[Any, Any]] = {}
    options = turn_options or {}
    for cap_id in selected_capability_ids or []:
        capability = registry.capability(cap_id)
        slice_ = capability_config.get(cap_id)
        if slice_ is None:
            # No persisted slice: StoredConfigModel defaults at the installed
            # version (still through the named-error path).
            slice_ = StoredCapabilityConfig(
                schema_version=capability.manifest.version, config={}
            )
        config = resolve_stored_config(capability, slice_)
        contexts[cap_id] = build_capability_context(
            capability,
            identity=identity,
            services=services,
            config=config,
            turn_options=options.get(cap_id),
        )
    return contexts


def build_capability_context(
    capability: AgentCapability[Any, Any, Any],
    *,
    identity: CapabilityIdentity,
    services: RuntimeServices,
    config: BaseModel | Mapping[str, Any] | None = None,
    turn_options: BaseModel | Mapping[str, Any] | None = None,
    team_settings: BaseModel | Mapping[str, Any] | None = None,
) -> CapabilityContext[Any, Any]:
    """
    Build one capability's typed context from raw slices (RFC §3.5, §3.8).

    Each slice is validated against THAT capability's models
    (`StoredConfigModel`, `TurnOptionsModel`, `TeamSettingsModel`) — inside a
    capability everything is statically typed; only this loop is generic.
    Invalid slices raise `pydantic.ValidationError` for the caller to map to
    its typed 422 / suspension handling (RFC §3.9).
    """

    return CapabilityContext(
        identity=identity,
        config=_validated_slice(capability.StoredConfigModel, config),
        turn_options=_validated_slice(capability.TurnOptionsModel, turn_options),
        team_settings=_validated_slice(capability.TeamSettingsModel, team_settings),
        services=services,
    )


@dataclass(frozen=True)
class CapabilityAgentBlock:
    """What one agent's selected capabilities contribute to the frame."""

    middleware: tuple[AgentMiddleware, ...]
    hitl: Mapping[str, CapabilityHitlBinding]


def build_capability_agent_block(
    registry: CapabilityRegistry,
    contexts: Mapping[str, CapabilityContext[Any, Any]],
) -> CapabilityAgentBlock:
    """
    Assemble the selected capabilities into the frame's capability block.

    Determinism rule (RFC §5.3): iteration is `sorted(capability id)` — never
    selection order, never registration order — and each capability's
    authored middleware list order is preserved within its block.
    """

    middleware: list[AgentMiddleware] = []
    hitl: dict[str, CapabilityHitlBinding] = {}
    for cap_id in sorted(contexts):
        capability = registry.capability(cap_id)
        ctx = contexts[cap_id]
        stack = list(capability.middleware(ctx))
        middleware.extend(stack)

        tools_by_name: dict[str, Any] = {}
        for mw in stack:
            for candidate in getattr(mw, "tools", None) or []:
                candidate_name = getattr(candidate, "name", None)
                if isinstance(candidate_name, str):
                    tools_by_name[candidate_name] = candidate

        for spec in capability.hitl_specs():
            owner = hitl.get(spec.tool)
            if owner is not None:
                raise CapabilityAssemblyError(
                    f"Tool '{spec.tool}' has HitlSpec declarations from two "
                    f"capabilities (capability '{cap_id}' collides with an "
                    "earlier one). Capability tools must be uniquely named."
                )
            hitl[spec.tool] = CapabilityHitlBinding(
                spec=spec,
                context=ctx,
                tool=tools_by_name.get(spec.tool),
            )
    return CapabilityAgentBlock(middleware=tuple(middleware), hitl=hitl)
