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
Dedicated, closed-cardinality timer for the three TURN-01 pre-LLM stages.

Why this is a separate mechanism from kpi_phase_metric.phase_timer:
- `app.phase_latency_ms{phase=...}` is shared by Graph, checkpoint SQL, and
  Knowledge Flow, with a wide and still-growing value set — adding `phase` to
  PROMETHEUS_ALLOWED_LABELS would make all of that visible in Grafana at once,
  a far bigger cardinality decision than "make TURN-01's three stages
  distinguishable."
- `runtime_stage` here has exactly three closed values (see RuntimeStage) and
  is deliberately isolated in its own metric name (`runtime.stage_latency_ms`)
  and its own module, so a future change to the generic phase mechanism can
  never silently affect this dedicated Grafana contract, or vice versa.
"""

import time
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import Dims, KPIActor

RUNTIME_STAGE_METRIC_ACTOR = KPIActor(type="system", user_id=None)

RuntimeStage = Literal["pod_authz", "runtime_binding", "runtime_binding_internal"]


def record_runtime_stage_metric(
    *,
    kpi_writer: BaseKPIWriter,
    runtime_stage: RuntimeStage,
    start_ts: float,
    trace_id: Optional[str] = None,
) -> None:
    """
    Emit `runtime.stage_latency_ms` for one pre-LLM stage.

    `trace_id`, when provided, correlates this stage across a service
    boundary (e.g. a pod's runtime-binding call and the control-plane request
    it triggers) — it is carried only in `trace.trace_id` for OpenSearch and
    must never be added to PROMETHEUS_ALLOWED_LABELS (unbounded cardinality,
    a pivot vector from a wide-audience dashboard back into raw logs).
    """
    ms = int((time.monotonic() - start_ts) * 1000)
    dims: Dims = {"runtime_stage": runtime_stage}
    kpi_writer.emit(
        name="runtime.stage_latency_ms",
        type="timer",
        value=ms,
        unit="ms",
        dims=dims,
        trace={"trace_id": trace_id} if trace_id else None,
        actor=RUNTIME_STAGE_METRIC_ACTOR,
    )


@asynccontextmanager
async def runtime_stage_timer(
    kpi_writer: BaseKPIWriter,
    runtime_stage: RuntimeStage,
    *,
    trace_id: Optional[str] = None,
):
    """
    Context manager timing one pre-LLM stage.

    Usage:
        async with runtime_stage_timer(kpi, "pod_authz"):
            ... do the OpenFGA check ...
    """
    start = time.monotonic()
    try:
        yield
    finally:
        record_runtime_stage_metric(
            kpi_writer=kpi_writer,
            runtime_stage=runtime_stage,
            start_ts=start,
            trace_id=trace_id,
        )
