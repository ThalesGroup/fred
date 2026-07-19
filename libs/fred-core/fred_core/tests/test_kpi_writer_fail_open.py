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

"""KPIWriter must never let a sink outage break or propagate into the
business request that triggered a metric (issue #2009; see
docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §6).
"""

from __future__ import annotations

from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import KPIQuery, KPIQueryResult
from fred_core.kpi.kpi_writer import KPIWriter
from fred_core.kpi.kpi_writer_structures import KPIActor, KPIEvent


class _RaisingKPIStore(BaseKPIStore):
    def ensure_ready(self) -> None:
        return None

    def index_event(self, event: KPIEvent) -> None:
        raise ConnectionError("OpenSearch is down")

    def bulk_index(self, events: list[KPIEvent]) -> None:
        raise ConnectionError("OpenSearch is down")

    def query(self, q: KPIQuery) -> KPIQueryResult:
        raise NotImplementedError


def test_emit_swallows_a_raising_store() -> None:
    writer = KPIWriter(store=_RaisingKPIStore())

    # Must not raise, even though the underlying store always does.
    writer.count("doc.used_total", actor=KPIActor(type="system"))


def test_timer_swallows_a_raising_store_on_exit() -> None:
    writer = KPIWriter(store=_RaisingKPIStore())

    # The business code inside the `with` block must run to completion, and
    # exiting the block must not raise even though the store write on exit does.
    ran = False
    with writer.timer("app.phase_latency_ms", actor=KPIActor(type="system")):
        ran = True
    assert ran
