"""
Offline unit tests for McpCatalogConfiguration and AgentPodConfig MCP wiring.

Ref: docs/backlog/BACKLOG.md §3d (C1) — MCP catalog loading, duplicate detection,
     tri-state server selection (null=inherit, []=none, list=exact subset).
"""

from __future__ import annotations

import pytest

from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.mcp_config import McpCatalogConfiguration, McpServerEntry


def test_mcp_catalog_configuration_parses_empty_servers() -> None:
    """McpCatalogConfiguration defaults to an empty server list."""
    config = McpCatalogConfiguration()
    assert config.servers == []


def test_mcp_catalog_configuration_parses_server_entry() -> None:
    """McpServerEntry must round-trip through model_validate."""
    raw = {
        "servers": [
            {
                "name": "my-mcp",
                "url": "http://localhost:9090/mcp",
                "transport": "sse",
                "description": "test server",
            }
        ]
    }
    config = McpCatalogConfiguration.model_validate(raw)
    assert len(config.servers) == 1
    entry = config.servers[0]
    assert isinstance(entry, McpServerEntry)
    assert entry.name == "my-mcp"
    assert entry.url == "http://localhost:9090/mcp"
    assert entry.transport == "sse"
    assert entry.description == "test server"


def test_mcp_catalog_configuration_allows_extra_fields() -> None:
    """Extra fields on both catalog and server entry must not raise validation errors."""
    raw = {
        "servers": [
            {
                "name": "srv",
                "url": "http://localhost/mcp",
                "extra_server_field": "ignored",
            }
        ],
        "extra_catalog_field": True,
    }
    config = McpCatalogConfiguration.model_validate(raw)
    assert len(config.servers) == 1
    assert config.servers[0].name == "srv"


def test_agent_pod_config_set_and_get_mcp_configuration_roundtrip(
    minimal_config: AgentPodConfig,
) -> None:
    """set_mcp_configuration / get_mcp_configuration must be an exact roundtrip."""
    from fred_runtime.app._catalogs import _LoadedMcpConfiguration

    mcp = _LoadedMcpConfiguration()
    minimal_config.set_mcp_configuration(mcp)
    assert minimal_config.get_mcp_configuration() is mcp


def test_agent_pod_config_mcp_configuration_defaults_to_none(
    minimal_config: AgentPodConfig,
) -> None:
    """get_mcp_configuration() must return None before set_mcp_configuration is called."""
    assert minimal_config.get_mcp_configuration() is None


def test_load_mcp_catalog_rejects_duplicate_server_ids(tmp_path) -> None:
    """The external MCP catalog must fail fast when two servers share one id."""
    from fred_runtime.app._catalogs import load_mcp_catalog

    catalog_path = tmp_path / "mcp_catalog.yaml"
    catalog_path.write_text(
        """
version: v1
servers:
  - id: "dup"
    name: "First"
    transport: "streamable_http"
    url: "http://localhost:8111/one"
  - id: "dup"
    name: "Second"
    transport: "streamable_http"
    url: "http://localhost:8111/two"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate MCP server id"):
        load_mcp_catalog(catalog_path)
