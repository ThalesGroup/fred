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
"""
Offline tests for HistoryCaptureReader.

Verify the capture contract from EVAL-DATASET Phase 2:
- transversal filter by team + agent + period (all users), roles user/assistant
- keyset cursor pagination (no gap, no duplicate, ordered)
- period cap is enforced
- content is projected from text parts

All offline — a temporary SQLite file backs the store.
"""

from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from fred_core.history.capture_reader import (
    MAX_PERIOD_DAYS,
    HistoryCaptureReader,
)
from fred_core.history.history_schema import (
    Channel,
    ChatMessage,
    Role,
    TextPart,
)
from fred_core.history.postgres_history_store import PostgresHistoryStore

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _msg(
    session_id: str, rank: int, role: Role, text: str, ts: datetime
) -> ChatMessage:
    return ChatMessage(
        session_id=session_id,
        rank=rank,
        timestamp=ts,
        role=role,
        channel=Channel.final,
        exchange_id=f"ex-{session_id}-{rank}",
        parts=[TextPart(text=text)],
    )


async def _make_store(path: Path) -> tuple[PostgresHistoryStore, AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    store = PostgresHistoryStore(engine)
    # Seed: agent "rico" in team "fredlab", two users, two sessions.
    await store.save(
        "s1",
        [
            _msg("s1", 0, Role.user, "q1", _T0),
            _msg("s1", 1, Role.assistant, "a1", _T0 + timedelta(seconds=1)),
        ],
        user_id="alice",
        team_id="fredlab",
        agent_instance_id="rico",
    )
    await store.save(
        "s2",
        [
            _msg("s2", 0, Role.user, "q2", _T0 + timedelta(hours=1)),
            _msg("s2", 1, Role.assistant, "a2", _T0 + timedelta(hours=1, seconds=1)),
        ],
        user_id="bob",
        team_id="fredlab",
        agent_instance_id="rico",
    )
    # Noise: other team and other agent must NOT be captured.
    await store.save(
        "s3",
        [_msg("s3", 0, Role.user, "other-team", _T0)],
        user_id="carol",
        team_id="other-team",
        agent_instance_id="rico",
    )
    await store.save(
        "s4",
        [_msg("s4", 0, Role.user, "other-agent", _T0)],
        user_id="alice",
        team_id="fredlab",
        agent_instance_id="other-agent",
    )
    return store, engine


def test_captures_all_users_of_team_and_agent_only():
    async def run():
        with tempfile.TemporaryDirectory() as d:
            _, engine = await _make_store(Path(d) / "h.db")
            reader = HistoryCaptureReader(engine)
            page = await reader.fetch_page(
                team_id="fredlab",
                agent_instance_id="rico",
                period_from=_T0 - timedelta(days=1),
                period_to=_T0 + timedelta(days=1),
            )
            contents = {m.content for m in page.messages}
            users = {m.user_id for m in page.messages}
            assert contents == {"q1", "a1", "q2", "a2"}  # only fredlab/rico
            assert users == {"alice", "bob"}  # all users, no filter
            assert page.next_cursor is None

    asyncio.run(run())


def test_cursor_pagination_no_gap_no_duplicate():
    async def run():
        with tempfile.TemporaryDirectory() as d:
            _, engine = await _make_store(Path(d) / "h.db")
            reader = HistoryCaptureReader(engine)
            seen: list[str] = []
            cursor = None
            for _ in range(10):  # safety bound
                page = await reader.fetch_page(
                    team_id="fredlab",
                    agent_instance_id="rico",
                    period_from=_T0 - timedelta(days=1),
                    period_to=_T0 + timedelta(days=1),
                    cursor=cursor,
                    limit=2,
                )
                seen.extend(m.content for m in page.messages)
                cursor = page.next_cursor
                if cursor is None:
                    break
            assert seen == ["q1", "a1", "q2", "a2"]  # ordered, complete, unique

    asyncio.run(run())


def test_period_cap_is_enforced():
    async def run():
        with tempfile.TemporaryDirectory() as d:
            _, engine = await _make_store(Path(d) / "h.db")
            reader = HistoryCaptureReader(engine)
            with pytest.raises(ValueError):
                await reader.fetch_page(
                    team_id="fredlab",
                    agent_instance_id="rico",
                    period_from=_T0,
                    period_to=_T0 + timedelta(days=MAX_PERIOD_DAYS + 1),
                )

    asyncio.run(run())


def test_period_filters_out_of_window():
    async def run():
        with tempfile.TemporaryDirectory() as d:
            _, engine = await _make_store(Path(d) / "h.db")
            reader = HistoryCaptureReader(engine)
            # Window before any message → empty.
            page = await reader.fetch_page(
                team_id="fredlab",
                agent_instance_id="rico",
                period_from=_T0 - timedelta(days=10),
                period_to=_T0 - timedelta(days=5),
            )
            assert page.messages == []
            assert page.next_cursor is None

    asyncio.run(run())
