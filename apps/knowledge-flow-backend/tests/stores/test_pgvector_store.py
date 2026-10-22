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

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_core.documents import Document

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, SearchFilter
from knowledge_flow_backend.core.stores.vector.pgvector_store import PgVectorStoreAdapter


class _FakePGVector:
    """Applies a PGVector metadata filter the way SQL does: a plain value is $eq, a dict may hold $in."""

    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.filters: list[Any] = []

    def similarity_search_with_relevance_scores(self, query: str, *, k: int, filter: dict[str, Any] | None = None):
        self.filters.append(filter)

        def matches(md: dict[str, Any]) -> bool:
            for key, cond in (filter or {}).items():
                if isinstance(cond, dict):
                    if md.get(key) not in cond["$in"]:
                        return False
                elif md.get(key) != cond:
                    return False
            return True

        return [(doc, 1.0) for doc in self.documents if matches(doc.metadata)][:k]


def _make_store(documents: list[Document]) -> tuple[PgVectorStoreAdapter, _FakePGVector]:
    fake = _FakePGVector(documents)
    store = PgVectorStoreAdapter.__new__(PgVectorStoreAdapter)
    store.collection_name = "test-collection"
    store._vs = cast(Any, fake)
    return store, fake


def _chunk(document_uid: str, index: int) -> Document:
    return Document(
        page_content=f"chunk {index} of {document_uid}",
        metadata={CHUNK_ID_FIELD: f"{document_uid}-{index}", "document_uid": document_uid, "retrievable": True},
    )


def test_ann_search_pushes_every_requested_document_uid_to_sql():
    store, fake = _make_store([_chunk(uid, i) for uid in ("doc-a", "doc-b", "doc-c") for i in range(2)])

    hits = store.ann_search(
        "chunk",
        k=10,
        search_filter=SearchFilter(metadata_terms={"retrievable": [True], "document_uid": ["doc-a", "doc-b"]}),
    )

    assert fake.filters == [{"document_uid": {"$in": ["doc-a", "doc-b"]}}]
    assert {h.document.metadata["document_uid"] for h in hits} == {"doc-a", "doc-b"}


def test_ann_search_keeps_a_single_value_as_plain_equality():
    store, fake = _make_store([_chunk(uid, 0) for uid in ("doc-a", "doc-b")])

    hits = store.ann_search("chunk", k=10, search_filter=SearchFilter(metadata_terms={"document_uid": ["doc-a"]}))

    assert fake.filters == [{"document_uid": "doc-a"}]
    assert [h.document.metadata["document_uid"] for h in hits] == ["doc-a"]


class _RecordingEngine:
    """Captures the statement and parameters `set_document_tag_ids` sends."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict[str, Any]]] = []

    def begin(self):
        engine = self

        class _Conn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, statement, params):
                engine.executed.append((str(statement), params))
                return type("Result", (), {"rowcount": 2})()

        return _Conn()


def test_set_document_tag_ids_replaces_the_jsonb_array_on_every_chunk():
    store, _ = _make_store([])
    engine = _RecordingEngine()
    store._engine = cast(Any, engine)

    store.set_document_tag_ids(document_uid="doc-1", tag_ids=["alpha", "beta"])

    [(sql, params)] = engine.executed
    assert "jsonb_set(e.cmetadata, '{tag_ids}', CAST(:tag_ids AS jsonb))" in sql
    assert params == {"collection": "test-collection", "doc_uid": "doc-1", "tag_ids": '["alpha", "beta"]'}


class _FakeEngine:
    """Applies the adapter's retrievable UPDATE to the fake store's chunks, matching on document and collection."""

    def __init__(self, fake: _FakePGVector, collection: str, *, fail: bool = False) -> None:
        self.fake = fake
        self.collection = collection
        self.fail = fail
        self.statements: list[tuple[str, dict[str, Any]]] = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement: Any, params: dict[str, Any]):
        if self.fail:
            raise ConnectionError("database unavailable")
        sql = str(statement)
        self.statements.append((sql, params))
        assert "jsonb_set(e.cmetadata, '{retrievable}'" in sql
        updated = 0
        if params["collection"] == self.collection:
            for doc in self.fake.documents:
                if doc.metadata.get("document_uid") == params["doc_uid"]:
                    doc.metadata["retrievable"] = params["value"]
                    updated += 1
        return SimpleNamespace(rowcount=updated)


def _searchable_uids(store: PgVectorStoreAdapter) -> set[str]:
    hits = store.ann_search("chunk", k=10, search_filter=SearchFilter(metadata_terms={"retrievable": [True]}))
    return {h.document.metadata["document_uid"] for h in hits}


def test_retrievable_toggle_round_trip_hides_then_restores_only_that_document():
    store, fake = _make_store([_chunk(uid, i) for uid in ("doc-a", "doc-b") for i in range(2)])
    engine = _FakeEngine(fake, "test-collection")
    store._engine = cast(Any, engine)

    store.set_document_retrievable(document_uid="doc-a", value=False)

    assert engine.statements[0][1] == {"collection": "test-collection", "doc_uid": "doc-a", "value": False}
    assert {d.metadata["document_uid"]: d.metadata["retrievable"] for d in fake.documents} == {"doc-a": False, "doc-b": True}
    assert _searchable_uids(store) == {"doc-b"}

    store.set_document_retrievable(document_uid="doc-a", value=True)

    assert all(d.metadata["retrievable"] is True for d in fake.documents)
    assert _searchable_uids(store) == {"doc-a", "doc-b"}


def test_ann_search_keeps_legacy_chunks_without_a_retrievable_field():
    legacy = Document(page_content="chunk 0 of doc-old", metadata={CHUNK_ID_FIELD: "doc-old-0", "document_uid": "doc-old"})
    store, _ = _make_store([legacy, _chunk("doc-a", 0)])

    assert _searchable_uids(store) == {"doc-old", "doc-a"}


def test_retrievable_toggle_raises_when_the_update_fails():
    store, fake = _make_store([_chunk("doc-a", 0)])
    store._engine = cast(Any, _FakeEngine(fake, "test-collection", fail=True))

    with pytest.raises(RuntimeError, match="retrievable"):
        store.set_document_retrievable(document_uid="doc-a", value=False)
