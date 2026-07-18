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

"""ResilientSinkStore: bounded queue + circuit breaker (issue #2009).

See docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §6: a KPI/log sink outage
must never block or fail the business request that triggered the write.
"""

from __future__ import annotations

import threading
import time

from fred_core.common.resilient_sink import ResilientSinkStore


def _wait_until(predicate, timeout_s: float = 2.0, interval_s: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_s)
    return predicate()


class _RecordingStore:
    def __init__(self) -> None:
        self.indexed: list[object] = []
        self.lock = threading.Lock()

    def ensure_ready(self) -> None:
        return None

    def index_event(self, event: object) -> None:
        with self.lock:
            self.indexed.append(event)

    def bulk_index(self, events: list[object]) -> None:
        for e in events:
            self.index_event(e)

    def query(self, q: object) -> object:
        return {"echo": q}


class _AlwaysRaisingStore:
    def __init__(self) -> None:
        self.call_count = 0
        self.lock = threading.Lock()

    def ensure_ready(self) -> None:
        return None

    def index_event(self, event: object) -> None:
        with self.lock:
            self.call_count += 1
        raise ConnectionError("sink is down")

    def bulk_index(self, events: list[object]) -> None:
        for e in events:
            self.index_event(e)

    def query(self, q: object) -> object:
        raise NotImplementedError


def test_index_event_never_blocks_or_raises_and_reaches_the_wrapped_store() -> None:
    wrapped = _RecordingStore()
    sink = ResilientSinkStore(wrapped)

    sink.index_event("event-1")  # must not raise, must not block

    assert _wait_until(lambda: wrapped.indexed == ["event-1"])


def test_query_and_ensure_ready_pass_through_directly() -> None:
    wrapped = _RecordingStore()
    sink = ResilientSinkStore(wrapped)

    sink.ensure_ready()  # must not raise
    assert sink.query("q") == {"echo": "q"}


def test_full_queue_drops_without_blocking_the_caller() -> None:
    wrapped = _RecordingStore()
    # queue_size=1 with an always-failing breaker threshold high enough that
    # writes are attempted (not short-circuited) — the *queue*, not the
    # breaker, is what we're forcing to overflow here. Block the worker by
    # holding wrapped.lock so nothing drains while we flood the queue.
    sink = ResilientSinkStore(wrapped, queue_size=1, failure_threshold=1000)
    with wrapped.lock:
        sink.index_event(
            "a"
        )  # may or may not be picked up before the lock; either way, non-blocking
        for _ in range(10):
            sink.index_event("flood")

    assert sink.dropped_queue_full > 0


def test_circuit_breaker_opens_after_threshold_and_stops_calling_wrapped_store() -> (
    None
):
    wrapped = _AlwaysRaisingStore()
    sink = ResilientSinkStore(wrapped, failure_threshold=2, cooldown_s=60.0)

    sink.index_event("e1")
    sink.index_event("e2")
    assert _wait_until(lambda: wrapped.call_count >= 2)

    calls_when_open = wrapped.call_count
    sink.index_event(
        "e3"
    )  # breaker should now be open — dropped before reaching the store
    time.sleep(0.05)
    assert wrapped.call_count == calls_when_open
    assert sink.dropped_circuit_open > 0


def test_circuit_breaker_half_opens_and_recovers_after_cooldown() -> None:
    wrapped = _AlwaysRaisingStore()
    sink = ResilientSinkStore(wrapped, failure_threshold=1, cooldown_s=0.05)

    sink.index_event("e1")
    assert _wait_until(lambda: wrapped.call_count >= 1)
    assert _wait_until(lambda: sink._breaker.is_open)

    # Swap in a store that succeeds, then wait past the cooldown for the
    # half-open trial to close the breaker.
    recovered = _RecordingStore()
    sink._wrapped = recovered  # type: ignore[assignment]
    time.sleep(0.1)
    sink.index_event("e2")

    assert _wait_until(lambda: recovered.indexed == ["e2"])
    assert not sink._breaker.is_open
