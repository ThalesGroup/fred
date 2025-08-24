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

"""
Base KPI Store Abstraction
==========================

This module defines the *storage contract* for Fred’s KPI system.

Why this exists in Fred:
- We want **one emission API** (KPIWriter) that can plug into **many backends**
  (OpenSearch, Prometheus/Remote Write, ClickHouse, CSV for tests, etc.).
- Backends differ in capabilities, so we keep the store interface minimal but
  sufficient: readiness, single-event ingest, bulk ingest, and a *best-effort*
  query API for dashboards/health checks.

Key ideas:
- `BaseKPIStore` is a `Protocol` (static duck-typing) → implementations don’t
  need inheritance, only matching shape.
- `NoopKPIStore` is the dev/default sink: never fails, logs what would happen.
  Useful for local runs and unit tests where metrics persistence is out of scope.
"""

from __future__ import annotations
from typing import Protocol
from typing import List
import logging
from fred_core.kpi.kpi_writer_structures import (
    KPIEvent,
)
from fred_core.kpi.kpi_reader_structures import (
    KPIQuery,
    KPIQueryResult,
)

logger = logging.getLogger(__name__)


class BaseKPIStore(Protocol):
    """Abstract KPI store API used by `KPIWriter`.

    Architectural role:
    - Decouple **metric emission** from **physical storage**.
    - Keep the contract intentionally small so backends remain easy to implement.
    - Allow services to boot even if the store is slow to initialize
      (writer calls `ensure_ready()` but does not crash the app on failure).

    Implementation notes:
    - Implementers should be idempotent and fast for `index_event`.
    - `bulk_index` is for throughput (batching) when the caller can coalesce.
    - `query` is intentionally generic (best-effort); some backends may
      implement only a subset of filtering/aggregation.
    """

    def ensure_ready(self) -> None:
        """Ensure the backing store is initialized (indices/tables exist, mappings applied).

        Why:
        - We prefer to *self-provision* indices/mappings on first run to reduce ops toil.
        - Called once at startup by `KPIWriter`; failures should be non-fatal upstream.
        """
        ...

    def index_event(self, event: KPIEvent) -> None:
        """Insert one KPI event.

        Contract:
        - Must be non-blocking or bounded in latency; callers may be on hot paths.
        - Should drop or buffer on outage rather than crash business logic.
        """
        ...

    def bulk_index(self, events: list[KPIEvent]) -> None:
        """Insert a batch of KPI events atomically or efficiently.

        Why:
        - Backends like OpenSearch/ClickHouse benefit from bulk ingestion.
        - Caller decides batching cadence; store should optimize the write path.
        """
        ...

    def query(self, q: KPIQuery) -> KPIQueryResult:
        """Run a best-effort query over stored metrics.

        Design:
        - Used by internal dashboards, health checks, or lightweight analytics.
        - Not intended to replace BI/ELT; keep semantics simple and documented.
        """
        ...


class NoopKPIStore(BaseKPIStore):
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

    def ensure_ready(self) -> None:
        logger.debug("[KPI][noop] ensure_ready called")

    def index_event(self, event: KPIEvent) -> None:
        logger.debug(f"[KPI][noop] index_event: {event.metric.name} {event.metric.value} dims={event.dims}")

    def bulk_index(self, events: List[KPIEvent]) -> None:
        logger.debug(f"[KPI][noop] bulk_index: {len(events)} events")

    def query(self, q: KPIQuery) -> KPIQueryResult:
        logger.debug(f"[KPI][noop] query: {q.model_dump(exclude_none=True)}")
        return KPIQueryResult(rows=[])
