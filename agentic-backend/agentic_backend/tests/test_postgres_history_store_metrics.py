from datetime import datetime, timezone
from typing import Any, cast

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects import postgresql

from agentic_backend.core.monitoring.postgres_history_store import PostgresHistoryStore


class _FakeResult:
    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _FakeResult()


class _FakeBeginContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeStore:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return _FakeBeginContext(self.conn)


@pytest.mark.asyncio
async def test_get_chatbot_metrics_binds_datetime_filters():
    conn = _FakeConn()

    # Bypass __init__ on purpose to isolate the SQL filter typing behavior.
    # Use Any during setup because we inject test doubles for internals.
    store = cast(Any, object.__new__(PostgresHistoryStore))
    store.store = _FakeStore(conn)
    store.table = Table(
        "session_history",
        MetaData(),
        Column("session_id", String),
        Column("user_id", String),
        Column("rank", Integer),
        Column("timestamp", DateTime(timezone=True)),
        Column("role", String),
        Column("channel", String),
        Column("exchange_id", String),
        Column("parts_json", String),
        Column("metadata_json", String),
    )

    response = await cast(PostgresHistoryStore, store).get_chatbot_metrics(
        start="2026-02-15T16:00:00.000Z",
        end="2026-02-16T04:59:59.999Z",
        user_id="u-1",
        precision="hour",
        groupby=[],
        agg_mapping={},
    )

    assert response.buckets == []
    assert conn.statement is not None

    compiled = conn.statement.compile(dialect=postgresql.dialect())
    timestamp_params = {
        key: value for key, value in compiled.params.items() if "timestamp" in key
    }

    assert len(timestamp_params) == 2
    assert all(isinstance(value, datetime) for value in timestamp_params.values())
    assert all(value.tzinfo is not None for value in timestamp_params.values())

    expected_values = {
        datetime(2026, 2, 15, 16, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 2, 16, 4, 59, 59, 999000, tzinfo=timezone.utc),
    }
    assert set(timestamp_params.values()) == expected_values


@pytest.mark.asyncio
async def test_get_chatbot_metrics_rejects_invalid_start_timestamp():
    conn = _FakeConn()

    store = cast(Any, object.__new__(PostgresHistoryStore))
    store.store = _FakeStore(conn)
    store.table = Table(
        "session_history",
        MetaData(),
        Column("session_id", String),
        Column("user_id", String),
        Column("rank", Integer),
        Column("timestamp", DateTime(timezone=True)),
        Column("role", String),
        Column("channel", String),
        Column("exchange_id", String),
        Column("parts_json", String),
        Column("metadata_json", String),
    )

    with pytest.raises(ValueError, match=r"Invalid 'start' timestamp"):
        await cast(PostgresHistoryStore, store).get_chatbot_metrics(
            start="not-a-datetime",
            end="2026-02-16T04:59:59.999Z",
            user_id="u-1",
            precision="hour",
            groupby=[],
            agg_mapping={},
        )
