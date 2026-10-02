# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Catalog and prompt resources must load with SDK dependencies alone."""

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from fred_sdk.contracts.services import FredService
from fred_sdk.resources.mcp import load_mcp_catalog, load_packaged_mcp_catalog


@dataclass
class ServiceEndpoints:
    base_url: str

    def get_base_url(self, service: FredService) -> str:
        assert service is FredService.KNOWLEDGE_FLOW
        return self.base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "https://kf.example:9443/custom/v2/",
        "https://kf.example/custom/v2",
        "http://[::1]:8112/knowledge-flow/v1",
    ],
)
@pytest.mark.parametrize("path", ["mcp-tabular", "/mcp-tabular"])
def test_service_reference_preserves_configured_address(
    tmp_path: Path, base_url: str, path: str
) -> None:
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(
        catalog_path, service="knowledge_flow", path=path, transport="streamable_http"
    )
    server = load_mcp_catalog(
        catalog_path, services=ServiceEndpoints(base_url)
    ).servers[0]

    assert server.url == f"{base_url.rstrip('/')}/mcp-tabular"
    assert "service" not in server.model_dump()
    assert "path" not in server.model_dump()


@pytest.mark.parametrize(
    "fields",
    [
        {"service": "unknown", "path": "mcp"},
        {"path": "mcp"},
        {"service": "knowledge_flow"},
        {"service": "knowledge_flow", "path": "mcp", "url": "https://other/mcp"},
        {"service": "knowledge_flow", "transport": "inprocess", "path": "mcp"},
        {"service": "knowledge_flow", "transport": "stdio", "path": "mcp"},
    ],
)
def test_catalog_rejects_invalid_service_reference(
    tmp_path: Path, fields: dict[str, object]
) -> None:
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(catalog_path, **fields)
    with pytest.raises(ValueError):
        load_mcp_catalog(catalog_path, services=ServiceEndpoints("https://kf/api"))


@pytest.mark.parametrize(
    "path",
    [
        "",
        "https://other/mcp",
        "//other/mcp",
        "../mcp",
        "%2e%2e/mcp",
        "mcp/../other",
        "mcp?query=1",
        "mcp#fragment",
        "mcp?",
        "mcp#",
        "mcp\\other",
        "mcp\n",
        "/",
    ],
)
def test_catalog_rejects_paths_outside_service_api(tmp_path: Path, path: str) -> None:
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(catalog_path, service="knowledge_flow", path=path)
    with pytest.raises(ValueError):
        load_mcp_catalog(catalog_path, services=ServiceEndpoints("https://kf/api"))


def test_service_reference_requires_endpoint_provider(tmp_path: Path) -> None:
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(catalog_path, service="knowledge_flow", path="mcp")
    with pytest.raises(
        ValueError, match="knowledge_flow.*needs a service endpoint provider"
    ):
        load_mcp_catalog(catalog_path)


@pytest.mark.parametrize("transport", ["inprocess", "unknown"])
def test_catalog_rejects_unsupported_transport(tmp_path: Path, transport: str) -> None:
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(catalog_path, transport=transport)
    with pytest.raises(ValueError, match="transport"):
        load_mcp_catalog(catalog_path)


def test_concrete_url_remains_unchanged_with_service_provider(tmp_path: Path) -> None:
    catalog_path = tmp_path / "mcp.yaml"
    url = "https://third-party:8443/mcp?token=example"
    _write_instructions_catalog(catalog_path, url=url)
    server = load_mcp_catalog(
        catalog_path, services=ServiceEndpoints("https://kf/api")
    ).servers[0]
    assert server.url == url


def test_packaged_catalog_and_relative_instructions_load_from_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wheel resource needs no real filesystem path or runtime package."""
    from zipfile import ZipFile

    wheel = tmp_path / "catalog.zip"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("sdk_mcp_wheel_fixture/__init__.py", "")
        archive.writestr(
            "sdk_mcp_wheel_fixture/config/catalog.yaml",
            "servers: [{id: zipped, name: Zipped, prompt_file: search.md, "
            "service: knowledge_flow, path: mcp}]",
        )
        archive.writestr(
            "sdk_mcp_wheel_fixture/config/search.md",
            "# Sources\n\nCiter les résultats.\n",
        )
    monkeypatch.syspath_prepend(str(wheel))

    catalog = load_packaged_mcp_catalog(
        package="sdk_mcp_wheel_fixture",
        path_parts=("config", "catalog.yaml"),
        services=ServiceEndpoints("https://kf.example:9443/api/v2/"),
    )

    assert (
        catalog.servers[0].agent_instructions == "# Sources\n\nCiter les résultats.\n"
    )
    assert catalog.servers[0].url == "https://kf.example:9443/api/v2/mcp"


@pytest.mark.parametrize(
    "payload", ["", "[]", "version: invalid\nservers: []", "unknown: true\nservers: []"]
)
def test_catalog_rejects_invalid_envelopes(tmp_path: Path, payload: str) -> None:
    catalog = tmp_path / "invalid.yaml"
    catalog.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        load_mcp_catalog(catalog)


def test_load_mcp_catalog_rejects_duplicate_server_ids(tmp_path) -> None:
    """The external MCP catalog must fail fast when two servers share one id."""
    from fred_sdk.resources.mcp import load_mcp_catalog

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


def _write_instructions_catalog(catalog_path: Path, **fields: object) -> None:
    """Write one server so tests exercise instruction sources through the loader."""
    catalog_path.write_text(
        yaml.safe_dump({"servers": [{"id": "search", "name": "Search", **fields}]}),
        encoding="utf-8",
    )


@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("instructions", ["# Règles\n\nGarder les sources.\n\n", ""])
def test_load_mcp_catalog_reads_instruction_file_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, absolute: bool, instructions: str
) -> None:
    """File references resolve beside the catalog, independently of the cwd."""
    catalog_dir = tmp_path / "config"
    catalog_dir.mkdir()
    instructions_path = catalog_dir / "search.md"
    instructions_path.write_text(instructions, encoding="utf-8")
    catalog_path = catalog_dir / "mcp.yaml"
    _write_instructions_catalog(
        catalog_path,
        prompt_file=str(instructions_path) if absolute else "search.md",
    )
    monkeypatch.chdir(tmp_path)

    server = load_mcp_catalog(catalog_path).servers[0]

    assert server.agent_instructions == instructions
    assert "prompt_file" not in server.model_dump()


@pytest.mark.parametrize("instructions", [None, "", "Inline instructions.\n"])
def test_load_mcp_catalog_preserves_inline_instructions(
    tmp_path: Path, instructions: str | None
) -> None:
    """Existing inline catalogs keep their exact instruction value."""
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(catalog_path, agent_instructions=instructions)

    assert load_mcp_catalog(catalog_path).servers[0].agent_instructions == instructions


@pytest.mark.parametrize("inline", ["", "Inline instructions."])
def test_load_mcp_catalog_rejects_competing_instruction_sources(
    tmp_path: Path, inline: str
) -> None:
    """An explicit inline value must not be silently replaced by a file."""
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(
        catalog_path, agent_instructions=inline, prompt_file="search.md"
    )

    with pytest.raises(ValueError, match="use either agent_instructions"):
        load_mcp_catalog(catalog_path)


@pytest.mark.parametrize("reference", ["", "  ", 42, ["search.md"]])
def test_load_mcp_catalog_rejects_invalid_instruction_file_reference(
    tmp_path: Path, reference: object
) -> None:
    """A malformed file reference fails instead of silently dropping instructions."""
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(catalog_path, prompt_file=reference)

    with pytest.raises(ValueError, match="prompt_file"):
        load_mcp_catalog(catalog_path)


def test_load_mcp_catalog_fails_when_instruction_file_is_missing(
    tmp_path: Path,
) -> None:
    """Missing packaged instructions prevent boot with an incomplete prompt."""
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(catalog_path, prompt_file="missing.md")

    with pytest.raises(FileNotFoundError, match="missing.md"):
        load_mcp_catalog(catalog_path)


def test_load_mcp_catalog_reads_packaged_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resource package supplies the same text to the existing MCP capability."""
    from fred_sdk.contracts.capability.mcp import build_mcp_capability
    from fred_sdk.contracts.models import MCPServerConfiguration

    package = tmp_path / "mcp_instruction_fixture"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    instructions = "# Instructions\n\nUse retrieved evidence.\n"
    (package / "search.md").write_text(instructions, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(
        catalog_path,
        prompt_file="pkg://mcp_instruction_fixture/search.md",
    )

    server = load_mcp_catalog(catalog_path).servers[0]

    assert type(server) is MCPServerConfiguration
    assert server.agent_instructions == instructions
    assert (
        build_mcp_capability(server).prompt_group().agent_instructions
        == instructions.strip()
    )


@pytest.mark.parametrize("reference", ["pkg://", "pkg://fred_sdk", "pkg:///search.md"])
def test_load_mcp_catalog_rejects_incomplete_package_reference(
    tmp_path: Path, reference: str
) -> None:
    """An incomplete package URI cannot silently discard the instructions."""
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(catalog_path, prompt_file=reference)

    with pytest.raises(ValueError, match="require pkg://package/path"):
        load_mcp_catalog(catalog_path)


def test_load_mcp_catalog_fails_when_packaged_instructions_are_missing(
    tmp_path: Path,
) -> None:
    """A broken packaged reference fails during loading, before agent assembly."""
    catalog_path = tmp_path / "mcp.yaml"
    _write_instructions_catalog(
        catalog_path, prompt_file="pkg://fred_sdk/prompts/missing.md"
    )

    with pytest.raises(RuntimeError, match="Missing packaged Markdown resource"):
        load_mcp_catalog(catalog_path)
