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

from typing import Any, cast

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
