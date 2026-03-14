from __future__ import annotations

from collections.abc import Generator

import pytest
from fred_core.common import parse_yaml_mapping_file
from fred_core.scheduler import FRED_STANDALONE_RUNTIME_ENV, SchedulerBackend

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


def test_control_plane_scheduler_backend_defaults_to_temporal_without_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(FRED_STANDALONE_RUNTIME_ENV, raising=False)
    config = _config_with_scheduler_backend("temporal")
    context = ApplicationContext(config)
    assert context.get_scheduler_backend() == SchedulerBackend.TEMPORAL


def test_control_plane_scheduler_backend_forces_memory_with_standalone_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(FRED_STANDALONE_RUNTIME_ENV, "true")
    config = _config_with_scheduler_backend("temporal")
    context = ApplicationContext(config)
    assert context.get_scheduler_backend() == SchedulerBackend.MEMORY

    with pytest.raises(ValueError, match="scheduler backend is memory"):
        context.get_temporal_client_provider()
