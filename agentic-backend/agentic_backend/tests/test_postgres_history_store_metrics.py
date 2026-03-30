from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from agentic_backend.core.monitoring.postgres_history_store import PostgresHistoryStore


class _FakeResult:
    def __init__(self):
        self.statement = None

    def scalars(self):
        return MagicMock(all=MagicMock(return_value=[]))


class _FakeSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _FakeResult()


@pytest.mark.asyncio
async def test_get_chatbot_metrics_binds_datetime_filters():
    fake_session = _FakeSession()

    store = cast(Any, object.__new__(PostgresHistoryStore))
    store._sessions = None  # bypassed __init__; use_session is patched below

    with patch(
        "agentic_backend.core.monitoring.postgres_history_store.use_session"
    ) as mock_use_session:
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _fake_use_session(factory, session=None):
            yield fake_session

        mock_use_session.side_effect = _fake_use_session

        response = await cast(PostgresHistoryStore, store).get_chatbot_metrics(
            start="2026-02-15T16:00:00.000Z",
            end="2026-02-16T04:59:59.999Z",
            user_id="u-1",
            precision="hour",
            groupby=[],
            agg_mapping={},
        )

    assert response.buckets == []
    assert fake_session.statement is not None

    compiled = fake_session.statement.compile(dialect=postgresql.dialect())
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
    store = cast(Any, object.__new__(PostgresHistoryStore))
    store._sessions = None  # bypassed __init__; use_session is patched below

    with patch("agentic_backend.core.monitoring.postgres_history_store.use_session"):
        with pytest.raises(ValueError, match=r"Invalid 'start' timestamp"):
            await cast(PostgresHistoryStore, store).get_chatbot_metrics(
                start="not-a-datetime",
                end="2026-02-16T04:59:59.999Z",
                user_id="u-1",
                precision="hour",
                groupby=[],
                agg_mapping={},
            )
