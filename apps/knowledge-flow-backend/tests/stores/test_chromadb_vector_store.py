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

import subprocess
import sys

from langchain_community.embeddings import FakeEmbeddings
from langchain_core.documents import Document

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, SearchFilter
from knowledge_flow_backend.core.stores.vector.chromadb_vector_store import ChromaDBVectorStore


def _make_store(tmp_path) -> ChromaDBVectorStore:
    return ChromaDBVectorStore(
        persist_path=str(tmp_path / "chroma"),
        collection_name="test-collection",
        embeddings=FakeEmbeddings(size=8),
        embedding_model_name="fake-embeddings",
    )


def test_add_documents_reingestion_upserts_by_chunk_uid(tmp_path):
    """
    Chroma's `Collection.add()` raises on a duplicate id, which (before this
    fix) was swallowed by the caller's broad except and left the stale chunk
    in place. `Collection.upsert()` must replace the existing record for a
    matching chunk_uid instead of erroring or silently no-op'ing.

    This is the property RAG-DATASET-DISCOVERY-RFC.md relies on for dataset
    pointer chunks: "exactly one pointer chunk per dataset, upserted
    idempotently by a deterministic chunk_uid".
    """
    store = _make_store(tmp_path)
    chunk_uid = "doc-1::pointer"

    first = Document(
        page_content="stale title and columns",
        metadata={CHUNK_ID_FIELD: chunk_uid, "document_uid": "doc-1"},
    )
    store.add_documents([first])

    second = Document(
        page_content="fresh title and columns",
        metadata={CHUNK_ID_FIELD: chunk_uid, "document_uid": "doc-1"},
    )
    store.add_documents([second])

    chunks = store.get_chunks_for_document("doc-1")
    assert len(chunks) == 1, f"expected exactly one chunk for chunk_uid={chunk_uid}, got {len(chunks)}"
    assert chunks[0]["chunk_uid"] == chunk_uid
    assert chunks[0]["text"] == "fresh title and columns"


def test_add_documents_distinct_chunk_uids_are_both_kept(tmp_path):
    store = _make_store(tmp_path)

    doc_a = Document(page_content="a", metadata={CHUNK_ID_FIELD: "doc-1::chunk::0", "document_uid": "doc-1"})
    doc_b = Document(page_content="b", metadata={CHUNK_ID_FIELD: "doc-1::chunk::1", "document_uid": "doc-1"})
    store.add_documents([doc_a, doc_b])

    chunks = store.get_chunks_for_document("doc-1")
    assert len(chunks) == 2
    assert {c["chunk_uid"] for c in chunks} == {"doc-1::chunk::0", "doc-1::chunk::1"}


def test_persisted_chunks_can_be_searched_and_deleted_after_restart(tmp_path):
    store = _make_store(tmp_path)
    store.add_documents([Document(page_content="persistent local knowledge", metadata={CHUNK_ID_FIELD: "doc-1::chunk::0", "document_uid": "doc-1"})])
    # A separate interpreter cannot reuse the parent's cached Chroma client.
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from langchain_community.embeddings import FakeEmbeddings
from knowledge_flow_backend.core.stores.vector.chromadb_vector_store import ChromaDBVectorStore

store = ChromaDBVectorStore(
    persist_path=sys.argv[1], collection_name="test-collection",
    embeddings=FakeEmbeddings(size=8), embedding_model_name="fake-embeddings",
)
chunks = store.get_chunks_for_document("doc-1")
assert len(chunks) == 1 and chunks[0]["text"] == "persistent local knowledge"
hits = store.ann_search("local knowledge", k=1)
assert len(hits) == 1 and hits[0].document.metadata["document_uid"] == "doc-1"
store.delete_vectors_for_document(document_uid="doc-1")
assert store.get_chunks_for_document("doc-1") == []
""",
            str(tmp_path / "chroma"),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _found(store: ChromaDBVectorStore, tag_id: str) -> set[str]:
    return {h.document.metadata["document_uid"] for h in store.ann_search("report", k=5, search_filter=SearchFilter(tag_ids=[tag_id]))}


def test_a_document_in_several_folders_matches_each_of_them(tmp_path):
    store = _make_store(tmp_path)
    store.add_documents([Document(page_content="report", metadata={CHUNK_ID_FIELD: "doc-1::chunk::0", "document_uid": "doc-1", "tag_ids": ["alpha", "beta"]})])

    assert (_found(store, "alpha"), _found(store, "beta"), _found(store, "gamma")) == ({"doc-1"}, {"doc-1"}, set())
    assert store.get_chunks_for_document("doc-1")[0]["metadata"]["tag_ids"] == ["alpha", "beta"]


def test_chunks_stored_as_one_folder_json_strings_still_match(tmp_path):
    store = _make_store(tmp_path)
    store._collection.upsert(ids=["legacy::0"], embeddings=[[0.1] * 8], documents=["report"], metadatas=[{"document_uid": "legacy", "tag_ids": '["alpha"]'}])

    assert _found(store, "alpha") == {"legacy"}
    assert _found(store, "beta") == set()


def test_set_document_tag_ids_moves_the_document_between_folder_filters(tmp_path):
    store = _make_store(tmp_path)
    store.add_documents([Document(page_content="report", metadata={CHUNK_ID_FIELD: "doc-1::chunk::0", "document_uid": "doc-1", "tag_ids": ["alpha"]})])

    store.set_document_tag_ids(document_uid="doc-1", tag_ids=["alpha", "beta"])
    assert (_found(store, "alpha"), _found(store, "beta"), _found(store, "gamma")) == ({"doc-1"}, {"doc-1"}, set())

    store.set_document_tag_ids(document_uid="doc-1", tag_ids=["beta"])
    assert (_found(store, "alpha"), _found(store, "beta")) == (set(), {"doc-1"})
    assert store.get_chunks_for_document("doc-1")[0]["metadata"]["tag_ids"] == ["beta"]
