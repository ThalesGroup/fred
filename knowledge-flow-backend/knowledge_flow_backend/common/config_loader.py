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

from knowledge_flow_backend.common.structures import Configuration
from knowledge_flow_backend.common.utils import parse_server_configuration

# Shared startup contract (Agentic / Knowledge Flow / Control Plane):
# docs/CONFIGURATION_AND_POLICY_CONVENTIONS.md
_config_files = ConfigFiles(logger=logging.getLogger(__name__))


def load_environment(dotenv_path: str | None = None) -> str:
    return _config_files.load_environment(dotenv_path)


def load_configuration() -> Configuration:
    load_environment()
    config_file = _config_files.resolve_config_file_path()
    configuration: Configuration = parse_server_configuration(config_file)
    _config_files.mark_config_loaded(config_file)
    return configuration


def get_loaded_env_file_path() -> str | None:
    return _config_files.get_loaded_env_file_path()


def get_loaded_config_file_path() -> str | None:
    return _config_files.get_loaded_config_file_path()
