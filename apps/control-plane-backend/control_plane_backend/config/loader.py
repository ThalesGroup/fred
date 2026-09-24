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

from __future__ import annotations

import logging

from fred_core.common import (
    ConfigFiles,
    load_configuration_with_config_files,
    parse_yaml_mapping_file,
)

from control_plane_backend.config.models import Configuration

_CONFIG_FILES = ConfigFiles(logger=logging.getLogger(__name__))


def load_configuration() -> Configuration:
    def _parse_configuration(config_file: str) -> Configuration:
        payload = parse_yaml_mapping_file(config_file)
        return Configuration.model_validate(payload)

    return load_configuration_with_config_files(
        _CONFIG_FILES,
        _parse_configuration,
    )


def get_loaded_config_file_path() -> str | None:
    return _CONFIG_FILES.get_loaded_config_file_path()


def get_loaded_env_file_path() -> str | None:
    return _CONFIG_FILES.get_loaded_env_file_path()
