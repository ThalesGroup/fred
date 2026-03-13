from __future__ import annotations

import pytest

from agentic_backend.common.catalog_overrides import (
    apply_external_catalog_overrides,
    resolve_model_routing_bootstrap_config,
)
from agentic_backend.common.structures import Configuration


def _minimal_configuration(
    *,
    include_agents: bool = True,
    include_mcp: bool = True,
    include_models: bool = True,
) -> Configuration:
    ai_payload: dict[str, object] = {
        "knowledge_flow_url": "http://localhost:8111/knowledge-flow/v1",
        "timeout": {"connect": 5, "read": 15},
        "use_static_config_only": True,
        "restore_max_exchanges": 20,
        "max_concurrent_agents": 32,
        "max_concurrent_sessions_per_user": 10,
        "max_attached_files_per_user": 20,
        "max_attached_file_size_mb": 10,
    }
    if include_models:
        ai_payload["default_chat_model"] = {
            "provider": "openai",
            "name": "gpt-5-mini",
            "settings": {"temperature": 0.0},
        }
    if include_agents:
        ai_payload["agents"] = [
            {
                "id": "Georges",
                "name": "Georges",
                "type": "agent",
                "class_path": "agentic_backend.agents.generalist.generalist_expert.Georges",
                "enabled": True,
            }
        ]

    payload = {
        "app": {
            "name": "Agentic Backend",
            "base_url": "/agentic/v1",
            "address": "127.0.0.1",
            "port": 8000,
            "log_level": "info",
            "reload": False,
            "reload_dir": ".",
        },
        "security": {
            "m2m": {
                "enabled": False,
                "client_id": "agentic",
                "realm_url": "http://localhost:8080/realms/app",
            },
            "user": {
                "enabled": False,
                "client_id": "app",
                "realm_url": "http://localhost:8080/realms/app",
            },
            "authorized_origins": ["http://localhost:5173"],
            "rebac": None,
        },
        "frontend_settings": {
            "feature_flags": {
                "enableK8Features": False,
                "enableElecWarfare": False,
            },
            "properties": {
                "logoName": "fred",
                "logoNameDark": "fred-dark",
                "siteDisplayName": "Fred",
            },
        },
        "ai": ai_payload,
        "storage": {
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "fred",
                "username": "admin",
            },
            "agent_store": {"type": "duckdb", "duckdb_path": "/tmp/agent.duckdb"},
            "mcp_servers_store": {
                "type": "duckdb",
                "duckdb_path": "/tmp/mcp_servers.duckdb",
            },
            "session_store": {"type": "duckdb", "duckdb_path": "/tmp/session.duckdb"},
            "history_store": {"type": "duckdb", "duckdb_path": "/tmp/history.duckdb"},
            "feedback_store": {
                "type": "duckdb",
                "duckdb_path": "/tmp/feedback.duckdb",
            },
            "kpi_store": {"type": "duckdb", "duckdb_path": "/tmp/kpi.duckdb"},
        },
    }
    if include_mcp:
        payload["mcp"] = {
            "servers": [
                {
                    "id": "mcp-knowledge-flow-opensearch-ops",
                    "name": "mcp.servers.search_opensearch.name",
                    "transport": "streamable_http",
                    "url": "http://knowledge-flow-backend:8000/knowledge-flow/v1/mcp-opensearch-ops",
                    "enabled": True,
                    "auth_mode": "user_token",
                }
            ]
        }
    return Configuration.model_validate(payload)


def test_catalog_files_are_ignored_even_when_present(tmp_path, monkeypatch) -> None:
    configuration = _minimal_configuration()
    agents_catalog = tmp_path / "agents_catalog.yaml"
    agents_catalog.write_text(
        """
version: v1
agents:
  - id: "Catalog Agent"
    name: "Catalog Agent"
    type: "agent"
    definition_ref: "v2.react.basic"
    enabled: true
        """.strip(),
        encoding="utf-8",
    )
    mcp_catalog = tmp_path / "mcp_catalog.yaml"
    mcp_catalog.write_text(
        """
version: v1
servers:
  - id: "mcp-catalog-only"
    name: "mcp.catalog.only"
    transport: "streamable_http"
    url: "http://mcp-server:8080/mcp"
    enabled: true
    auth_mode: "user_token"
        """.strip(),
        encoding="utf-8",
    )
    models_catalog = tmp_path / "models_catalog.yaml"
    models_catalog.write_text(
        """
version: v1
default_profile_by_capability:
  chat: default.chat
  language: default.language
profiles:
  - profile_id: default.chat
    capability: chat
    model:
      provider: openai
      name: gpt-5
      settings: {}
  - profile_id: default.language
    capability: language
    model:
      provider: openai
      name: gpt-5-mini
      settings: {}
rules: []
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_AGENTS_CATALOG_FILE", str(agents_catalog))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(mcp_catalog))
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(models_catalog))

    apply_external_catalog_overrides(configuration)

    assert [agent.id for agent in configuration.ai.agents] == ["Georges"]
    assert [server.id for server in configuration.mcp.servers] == [
        "mcp-knowledge-flow-opensearch-ops"
    ]
    assert configuration.ai.default_chat_model is not None
    assert configuration.ai.default_chat_model.name == "gpt-5-mini"
    assert configuration.ai.default_language_model is None
    assert configuration.ai.react_profile_allowlist == []


def test_catalogs_do_not_fill_missing_agents_or_mcp(tmp_path, monkeypatch) -> None:
    configuration = _minimal_configuration(include_agents=False, include_mcp=False)
    agents_catalog = tmp_path / "agents_catalog.yaml"
    agents_catalog.write_text(
        """
version: v1
agents:
  - id: "Catalog Agent"
    name: "Catalog Agent"
    type: "agent"
    definition_ref: "v2.react.basic"
    enabled: true
        """.strip(),
        encoding="utf-8",
    )
    mcp_catalog = tmp_path / "mcp_catalog.yaml"
    mcp_catalog.write_text(
        """
version: v1
servers:
  - id: "mcp-catalog-only"
    name: "mcp.catalog.only"
    transport: "streamable_http"
    url: "http://mcp-server:8080/mcp"
    enabled: true
    auth_mode: "user_token"
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_AGENTS_CATALOG_FILE", str(agents_catalog))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(mcp_catalog))

    apply_external_catalog_overrides(configuration)

    assert configuration.ai.agents == []
    assert configuration.mcp.servers == []


def test_missing_chat_model_fails_fast_without_catalog_fallback(
    tmp_path, monkeypatch
) -> None:
    configuration = _minimal_configuration(include_models=False)
    models_catalog = tmp_path / "models_catalog.yaml"
    models_catalog.write_text(
        """
version: v1
default_profile_by_capability:
  chat: default.chat
profiles:
  - profile_id: default.chat
    capability: chat
    model:
      provider: openai
      name: gpt-5
      settings: {}
rules: []
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(models_catalog))

    with pytest.raises(ValueError, match="Missing required chat model configuration"):
        apply_external_catalog_overrides(configuration)


def test_react_allowlist_is_reset_to_empty() -> None:
    configuration = _minimal_configuration()
    configuration.ai.react_profile_allowlist = ["sentinel"]

    apply_external_catalog_overrides(configuration)

    assert configuration.ai.react_profile_allowlist == []


def test_model_routing_bootstrap_ignores_models_catalog_file(
    tmp_path, monkeypatch
) -> None:
    models_catalog = tmp_path / "models_catalog.yaml"
    models_catalog.write_text(
        "version: v1\nprofiles: []\nrules: []\n", encoding="utf-8"
    )
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(models_catalog))

    bootstrap = resolve_model_routing_bootstrap_config()

    assert bootstrap.catalog_exists is False
