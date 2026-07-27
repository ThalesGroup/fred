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
Offline unit tests for fred_core.kpi.kpi_persist_metric.record_persist_metrics.
"""

from __future__ import annotations

from fred_core.kpi.kpi_persist_metric import record_persist_metrics
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter


class _RecordingKPIWriter(NoOpKPIWriter):
    def __init__(self) -> None:
        self.emitted: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.emitted.append(kwargs)


def test_record_persist_metrics_emits_both_timers_with_bounded_dims() -> None:
    writer = _RecordingKPIWriter()

    record_persist_metrics(
        writer,
        store="checkpoint",
        op="put",
        pool_wait_ms=1.5,
        sql_ms=4.2,
    )

    names = {e["name"] for e in writer.emitted}
    assert names == {"persist_pool_wait_ms", "persist_sql_ms"}
    for event in writer.emitted:
        assert event["dims"] == {"store": "checkpoint", "op": "put"}
        assert event["type"] == "timer"
        assert event["unit"] == "ms"

    pool_event = next(e for e in writer.emitted if e["name"] == "persist_pool_wait_ms")
    sql_event = next(e for e in writer.emitted if e["name"] == "persist_sql_ms")
    assert pool_event["value"] == 1.5
    assert sql_event["value"] == 4.2


def test_record_persist_metrics_is_a_no_op_without_a_kpi_writer() -> None:
    # Must not raise — every checkpoint/history write path calls this
    # unconditionally regardless of whether a KPI writer was configured.
    record_persist_metrics(
        None, store="history", op="save", pool_wait_ms=0.0, sql_ms=0.0
    )
