from __future__ import annotations

import logging

from fred_core.common import ConfigFiles, load_configuration_with_config_files, parse_yaml_mapping_file

from fred_evaluation_backend.config.models import EvaluationConfig

_CONFIG_FILES = ConfigFiles(logger=logging.getLogger(__name__))


def load_configuration() -> EvaluationConfig:
    def _parse(config_file: str) -> EvaluationConfig:
        payload = parse_yaml_mapping_file(config_file)
        return EvaluationConfig.model_validate(payload)

    return load_configuration_with_config_files(_CONFIG_FILES, _parse)
