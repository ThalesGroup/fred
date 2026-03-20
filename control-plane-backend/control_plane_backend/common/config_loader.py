from __future__ import annotations

import logging

from fred_core.common import (
    ConfigFiles,
    load_configuration_with_config_files,
    parse_yaml_mapping_file,
)

from control_plane_backend.common.structures import Configuration

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
