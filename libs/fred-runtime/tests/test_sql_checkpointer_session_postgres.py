# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
"""Real PostgreSQL index upgrade and prepared-plan regression coverage.

Set FRED_TEST_POSTGRES_URL to an isolated local postgresql+asyncpg database.
Only uniquely prefixed test tables are created and dropped.
"""

import os
from uuid import uuid4

import pytest
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.integration
@pytest.mark.integration_postgres
@pytest.mark.asyncio
async def test_session_indexes_upgrade_and_support_generic_plans():
    url = os.environ.get("FRED_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FRED_TEST_POSTGRES_URL is required")
    engine = create_async_engine(url)
    cp = FredSqlCheckpointer(engine, prefix=f"perf_{uuid4().hex[:8]}_")
    try:
        # Model an existing deployment that has tables but lacks the new indexes.
        async with engine.begin() as conn:
            await conn.run_sync(cp._metadata.create_all)
            for index in cp._session_indexes:
                await conn.run_sync(index.drop)
        await cp._ensure_tables()
        rebuilt = FredSqlCheckpointer(engine, prefix=cp.store.prefix)
        await rebuilt._ensure_tables()
        async with engine.begin() as conn:
            for table in (cp.checkpoints_table, cp.writes_table):
                indexes = await conn.run_sync(
                    lambda c: inspect(c).get_indexes(table.name)
                )
                assert f"{table.name}_session_idx" in {
                    index["name"] for index in indexes
                }

            ct, wt = cp.checkpoints_table.name, cp.writes_table.name
            await conn.execute(
                text(f"""
                INSERT INTO {ct} (thread_id, checkpoint_ns, checkpoint_id,
                    checkpoint_type, checkpoint_blob, metadata_json)
                SELECT md5(i::text), '', '1', 'test', ''::bytea, '{{}}'::jsonb
                FROM generate_series(1, 20000) i
            """)
            )
            sessions = ["s_1", r"s%_\1"]
            threads = [
                thread
                for session in sessions
                for thread in (
                    session,
                    f"{session}:agent",
                    f"{session}:dynamic:child",
                    f"{session}0",
                )
            ]
            await conn.execute(
                cp.checkpoints_table.insert(),
                [
                    dict(
                        thread_id=thread,
                        checkpoint_id="1",
                        checkpoint_type="test",
                        checkpoint_blob=b"",
                        metadata_json={},
                    )
                    for thread in threads
                ],
            )
            await conn.execute(
                text(f"""
                INSERT INTO {wt} (thread_id, checkpoint_ns, checkpoint_id,
                    task_id, idx, channel, value_type, value_blob, task_path)
                SELECT thread_id, '', '1', 'task', 0, 'test', 'test', ''::bytea, '' FROM {ct}
            """)
            )
            await conn.execute(text("SET LOCAL plan_cache_mode=force_generic_plan"))
            for number, table in enumerate((cp.checkpoints_table, cp.writes_table)):
                await conn.execute(text(f"ANALYZE {table.name}"))
                column = table.c.thread_id
                for session in sessions:
                    query = select(column).where(
                        cp.session_threads(column, session, f"{session}:")
                    )
                    found = set((await conn.execute(query)).scalars())
                    assert found == {
                        session,
                        f"{session}:agent",
                        f"{session}:dynamic:child",
                    }
                query = select(column).where(cp.session_threads(column, "s_1", "s_1:"))
                compiled = query.compile(
                    dialect=postgresql.dialect(paramstyle="numeric")
                )
                assert (
                    len(compiled.params) == 1
                )  # Delimiter/position must remain SQL literals.
                prepared_sql = str(compiled).replace(":1", "$1")
                await conn.execute(
                    text(f"PREPARE session_lookup_{number}(text) AS {prepared_sql}")
                )
                plan = (
                    await conn.execute(
                        text(
                            f"EXPLAIN (FORMAT JSON) EXECUTE session_lookup_{number}('s_1')"
                        )
                    )
                ).scalar_one()
                assert f"{table.name}_session_idx" in str(plan)
                assert "Seq Scan" not in str(plan)
                await conn.execute(text(f"DEALLOCATE session_lookup_{number}"))
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(cp._metadata.drop_all)
        await engine.dispose()
