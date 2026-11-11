# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Tabular business contribution. Connections and publication belong to Control Plane."""

from fred_sdk.authoring.knowledge_flow_mcp import MCP_SERVER_KNOWLEDGE_FLOW_TABULAR
from fred_sdk.contracts.capability import CapabilityManifest
from fred_sdk.contracts.capability.mcp import McpCapability, McpPromptGroup
from fred_sdk.resources.prompts import load_packaged_markdown


class TabularCapability(McpCapability):
    manifest = CapabilityManifest(
        id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
        version="1",
        public_version=None,
        name="mcp.servers.tabular.name",
        description="mcp.servers.tabular.description",
        icon="extension",
        mcp_service="knowledge_flow_tabular",
    )

    def prompt_group(self) -> McpPromptGroup:
        return McpPromptGroup(
            server_id=self.manifest.id,
            title="tabular action",
            agent_instructions=load_packaged_markdown(
                package=__package__, path_parts=("prompts", "tabular.md")
            ),
        )
