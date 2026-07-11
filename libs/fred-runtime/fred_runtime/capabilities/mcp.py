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
`McpCapability` — an MCP server surfaced as an `AgentCapability`
(#1978, RFC AGENT-CAPABILITY-RFC.md §3.8, §6 Tier 1).

Why this module exists:
- MCP stops being special. Every `mcp_catalog.yaml` entry becomes a
  pre-registered `mcp:<server>` capability instance, so MCP servers, built-ins,
  and full-vertical capabilities live in ONE registry and ONE product contract
  (the "one Tools tab"). This retires the `ManagedAgentTuning`/`AgentTuning` MCP
  trio (`mcp_servers`, `selected_mcp_server_ids`, `mcp_config_values`).

Contained Tier-1 shape (does NOT touch the execution loop):
- an `McpCapability` does NOT itself load MCP tools. Live MCP tool loading stays
  in `FredMcpToolProvider`, driven by `definition.default_mcp_servers` — which
  agent assembly derives from the `mcp:<id>` entries of `selected_capability_ids`
  (see `fred_runtime.app.agent_app`).
- the capability's ONLY runtime contribution is a prompt-fragment middleware
  carrying the catalog server's `agent_instructions` (RFC §3.8 AC4), delivered
  through `awrap_model_call` exactly like `DynamicPromptMiddleware`.

How to use:
- `register_mcp_capabilities(registry, servers)` at pod boot registers one
  instance per enabled catalog server (`boot_capability_registry` calls it).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any

from fred_sdk.contracts.capability import (
    MCP_CAPABILITY_PREFIX,
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    TeamScopePolicy,
    is_mcp_capability_id,
    mcp_capability_id,
    mcp_server_id_of,
)

# Re-exported (the `mcp:<server>` id contract lives in fred-sdk so control-plane
# shares it) so callers can keep importing them from the runtime capability
# package.
__all__ = [
    "MCP_CAPABILITY_PREFIX",
    "MCP_CAPABILITY_SCHEMA_VERSION",
    "McpCapability",
    "McpServerConfig",
    "build_mcp_capability",
    "is_mcp_capability_id",
    "mcp_capability_id",
    "mcp_server_id_of",
    "register_mcp_capabilities",
]
from fred_sdk.contracts.models import MCPServerConfiguration
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from .registry import CapabilityRegistry

# Stored-config schema version for MCP capabilities. The config is a permissive
# key/value bag (below) that the runtime does not consume, so it never needs a
# real `upgrade_config` — a stable version is enough.
MCP_CAPABILITY_SCHEMA_VERSION = "1"

_MCP_CAPABILITY_ICON = "Extension"


class McpServerConfig(BaseModel):
    """
    The agent-creation / stored config of one MCP-server capability.

    MCP servers declare arbitrary, dotted `config_fields` keys in the catalog
    (e.g. `chat_options.attach_files`). Pydantic cannot declare dotted field
    names, so this stays a permissive bag: it round-trips whatever the catalog
    declared, verbatim. The values are stored (control-plane persists the
    pod-validated envelope) but NOT consumed by the runtime — chat-option
    resolution reads them control-plane-side (RFC §3.3 retirement is a sibling
    ticket).
    """

    model_config = ConfigDict(extra="allow")


class _McpInstructionsMiddleware(AgentMiddleware):
    """
    Append one MCP server's non-negotiable `agent_instructions` to the system
    prompt (the prompt-fragment delivery path, #1978 AC4).

    Mirrors `DynamicPromptMiddleware`: the static composed system prompt reaches
    `create_agent`; this middleware overlays the capability fragment per model
    call so it survives across turns without being persisted.
    """

    def __init__(self, fragment: str) -> None:
        super().__init__()
        self._fragment = fragment

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        base = request.system_prompt or ""
        merged = f"{base}\n\n{self._fragment}" if base else self._fragment
        request = request.override(system_message=SystemMessage(content=merged))
        return await handler(request)


class McpCapability(AgentCapability[McpServerConfig, McpServerConfig, EmptyModel]):
    """
    Base class for a catalog MCP server surfaced as a capability (#1978).

    Concrete per-server capabilities are built by `build_mcp_capability`, which
    creates a dynamic subclass carrying that server's `manifest` and `_server`.
    This keeps the SDK `ClassVar` contract honest (one manifest per class) while
    the catalog stays the single source of MCP metadata.
    """

    ConfigModel = McpServerConfig

    # Per-server catalog entry, set on the dynamic subclass by
    # `build_mcp_capability`. Declared here for typing only.
    _server: MCPServerConfiguration

    def middleware(
        self, ctx: CapabilityContext[McpServerConfig, EmptyModel]
    ) -> Sequence[AgentMiddleware]:
        del ctx
        fragment = (self._server.agent_instructions or "").strip()
        if not fragment:
            return []
        return [_McpInstructionsMiddleware(fragment)]


def build_mcp_capability(server: MCPServerConfiguration) -> McpCapability:
    """
    Build one `McpCapability` instance for a catalog MCP server.

    The manifest is server-specific, so a dynamic subclass carries it (the SDK
    declares `manifest`/`ConfigModel` as `ClassVar`s). `name`/`description` are
    already i18n keys on `MCPServerConfiguration`; `team_scope` is `DEFAULT_ON`
    to preserve today's behaviour (MCP servers were never admin-gated —
    per-team gating is Tier 3).
    """

    manifest = CapabilityManifest(
        id=mcp_capability_id(server.id),
        version=MCP_CAPABILITY_SCHEMA_VERSION,
        name=server.name,
        description=server.description or server.name,
        icon=_MCP_CAPABILITY_ICON,
        config_fields=[field.model_copy(deep=True) for field in server.config_fields],
        team_scope=TeamScopePolicy.DEFAULT_ON,
    )
    attributes: dict[str, Any] = {"manifest": manifest, "_server": server}
    subclass = type(f"McpCapability_{server.id}", (McpCapability,), attributes)
    return subclass()


def register_mcp_capabilities(
    registry: "CapabilityRegistry", servers: Iterable[MCPServerConfiguration]
) -> list[str]:
    """
    Register one `mcp:<server>` capability per ENABLED catalog server (#1978).

    Called from `boot_capability_registry` between entry-point discovery and
    boot validation, so a catalog id colliding with an installed capability id
    still fails startup loudly (`DuplicateCapabilityIdError`).
    """

    registered: list[str] = []
    for server in servers:
        if not server.enabled:
            continue
        registered.append(registry.register(build_mcp_capability(server)))
    return registered
