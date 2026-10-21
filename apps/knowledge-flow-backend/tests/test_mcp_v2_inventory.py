"""Knowledge Flow MCP v2 keeps the v1 tool catalog and callable schemas."""

import json
from pathlib import Path

import pytest
from fred_pod.common.structures import PostgresTableConfig

from knowledge_flow_backend import main as main_module
from knowledge_flow_backend.application_context import ApplicationContext


def _semantic_schema(value):
    if isinstance(value, list):
        return [_semantic_schema(item) for item in value]
    if isinstance(value, dict):
        result = {key: _semantic_schema(item) for key, item in value.items() if key != "title" and not (key == "required" and item == [])}
        if "anyOf" in result:
            result.pop("type", None)
        return result
    return value


@pytest.mark.asyncio
async def test_enabled_mcp_catalog_matches_v1(app_context, monkeypatch):
    config = app_context.configuration
    monkeypatch.setenv("FRED_POSTGRES_PASSWORD", "test")
    config.mcp.opensearch_ops_enabled = True
    config.mcp.prometheus_ops_enabled = False
    config.storage.metadata_store = PostgresTableConfig(type="postgres")
    config.storage.tag_store = PostgresTableConfig(type="postgres")
    config.storage.resource_store = PostgresTableConfig(type="postgres")
    monkeypatch.setattr(main_module, "load_configuration", lambda: config)
    monkeypatch.setattr(main_module, "start_http_server", lambda *args, **kwargs: None)
    captured = []
    original = main_module.mount_fastapi_tools

    def record(*args, **kwargs):
        mcp = original(*args, **kwargs)
        captured.append(mcp)
        return mcp

    monkeypatch.setattr(main_module, "mount_fastapi_tools", record)
    ApplicationContext.reset_instance()
    try:
        main_module.create_app()
        inventory = []
        for mcp in captured:
            tools = await mcp.list_tools()
            inventory.append(
                {
                    tool.name: {
                        "description": tool.description,
                        "inputSchema": _semantic_schema(tool.parameters),
                    }
                    for tool in tools
                }
            )
        fixture = Path(__file__).parent / "fixtures" / "mcp_v1_inventory.json"
        old = json.loads(fixture.read_text())
        assert len(inventory) == len(old) == 6
        for prior_tools, actual_tools in zip(old, inventory, strict=True):
            expected = {
                tool["name"]: {
                    "description": tool["description"],
                    "inputSchema": _semantic_schema(tool["inputSchema"]),
                }
                for tool in prior_tools
            }
            assert actual_tools == expected
    finally:
        ApplicationContext.reset_instance()
