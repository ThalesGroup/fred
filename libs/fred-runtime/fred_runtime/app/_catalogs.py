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
from collections.abc import Callable
from importlib.metadata import entry_points
from pathlib import Path
from typing import cast

from fred_sdk.contracts.models import MCPServerConfiguration
from fred_sdk.contracts.services import ServiceEndpointsPort
from fred_sdk.resources.mcp import McpCatalog
from fred_sdk.resources.mcp import McpCatalog as _LoadedMcpConfiguration
from fred_sdk.resources.mcp import load_mcp_catalog as load_mcp_catalog
from pydantic import BaseModel, ConfigDict, Field

from .config import AgentPodConfig
from .service_endpoints import ConfiguredServiceEndpoints

__all__ = ["_LoadedMcpConfiguration", "load_mcp_catalog"]

logger = logging.getLogger(__name__)

MCP_CATALOG_ENV = "FRED_MCP_CATALOG_FILE"
MCP_EXTERNAL_CATALOG_ENV = "FRED_MCP_EXTERNAL_CATALOG_FILE"
MODELS_CATALOG_ENV = "FRED_MODELS_CATALOG_FILE"
PLATFORM_PROMPT_ENV = "FRED_PLATFORM_PROMPT_FILE"
MCP_CATALOG_DEFAULT_PATH = "./config/mcp_catalog.yaml"
MCP_EXTERNAL_CATALOG_DEFAULT_PATH = "./config/mcp_catalog_external.yaml"
MODELS_CATALOG_DEFAULT_PATH = "./config/models_catalog.yaml"
PLATFORM_PROMPT_DEFAULT_PATH = "./config/platform_prompt.json"


def load_installed_mcp_catalogs(services: ServiceEndpointsPort) -> McpCatalog:
    """Resolve installed catalog providers once, before MCP transport and registration."""
    servers: list[MCPServerConfiguration] = []
    for entry in sorted(
        entry_points(group="fred.mcp_catalogs"), key=lambda ep: (ep.name, ep.value)
    ):
        try:
            provider = entry.load()
            if not callable(provider):
                raise TypeError(
                    "expected a catalog loader accepting a service endpoint provider"
                )
            catalog = cast(Callable[[ServiceEndpointsPort], object], provider)(services)
            if not isinstance(catalog, McpCatalog):
                raise TypeError("catalog loader must return McpCatalog")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load MCP catalog '{entry.name}' ({entry.value}): {exc}"
            ) from exc
        servers.extend(catalog.servers)
    return McpCatalog(servers=servers)


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
    services = ConfiguredServiceEndpoints(config)
    if os.getenv(MCP_CATALOG_ENV) or mcp_catalog_path.exists():
        if not mcp_catalog_path.exists():
            config.set_mcp_configuration(None)
            logger.info(
                "[fred-runtime][config] MCP catalog not found at %s; pod starts with no external MCP servers",
                mcp_catalog_path,
            )
            return config

        catalog = load_mcp_catalog(mcp_catalog_path, services=services)
        config.set_mcp_configuration(catalog)
        logger.info(
            "[fred-runtime][config] loaded MCP catalog from %s (servers=%d)",
            mcp_catalog_path,
            len(catalog.servers),
        )
        return config

    installed = load_installed_mcp_catalogs(services)
    selected_external = os.getenv(MCP_EXTERNAL_CATALOG_ENV)
    external_path = Path(selected_external or MCP_EXTERNAL_CATALOG_DEFAULT_PATH)
    if selected_external and not external_path.exists():
        raise FileNotFoundError(
            f"Selected external MCP catalog file was not found: {external_path}"
        )
    external = (
        load_mcp_catalog(external_path, services=services)
        if external_path.exists()
        else McpCatalog()
    )
    catalog = McpCatalog(servers=[*installed.servers, *external.servers])
    config.set_mcp_configuration(catalog if catalog.servers else None)
    logger.info(
        "[fred-runtime][config] loaded MCP catalogs (installed=%d external=%d)",
        len(installed.servers),
        len(external.servers),
    )
    return config
