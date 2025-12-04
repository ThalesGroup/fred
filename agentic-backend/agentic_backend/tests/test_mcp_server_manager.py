# agentic_backend/tests/test_mcp_server_manager.py

from types import SimpleNamespace

from agentic_backend.core.agents.agent_spec import MCPServerConfiguration
from agentic_backend.core.mcp.mcp_server_manager import McpServerManager
from agentic_backend.core.mcp.store.base_mcp_server_store import BaseMcpServerStore


class InMemoryMcpStore(BaseMcpServerStore):
    def __init__(self):
        self._data: dict[str, MCPServerConfiguration] = {}
        self.seeded = False

    def save(self, server: MCPServerConfiguration) -> None:
        self._data[server.id] = server

    def load_all(self):
        return list(self._data.values())

    def get(self, server_id: str):
        return self._data.get(server_id)

    def delete(self, server_id: str) -> None:
        self._data.pop(server_id, None)

    def static_seeded(self) -> bool:
        return self.seeded

    def mark_static_seeded(self) -> None:
        self.seeded = True


def make_config(static_servers: list[MCPServerConfiguration]):
    # Minimal config stub exposing the bits the manager reads/updates.
    return SimpleNamespace(
        ai=SimpleNamespace(use_static_config_only=False),
        mcp=SimpleNamespace(servers=static_servers),
    )


def test_delete_dynamic_server_removes_entry():
    dynamic_server = MCPServerConfiguration(id="dyn", name="Dynamic server")
    store = InMemoryMcpStore()
    config = make_config([])
    manager = McpServerManager(config=config, store=store)
    manager.bootstrap()
    manager.upsert(dynamic_server)

    manager.delete("dyn")

    assert store.get("dyn") is None
    assert "dyn" not in manager.servers
    assert all(s.id != "dyn" for s in manager.config.mcp.servers)


def test_static_servers_are_persisted_on_bootstrap():
    static_server = MCPServerConfiguration(id="static", name="Static server")
    store = InMemoryMcpStore()
    manager = McpServerManager(config=make_config([static_server]), store=store)

    manager.bootstrap()

    # Static server should be written to the store and visible in manager
    assert store.get("static") is not None
    assert manager.get("static") is not None


def test_restore_static_servers_reenables_deleted_static():
    static_server = MCPServerConfiguration(id="static", name="Static server")
    store = InMemoryMcpStore()
    manager = McpServerManager(config=make_config([static_server]), store=store)
    manager.bootstrap()

    # Simulate delete → removed from store/catalog
    manager.delete("static")
    assert store.get("static") is None
    assert manager.get("static") is None

    # Restore should re-enable and overwrite the override
    manager.restore_static_servers()
    restored = store.get("static")
    assert restored is not None
    assert restored.enabled is True
    assert manager.get("static").enabled is True


def test_deleted_static_not_reseeded_on_bootstrap():
    static_server = MCPServerConfiguration(id="static", name="Static server")
    store = InMemoryMcpStore()
    manager = McpServerManager(config=make_config([static_server]), store=store)
    manager.bootstrap()

    # Delete and simulate restart (new manager with same store contents)
    manager.delete("static")
    assert store.get("static") is None

    manager2 = McpServerManager(config=make_config([static_server]), store=store)
    manager2.bootstrap()

    assert manager2.get("static") is None
    assert store.get("static") is None


def test_static_seed_happens_on_first_bootstrap_even_with_existing_entries():
    static_server = MCPServerConfiguration(id="static", name="Static server")
    existing = MCPServerConfiguration(id="dyn", name="Dyn server")
    store = InMemoryMcpStore()
    store.save(existing)
    manager = McpServerManager(config=make_config([static_server]), store=store)

    manager.bootstrap()

    assert store.get("static") is not None
    assert manager.get("static") is not None
