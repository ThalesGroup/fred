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
Offline unit test for fred_core.kpi.kpi_process.emit_process_kpis' new
event_loop_lag_ms gauge.

Ref: docs/swift/reviews/performance/2026-07-26-agent-turn-core/TURN-01... — the
review found `event_loop_lag_ms` referenced by the KPI summary formatter
(kpi_writer.py) but emitted by no code site anywhere in the codebase.
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock

import pytest
from fred_core.kpi.kpi_process import emit_process_kpis
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter


@pytest.mark.asyncio
async def test_emit_process_kpis_emits_event_loop_lag_gauge() -> None:
    """
    event_loop_lag_ms must be emitted from the second tick onward (no prior
    sleep exists to measure lag against on the very first tick).
    """
    writer = NoOpKPIWriter()
    spy = MagicMock(wraps=writer.gauge)
    writer.gauge = spy

    task = asyncio.create_task(emit_process_kpis(0.01, writer))
    try:
        await asyncio.sleep(0.1)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    lag_calls = [c for c in spy.call_args_list if c.args[:1] == ("event_loop_lag_ms",)]
    assert lag_calls, "expected at least one event_loop_lag_ms gauge emission"
    for call in lag_calls:
        assert call.args[1] >= 0.0
