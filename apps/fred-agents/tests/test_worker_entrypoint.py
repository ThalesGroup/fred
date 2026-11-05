# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import AsyncMock, Mock

import pytest
from fred_agents import __main__ as entrypoint
from fred_runtime.app import preparation_worker
from fred_runtime.app.config import AgentPodConfig


@pytest.mark.parametrize("mode", ["api", "worker"])
def test_api_is_the_default_and_worker_never_starts_http(monkeypatch, tmp_path, mode):
    config = AgentPodConfig.model_validate(
        {
            "app": {"runtime_id": "test"},
            "security": {
                "user": {
                    "enabled": False,
                    "realm_url": "http://localhost/r",
                    "client_id": "test",
                },
                "m2m": {
                    "enabled": False,
                    "realm_url": "http://localhost/r",
                    "client_id": "test",
                },
                "authorized_origins": [],
            },
        }
    )
    monkeypatch.setattr(entrypoint, "load_agent_pod_config", lambda: config)
    monkeypatch.setattr(
        "sys.argv", ["fred_agents"] + (["--mode", "worker"] if mode == "worker" else [])
    )
    http = Mock()
    worker = AsyncMock()
    monkeypatch.setattr(entrypoint.uvicorn, "run", http)
    monkeypatch.setattr(preparation_worker, "run_preparation_worker", worker)
    entrypoint.main()
    if mode == "worker":
        worker.assert_awaited_once_with(config)
        http.assert_not_called()
    else:
        http.assert_called_once()
        assert http.call_args.args == ("fred_agents.main:app",)
        worker.assert_not_called()
