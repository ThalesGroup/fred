from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from fred_core.common import PostgresStoreConfig
from fred_core.session.stores import PostgresJsonSessionStore
from fred_core.sql import create_async_engine_from_config


@pytest.mark.asyncio
async def test_sqlite_store_save_get_count_delete(tmp_path) -> None:
    db_path = tmp_path / "session_store.sqlite3"
    cfg = PostgresStoreConfig(sqlite_path=str(db_path))
    engine = create_async_engine_from_config(cfg)
    store = PostgresJsonSessionStore(engine=engine, table_name="session", prefix="")

    payload = {
        "id": "s1",
        "user_id": "u1",
        "team_id": "t1",
        "agent_id": "a1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "messages": [],
    }

    await store.save(
        session_id="s1",
        user_id="u1",
        updated_at=datetime.now(timezone.utc),
        payload=payload,
        team_id="t1",
        agent_id="a1",
    )

    got = await store.get_payload("s1")
    assert got is not None
    assert got["id"] == "s1"

    assert await store.count_for_user("u1") == 1

    await store.delete("s1")
    assert await store.count_for_user("u1") == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_store_backfills_missing_team_id_column(tmp_path) -> None:
    db_path = tmp_path / "session_store_migration.sqlite3"
    cfg = PostgresStoreConfig(sqlite_path=str(db_path))
    engine = create_async_engine_from_config(cfg)

    # Simulate a pre-migration table that does not yet have team_id.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE "session" (
                    session_id VARCHAR PRIMARY KEY,
                    user_id VARCHAR,
                    agent_id VARCHAR,
                    session_data JSON,
                    updated_at DATETIME
                )
                """
            )
        )

    # Instantiating the store should add missing team_id without SQL errors.
    store = PostgresJsonSessionStore(engine=engine, table_name="session", prefix="")
    await store._ensure_schema_ready()

    async with engine.begin() as conn:
        rows = await conn.execute(text('PRAGMA table_info("session")'))
        column_names = {row[1] for row in rows.fetchall()}
    assert "team_id" in column_names

    await engine.dispose()
