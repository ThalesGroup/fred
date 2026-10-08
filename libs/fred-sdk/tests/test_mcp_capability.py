# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""MCP authoring behavior belongs to the SDK and needs no runtime import."""

from fred_sdk.contracts.capability.mcp import (
    McpCapability,
    McpServerConfig,
    build_mcp_capability,
    register_mcp_capabilities,
)
from fred_sdk.contracts.models import FieldSpec, MCPServerConfiguration, TeamScopePolicy


def test_mcp_metadata_and_config_defaults() -> None:
    server = MCPServerConfiguration.model_validate(
        {
            "id": "search",
            "name": "Search",
            "team_scope": TeamScopePolicy.DEFAULT_ON,
            "prompt_group_title": "Corpus",
            "agent_instructions": "  Cite evidence.\n",
            "config_fields": [
                FieldSpec(
                    key="chat_options.attach_files",
                    type="boolean",
                    title="Attach files",
                    default=True,
                )
            ],
        }
    )
    capability = build_mcp_capability(server)
    assert isinstance(capability, McpCapability)
    assert capability.manifest.id == "search"
    assert capability.manifest.team_scope is TeamScopePolicy.DEFAULT_ON
    assert capability.manifest.public_version is None
    assert capability.manifest.config_fields == server.config_fields
    assert capability.manifest.config_fields[0] is not server.config_fields[0]
    assert capability.prompt_group().title == "Corpus"
    assert capability.prompt_group().agent_instructions == "Cite evidence."
    assert [
        control.widget for control in capability.chat_controls(McpServerConfig())
    ] == ["attach_files"]
    assert (
        capability.chat_controls(
            McpServerConfig.model_validate({"chat_options.attach_files": False})
        )
        == []
    )


def test_mcp_stored_controls_and_registration() -> None:
    server = MCPServerConfiguration.model_validate({"id": "search", "name": "Search"})
    capability = build_mcp_capability(server)
    config = McpServerConfig.model_validate(
        {
            "chat_options.libraries_binding": True,
            "chat_options.libraries_selection": True,
            "chat_options.bound_library_ids": ["library-a"],
            "chat_options.documents_selection": True,
            "chat_options.search_policy_enabled": True,
            "chat_options.search_policy": "strict",
            "chat_options.search_rag_scope_enabled": True,
            "chat_options.search_rag_scope": "corpus_only",
        }
    )
    controls = {
        control.widget: control.params.model_dump()
        for control in capability.chat_controls(config)
        if control.params is not None
    }
    assert controls["document_scope"] == {
        "libraries": True,
        "documents": True,
        "bound_library_ids": ["library-a"],
    }
    assert controls["search_policy"] == {"default": "strict"}
    assert controls["rag_scope"] == {"default": "corpus_only", "options": None}

    class Registry:
        def __init__(self) -> None:
            self.registered: list[McpCapability] = []

        def register(self, capability: McpCapability) -> str:
            self.registered.append(capability)
            return capability.manifest.id

    registry = Registry()
    assert register_mcp_capabilities(
        registry,
        [
            server,
            MCPServerConfiguration.model_validate(
                {"id": "off", "name": "Off", "enabled": False}
            ),
        ],
    ) == ["search"]
    assert len(registry.registered) == 1
