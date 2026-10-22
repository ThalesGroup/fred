"""Knowledge Flow exposes the expected MCP tools from its selected routes."""

import pytest
from fred_pod.common.structures import PostgresTableConfig

from knowledge_flow_backend import main as main_module
from knowledge_flow_backend.application_context import ApplicationContext


@pytest.mark.asyncio
async def test_enabled_mcp_catalog_exposes_selected_tools(app_context, monkeypatch):
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
        assert len(captured) == 6
        catalogs = [{tool.name: tool for tool in await mcp.list_tools()} for mcp in captured]
        assert set(catalogs[0]) == {"write_report"}
        assert "os_health" in catalogs[1]
        assert set(catalogs[2]) == {
            "list_tabular_documents",
            "describe_tabular_documents",
            "read_query",
            "search_tabular_values",
        }
        assert "similarity_search" in catalogs[3]
        assert catalogs[4] == {}
        assert {"list_tags", "get_resource_creation_schema"} <= set(catalogs[5])
        assert set(catalogs[0]["write_report"].parameters["required"]) == {"title", "markdown", "tag_id"}
        assert catalogs[2]["read_query"].parameters["required"] == ["sql"]
        assert "max_rows" in catalogs[2]["read_query"].parameters["properties"]
        assert catalogs[2]["describe_tabular_documents"].parameters["required"] == ["document_uids"]
    finally:
        ApplicationContext.reset_instance()
