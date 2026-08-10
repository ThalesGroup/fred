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
Offline unit tests: `require_tables` — a deployment that skipped its migrations
must be caught at startup with an actionable message (#2290), never mid-request
as an UndefinedTableError (#2137).
"""

from __future__ import annotations

import logging

import pytest
from fred_core.history.postgres_history_store import create_history_schema
from fred_core.sql.schema_guard import SchemaNotMigratedError, require_tables
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _engine(tmp_path, name: str = "guard.sqlite3"):
    return create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")


@pytest.mark.asyncio
async def test_missing_table_raises_with_the_fix_command(tmp_path) -> None:
    engine = _engine(tmp_path)

    with pytest.raises(SchemaNotMigratedError) as excinfo:
        await require_tables(
            engine,
            ["session_history"],
            component="fred-runtime",
            migrate_command="python -m fred_runtime migrate",
        )

    message = str(excinfo.value)
    # The operator must learn *what* is missing and *how* to fix it, without
    # reading the source.
    assert "session_history" in message
    assert "python -m fred_runtime migrate" in message
    assert "DATABASE_MIGRATIONS.md" in message


@pytest.mark.asyncio
async def test_present_and_stamped_tables_pass_silently(tmp_path, caplog) -> None:
    engine = _engine(tmp_path)
    await create_history_schema(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE alembic_version_runtime (version_num TEXT)")
        )
        await conn.execute(text("INSERT INTO alembic_version_runtime VALUES ('c3d4')"))

    with caplog.at_level(logging.WARNING):
        await require_tables(
            engine,
            ["session_history"],
            component="fred-runtime",
            migrate_command="python -m fred_runtime migrate",
            version_table="alembic_version_runtime",
        )

    assert caplog.records == []


@pytest.mark.asyncio
async def test_unstamped_database_warns_but_still_boots(tmp_path, caplog) -> None:
    """The pre-#2290 state: tables self-created by the store, Alembic never
    stamped. The pod must still serve (the schema is correct) but the operator
    must be told, because the next `alembic upgrade head` will fail."""
    engine = _engine(tmp_path)
    await create_history_schema(engine)

    with caplog.at_level(logging.WARNING):
        await require_tables(
            engine,
            ["session_history"],
            component="fred-runtime",
            migrate_command="python -m fred_runtime migrate",
            version_table="alembic_version_runtime",
        )

    assert any(
        "alembic_version_runtime" in record.getMessage() for record in caplog.records
    )


@pytest.mark.asyncio
async def test_empty_version_table_counts_as_unstamped(tmp_path, caplog) -> None:
    engine = _engine(tmp_path)
    await create_history_schema(engine)
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE alembic_version_runtime (version_num TEXT)")
        )

    with caplog.at_level(logging.WARNING):
        await require_tables(
            engine,
            ["session_history"],
            component="fred-runtime",
            migrate_command="python -m fred_runtime migrate",
            version_table="alembic_version_runtime",
        )

    assert caplog.records != []
