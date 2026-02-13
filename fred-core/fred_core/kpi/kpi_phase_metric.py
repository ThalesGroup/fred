# Copyright Thales 2025
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
import time
from contextlib import asynccontextmanager

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import Dims, KPIActor

PHASE_METRIC_ACTOR = KPIActor(type="system", user_id=None, groups=None)


def record_phase_metric(
    *,
    kpiWriter: BaseKPIWriter,
    phase: str,
    start_ts: float,
) -> None:
    """
    Helper to record a KPI metric for a phase of some processing.
    """
    ms = int((time.monotonic() - start_ts) * 1000)
    # Keep cardinality low for Prometheus: only agent + phase + status.
    dims: Dims = {
        "phase": phase,
    }
    kpiWriter.emit(
        name="app.phase_latency_ms",
        type="timer",
        value=ms,
        unit="ms",
        dims=dims,
        actor=PHASE_METRIC_ACTOR,
    )


@asynccontextmanager
async def phase_timer(kpiWriter, phase: str):
    """
    This is a very conbvenient way to time phases of the agent orchestration and emit KPIs without littering the code with boilerplate.
    Context manager to time a phase of the agent orchestration and emit a KPI metric.
    Usage:
        with phase_timer(kpi, "planning"):
            ... do planning phase ...
    """
    start = time.monotonic()
    try:
        yield
    finally:
        record_phase_metric(kpiWriter=kpiWriter, phase=phase, start_ts=start)
