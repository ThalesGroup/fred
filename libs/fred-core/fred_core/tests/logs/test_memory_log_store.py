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
- _parse_since: relative (now-Xs/m/h) and absolute (epoch float string)
- RamLogStore: append, bulk_index, capacity eviction, query filtering
  (time window, level, logger, service, text_like, order, limit)
"""

from __future__ import annotations

import time
from typing import Literal

import pytest
from fred_core.logs.log_structures import LogEventDTO, LogFilter, LogLevel, LogQuery
from fred_core.logs.memory_log_store import RamLogStore, _parse_since

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
) -> LogEventDTO:
    return LogEventDTO(
        ts=ts if ts is not None else time.time(),
        level=level,
        logger=logger,
        file="test.py",
        line=1,
        msg=msg,
        service=service,
    )


def _query(
    *,
    since: str = "now-1h",
    until: str | None = None,
    level_at_least: LogLevel | None = None,
    logger_like: str | None = None,
    service: str | None = None,
    text_like: str | None = None,
    limit: int = 500,
    order: "Literal['asc', 'desc']" = "asc",
) -> LogQuery:
    return LogQuery(
        since=since,
        until=until,
        filters=LogFilter(
            level_at_least=level_at_least,
            logger_like=logger_like,
            service=service,
            text_like=text_like,
        ),
        limit=limit,
        order=order,
    )


# ---------------------------------------------------------------------------
# _parse_since
# ---------------------------------------------------------------------------


class TestParseSince:
    def test_now_minus_seconds(self) -> None:
        now = 1000.0
        result = _parse_since("now-30s", now)
        assert result == pytest.approx(970.0)

    def test_now_minus_minutes(self) -> None:
        now = 1000.0
        result = _parse_since("now-2m", now)
        assert result == pytest.approx(880.0)

    def test_now_minus_hours(self) -> None:
        now = 7200.0
        result = _parse_since("now-1h", now)
        assert result == pytest.approx(3600.0)

    def test_epoch_float_string(self) -> None:
        result = _parse_since("1234567890.5", 0.0)
        assert result == pytest.approx(1234567890.5)

    def test_unsupported_unit_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            _parse_since("now-5d", 1000.0)


# ---------------------------------------------------------------------------
# RamLogStore — lifecycle
# ---------------------------------------------------------------------------


class TestRamLogStoreLifecycle:
    def test_ensure_ready_does_not_raise(self) -> None:
        store = RamLogStore()
        store.ensure_ready()

    def test_empty_store_returns_no_events(self) -> None:
        store = RamLogStore()
        result = store.query(_query())
        assert result.events == []

    def test_capacity_evicts_oldest(self) -> None:
        store = RamLogStore(capacity=3)
        base = (
            time.time() - 300
        )  # anchor in the past so all events are within the query window
        for i in range(5):
            store.index_event(_event(f"msg-{i}", ts=base + i))
        result = store.query(_query(since="now-1h", limit=10))
        msgs = [e.msg for e in result.events]
        assert "msg-0" not in msgs
        assert "msg-1" not in msgs
        assert "msg-4" in msgs


# ---------------------------------------------------------------------------
# RamLogStore — writes
# ---------------------------------------------------------------------------


class TestRamLogStoreWrites:
    def test_single_event_indexed(self) -> None:
        store = RamLogStore()
        store.index_event(_event("hello"))
        result = store.query(_query())
        assert len(result.events) == 1
        assert result.events[0].msg == "hello"

    def test_bulk_index(self) -> None:
        store = RamLogStore()
        events = [_event(f"msg-{i}") for i in range(5)]
        store.bulk_index(events)
        result = store.query(_query())
        assert len(result.events) == 5

    def test_bulk_index_empty_list_does_nothing(self) -> None:
        store = RamLogStore()
        store.bulk_index([])
        result = store.query(_query())
        assert result.events == []


# ---------------------------------------------------------------------------
# RamLogStore — query: time window
# ---------------------------------------------------------------------------


class TestRamLogStoreQueryTimeWindow:
    def test_event_outside_window_excluded(self) -> None:
        store = RamLogStore()
        old_ts = time.time() - 7200  # 2 hours ago
        store.index_event(_event("old", ts=old_ts))
        result = store.query(_query(since="now-1h"))
        assert result.events == []

    def test_event_inside_window_included(self) -> None:
        store = RamLogStore()
        store.index_event(_event("recent", ts=time.time() - 60))
        result = store.query(_query(since="now-1h"))
        assert len(result.events) == 1

    def test_until_excludes_future_events(self) -> None:
        store = RamLogStore()
        past = time.time() - 300
        future = time.time() + 300
        store.index_event(_event("past", ts=past))
        store.index_event(_event("future", ts=future))
        result = store.query(_query(since="now-1h", until="now-0s"))
        msgs = [e.msg for e in result.events]
        assert "past" in msgs
        assert "future" not in msgs


# ---------------------------------------------------------------------------
# RamLogStore — query: filters
# ---------------------------------------------------------------------------


class TestRamLogStoreQueryFilters:
    def _populated_store(self) -> RamLogStore:
        store = RamLogStore()
        now = time.time() - 10
        store.bulk_index(
            [
                _event(
                    "debug msg",
                    ts=now,
                    level="DEBUG",
                    logger="app.debug",
                    service="svc-a",
                ),
                _event(
                    "info msg", ts=now, level="INFO", logger="app.info", service="svc-a"
                ),
                _event(
                    "warn msg",
                    ts=now,
                    level="WARNING",
                    logger="app.warn",
                    service="svc-b",
                ),
                _event(
                    "error msg",
                    ts=now,
                    level="ERROR",
                    logger="app.error",
                    service="svc-b",
                ),
            ]
        )
        return store

    def test_level_at_least_warning_excludes_debug_info(self) -> None:
        store = self._populated_store()
        result = store.query(_query(level_at_least="WARNING"))
        levels = {e.level for e in result.events}
        assert "DEBUG" not in levels
        assert "INFO" not in levels
        assert "WARNING" in levels
        assert "ERROR" in levels

    def test_level_at_least_error_keeps_only_error(self) -> None:
        store = self._populated_store()
        result = store.query(_query(level_at_least="ERROR"))
        assert all(e.level == "ERROR" for e in result.events)

    def test_logger_like_substring_match(self) -> None:
        store = self._populated_store()
        result = store.query(_query(logger_like="warn"))
        assert all("warn" in e.logger for e in result.events)

    def test_service_exact_match(self) -> None:
        store = self._populated_store()
        result = store.query(_query(service="svc-a"))
        assert all(e.service == "svc-a" for e in result.events)

    def test_text_like_case_insensitive(self) -> None:
        store = self._populated_store()
        result = store.query(_query(text_like="WARN"))
        assert len(result.events) == 1
        assert result.events[0].msg == "warn msg"

    def test_no_filters_returns_all(self) -> None:
        store = self._populated_store()
        result = store.query(_query())
        assert len(result.events) == 4


# ---------------------------------------------------------------------------
# RamLogStore — query: ordering and limit
# ---------------------------------------------------------------------------


class TestRamLogStoreQueryOrderAndLimit:
    def _store_with_timestamps(self) -> RamLogStore:
        store = RamLogStore()
        base = time.time() - 100
        store.bulk_index([_event(f"msg-{i}", ts=base + i) for i in range(5)])
        return store

    def test_asc_order(self) -> None:
        store = self._store_with_timestamps()
        result = store.query(_query(order="asc"))
        ts_list = [e.ts for e in result.events]
        assert ts_list == sorted(ts_list)

    def test_desc_order(self) -> None:
        store = self._store_with_timestamps()
        result = store.query(_query(order="desc"))
        ts_list = [e.ts for e in result.events]
        assert ts_list == sorted(ts_list, reverse=True)

    def test_limit_truncates_results(self) -> None:
        store = self._store_with_timestamps()
        result = store.query(_query(limit=3))
        assert len(result.events) == 3
