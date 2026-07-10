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
Capability runtime context — the typed runtime/LLM split (#1973, RFC §3.5).

Why this module exists:
- capability tools receive ONLY LLM arguments in their signatures; identity,
  config, chat-time options, and platform services reach the capability
  through these context objects (closed over by the capability's middleware),
  never through the tool schema the model sees
- inside a capability everything is statically typed: each capability gets a
  `CapabilityContext[StoredT, TurnOptionsT]` carrying only its own typed
  slices — only the assembly loop is generic

How to use:
- the runtime builds one `CapabilityContext` per selected capability at
  agent-assembly time and passes it to `AgentCapability.middleware(ctx)`
- `SaveContext` is the agent-save-time counterpart passed to
  `AgentCapability.validate_config`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from ..runtime import RuntimeServices


class EmptyModel(BaseModel):
    """
    Explicit "no fields" model.

    Why this exists:
    - `TurnOptionsModel` and `TeamSettingsModel` default to this when a
      capability has no chat-time options or team settings (RFC §3.2), keeping
      every slice typed instead of `None`-guarded
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class CapabilityIdentity(BaseModel):
    """
    Who and where one capability invocation runs for (RFC §3.5 `identity`).

    Why this exists:
    - capabilities need the acting user/session/team/agent-instance without
      depending on the full platform `RuntimeContext`; this is the minimal
      identity slice the RFC names
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    session_id: str | None = None
    team_id: str | None = None
    agent_instance_id: str | None = None


StoredT = TypeVar("StoredT", bound=BaseModel)
TurnOptionsT = TypeVar("TurnOptionsT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class SaveContext:
    """
    Agent-save-time context for `AgentCapability.validate_config` (RFC §3.2).

    How to use:
    - `services` carries the ports a save-time transform may need (e.g. the KF
      workspace client to store uploaded asset binaries, RFC §3.8)
    """

    identity: CapabilityIdentity
    services: RuntimeServices


@dataclass(frozen=True)
class CapabilityContext(Generic[StoredT, TurnOptionsT]):
    """
    Per-capability, per-turn typed context (RFC §3.5).

    Why this exists:
    - this is the "don't mix runtime info with LLM-exposed params" requirement,
      formalized: the middleware closure carries this object; the tool schema
      exposed to the model never does

    Fields:
    - `config`: this capability's typed stored config slice (RFC §3.8)
    - `turn_options`: this capability's typed chat-time values (RFC §3.5)
    - `team_settings`: typed per-team enablement settings (RFC §8.2);
      `EmptyModel` until Tier 3
    - `services`: platform ports (KF client, workspace fs, model factory, ...)
    """

    identity: CapabilityIdentity
    config: StoredT
    turn_options: TurnOptionsT
    services: RuntimeServices
    team_settings: BaseModel = field(default_factory=EmptyModel)
