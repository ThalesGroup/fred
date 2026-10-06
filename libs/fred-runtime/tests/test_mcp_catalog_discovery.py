# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Package discovery and external overrides must feed one MCP server list."""

import sys
from collections.abc import Callable
from importlib.metadata import EntryPoint
from pathlib import Path
from types import ModuleType

import pytest
from fred_runtime.app import _catalogs
from fred_runtime.app.config import AgentPodConfig
from fred_runtime.app.service_endpoints import ConfiguredServiceEndpoints
from fred_runtime.capabilities.registry import boot_capability_registry
from fred_sdk.contracts.models import MCPServerConfiguration
from fred_sdk.contracts.services import ServiceEndpointsPort
from fred_sdk.resources.mcp import McpCatalog


@pytest.fixture
def services(minimal_config: AgentPodConfig) -> ServiceEndpointsPort:
    return ConfiguredServiceEndpoints(minimal_config)


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def install(**loaders: object) -> None:
        module = ModuleType("mcp_catalog_fixture")
        for name, provider in loaders.items():
            setattr(module, name, provider)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        entries = [
            EntryPoint(name, f"{module.__name__}:{name}", "fred.mcp_catalogs")
            for name in loaders
        ]
        monkeypatch.setattr(_catalogs, "entry_points", lambda **_: entries)

    install()
    return install


def test_discovery_shares_enabled_and_disabled_servers(
    providers: Callable[..., None],
    services: ServiceEndpointsPort,
) -> None:
    providers(
        z=lambda _: McpCatalog(
            servers=[
                MCPServerConfiguration.model_validate(
                    {"id": "off", "name": "Off", "enabled": False}
                )
            ]
        ),
        a=lambda _: McpCatalog(
            servers=[MCPServerConfiguration.model_validate({"id": "on", "name": "On"})]
        ),
    )
    catalog = _catalogs.load_installed_mcp_catalogs(services)
    assert [server.id for server in catalog.servers] == ["on", "off"]
    assert catalog.get_server("off") is None
    assert catalog.get_server("on") is catalog.servers[0]
    registry = boot_capability_registry(mcp_servers=catalog.servers, env={})
    assert "on" in registry
    assert "off" not in registry


def test_discovery_rejects_duplicate_ids(
    providers: Callable[..., None], services: ServiceEndpointsPort
) -> None:
    def load(services: ServiceEndpointsPort) -> McpCatalog:
        return McpCatalog(
            servers=[
                MCPServerConfiguration.model_validate({"id": "same", "name": "Same"})
            ]
        )

    providers(first=load, second=load)
    with pytest.raises(ValueError, match="Duplicate MCP server id"):
        _catalogs.load_installed_mcp_catalogs(services)


@pytest.mark.parametrize("loader", [42, lambda _: [], lambda _: None])
def test_discovery_rejects_invalid_providers(
    providers: Callable[..., None], services: ServiceEndpointsPort, loader: object
) -> None:
    providers(broken=loader)
    with pytest.raises(RuntimeError, match="Failed to load MCP catalog 'broken'"):
        _catalogs.load_installed_mcp_catalogs(services)


def test_discovery_preserves_provider_failure(
    providers: Callable[..., None], services: ServiceEndpointsPort
) -> None:
    def broken(services: ServiceEndpointsPort) -> McpCatalog:
        raise FileNotFoundError("missing-instructions.md")

    providers(broken=broken)
    with pytest.raises(RuntimeError, match="missing-instructions.md") as error:
        _catalogs.load_installed_mcp_catalogs(services)
    assert isinstance(error.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize(
    "source", ["package", "legacy", "explicit", "empty", "missing", "none"]
)
def test_catalog_precedence(
    source: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimal_config: AgentPodConfig,
    providers: Callable[..., None],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)
    monkeypatch.delenv("FRED_MCP_EXTERNAL_CATALOG_FILE", raising=False)
    (tmp_path / "models.yaml").write_text("models: []", encoding="utf-8")
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(tmp_path / "models.yaml"))
    calls: list[str] = []

    def packaged(services: ServiceEndpointsPort) -> McpCatalog:
        calls.append("package")
        return McpCatalog(
            servers=[
                MCPServerConfiguration.model_validate(
                    {"id": "packaged", "name": "Packaged"}
                )
            ]
        )

    if source != "none":
        providers(packaged=packaged)
    if source in {"legacy", "explicit", "empty", "missing"}:
        (tmp_path / "config").mkdir()
        (tmp_path / "config/mcp_catalog.yaml").write_text(
            "servers: [{id: legacy, name: Legacy}]", encoding="utf-8"
        )
    if source in {"explicit", "empty", "missing"}:
        monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "override.yaml"))
        if source != "missing":
            (tmp_path / "override.yaml").write_text(
                "servers: []"
                if source == "empty"
                else "servers: [{id: external, name: External}]",
                encoding="utf-8",
            )
    config = _catalogs.apply_external_catalog_overrides(
        minimal_config
    ).get_mcp_configuration()
    expected = {
        "package": ["packaged"],
        "legacy": ["legacy"],
        "explicit": ["external"],
    }.get(source, [])
    assert (
        [server.id for server in config.servers] if config is not None else []
    ) == expected
    assert calls == (["package"] if source == "package" else [])


def test_external_file_adds_to_installed_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimal_config: AgentPodConfig,
    providers: Callable[..., None],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)
    monkeypatch.delenv("FRED_MCP_EXTERNAL_CATALOG_FILE", raising=False)
    (tmp_path / "models.yaml").write_text("models: []", encoding="utf-8")
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(tmp_path / "models.yaml"))
    (tmp_path / "config").mkdir()
    (tmp_path / "config/mcp_catalog_external.yaml").write_text(
        "servers: [{id: third-party, name: Third Party, url: https://example.com/mcp}]",
        encoding="utf-8",
    )
    providers(
        packaged=lambda _: McpCatalog(
            servers=[
                MCPServerConfiguration.model_validate(
                    {"id": "packaged", "name": "Packaged"}
                )
            ]
        )
    )

    catalog = _catalogs.apply_external_catalog_overrides(
        minimal_config
    ).get_mcp_configuration()

    assert catalog is not None
    assert [server.id for server in catalog.servers] == ["packaged", "third-party"]
    assert catalog.servers[1].url == "https://example.com/mcp"
    registry = boot_capability_registry(mcp_servers=catalog.servers, env={})
    assert {"packaged", "third-party"}.issubset(registry.ids())


def test_empty_external_file_keeps_installed_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimal_config: AgentPodConfig,
    providers: Callable[..., None],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)
    (tmp_path / "models.yaml").write_text("models: []", encoding="utf-8")
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(tmp_path / "models.yaml"))
    (tmp_path / "external.yaml").write_text("servers: []", encoding="utf-8")
    monkeypatch.setenv(
        "FRED_MCP_EXTERNAL_CATALOG_FILE", str(tmp_path / "external.yaml")
    )
    providers(
        packaged=lambda _: McpCatalog(
            servers=[
                MCPServerConfiguration.model_validate(
                    {"id": "packaged", "name": "Packaged"}
                )
            ]
        )
    )

    catalog = _catalogs.apply_external_catalog_overrides(
        minimal_config
    ).get_mcp_configuration()

    assert catalog is not None
    assert [server.id for server in catalog.servers] == ["packaged"]


def test_external_file_works_without_installed_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimal_config: AgentPodConfig,
    providers: Callable[..., None],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models.yaml").write_text("models: []", encoding="utf-8")
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(tmp_path / "models.yaml"))
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)
    (tmp_path / "external.yaml").write_text(
        "servers: [{id: third-party, name: Third Party}]", encoding="utf-8"
    )
    monkeypatch.setenv(
        "FRED_MCP_EXTERNAL_CATALOG_FILE", str(tmp_path / "external.yaml")
    )
    providers()

    catalog = _catalogs.apply_external_catalog_overrides(
        minimal_config
    ).get_mcp_configuration()

    assert catalog is not None
    assert [server.id for server in catalog.servers] == ["third-party"]


def test_external_file_rejects_duplicate_installed_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimal_config: AgentPodConfig,
    providers: Callable[..., None],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models.yaml").write_text("models: []", encoding="utf-8")
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(tmp_path / "models.yaml"))
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)
    (tmp_path / "external.yaml").write_text(
        "servers: [{id: duplicate, name: External}]", encoding="utf-8"
    )
    monkeypatch.setenv(
        "FRED_MCP_EXTERNAL_CATALOG_FILE", str(tmp_path / "external.yaml")
    )
    providers(
        packaged=lambda _: McpCatalog(
            servers=[
                MCPServerConfiguration.model_validate(
                    {"id": "duplicate", "name": "Packaged"}
                )
            ]
        )
    )

    with pytest.raises(ValueError, match="Duplicate MCP server id"):
        _catalogs.apply_external_catalog_overrides(minimal_config)


def test_missing_explicit_external_file_fails_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimal_config: AgentPodConfig,
    providers: Callable[..., None],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models.yaml").write_text("models: []", encoding="utf-8")
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(tmp_path / "models.yaml"))
    monkeypatch.delenv("FRED_MCP_CATALOG_FILE", raising=False)
    monkeypatch.setenv("FRED_MCP_EXTERNAL_CATALOG_FILE", str(tmp_path / "missing.yaml"))
    providers()

    with pytest.raises(FileNotFoundError, match="Selected external MCP catalog"):
        _catalogs.apply_external_catalog_overrides(minimal_config)


def test_legacy_replacement_ignores_additive_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimal_config: AgentPodConfig,
    providers: Callable[..., None],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models.yaml").write_text("models: []", encoding="utf-8")
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(tmp_path / "models.yaml"))
    (tmp_path / "replacement.yaml").write_text(
        "servers: [{id: replacement, name: Replacement}]", encoding="utf-8"
    )
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "replacement.yaml"))
    monkeypatch.setenv("FRED_MCP_EXTERNAL_CATALOG_FILE", str(tmp_path / "missing.yaml"))
    providers(
        packaged=lambda _: McpCatalog(
            servers=[
                MCPServerConfiguration.model_validate(
                    {"id": "packaged", "name": "Packaged"}
                )
            ]
        )
    )

    catalog = _catalogs.apply_external_catalog_overrides(
        minimal_config
    ).get_mcp_configuration()

    assert catalog is not None
    assert [server.id for server in catalog.servers] == ["replacement"]


@pytest.mark.parametrize("configured", [True, False])
def test_external_catalog_resolves_runtime_service(
    configured: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    minimal_config: AgentPodConfig,
    providers: Callable[..., None],
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models.yaml").write_text("models: []", encoding="utf-8")
    monkeypatch.setenv("FRED_MODELS_CATALOG_FILE", str(tmp_path / "models.yaml"))
    (tmp_path / "mcp.yaml").write_text(
        "servers: [{id: cp-mcp, name: CP, service: control_plane, path: mcp}]",
        encoding="utf-8",
    )
    monkeypatch.setenv("FRED_MCP_CATALOG_FILE", str(tmp_path / "mcp.yaml"))
    if not configured:
        with pytest.raises(ValueError, match="No URL configured.*control_plane"):
            _catalogs.apply_external_catalog_overrides(minimal_config)
        return
    minimal_config.platform.control_plane_url = (
        "https://cp.example:9443/control-plane/v2/"
    )

    catalog = _catalogs.apply_external_catalog_overrides(
        minimal_config
    ).get_mcp_configuration()

    assert catalog is not None
    assert catalog.servers[0].url == "https://cp.example:9443/control-plane/v2/mcp"
