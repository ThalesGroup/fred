# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Compatibility imports; MCP capability authoring now lives in fred-sdk."""

from fred_sdk.contracts.capability.mcp import (
    MCP_CAPABILITY_SCHEMA_VERSION,
    McpCapability,
    McpPromptGroup,
    McpServerConfig,
    build_mcp_capability,
    register_mcp_capabilities,
)

__all__ = [
    "MCP_CAPABILITY_SCHEMA_VERSION",
    "McpCapability",
    "McpPromptGroup",
    "McpServerConfig",
    "build_mcp_capability",
    "register_mcp_capabilities",
]
