# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The same ownership contract on SQLite and an isolated PostgreSQL database."""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_runtime.app.agent_app import _write_turn_history
from fred_runtime.runtime_support.active_turn import (
    ACTIVE_TURN,
    ActiveTurnLost,
    ActiveTurnStore,
)
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture(params=["sqlite", "postgresql"])
async def store(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[ActiveTurnStore]:
    if request.param == "postgresql":
        url = os.environ.get("FRED_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("FRED_TEST_POSTGRES_URL is required")
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'turn.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(ACTIVE_TURN.create, checkfirst=True)
    try:
        yield ActiveTurnStore(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_take_expiry_and_token_fencing(store: ActiveTurnStore) -> None:
    session_id, other_id = str(uuid4()), str(uuid4())
    # Independent engines stand in for separate pods, with no shared lock.
    engine2 = create_async_engine(store.engine.url)
    competitor = ActiveTurnStore(engine2)
    try:
        owners = await asyncio.gather(
            store.take(session_id), competitor.take(session_id)
        )
        assert sum(owner is not None for owner in owners) == 1
        owner = next(owner for owner in owners if owner is not None)
        other = await competitor.take(other_id)
        assert other is not None
        assert await store.renew(session_id, owner.token)
        assert not await store.renew(session_id, "wrong-token")
        await store.release(session_id, "wrong-token")
        assert await competitor.take(session_id) is None
        # Force expiry using the database clock, never a pod timestamp.
        expired = (
            text("clock_timestamp() - INTERVAL '1 second'")
            if store.engine.dialect.name == "postgresql"
            else text("datetime('now', '-1 second')")
        )
        async with store.engine.begin() as conn:
            await conn.execute(
                update(ACTIVE_TURN)
                .where(ACTIVE_TURN.c.session_id == session_id)
                .values(expires_at=expired)
            )
        assert not await store.renew(session_id, owner.token)
        replacement = await competitor.take(session_id)
        assert replacement is not None and replacement.token != owner.token
        await owner.release()
        assert not await store.renew(session_id, owner.token)
        assert await competitor.take(session_id) is None
        await replacement.release()
        await replacement.release()
        await other.release()
        successor = await store.take(session_id)
        assert successor is not None
        await successor.release()
    finally:
        await engine2.dispose()


@pytest.mark.asyncio
async def test_write_guard_rolls_back_and_refuses_stale_owner(
    store: ActiveTurnStore,
) -> None:
    lease = await store.take(str(uuid4()))
    assert lease is not None
    with pytest.raises(ValueError):
        async with lease.writing() as sql:
            await sql.execute(
                delete(ACTIVE_TURN).where(ACTIVE_TURN.c.session_id == lease.session_id)
            )
            raise ValueError("rollback")
    assert await store.take(lease.session_id) is None
    await store.release(lease.session_id, lease.token)
    with pytest.raises(ActiveTurnLost):
        async with lease.writing():
            pytest.fail("A lost owner reached the history transaction")


@pytest.mark.asyncio
async def test_heartbeat_marks_loss_and_release_joins_it(
    store: ActiveTurnStore, monkeypatch
) -> None:
    lease = await store.take(str(uuid4()))
    assert lease is not None
    # Exercise the renewal loop without waiting its production 20-second interval.
    import fred_runtime.runtime_support.active_turn as module

    monkeypatch.setattr(module, "RENEW_INTERVAL_SECONDS", 0.01)
    await store.release(lease.session_id, lease.token)
    lease.start()
    assert lease._heartbeat is not None
    await asyncio.wait_for(lease._heartbeat, timeout=3)
    with pytest.raises(ActiveTurnLost):
        lease.check()
    await lease.release()
    assert lease._heartbeat is None


@pytest.mark.asyncio
async def test_final_history_is_fenced_in_its_transaction(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    from fred_runtime.migrations import upgrade_sqlite_database

    path = tmp_path / "history.sqlite"
    await asyncio.to_thread(upgrade_sqlite_database, path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    store, history = ActiveTurnStore(engine), PostgresHistoryStore(engine)
    lease = await store.take("s1")
    assert lease is not None
    original = history.save

    async def save(**kwargs):
        sql = kwargs["session"]
        assert sql is not None and sql.in_transaction()
        assert await sql.scalar(select(ACTIVE_TURN.c.owner_token)) == lease.token
        await original(**kwargs)

    monkeypatch.setattr(history, "save", save)
    args: dict[str, Any] = dict(
        session_id="s1",
        user_id="u1",
        request_message="question",
        payloads=[{"kind": "final", "content": "answer"}],
        history_store=history,
        active_turn=lease,
        base_rank=0,
    )
    try:
        await _write_turn_history(**args)
        before = await history.get("s1")
        assert len(before) == 2
        await lease.release()
        successor = await store.take("s1")
        assert successor is not None
        args["request_message"] = "stale request"
        with pytest.raises(ActiveTurnLost):
            await _write_turn_history(**args)
        assert await history.get("s1") == before
        assert "reason=active_turn_lost" in caplog.text
        await successor.release()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_migration_cascades_deletion_without_extra_index(
    store: ActiveTurnStore,
) -> None:
    if store.engine.dialect.name != "postgresql":
        pytest.skip("The conversation root is owned by Control Plane on PostgreSQL")
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import Connection

    schema = "lot_g_" + uuid4().hex
    session_id = str(uuid4())
    migration = import_module(
        "fred_runtime.migrations.versions.e1f2a3b4c5d6_session_active_turn"
    )

    def upgrade(conn: Connection) -> None:
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

    async with store.engine.connect() as conn:
        transaction = await conn.begin()
        try:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS control_plane"))
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS control_plane.session_metadata(session_id uuid PRIMARY KEY)"
                )
            )
            await conn.run_sync(upgrade)
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM pg_indexes WHERE schemaname=:schema AND tablename='session_active_turn'"
                    ),
                    {"schema": schema},
                )
                == 1
            )
            await conn.execute(
                text("INSERT INTO control_plane.session_metadata VALUES (:id)"),
                {"id": session_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO session_active_turn VALUES (:id, 'owner', clock_timestamp() + INTERVAL '60 seconds')"
                ),
                {"id": session_id},
            )
            await conn.execute(
                text("DELETE FROM control_plane.session_metadata WHERE session_id=:id"),
                {"id": session_id},
            )
            assert (
                await conn.scalar(text("SELECT count(*) FROM session_active_turn")) == 0
            )
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("first", ["checkpoint", "writes"])
async def test_late_checkpoint_writer_keeps_old_token_after_takeover(
    store: ActiveTurnStore,
    first: str,
) -> None:
    from fred_runtime.runtime_support.run_scope import RunScope
    from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.base import empty_checkpoint

    cp = FredSqlCheckpointer(store.engine, prefix=f"r1_{uuid4().hex[:8]}_")
    async with store.engine.begin() as conn:
        await conn.run_sync(cp._metadata.create_all)
    old = await store.take(str(uuid4()))
    assert old is not None
    config: RunnableConfig = {"configurable": {"thread_id": old.session_id + ":agent"}}
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"value": "original"}
    versions: dict[str, str | int | float] = {"value": "1"}
    checkpoint["channel_versions"] = versions
    resume = asyncio.Event()

    async def late_write():
        await resume.wait()
        # Even a task surviving cancellation inherits the old RunScope/token.
        if first == "checkpoint":
            with pytest.raises(ActiveTurnLost):
                await cp.aput(config, checkpoint, {}, versions)
        else:
            with pytest.raises(ActiveTurnLost):
                await cp.aput_writes(config, [("value", "stale")], "task")

    try:
        with RunScope.open() as scope:
            scope.active_turn = old
            config = await cp.aput(config, checkpoint, {}, versions)
            await cp.aput_writes(config, [("value", "original")], "task")
            late = asyncio.create_task(late_write())
        # Simulate database expiry without telling the old process.
        async with store.engine.begin() as conn:
            expiry = (
                text("clock_timestamp() - INTERVAL '1 second'")
                if store.engine.dialect.name == "postgresql"
                else text("datetime('now', '-1 second')")
            )
            await conn.execute(
                update(ACTIVE_TURN)
                .where(ACTIVE_TURN.c.session_id == old.session_id)
                .values(expires_at=expiry)
            )
        replacement = await store.take(old.session_id)
        assert replacement is not None
        with RunScope.open() as scope:
            scope.active_turn = replacement
            checkpoint["channel_values"] = {"value": "replacement"}
            await cp.aput(config, checkpoint, {}, versions)
            await cp.aput_writes(config, [("value", "replacement")], "task")
        assert not old.lost
        checkpoint["channel_values"] = {"value": "stale"}
        resume.set()
        await asyncio.wait_for(late, 3)
        saved = await cp.aget_tuple(config)
        assert saved is not None
        assert saved.checkpoint["channel_values"] == {"value": "replacement"}
        assert saved.pending_writes == [("task", "value", "replacement")]
        await replacement.release()
    finally:
        await old.release()
        async with store.engine.begin() as conn:
            await conn.run_sync(cp._metadata.drop_all)


@pytest_asyncio.fixture
async def steering_history(store: ActiveTurnStore, monkeypatch):
    from fred_core.history.postgres_history_store import create_history_schema
    from fred_runtime.app.agent_app import turn_messages

    # Reuse the core store's isolated SQL fixture on both dialects.
    await create_history_schema(store.engine)
    history = PostgresHistoryStore(store.engine)
    monkeypatch.setattr(turn_messages, "require_history", lambda: history)
    return history


@pytest.mark.asyncio
@pytest.mark.parametrize("rollback", [False, True])
async def test_steering_delivery_shares_lease_transaction_and_receipt(
    store: ActiveTurnStore,
    steering_history: PostgresHistoryStore,
    monkeypatch,
    rollback: bool,
) -> None:
    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event
    from fred_runtime.runtime_support.run_scope import RunScope

    session_id = str(uuid4())
    lease = await store.take(session_id)
    assert lease is not None
    await steering_history.submit_steered_message(
        session_id=session_id,
        user_id="u",
        space_id="space",
        agent_instance_id="agent",
        message_id="m",
        content="steer",
    )
    before = (await steering_history.get(session_id))[0]
    deliver = steering_history.deliver_steered_message

    async def delivery(**kwargs):
        sql = kwargs["session"]
        assert sql is not None and sql.in_transaction()
        assert (
            await sql.scalar(
                select(ACTIVE_TURN.c.owner_token).where(
                    ACTIVE_TURN.c.session_id == session_id
                )
            )
            == lease.token
        )
        result = await deliver(**kwargs)
        # No inner commit: other readers still see the pending message.
        assert await steering_history.get(session_id) == [before]
        assert not receipt.done()
        if rollback:
            raise RuntimeError("rollback delivery")
        return result

    monkeypatch.setattr(steering_history, "deliver_steered_message", delivery)
    try:
        with RunScope.open() as scope:
            scope.active_turn = lease
            receipt = scope.register_event_receipt("steered-user:m")
            ranker = _HistoryRanker(
                0,
                opening_rank=0,
                pending_message_id=None,
                previously_pending_occurrence_ids=(),
            )
            work = _rank_runtime_event(
                {"kind": "steered_user_message", "message_id": "m", "content": "steer"},
                ranker,
                session_id=session_id,
                user_id="u",
                exchange_id="exchange",
            )
            if rollback:
                with pytest.raises(RuntimeError, match="rollback delivery"):
                    await work
                with pytest.raises(RuntimeError, match="rollback delivery"):
                    await receipt
                assert await steering_history.get(session_id) == [before]
            else:
                result = await work
                assert await receipt == result
                saved = await steering_history.get(session_id)
                assert saved[0].rank == 0 and saved[0].exchange_id == "exchange"
                assert await steering_history.pending_steered_messages(session_id) == []
    finally:
        await lease.release()


@pytest.mark.asyncio
async def test_steering_delivery_waiting_for_sql_refuses_replaced_owner(
    store: ActiveTurnStore, steering_history: PostgresHistoryStore
) -> None:
    from fred_runtime.app.agent_app import _HistoryRanker, _rank_runtime_event
    from fred_runtime.runtime_support.active_turn import ActiveTurn
    from fred_runtime.runtime_support.run_scope import RunScope
    from sqlalchemy import event

    session_id = str(uuid4())
    old = await store.take(session_id)
    assert old is not None
    await steering_history.submit_steered_message(
        session_id=session_id,
        user_id="u",
        space_id="space",
        agent_instance_id="agent",
        message_id="m",
        content="steer",
    )
    before = (await steering_history.get(session_id))[0]
    replacement = ActiveTurn(store, session_id, uuid4().hex)
    waiting = asyncio.Event()

    def observe(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("UPDATE session_active_turn SET expires_at="):
            waiting.set()

    event.listen(store.engine.sync_engine, "before_cursor_execute", observe)

    async def deliver():
        return await _rank_runtime_event(
            {"kind": "steered_user_message", "message_id": "m", "content": "steer"},
            _HistoryRanker(
                0,
                opening_rank=0,
                pending_message_id=None,
                previously_pending_occurrence_ids=(),
            ),
            session_id=session_id,
            user_id="u",
            exchange_id="old-exchange",
        )

    try:
        with RunScope.open() as scope:
            scope.active_turn = old
            receipt = scope.register_event_receipt("steered-user:m")
            async with store.engine.begin() as blocker:
                # Hold the takeover uncommitted: the old writer sees its former
                # token, waits for the SQL lock, then must recheck after commit.
                await blocker.execute(
                    update(ACTIVE_TURN)
                    .where(ACTIVE_TURN.c.session_id == session_id)
                    .values(owner_token=replacement.token)
                )
                task = asyncio.create_task(deliver())
                await asyncio.wait_for(waiting.wait(), 3)
                assert not task.done()
                assert not old.lost
            result = await asyncio.wait_for(task, 3)
            assert result["kind"] == "execution_error"
            assert "expired or was lost" in result["message"]
            with pytest.raises(ActiveTurnLost):
                await receipt
        assert await steering_history.get(session_id) == [before]
        assert (await steering_history.pending_steered_messages(session_id))[
            0
        ] == before
        assert await store.renew(session_id, replacement.token)
    finally:
        event.remove(store.engine.sync_engine, "before_cursor_execute", observe)
        await old.release()
        await replacement.release()
