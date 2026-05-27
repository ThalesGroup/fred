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
Base Log Store Abstraction
==========================

This module defines the *storage contract* for Fred’s application logs.

Why this exists in Fred:
- We want **one emission API** (logging handler / writer) that can plug into
  **many backends** (OpenSearch, in-memory ring for dev, CSV for tests, etc.).
- Backends differ in capabilities and SLOs; we keep the interface minimal but
  sufficient: readiness, single-event ingest, bulk ingest, and a *best-effort*
  query API for the monitoring UI.

Key ideas:
- `BaseLogStore` is a `Protocol` (static duck-typing) → implementations don’t
  need inheritance, only matching shape.
- Dev default can be an in-memory ring (fast, zero-ops); prod can be OpenSearch.
"""

from __future__ import annotations

from typing import Protocol

from fred_core.logs.log_structures import LogEventDTO, LogQuery, LogQueryResult


class BaseLogStore(Protocol):
    """Abstract Log store API used by the logging pipeline and monitoring UI.

    Architectural role:
    - Decouple **log emission** from **physical storage & query**.
    - Keep the contract intentionally small so backends remain easy to implement.
    - Allow services to boot even if the store is slow to initialize
      (callers may handle failures without crashing business logic).

    Implementation notes:
    - `index_event` must be non-blocking or bounded in latency (hot paths).
    - `bulk_index` is for throughput (batching) when the caller can coalesce.
    - `query` is intentionally lightweight: time range + simple filters
      for the built-in console; not meant to replace a full SIEM.
    """

    def ensure_ready(self) -> None:
        """Ensure the backing store is initialized (indices/tables exist, mappings applied).

        Why:
        - We prefer to *self-provision* indices/mappings on first run to reduce ops toil.
        - Called once at startup; failures should be handled upstream as non-fatal when possible.
        """
        ...

    def index_event(self, event: LogEventDTO) -> None:
        """Insert one log event.

        Contract:
        - Must not block request handling; drop/buffer on outage rather than crash.
        - Idempotency is best-effort (logs are observability, not correctness).
        """
        ...

    def bulk_index(self, events: list[LogEventDTO]) -> None:
        """Insert a batch of log events efficiently.

        Why:
        - Backends like OpenSearch benefit from bulk ingestion.
        - Caller decides batching cadence; store optimizes the write path.
        """
        ...

    def query(self, q: LogQuery) -> LogQueryResult:
        """Run a best-effort query over stored logs.

        Design:
        - Used by the Fred monitoring UI (time window, filters, limit/order).
        - Implementations may support a subset of filters; document trade-offs.
        """
        ...
