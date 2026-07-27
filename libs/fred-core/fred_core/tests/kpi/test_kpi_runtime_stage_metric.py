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
Offline unit tests for fred_core.kpi.kpi_runtime_stage_metric.runtime_stage_timer
/ record_runtime_stage_metric — the dedicated, closed-set contract for
TURN-01's three pre-LLM stages (pod_authz, runtime_binding,
runtime_binding_internal), isolated from the generic app.phase_latency_ms
mechanism so it can be safely promoted to a Prometheus label.
"""

from __future__ import annotations

import pytest
from fred_core.kpi.kpi_runtime_stage_metric import runtime_stage_timer
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter


class _RecordingKPIWriter(NoOpKPIWriter):
    def __init__(self) -> None:
        self.emitted: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.emitted.append(kwargs)


@pytest.mark.asyncio
async def test_runtime_stage_timer_emits_runtime_stage_latency_ms() -> None:
    writer = _RecordingKPIWriter()

    async with runtime_stage_timer(writer, "pod_authz"):
        pass

    assert len(writer.emitted) == 1
    event = writer.emitted[0]
    assert event["name"] == "runtime.stage_latency_ms"
    assert event["type"] == "timer"
    assert event["dims"] == {"runtime_stage": "pod_authz"}
    assert event.get("trace") is None
    assert event["value"] >= 0.0


@pytest.mark.asyncio
async def test_runtime_stage_timer_sets_trace_id_when_provided() -> None:
    writer = _RecordingKPIWriter()

    async with runtime_stage_timer(writer, "runtime_binding", trace_id="req-123"):
        pass

    assert writer.emitted[0]["trace"] == {"trace_id": "req-123"}


@pytest.mark.asyncio
async def test_runtime_stage_timer_emits_for_each_closed_value() -> None:
    writer = _RecordingKPIWriter()

    for stage in ("pod_authz", "runtime_binding", "runtime_binding_internal"):
        async with runtime_stage_timer(writer, stage):
            pass

    stages = [e["dims"]["runtime_stage"] for e in writer.emitted]
    assert stages == ["pod_authz", "runtime_binding", "runtime_binding_internal"]


@pytest.mark.asyncio
async def test_runtime_stage_timer_still_emits_on_exception() -> None:
    """
    Functional-regression item C: errors must propagate exactly as before —
    the timer must not swallow the exception, but must still emit the metric
    (matching phase_timer's existing try/finally shape).
    """
    writer = _RecordingKPIWriter()

    with pytest.raises(ValueError):
        async with runtime_stage_timer(writer, "pod_authz"):
            raise ValueError("boom")

    assert len(writer.emitted) == 1
    assert writer.emitted[0]["dims"] == {"runtime_stage": "pod_authz"}
