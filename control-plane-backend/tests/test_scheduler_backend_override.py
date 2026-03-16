from __future__ import annotations

from collections.abc import Generator

import pytest
from fred_core.common import parse_yaml_mapping_file

from control_plane_backend.application_context import ApplicationContext
from control_plane_backend.common.structures import Configuration


def _config_with_scheduler_backend(backend: str) -> Configuration:
    payload = parse_yaml_mapping_file("./config/configuration.yaml")
    payload["scheduler"]["enabled"] = True
    payload["scheduler"]["backend"] = backend
    return Configuration.model_validate(payload)


@pytest.fixture(autouse=True)
def _reset_application_context() -> Generator[None, None, None]:
    ApplicationContext._instance = None
    yield
    ApplicationContext._instance = None
