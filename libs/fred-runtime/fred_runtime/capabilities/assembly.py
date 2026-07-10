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
)
from fred_sdk.contracts.runtime import RuntimeServices
from langchain.agents.middleware import AgentMiddleware
from pydantic import BaseModel

from fred_runtime.react.middleware.hitl import CapabilityHitlBinding

from .errors import CapabilityAssemblyError
from .registry import CapabilityRegistry


def _validated_slice(
    model: type[BaseModel], value: BaseModel | Mapping[str, Any] | None
) -> BaseModel:
    """Validate one raw config/options slice against a capability's typed model."""

    if isinstance(value, BaseModel):
        return model.model_validate(value.model_dump())
    return model.model_validate(dict(value) if value is not None else {})


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
