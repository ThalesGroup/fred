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
Offline unit test for fred_core.kpi.kpi_phase_metric.phase_timer — the
generic, shared phase mechanism (Graph, checkpoint SQL, Knowledge Flow).

Kept deliberately untouched by the TURN-01 Grafana-visibility work: `phase`
is not in PROMETHEUS_ALLOWED_LABELS and stays that way (its value set is wide
and shared across unrelated call sites — see kpi_runtime_stage_metric.py for
the narrow, closed-set contract used for the three pre-LLM stages instead).
"""

from __future__ import annotations

import pytest
from fred_core.kpi.kpi_phase_metric import phase_timer
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter


class _RecordingKPIWriter(NoOpKPIWriter):
    def __init__(self) -> None:
        self.emitted: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.emitted.append(kwargs)


@pytest.mark.asyncio
async def test_phase_timer_emits_app_phase_latency_ms_with_phase_dim() -> None:
    writer = _RecordingKPIWriter()

    async with phase_timer(writer, "planning"):
        pass

    assert len(writer.emitted) == 1
    event = writer.emitted[0]
    assert event["name"] == "app.phase_latency_ms"
    assert event["dims"] == {"phase": "planning"}
    assert event.get("trace") is None
