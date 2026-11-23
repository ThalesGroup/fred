# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Native Tabular capability, using Knowledge Flow through trusted admission."""

from fred_sdk.authoring.knowledge_flow_mcp import MCP_SERVER_KNOWLEDGE_FLOW_TABULAR
from fred_sdk.contracts.capability import CapabilityManifest
from fred_sdk.contracts.capability.mcp import (
    McpCapability,
    McpPromptGroup,
    McpServerConfig,
)
from fred_sdk.contracts.capability.scope import ScopePrivate
from fred_sdk.contracts.models import FieldSpec, UIHints
from fred_sdk.resources.prompts import load_packaged_markdown
from pydantic import ConfigDict, Field


class TabularConfig(McpServerConfig):
    model_config = ConfigDict(extra="allow", serialize_by_alias=True)

    libraries_binding: bool = Field(
        default=False, alias="chat_options.libraries_binding", strict=True
    )
    bound_library_ids: ScopePrivate[list[str]] = Field(
        default_factory=list, alias="chat_options.bound_library_ids"
    )


class TabularCapability(McpCapability):
    ConfigModel = TabularConfig
    StoredConfigModel = TabularConfig

    manifest = CapabilityManifest(
        id=MCP_SERVER_KNOWLEDGE_FLOW_TABULAR,
        version="1",
        public_version=None,
        name="mcp.servers.tabular.name",
        description="mcp.servers.tabular.description",
        icon="extension",
        config_fields=[
            FieldSpec(
                key="chat_options.libraries_binding",
                type="boolean",
                title="mcp.servers.tabular.libraryBinding.title",
                description="mcp.servers.tabular.libraryBinding.description",
                default=False,
            ),
            FieldSpec(
                key="chat_options.bound_library_ids",
                type="array",
                item_type="string",
                title="capability.document_access.fields.library_tag_ids.title",
                description="capability.document_access.fields.library_tag_ids.description",
                default=[],
                scope_private=True,
                ui=UIHints(
                    widget="document_libraries",
                    visible_when="chat_options.libraries_binding",
                ),
            ),
            FieldSpec(
                key="chat_options.libraries_selection",
                type="boolean",
                title="capability.document_access.fields.show_library_selection.title",
                default=True,
                ui=UIHints(advanced=True),
            ),
            FieldSpec(
                key="chat_options.documents_selection",
                type="boolean",
                title="capability.document_access.fields.show_document_selection.title",
                default=True,
                ui=UIHints(advanced=True),
            ),
        ],
    )

    def validate_export(self, stored: McpServerConfig) -> None:
        config = TabularConfig.model_validate(stored.model_dump())
        if config.libraries_binding:
            raise ValueError(
                "This agent is bound to a source corpus. Remove its Tabular "
                "library binding before proposing it to the marketplace."
            )

    def prompt_group(self) -> McpPromptGroup:
        return McpPromptGroup(
            server_id=self.manifest.id,
            title="tabular action",
            agent_instructions=load_packaged_markdown(
                package=__name__, path_parts=("prompts", "tabular.md")
            ),
        )
