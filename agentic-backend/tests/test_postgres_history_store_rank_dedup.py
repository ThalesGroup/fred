# Copyright Thales 2025
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

"""Regression test for PostgresHistoryStore.save rank-collision handling.

A multi-row `INSERT ... ON CONFLICT (session_id, user_id, rank) DO UPDATE`
raises Postgres CardinalityViolationError if two rows in the same batch share
the conflict key. This happened when a system_note (attachment upload / edited
doc) was injected and the agent run then failed: the error-fallback message was
assigned the same rank as the system_note. `save` now collapses same-rank rows
to the last occurrence so a stray caller-side collision degrades gracefully
instead of losing the whole exchange.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import patch

import pytest

from agentic_backend.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    Role,
    TextPart,
)
from agentic_backend.core.monitoring.postgres_history_store import PostgresHistoryStore

_TS = datetime(2026, 7, 7, 16, 10, 10, tzinfo=timezone.utc)


class _FakeSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement


def _msg(rank: int, role: Role, channel: Channel, text: str) -> ChatMessage:
    return ChatMessage(
        session_id="sess-1",
        exchange_id="ex-1",
        rank=rank,
        timestamp=_TS,
        role=role,
        channel=channel,
        parts=[TextPart(text=text)],
    )


async def _save(messages):
    fake_session = _FakeSession()
    store = cast(Any, object.__new__(PostgresHistoryStore))
    store._sessions = None  # __init__ bypassed; use_session is patched

    with patch(
        "agentic_backend.core.monitoring.postgres_history_store.use_session"
    ) as mock_use_session:

        @asynccontextmanager
        async def _fake_use_session(factory, session=None):
            yield fake_session

        mock_use_session.side_effect = _fake_use_session

        await cast(PostgresHistoryStore, store).save(
            session_id="sess-1", messages=messages, user_id="u-1"
        )
    return fake_session.statement


@pytest.mark.asyncio
async def test_duplicate_ranks_are_collapsed_to_last_occurrence():
    """user(0) + system_note(1) + error-fallback(1) must not crash the upsert."""
    messages = [
        _msg(0, Role.user, Channel.final, "generate a user manual"),
        _msg(1, Role.system, Channel.system_note, "The user uploaded an attachment"),
        _msg(1, Role.assistant, Channel.final, "Agent could not start: MCP failed"),
    ]

    statement = await _save(messages)

    # The compiled INSERT must carry exactly one row per rank (0 and 1), and the
    # rank=1 row that survives is the last-written one (the assistant fallback).
    compiled = statement.compile()
    rank_params = sorted(
        v for k, v in compiled.params.items() if k == "rank" or k.startswith("rank_")
    )
    assert rank_params == [0, 1]

    role_params = [
        v for k, v in compiled.params.items() if k == "role" or k.startswith("role_")
    ]
    assert "assistant" in role_params
    # The overwritten system_note role must be gone from the batch.
    assert "system" not in role_params


@pytest.mark.asyncio
async def test_distinct_ranks_are_all_preserved():
    messages = [
        _msg(0, Role.user, Channel.final, "hi"),
        _msg(1, Role.system, Channel.system_note, "note"),
        _msg(2, Role.assistant, Channel.final, "answer"),
    ]

    statement = await _save(messages)

    compiled = statement.compile()
    rank_params = sorted(
        v for k, v in compiled.params.items() if k == "rank" or k.startswith("rank_")
    )
    assert rank_params == [0, 1, 2]
