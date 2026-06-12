from __future__ import annotations

import os
from functools import lru_cache

from fred_evaluation_backend.config.models import EvaluationConfig


@lru_cache(maxsize=1)
def load_configuration() -> EvaluationConfig:
    config_file = os.environ.get("CONFIG_FILE")
    if config_file and os.path.exists(config_file):
        import yaml
        with open(config_file) as f:
            data = yaml.safe_load(f) or {}
        return EvaluationConfig(**data)
    return EvaluationConfig()