from __future__ import annotations

from langchain_community.embeddings import FakeEmbeddings
from langchain_core.documents import Document

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD
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
