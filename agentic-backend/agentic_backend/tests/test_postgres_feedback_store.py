from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from fred_core.sql import AsyncBaseSqlStore
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text

from agentic_backend.core.feedback.feedback_structures import FeedbackRecord
from agentic_backend.core.feedback.store import (
    postgres_feedback_store as feedback_store_module,
)
from agentic_backend.core.feedback.store.postgres_feedback_store import (
    PostgresFeedbackStore,
)


class _FakeTask:
    def __init__(self, coro):
        self._coro = coro
        self._done = False

    def done(self):
        return self._done

    def __await__(self):
        async def _runner():
            try:
                return await self._coro
            finally:
                self._done = True

        return _runner().__await__()


class _FakeLoop:
    def __init__(self):
        self.task = None

    def create_task(self, coro):
        self.task = _FakeTask(coro)
        return self.task


class _FakeRow:
    def __init__(self, **values):
        self._mapping = values


class _FakeResult:
    def __init__(self, *, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._row


def _build_feedback_table() -> Table:
    return Table(
        "feedbacks",
        MetaData(),
        Column("id", String, primary_key=True),
        Column("session_id", String, nullable=False),
        Column("message_id", String, nullable=False),
        Column("agent_id", String, nullable=False),
        Column("rating", Integer, nullable=False),
        Column("comment", Text, nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("user_id", String, nullable=False),
    )


def _build_feedback() -> FeedbackRecord:
    return FeedbackRecord(
        id="fb-1",
        session_id="session-1",
        message_id="message-1",
        agent_id="agent-1",
        rating=4,
        comment="useful",
        created_at=datetime(2026, 3, 11, 12, 47, tzinfo=timezone.utc),
        user_id="user-1",
    )


def test_feedback_store_initialization_schedules_table_creation(monkeypatch):
    async def _run() -> None:
        fake_loop = _FakeLoop()
        run_ddl = AsyncMock()

        monkeypatch.setattr(
            feedback_store_module.asyncio,
            "get_running_loop",
            lambda: fake_loop,
        )
        monkeypatch.setattr(
            feedback_store_module,
            "run_ddl_with_advisory_lock",
            run_ddl,
        )

        store = PostgresFeedbackStore(
            engine=MagicMock(name="engine"),
            table_name="feedbacks",
            prefix="",
        )

        assert store._create_task is fake_loop.task
        await store._ensure_table()
        run_ddl.assert_awaited_once()

    asyncio.run(_run())


def test_feedback_store_methods_wait_for_table_and_use_row_results():
    async def _run() -> None:
        feedback = _build_feedback()
        row = _FakeRow(**feedback.model_dump())
        ensure_table = AsyncMock()
        upsert = AsyncMock()
        conn = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    _FakeResult(rows=[row]),
                    _FakeResult(row=row),
                    SimpleNamespace(rowcount=1),
                    _FakeResult(row=None),
                ]
            )
        )

        @asynccontextmanager
        async def _begin():
            yield conn

        store = object.__new__(PostgresFeedbackStore)
        store.table = _build_feedback_table()
        store.store = cast(
            AsyncBaseSqlStore,
            SimpleNamespace(begin=_begin, upsert=upsert),
        )
        store._ensure_table = ensure_table

        listed = await store.list()
        stored = await store.get(feedback.id)
        await store.save(feedback)
        await store.delete(feedback.id)
        missing = await store.get(feedback.id)

        assert [item.id for item in listed] == [feedback.id]
        assert stored is not None
        assert stored.id == feedback.id
        assert missing is None
        assert ensure_table.await_count == 5

        upsert.assert_awaited_once()
        upsert_call = upsert.await_args
        assert upsert_call is not None
        assert upsert_call.args[1] is store.table
        assert upsert_call.kwargs["values"]["created_at"] == feedback.created_at
        assert upsert_call.kwargs["pk_cols"] == ["id"]

    asyncio.run(_run())
