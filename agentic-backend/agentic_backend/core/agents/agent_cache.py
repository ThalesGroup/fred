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
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class AgentCacheStats:
    size: int
    max_size: int
    in_use_entries: int
    in_use_total: int
    evictions: int
    blocked_evictions: int


@dataclass
class _CacheEntry(Generic[V]):
    value: V
    in_use: int = 0


class ActiveAgentCache(Generic[K, V]):
    def __init__(self, max_size: int):
        self._max_size = max_size
        self._lock = Lock()
        self._cache: OrderedDict[K, _CacheEntry[V]] = OrderedDict()
        self._evictions = 0
        self._blocked_evictions = 0

    def get(self, key: K) -> Optional[V]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                self._cache.move_to_end(key)
                return entry.value
            return None

    def set(self, key: K, value: V) -> None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._cache[key] = _CacheEntry(value=value)
            else:
                entry.value = value
            self._cache.move_to_end(key)
            self._evict_idle_locked()

    def acquire(self, key: K) -> bool:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            entry.in_use += 1
            self._cache.move_to_end(key)
            return True

    def release(self, key: K) -> None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return
            entry.in_use = max(0, entry.in_use - 1)
            if entry.in_use == 0:
                self._evict_idle_locked()

    def delete(self, key: K) -> Optional[V]:
        with self._lock:
            entry = self._cache.pop(key, None)
            return entry.value if entry else None

    def keys(self) -> list[K]:
        with self._lock:
            return list(self._cache.keys())

    def stats(self) -> AgentCacheStats:
        with self._lock:
            in_use_entries = sum(
                1 for entry in self._cache.values() if entry.in_use > 0
            )
            in_use_total = sum(entry.in_use for entry in self._cache.values())
            return AgentCacheStats(
                size=len(self._cache),
                max_size=self._max_size,
                in_use_entries=in_use_entries,
                in_use_total=in_use_total,
                evictions=self._evictions,
                blocked_evictions=self._blocked_evictions,
            )

    def _evict_idle_locked(self) -> None:
        while len(self._cache) > self._max_size:
            evicted = False
            for key, entry in self._cache.items():
                if entry.in_use == 0:
                    self._cache.pop(key, None)
                    self._evictions += 1
                    evicted = True
                    break
            if not evicted:
                self._blocked_evictions += 1
                logger.debug(
                    "[AGENTS] Cache at capacity; eviction blocked by in-flight agents (size=%d).",
                    len(self._cache),
                )
                break
