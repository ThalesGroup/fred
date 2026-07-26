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
import time
from contextlib import asynccontextmanager
from typing import Optional

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import Dims, KPIActor

CALL_METRIC_ACTOR = KPIActor(type="system", user_id=None)


@asynccontextmanager
async def call_metric(
    kpi_writer: Optional[BaseKPIWriter],
    *,
    latency_metric: str,
    total_metric: str,
    dims: Dims,
):
    """
    Time one async call and emit both a timer and a counter with the same dims.

    Shared shape for "counter+timer keyed by a bounded-cardinality dim"
    instrumentation (e.g. OpenFGA operation, remote-call type) — one call site
    per instrumented operation instead of hand-rolled timing/status bookkeeping
    at each one.

    Usage:
        async with call_metric(kpi, latency_metric="rebac.call_latency_ms",
                                total_metric="rebac.call_total",
                                dims={"rebac_operation": "check"}):
            ... do the call ...
    """
    if kpi_writer is None:
        yield
        return
    start = time.monotonic()
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        ms = (time.monotonic() - start) * 1000.0
        final_dims: Dims = {**dims, "status": status}
        kpi_writer.emit(
            name=latency_metric,
            type="timer",
            value=ms,
            unit="ms",
            dims=final_dims,
            actor=CALL_METRIC_ACTOR,
        )
        kpi_writer.count(total_metric, dims=final_dims, actor=CALL_METRIC_ACTOR)
