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
#
# Purpose:
# - Super-simple in-memory store for the last N log events (default 1000).
# - Zero infra, great for dev/tests and as a fallback when OS is down.
#
# Design notes:
# - Uses deque(maxlen=N) for O(1) append + automatic eviction.
# - Thread-safe with a simple RLock (works from async contexts too).
# - Query is a linear scan over <= N items — trivial and fast at this scale.

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, List

from fred_core.logs.base_log_store import (
    BaseLogStore,
    LogEventDTO,
    LogQuery,
    LogQueryResult,
)

_LEVEL_ORDER = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_LEVEL_INDEX = {lvl: i for i, lvl in enumerate(_LEVEL_ORDER)}


def _parse_since(s: str, now: float) -> float:
    # Accept ISO or 'now-<num><unit>' (s|m|h)
    if s.startswith("now-"):
        val = float(s[4:-1])
        unit = s[-1]
        mult = (
            1 if unit == "s" else 60 if unit == "m" else 3600 if unit == "h" else None
        )
        if mult is None:
            raise ValueError(f"Unsupported relative time: {s}")
        return now - val * mult
    # Fallback: try dateutil if present; else trust caller to pass epoch float as str
    try:
        import dateutil.parser  # optional

        return dateutil.parser.parse(s).timestamp()
    except Exception:
        return float(s)  # last resort: allow epoch seconds as string


class RamLogStore(BaseLogStore):
    """
    Last-1000 RAM-backed log store.
    - Append-only ring. Oldest entries are evicted automatically.
    - Query is best-effort and cheap at this bound.
    """

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self._q: Deque[LogEventDTO] = deque(maxlen=capacity)
        self._lock = threading.RLock()

    # --- lifecycle ------------------------------------------------------------
    def ensure_ready(self) -> None:
        # Nothing to provision.
        return

    # --- writes ---------------------------------------------------------------
    def index_event(self, event: LogEventDTO) -> None:
        with self._lock:
            self._q.append(event)

    def bulk_index(self, events: List[LogEventDTO]) -> None:
        if not events:
            return
        with self._lock:
            self._q.extend(events)

    # --- reads ----------------------------------------------------------------
    def query(self, q: LogQuery) -> LogQueryResult:
        now = time.time()
        since_ts = _parse_since(q.since, now)
        until_ts = _parse_since(q.until, now) if q.until else now

        f = q.filters
        min_idx = (
            _LEVEL_INDEX.get(f.level_at_least, -1) if f and f.level_at_least else -1
        )
        logger_like = (f.logger_like or "").strip() if f else ""
        service = (f.service or "").strip() if f else ""
        text_like = (f.text_like or "").lower().strip() if f else ""

        with self._lock:
            items = list(self._q)

        # Filter
        def ok(e: LogEventDTO) -> bool:
            if not (since_ts <= e.ts <= until_ts):
                return False
            if min_idx >= 0 and _LEVEL_INDEX.get(e.level, 0) < min_idx:
                return False
            if logger_like and logger_like not in e.logger:
                return False
            if service and service != (e.service or ""):
                return False
            if text_like and text_like not in e.msg.lower():
                return False
            return True

        filtered = [e for e in items if ok(e)]
        # Order by time
        reverse = q.order == "desc"
        filtered.sort(key=lambda e: e.ts, reverse=reverse)
        # Limit
        return LogQueryResult(events=filtered[: q.limit])
