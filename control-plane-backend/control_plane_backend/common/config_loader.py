from __future__ import annotations

import logging

import yaml
from fred_core import ConfigFiles

from control_plane_backend.common.structures import Configuration

logger = logging.getLogger(__name__)

# Shared startup contract (Agentic / Knowledge Flow / Control Plane):
# docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md
_CONFIG_FILES = ConfigFiles(logger=logger)


def get_loaded_config_file_path() -> str | None:
    """Return the effective YAML configuration path loaded at startup.

    Example:
    - `./config/configuration.yaml` for API mode.
    - `./config/configuration_worker.yaml` for worker mode.
    """
    return _CONFIG_FILES.get_loaded_config_file_path()


def get_loaded_env_file_path() -> str | None:
    """Return the effective env file path loaded at startup.

    This is intentionally separate from config file tracking so support teams
    can verify both data sources independently.
    """
    return _CONFIG_FILES.get_loaded_env_file_path()


def load_environment(dotenv_path: str | None = None) -> str:
    """Load environment variables following Fred conventions.

    Resolution order:
    1. Explicit argument.
    2. `ENV_FILE`.
    3. `./config/.env`.
    """
    return _CONFIG_FILES.load_environment(dotenv_path)


def load_configuration() -> Configuration:
    """Load and validate the Control Plane YAML configuration.

    Startup order:
    1. Load env file.
    2. Resolve YAML path from `CONFIG_FILE`.
    3. Parse YAML and validate against `Configuration`.

    Example:
    - Setting `CONFIG_FILE=./config/configuration_prod.yaml` switches the app
      to production-like runtime settings without code changes.
    """
    load_environment()

    config_file = _CONFIG_FILES.resolve_config_file_path()

    with open(config_file, encoding="utf-8") as file:
        payload = yaml.safe_load(file)
    if payload is None:
        raise ValueError(f"Configuration file is empty: {config_file}")
    if not isinstance(payload, dict):
        raise ValueError(f"Configuration file must be a mapping object: {config_file}")

    cfg = Configuration.model_validate(payload)
    _CONFIG_FILES.mark_config_loaded(config_file)
    return cfg
