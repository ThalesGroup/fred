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

"""Knowledge Flow's task tables must live in their own database (OPS-04, issue #2170).

Knowledge Flow shares its main Postgres database with control-plane, and the fred-core
task tables (`task_run` / `task_event_log`) carry no per-service discriminator. Sharing one
database therefore makes each backend's `GET /tasks` return rows created by the other, and
the Activity page — which queries both backends and concatenates the results — renders every
task twice.

These tests pin the wiring that fixes it: `get_task_service()` uses the dedicated task
engine, every other store keeps the shared one, and the two never get silently swapped.
Nothing else in the suite asserts which database a task row lands in.

All configs here use `sqlite_path`, so engines are built for real without a server, a
password, or a socket (the suite runs under --disable-socket).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from fred_core.common import DuckdbStoreConfig, PostgresStoreConfig

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import (
    InMemoryVectorStorage,
    StorageConfig,
)


def _storage(tmp_path, *, with_task_db: bool) -> StorageConfig:
    """Build a storage config with, or without, a dedicated task database.

    Both branches use SQLite files so `create_async_engine_from_config` takes its
    laptop-only path — real engines, no server, no credentials.
    """
    task_postgres = None
    if with_task_db:
        task_postgres = PostgresStoreConfig(sqlite_path=str(tmp_path / "tasks.db"), database="knowledge_flow")
    return StorageConfig(
        postgres=PostgresStoreConfig(sqlite_path=str(tmp_path / "shared.db"), database="fred"),
        task_postgres=task_postgres,
        resource_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "resource.duckdb")),
        tag_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "tag.duckdb")),
        metadata_store=DuckdbStoreConfig(type="duckdb", duckdb_path=str(tmp_path / "metadata.duckdb")),
        vector_store=InMemoryVectorStorage(type="in_memory"),
    )


def _context(storage: StorageConfig) -> ApplicationContext:
    """Return an ApplicationContext bound to `storage` without running __init__.

    `ApplicationContext.__init__` short-circuits when the process-wide singleton already
    exists — and conftest builds one via an autouse fixture before every test here — so
    constructing it normally would silently hand back the fixture's context and its
    storage config, not the one each test needs. Bypassing __init__ is what makes the
    per-test storage config take effect; the accessors under test read only
    `self.configuration` and the cached-engine slots, which are class-level defaults.
    """
    ctx = object.__new__(ApplicationContext)
    ctx.configuration = _MinimalConfig(storage)  # type: ignore[assignment]
    return ctx


class _MinimalConfig:
    """Stand-in for Configuration exposing only what the engine accessors read."""

    def __init__(self, storage: StorageConfig):
        self.storage = storage
        self.scheduler = _MemoryScheduler()


class _MemoryScheduler:
    """Scheduler config resolving to the MEMORY backend — `get_scheduler_backend()`
    short-circuits on `not enabled`, so no Temporal client is ever constructed."""

    enabled = False


def _patch_task_service_build(monkeypatch, captured: dict[str, Any]) -> None:
    """Replace `TaskService.build` with a recorder, so a test can inspect the engine and
    DSN it was handed without standing up a real store, bus or Temporal client."""
    from fred_core.tasks import service as task_service_module

    def _capture(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(task_service_module.TaskService, "build", staticmethod(_capture))


def test_task_engine_is_distinct_from_the_shared_engine_when_configured(tmp_path):
    ctx = _context(_storage(tmp_path, with_task_db=True))

    shared = ctx.get_pg_async_engine()
    tasks = ctx.get_task_pg_async_engine()

    assert tasks is not shared, "task tables must not share the control-plane database"
    assert "tasks.db" in str(tasks.url)
    assert "shared.db" in str(shared.url)


def test_task_engine_is_cached(tmp_path):
    ctx = _context(_storage(tmp_path, with_task_db=True))

    assert ctx.get_task_pg_async_engine() is ctx.get_task_pg_async_engine()


def test_task_engine_falls_back_to_the_shared_engine_and_warns_when_unconfigured(tmp_path, caplog):
    """Absent `task_postgres`, the process must still boot — an image can ship before the
    dedicated database is provisioned. The duplicate-row bug persists until it is, so the
    fallback has to be loud rather than silent."""
    ctx = _context(_storage(tmp_path, with_task_db=False))

    with caplog.at_level(logging.WARNING):
        tasks = ctx.get_task_pg_async_engine()

    assert tasks is ctx.get_pg_async_engine()
    assert any("task_postgres" in record.message for record in caplog.records), "falling back to the shared database must warn — otherwise #2170 silently persists"


def test_task_service_is_built_with_the_task_engine(tmp_path, monkeypatch):
    """The load-bearing assertion: TaskStore writes through the engine handed to
    TaskService.build, so this is what decides which database a task row lands in."""
    ctx = _context(_storage(tmp_path, with_task_db=True))
    captured: dict[str, Any] = {}

    _patch_task_service_build(monkeypatch, captured)

    ctx.get_task_service()

    assert captured["engine"] is ctx.get_task_pg_async_engine()
    assert captured["engine"] is not ctx.get_pg_async_engine()


def test_event_bus_dsn_names_the_task_database(tmp_path, monkeypatch):
    """The SSE bus DSN must name the same database as the engine.

    `PostgresEventBus` uses LISTEN/NOTIFY, and notification channels are per-database.
    A bus pointed at the shared database while rows are written to the task database
    fails silently: events still persist and replay, but live streaming delivers nothing
    and no error is raised anywhere.
    """
    storage = _storage(tmp_path, with_task_db=True)
    # A real Postgres target, so the DSN under test is the one production would build.
    storage.task_postgres = PostgresStoreConfig(
        host="task-host",
        database="knowledge_flow",
        username="kf",
        password="pw",  # nosec B106 # pragma: allowlist secret
    )

    ctx = _context(storage)
    ctx.configuration.scheduler = _TemporalScheduler()  # type: ignore[assignment]
    captured: dict[str, Any] = {}

    _patch_task_service_build(monkeypatch, captured)

    ctx.get_task_service()

    assert "knowledge_flow" in captured["postgres_dsn"]
    assert "task-host" in captured["postgres_dsn"]
    assert "/fred" not in captured["postgres_dsn"]


@pytest.mark.asyncio
async def test_shutdown_disposes_the_shared_engine_once_under_fallback():
    """Under the fallback both slots hold the same engine, so shutdown must dispose it
    once. `dispose()` is idempotent, so a second call would not corrupt anything — it
    would just build a fresh pool and abandon it."""
    ctx = object.__new__(ApplicationContext)
    engine = _RecordingEngine()
    ctx._pg_async_engine = engine  # type: ignore[assignment]
    ctx._task_pg_async_engine = engine  # type: ignore[assignment]

    await ctx.shutdown()

    assert engine.dispose_calls == 1


@pytest.mark.asyncio
async def test_shutdown_disposes_both_engines_when_they_are_distinct():
    ctx = object.__new__(ApplicationContext)
    shared, tasks = _RecordingEngine(), _RecordingEngine()
    ctx._pg_async_engine = shared  # type: ignore[assignment]
    ctx._task_pg_async_engine = tasks  # type: ignore[assignment]

    await ctx.shutdown()

    assert (shared.dispose_calls, tasks.dispose_calls) == (1, 1)


class _RecordingEngine:
    """Minimal stand-in for AsyncEngine — the real class rejects attribute injection."""

    def __init__(self):
        self.dispose_calls = 0

    async def dispose(self):
        self.dispose_calls += 1


class _TemporalScheduler:
    enabled = True
    backend = "temporal"
    temporal = None


# --------------------------------------------------------------------------------------
# Boot-time table placement — the invariant #2170 actually turns on.
# --------------------------------------------------------------------------------------


async def _table_names(engine) -> set[str]:
    """Reflect the table names a real (SQLite) engine sees."""
    from sqlalchemy import inspect as sa_inspect

    async with engine.begin() as conn:
        return set(await conn.run_sync(lambda sync_conn: sa_inspect(sync_conn).get_table_names()))


@pytest.mark.asyncio
async def test_create_core_tables_puts_task_tables_only_in_the_task_database(tmp_path):
    """The task tables must be created in the dedicated database and NOWHERE else.

    This is the regression guard for #2170. Reverting `create_core_tables` to a single
    `create_all(CoreBase.metadata)` on the shared engine leaves every other test in the
    suite green while silently recreating task_run/task_event_log in the database shared
    with control-plane — which is exactly the duplicate-rows bug.
    """
    from fred_core.tasks import TASK_TABLE_NAMES

    from knowledge_flow_backend.main import create_core_tables

    ctx = _context(_storage(tmp_path, with_task_db=True))
    await create_core_tables(ctx)

    shared_tables = await _table_names(ctx.get_pg_async_engine())
    task_tables = await _table_names(ctx.get_task_pg_async_engine())

    assert TASK_TABLE_NAMES <= task_tables, "task tables missing from the dedicated database"
    assert not (TASK_TABLE_NAMES & shared_tables), f"task tables leaked into the shared database: {sorted(TASK_TABLE_NAMES & shared_tables)}"
    # The split must not cost the shared database its own tables.
    assert shared_tables, "shared database got no tables at all"


@pytest.mark.asyncio
async def test_create_core_tables_keeps_pre_ops_04_behaviour_when_unconfigured(tmp_path):
    """With `task_postgres` unset both engines are one engine, so everything lands together.

    The fallback has to stay byte-for-byte the old behaviour: an operator who has not
    provisioned the dedicated database yet gets a working backend, duplicate rows included.
    """
    from fred_core.tasks import TASK_TABLE_NAMES

    from knowledge_flow_backend.main import create_core_tables

    ctx = _context(_storage(tmp_path, with_task_db=False))
    await create_core_tables(ctx)

    assert ctx.get_task_pg_async_engine() is ctx.get_pg_async_engine()
    assert TASK_TABLE_NAMES <= await _table_names(ctx.get_pg_async_engine())


@pytest.mark.asyncio
async def test_create_core_tables_survives_an_unreachable_task_database(tmp_path):
    """A dedicated task database that is down must not crash-loop the whole API pod.

    `create_core_tables` is the first statement of the FastAPI lifespan, so raising here
    exits uvicorn non-zero and takes document search, upload, tag and metadata reads down
    with it — for a database only `GET /tasks`, task SSE and ingestion start use. That
    directly contradicts the `postgres_tasks` readiness probe, which is deliberately
    advisory for exactly this reason, and Alembic (`alembic_tasks/`) owns the real schema
    anyway. The lifespan already treats `get_task_service()` this way.
    """
    storage = _storage(tmp_path, with_task_db=True)
    # A directory where SQLite expects a file: the engine still builds (an unreachable
    # server's would too), and the failure lands on connect — `unable to open database
    # file` — exactly where an unreachable Postgres would raise. Note a merely missing
    # parent directory would NOT work: `create_async_engine_from_config` mkdirs it.
    unopenable = tmp_path / "unopenable-tasks.db"
    unopenable.mkdir()
    ctx = _context(storage.model_copy(update={"task_postgres": PostgresStoreConfig(sqlite_path=str(unopenable), database="knowledge_flow")}))

    from knowledge_flow_backend.main import create_core_tables

    await create_core_tables(ctx)  # must not raise

    # The shared database is untouched by the task database's outage.
    assert await _table_names(ctx.get_pg_async_engine()), "shared tables must still be created"


# --------------------------------------------------------------------------------------
# Migration guards for a database WITHOUT task_run.
# --------------------------------------------------------------------------------------


def test_task_run_index_migrations_are_no_ops_when_the_table_is_absent(tmp_path):
    """`task_run` absent must be a no-op in BOTH directions, for every chain that alters it.

    OPS-04 makes this the normal state: the shared database no longer holds the task tables,
    so knowledge-flow's own chain now alters a table that is not there. Nothing else covers
    it — `db-check-combined-sqlite`/`-postgres` upgrade control-plane FIRST into the *same*
    database, so `task_run` always exists by the time this chain runs and the table-absent
    branch is never taken. A guard that is correct for upgrade but inverted for downgrade
    (returning a sentinel that reads as "present, drop it") passed every gate and still
    raised `UndefinedObjectError` on a real standalone downgrade.
    """
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa

    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    modules = sorted(versions.glob("*task_run_single_active_migration*.py")) + sorted(versions.glob("*add_task_run*.py"))
    assert modules, "expected at least one task_run index/column migration to exist"

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'no_task_run.db'}")
    with engine.begin() as conn:
        # A database that has everything EXCEPT task_run — the post-OPS-04 shared database.
        conn.execute(sa.text("CREATE TABLE metadata (document_uid TEXT PRIMARY KEY)"))

        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)

        for path in modules:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not (hasattr(mod, "upgrade") and hasattr(mod, "downgrade")):
                continue
            with Operations.context(ops):
                # Neither direction may touch a table that is not there.
                mod.upgrade()
                mod.downgrade()

        assert "task_run" not in sa.inspect(conn).get_table_names(), "a guard created task_run instead of skipping"


def test_task_run_index_migrations_tolerate_existing_same_kind_rows_on_sqlite(tmp_path):
    """Two non-terminal rows of one kind must survive the index migrations on SQLite.

    `e2f3a4b5c6d7` passed only `postgresql_where`. SQLAlchemy silently drops
    dialect-prefixed kwargs on other dialects, so on SQLite the predicate vanished and the
    index landed as an unconditional `UNIQUE (kind)`. On a database already holding two
    non-terminal `ingestion` rows the upgrade then aborted with `UNIQUE constraint failed:
    task_run.kind` — stranding the chain *before* the repair revision `f7a8b9c0d1e2` could
    ever run, so migrations were permanently blocked rather than merely wrong.

    Nothing else covers this: `db-check-combined-sqlite` migrates an empty database, where
    an unconditional unique index is created happily and the defect is invisible.
    """
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    versions = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    # Order matters: the defect is that the FIRST of these aborts, so the second never runs.
    ordered = [
        "e2f3a4b5c6d7_add_task_run_single_active_migration_index.py",
        "f7a8b9c0d1e2_repair_task_run_single_active_migration_index.py",
    ]

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'seeded.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE task_run (id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL)"))
        conn.execute(sa.text("INSERT INTO task_run (id, kind, state) VALUES ('a', 'ingestion', 'running'), ('b', 'ingestion', 'pending')"))

        migration_ctx = MigrationContext.configure(conn)
        for name in ordered:
            path = versions / name
            spec = importlib.util.spec_from_file_location(path.stem, path)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            with Operations.context(migration_ctx):
                mod.upgrade()

        assert conn.execute(sa.text("SELECT count(*) FROM task_run")).scalar_one() == 2, "the migrations dropped rows"
        # And the index that landed is the intended partial one, not `UNIQUE (kind)`: a
        # third non-terminal ingestion row still inserts.
        conn.execute(sa.text("INSERT INTO task_run (id, kind, state) VALUES ('c', 'ingestion', 'running')"))


def test_repair_migration_is_a_no_op_on_postgres_in_both_directions():
    """`f7a8b9c0d1e2` must emit nothing on Postgres — and the two directions must agree.

    The repair exists for a SQLite-only defect, and since OPS-04 this chain no longer owns
    `task_run`: on a deployment still sharing the `fred` database that table is
    control-plane's, so any DDL here takes ACCESS EXCLUSIVE on another service's live table.

    Gating only `upgrade()` is worse than gating neither. `e2f3a4b5c6d7` owns the index on
    Postgres, so an ungated `downgrade()` drops it and a gated `upgrade()` then declines to
    put it back: `make db-downgrade` (a documented operator procedure) followed by a
    re-upgrade silently and permanently destroys the single-active-migration constraint.
    Verified against PG 16: ungated, the round trip ends with the index gone and two
    non-terminal `kind='migration'` rows accepted.

    A mock engine keeps this offline while still presenting a real `postgresql` dialect —
    the gate is the only thing standing between the call and `sa.inspect()`, which a
    MockConnection cannot satisfy, so removing it fails this test rather than skipping it.
    """
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    emitted: list[str] = []
    mock_engine = sa.create_mock_engine("postgresql+psycopg://", lambda sql, *a, **kw: emitted.append(str(sql)))

    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "f7a8b9c0d1e2_repair_task_run_single_active_migration_index.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    ctx = MigrationContext.configure(connection=mock_engine)  # type: ignore[arg-type]
    with Operations.context(ctx):
        mod.upgrade()
        mod.downgrade()

    assert emitted == [], f"the repair migration emitted DDL on Postgres: {emitted}"
