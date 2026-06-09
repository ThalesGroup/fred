from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fred_core.models import Base as CoreBase
from fred_core.tasks.models import (
    IngestionTaskEvent,
    TaskState,
    TaskTarget,
)
from fred_core.tasks.store import TaskNotFoundError, TaskStore
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

_NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    import fred_core.tasks.orm_models  # noqa: F401 — registers ORM models with CoreBase

    db_path = tmp_path / name
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_task_store_create_and_get_run(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_create.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(task_id="t1", kind="ingestion", created_by="user-1")
        row = await store.get_run("t1")
        assert row is not None
        assert row.task_id == "t1"
        assert row.kind == "ingestion"
        assert row.state == TaskState.pending
        assert row.seq == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_get_run_returns_none_for_missing(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_missing.sqlite3")
    try:
        store = TaskStore(engine)
        assert await store.get_run("no-such-id") is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_record_event_updates_run_and_appends_log(
    tmp_path: Path,
) -> None:
    engine = await _make_engine(tmp_path, "store_record.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(task_id="t2", kind="ingestion", created_by=None)

        # seq is a placeholder — store auto-assigns monotonically from run.seq
        event = IngestionTaskEvent(
            task_id="t2",
            state=TaskState.running,
            seq=0,
            timestamp=_NOW,
            progress=0.3,
            step="copy_tables",
        )
        assigned = await store.record_event(event)
        assert assigned == 1

        row = await store.get_run("t2")
        assert row is not None
        assert row.state == TaskState.running
        assert row.seq == 1
        assert row.progress == pytest.approx(0.3)
        assert row.step == "copy_tables"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_record_event_raises_for_unknown_task(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_unknown.sqlite3")
    try:
        store = TaskStore(engine)
        event = IngestionTaskEvent(
            task_id="ghost", state=TaskState.running, seq=1, timestamp=_NOW
        )
        with pytest.raises(TaskNotFoundError):
            await store.record_event(event)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_replay_events_returns_ordered_subset(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_replay.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(task_id="t3", kind="ingestion", created_by=None)

        # All events carry seq=0 (placeholder); store assigns 1, 2, 3 monotonically.
        for state in [TaskState.running, TaskState.running, TaskState.succeeded]:
            await store.record_event(
                IngestionTaskEvent(task_id="t3", state=state, seq=0, timestamp=_NOW)
            )

        # Replay from seq=1 (i.e. events with seq > 1)
        events = await store.replay_events("t3", after_seq=1)
        assert len(events) == 2
        assert events[0].seq == 2
        assert events[1].seq == 3

        # Full replay (seq > -1)
        all_events = await store.replay_events("t3", after_seq=-1)
        assert len(all_events) == 3
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_list_tasks_filters_by_team_and_state(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_list.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(
            task_id="a1", kind="ingestion", created_by="u1", team_id="team-x"
        )
        await store.create(
            task_id="a2", kind="migration", created_by="u2", team_id="team-x"
        )
        await store.create(
            task_id="a3", kind="ingestion", created_by="u3", team_id="team-y"
        )
        await store.create(task_id="a4", kind="ingestion", created_by="u4")

        all_tasks = await store.list_tasks()
        assert len(all_tasks) == 4

        team_x = await store.list_tasks(team_id="team-x")
        assert len(team_x) == 2
        assert all(t.team_id == "team-x" for t in team_x)

        ingestions = await store.list_tasks(kind="ingestion")
        assert len(ingestions) == 3

        pending = await store.list_tasks(state="pending")
        assert len(pending) == 4

        team_x_ingestions = await store.list_tasks(team_id="team-x", kind="ingestion")
        assert len(team_x_ingestions) == 1
        assert team_x_ingestions[0].task_id == "a1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_replay_preserves_target_and_owner(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "store_target.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(task_id="t4", kind="ingestion", created_by="user-42")

        event = IngestionTaskEvent(
            task_id="t4",
            state=TaskState.running,
            seq=0,
            timestamp=_NOW,
            target=TaskTarget(type="document", id="doc-abc", label="report.pdf"),
            owner="user-42",
        )
        await store.record_event(event)

        replayed = await store.replay_events("t4", after_seq=-1)
        assert len(replayed) == 1
        assert replayed[0].target is not None
        assert replayed[0].target.type == "document"
        assert replayed[0].target.id == "doc-abc"
        assert replayed[0].target.label == "report.pdf"
        assert replayed[0].owner == "user-42"
    finally:
        await engine.dispose()
