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

"""Tests for `OpenSearchLogStore.ensure_ready` mapping migration.

`category` was added to `LOG_INDEX_MAPPING` after some log indices were
already created. An existing index predates it, so `ensure_ready` must add
it additively (put_mapping) — otherwise `category` silently falls under
`dynamic="false"` and is never indexed for search, the same class of gap
`OpenSearchKPIStore._ensure_dim_mapping` closes for `dims.session_id`.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, cast

from fred_core.logs.opensearch_log_store import (
    LOG_INDEX_MAPPING,
    OpenSearchLogStore,
)


class _FakeIndices:
    """Minimal OpenSearch `indices` client backed by a mutable mapping dict."""

    def __init__(self, mappings: Dict[str, Any], index: str) -> None:
        self._mappings = mappings
        self._index = index
        self.created = False
        self.put_calls: List[Dict[str, Any]] = []

    def exists(self, *, index: str) -> bool:
        return True

    def create(self, *, index: str, body: Dict[str, Any]) -> None:
        raise AssertionError("must not create an index that already exists")

    def get_mapping(self, *, index: str) -> Dict[str, Any]:
        return {self._index: {"mappings": self._mappings}}

    def put_mapping(self, *, index: str, body: Dict[str, Any]) -> None:
        self.put_calls.append(body)
        incoming = body.get("properties", {})
        self._mappings.setdefault("properties", {}).update(incoming)


class _FakeClient:
    def __init__(self, mappings: Dict[str, Any], index: str) -> None:
        self.indices = _FakeIndices(mappings, index)


class _FakeIndicesMissingIndex:
    """Minimal OpenSearch `indices` client for a not-yet-created index."""

    def __init__(self) -> None:
        self.create_calls: List[Dict[str, Any]] = []

    def exists(self, *, index: str) -> bool:
        return False

    def create(self, *, index: str, body: Dict[str, Any]) -> None:
        self.create_calls.append(body)


class _FakeClientMissingIndex:
    def __init__(self) -> None:
        self.indices = _FakeIndicesMissingIndex()


def _store_on_existing_index(mappings: Dict[str, Any]) -> OpenSearchLogStore:
    store = OpenSearchLogStore.__new__(OpenSearchLogStore)
    store.index = "log-index"
    store.client = _FakeClient(mappings, "log-index")  # type: ignore[assignment]
    return store


def test_ensure_ready_adds_missing_category_mapping_on_existing_index() -> None:
    """An existing index missing `category` is patched additively."""
    mappings = copy.deepcopy(LOG_INDEX_MAPPING["mappings"])
    mappings["properties"].pop("category", None)
    store = _store_on_existing_index(mappings)

    store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    assert len(indices.put_calls) == 1
    assert indices.put_calls[0] == {"properties": {"category": {"type": "keyword"}}}


def test_ensure_ready_is_noop_put_when_category_already_present() -> None:
    """A complete index needs no put_mapping for `category` (idempotent)."""
    mappings = copy.deepcopy(LOG_INDEX_MAPPING["mappings"])
    store = _store_on_existing_index(mappings)

    store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    assert indices.put_calls == []


def test_ensure_ready_creates_index_unchanged_when_missing() -> None:
    """A not-yet-created index is created with LOG_INDEX_MAPPING as-is."""
    store = OpenSearchLogStore.__new__(OpenSearchLogStore)
    store.index = "log-index"
    store.client = _FakeClientMissingIndex()  # type: ignore[assignment]

    store.ensure_ready()

    indices = cast(_FakeIndicesMissingIndex, store.client.indices)
    assert indices.create_calls == [LOG_INDEX_MAPPING]
