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

import pytest

from fred_core.common import (
    ConfigFiles,
    load_configuration_with_config_files,
    parse_yaml_mapping_file,
)


def test_parse_yaml_mapping_file_success(tmp_path) -> None:
    config_file = tmp_path / "configuration.yaml"
    config_file.write_text("app:\n  name: fred\n", encoding="utf-8")

    payload = parse_yaml_mapping_file(str(config_file))

    assert payload == {"app": {"name": "fred"}}


def test_parse_yaml_mapping_file_rejects_empty_file(tmp_path) -> None:
    config_file = tmp_path / "configuration.yaml"
    config_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="Configuration file is empty"):
        parse_yaml_mapping_file(str(config_file))


def test_parse_yaml_mapping_file_rejects_non_mapping(tmp_path) -> None:
    config_file = tmp_path / "configuration.yaml"
    config_file.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Configuration file must be a mapping object"):
        parse_yaml_mapping_file(str(config_file))


def test_load_configuration_with_config_files_tracks_loaded_paths(
    tmp_path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    config_file = tmp_path / "configuration.yaml"

    env_file.write_text("FRED_CORE_CONFIG_LOADER_TEST_KEY=from-env\n", encoding="utf-8")
    config_file.write_text("app:\n  name: fred\n", encoding="utf-8")

    monkeypatch.delenv("FRED_CORE_CONFIG_LOADER_TEST_KEY", raising=False)
    monkeypatch.delenv("ENV_FILE", raising=False)
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    config_files = ConfigFiles(
        logger=logging.getLogger("fred_core.tests.config_loader"),
        default_env_file=str(env_file),
        default_config_file=str(config_file),
    )

    def parser(path: str) -> dict:
        assert path == str(config_file)
        return parse_yaml_mapping_file(path)

    configuration = load_configuration_with_config_files(
        config_files,
        parser,
    )

    assert configuration == {"app": {"name": "fred"}}
    assert config_files.get_loaded_env_file_path() == str(env_file)
    assert config_files.get_loaded_config_file_path() == str(config_file)
