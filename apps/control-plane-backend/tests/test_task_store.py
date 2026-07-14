from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fred_core.models import Base as CoreBase
from fred_core.tasks.models import (
    ErasureDetail,
    IngestionDetail,
    IngestionTaskEvent,
    MigrationDetail,
    MigrationResult,
    MigrationTaskEvent,
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


@pytest.mark.asyncio
async def test_task_store_list_tasks_projects_typed_migration_detail_with_result(
    tmp_path: Path,
) -> None:
    """AUTHZ-07 Step 3: GET /tasks (TaskStore.list_tasks) must not lose the last
    persisted detail — including the nested structured `MigrationResult` — so a
    partial reconciliation is never indistinguishable from full success after a
    reload."""
    engine = await _make_engine(tmp_path, "store_migration_detail.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(
            task_id="m1",
            kind="migration",
            created_by="admin-1",
            target=TaskTarget(type="platform_import", id="imp-1", label="demo.zip"),
        )
        await store.record_event(
            MigrationTaskEvent(
                task_id="m1",
                state=TaskState.succeeded,
                seq=0,
                timestamp=_NOW,
                progress=1.0,
                detail=MigrationDetail(
                    step_id="done",
                    processed=1,
                    total=1,
                    failed=0,
                    result=MigrationResult(
                        import_id="imp-1",
                        source_platform="swift",
                        agents_imported=3,
                        warnings=["agent x: gap"],
                    ),
                ),
            )
        )

        tasks = await store.list_tasks(kind="migration")
        assert len(tasks) == 1
        detail = tasks[0].detail
        assert isinstance(detail, MigrationDetail)
        assert detail.step_id == "done"
        assert detail.result is not None
        assert detail.result.import_id == "imp-1"
        assert detail.result.agents_imported == 3
        assert detail.result.warnings == ["agent x: gap"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_list_tasks_detail_is_none_for_legacy_task(
    tmp_path: Path,
) -> None:
    """A task that never had an event with `detail` (or was created before this
    field existed) must still list cleanly — `detail=None`, no crash — proving
    the addition is backward compatible (AUTHZ-07 Step 3)."""
    engine = await _make_engine(tmp_path, "store_legacy_detail.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(task_id="legacy1", kind="ingestion", created_by="u1")
        await store.record_event(
            IngestionTaskEvent(
                task_id="legacy1", state=TaskState.running, seq=0, timestamp=_NOW
            )
        )

        tasks = await store.list_tasks(kind="ingestion")
        assert len(tasks) == 1
        assert tasks[0].detail is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_task_store_list_tasks_projects_other_kinds_without_regression(
    tmp_path: Path,
) -> None:
    """Non-migration TaskSummary variants keep parsing their own detail shape
    correctly after the union field was added (AUTHZ-07 Step 3)."""
    engine = await _make_engine(tmp_path, "store_other_kinds_detail.sqlite3")
    try:
        store = TaskStore(engine)
        await store.create(task_id="i1", kind="ingestion", created_by="u1")
        await store.record_event(
            IngestionTaskEvent(
                task_id="i1",
                state=TaskState.running,
                seq=0,
                timestamp=_NOW,
                detail=IngestionDetail(
                    processed=2,
                    total=5,
                    failed=0,
                    preview=2,
                    vectorized=1,
                    sql_indexed=0,
                ),
            )
        )

        tasks = await store.list_tasks(kind="ingestion")
        assert len(tasks) == 1
        detail = tasks[0].detail
        assert isinstance(detail, IngestionDetail)
        assert detail.processed == 2
        assert detail.total == 5
    finally:
        await engine.dispose()


def test_erasure_detail_still_parses_via_generic_projection() -> None:
    """`ErasureDetail`'s all-defaulted fields must still round-trip through the
    same kind→model mapping `_parse_task_detail` uses (AUTHZ-07 Step 3) — a
    sanity check independent of the DB round-trip above."""
    from fred_core.tasks.store import _parse_task_detail

    parsed = _parse_task_detail(
        "erasure",
        {"reason": "user_deleted", "stores_ok": 2, "stores_total": 2, "attempts": 1},
    )
    assert isinstance(parsed, ErasureDetail)
    assert parsed.stores_ok == 2
