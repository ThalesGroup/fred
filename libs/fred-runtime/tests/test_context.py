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

"""Offline unit tests for PodApplicationContext, container, and dependency helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from fastapi import FastAPI, Request
from fred_runtime.app.container import build_pod_container
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.app.dependencies import (
    attach_pod_container,
    get_pod_configuration,
    get_pod_container_from_app,
)


def test_build_pod_container_returns_context_with_configuration(minimal_config) -> None:
    """build_pod_container must return a PodApplicationContext bound to the config."""
    container = build_pod_container(minimal_config)
    assert isinstance(container, PodApplicationContext)
    assert container.configuration is minimal_config


def test_pod_context_get_kpi_writer_raises_before_initialize(minimal_config) -> None:
    """get_kpi_writer() must raise RuntimeError until initialize_kpi_writer() is called."""
    container = PodApplicationContext(minimal_config)
    with pytest.raises(RuntimeError, match="initialize_kpi_writer"):
        container.get_kpi_writer()


def test_pod_context_get_kpi_writer_succeeds_after_initialize(minimal_config) -> None:
    """get_kpi_writer() must return the writer once initialize_kpi_writer() has run."""
    container = PodApplicationContext(minimal_config)
    container.initialize_kpi_writer()
    writer = container.get_kpi_writer()
    assert writer is not None


def test_pod_context_control_plane_client_raises_before_initialize(
    minimal_config,
) -> None:
    """get_control_plane_http_client() must raise until initialize runs (TURN-01)."""
    container = PodApplicationContext(minimal_config)
    with pytest.raises(RuntimeError, match="initialize_control_plane_client"):
        container.get_control_plane_http_client()


def test_pod_context_control_plane_client_is_reused_across_calls(
    minimal_config,
) -> None:
    """Every caller must observe the exact same client instance — no per-turn
    construction (TURN-01's finding)."""
    container = PodApplicationContext(minimal_config)
    container.initialize_control_plane_client()

    first = container.get_control_plane_http_client()
    second = container.get_control_plane_http_client()

    assert first is second


def test_pod_context_control_plane_client_has_explicit_bounded_timeout_and_pool(
    minimal_config, monkeypatch
) -> None:
    """The shared client must be built with an explicit, bounded timeout and
    pool — not the httpx default (unbounded connect/read, unlimited connections)."""
    from fred_runtime.app import context as context_module

    captured: dict[str, object] = {}

    class _RecordingAsyncClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(context_module.httpx, "AsyncClient", _RecordingAsyncClient)

    container = PodApplicationContext(minimal_config)
    container.initialize_control_plane_client()

    timeout = cast(httpx.Timeout, captured["timeout"])
    limits = cast(httpx.Limits, captured["limits"])
    assert timeout.connect is not None and timeout.connect > 0
    assert timeout.read is not None and timeout.read > 0
    assert limits.max_connections is not None
    assert limits.max_keepalive_connections is not None


@pytest.mark.asyncio
async def test_pod_context_shutdown_closes_control_plane_client(
    minimal_config,
) -> None:
    """shutdown() must close the shared control-plane client (TURN-01)."""
    container = PodApplicationContext(minimal_config)
    container.initialize_control_plane_client()
    client = container.get_control_plane_http_client()
    assert not client.is_closed

    await container.shutdown()

    assert client.is_closed


@pytest.mark.asyncio
async def test_pod_context_shutdown_without_control_plane_client_does_not_raise(
    minimal_config,
) -> None:
    """shutdown() must stay a no-op for this resource when it was never initialized."""
    container = PodApplicationContext(minimal_config)
    await container.shutdown()  # must not raise


@pytest.mark.asyncio
async def test_pod_context_shutdown_cancels_kpi_tasks(minimal_config) -> None:
    """shutdown() must cancel any running KPI background tasks."""
    container = PodApplicationContext(minimal_config)

    done_event = asyncio.Event()

    async def _long_running() -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            done_event.set()
            raise

    task = asyncio.create_task(_long_running())
    container._kpi_tasks = [task]

    await container.shutdown()

    assert task.cancelled()


@pytest.mark.asyncio
async def test_pod_context_shutdown_handles_no_tasks_gracefully(minimal_config) -> None:
    """shutdown() must complete without error when no KPI tasks are running."""
    container = PodApplicationContext(minimal_config)
    await container.shutdown()  # must not raise


def test_attach_and_get_pod_container_roundtrip(minimal_config) -> None:
    """attach_pod_container / get_pod_container_from_app must be an exact roundtrip."""
    app = FastAPI()
    container = PodApplicationContext(minimal_config)
    attach_pod_container(app, container)
    retrieved = get_pod_container_from_app(app)
    assert retrieved is container


def test_get_pod_configuration_returns_config_from_container(minimal_config) -> None:
    """get_pod_configuration dependency must return the config held by the container."""
    app = FastAPI()
    container = PodApplicationContext(minimal_config)
    attach_pod_container(app, container)

    async def _receive():
        return {"type": "http.request", "body": b""}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "app": app,
    }
    request = Request(scope=scope, receive=_receive)

    config = get_pod_configuration(request)
    assert config is minimal_config


def test_ring_buffers_are_instance_level_not_global(minimal_config) -> None:
    """Each PodApplicationContext must have its own independent ring buffers."""
    from fred_runtime.app import agent_app as agent_app_module

    c1 = PodApplicationContext(minimal_config)
    c2 = PodApplicationContext(minimal_config)

    agent_app_module._emit_audit_event(c1, "info", "event_a", user_id="alice")
    agent_app_module._emit_audit_event(c2, "info", "event_b", user_id="bob")

    with c1._audit_events_lock:
        events1 = list(c1.audit_events_buffer)
    with c2._audit_events_lock:
        events2 = list(c2.audit_events_buffer)

    assert len(events1) == 1
    assert events1[0]["audit_event"] == "event_a"
    assert len(events2) == 1
    assert events2[0]["audit_event"] == "event_b"


# ---------------------------------------------------------------------------
# initialize_sql() — durable storage must never degrade silently (finding:
# a SQL init failure used to be swallowed and logged as "running stateless",
# leaving checkpointer/history_store at None with no signal to the caller).
# ---------------------------------------------------------------------------


def _sqlite_config(minimal_config, tmp_path):
    config = minimal_config.model_copy(deep=True)
    config.storage.postgres.sqlite_path = str(tmp_path / "runtime.sqlite3")
    return config


async def _migrate_sqlite(config) -> None:
    """Stand in for `python -m fred_runtime migrate` on the test's SQLite file.

    Since #2290 the history store creates no tables itself — the schema comes
    from Alembic — so a test that boots the pod must set the schema up first,
    exactly as a deployment's migration job does.
    """
    from fred_core.history.postgres_history_store import create_history_schema
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{config.storage.postgres.sqlite_path}"
    )
    try:
        await create_history_schema(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_initialize_sql_succeeds_and_wires_checkpointer_and_history_store(
    minimal_config, tmp_path
) -> None:
    """A reachable (sqlite, dev-equivalent) store must produce a non-None
    checkpointer and history store — the happy path the failure tests below
    are contrasted against."""
    config = _sqlite_config(minimal_config, tmp_path)
    await _migrate_sqlite(config)
    container = PodApplicationContext(config)
    container.initialize_kpi_writer()

    await container.initialize_sql()

    assert container.get_sql_engine() is not None
    assert container.get_checkpointer() is not None
    assert container.get_history_store() is not None


@pytest.mark.asyncio
async def test_initialize_sql_propagates_when_engine_construction_fails(
    minimal_config, tmp_path, monkeypatch
) -> None:
    """A local config error (e.g. missing FRED_POSTGRES_PASSWORD, missing
    host/database/username) must abort pod startup, not degrade silently."""
    import fred_core.sql.base_sql as base_sql_module

    def _raise(_config):
        raise ValueError("Missing required Postgres config fields: host")

    monkeypatch.setattr(base_sql_module, "create_async_engine_from_config", _raise)

    container = PodApplicationContext(_sqlite_config(minimal_config, tmp_path))
    container.initialize_kpi_writer()

    with pytest.raises(ValueError, match="Missing required Postgres config fields"):
        await container.initialize_sql()

    assert container.get_checkpointer() is None
    assert container.get_history_store() is None


class _FailingConnection:
    async def __aenter__(self):
        raise ConnectionRefusedError("could not connect to server")

    async def __aexit__(self, *exc_info):
        return False


class _UnreachableEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self) -> None:
        self.disposed = False

    def connect(self):
        return _FailingConnection()

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_initialize_sql_propagates_when_postgres_is_unreachable(
    minimal_config, tmp_path, monkeypatch
) -> None:
    """The actual production incident: config is well-formed but Postgres
    cannot be reached. SQLAlchemy's async engine is lazy — construction alone
    never opens a connection — so this only surfaces through the explicit
    boot-time SELECT 1 ping. Must abort startup, not run stateless."""
    import fred_core.sql.base_sql as base_sql_module

    engine = _UnreachableEngine()
    monkeypatch.setattr(
        base_sql_module,
        "create_async_engine_from_config",
        lambda _config: engine,
    )

    container = PodApplicationContext(_sqlite_config(minimal_config, tmp_path))
    container.initialize_kpi_writer()

    with pytest.raises(ConnectionRefusedError):
        await container.initialize_sql()

    assert container.get_sql_engine() is None
    assert container.get_checkpointer() is None
    assert container.get_history_store() is None
    # This engine never reaches self._sql_engine on this failure path, so
    # shutdown()'s own dispose() can never reach it either — it must be
    # disposed on the failure path itself, or it leaks.
    assert engine.disposed is True


class _SlowConnection:
    async def __aenter__(self):
        await asyncio.sleep(1.0)
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def execute(self, *args, **kwargs):
        return None


class _HangingEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self) -> None:
        self.disposed = False

    def connect(self):
        return _SlowConnection()

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_initialize_sql_bounds_the_connectivity_ping(
    minimal_config, tmp_path, monkeypatch
) -> None:
    """A network black hole (dropped packets, no TCP RST) must not hang pod
    startup for asyncpg's ~60s default connect timeout — the boot ping is
    bounded and fails fast instead."""
    import fred_core.sql.base_sql as base_sql_module
    from fred_runtime.app import context as context_module

    engine = _HangingEngine()
    monkeypatch.setattr(
        base_sql_module,
        "create_async_engine_from_config",
        lambda _config: engine,
    )
    monkeypatch.setattr(context_module, "_SQL_BOOT_PING_TIMEOUT_S", 0.05)

    container = PodApplicationContext(_sqlite_config(minimal_config, tmp_path))
    container.initialize_kpi_writer()

    with pytest.raises(TimeoutError):
        await container.initialize_sql()

    assert container.get_checkpointer() is None
    # Same leak-on-failure regression as the unreachable-Postgres case above
    # — the timeout path must dispose the engine too.
    assert engine.disposed is True


# ---------------------------------------------------------------------------
# initialize_sql() — an unmigrated database must abort startup (#2290). The
# history store no longer self-creates `session_history`, so an install whose
# migration job never ran has no schema; without this guard it would boot green
# and die mid-turn on UndefinedTableError (the #2137 failure class).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_sql_fails_fast_when_the_schema_was_never_migrated(
    minimal_config, tmp_path
) -> None:
    """Reachable database, no `session_history` — startup must abort with a
    message naming the missing table and the command that fixes it."""
    from fred_core.sql.schema_guard import SchemaNotMigratedError

    container = PodApplicationContext(_sqlite_config(minimal_config, tmp_path))
    container.initialize_kpi_writer()

    with pytest.raises(SchemaNotMigratedError) as excinfo:
        await container.initialize_sql()

    message = str(excinfo.value)
    assert "session_history" in message
    assert "python -m fred_runtime migrate" in message
    # No partially initialized store may be published on this path.
    assert container.get_sql_engine() is None
    assert container.get_checkpointer() is None
    assert container.get_history_store() is None


@pytest.mark.asyncio
async def test_initialize_sql_does_not_create_the_history_schema_itself(
    minimal_config, tmp_path
) -> None:
    """Regression guard for #2290: booting the pod must never leave DDL behind.
    A second boot against the same database must fail identically — proof that
    the first one created nothing."""
    from fred_core.sql.schema_guard import SchemaNotMigratedError

    config = _sqlite_config(minimal_config, tmp_path)
    container = PodApplicationContext(config)
    container.initialize_kpi_writer()

    with pytest.raises(SchemaNotMigratedError):
        await container.initialize_sql()

    second = PodApplicationContext(config)
    second.initialize_kpi_writer()
    with pytest.raises(SchemaNotMigratedError):
        await second.initialize_sql()
