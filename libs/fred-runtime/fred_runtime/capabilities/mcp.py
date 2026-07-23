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
  pre-registered capability instance whose id IS the catalog server id (#1988),
  so MCP servers, built-ins, and full-vertical capabilities live in ONE
  registry, ONE product contract, and ONE team-gating model (the "one Tools
  tab"). This retires the `ManagedAgentTuning`/`AgentTuning` MCP trio
  (`mcp_servers`, `selected_mcp_server_ids`, `mcp_config_values`).

Contained Tier-1 shape (does NOT touch the execution loop):
- an `McpCapability` does NOT itself load MCP tools. Live MCP tool loading stays
  in `FredMcpToolProvider`, driven by `definition.default_mcp_servers` — which
  agent assembly derives from the selected capability ids that resolve to
  `McpCapability` registry entries (see `fred_runtime.app.agent_app`).
- the capability's ONLY runtime contribution is a prompt-fragment middleware
  carrying the catalog server's `agent_instructions` (RFC §3.8 AC4), delivered
  through `awrap_model_call` exactly like `DynamicPromptMiddleware`.

How to use:
- `register_mcp_capabilities(registry, servers)` at pod boot registers one
  instance per enabled catalog server (`boot_capability_registry` calls it).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any, Literal

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    ChatControlSpec,
    EmptyModel,
)

__all__ = [
    "MCP_CAPABILITY_SCHEMA_VERSION",
    "McpCapability",
    "McpServerConfig",
    "build_mcp_capability",
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

_MCP_CAPABILITY_ICON = "extension"

# Dotted `chat_options.*` config keys an MCP catalog server may declare — the
# same keys `_resolve_effective_chat_options` read control-plane-side before
# #1976 moved chat-option resolution to computed `chat_controls` (RFC §3.3).
_OPT_ATTACH_FILES = "chat_options.attach_files"
_OPT_LIBRARIES_BINDING = "chat_options.libraries_binding"
_OPT_BOUND_LIBRARY_IDS = "chat_options.bound_library_ids"
_OPT_LIBRARIES_SELECTION = "chat_options.libraries_selection"
_OPT_DOCUMENTS_SELECTION = "chat_options.documents_selection"
_OPT_SEARCH_POLICY_ENABLED = "chat_options.search_policy_enabled"
_OPT_SEARCH_POLICY = "chat_options.search_policy"
_OPT_RAG_SCOPE_ENABLED = "chat_options.search_rag_scope_enabled"
_OPT_RAG_SCOPE = "chat_options.search_rag_scope"

_SEARCH_POLICIES = frozenset({"strict", "hybrid", "semantic"})
_RAG_SCOPES = frozenset({"corpus_only", "hybrid", "general_only"})

SearchPolicyName = Literal["strict", "hybrid", "semantic"]
RagScopeName = Literal["corpus_only", "hybrid", "general_only"]


def _as_bool(value: object) -> bool:
    """Strict boolean view of one stored config value (literal True only)."""

    return isinstance(value, bool) and value


class DocumentScopeControlParams(BaseModel):
    """
    Params for the `document_scope` composer widget (#1976, RFC §3.3).

    Reproduces the retired `EffectiveChatOptions` library/document affordance:
    the picker shows libraries and/or documents, and `bound_library_ids` (when
    set) pins the selection read-only — exactly the old `bound_library_ids`
    semantics, now carried as widget params.
    """

    libraries: bool = False
    documents: bool = False
    bound_library_ids: list[str] | None = None


class SearchPolicyControlParams(BaseModel):
    """Params for the `search_policy` enum-row widget: its default value."""

    default: SearchPolicyName = "hybrid"


class RagScopeControlParams(BaseModel):
    """Params for the `rag_scope` enum-row widget: its default value."""

    default: RagScopeName = "hybrid"


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

    def __init__(self, fragment: str, *, server_id: str) -> None:
        super().__init__()
        self._fragment = fragment
        self._server_id = server_id

    @property
    def name(self) -> str:
        # Unique per MCP server. An agent may select several MCP capabilities,
        # each contributing one of these instances; `create_agent` rejects a
        # middleware list with duplicate `.name`s ("Please remove duplicate
        # middleware instances."), and the base default is the shared class
        # name. Keying on the catalog server id keeps every instance distinct.
        return f"McpInstructions[{self._server_id}]"

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

    def chat_controls(self, config: McpServerConfig) -> list[ChatControlSpec]:
        """
        Compute this MCP server's chat-time composer controls (#1976, RFC §3.3).

        This is the durable move #1978 deferred: the per-server chat-option
        resolution that used to run control-plane-side in
        `_resolve_effective_chat_options` (reading `chat_options.*` slices +
        pod-advertised defaults) now runs HERE, where the capability owns its
        config and its declared defaults (`self._server.config_fields`) — no
        pod-reachability-at-read-time dependency. It emits STOCK composer widget
        ids the frontend kit renders; the chosen search values still travel on
        `RuntimeContext` (Group C), so this restores visibility/defaults/bound
        ids without rebuilding the bespoke interlocking #1978 dropped.

        Cross-server merge (multiple MCP capabilities active) is the composer
        host's job: at most one control per widget id, first-wins in
        (registration, list) order — the same "OR / first-wins" outcome the old
        accumulation produced.
        """

        defaults = {field.key: field.default for field in self._server.config_fields}
        stored = config.model_dump()

        def value(key: str) -> Any:
            return stored.get(key, defaults.get(key))

        controls: list[ChatControlSpec] = []
        binding_enabled = _as_bool(value(_OPT_LIBRARIES_BINDING))

        if _as_bool(value(_OPT_ATTACH_FILES)):
            controls.append(ChatControlSpec(widget="attach_files"))

        show_libraries = (not binding_enabled) and _as_bool(
            value(_OPT_LIBRARIES_SELECTION)
        )
        show_documents = _as_bool(value(_OPT_DOCUMENTS_SELECTION))
        raw_bound = value(_OPT_BOUND_LIBRARY_IDS) if binding_enabled else None
        bound_ids = [str(v) for v in raw_bound] if isinstance(raw_bound, list) else None
        if show_libraries or show_documents or bound_ids:
            controls.append(
                ChatControlSpec(
                    widget="document_scope",
                    params=DocumentScopeControlParams(
                        libraries=show_libraries or bool(bound_ids),
                        documents=show_documents,
                        bound_library_ids=bound_ids,
                    ),
                )
            )

        if _as_bool(value(_OPT_SEARCH_POLICY_ENABLED)):
            policy = value(_OPT_SEARCH_POLICY)
            policy_params = (
                SearchPolicyControlParams(default=policy)
                if policy in _SEARCH_POLICIES
                else SearchPolicyControlParams()
            )
            controls.append(
                ChatControlSpec(widget="search_policy", params=policy_params)
            )

        if _as_bool(value(_OPT_RAG_SCOPE_ENABLED)):
            scope = value(_OPT_RAG_SCOPE)
            scope_params = (
                RagScopeControlParams(default=scope)
                if scope in _RAG_SCOPES
                else RagScopeControlParams()
            )
            controls.append(ChatControlSpec(widget="rag_scope", params=scope_params))

        return controls

    def middleware(
        self, ctx: CapabilityContext[McpServerConfig, EmptyModel]
    ) -> Sequence[AgentMiddleware]:
        del ctx
        fragment = (self._server.agent_instructions or "").strip()
        if not fragment:
            return []
        return [_McpInstructionsMiddleware(fragment, server_id=self._server.id)]


def build_mcp_capability(server: MCPServerConfiguration) -> McpCapability:
    """
    Build one `McpCapability` instance for a catalog MCP server.

    The manifest is server-specific, so a dynamic subclass carries it (the SDK
    declares `manifest`/`ConfigModel` as `ClassVar`s). `name`/`description` are
    already i18n keys on `MCPServerConfiguration`. The capability id IS the
    catalog server id, and `team_scope` comes from the catalog entry
    (`admin_gated` unless the yaml opts into `default_on`) — MCP servers are
    team-gated like every other capability (#1988).
    """

    manifest = CapabilityManifest(
        id=server.id,
        version=MCP_CAPABILITY_SCHEMA_VERSION,
        name=server.name,
        description=server.description or server.name,
        icon=_MCP_CAPABILITY_ICON,
        config_fields=[field.model_copy(deep=True) for field in server.config_fields],
        team_scope=server.team_scope,
    )
    attributes: dict[str, Any] = {"manifest": manifest, "_server": server}
    subclass = type(f"McpCapability_{server.id}", (McpCapability,), attributes)
    return subclass()


def register_mcp_capabilities(
    registry: "CapabilityRegistry", servers: Iterable[MCPServerConfiguration]
) -> list[str]:
    """
    Register one capability per ENABLED catalog server (#1978, #1988).

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
