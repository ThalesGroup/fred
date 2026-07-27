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

"""
TURN-01 instrumentation: control-plane previously had no periodic
process.*/event_loop_lag_ms sampler at all (unlike fred-runtime and
knowledge-flow, which already call the same shared `emit_process_kpis` /
`emit_sql_pool_kpis`). These tests lock the wiring in `ApplicationContext`.
"""

from __future__ import annotations

import asyncio

import pytest
from control_plane_backend.app import context as context_module
from control_plane_backend.app.context import ApplicationContext
from control_plane_backend.config.loader import load_configuration


def _context(monkeypatch: pytest.MonkeyPatch) -> ApplicationContext:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    return ApplicationContext(load_configuration())


@pytest.mark.asyncio
async def test_start_kpi_tasks_schedules_process_and_pool_samplers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context(monkeypatch)
    ctx.configuration.observability.kpi.process_metrics_interval_sec = 7

    observed: dict[str, object] = {}

    async def _neverending_process(interval_s: float, kpi_writer) -> None:
        observed["process_task"] = (interval_s, type(kpi_writer).__name__)
        await asyncio.sleep(3600)

    async def _neverending_pool(
        interval_s, kpi_writer, engine, *, pool_name="postgres"
    ):
        observed["pool_task"] = (interval_s, pool_name, engine is not None)
        await asyncio.sleep(3600)

    monkeypatch.setattr(context_module, "emit_process_kpis", _neverending_process)
    monkeypatch.setattr(context_module, "emit_sql_pool_kpis", _neverending_pool)

    ctx.start_kpi_tasks()
    await asyncio.sleep(0)  # let the scheduled tasks start running

    assert observed["process_task"] == (7.0, "KPIWriter")
    assert observed["pool_task"] == (7.0, "control-plane-postgres", True)

    await ctx.shutdown()
    assert ctx._kpi_tasks == []


@pytest.mark.asyncio
async def test_start_kpi_tasks_is_a_no_op_when_interval_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context(monkeypatch)
    assert ctx.configuration.observability.kpi.process_metrics_interval_sec == 0

    called = False

    async def _fail(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(context_module, "emit_process_kpis", _fail)
    monkeypatch.setattr(context_module, "emit_sql_pool_kpis", _fail)

    ctx.start_kpi_tasks()
    await asyncio.sleep(0)

    assert called is False
    assert ctx._kpi_tasks == []


@pytest.mark.asyncio
async def test_get_rebac_engine_receives_the_kpi_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context(monkeypatch)
    captured: dict[str, object] = {}

    def _fake_rebac_factory(security_config, *, kpi_writer=None):
        captured["kpi_writer"] = kpi_writer
        from fred_core.security.rebac.noop_engine import NoopRebacEngine

        return NoopRebacEngine()

    monkeypatch.setattr(context_module, "rebac_factory", _fake_rebac_factory)

    ctx.get_rebac_engine()

    assert captured["kpi_writer"] is ctx.get_kpi_writer()
