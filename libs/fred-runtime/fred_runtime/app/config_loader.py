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
Configuration loader for Fred agent pods.

Why this exists:
- Every Fred backend loads config the same way: read `.env`, then parse a YAML
  file into a typed Pydantic model.
- `ConfigFiles` and `load_configuration_with_config_files` in fred-core already
  implement this pattern (same code used by agentic-backend).
- This module wires that pattern to `AgentPodConfig`.

How to use it:
- Place `config/configuration.yaml` and optionally `config/.env` in your pod.
- Call `load_agent_pod_config()` in `main.py`.
- Override the config file path via the `CONFIG_FILE` env var.
- Override the env file path via the `ENV_FILE` env var.

Example:
    from fred_runtime.app import load_agent_pod_config, create_agent_app

    config = load_agent_pod_config()
    app = create_agent_app(registry=REGISTRY, config=config)
"""

from __future__ import annotations

import logging

from fred_core.common import ConfigFiles, load_configuration_with_config_files

from ._catalogs import apply_external_catalog_overrides
from .config import AgentPodConfig

logger = logging.getLogger(__name__)

_config_files = ConfigFiles(logger=logger)


def _parse_agent_pod_config(config_file: str) -> AgentPodConfig:
    """
    Parse a YAML configuration file into AgentPodConfig.

    Why a separate function:
    - `load_configuration_with_config_files` accepts a parser callback
    - this keeps the YAML→Pydantic conversion isolated and testable
    - external models/MCP catalogs must be applied consistently after the main
      YAML file is validated

    How to use it:
    - called indirectly by `load_agent_pod_config()`

    Example:
    - `config = _parse_agent_pod_config("./config/configuration.yaml")`
    """
    from fred_core.common import parse_yaml_mapping_file

    payload = parse_yaml_mapping_file(config_file)
    configuration = AgentPodConfig.model_validate(payload)
    return apply_external_catalog_overrides(configuration)


def load_agent_pod_config() -> AgentPodConfig:
    """
    Load the agent pod configuration from YAML, env file, and external catalogs.

    Selection order (same as agentic-backend):
    1. `ENV_FILE` env var → `.env` path (default: `./config/.env`)
    2. `CONFIG_FILE` env var → YAML path (default: `./config/configuration.yaml`)
    3. `FRED_MODELS_CATALOG_FILE` optionally overrides
       `./config/models_catalog.yaml`
    4. `FRED_MCP_CATALOG_FILE` optionally overrides `./config/mcp_catalog.yaml`

    Raises:
    - FileNotFoundError if the YAML config file is not found.

    Example:
        config = load_agent_pod_config()
        app = create_agent_app(registry=REGISTRY, config=config)
    """
    return load_configuration_with_config_files(_config_files, _parse_agent_pod_config)


def get_loaded_env_file_path() -> str | None:
    """Return the env file path that was loaded at startup."""
    return _config_files.get_loaded_env_file_path()


def get_loaded_config_file_path() -> str | None:
    """Return the YAML config file path that was loaded at startup."""
    return _config_files.get_loaded_config_file_path()
