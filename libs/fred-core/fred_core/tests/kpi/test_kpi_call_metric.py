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
Offline unit tests for fred_core.kpi.kpi_call_metric.call_metric — the shared
counter+timer helper for bounded-cardinality "operation" instrumentation
(OpenFGA calls today; reusable for any future call site with the same shape).
"""

from __future__ import annotations

import pytest
from fred_core.kpi.kpi_call_metric import call_metric
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter


class _RecordingKPIWriter(NoOpKPIWriter):
    def __init__(self) -> None:
        self.emitted: list[dict] = []
        self.counted: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.emitted.append(kwargs)

    def count(self, name, inc=1, *, dims=None, labels=None, actor) -> None:
        self.counted.append({"name": name, "dims": dims})


@pytest.mark.asyncio
async def test_call_metric_emits_timer_and_counter_on_success() -> None:
    writer = _RecordingKPIWriter()

    async with call_metric(
        writer,
        latency_metric="rebac.call_latency_ms",
        total_metric="rebac.call_total",
        dims={"operation": "check"},
    ):
        pass

    assert len(writer.emitted) == 1
    timer_event = writer.emitted[0]
    assert timer_event["name"] == "rebac.call_latency_ms"
    assert timer_event["type"] == "timer"
    assert timer_event["dims"] == {"operation": "check", "status": "ok"}

    assert len(writer.counted) == 1
    assert writer.counted[0]["name"] == "rebac.call_total"
    assert writer.counted[0]["dims"] == {"operation": "check", "status": "ok"}


@pytest.mark.asyncio
async def test_call_metric_marks_status_error_and_reraises_on_exception() -> None:
    writer = _RecordingKPIWriter()

    with pytest.raises(ValueError):
        async with call_metric(
            writer,
            latency_metric="rebac.call_latency_ms",
            total_metric="rebac.call_total",
            dims={"operation": "write"},
        ):
            raise ValueError("boom")

    assert writer.emitted[0]["dims"]["status"] == "error"
    assert writer.counted[0]["dims"]["status"] == "error"


@pytest.mark.asyncio
async def test_call_metric_is_a_no_op_without_a_kpi_writer() -> None:
    # Must not raise even with kpi_writer=None (matches every other KPI helper
    # in the codebase — instrumentation is always optional).
    async with call_metric(
        None,
        latency_metric="rebac.call_latency_ms",
        total_metric="rebac.call_total",
        dims={"operation": "check"},
    ):
        pass
