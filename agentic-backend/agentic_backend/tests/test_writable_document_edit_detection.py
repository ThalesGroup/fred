from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import agentic_backend.core.chatbot.session_orchestrator as so
from agentic_backend.core.session.stores.base_writable_document_store import (
    BaseWritableDocumentStore,
    WritableDocumentAuthor,
    WritableDocumentRecord,
)

T0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


class _FakeStore(BaseWritableDocumentStore):
    def __init__(self, records: list[WritableDocumentRecord]) -> None:
        self._records = records

    async def list_for_session(self, session_id, session=None):
        return [r for r in self._records if r.session_id == session_id]

    # Unused by the helper under test.
    async def upsert(self, record, session=None):  # pragma: no cover
        raise NotImplementedError

    async def get(self, session_id, document_id, session=None):  # pragma: no cover
        raise NotImplementedError

    async def delete(self, session_id, document_id, session=None):  # pragma: no cover
        raise NotImplementedError

    async def delete_for_session(self, session_id, session=None):  # pragma: no cover
        raise NotImplementedError


def _doc(doc_id, *, updated_by, updated_at) -> WritableDocumentRecord:
    return WritableDocumentRecord(
        session_id="s1",
        document_id=doc_id,
        title=doc_id,
        content_md="x",
        updated_by=updated_by,
        created_at=T0,
        updated_at=updated_at,
    )


def _collect(records, since, monkeypatch):
    orchestrator = object.__new__(so.SessionOrchestrator)  # bypass heavy __init__
    monkeypatch.setattr(so, "get_writable_document_store", lambda: _FakeStore(records))
    return asyncio.run(
        orchestrator._collect_user_edited_documents(session_id="s1", since=since)
    )


def test_selects_only_user_edits_newer_than_since(monkeypatch):
    records = [
        _doc(
            "agent-recent",
            updated_by=WritableDocumentAuthor.agent,
            updated_at=T0 + timedelta(minutes=5),
        ),
        _doc(
            "user-old",
            updated_by=WritableDocumentAuthor.user,
            updated_at=T0 - timedelta(minutes=5),
        ),
        _doc(
            "user-recent",
            updated_by=WritableDocumentAuthor.user,
            updated_at=T0 + timedelta(minutes=5),
        ),
    ]
    selected = _collect(records, since=T0, monkeypatch=monkeypatch)
    assert [r.document_id for r in selected] == ["user-recent"]


def test_returns_empty_when_store_disabled(monkeypatch):
    orchestrator = object.__new__(so.SessionOrchestrator)
    monkeypatch.setattr(so, "get_writable_document_store", lambda: None)
    out = asyncio.run(
        orchestrator._collect_user_edited_documents(session_id="s1", since=T0)
    )
    assert out == []


def test_since_none_selects_all_user_edits(monkeypatch):
    records = [
        _doc("user-1", updated_by=WritableDocumentAuthor.user, updated_at=T0),
        _doc("agent-1", updated_by=WritableDocumentAuthor.agent, updated_at=T0),
    ]
    selected = _collect(records, since=None, monkeypatch=monkeypatch)
    assert [r.document_id for r in selected] == ["user-1"]


def test_naive_timestamps_are_compared_safely(monkeypatch):
    # Store returns naive updated_at (as SQLite may); helper must coerce to aware.
    naive_recent = (T0 + timedelta(minutes=10)).replace(tzinfo=None)
    records = [
        _doc(
            "user-recent",
            updated_by=WritableDocumentAuthor.user,
            updated_at=naive_recent,
        )
    ]
    selected = _collect(records, since=T0, monkeypatch=monkeypatch)
    assert [r.document_id for r in selected] == ["user-recent"]
