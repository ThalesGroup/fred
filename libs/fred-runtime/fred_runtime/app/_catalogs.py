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

import json
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
PLATFORM_PROMPT_ENV = "FRED_PLATFORM_PROMPT_FILE"
MCP_CATALOG_DEFAULT_PATH = "./config/mcp_catalog.yaml"
MODELS_CATALOG_DEFAULT_PATH = "./config/models_catalog.yaml"
PLATFORM_PROMPT_DEFAULT_PATH = "./config/platform_prompt.json"


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


class PlatformPromptFile(BaseModel):
    """
    Shape of `config/platform_prompt.json` — the two blocks that open every
    agent's system prompt, in the order the model receives them.

    Why one file with two fields:
    - they are one thing, the head of the prompt, and reading them side by side
      is the only way to see whether they contradict each other.

    They differ in exactly one way, which the field names carry:
    - `platform_prompt` is a STARTING POINT. A platform admin edits it in the
      admin UI; the saved value lives in Postgres and reaches the runtime per
      turn on `BoundRuntimeContext.platform_prompt`, after which this text is
      no longer used.
    - `platform_instructions` is SHIPPED. Nothing edits it; the admin UI renders
      it read-only. It is what keeps agents coherent (call the tools you were
      given, never fake a call, recover from a failed one) however the prompt
      above it is rewritten.

    Both are required under `extra="forbid"`: making either optional is what
    would let a bad edit silently drop a block, since the runtime renders
    nothing for an empty one and nothing else would fail.

    `version` is not a schema version to branch on — it lets a future migration
    tell a hand-edited file from a shipped default. `_comment` documents the
    file for whoever opens it and is accepted but unused.

    How to use:
    - resolved and loaded once at pod boot by `apply_external_catalog_overrides`
    - served to control-plane by `GET /agents/platform-prompt`
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: int
    platform_prompt: str
    platform_instructions: str
    comment: str | None = Field(default=None, alias="_comment")


def resolve_platform_prompt_path() -> Path:
    """
    Resolve the canonical platform-prompt file path for one pod startup.

    Why this exists:
    - same env-override contract as the two catalogs above, so operators have
      one mental model for "pod-shipped config file" across all three.

    How to use it:
    - call during config bootstrap.

    Example:
    - `path = resolve_platform_prompt_path()`
    """

    return Path(os.getenv(PLATFORM_PROMPT_ENV, PLATFORM_PROMPT_DEFAULT_PATH))


def load_platform_prompt_file(path: str | Path) -> PlatformPromptFile:
    """
    Read and validate `platform_prompt.json`.

    Why this exists:
    - one loader keeps the file's shape validated in a single place, for both
      the prompt composer and the endpoint that serves it to control-plane.

    How to use it:
    - `file = load_platform_prompt_file("./config/platform_prompt.json")`
    """

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return PlatformPromptFile.model_validate(raw)


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

    platform_prompt_path = resolve_platform_prompt_path()
    if platform_prompt_path.exists():
        config.set_platform_prompt_file(load_platform_prompt_file(platform_prompt_path))
        logger.info(
            "[fred-runtime][config] platform prompt file loaded from %s",
            platform_prompt_path,
        )
    else:
        # Optional, unlike models_catalog.yaml: a pod with no file contributes
        # neither head block, and an admin-saved platform prompt (which arrives
        # per turn, not from here) still applies. Logged at WARNING, not INFO:
        # a pod running without the platform instructions has lost the tool
        # discipline every agent depends on, which is worth noticing.
        logger.warning(
            "[fred-runtime][config] no platform prompt file at %s; this pod "
            "contributes no platform prompt and no platform instructions",
            platform_prompt_path,
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
