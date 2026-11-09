# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Real PostgreSQL ownership, role boundaries and deletion races.

FRED_TEST_POSTGRES_URL must name an isolated local admin database. Each test
creates a separate database, with the same restricted roles as deployment.
"""

import asyncio
import os
import runpy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fred_core.history.history_schema import Channel, ChatMessage, Role
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_runtime.app.web_research_activity import WebResearchActivityStore
from fred_runtime.migrations import RUNTIME_ALEMBIC_DIR
from fred_runtime.runtime_support.checkpoints import graph_thread_id
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import MetaData, Table, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.integration_postgres,
    pytest.mark.asyncio,
]
SESSION = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
TABLES = (
    "session_history",
    "v2_langgraph_checkpoint",
    "v2_langgraph_checkpoint_blob",
    "v2_langgraph_checkpoint_write",
    "v2_checkpoint_thread_owner",
    "v2_checkpoint_hitl_claim",
    "cap_writable_document_docs",
    "cap_ppt_builder_deck_plan",
)


def _upgrade(revision):
    config = Config()
    config.set_main_option("script_location", str(RUNTIME_ALEMBIC_DIR))
    command.upgrade(config, revision)


def _capability_migrations(connection):
    capabilities = Path(__file__).resolve().parents[2] / "capabilities"
    trees = (
        (
            "fred-capability-writable-document/fred_capability_writable_document/writable_document_migrations/versions",
            "w*.py",
        ),
        (
            "fred-capability-ppt-filler/fred_capability_ppt_filler/builder/ppt_builder_migrations/versions",
            "r*.py",
        ),
    )
    with Operations.context(MigrationContext.configure(connection)):
        for versions, pattern in trees:
            for migration in sorted((capabilities / versions).glob(pattern)):
                runpy.run_path(str(migration))["upgrade"]()


@pytest_asyncio.fixture
async def database(monkeypatch):
    url = os.environ.get("FRED_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FRED_TEST_POSTGRES_URL is required")
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    name = f"ownership_{uuid4().hex}"
    async with admin.connect() as conn:
        for role in ("fred_cp", "fred_runtime"):
            if not await conn.scalar(
                text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}
            ):
                await conn.execute(
                    text(
                        f"CREATE ROLE {role} LOGIN PASSWORD 'it' NOSUPERUSER NOCREATEDB NOCREATEROLE"
                    )
                )
        await conn.execute(text(f"CREATE DATABASE {name}"))
    role_password = os.environ.get("FRED_TEST_ROLE_PASSWORD", "it")
    dburl = make_url(url).set(database=name)
    setup = create_async_engine(dburl)
    cp = create_async_engine(
        dburl.set(username="fred_cp", password=role_password),
        connect_args={"server_settings": {"search_path": "control_plane"}},
    )
    runtime_url = dburl.set(username="fred_runtime", password=role_password)
    runtime = create_async_engine(
        runtime_url, connect_args={"server_settings": {"search_path": "runtime"}}
    )
    try:
        async with setup.begin() as conn:
            await conn.execute(text("REVOKE ALL ON SCHEMA public FROM PUBLIC"))
            await conn.execute(
                text("CREATE SCHEMA control_plane AUTHORIZATION fred_cp")
            )
            await conn.execute(text("CREATE SCHEMA runtime AUTHORIZATION fred_runtime"))
        async with cp.begin() as conn:
            await conn.execute(
                text("CREATE TABLE session_metadata(session_id uuid PRIMARY KEY)")
            )
            await conn.execute(
                text("GRANT USAGE ON SCHEMA control_plane TO fred_runtime")
            )
            await conn.execute(
                text("GRANT REFERENCES(session_id) ON session_metadata TO fred_runtime")
            )
            await conn.execute(
                text("INSERT INTO session_metadata VALUES (:id), (:other)"),
                {"id": SESSION, "other": OTHER},
            )
        monkeypatch.setenv(
            "DATABASE_URL", runtime_url.render_as_string(hide_password=False)
        )
        monkeypatch.setenv("DATABASE_SCHEMA", "runtime")
        await asyncio.to_thread(_upgrade, "head")
        yield cp, runtime
    finally:
        await cp.dispose()
        await runtime.dispose()
        await setup.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
        await admin.dispose()


async def _migrate(runtime):
    await asyncio.to_thread(_upgrade, "head")
    async with runtime.begin() as conn:
        await conn.run_sync(_capability_migrations)
    cp = FredSqlCheckpointer(runtime)
    await cp._ensure_tables()
    return cp


def _message(session):
    return ChatMessage(
        session_id=session,
        exchange_id="exchange",
        rank=0,
        timestamp=datetime.now(timezone.utc),
        role=Role.user,
        channel=Channel.final,
        parts=[],
    )


async def _seed(runtime, cp, session):
    await PostgresHistoryStore(runtime).save(session, [_message(session)], "alice")
    thread = graph_thread_id(session, "agent:child")
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": ["private"]}
    config = {"configurable": {"thread_id": thread, "checkpoint_ns": "agent"}}
    await cp.aput(config, checkpoint, {}, {"messages": "1"})
    config["configurable"]["checkpoint_id"] = checkpoint["id"]
    await cp.aput_writes(config, [("messages", "private")], "task")
    await cp.aclaim_hitl_resume(
        thread_id=thread, checkpoint_ns="agent", interrupt_id="pause"
    )
    await PostgresHistoryStore(runtime).submit_steered_message(
        session_id=session,
        user_id="alice",
        space_id="space",
        agent_instance_id="agent",
        message_id="pending",
        content="private update",
    )
    async with runtime.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO cap_writable_document_docs (session_id, document_id, user_id, title, content_md, updated_by, created_at, updated_at) VALUES (:id, 'doc', 'alice', 'Title', 'private', 'agent', now(), now())"
            ),
            {"id": session},
        )
        await conn.execute(
            text(
                "INSERT INTO cap_ppt_builder_deck_plan (session_id, agent_instance_id, plan_json, updated_at) VALUES (:id, 'agent', 'private', now())"
            ),
            {"id": session},
        )


async def _counts(runtime, session):
    async with runtime.connect() as conn:
        return [
            await conn.scalar(
                text(f"SELECT count(*) FROM {table} WHERE conversation_id=:id"),
                {"id": session},
            )
            for table in TABLES
        ]


async def test_fresh_content_cascade_isolated_and_idempotent(database):
    control, runtime = database
    cp = await _migrate(runtime)
    await _seed(runtime, cp, SESSION)
    await _seed(runtime, cp, OTHER)
    await WebResearchActivityStore(runtime, 7).begin(
        request_id=str(uuid4()),
        user_id="alice",
        session_id=SESSION,
        correlation_id="c",
        operation="search",
        query="audit",
    )
    before = await _counts(runtime, OTHER)
    assert all(before)
    for _ in range(2):
        async with control.begin() as conn:
            await conn.execute(
                text("DELETE FROM session_metadata WHERE session_id=:id"),
                {"id": SESSION},
            )
    assert await _counts(runtime, SESSION) == [0] * len(TABLES)
    assert await _counts(runtime, OTHER) == before
    async with runtime.connect() as conn:
        assert (
            await conn.scalar(
                text(
                    "SELECT count(*) FROM runtime_web_research_activity WHERE session_id=:id"
                ),
                {"id": SESSION},
            )
            == 1
        )


async def test_late_writes_fail_in_database_after_runtime_restarts(database):
    control, runtime = database
    cp = await _migrate(runtime)
    await _seed(runtime, cp, SESSION)
    async with control.begin() as conn:
        await conn.execute(
            text("DELETE FROM session_metadata WHERE session_id=:id"), {"id": SESSION}
        )
    await runtime.dispose()
    restarted = FredSqlCheckpointer(runtime)
    await restarted._ensure_tables()
    with pytest.raises(IntegrityError):
        await restarted.aput(
            {"configurable": {"thread_id": graph_thread_id(SESSION, "late")}},
            empty_checkpoint(),
            {},
            {},
        )
    with pytest.raises(IntegrityError):
        await PostgresHistoryStore(runtime).save(SESSION, [_message(SESSION)], "alice")
    # Every table is protected even for SQL issued by a producer admitted before
    # the purge.
    async with runtime.connect() as conn:
        metadata = MetaData()
        reflected = await conn.run_sync(
            lambda sync: [Table(name, metadata, autoload_with=sync) for name in TABLES]
        )
    for table in reflected:
        async with runtime.begin() as conn:
            row = (
                (
                    await conn.execute(
                        select(table).where(table.c.conversation_id == OTHER)
                    )
                )
                .mappings()
                .first()
            )
        # Seed the neighbor if this case started without one.
        if row is None:
            await _seed(runtime, cp, OTHER)
            async with runtime.connect() as conn:
                row = (
                    (
                        await conn.execute(
                            select(table).where(table.c.conversation_id == OTHER)
                        )
                    )
                    .mappings()
                    .first()
                )
        values = dict(row)
        values.pop("conversation_id")
        key = "thread_id" if "thread_id" in values else "session_id"
        values[key] = values[key].replace(OTHER, SESSION)
        with pytest.raises(IntegrityError):
            async with runtime.begin() as conn:
                await conn.execute(table.insert().values(**values))
    assert await _counts(runtime, SESSION) == [0] * len(TABLES)


async def test_root_delete_waits_for_admitted_writer_then_erases_it(database):
    control, runtime = database
    cp = await _migrate(runtime)
    writer = await runtime.connect()
    tx = await writer.begin()
    await writer.execute(
        cp.thread_owner_table.insert().values(thread_id=SESSION, user_id="alice")
    )

    async def erase():
        async with control.begin() as conn:
            await conn.execute(
                text("DELETE FROM session_metadata WHERE session_id=:id"),
                {"id": SESSION},
            )

    deleting = asyncio.create_task(erase())
    await asyncio.sleep(0.05)
    assert not deleting.done()
    await tx.commit()
    await writer.close()
    await asyncio.wait_for(deleting, 5)
    assert await _counts(runtime, SESSION) == [0] * len(TABLES)


async def test_writer_waiting_behind_delete_cannot_recreate_content(database):
    control, runtime = database
    cp = await _migrate(runtime)
    deletion = await control.connect()
    tx = await deletion.begin()
    await deletion.execute(
        text("DELETE FROM session_metadata WHERE session_id=:id"), {"id": SESSION}
    )

    async def write():
        async with runtime.begin() as conn:
            await conn.execute(
                cp.thread_owner_table.insert().values(
                    thread_id=SESSION, user_id="alice"
                )
            )

    writing = asyncio.create_task(write())
    await asyncio.sleep(0.05)
    assert not writing.done()
    await tx.commit()
    await deletion.close()
    with pytest.raises(IntegrityError):
        await asyncio.wait_for(writing, 5)


async def test_runtime_cannot_read_or_create_roots_and_cp_cannot_read_content(database):
    control, runtime = database
    await _migrate(runtime)
    for sql in (
        "SELECT * FROM control_plane.session_metadata",
        "INSERT INTO control_plane.session_metadata VALUES (gen_random_uuid())",
    ):
        with pytest.raises(DBAPIError):
            async with runtime.begin() as conn:
                await conn.execute(text(sql))
    with pytest.raises(DBAPIError):
        async with control.begin() as conn:
            await conn.execute(text("SELECT * FROM runtime.session_history"))


async def test_runtime_metadata_matches_migrated_schema(database):
    _, runtime = database
    await _migrate(runtime)
    config = Config()
    config.set_main_option("script_location", str(RUNTIME_ALEMBIC_DIR))
    await asyncio.to_thread(command.check, config)


async def test_crashed_root_deletion_rolls_back_cascade_then_retries(database):
    control, runtime = database
    cp = await _migrate(runtime)
    await _seed(runtime, cp, SESSION)
    before = await _counts(runtime, SESSION)
    deletion = await control.connect()
    tx = await deletion.begin()
    try:
        await deletion.execute(
            text("DELETE FROM session_metadata WHERE session_id=:id"), {"id": SESSION}
        )
        pid = await deletion.scalar(text("SELECT pg_backend_pid()"))
        async with control.begin() as killer:
            assert await killer.scalar(
                text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
            )
        with pytest.raises(DBAPIError):
            await deletion.execute(text("SELECT 1"))
        await tx.rollback()
    finally:
        await deletion.close()
    assert await _counts(runtime, SESSION) == before
    async with control.begin() as conn:
        await conn.execute(
            text("DELETE FROM session_metadata WHERE session_id=:id"), {"id": SESSION}
        )
    assert await _counts(runtime, SESSION) == [0] * len(TABLES)
