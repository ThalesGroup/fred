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

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fred_core.common import PostgresStoreConfig
from fred_core.session.session_schema import SessionSchema
from fred_core.session.stores.postgres_session_store import PostgresSessionStore
from fred_core.sql import create_async_engine_from_config

# Note: this test uses SQLite (via aiosqlite) so it runs without a real Postgres server.
# The ORM model uses JSONB().with_variant(JSON(), "sqlite") so session_data works on both.


@pytest.mark.asyncio
async def test_sqlite_store_save_get_count_delete(tmp_path) -> None:
    db_path = tmp_path / "session_store.sqlite3"
    cfg = PostgresStoreConfig(sqlite_path=str(db_path))
    engine = create_async_engine_from_config(cfg)

    # Create the table for the test
    from fred_core.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    store = PostgresSessionStore(engine=engine)

    session = SessionSchema(
        id="s1",
        user_id="u1",
        team_id="t1",
        agent_id="a1",
        title="Test Session",
        updated_at=datetime.now(timezone.utc),
    )

    await store.save(session)

    got = await store.get("s1")
    assert got is not None
    assert got.id == "s1"
    assert got.user_id == "u1"
    assert got.team_id == "t1"

    assert await store.count_for_user("u1") == 1

    sessions = await store.get_for_user("u1", "t1")
    assert len(sessions) == 1
    assert sessions[0].id == "s1"

    await store.delete("s1")
    assert await store.count_for_user("u1") == 0
    assert await store.get("s1") is None

    await engine.dispose()
