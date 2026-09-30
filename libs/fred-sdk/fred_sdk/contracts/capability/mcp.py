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

"""MCP capability construction and composer controls for catalog-backed servers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityManifest,
    ChatControlSpec,
    EmptyModel,
)
from fred_sdk.contracts.models import (
    DocumentScopeControlParams,
    MCPServerConfiguration,
    RagScopeControlParams,
    SearchPolicyControlParams,
)

__all__ = [
    "MCP_CAPABILITY_SCHEMA_VERSION",
    "McpCapability",
    "McpPromptGroup",
    "McpServerConfig",
    "build_mcp_capability",
    "register_mcp_capabilities",
]


class _McpCapabilityRegistry(Protocol):
    """Structural registration port; SDK builders do not import the runtime."""

    def register(self, capability: McpCapability) -> str: ...


# Moving the authoring code does not change persisted MCP configuration.
MCP_CAPABILITY_SCHEMA_VERSION = "1"

_MCP_CAPABILITY_ICON = "extension"

# Dotted keys remain compatible with existing stored MCP configurations.
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


def _as_bool(value: object) -> bool:
    """Strict boolean view of one stored config value (literal True only)."""

    return isinstance(value, bool) and value


class McpServerConfig(BaseModel):
    """Open bag of catalog-defined keys, including dotted chat_options settings."""

    model_config = ConfigDict(extra="allow")


@dataclass(frozen=True, slots=True)
class McpPromptGroup:
    """One server’s title and instructions, rendered beside its tool group."""

    server_id: str
    title: str
    agent_instructions: str | None


class McpCapability(AgentCapability[McpServerConfig, McpServerConfig, EmptyModel]):
    """Catalog-backed capability; use build_mcp_capability to bind server metadata."""

    ConfigModel = McpServerConfig

    # Per-server catalog entry, set on the dynamic subclass by
    # `build_mcp_capability`. Declared here for typing only.
    _server: MCPServerConfiguration

    def chat_controls(self, config: McpServerConfig) -> list[ChatControlSpec]:
        """Compute stock composer controls from stored values and catalog defaults."""

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

    def prompt_group(self) -> McpPromptGroup:
        """Return grouping metadata for this server’s static tool prompt."""

        agent_instructions = (self._server.agent_instructions or "").strip() or None
        return McpPromptGroup(
            server_id=self._server.id,
            title=self._server.prompt_group_title or self._server.id,
            agent_instructions=agent_instructions,
        )


def build_mcp_capability(server: MCPServerConfiguration) -> McpCapability:
    """Build a server-specific class so its manifest follows the SDK ClassVar contract."""

    manifest = CapabilityManifest(
        id=server.id,
        version=MCP_CAPABILITY_SCHEMA_VERSION,
        # The stored-config schema version is not a public server release.
        public_version=None,
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
    registry: _McpCapabilityRegistry, servers: Iterable[MCPServerConfiguration]
) -> list[str]:
    """Register enabled servers at boot; the registry rejects duplicate IDs."""

    registered: list[str] = []
    for server in servers:
        if not server.enabled:
            continue
        registered.append(registry.register(build_mcp_capability(server)))
    return registered
