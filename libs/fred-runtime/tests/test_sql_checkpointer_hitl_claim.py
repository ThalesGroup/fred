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
Offline tests for the HITL resume claim (`checkpoint_hitl_claim`, #2216).

Why this file exists:
- the claim is the durable, cross-replica arbiter that stops two concurrent
  duplicate resume requests for the same pending interrupt from both
  invoking the graph — its claimed -> started -> consumed lifecycle,
  claim_token fencing, and TTL-vs-no-TTL behavior per state need direct,
  fast coverage independent of the full HTTP app.
- the claim table was deliberately kept separate from
  `langgraph_checkpoint_write` (that table is LangGraph-owned semantic
  storage, read back as `pending_writes`); a claim row must never surface
  there or corrupt checkpoint administration counts.

All tests are offline — a temporary SQLite database, no external services.
Postgres uses the identical `pg_insert(...).on_conflict_do_update(...)`
branch already proven in production by `aput_writes`/`AsyncBaseSqlStore.upsert`
(both of these ALSO use a plain, unconditional upsert though — this claim's
`WHERE` + `RETURNING` combination is new and is exercised only against
SQLite by this offline suite, not independently proven against Postgres).
"""

from __future__ import annotations

import asyncio

import pytest
from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_runtime.runtime_support.checkpoints import checkpoint_config, load_checkpoint
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture
def engine(tmp_path):
    """A throwaway file-backed async SQLite engine (shared across connections)."""
    db = tmp_path / "checkpointer.sqlite3"
    eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
    yield eng


@pytest.fixture
def checkpointer(engine) -> FredSqlCheckpointer:
    return FredSqlCheckpointer(engine, prefix="v2_")


async def _claim_rows(cp: FredSqlCheckpointer) -> list:
    async with cp.store.begin() as conn:
        return list((await conn.execute(select(cp.hitl_claim_table))).fetchall())


async def _claim_and_start(cp: FredSqlCheckpointer, **kwargs) -> str:
    """Convenience: acquire + confirm-start in one call, returning the token."""
    token = await cp.aclaim_hitl_resume(**kwargs)
    assert token is not None
    started = await cp.astart_hitl_resume(claim_token=token, **kwargs)
    assert started is True
    return token


@pytest.mark.asyncio
async def test_aclaim_hitl_resume_first_call_wins(checkpointer) -> None:
    token = await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )
    assert isinstance(token, str) and token
    rows = await _claim_rows(checkpointer)
    assert len(rows) == 1
    assert rows[0].thread_id == "t1"
    assert rows[0].interrupt_id == "interrupt-a"
    assert rows[0].claim_token == token
    assert rows[0].status == "claimed"


@pytest.mark.asyncio
async def test_aclaim_hitl_resume_second_call_for_same_occurrence_loses(
    checkpointer,
) -> None:
    first = await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )
    second = await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )
    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_aclaim_hitl_resume_different_interrupt_ids_are_independent(
    checkpointer,
) -> None:
    a = await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )
    b = await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-b"
    )
    assert a is not None
    assert b is not None
    assert a != b


@pytest.mark.asyncio
async def test_concurrent_claims_for_the_same_occurrence_have_exactly_one_winner(
    checkpointer,
) -> None:
    """
    Real concurrency, not a sequential simulation: N coroutines race the same
    atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE <stale>` via
    `asyncio.gather`. No sleeps — the database's own atomicity is what's
    under test, not timing.
    """

    # Pre-create the tables outside the race: `_ensure_tables()` is
    # idempotent and safe under concurrent callers (advisory-locked DDL),
    # but this test wants to race the CLAIM itself, not first-boot table
    # creation.
    await checkpointer._ensure_tables()

    results = await asyncio.gather(
        *[
            checkpointer.aclaim_hitl_resume(
                thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-race"
            )
            for _ in range(5)
        ]
    )
    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 4


@pytest.mark.asyncio
async def test_concurrent_claims_across_separate_checkpointer_instances_have_one_winner(
    tmp_path,
) -> None:
    """
    Cross-replica proof: `aclaim_hitl_resume` is atomic across TWO
    INDEPENDENT `FredSqlCheckpointer` objects, each built on its OWN
    `AsyncEngine` (its own connection pool) connected to the SAME
    file-backed SQLite database — the actual property fred-agents running
    multiple replicas needs, since each replica opens its own engine/pool
    against the same database. A single shared `AsyncEngine` would NOT
    prove this: SQLAlchemy's `AsyncEngine` owns the connection pool, so two
    `FredSqlCheckpointer` objects built on one shared engine share that
    pool too — this test previously made exactly that mistake (two
    checkpointers, one engine) and mislabeled it as "separate pools".

    Deliberately not a full `create_agent_app`-level test: fred-runtime's
    `get_runtime_context()`/`set_runtime_context()` is a single process-wide
    global (`runtime_context.py`), so two live `create_agent_app` instances
    cannot safely coexist within one Python process — the second one's
    startup overwrites the first's context. True multi-process replica
    testing would require spawning separate OS processes, which is
    disproportionate for this offline suite. This test instead proves the
    property at the layer that actually matters: the database-level atomic
    claim, exercised through genuinely independent engines/pools — the same
    distinction two real fred-agents pods would have. PostgreSQL is not
    exercised here (SQLite only, like every other checkpointer test in this
    file) — see `test_hitl_claim_insert_compiles_the_expected_postgresql_statement`
    for the offline dialect-compilation check that stands in for a real
    PostgreSQL concurrency proof, which this suite does not attempt.
    """

    db = tmp_path / "checkpointer.sqlite3"
    engine_a = create_async_engine(f"sqlite+aiosqlite:///{db}")
    engine_b = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        cp_a = FredSqlCheckpointer(engine_a, prefix="v2_")
        cp_b = FredSqlCheckpointer(engine_b, prefix="v2_")
        await cp_a._ensure_tables()

        kwargs = {
            "thread_id": "t1",
            "checkpoint_ns": "",
            "interrupt_id": "interrupt-a",
        }
        results = await asyncio.gather(
            *[
                (cp_a if i % 2 == 0 else cp_b).aclaim_hitl_resume(**kwargs)
                for i in range(6)
            ]
        )

        winners = [r for r in results if r is not None]
        assert len(winners) == 1
    finally:
        await engine_a.dispose()
        await engine_b.dispose()


def test_hitl_claim_insert_compiles_the_expected_postgresql_statement() -> None:
    """
    Offline dialect-compilation check (#2216 item 5) — proves the exact
    conditional `ON CONFLICT ... WHERE ... RETURNING` statement
    `aclaim_hitl_resume` builds is valid, well-formed PostgreSQL SQL when
    compiled for that dialect. This is NOT a substitute for a real
    PostgreSQL concurrency integration test (none exists in this offline
    suite — see the cross-instance test above for the SQLite-only proof of
    atomicity); it only proves the statement shape itself compiles for
    Postgres, catching a syntax-level regression (e.g. a construct valid
    for SQLite but not Postgres) without a live database.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy.dialects import postgresql

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    cp = FredSqlCheckpointer(engine, prefix="v2_")

    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(seconds=cp._hitl_claim_ttl_seconds)

    # Mirrors the exact statement `aclaim_hitl_resume` builds — kept as a
    # literal reconstruction (not a shared helper) so this stays a pure
    # compile-only check with no dependency on a live connection.
    stmt = cp._hitl_claim_insert("postgresql").values(
        thread_id="t1",
        checkpoint_ns="",
        interrupt_id="interrupt-a",
        claim_token="tok",
        status=cp._HITL_CLAIM_CLAIMED,
        claimed_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["thread_id", "checkpoint_ns", "interrupt_id"],
        set_={
            "claim_token": "tok",
            "status": cp._HITL_CLAIM_CLAIMED,
            "claimed_at": now,
        },
        where=(
            (cp.hitl_claim_table.c.status == cp._HITL_CLAIM_CLAIMED)
            & (cp.hitl_claim_table.c.claimed_at < stale_cutoff)
        ),
    ).returning(cp.hitl_claim_table.c.claim_token)

    compiled = str(stmt.compile(dialect=postgresql.dialect()))

    assert "INSERT INTO" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO UPDATE SET" in compiled
    assert "WHERE" in compiled
    assert "RETURNING" in compiled


@pytest.mark.asyncio
async def test_astart_hitl_resume_requires_the_matching_token(checkpointer) -> None:
    token = await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )
    assert token is not None

    wrong_token_result = await checkpointer.astart_hitl_resume(
        thread_id="t1",
        checkpoint_ns="",
        interrupt_id="interrupt-a",
        claim_token="not-the-real-token",
    )
    assert wrong_token_result is False

    right_token_result = await checkpointer.astart_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a", claim_token=token
    )
    assert right_token_result is True


@pytest.mark.asyncio
async def test_a_started_claim_is_never_superseded_regardless_of_age(engine) -> None:
    """
    A living long-running request must not be stolen merely because
    wall-clock time passed: once 'started', a claim is immune to the TTL
    entirely — proven here with a near-zero TTL, which would supersede a
    merely-'claimed' row instantly but must never touch a 'started' one.
    """

    cp = FredSqlCheckpointer(engine, prefix="v2_", hitl_claim_ttl_seconds=0.001)
    kwargs = {"thread_id": "t1", "checkpoint_ns": "", "interrupt_id": "interrupt-a"}
    token = await _claim_and_start(cp, **kwargs)

    await asyncio.sleep(0.05)  # comfortably past the 0.001s TTL

    stolen = await cp.aclaim_hitl_resume(**kwargs)
    assert stolen is None  # 'started' rows are never eligible, however stale

    # The original owner can still consume its own claim afterwards.
    await cp.aconsume_hitl_resume(claim_token=token, **kwargs)
    rows = await _claim_rows(cp)
    assert rows[0].status == "consumed"
    assert rows[0].claim_token == token


@pytest.mark.asyncio
async def test_stale_claimed_row_is_superseded_after_ttl_expiry(engine) -> None:
    """
    Crash-recovery proof: a claim whose winning process died before it
    could call `astart_hitl_resume` (or release it) must not strand the
    HITL dialog forever — only until the lease expires. This is a
    genuinely time-based feature, so a short configured TTL plus a real
    sleep past it is the correct way to test it deterministically (not a
    race-condition sleep).
    """

    cp = FredSqlCheckpointer(engine, prefix="v2_", hitl_claim_ttl_seconds=0.05)
    kwargs = {"thread_id": "t1", "checkpoint_ns": "", "interrupt_id": "interrupt-a"}
    first = await cp.aclaim_hitl_resume(**kwargs)
    assert first is not None

    # Still fresh: a second attempt loses.
    assert await cp.aclaim_hitl_resume(**kwargs) is None

    await asyncio.sleep(0.1)  # cross the 0.05s lease boundary deterministically

    # Now stale — recovers the dialog with a FRESH token instead of leaving
    # it stuck forever.
    second = await cp.aclaim_hitl_resume(**kwargs)
    assert second is not None
    assert second != first


@pytest.mark.asyncio
async def test_stale_owners_late_start_and_release_cannot_affect_the_new_owner(
    engine,
) -> None:
    """
    A expires; B acquires; A's late start/release attempts (fenced by A's
    now-superseded token) must be no-ops against B's live claim — proving
    "a stale owner must never delete, renew, consume, or act on a newer
    owner's claim".
    """

    cp = FredSqlCheckpointer(engine, prefix="v2_", hitl_claim_ttl_seconds=0.02)
    kwargs = {"thread_id": "t1", "checkpoint_ns": "", "interrupt_id": "interrupt-a"}
    token_a = await cp.aclaim_hitl_resume(**kwargs)
    assert token_a is not None

    await asyncio.sleep(0.05)  # A goes stale

    token_b = await cp.aclaim_hitl_resume(**kwargs)
    assert token_b is not None
    assert token_b != token_a
    started_b = await cp.astart_hitl_resume(claim_token=token_b, **kwargs)
    assert started_b is True

    # A, unaware it lost ownership, tries to start and release using its
    # OLD token — both must be no-ops against B's live 'started' row.
    a_start = await cp.astart_hitl_resume(claim_token=token_a, **kwargs)
    assert a_start is False
    await cp.arelease_hitl_resume(claim_token=token_a, **kwargs)

    rows = await _claim_rows(cp)
    assert len(rows) == 1
    assert rows[0].claim_token == token_b
    assert rows[0].status == "started"


@pytest.mark.asyncio
async def test_arelease_hitl_resume_allows_a_fresh_claim(checkpointer) -> None:
    token = await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )
    assert token is not None
    await checkpointer.arelease_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a", claim_token=token
    )

    reclaimed = await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )
    assert reclaimed is not None


@pytest.mark.asyncio
async def test_arelease_hitl_resume_never_releases_a_started_row(checkpointer) -> None:
    kwargs = {"thread_id": "t1", "checkpoint_ns": "", "interrupt_id": "interrupt-a"}
    token = await _claim_and_start(checkpointer, **kwargs)

    await checkpointer.arelease_hitl_resume(claim_token=token, **kwargs)

    rows = await _claim_rows(checkpointer)
    assert len(rows) == 1  # not deleted
    assert rows[0].status == "started"


@pytest.mark.asyncio
async def test_arelease_hitl_resume_is_a_silent_noop_for_an_unknown_claim(
    checkpointer,
) -> None:
    # Nothing to release (setup failed before any claim existed, or another
    # request already released/superseded it) — must never raise.
    await checkpointer.arelease_hitl_resume(
        thread_id="t1",
        checkpoint_ns="",
        interrupt_id="never-claimed",
        claim_token="whatever",
    )


@pytest.mark.asyncio
async def test_aconsume_hitl_resume_marks_terminal_state(checkpointer) -> None:
    kwargs = {"thread_id": "t1", "checkpoint_ns": "", "interrupt_id": "interrupt-a"}
    token = await _claim_and_start(checkpointer, **kwargs)

    await checkpointer.aconsume_hitl_resume(claim_token=token, **kwargs)

    rows = await _claim_rows(checkpointer)
    assert rows[0].status == "consumed"

    # A consumed occurrence must never be re-claimable — it is permanent,
    # not merely stale.
    reclaimed = await checkpointer.aclaim_hitl_resume(**kwargs)
    assert reclaimed is None


@pytest.mark.asyncio
async def test_aconsume_hitl_resume_is_a_silent_noop_for_the_wrong_token(
    checkpointer,
) -> None:
    kwargs = {"thread_id": "t1", "checkpoint_ns": "", "interrupt_id": "interrupt-a"}
    await _claim_and_start(checkpointer, **kwargs)

    await checkpointer.aconsume_hitl_resume(claim_token="wrong-token", **kwargs)

    rows = await _claim_rows(checkpointer)
    assert rows[0].status == "started"  # unchanged


@pytest.mark.asyncio
async def test_adelete_thread_removes_hitl_claims(checkpointer) -> None:
    await checkpointer.aput(
        checkpoint_config(thread_id="t1"), empty_checkpoint(), {}, {}
    )
    await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )

    await checkpointer.adelete_thread("t1")

    assert await _claim_rows(checkpointer) == []


@pytest.mark.asyncio
async def test_aclaim_and_astart_hitl_resume_emit_honestly_timed_metrics(
    engine,
) -> None:
    """
    #2216 item 6 — `aclaim_hitl_resume`/`astart_hitl_resume` must emit
    `persist_pool_wait_ms`/`persist_sql_ms` measuring what their names say:
    pool-wait is the time to acquire a connection (BEFORE
    `self.store.begin()` is entered, matching `aput`/`aput_writes`'s own
    convention), and the SQL timer includes the `_db_now` round trip that
    `aclaim_hitl_resume` does inside the same transaction as its insert —
    not just the insert alone.
    """
    emitted: list[dict] = []

    class _RecordingKPIWriter(NoOpKPIWriter):
        def emit(self, **kwargs) -> None:
            emitted.append(kwargs)

    cp = FredSqlCheckpointer(engine, prefix="v2_", kpi=_RecordingKPIWriter())
    kwargs = {"thread_id": "t1", "checkpoint_ns": "", "interrupt_id": "interrupt-a"}

    token = await cp.aclaim_hitl_resume(**kwargs)
    assert token is not None
    started = await cp.astart_hitl_resume(claim_token=token, **kwargs)
    assert started is True

    claim_events = [
        e for e in emitted if e["dims"] == {"store": "checkpoint", "op": "hitl_claim"}
    ]
    start_events = [
        e
        for e in emitted
        if e["dims"] == {"store": "checkpoint", "op": "hitl_claim_start"}
    ]
    assert {e["name"] for e in claim_events} == {
        "persist_sql_ms",
        "persist_pool_wait_ms",
    }
    assert {e["name"] for e in start_events} == {
        "persist_sql_ms",
        "persist_pool_wait_ms",
    }
    for event in claim_events + start_events:
        assert event["value"] >= 0.0

    # aconsume_hitl_resume/arelease_hitl_resume are best-effort side
    # operations (same un-instrumented convention as adelete_thread/aget_tuple)
    # — they must not silently start claiming KPI coverage they don't have.
    await cp.aconsume_hitl_resume(claim_token=token, **kwargs)
    assert not any(
        e["dims"].get("op") in ("hitl_claim_consume", "hitl_claim_release")
        for e in emitted
    )


@pytest.mark.asyncio
async def test_hitl_claim_rows_never_appear_in_pending_writes(checkpointer) -> None:
    """
    Regression guard for the design constraint that ruled out
    `langgraph_checkpoint_write` as the claim's home: a claim row must never
    be mistaken by `load_checkpoint` (or LangGraph's own pending-write
    reads) for a real pending write, and checkpoint administration counts
    (`pending_write_count`, computed from `writes_table` alone) must stay
    truthful.
    """

    stored_config = await checkpointer.aput(
        checkpoint_config(thread_id="t1"),
        empty_checkpoint(),
        {"source": "update", "step": 0, "parents": {}},
        {},
    )
    await checkpointer.aput_writes(
        stored_config,
        [("__interrupt__", {"value": {"question": "proceed?"}, "id": "interrupt-a"})],
        task_id="task-1",
    )
    await checkpointer.aclaim_hitl_resume(
        thread_id="t1", checkpoint_ns="", interrupt_id="interrupt-a"
    )

    loaded = await load_checkpoint(checkpointer, thread_id="t1")
    assert loaded is not None
    _checkpoint, pending_writes = loaded
    channels = {channel for _task_id, channel, _value in pending_writes}
    assert channels == {"__interrupt__"}  # the claim row is NOT among them
