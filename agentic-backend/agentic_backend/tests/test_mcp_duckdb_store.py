from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.store.duckdb_mcp_server_store import DuckDBMcpServerStore


def test_save_then_delete_removes_server(tmp_path):
    db_path = tmp_path / "mcp_servers.duckdb"
    store = DuckDBMcpServerStore(db_path)

    server = MCPServerConfiguration(id="demo", name="Demo server")
    store.save(server)

    assert [s.id for s in store.load_all()] == ["demo"]

    store.delete("demo")

    assert store.get("demo") is None
    assert store.load_all() == []


def test_delete_missing_is_noop(tmp_path):
    db_path = tmp_path / "mcp_servers.duckdb"
    store = DuckDBMcpServerStore(db_path)

    # Should not raise even if the server was never persisted
    store.delete("missing-id")
