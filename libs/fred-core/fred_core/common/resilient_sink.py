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
Resilient sink decorator — bounded queue + circuit breaker (issue #2009).

Why this exists:
- `BaseLogStore` and `BaseKPIStore` share the same write shape (`index_event`,
  `bulk_index`) and the same contract note: "must not block or crash the
  caller on outage." Nothing previously enforced that for the OpenSearch-
  backed implementations — a down/slow cluster could block the calling
  thread for a full HTTP timeout on every write, or (for `KPIWriter`, which
  calls `index_event` synchronously and inline) let the exception propagate
  into the business request that triggered the metric.
- This wraps any such store: writes are handed to a single background
  thread via a bounded queue (never blocks the caller — full queue means
  drop, not wait) and short-circuited once the wrapped store has failed
  repeatedly, so a known-down cluster stops being hammered from the hot path.

How to use:
- `ResilientSinkStore(wrapped_store)` — same write shape as the store it
  wraps (`ensure_ready`/`index_event`/`bulk_index`), so it's a drop-in
  decorator. `ensure_ready()` passes straight through: startup provisioning
  is not this decorator's concern, only the steady-state write path is.
  `query()` also passes through, best-effort, for wrapped stores that
  support it (KPI stores do; the log store no longer does since Fred stopped
  exposing its own log-query surface — OpenSearch Dashboards reads that
  index directly instead).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class _WritableStore(Protocol):
    def ensure_ready(self) -> None:
        pass

    def index_event(self, event: Any) -> None:
        pass

    def bulk_index(self, events: list[Any]) -> None:
        pass


class _CircuitBreaker:
    """Opens after `failure_threshold` consecutive failures; half-opens
    (allows one trial) after `cooldown_s`; closes again on a trial success."""

    def __init__(self, *, failure_threshold: int, cooldown_s: float) -> None:
        self._threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            return (time.monotonic() - self._opened_at) >= self._cooldown_s

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if (
                self._consecutive_failures >= self._threshold
                and self._opened_at is None
            ):
                self._opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            return (time.monotonic() - self._opened_at) < self._cooldown_s


class ResilientSinkStore:
    """Fail-open, non-blocking decorator around a `BaseLogStore`/`BaseKPIStore`.

    Contract with the caller:
    - `index_event`/`bulk_index` never raise and never block beyond a
      non-blocking queue put.
    - A full queue (sink can't keep up) or an open circuit (sink is known
      down) both mean "drop the event", counted separately for diagnostics.
    """

    def __init__(
        self,
        wrapped: _WritableStore,
        *,
        queue_size: int = 1000,
        failure_threshold: int = 5,
        cooldown_s: float = 30.0,
    ) -> None:
        self._wrapped = wrapped
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=queue_size)
        self._breaker = _CircuitBreaker(
            failure_threshold=failure_threshold, cooldown_s=cooldown_s
        )
        self.dropped_queue_full = 0
        self.dropped_circuit_open = 0
        self._thread = threading.Thread(
            target=self._worker, name="resilient-sink-writer", daemon=True
        )
        self._thread.start()

    @property
    def wrapped(self) -> _WritableStore:
        """The underlying store — exposed read-only for introspection/tests."""
        return self._wrapped

    # -- passthrough: not this decorator's concern -----------------------------
    def ensure_ready(self) -> None:
        self._wrapped.ensure_ready()

    def query(self, q: Any) -> Any:
        """Best-effort passthrough for wrapped stores that support querying
        (KPI stores do; the log store no longer does)."""
        query_fn = getattr(self._wrapped, "query", None)
        if query_fn is None:
            raise AttributeError(
                f"{type(self._wrapped).__name__} does not support query()"
            )
        return query_fn(q)

    # -- writes: bounded, non-blocking, fail-open ------------------------------
    def index_event(self, event: Any) -> None:
        if not self._breaker.allow():
            self.dropped_circuit_open += 1
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped_queue_full += 1

    def bulk_index(self, events: list[Any]) -> None:
        for event in events:
            self.index_event(event)

    # -- background worker ------------------------------------------------------
    def _worker(self) -> None:
        while True:
            event = self._queue.get()
            try:
                if not self._breaker.allow():
                    self.dropped_circuit_open += 1
                    continue
                try:
                    self._wrapped.index_event(event)
                    self._breaker.record_success()
                except Exception:
                    self._breaker.record_failure()
                    logger.warning(
                        "Resilient sink write failed; dropping event", exc_info=True
                    )
            finally:
                self._queue.task_done()


__all__ = ["ResilientSinkStore"]
