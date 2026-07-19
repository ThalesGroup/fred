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
Offline unit tests for fred_core.logs.memory_log_store.

Covers:
- RamLogStore: append, bulk_index, capacity eviction (write path only —
  Fred no longer queries its own log store; OpenSearch Dashboards does).
"""

from __future__ import annotations

import time

from fred_core.logs.log_structures import LogEventDTO, LogLevel
from fred_core.logs.memory_log_store import RamLogStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    msg: str,
    *,
    ts: float | None = None,
    level: LogLevel = "INFO",
    logger: str = "app",
    service: str | None = None,
    category: str = "application",
) -> LogEventDTO:
    return LogEventDTO(
        ts=ts if ts is not None else time.time(),
        level=level,
        logger=logger,
        file="test.py",
        line=1,
        msg=msg,
        service=service,
        category=category,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# RamLogStore — lifecycle
# ---------------------------------------------------------------------------


class TestRamLogStoreLifecycle:
    def test_ensure_ready_does_not_raise(self) -> None:
        store = RamLogStore()
        store.ensure_ready()

    def test_capacity_evicts_oldest(self) -> None:
        store = RamLogStore(capacity=3)
        base = time.time() - 300
        for i in range(5):
            store.index_event(_event(f"msg-{i}", ts=base + i))
        msgs = [e.msg for e in store._q]
        assert "msg-0" not in msgs
        assert "msg-1" not in msgs
        assert "msg-4" in msgs
        assert len(store._q) == 3


# ---------------------------------------------------------------------------
# RamLogStore — writes
# ---------------------------------------------------------------------------


class TestRamLogStoreWrites:
    def test_single_event_indexed(self) -> None:
        store = RamLogStore()
        store.index_event(_event("hello"))
        assert len(store._q) == 1
        assert store._q[0].msg == "hello"

    def test_bulk_index(self) -> None:
        store = RamLogStore()
        events = [_event(f"msg-{i}") for i in range(5)]
        store.bulk_index(events)
        assert len(store._q) == 5

    def test_bulk_index_empty_list_does_nothing(self) -> None:
        store = RamLogStore()
        store.bulk_index([])
        assert len(store._q) == 0
