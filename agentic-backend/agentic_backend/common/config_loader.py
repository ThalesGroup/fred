# Copyright Thales 2025
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

from __future__ import annotations

import logging

from fred_core import ConfigFiles

from agentic_backend.common.catalog_overrides import apply_external_catalog_overrides
from agentic_backend.common.structures import Configuration
from agentic_backend.common.utils import parse_server_configuration

# Shared startup contract (Agentic / Knowledge Flow / Control Plane):
# docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md
_config_files = ConfigFiles(logger=logging.getLogger(__name__))


def load_environment(dotenv_path: str | None = None) -> str:
    """Load ENV_FILE into process env and remember the effective env file path.

    Fred convention:
    - ENV file contains secrets and deployment-specific variables.
    - This function handles only that source.
    """
    return _config_files.load_environment(dotenv_path)


def load_configuration() -> Configuration:
    """Load backend YAML configuration and apply Agentic catalog overrides.

    Fred convention:
    - CONFIG_FILE points to the structured application config (models, stores, limits).
    - ENV_FILE is loaded first because YAML parsing may depend on env values.
    """
    load_environment()
    config_file = _config_files.resolve_config_file_path()
    configuration: Configuration = parse_server_configuration(config_file)
    configuration = apply_external_catalog_overrides(configuration)
    _config_files.mark_config_loaded(config_file)
    return configuration


def get_loaded_env_file_path() -> str | None:
    """Return the effective ENV_FILE path used at startup.

    Kept separate from config path so logs/diagnostics can tell where secrets/env
    came from, independently from which YAML config profile was loaded.
    """
    return _config_files.get_loaded_env_file_path()


def get_loaded_config_file_path() -> str | None:
    """Return the effective CONFIG_FILE path used at startup.

    This is separate from ENV_FILE on purpose: Fred allows same env file with
    different YAML profiles (dev/prod/worker), and diagnostics must show both.
    """
    return _config_files.get_loaded_config_file_path()
