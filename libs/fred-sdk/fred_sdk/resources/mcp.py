# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Load MCP catalogs and their instruction files without a runtime dependency."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fred_sdk.contracts.models import MCPServerConfiguration
from fred_sdk.contracts.services import FredService, ServiceEndpointsPort
from fred_sdk.resources.packaged import load_packaged_resource
from fred_sdk.resources.prompts import load_packaged_markdown


class McpCatalog(BaseModel):
    """Resolved servers shared by capability registration and transport setup."""

    model_config = ConfigDict(extra="forbid")
    servers: list[MCPServerConfiguration] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_duplicate_server_ids(self) -> McpCatalog:
        """Reject ambiguous identifiers, including across installed catalogs."""
        seen: set[str] = set()
        duplicates: list[str] = []
        for server in self.servers:
            if server.id in seen and server.id not in duplicates:
                duplicates.append(server.id)
            seen.add(server.id)
        if duplicates:
            identifiers = ", ".join(repr(server_id) for server_id in duplicates)
            raise ValueError(f"Duplicate MCP server id(s) in catalog: {identifiers}")
        return self

    def get_server(self, id: str) -> MCPServerConfiguration | None:
        """Look up an enabled server for transport binding."""
        return next(
            (server for server in self.servers if server.id == id and server.enabled),
            None,
        )


class _McpCatalogServer(MCPServerConfiguration):
    """File-only references are resolved before exposing server metadata."""

    prompt_file: str | None = Field(
        default=None, min_length=1, pattern=r"\S", exclude=True
    )
    service: FredService | None = Field(default=None, exclude=True)
    path: str | None = Field(default=None, min_length=1, exclude=True)

    @model_validator(mode="after")
    def _check_service_reference(self) -> _McpCatalogServer:
        if self.service is None:
            if self.path is not None:
                raise ValueError(f"MCP '{self.id}': path requires a service")
            return self
        if self.url is not None:
            raise ValueError(f"MCP '{self.id}': use either service or url, not both")
        if self.transport not in {"sse", "streamable_http"}:
            raise ValueError(f"MCP '{self.id}': service requires an HTTP transport")
        if self.path is None:
            raise ValueError(f"MCP '{self.id}': HTTP service requires a path")
        decoded = unquote(self.path)
        parts = urlsplit(decoded)
        if (
            parts.scheme
            or parts.netloc
            or "?" in decoded
            or "#" in decoded
            or not decoded.strip("/")
            or "\\" in decoded
            or any(char.isspace() for char in decoded)
            or any(segment in {".", ".."} for segment in decoded.split("/"))
        ):
            raise ValueError(
                f"MCP '{self.id}': path must be relative to the service API"
            )
        return self

    @model_validator(mode="after")
    def _check_instruction_source(self) -> _McpCatalogServer:
        """Reject competing sources before reading any instruction file."""
        if self.prompt_file is not None and self.agent_instructions is not None:
            raise ValueError("use either agent_instructions or prompt_file, not both")
        return self


class _McpCatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"] = "v1"
    servers: list[_McpCatalogServer] = Field(default_factory=list)


def _load_catalog(
    source: Traversable,
    instructions_dir: Traversable,
    services: ServiceEndpointsPort | None,
) -> McpCatalog:
    """Decode a filesystem or wheel resource with one validation path."""
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if payload is None:
        raise ValueError(f"Catalog file is empty: {source}")
    if not isinstance(payload, dict):
        raise ValueError(f"Catalog file must be a YAML mapping object: {source}")
    raw = _McpCatalogFile.model_validate(payload)
    catalog = McpCatalog(
        servers=[
            MCPServerConfiguration.model_validate(server.model_dump())
            for server in raw.servers
        ]
    )
    for entry, server in zip(raw.servers, catalog.servers, strict=True):
        if entry.service is not None and entry.path is not None:
            if services is None:
                raise ValueError(
                    f"MCP '{entry.id}': service '{entry.service}' needs a service endpoint provider"
                )
            base_url = services.get_base_url(entry.service)
            server.url = f"{base_url.rstrip('/')}/{entry.path.lstrip('/')}"
        reference = entry.prompt_file
        if reference is None:
            continue
        if reference.startswith("pkg://"):
            package, _, resource = reference.removeprefix("pkg://").partition("/")
            if not package or not resource:
                raise ValueError(
                    "prompt_file package references require pkg://package/path"
                )
            server.agent_instructions = load_packaged_markdown(
                package=package, path_parts=resource.split("/")
            )
        else:
            resource_path = (
                Path(reference)
                if Path(reference).is_absolute()
                else instructions_dir.joinpath(reference)
            )
            server.agent_instructions = resource_path.read_text(encoding="utf-8")
    return catalog


def load_mcp_catalog(
    path: str | Path, *, services: ServiceEndpointsPort | None = None
) -> McpCatalog:
    """Read an external catalog; relative instruction paths resolve beside it."""
    source = Path(path)
    return _load_catalog(source, source.parent, services)


def load_packaged_mcp_catalog(
    *,
    package: str,
    path_parts: Sequence[str] = ("mcp_catalog.yaml",),
    services: ServiceEndpointsPort | None = None,
) -> McpCatalog:
    """Load a package's catalog and instructions from an installed wheel or checkout."""
    return load_packaged_resource(
        package=package,
        path_parts=path_parts,
        decoder=lambda source: _load_catalog(
            source, files(package).joinpath(*path_parts[:-1]), services
        ),
        missing_resource_kind="MCP catalog",
    )
