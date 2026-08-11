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

Guarded beyond that one field since 2026-08-11: what to patch is diffed against
KPI_INDEX_MAPPING rather than read off a hand-kept list of recent names, because
the list was one more thing to remember and the field that forgot it took
startup down on every pre-existing index.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, cast

import pytest
from fred_core.kpi.opensearch_kpi_store import KPI_INDEX_MAPPING, OpenSearchKPIStore
from fred_core.store import MappingValidationError


def _deep_merge(target: Dict[str, Any], patch: Dict[str, Any]) -> None:
    """Apply a `put_mapping` body the way OpenSearch does — merge, never replace.

    A shallow merge would model the index wrongly now that the store sends whole
    missing branches (a root field, or a nested object with its own properties)
    rather than only leaves under `dims`/`quantities`.
    """
    for name, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(name), dict):
            _deep_merge(target[name], value)
        else:
            target[name] = value


class _FakeIndices:
    """Minimal OpenSearch `indices` client backed by a mutable mapping dict."""

    def __init__(self, mappings: Dict[str, Any], index: str) -> None:
        self._mappings = mappings
        self._index = index
        self.put_calls: List[Dict[str, Any]] = []
        self.get_mapping_calls = 0

    def exists(self, *, index: str) -> bool:
        return True

    def create(self, *, index: str, body: Dict[str, Any]) -> None:
        raise AssertionError("must not create an index that already exists")

    def get_mapping(self, *, index: str) -> Dict[str, Any]:
        self.get_mapping_calls += 1
        return {self._index: {"mappings": self._mappings}}

    def put_mapping(self, *, index: str, body: Dict[str, Any]) -> None:
        self.put_calls.append(body)
        _deep_merge(
            self._mappings.setdefault("properties", {}), body.get("properties", {})
        )


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


def test_ensure_ready_patches_every_missing_field_in_one_round_trip() -> None:
    """Startup must not re-read the whole index mapping once per field.

    Each missing field used to trigger its own `get_mapping` + `put_mapping`
    (~15 round trips per store on every boot) for an answer the first response
    already contained.
    """
    store = _store_on_existing_index_missing("session_id")
    mappings = cast(_FakeIndices, cast(_FakeClient, store.client).indices)._mappings
    mappings["properties"]["dims"]["properties"].pop("team_id", None)
    mappings["properties"]["quantities"]["properties"].pop("input_tokens", None)

    store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    # One read to diff, one after patching — validation judges the live index,
    # not an optimistic local merge of what we believe we just wrote.
    assert indices.get_mapping_calls == 2
    assert len(indices.put_calls) == 1
    body = indices.put_calls[0]["properties"]
    assert set(body["dims"]["properties"]) == {"session_id", "team_id"}
    assert set(body["quantities"]["properties"]) == {"input_tokens"}


def test_ensure_ready_adds_a_field_no_hardcoded_list_ever_knew_about() -> None:
    """The real regression: the patch set is diffed, not enumerated.

    `dims.tool_name` shipped with the very first mapping, so it never appeared in
    the hand-kept "fields added since v1" list. Under that list an index lacking
    it — any index whose mapping drifted, or that predates a dim someone added
    without touching the second list — crashed startup with no recovery but
    deleting the kpi index. Every field of KPI_INDEX_MAPPING must be patchable,
    not just the ones somebody remembered to register.
    """
    store = _store_on_existing_index_missing("tool_name")

    store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    assert len(indices.put_calls) == 1
    assert set(indices.put_calls[0]["properties"]["dims"]["properties"]) == {
        "tool_name"
    }


def test_ensure_ready_adds_a_whole_missing_top_level_branch() -> None:
    """An index predating a whole object (here `trace`) gets it with its leaves."""
    mappings = copy.deepcopy(KPI_INDEX_MAPPING["mappings"])
    mappings["properties"].pop("trace")
    store = OpenSearchKPIStore.__new__(OpenSearchKPIStore)
    store.index = "kpi-index"
    store.client = _FakeClient(mappings, "kpi-index")  # type: ignore[assignment]

    store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    added = indices.put_calls[0]["properties"]["trace"]["properties"]
    assert set(added) == {"trace_id", "span_id", "parent_span_id"}


def test_ensure_ready_leaves_type_drift_to_the_validator() -> None:
    """A field whose type drifted is reported, not silently put_mapping'd.

    OpenSearch cannot change an existing field's type, so sending it would make
    it reject the whole request — taking the legitimately-missing fields in the
    same call down with it. The store patches what is absent and lets
    validate_index_mapping raise on the rest.
    """
    store = _store_on_existing_index_missing("session_id")
    mappings = cast(_FakeIndices, cast(_FakeClient, store.client).indices)._mappings
    mappings["properties"]["dims"]["properties"]["model"] = {"type": "text"}

    with pytest.raises(MappingValidationError):
        store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    patched = indices.put_calls[0]["properties"]["dims"]["properties"]
    assert set(patched) == {"session_id"}  # the drifted `model` is not in there


def test_ensure_ready_writes_nothing_when_the_index_is_current() -> None:
    """The common case — an up-to-date index — costs exactly one read, no write.

    Every boot but a migrating one lands here, so the diff and the validation
    share the single `get_mapping` response rather than asking twice.
    """
    store = OpenSearchKPIStore.__new__(OpenSearchKPIStore)
    store.index = "kpi-index"
    client = _FakeClient(copy.deepcopy(KPI_INDEX_MAPPING["mappings"]), "kpi-index")
    store.client = client  # type: ignore[assignment]

    store.ensure_ready()

    indices = cast(_FakeIndices, cast(_FakeClient, store.client).indices)
    assert indices.put_calls == []
    assert indices.get_mapping_calls == 1
