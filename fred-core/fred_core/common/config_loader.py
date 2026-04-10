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

from typing import Callable, TypeVar

import yaml

from .config_files import ConfigFiles

TConfig = TypeVar("TConfig")


def parse_yaml_mapping_file(config_file: str) -> dict:
    """Load a YAML file and ensure it is a non-empty mapping."""
    with open(config_file, encoding="utf-8") as file:
        payload = yaml.safe_load(file)
    if payload is None:
        raise ValueError(f"Configuration file is empty: {config_file}")
    if not isinstance(payload, dict):
        raise ValueError(f"Configuration file must be a mapping object: {config_file}")
    return payload


def load_configuration_with_config_files(
    config_files: ConfigFiles,
    parser: Callable[[str], TConfig],
    dotenv_path: str | None = None,
) -> TConfig:
    """Load env + config path using ConfigFiles and parse via callback."""
    config_files.load_environment(dotenv_path)
    config_file = config_files.resolve_config_file_path()
    configuration = parser(config_file)
    config_files.mark_config_loaded(config_file)
    return configuration
