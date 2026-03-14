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

from fred_core.common import ConfigFiles, load_configuration_with_config_files

from agentic_backend.common.catalog_overrides import apply_external_catalog_overrides
from agentic_backend.common.structures import Configuration
from agentic_backend.common.utils import parse_server_configuration

_config_files = ConfigFiles(logger=logging.getLogger(__name__))


def _parse_configuration(config_file: str) -> Configuration:
    configuration = parse_server_configuration(config_file)
    return apply_external_catalog_overrides(configuration)


def load_configuration() -> Configuration:
    return load_configuration_with_config_files(
        _config_files,
        _parse_configuration,
    )


def get_loaded_env_file_path() -> str | None:
    return _config_files.get_loaded_env_file_path()


def get_loaded_config_file_path() -> str | None:
    return _config_files.get_loaded_config_file_path()
