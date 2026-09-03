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


def test_may_delete_session_document_true_when_a_chunk_matches():
    store = _FakeChunkStore([{"metadata": {"scope": "session", "user_id": "alice"}}])
    assert store.may_delete_session_document("doc-1", "alice") is True


def test_may_delete_session_document_false_for_different_user():
    store = _FakeChunkStore([{"metadata": {"scope": "session", "user_id": "mallory"}}])
    assert store.may_delete_session_document("doc-1", "alice") is False


def test_may_delete_session_document_true_when_no_chunks_left():
    """Idempotent-retry case: an earlier delete already removed every chunk,
    so there is nothing left to prove ownership over -- must not deny forever."""
    store = _FakeChunkStore([])
    assert store.may_delete_session_document("doc-1", "alice") is True


def test_may_delete_session_document_fails_closed_when_unsupported():
    store = _FakeChunkStore(unsupported=True)
    assert store.may_delete_session_document("doc-1", "alice") is False


def _session_chunk(
    text: str,
    *,
    user_id: str,
    page: int | None = None,
    scope: str = "session",
    truncated: bool | None = None,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"scope": scope, "user_id": user_id}
    if page is not None:
        metadata["page"] = page
    if truncated is not None:
        metadata["truncated"] = truncated
    return {"chunk_uid": f"c-{page}", "text": text, "metadata": metadata}


def test_get_own_session_document_text_joins_owned_chunks_in_page_order():
    store = _FakeChunkStore(
        [
            _session_chunk("Second page.", user_id="alice", page=2),
            _session_chunk("First page.", user_id="alice", page=1),
        ]
    )
    assert store.get_own_session_document_text("att-1", "alice") == "First page.\n\nSecond page."


def test_get_own_session_document_text_ignores_another_users_chunks():
    store = _FakeChunkStore([_session_chunk("Secret.", user_id="mallory", page=1)])
    assert store.get_own_session_document_text("att-1", "alice") == ""


def test_get_own_session_document_text_never_reconstructs_corpus_chunks():
    """A corpus document the caller was DENIED may still carry chunks stamped
    with their user_id. Reconstructing those would turn the fallback into a
    ReBAC bypass, so only session-scoped chunks are ever joined."""
    store = _FakeChunkStore([_session_chunk("Corpus secret.", user_id="alice", page=1, scope="library")])
    assert store.get_own_session_document_text("doc-1", "alice") == ""


def test_get_own_session_document_text_handles_chunks_without_a_page():
    """The single combined-doc fast-ingest fallback stores no 'page' key."""
    store = _FakeChunkStore([_session_chunk("Whole doc.", user_id="alice", page=None)])
    assert store.get_own_session_document_text("att-1", "alice") == "Whole doc."


def test_get_own_session_document_text_empty_when_backend_cannot_fetch_chunks():
    store = _FakeChunkStore(unsupported=True)
    assert store.get_own_session_document_text("att-1", "alice") == ""


def test_get_own_session_document_text_flags_a_clipped_attachment():
    """Fast ingest drops whole pages past its char cap. read_document and
    extract_from_document both promise completeness, so a clipped attachment
    must not come back looking whole."""
    store = _FakeChunkStore([_session_chunk("Head of the file.", user_id="alice", page=1, truncated=True)])

    text = store.get_own_session_document_text("att-1", "alice")

    assert text.startswith("Head of the file.")
    assert "NOT the complete document" in text


def test_get_own_session_document_text_stays_silent_for_a_whole_attachment():
    """Includes attachments ingested before the flag existed (no key at all)."""
    complete = _FakeChunkStore([_session_chunk("All of it.", user_id="alice", page=1, truncated=False)])
    legacy = _FakeChunkStore([_session_chunk("All of it.", user_id="alice", page=1)])

    assert complete.get_own_session_document_text("att-1", "alice") == "All of it."
    assert legacy.get_own_session_document_text("att-1", "alice") == "All of it."
