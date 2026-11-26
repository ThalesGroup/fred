# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The shipped chart must satisfy runtime transport validation, not just JSON Schema."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from knowledge_flow_worker.common.structures import ManagerProcessingConfig

CHART = Path(__file__).resolve().parents[4] / "deploy/charts/fred/values.yaml"


def processing_values() -> dict:
    values = yaml.safe_load(CHART.read_text())
    return values["applications"]["knowledge-flow-worker"]["configuration"]["manager_processing"]


def test_chart_processing_defaults_require_tls() -> None:
    config = ManagerProcessingConfig.model_validate(processing_values())
    assert not config.allow_insecure


@pytest.mark.parametrize("field", ["url", "issuer", "endpoint"])
def test_http_requires_explicit_local_opt_in(field: str) -> None:
    values = processing_values()
    values[field] = "http://local.example.test"
    with pytest.raises(ValidationError):
        ManagerProcessingConfig.model_validate(values)
    values["allow_insecure"] = True
    assert ManagerProcessingConfig.model_validate(values).allow_insecure
