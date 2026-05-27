# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Internal catalog bootstrap helpers for Fred agent pods.

Why this module exists:
- pod apps should bootstrap the same external catalog files as agentic-backend
  without duplicating that logic in every pod
- `load_agent_pod_config()` must remain the single entrypoint pod authors use,
  while path resolution and YAML parsing stay internal to `fred-runtime`

How to use it:
- call `apply_external_catalog_overrides(config)` immediately after parsing the
  main `configuration.yaml`
- do not import this module from pod code; it is an internal bootstrap detail

Example:
    payload = AgentPodConfig.model_validate(raw_payload)
    config = apply_external_catalog_overrides(payload)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from fred_sdk.contracts.models import MCPServerConfiguration
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import AgentPodConfig

logger = logging.getLogger(__name__)

MCP_CATALOG_ENV = "FRED_MCP_CATALOG_FILE"
MODELS_CATALOG_ENV = "FRED_MODELS_CATALOG_FILE"
MCP_CATALOG_DEFAULT_PATH = "./config/mcp_catalog.yaml"
MODELS_CATALOG_DEFAULT_PATH = "./config/models_catalog.yaml"


class _CatalogFile(BaseModel):
    """Strict base model for pod catalog file payloads."""

    model_config = ConfigDict(extra="forbid")


class _LoadedMcpConfiguration(BaseModel):
    """
    Internal MCP configuration object attached to `AgentPodConfig`.

    Why this exists:
    - the pod runtime still needs a `servers + get_server(...)` object for MCP
      wiring after the public `AgentPodConfig` schema stops exposing an `mcp`
      section

    How to use it:
    - create it only inside the catalog bootstrap helpers and attach it with
      `config.set_mcp_configuration(...)`

    Example:
    - `config.set_mcp_configuration(_LoadedMcpConfiguration(servers=[...]))`
    """

    servers: list[MCPServerConfiguration] = Field(default_factory=list)

    def get_server(self, id: str) -> MCPServerConfiguration | None:
        """
        Return one enabled MCP server from the loaded catalog.

        Why this exists:
        - runtime MCP adapters expect a configuration object with `get_server`

        How to use it:
        - call from runtime adapter code through the shared MCP configuration

        Example:
        - `server = loaded_config.get_server("mcp-knowledge-flow-corpus")`
        """

        for server in self.servers:
            if server.id == id and server.enabled:
                return server
        return None


class _McpCatalog(_CatalogFile):
    """
    File contract for `mcp_catalog.yaml`.

    Why this exists:
    - pod startup needs the same strict YAML validation as agentic-backend when
      loading the external MCP catalog

    How to use it:
    - created indirectly through `load_mcp_catalog(path)`

    Example:
    - `catalog = load_mcp_catalog("./config/mcp_catalog.yaml")`
    """

    version: Literal["v1"] = "v1"
    servers: list[MCPServerConfiguration] = Field(default_factory=list)

    @model_validator(mode="after")
    def _reject_duplicate_server_ids(self) -> "_McpCatalog":
        """
        Reject duplicate MCP server ids in one catalog.

        Why this exists:
        - the managed-agent contract now stores per-server config keyed by MCP
          server id, so duplicates would make selection and config resolution
          ambiguous and unsafe

        How to use it:
        - triggered automatically during `_McpCatalog.model_validate(...)`

        Example:
        - `load_mcp_catalog("./config/mcp_catalog.yaml")`
        """

        seen: set[str] = set()
        duplicates: list[str] = []
        for server in self.servers:
            if server.id in seen and server.id not in duplicates:
                duplicates.append(server.id)
            seen.add(server.id)
        if duplicates:
            duplicates_text = ", ".join(repr(server_id) for server_id in duplicates)
            raise ValueError(
                f"Duplicate MCP server id(s) in catalog: {duplicates_text}"
            )
        return self


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """
    Load one YAML mapping file from disk.

    Why this exists:
    - both model and MCP catalog bootstrap need the same strict "YAML mapping"
      validation rule

    How to use it:
    - pass a catalog file path and receive the decoded mapping payload

    Example:
    - `payload = _load_yaml_mapping(Path("./config/mcp_catalog.yaml"))`
    """

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        raise ValueError(f"Catalog file is empty: {path}")
    if not isinstance(payload, dict):
        raise ValueError(f"Catalog file must be a YAML mapping object: {path}")
    return payload


def load_mcp_catalog(path: str | Path) -> _McpCatalog:
    """
    Load and validate an external MCP catalog file.

    Why this exists:
    - pod bootstrap should reuse the same strict MCP catalog contract as the
      backend instead of treating `mcp_catalog.yaml` as ad-hoc YAML

    How to use it:
    - call from `apply_external_catalog_overrides(...)` when external MCP
      servers should populate the internal pod MCP configuration

    Example:
    - `catalog = load_mcp_catalog("./config/mcp_catalog.yaml")`
    """

    catalog_path = Path(path)
    return _McpCatalog.model_validate(_load_yaml_mapping(catalog_path))


def resolve_models_catalog_path() -> Path:
    """
    Resolve the canonical models catalog path for one pod startup.

    Why this exists:
    - pod startup should expose one canonical model-catalog override while
      keeping `AgentPodConfig` as the public structured config model

    How to use it:
    - call during config bootstrap; the returned path should be attached to the
      resolved pod config as internal runtime data

    Example:
    - `config.set_models_catalog_path(str(resolve_models_catalog_path()))`
    """

    explicit = os.getenv(MODELS_CATALOG_ENV)
    if explicit:
        return Path(explicit)

    return Path(MODELS_CATALOG_DEFAULT_PATH)


def resolve_mcp_catalog_path() -> Path:
    """
    Resolve the canonical MCP catalog path for one pod startup.

    Why this exists:
    - pod startup should follow the same MCP catalog env-var override contract
      as agentic-backend

    How to use it:
    - call when pod startup needs to populate the runtime MCP configuration
      from an external `mcp_catalog.yaml`

    Example:
    - `catalog_path = resolve_mcp_catalog_path()`
    """

    return Path(os.getenv(MCP_CATALOG_ENV, MCP_CATALOG_DEFAULT_PATH))


def apply_external_catalog_overrides(config: AgentPodConfig) -> AgentPodConfig:
    """
    Apply external catalog files over the parsed pod configuration.

    Why this exists:
    - pods must bootstrap model-routing and MCP catalogs with backend-like
      precedence while still exposing a very small public API

    How to use it:
    - call once inside `load_agent_pod_config()` right after Pydantic
      validation and before the config is returned to application startup

    Example:
    - `return apply_external_catalog_overrides(AgentPodConfig.model_validate(raw))`
    """

    models_catalog_path = resolve_models_catalog_path()
    if not models_catalog_path.exists():
        raise FileNotFoundError(
            f"Mandatory models catalog file was not found: {models_catalog_path}"
        )
    config.set_models_catalog_path(str(models_catalog_path))
    logger.info(
        "[fred-runtime][config] models catalog path resolved to %s",
        models_catalog_path,
    )

    mcp_catalog_path = resolve_mcp_catalog_path()
    if not mcp_catalog_path.exists():
        config.set_mcp_configuration(None)
        logger.info(
            "[fred-runtime][config] MCP catalog not found at %s; pod starts with no external MCP servers",
            mcp_catalog_path,
        )
        return config

    catalog = load_mcp_catalog(mcp_catalog_path)
    config.set_mcp_configuration(
        _LoadedMcpConfiguration(
            servers=[server.model_copy(deep=True) for server in catalog.servers]
        )
    )
    logger.info(
        "[fred-runtime][config] loaded MCP catalog from %s (servers=%d)",
        mcp_catalog_path,
        len(catalog.servers),
    )
    return config
