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
Offline tests for the ``checkpoint_thread_owner`` index (CTRLP-12 A4).

Why this file exists:
- every ``aput`` must write exactly one owner row per thread (upsert, not
  duplicate) and its owner write must be best-effort — a forced failure must
  NEVER raise out of ``aput`` (it cannot fail a user's turn);
- the one-shot backfill must produce one owner row per DISTINCT thread in
  ``session_history``;
- the per-user purge must delete exactly that user's threads and no others.

All tests are offline — a temporary SQLite database, no external services.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import create_async_engine

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def engine(tmp_path):
    """A throwaway file-backed async SQLite engine (shared across connections)."""
    db = tmp_path / "checkpointer.sqlite3"
    eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
    yield eng


@pytest.fixture
def checkpointer(engine) -> FredSqlCheckpointer:
    return FredSqlCheckpointer(engine, prefix="v2_")


def _config(thread_id: str, **configurable) -> RunnableConfig:
    return {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": "",
            **configurable,
        }
    }


async def _put(cp: FredSqlCheckpointer, thread_id: str, **configurable) -> None:
    """Persist one empty checkpoint for a thread (mirrors a real turn's aput)."""
    checkpoint = empty_checkpoint()
    await cp.aput(_config(thread_id, **configurable), checkpoint, {}, {})


async def _owner_rows(cp: FredSqlCheckpointer) -> list:
    async with cp.store.begin() as conn:
        return list((await conn.execute(select(cp.thread_owner_table))).fetchall())


async def _seed_history(engine, rows: list[dict]) -> None:
    """Create a minimal ``session_history`` table and insert the given rows."""
    md = MetaData()
    history = Table(
        "session_history",
        md,
        Column("session_id", String, primary_key=True),
        Column("user_id", String, primary_key=True),
        Column("rank", Integer, primary_key=True),
        Column("team_id", String, nullable=True),
        Column("timestamp", DateTime(timezone=True), nullable=False),
    )
    async with engine.begin() as conn:
        await conn.run_sync(md.create_all)
        await conn.execute(insert(history), rows)


@pytest.mark.asyncio
async def test_aput_writes_exactly_one_owner_row_upsert(checkpointer):
    # Two turns on the same thread → still exactly one owner row (upsert).
    await _put(checkpointer, "thread-A")
    await _put(checkpointer, "thread-A")

    rows = await _owner_rows(checkpointer)
    assert len(rows) == 1
    row = rows[0]
    assert row.thread_id == "thread-A"
    assert row.user_id is None  # nothing injects identity at aput time yet
    assert row.last_activity_at is not None
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_aput_records_injected_identity(checkpointer):
    # If a caller injects __fred_user_id/__fred_team_id, aput records them.
    await _put(
        checkpointer,
        "thread-Z",
        __fred_user_id="alice",
        __fred_team_id="team-1",
    )
    rows = await _owner_rows(checkpointer)
    assert len(rows) == 1
    assert rows[0].user_id == "alice"
    assert rows[0].team_id == "team-1"


@pytest.mark.asyncio
async def test_injected_identity_not_leaked_into_checkpoint_metadata(checkpointer):
    # The __-prefixed identity keys must not land in persisted checkpoint metadata.
    await _put(
        checkpointer,
        "thread-Z",
        __fred_user_id="alice",
        __fred_team_id="team-1",
    )
    tuple_ = await checkpointer.aget_tuple(_config("thread-Z"))
    assert tuple_ is not None
    assert "__fred_user_id" not in tuple_.metadata
    assert "__fred_team_id" not in tuple_.metadata


@pytest.mark.asyncio
async def test_owner_write_failure_does_not_raise_out_of_aput(checkpointer, caplog):
    # Force the owner write to blow up; aput must still succeed and persist the
    # checkpoint, and no owner row must be written.
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("forced owner-write failure")

    checkpointer._upsert_owner = _boom  # type: ignore[assignment]

    await _put(checkpointer, "thread-B")  # must NOT raise

    # The checkpoint itself is intact...
    assert await checkpointer.aget_tuple(_config("thread-B")) is not None
    # ...and the failure left no owner row (and was logged, not swallowed silently).
    assert await _owner_rows(checkpointer) == []


@pytest.mark.asyncio
async def test_backfill_matches_distinct_threads(checkpointer, engine):
    await _seed_history(
        engine,
        [
            {
                "session_id": "s1",
                "user_id": "u1",
                "rank": 0,
                "team_id": "t1",
                "timestamp": _NOW,
            },
            {
                "session_id": "s1",
                "user_id": "u1",
                "rank": 1,
                "team_id": "t1",
                "timestamp": _NOW + timedelta(minutes=5),
            },
            {
                "session_id": "s2",
                "user_id": "u2",
                "rank": 0,
                "team_id": None,
                "timestamp": _NOW + timedelta(hours=1),
            },
            {
                "session_id": "s3",
                "user_id": "u1",
                "rank": 0,
                "team_id": "t1",
                "timestamp": _NOW + timedelta(hours=2),
            },
        ],
    )

    processed = await checkpointer.backfill_thread_owners_from_history()

    # One owner row per DISTINCT session_id (== thread_id) in history.
    async with engine.begin() as conn:
        distinct = (
            await conn.execute(
                select(
                    func.count(
                        func.distinct(
                            Table(
                                "session_history",
                                MetaData(),
                                Column("session_id", String),
                                keep_existing=True,
                            ).c.session_id
                        )
                    )
                )
            )
        ).scalar_one()
    rows = await _owner_rows(checkpointer)
    assert processed == distinct == 3
    assert {r.thread_id for r in rows} == {"s1", "s2", "s3"}
    owners = {r.thread_id: (r.user_id, r.team_id) for r in rows}
    assert owners["s1"] == ("u1", "t1")
    assert owners["s2"] == ("u2", None)
    assert owners["s3"] == ("u1", "t1")


@pytest.mark.asyncio
async def test_purge_deletes_exactly_that_users_threads(checkpointer, engine):
    # Threads for user u1 (s1, s3) and user u2 (s2), with real checkpoints.
    for thread_id in ("s1", "s2", "s3"):
        await _put(checkpointer, thread_id)
    await _seed_history(
        engine,
        [
            {
                "session_id": "s1",
                "user_id": "u1",
                "rank": 0,
                "team_id": "t1",
                "timestamp": _NOW,
            },
            {
                "session_id": "s2",
                "user_id": "u2",
                "rank": 0,
                "team_id": "t2",
                "timestamp": _NOW,
            },
            {
                "session_id": "s3",
                "user_id": "u1",
                "rank": 0,
                "team_id": "t1",
                "timestamp": _NOW,
            },
        ],
    )
    await checkpointer.backfill_thread_owners_from_history()

    purged = await checkpointer.purge_threads_for_user("u1")

    assert sorted(purged) == ["s1", "s3"]
    # u1's checkpoints and owner rows are gone; u2's survive.
    assert await checkpointer.aget_tuple(_config("s1")) is None
    assert await checkpointer.aget_tuple(_config("s3")) is None
    assert await checkpointer.aget_tuple(_config("s2")) is not None
    remaining = {r.thread_id for r in await _owner_rows(checkpointer)}
    assert remaining == {"s2"}
