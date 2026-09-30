# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Installed MCP catalog provider, built entirely on fred-sdk."""

from fred_sdk.contracts.services import ServiceEndpointsPort
from fred_sdk.resources.mcp import McpCatalog, load_packaged_mcp_catalog


def load_catalog(services: ServiceEndpointsPort) -> McpCatalog:
    """Load the MCP servers provided by Fred."""
    return load_packaged_mcp_catalog(
        package=__name__, path_parts=("mcp_catalog.yaml",), services=services
    )
