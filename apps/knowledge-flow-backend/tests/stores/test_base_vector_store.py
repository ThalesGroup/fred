from __future__ import annotations

from typing import Any, Dict, List

from knowledge_flow_backend.core.stores.vector.base_vector_store import (
    BaseVectorStore,
    is_own_session_chunk,
)


def test_is_own_session_chunk_requires_session_scope_and_matching_user():
    owned = {"metadata": {"scope": "session", "user_id": "alice"}}
    other_user = {"metadata": {"scope": "session", "user_id": "mallory"}}
    corpus_chunk = {"metadata": {"scope": "library", "user_id": "alice"}}
    no_metadata = {}

    assert is_own_session_chunk(owned, "alice") is True
    assert is_own_session_chunk(other_user, "alice") is False
    assert is_own_session_chunk(corpus_chunk, "alice") is False
    assert is_own_session_chunk(no_metadata, "alice") is False


class _FakeChunkStore(BaseVectorStore):
    def __init__(self, chunks: List[Dict[str, Any]] | None = None, *, unsupported: bool = False):
        self._chunks = chunks or []
        self._unsupported = unsupported

    def add_documents(self, documents, *, ids=None):
        raise NotImplementedError

    def delete_vectors_for_document(self, *, document_uid: str) -> None:
        raise NotImplementedError

    def ann_search(self, query, *, k, search_filter=None):
        raise NotImplementedError

    def get_chunks_for_document(self, document_uid: str) -> List[Dict[str, Any]]:
        if self._unsupported:
            raise NotImplementedError
        return self._chunks


def test_owns_session_document_true_when_a_chunk_matches():
    store = _FakeChunkStore([{"metadata": {"scope": "session", "user_id": "alice"}}])
    assert store.owns_session_document("doc-1", "alice") is True


def test_owns_session_document_false_for_different_user():
    store = _FakeChunkStore([{"metadata": {"scope": "session", "user_id": "mallory"}}])
    assert store.owns_session_document("doc-1", "alice") is False


def test_owns_session_document_fails_closed_when_unsupported():
    store = _FakeChunkStore(unsupported=True)
    assert store.owns_session_document("doc-1", "alice") is False
