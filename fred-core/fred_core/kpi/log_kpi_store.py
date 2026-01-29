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

import logging
from typing import List

from fred_core.kpi.base_kpi_store import BaseKPIStore
from fred_core.kpi.kpi_reader_structures import (
    KPIQuery,
    KPIQueryResult,
)
from fred_core.kpi.kpi_writer_structures import (
    KPIEvent,
)


class KpiLogStore(BaseKPIStore):
    """
    No-op KPI store.

    When to use:
    - Local dev & unit tests (no infra required).
    - Scenarios where we want *observability semantics* without persistence.
    - Safe fallback when the real store is unavailable.

    Behavior:
    - Does not persist anything.
    - Logs debug lines so developers can see what would have been recorded.
    """

    def __init__(self, level: str):
        self.level = level.lower()
        self.logger = logging.getLogger("KPI")

    def ensure_ready(self) -> None:
        self._log("[KPI][LOG] ensure_ready called")

    def index_event(self, event: KPIEvent) -> None:
        self._log(
            f"[KPI][LOG] index_event: {event.metric.name} {event.metric.value} dims={event.dims}"
        )

    def bulk_index(self, events: List[KPIEvent]) -> None:
        self._log(f"[KPI][LOG] bulk_index: {len(events)} events")

    def query(self, q: KPIQuery) -> KPIQueryResult:
        self._log(f"[KPI][LOG] query: {q.model_dump(exclude_none=True)}")
        return KPIQueryResult(rows=[])

    def _log(self, msg: str) -> None:
        if self.level == "debug":
            self.logger.debug(msg)
        elif self.level in ("info", "information"):
            self.logger.info(msg)
        elif self.level in ("warn", "warning"):
            self.logger.warning(msg)
        else:
            self.logger.debug(msg)
