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

from __future__ import annotations

import threading
from collections import deque
from typing import Deque, List

from fred_core.logs.base_log_store import BaseLogStore, LogEventDTO


class RamLogStore(BaseLogStore):
    """
    Last-1000 RAM-backed log store.
    - Append-only ring. Oldest entries are evicted automatically.
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
