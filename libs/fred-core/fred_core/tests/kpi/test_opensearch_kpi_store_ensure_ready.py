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

"""Tests for `OpenSearchKPIStore.ensure_ready` mapping migration (CTRLP-12).

An existing `kpi-index` predates the `dims.session_id` field that RGPD
conversation erasure needs. On startup, ensure_ready validates the live index
against the expected mapping and hard-fails on a missing field — so it must first
add new dims *additively* (put_mapping), exactly as it already does for other
fields. This is the regression guard for the "Missing nested field:
'dims.session_id'" startup crash.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, cast

from fred_core.kpi.opensearch_kpi_store import KPI_INDEX_MAPPING, OpenSearchKPIStore


class _FakeIndices:
    """Minimal OpenSearch `indices` client backed by a mutable mapping dict."""

    def __init__(self, mappings: Dict[str, Any], index: str) -> None:
        self._mappings = mappings
        self._index = index
        self.put_calls: List[Dict[str, Any]] = []

    def exists(self, *, index: str) -> bool:
        return True

    def create(self, *, index: str, body: Dict[str, Any]) -> None:
        raise AssertionError("must not create an index that already exists")

    def get_mapping(self, *, index: str) -> Dict[str, Any]:
        return {self._index: {"mappings": self._mappings}}

    def put_mapping(self, *, index: str, body: Dict[str, Any]) -> None:
        self.put_calls.append(body)
        incoming = body.get("properties", {}).get("dims", {}).get("properties", {})
        dims = (
            self._mappings.setdefault("properties", {})
            .setdefault("dims", {})
            .setdefault("properties", {})
        )
        dims.update(incoming)


class _FakeClient:
    def __init__(self, mappings: Dict[str, Any], index: str) -> None:
        self.indices = _FakeIndices(mappings, index)


def _store_on_existing_index_missing(field: str) -> OpenSearchKPIStore:
    """A store bound to an existing index whose mapping lacks `dims.<field>`."""
    mappings = copy.deepcopy(KPI_INDEX_MAPPING["mappings"])
    mappings["properties"]["dims"]["properties"].pop(field, None)
    store = OpenSearchKPIStore.__new__(OpenSearchKPIStore)
    store.index = "kpi-index"
    store.client = _FakeClient(mappings, "kpi-index")  # type: ignore[assignment]
    return store


def test_ensure_ready_adds_missing_session_id_dim_on_existing_index() -> None:
    """An existing index missing dims.session_id is patched, not rejected."""
    store = _store_on_existing_index_missing("session_id")

    # Previously raised MappingValidationError("Missing nested field:
    # 'dims.session_id'") and crashed app startup.
    store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    patched = [
        next(iter(b["properties"]["dims"]["properties"])) for b in indices.put_calls
    ]
    assert "session_id" in patched


def test_ensure_ready_is_noop_put_when_session_id_already_present() -> None:
    """A fresh/complete index needs no put_mapping for session_id (idempotent)."""
    mappings = copy.deepcopy(KPI_INDEX_MAPPING["mappings"])
    store = OpenSearchKPIStore.__new__(OpenSearchKPIStore)
    store.index = "kpi-index"
    store.client = _FakeClient(mappings, "kpi-index")  # type: ignore[assignment]

    store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    patched = [
        next(iter(b["properties"]["dims"]["properties"])) for b in indices.put_calls
    ]
    assert "session_id" not in patched
