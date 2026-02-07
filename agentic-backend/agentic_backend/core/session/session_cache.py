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
from typing import Optional

from agentic_backend.core.chatbot.chat_schema import SessionSchema
from agentic_backend.core.session.stores.base_session_attachment_store import (
    SessionAttachmentRecord,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionCacheStats:
    size: int
    max_size: int
    in_use_entries: int
    in_use_total: int
    evictions: int
    blocked_evictions: int


@dataclass
class CachedSession:
    session: SessionSchema
    attachments: Optional[list[SessionAttachmentRecord]] = None


@dataclass
class _CacheEntry:
    value: CachedSession
    in_use: int = 0


class SessionCache:
    """
    Small LRU cache for SessionSchema + attachments, mirroring ActiveAgentCache.
    Evicts only entries not marked in_use; acquire/release guards an active exchange.
    """

    def __init__(self, max_size: int):
        self._max_size = max_size
        self._lock = Lock()
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._evictions = 0
        self._blocked_evictions = 0

    def get(self, session_id: str) -> Optional[CachedSession]:
        with self._lock:
            entry = self._cache.get(session_id)
            if entry is not None:
                self._cache.move_to_end(session_id)
                return entry.value
            return None

    def set(self, session_id: str, value: CachedSession) -> None:
        with self._lock:
            entry = self._cache.get(session_id)
            if entry is None:
                self._cache[session_id] = _CacheEntry(value=value)
            else:
                entry.value = value
            self._cache.move_to_end(session_id)
            self._evict_idle_locked()

    def touch_session(self, session_id: str, session: SessionSchema) -> None:
        """Update only the SessionSchema for an existing entry."""
        with self._lock:
            entry = self._cache.get(session_id)
            if entry is None:
                return
            entry.value.session = session
            self._cache.move_to_end(session_id)

    def touch_attachments(
        self, session_id: str, attachments: Optional[list[SessionAttachmentRecord]]
    ) -> None:
        """Update only attachments for an existing entry."""
        with self._lock:
            entry = self._cache.get(session_id)
            if entry is None:
                return
            entry.value.attachments = attachments
            self._cache.move_to_end(session_id)

    def acquire(self, session_id: str) -> bool:
        with self._lock:
            entry = self._cache.get(session_id)
            if entry is None:
                return False
            entry.in_use += 1
            self._cache.move_to_end(session_id)
            return True

    def release(self, session_id: str) -> None:
        with self._lock:
            entry = self._cache.get(session_id)
            if entry is None:
                return
            entry.in_use = max(0, entry.in_use - 1)
            if entry.in_use == 0:
                self._evict_idle_locked()

    def delete(self, session_id: str) -> Optional[CachedSession]:
        with self._lock:
            entry = self._cache.pop(session_id, None)
            return entry.value if entry else None

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._cache.keys())

    def stats(self) -> SessionCacheStats:
        with self._lock:
            in_use_entries = sum(
                1 for entry in self._cache.values() if entry.in_use > 0
            )
            in_use_total = sum(entry.in_use for entry in self._cache.values())
            return SessionCacheStats(
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
                    "[SESSIONS] Cache at capacity; eviction blocked by in-flight sessions (size=%d).",
                    len(self._cache),
                )
                break
