from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from fred_runtime.app import load_agent_pod_config

_MISSING = object()


def _write_configuration_yaml(
    config_dir: Path, *, limit_concurrency: int | None | object = None
) -> None:
    """
    Write one minimal pod `configuration.yaml` fixture.

    Why this exists:
    - the config-loader regression tests need a realistic pod bootstrap layout
      without depending on any checked-in project config files

    How to use it:
    - pass the temporary `config/` directory for a minimal pod config whose MCP
      truth comes only from the external catalog file
    - pass `limit_concurrency=<int>` to exercise the optional Uvicorn cap
    - pass `limit_concurrency=_MISSING` to omit the field entirely

    Example:
    - `_write_configuration_yaml(config_dir)`
    """

    limit_concurrency_block = ""
    if limit_concurrency is not _MISSING:
        literal = "null" if limit_concurrency is None else str(limit_concurrency)
        limit_concurrency_block = f"\n              limit_concurrency: {literal}"

    (config_dir / "configuration.yaml").write_text(
        dedent(
            f"""
            app:
              name: "Test Pod"
              base_url: "/pod/v1"
              port: 8000
              log_level: "info"{limit_concurrency_block}

            security:
              m2m:
                enabled: false
                realm_url: "http://localhost:8080/realms/fred"
                client_id: "test-m2m"
              user:
                enabled: false
                realm_url: "http://localhost:8080/realms/fred"
                client_id: "test-user"
              authorized_origins: []

            ai:
              knowledge_flow_url: "http://localhost:8111/knowledge-flow/v1"
              timeout:
                connect: 5
                read: 30

            storage:
              postgres:
                sqlite_path: "./runtime.sqlite3"

            scheduler:
              enabled: false
            """
        ).strip(),
        encoding="utf-8",
    )


def _write_models_catalog(path: Path, *, chat_name: str = "gpt-5") -> None:
    """
    Write one minimal valid `models_catalog.yaml` fixture.

    Why this exists:
    - the config loader should resolve real catalog files, not synthetic
      placeholders that would fail later during runtime startup

    How to use it:
    - pass the destination file path and an optional chat model name so tests
      can distinguish default and env-override catalogs

    Example:
    - `_write_models_catalog(config_dir / "models_catalog.yaml")`
    """

    path.write_text(
        dedent(
            f"""
            version: v1
            default_profile_by_capability:
              chat: default.chat
              language: default.language
            profiles:
              - profile_id: default.chat
                capability: chat
                model:
                  provider: openai
                  name: {chat_name}
                  settings: {{}}
              - profile_id: default.language
                capability: language
                model:
                  provider: openai
                  name: gpt-5-mini
                  settings: {{}}
            rules: []
            """
        ).strip(),
        encoding="utf-8",
    )


def _write_mcp_catalog(path: Path, *, server_id: str) -> None:
    """
    Write one minimal valid `mcp_catalog.yaml` fixture.

    Why this exists:
    - the config-loader tests need a strict MCP catalog payload to verify the
      same bootstrap behavior pod apps will use in production

    How to use it:
    - pass the destination file path and the server id you want the test to
      assert after loading

    Example:
    - `_write_mcp_catalog(config_dir / "mcp_catalog.yaml", server_id="mcp-demo")`
    """

    path.write_text(
        dedent(
            f"""
            version: v1
            servers:
              - id: "{server_id}"
                name: "{server_id}"
                transport: "streamable_http"
                url: "http://localhost:9999/mcp"
                enabled: true
                auth_mode: "user_token"
            """
        ).strip(),
        encoding="utf-8",
    )


def test_load_agent_pod_config_loads_default_external_catalogs(
    tmp_path, monkeypatch
) -> None:
    """
    Ensure pod startup loads default `models_catalog.yaml` and `mcp_catalog.yaml`.

    Why this exists:
    - pods now rely on `load_agent_pod_config()` to reproduce the same external
      catalog bootstrap contract on every startup

    How to use it:
    - run as part of the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_config_loader.py -q`
    """

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_configuration_yaml(config_dir)
    _write_models_catalog(config_dir / "models_catalog.yaml")
    _write_mcp_catalog(config_dir / "mcp_catalog.yaml", server_id="mcp-default")
    (config_dir / ".env").write_text("", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_dir / "configuration.yaml"))
    monkeypatch.setenv("ENV_FILE", str(config_dir / ".env"))
    monkeypatch.delenv("FRED_MODELS_CATALOG_FILE", raising=False)
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)

    config = load_agent_pod_config()

    assert Path(config.get_models_catalog_path() or "") == Path(
        "config/models_catalog.yaml"
    )
    assert config.app.limit_concurrency is None
    assert config.ai.timeout.connect == 5.0
    assert config.ai.timeout.read == 30.0
    mcp_configuration = config.get_mcp_configuration()
    assert mcp_configuration is not None
    assert [server.id for server in mcp_configuration.servers] == ["mcp-default"]


def test_load_agent_pod_config_honors_catalog_env_overrides(
    tmp_path, monkeypatch
) -> None:
    """
    Ensure pod startup honors backend-compatible catalog env-var overrides.

    Why this exists:
    - pods and agentic-backend must share the same startup override knobs for
      external model and MCP catalogs

    How to use it:
    - run via the default offline `make test` suite in `fred-runtime`

    Example:
    - `pytest tests/test_config_loader.py -q`
    """

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_configuration_yaml(config_dir)
    _write_models_catalog(config_dir / "models_catalog.yaml", chat_name="gpt-5")
    _write_mcp_catalog(config_dir / "mcp_catalog.yaml", server_id="mcp-default")
    (config_dir / ".env").write_text("", encoding="utf-8")

    override_models_catalog = tmp_path / "override-models.yaml"
    override_mcp_catalog = tmp_path / "override-mcp.yaml"
    _write_models_catalog(override_models_catalog, chat_name="gpt-5-mini")
    _write_mcp_catalog(override_mcp_catalog, server_id="mcp-override")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_dir / "configuration.yaml"))
    monkeypatch.setenv("ENV_FILE", str(config_dir / ".env"))
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(override_models_catalog))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(override_mcp_catalog))

    config = load_agent_pod_config()

    assert Path(config.get_models_catalog_path() or "") == override_models_catalog
    mcp_configuration = config.get_mcp_configuration()
    assert mcp_configuration is not None
    assert [server.id for server in mcp_configuration.servers] == ["mcp-override"]


def test_load_agent_pod_config_requires_models_catalog_file(
    tmp_path, monkeypatch
) -> None:
    """
    Ensure pod startup fails fast when the mandatory models catalog is missing.

    Why this exists:
    - `models_catalog.yaml` is now a required part of the pod bootstrap
      contract, so startup should not silently fall back to another model
      configuration path

    How to use it:
    - run as part of the default offline regression suite

    Example:
    - `pytest tests/test_config_loader.py -q`
    """

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_configuration_yaml(config_dir)
    (config_dir / ".env").write_text("", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_dir / "configuration.yaml"))
    monkeypatch.setenv("ENV_FILE", str(config_dir / ".env"))
    monkeypatch.delenv("FRED_MODELS_CATALOG_FILE", raising=False)
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)

    with pytest.raises(FileNotFoundError, match="Mandatory models catalog file"):
        load_agent_pod_config()


def test_load_agent_pod_config_keeps_mcp_out_of_public_model(
    tmp_path, monkeypatch
) -> None:
    """
    Ensure the public pod config schema no longer exposes an `mcp` field.

    Why this exists:
    - the cleaned-up pod configuration story should keep MCP truth in
      `mcp_catalog.yaml`, not in the public Pydantic model

    How to use it:
    - run as part of the default offline regression suite

    Example:
    - `pytest tests/test_config_loader.py -q`
    """

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_configuration_yaml(config_dir)
    _write_models_catalog(config_dir / "models_catalog.yaml")
    (config_dir / ".env").write_text("", encoding="utf-8")

    override_mcp_catalog = tmp_path / "override-mcp.yaml"
    _write_mcp_catalog(override_mcp_catalog, server_id="mcp-override")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_dir / "configuration.yaml"))
    monkeypatch.setenv("ENV_FILE", str(config_dir / ".env"))
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(override_mcp_catalog))
    monkeypatch.delenv("FRED_MODELS_CATALOG_FILE", raising=False)

    config = load_agent_pod_config()

    payload = config.model_dump()
    assert "mcp" not in payload
    assert "models_catalog_path" not in payload["ai"]
    assert "default_model_profile" not in payload["ai"]
    mcp_configuration = config.get_mcp_configuration()
    assert mcp_configuration is not None
    assert [server.id for server in mcp_configuration.servers] == ["mcp-override"]


def test_load_agent_pod_config_loads_app_limit_concurrency(
    tmp_path, monkeypatch
) -> None:
    """
    Ensure pod startup preserves the optional Uvicorn connection cap setting.

    Why this test exists:
    - pod authors now configure the runtime-side Uvicorn concurrency cap in the
      shared YAML contract

    How to use it:
    - run via the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_config_loader.py -q`
    """

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_configuration_yaml(config_dir, limit_concurrency=37)
    _write_models_catalog(config_dir / "models_catalog.yaml")
    _write_mcp_catalog(config_dir / "mcp_catalog.yaml", server_id="mcp-default")
    (config_dir / ".env").write_text("", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_dir / "configuration.yaml"))
    monkeypatch.setenv("ENV_FILE", str(config_dir / ".env"))

    config = load_agent_pod_config()

    assert config.app.limit_concurrency == 37


def test_load_agent_pod_config_defaults_app_limit_concurrency_when_omitted(
    tmp_path, monkeypatch
) -> None:
    """
    Ensure older pod configs still load when the Uvicorn cap field is absent.

    Why this test exists:
    - adding `app.limit_concurrency` must remain backward compatible with
      existing configuration files that omit the new field entirely

    How to use it:
    - run via the default offline `fred-runtime` test suite

    Example:
    - `pytest tests/test_config_loader.py -q`
    """

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_configuration_yaml(config_dir, limit_concurrency=_MISSING)
    _write_models_catalog(config_dir / "models_catalog.yaml")
    _write_mcp_catalog(config_dir / "mcp_catalog.yaml", server_id="mcp-default")
    (config_dir / ".env").write_text("", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_FILE", str(config_dir / "configuration.yaml"))
    monkeypatch.setenv("ENV_FILE", str(config_dir / ".env"))

    config = load_agent_pod_config()

    assert config.app.limit_concurrency is None
