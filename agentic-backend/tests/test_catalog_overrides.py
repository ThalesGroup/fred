from __future__ import annotations

import pytest

from agentic_backend.common.catalog_overrides import apply_external_catalog_overrides
from agentic_backend.common.structures import Configuration


def _minimal_configuration() -> Configuration:
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
        "ai": {
            "knowledge_flow_url": "http://localhost:8111/knowledge-flow/v1",
            "timeout": {"connect": 5, "read": 15},
            "use_static_config_only": True,
            "restore_max_exchanges": 20,
            "max_concurrent_agents": 32,
            "max_concurrent_sessions_per_user": 10,
            "max_attached_files_per_user": 20,
            "max_attached_file_size_mb": 10,
            "default_chat_model": {
                "provider": "openai",
                "name": "gpt-5-mini",
                "settings": {"temperature": 0.0},
            },
            "agents": [
                {
                    "id": "Georges",
                    "name": "Georges",
                    "type": "agent",
                    "class_path": "agentic_backend.agents.generalist.generalist_expert.Georges",
                    "enabled": True,
                }
            ],
        },
        "mcp": {
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
        },
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
    return Configuration.model_validate(payload)


def test_agents_catalog_takes_precedence_when_present(tmp_path, monkeypatch) -> None:
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
    monkeypatch.setenv("FRED_AGENTS_CATALOG_FILE", str(agents_catalog))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))

    apply_external_catalog_overrides(configuration)

    assert [agent.id for agent in configuration.ai.agents] == ["Catalog Agent"]
    assert configuration.ai.agents[0].definition_ref == "v2.react.basic"


def test_mcp_catalog_takes_precedence_when_present(tmp_path, monkeypatch) -> None:
    configuration = _minimal_configuration()
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
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(mcp_catalog))
    monkeypatch.setenv(
        "FRED_AGENTS_CATALOG_FILE", str(tmp_path / "missing-agents.yaml")
    )

    apply_external_catalog_overrides(configuration)

    assert [server.id for server in configuration.mcp.servers] == ["mcp-catalog-only"]


def test_missing_catalog_files_keep_configuration_values(tmp_path, monkeypatch) -> None:
    configuration = _minimal_configuration()
    monkeypatch.setenv(
        "FRED_AGENTS_CATALOG_FILE", str(tmp_path / "does-not-exist-agents.yaml")
    )
    monkeypatch.setenv(
        "FRED_MCP_CATALOG_FILE", str(tmp_path / "does-not-exist-mcp.yaml")
    )

    apply_external_catalog_overrides(configuration)

    assert [agent.id for agent in configuration.ai.agents] == ["Georges"]
    assert [server.id for server in configuration.mcp.servers] == [
        "mcp-knowledge-flow-opensearch-ops"
    ]
    assert configuration.ai.react_profile_allowlist == []


def test_invalid_agents_catalog_fails_fast(tmp_path, monkeypatch) -> None:
    configuration = _minimal_configuration()
    agents_catalog = tmp_path / "agents_catalog.yaml"
    agents_catalog.write_text("version: v1\nagents: invalid\n", encoding="utf-8")
    monkeypatch.setenv("FRED_AGENTS_CATALOG_FILE", str(agents_catalog))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))

    with pytest.raises(Exception):
        apply_external_catalog_overrides(configuration)


def test_agents_catalog_can_define_react_profile_allowlist(
    tmp_path, monkeypatch
) -> None:
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
react_profiles:
  - profile_id: "rag_expert"
    enabled: true
  - profile_id: "geo_demo"
    enabled: false
  - profile_id: " sentinel "
    enabled: true
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_AGENTS_CATALOG_FILE", str(agents_catalog))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))

    apply_external_catalog_overrides(configuration)

    assert configuration.ai.react_profile_allowlist == ["rag_expert", "sentinel"]


def test_agents_catalog_allows_empty_react_profile_allowlist(
    tmp_path, monkeypatch
) -> None:
    configuration = _minimal_configuration()
    agents_catalog = tmp_path / "agents_catalog.yaml"
    agents_catalog.write_text(
        """
version: v1
agents: []
react_profiles: []
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_AGENTS_CATALOG_FILE", str(agents_catalog))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))

    apply_external_catalog_overrides(configuration)

    assert configuration.ai.react_profile_allowlist == []


def test_agents_catalog_without_react_profiles_exposes_no_profiles(
    tmp_path, monkeypatch
) -> None:
    configuration = _minimal_configuration()
    configuration.ai.react_profile_allowlist = ["sentinel"]

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
    monkeypatch.setenv("FRED_AGENTS_CATALOG_FILE", str(agents_catalog))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))

    apply_external_catalog_overrides(configuration)

    assert configuration.ai.react_profile_allowlist == []


def test_models_catalog_takes_precedence_when_present(tmp_path, monkeypatch) -> None:
    configuration = _minimal_configuration()
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
      settings:
        temperature: 0.0
  - profile_id: default.language
    capability: language
    model:
      provider: openai
      name: gpt-5-mini
      settings:
        temperature: 0.0
rules: []
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(models_catalog))
    monkeypatch.setenv(
        "FRED_AGENTS_CATALOG_FILE", str(tmp_path / "missing-agents.yaml")
    )
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))

    apply_external_catalog_overrides(configuration)

    assert configuration.ai.default_chat_model is not None
    assert configuration.ai.default_language_model is not None
    assert configuration.ai.default_chat_model.name == "gpt-5"
    assert configuration.ai.default_language_model.name == "gpt-5-mini"


def test_missing_chat_model_without_catalog_fails_fast(tmp_path, monkeypatch) -> None:
    base = _minimal_configuration()
    configuration = base.model_copy(
        update={"ai": base.ai.model_copy(update={"default_chat_model": None})},
        deep=True,
    )
    monkeypatch.setenv(
        "FRED_AGENTS_CATALOG_FILE", str(tmp_path / "missing-agents.yaml")
    )
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))
    monkeypatch.setenv(
        "FRED_MODELS_CATALOG_FILE", str(tmp_path / "missing-models.yaml")
    )

    with pytest.raises(ValueError, match="Missing required chat model configuration"):
        apply_external_catalog_overrides(configuration)


def test_models_catalog_default_profile_overrides_via_env(
    tmp_path, monkeypatch
) -> None:
    configuration = _minimal_configuration()
    models_catalog = tmp_path / "models_catalog.yaml"
    models_catalog.write_text(
        """
version: v1
default_profile_by_capability:
  chat: default.chat.openai
  language: default.language.openai
profiles:
  - profile_id: default.chat.openai
    capability: chat
    model:
      provider: openai
      name: gpt-5-mini
      settings: {}
  - profile_id: default.language.openai
    capability: language
    model:
      provider: openai
      name: gpt-5-mini
      settings: {}
  - profile_id: chat.ollama.mistral
    capability: chat
    model:
      provider: ollama
      name: mistral:latest
      settings:
        base_url: http://localhost:11434
  - profile_id: language.ollama.mistral
    capability: language
    model:
      provider: ollama
      name: mistral:latest
      settings:
        base_url: http://localhost:11434
rules: []
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(models_catalog))
    monkeypatch.setenv("FRED_MODELS_DEFAULT_CHAT_PROFILE_ID", "chat.ollama.mistral")
    monkeypatch.setenv(
        "FRED_MODELS_DEFAULT_LANGUAGE_PROFILE_ID", "language.ollama.mistral"
    )
    monkeypatch.setenv(
        "FRED_AGENTS_CATALOG_FILE", str(tmp_path / "missing-agents.yaml")
    )
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))

    apply_external_catalog_overrides(configuration)

    assert configuration.ai.default_chat_model is not None
    assert configuration.ai.default_chat_model.provider == "ollama"
    assert configuration.ai.default_chat_model.name == "mistral:latest"
    assert configuration.ai.default_language_model is not None
    assert configuration.ai.default_language_model.provider == "ollama"
    assert configuration.ai.default_language_model.name == "mistral:latest"


def test_models_catalog_profile_override_rejects_unknown_profile(
    tmp_path, monkeypatch
) -> None:
    configuration = _minimal_configuration()
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
      name: gpt-5-mini
      settings: {}
rules: []
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(models_catalog))
    monkeypatch.setenv("FRED_MODELS_DEFAULT_CHAT_PROFILE_ID", "chat.does.not.exist")
    monkeypatch.setenv(
        "FRED_AGENTS_CATALOG_FILE", str(tmp_path / "missing-agents.yaml")
    )
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "missing-mcp.yaml"))

    with pytest.raises(ValueError, match="was not found in profiles"):
        apply_external_catalog_overrides(configuration)
