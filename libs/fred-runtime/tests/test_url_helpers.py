"""Offline tests for fred_runtime.cli.url_helpers."""

from __future__ import annotations

from unittest.mock import patch

from fred_runtime.cli.url_helpers import (
    default_agent_pod_base_url,
    normalize_base_url,
)


def test_normalize_base_url_strips_trailing_slash() -> None:
    assert (
        normalize_base_url("http://localhost:8000/api/v1/")
        == "http://localhost:8000/api/v1"
    )


def test_normalize_base_url_no_op_when_clean() -> None:
    assert (
        normalize_base_url("http://localhost:8000/api/v1")
        == "http://localhost:8000/api/v1"
    )


def test_default_agent_pod_base_url_uses_env_var() -> None:
    with patch.dict("os.environ", {"FRED_AGENT_POD_URL": "http://custom-pod:9000/v2"}):
        url = default_agent_pod_base_url()
    assert url == "http://custom-pod:9000/v2"


def test_default_agent_pod_base_url_fallback_when_no_env_or_config() -> None:
    with (
        patch("fred_runtime.cli.url_helpers.os.getenv", return_value=None),
        patch(
            "fred_runtime.cli.url_helpers.load_configuration_yaml", return_value=None
        ),
        patch(
            "fred_runtime.cli.url_helpers.default_configuration_file",
            return_value="/tmp/none.yaml",
        ),
    ):
        url = default_agent_pod_base_url()
    assert url == "http://127.0.0.1:8000/api/v1"
