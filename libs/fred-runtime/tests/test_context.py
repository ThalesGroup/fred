# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Offline unit tests for PodApplicationContext, container, and dependency helpers."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, Request
from fred_runtime.app.container import build_pod_container
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.app.dependencies import (
    attach_pod_container,
    get_pod_configuration,
    get_pod_container_from_app,
)


def test_build_pod_container_returns_context_with_configuration(minimal_config) -> None:
    """build_pod_container must return a PodApplicationContext bound to the config."""
    container = build_pod_container(minimal_config)
    assert isinstance(container, PodApplicationContext)
    assert container.configuration is minimal_config


def test_pod_context_get_kpi_writer_raises_before_initialize(minimal_config) -> None:
    """get_kpi_writer() must raise RuntimeError until initialize_kpi_writer() is called."""
    container = PodApplicationContext(minimal_config)
    with pytest.raises(RuntimeError, match="initialize_kpi_writer"):
        container.get_kpi_writer()


def test_pod_context_get_kpi_writer_succeeds_after_initialize(minimal_config) -> None:
    """get_kpi_writer() must return the writer once initialize_kpi_writer() has run."""
    container = PodApplicationContext(minimal_config)
    container.initialize_kpi_writer()
    writer = container.get_kpi_writer()
    assert writer is not None


@pytest.mark.asyncio
async def test_pod_context_shutdown_cancels_kpi_tasks(minimal_config) -> None:
    """shutdown() must cancel any running KPI background tasks."""
    container = PodApplicationContext(minimal_config)

    done_event = asyncio.Event()

    async def _long_running() -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            done_event.set()
            raise

    task = asyncio.create_task(_long_running())
    container._kpi_tasks = [task]

    await container.shutdown()

    assert task.cancelled()


@pytest.mark.asyncio
async def test_pod_context_shutdown_handles_no_tasks_gracefully(minimal_config) -> None:
    """shutdown() must complete without error when no KPI tasks are running."""
    container = PodApplicationContext(minimal_config)
    await container.shutdown()  # must not raise


def test_attach_and_get_pod_container_roundtrip(minimal_config) -> None:
    """attach_pod_container / get_pod_container_from_app must be an exact roundtrip."""
    app = FastAPI()
    container = PodApplicationContext(minimal_config)
    attach_pod_container(app, container)
    retrieved = get_pod_container_from_app(app)
    assert retrieved is container


def test_get_pod_configuration_returns_config_from_container(minimal_config) -> None:
    """get_pod_configuration dependency must return the config held by the container."""
    app = FastAPI()
    container = PodApplicationContext(minimal_config)
    attach_pod_container(app, container)

    async def _receive():
        return {"type": "http.request", "body": b""}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "app": app,
    }
    request = Request(scope=scope, receive=_receive)

    config = get_pod_configuration(request)
    assert config is minimal_config


def test_ring_buffers_are_instance_level_not_global(minimal_config) -> None:
    """Each PodApplicationContext must have its own independent ring buffers."""
    from fred_runtime.app import agent_app as agent_app_module

    c1 = PodApplicationContext(minimal_config)
    c2 = PodApplicationContext(minimal_config)

    agent_app_module._emit_audit_event(c1, "info", "event_a", user_id="alice")
    agent_app_module._emit_audit_event(c2, "info", "event_b", user_id="bob")

    with c1._audit_events_lock:
        events1 = list(c1.audit_events_buffer)
    with c2._audit_events_lock:
        events2 = list(c2.audit_events_buffer)

    assert len(events1) == 1
    assert events1[0]["audit_event"] == "event_a"
    assert len(events2) == 1
    assert events2[0]["audit_event"] == "event_b"
