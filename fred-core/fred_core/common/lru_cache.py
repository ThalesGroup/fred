from collections import OrderedDict
from threading import Lock
from typing import Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class ThreadSafeLRUCache(Generic[K, V]):
    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._lock = Lock()
        self._cache: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        with self._lock:
            value = self._cache.get(key)
            if value is not None:
                self._cache.move_to_end(key)  # Mark as recently used
            return value

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)  # Remove LRU

    def delete(self, key: K) -> Optional[V]:
        with self._lock:
            return self._cache.pop(key, None)

    def keys(self) -> list[K]:
        with self._lock:
            return list(self._cache.keys())

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self._cache
