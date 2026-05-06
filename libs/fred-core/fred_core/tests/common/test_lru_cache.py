"""
Offline unit tests for fred_core.common.lru_cache.ThreadSafeLRUCache.

Covers get/set/delete/keys/clear/__contains__ and the LRU eviction policy.
Thread-safety smoke: concurrent writers must not corrupt state.
"""

from __future__ import annotations

import threading

from fred_core.common.lru_cache import ThreadSafeLRUCache


class TestThreadSafeLRUCacheBasicOps:
    def test_get_missing_returns_none(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        assert cache.get("missing") is None

    def test_set_and_get(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        cache.set("k", 42)
        assert cache.get("k") == 42

    def test_overwrite_key(self) -> None:
        cache: ThreadSafeLRUCache[str, str] = ThreadSafeLRUCache()
        cache.set("k", "first")
        cache.set("k", "second")
        assert cache.get("k") == "second"

    def test_delete_existing_returns_value(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        cache.set("k", 99)
        assert cache.delete("k") == 99
        assert cache.get("k") is None

    def test_delete_missing_returns_none(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        assert cache.delete("ghost") is None

    def test_keys_empty(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        assert cache.keys() == []

    def test_keys_returns_all_inserted(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        cache.set("a", 1)
        cache.set("b", 2)
        assert set(cache.keys()) == {"a", "b"}

    def test_keys_excludes_deleted(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.delete("a")
        assert cache.keys() == ["b"]

    def test_contains_present(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        cache.set("k", 1)
        assert "k" in cache

    def test_contains_absent(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        assert "ghost" not in cache

    def test_clear_removes_all(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.keys() == []
        assert cache.get("a") is None


class TestThreadSafeLRUCacheEviction:
    def test_lru_evicts_oldest_when_full(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_get_promotes_to_recent(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.get("a")  # promote "a" — "b" is now the least recently used
        cache.set("d", 4)  # should evict "b"
        assert cache.get("b") is None
        assert cache.get("a") == 1

    def test_size_one_cache(self) -> None:
        cache: ThreadSafeLRUCache[str, int] = ThreadSafeLRUCache(max_size=1)
        cache.set("first", 1)
        cache.set("second", 2)
        assert cache.get("first") is None
        assert cache.get("second") == 2


class TestThreadSafeLRUCacheConcurrency:
    def test_concurrent_writes_do_not_corrupt(self) -> None:
        cache: ThreadSafeLRUCache[int, int] = ThreadSafeLRUCache(max_size=500)
        errors: list[Exception] = []

        def writer(start: int) -> None:
            try:
                for i in range(start, start + 100):
                    cache.set(i, i * 2)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i * 100,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # All written keys should either be present or have been evicted by LRU
        for key in cache.keys():
            assert cache.get(key) == key * 2
