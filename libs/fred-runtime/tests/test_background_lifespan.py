from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml
from fastapi import FastAPI
from fred_core.scheduler import TemporalClientProvider
from fred_runtime import background
from fred_runtime.app import agent_app
from fred_runtime.app.config import AgentPodConfig


@pytest.mark.asyncio
async def test_background_worker_disabled_opens_no_scheduler_connection(monkeypatch):
    async def connect(self):
        pytest.fail("Disabled worker must not connect")

    monkeypatch.setattr(TemporalClientProvider, "get_client", connect)
    config = AgentPodConfig.model_validate(
        {
            "app": {"runtime_id": "test-pod"},
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "https://example.invalid/realm",
                    "client_id": "synthetic",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "https://example.invalid/realm",
                    "client_id": "synthetic",
                },
            },
        }
    )
    async with agent_app._background_agent_worker(
        app=FastAPI(),
        config=config,
        container=cast(Any, None),
        registry={},
        capability_registry=cast(Any, None),
    ):
        pass


@pytest.mark.asyncio
async def test_shipped_generic_scheduler_does_not_start_agent_run_worker(monkeypatch):
    async def connect(self):
        pytest.fail("Generic scheduler configuration must not connect the worker")

    monkeypatch.setattr(TemporalClientProvider, "get_client", connect)
    values_path = Path(__file__).resolve().parents[3] / "deploy/charts/fred/values.yaml"
    shipped = yaml.safe_load(values_path.read_text(encoding="utf-8"))["applications"][
        "fred-agents"
    ]["configuration"]
    config = AgentPodConfig.model_validate(
        {
            key: shipped[key]
            for key in ("app", "security", "scheduler", "platform")
            if key in shipped
        }
    )

    assert config.scheduler.enabled is True
    assert config.scheduler.agent_runs_enabled is False
    assert config.security.delegation.enabled is False
    async with agent_app._background_agent_worker(
        app=FastAPI(),
        config=config,
        container=cast(Any, None),
        registry={},
        capability_registry=cast(Any, None),
    ):
        pass


@pytest.mark.asyncio
async def test_background_worker_requires_delegation_before_connecting(monkeypatch):
    async def connect(self):
        pytest.fail("Invalid worker must not connect")

    monkeypatch.setattr(TemporalClientProvider, "get_client", connect)
    monkeypatch.setattr(agent_app, "get_delegation_runtime", lambda: None)
    monkeypatch.setattr(
        agent_app,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(rebac_engine=None)),
    )
    config = AgentPodConfig.model_validate(
        {
            "app": {"runtime_id": "test-pod"},
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "https://example.invalid/realm",
                    "client_id": "synthetic",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "https://example.invalid/realm",
                    "client_id": "synthetic",
                },
            },
            "scheduler": {
                "enabled": True,
                "agent_runs_enabled": True,
                "temporal": {"task_queue": "synthetic-queue"},
            },
        }
    )
    with pytest.raises(ValueError, match="requires delegation"):
        async with agent_app._background_agent_worker(
            app=FastAPI(),
            config=config,
            container=cast(Any, None),
            registry={},
            capability_registry=cast(Any, None),
        ):
            pytest.fail("Invalid worker must not start")


@pytest.mark.asyncio
async def test_background_worker_lifetime_closes_on_application_failure(monkeypatch):
    calls: list[str] = []
    captured: dict[str, Any] = {}

    class Worker:
        async def __aenter__(self):
            calls.append("start")
            return self

        async def __aexit__(self, *args):
            calls.append("stop")

    async def connect(self):
        assert self._log_connection_details is False
        calls.append("connect")
        return object()

    def build(**kwargs):
        captured.update(kwargs)
        return Worker()

    async def token():
        return "synthetic-workload-token"

    delegation = SimpleNamespace(
        enabled=True, ensure_usable=lambda: None, workload_token=token
    )
    rebac = SimpleNamespace(enforces_standing=True)
    monkeypatch.setattr(TemporalClientProvider, "get_client", connect)
    monkeypatch.setattr(agent_app, "get_delegation_runtime", lambda: delegation)
    monkeypatch.setattr(
        agent_app,
        "get_runtime_context",
        lambda: SimpleNamespace(config=SimpleNamespace(rebac_engine=rebac)),
    )
    monkeypatch.setattr(background, "build_background_worker", build)
    monkeypatch.setattr(
        background, "build_background_agent_executor", lambda **kwargs: object()
    )
    config = AgentPodConfig.model_validate(
        {
            "app": {"runtime_id": "test-pod"},
            "security": {
                "m2m": {
                    "enabled": False,
                    "realm_url": "https://example.invalid/realm",
                    "client_id": "synthetic",
                },
                "user": {
                    "enabled": False,
                    "realm_url": "https://example.invalid/realm",
                    "client_id": "synthetic",
                },
            },
            "scheduler": {
                "enabled": True,
                "agent_runs_enabled": True,
                "temporal": {"task_queue": "synthetic-queue"},
            },
            "platform": {"control_plane_url": "https://example.invalid"},
        }
    )
    app = FastAPI()
    with pytest.raises(RuntimeError, match="synthetic application failure"):
        async with agent_app._background_agent_worker(
            app=app,
            config=config,
            container=cast(
                Any, SimpleNamespace(get_control_plane_http_client=lambda: object())
            ),
            registry={},
            capability_registry=cast(Any, None),
        ):
            assert app.state.background_worker is not None
            raise RuntimeError("synthetic application failure")
    assert calls == ["connect", "start", "stop"]
    assert captured["task_queue"] == "synthetic-queue"
    assert app.state.background_worker is None
