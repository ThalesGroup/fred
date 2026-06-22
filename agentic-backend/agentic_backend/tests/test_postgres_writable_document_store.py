from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from agentic_backend.core.session.stores.base_writable_document_store import (
    WritableDocumentAuthor,
    WritableDocumentRecord,
)
from agentic_backend.core.session.stores.postgres_writable_document_store import (
    PostgresWritableDocumentStore,
)
from agentic_backend.core.session.stores.writable_document_models import (
    WritableDocumentRow,
)


async def _make_store() -> PostgresWritableDocumentStore:
    # Real in-memory async SQLite: exercises the actual upsert/get/list/delete SQL,
    # fully offline (no Postgres). The shared connection keeps the in-memory schema alive.
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(WritableDocumentRow.metadata.create_all)
    return PostgresWritableDocumentStore(engine=engine)


def _record(doc_id: str = "doc-1", content: str = "# Hello") -> WritableDocumentRecord:
    return WritableDocumentRecord(
        session_id="session-1",
        document_id=doc_id,
        title="Draft",
        content_md=content,
        updated_by=WritableDocumentAuthor.agent,
    )


def test_upsert_creates_then_updates_and_get():
    async def _run() -> None:
        store = await _make_store()

        created = await store.upsert(_record())
        assert created.created_at is not None
        assert created.updated_at is not None
        assert created.updated_by == WritableDocumentAuthor.agent

        fetched = await store.get("session-1", "doc-1")
        assert fetched is not None
        assert fetched.content_md == "# Hello"

        # Update same (session, doc): content + author change, created_at preserved.
        updated = await store.upsert(
            WritableDocumentRecord(
                session_id="session-1",
                document_id="doc-1",
                title="Draft v2",
                content_md="# Edited",
                updated_by=WritableDocumentAuthor.user,
            )
        )
        assert updated.title == "Draft v2"
        assert updated.content_md == "# Edited"
        assert updated.updated_by == WritableDocumentAuthor.user
        # created_at is preserved across updates. (Compare naive instants: SQLite does
        # not round-trip tzinfo the way Postgres does, which is a test-env artifact only.)
        assert updated.created_at is not None
        assert created.created_at is not None
        assert updated.created_at.replace(tzinfo=None) == created.created_at.replace(
            tzinfo=None
        )

        # Still a single row for that (session, doc).
        listed = await store.list_for_session("session-1")
        assert len(listed) == 1
        assert listed[0].content_md == "# Edited"

    asyncio.run(_run())


def test_list_is_scoped_to_session():
    async def _run() -> None:
        store = await _make_store()
        await store.upsert(_record("doc-1"))
        await store.upsert(_record("doc-2"))
        await store.upsert(
            WritableDocumentRecord(
                session_id="session-OTHER",
                document_id="doc-3",
                title="Other",
                content_md="x",
            )
        )

        listed = await store.list_for_session("session-1")
        assert {r.document_id for r in listed} == {"doc-1", "doc-2"}

    asyncio.run(_run())


def test_delete_and_delete_for_session():
    async def _run() -> None:
        store = await _make_store()
        await store.upsert(_record("doc-1"))
        await store.upsert(_record("doc-2"))

        await store.delete("session-1", "doc-1")
        assert await store.get("session-1", "doc-1") is None
        assert {r.document_id for r in await store.list_for_session("session-1")} == {
            "doc-2"
        }

        await store.delete_for_session("session-1")
        assert await store.list_for_session("session-1") == []

    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
