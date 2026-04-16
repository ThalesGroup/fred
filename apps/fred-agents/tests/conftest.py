from __future__ import annotations

from collections.abc import Generator

import httpx
import pytest

from fred_runtime.client import AgentPodClient, normalize_base_url

_DEFAULT_POD_URL = "http://127.0.0.1:8010/fred/agents/v2"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--pod-url",
        default=_DEFAULT_POD_URL,
        help=(
            "Base URL of the running fred-agents pod. "
            f"Defaults to {_DEFAULT_POD_URL}. "
            "Override with --pod-url or set FRED_AGENT_POD_URL."
        ),
    )


@pytest.fixture
def pod_base_url(request: pytest.FixtureRequest) -> str:
    """
    Resolve the pod base URL for integration tests.

    Why this fixture exists:
    - scenario tests must target a running pod, not a TestClient
    - the URL should be configurable per run without editing source
    """
    import os

    cli_url = request.config.getoption("--pod-url")
    return cli_url or os.getenv("FRED_AGENT_POD_URL", _DEFAULT_POD_URL)


@pytest.fixture
def pod_client(pod_base_url: str) -> Generator[AgentPodClient, None, None]:
    """
    Provide a connected AgentPodClient for integration scenarios.

    Why this fixture exists:
    - all scenario tests share one client instance per test
    - the read timeout is generous (120 s) because LLM calls can be slow
    - the fixture owns the httpx.Client lifecycle so connections are closed
      even when a test fails mid-scenario
    """
    http = httpx.Client(
        timeout=httpx.Timeout(120.0, connect=5.0, read=None),
    )
    client = AgentPodClient(
        base_url=normalize_base_url(pod_base_url),
        http_client=http,
    )
    yield client
    http.close()
