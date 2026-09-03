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

"""`PlatformSqlAdapter`'s enforcement stack, executed against a real PostgreSQL.

These tests are the executable form of the security claims in
`docs/swift/rfc/admin-ops-capabilities/PLATFORM-POSTGRES.md` §3: single
statement by construction (asyncpg's extended/prepared protocol), explicit
READ ONLY transaction per query, the session-level read-only default, the
hard 200-row cap, and the server-side statement timeout. None of this can be
proven on SQLite — the enforcement IS the Postgres server's behavior.

Run:

    export FRED_PG_DSN="postgresql+asyncpg://fred:Azerty123_@localhost:5432/fred"  # pragma: allowlist secret
    .venv/bin/pytest tests/test_platform_sql_postgres_integration.py -m integration_postgres

Each test gets its own throwaway PostgreSQL schema (dropped on teardown), so
this never reads or writes the shared dev database's real tables. The adapter
under test is built through the production factory
(`build_platform_sql_adapter`) so the connect-time
`default_transaction_read_only=on` server setting is exercised too; test SQL
schema-qualifies its table names because the adapter's pool deliberately gets
no test-scoped `search_path`.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fred_core.common.structures import PostgresStoreConfig
from fred_runtime.app.platform_sql import (
    PlatformSqlAdapter,
    build_platform_sql_adapter,
)
from fred_sdk.contracts.runtime import PlatformSqlPortError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]

_PG_DSN_ENV = "FRED_PG_DSN"
_DEFAULT_DSN = "postgresql+asyncpg://fred:Azerty123_@localhost:5432/fred"  # pragma: allowlist secret


class _Fixture:
    def __init__(self, adapter: PlatformSqlAdapter, schema: str) -> None:
        self.adapter = adapter
        self.schema = schema

    def table(self) -> str:
        return f'"{self.schema}".t'


@pytest_asyncio.fixture
async def pg() -> AsyncIterator[_Fixture]:
    dsn = os.environ.get(_PG_DSN_ENV, _DEFAULT_DSN)
    schema = f"fred_runtime_itest_{uuid.uuid4().hex[:8]}"

    admin = create_async_engine(dsn)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.execute(
            text(f'CREATE TABLE "{schema}".t (id integer PRIMARY KEY, label text)')
        )
        await conn.execute(
            text(
                f'INSERT INTO "{schema}".t (id, label) '
                "VALUES (1, 'one'), (2, 'two'), (3, 'three')"
            )
        )
    await admin.dispose()

    url = make_url(dsn)
    config = PostgresStoreConfig(
        host=url.host,
        port=url.port or 5432,
        database=url.database,
        username=url.username,
        password=url.password,
    )
    adapter = build_platform_sql_adapter(config)
    assert adapter is not None
    try:
        yield _Fixture(adapter, schema)
    finally:
        await adapter.dispose()
        admin = create_async_engine(dsn)
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


async def _row_count(pg: _Fixture) -> int:
    result = await pg.adapter.execute_read(f"SELECT count(*) FROM {pg.table()}")
    return int(result.rows[0][0])


# ---------------------------------------------------------------------------
# (d) A normal SELECT works and returns typed columns/rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_returns_columns_and_rows(pg: _Fixture) -> None:
    result = await pg.adapter.execute_read(
        f"SELECT id, label FROM {pg.table()} ORDER BY id"
    )
    assert result.columns == ("id", "label")
    assert result.rows == ((1, "one"), (2, "two"), (3, "three"))
    assert result.row_limit_hit is False


@pytest.mark.asyncio
async def test_empty_result_keeps_column_names(pg: _Fixture) -> None:
    result = await pg.adapter.execute_read(
        f"SELECT id, label FROM {pg.table()} WHERE id = -1"
    )
    assert result.columns == ("id", "label")
    assert result.rows == ()
    assert result.row_limit_hit is False


# ---------------------------------------------------------------------------
# (a) Multi-statement strings are rejected at parse — layer 1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_statement_string_is_rejected(pg: _Fixture) -> None:
    with pytest.raises(PlatformSqlPortError) as excinfo:
        await pg.adapter.execute_read(f"SELECT 1; DELETE FROM {pg.table()}")
    assert excinfo.value.sqlstate == "42601"
    assert "multiple commands" in str(excinfo.value)
    assert await _row_count(pg) == 3


# ---------------------------------------------------------------------------
# (b) Plain writes are rejected inside the READ ONLY transaction — layer 2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "write_sql",
    [
        "INSERT INTO {table} (id, label) VALUES (99, 'nope')",
        "UPDATE {table} SET label = 'nope' WHERE id = 1",
        "DELETE FROM {table}",
    ],
)
async def test_single_statement_writes_are_rejected(
    pg: _Fixture, write_sql: str
) -> None:
    with pytest.raises(PlatformSqlPortError) as excinfo:
        await pg.adapter.execute_read(write_sql.format(table=pg.table()))
    assert excinfo.value.sqlstate == "25006"
    assert "read-only" in str(excinfo.value)
    result = await pg.adapter.execute_read(
        f"SELECT id, label FROM {pg.table()} ORDER BY id"
    )
    assert result.rows == ((1, "one"), (2, "two"), (3, "three"))


# ---------------------------------------------------------------------------
# (c) The session-state escape is unreachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_only_escape_script_is_rejected(pg: _Fixture) -> None:
    """The exact escape §3 calls out: mutate session state, commit, write."""
    with pytest.raises(PlatformSqlPortError) as excinfo:
        await pg.adapter.execute_read(
            f"SET default_transaction_read_only = off; COMMIT; DELETE FROM {pg.table()}"
        )
    assert excinfo.value.sqlstate == "42601"
    assert await _row_count(pg) == 3


@pytest.mark.asyncio
async def test_single_set_statement_cannot_unlock_later_writes(pg: _Fixture) -> None:
    """
    Layer 2 is per-query: even if a lone `SET default_transaction_read_only =
    off` slips through as a legal single statement on some pooled connection,
    the next query still runs inside its own explicit READ ONLY transaction.
    """
    with contextlib.suppress(PlatformSqlPortError):
        await pg.adapter.execute_read("SET default_transaction_read_only = off")
    # Hit more than the pool's 2 connections' worth of attempts so a poisoned
    # session default (if any) would be reached.
    for _ in range(4):
        with pytest.raises(PlatformSqlPortError) as excinfo:
            await pg.adapter.execute_read(f"DELETE FROM {pg.table()}")
        assert excinfo.value.sqlstate == "25006"
    assert await _row_count(pg) == 3


# ---------------------------------------------------------------------------
# (e) Row cap: 200 rows, flag when a 201st existed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_row_cap_truncates_and_flags(pg: _Fixture) -> None:
    result = await pg.adapter.execute_read("SELECT generate_series(1, 250) AS n")
    assert len(result.rows) == 200
    assert result.row_limit_hit is True
    assert result.rows[0] == (1,)
    assert result.rows[-1] == (200,)


@pytest.mark.asyncio
async def test_exactly_200_rows_is_not_flagged(pg: _Fixture) -> None:
    result = await pg.adapter.execute_read("SELECT generate_series(1, 200) AS n")
    assert len(result.rows) == 200
    assert result.row_limit_hit is False


# ---------------------------------------------------------------------------
# (f) Server-side statement timeout maps to timed_out=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_statement_timeout_maps_to_timed_out(pg: _Fixture) -> None:
    with pytest.raises(PlatformSqlPortError) as excinfo:
        await pg.adapter.execute_read("SELECT pg_sleep(5)", timeout_s=1)
    assert excinfo.value.timed_out is True
    assert excinfo.value.sqlstate == "57014"
    assert "statement timeout" in str(excinfo.value)


# ---------------------------------------------------------------------------
# (g) Legitimate read shapes are NOT wrongly rejected (no string validator)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_cte_works(pg: _Fixture) -> None:
    result = await pg.adapter.execute_read(
        f"WITH counted AS (SELECT count(*) AS n FROM {pg.table()}) "
        "SELECT n FROM counted"
    )
    assert result.columns == ("n",)
    assert result.rows == ((3,),)


@pytest.mark.asyncio
async def test_explain_without_analyze_works(pg: _Fixture) -> None:
    result = await pg.adapter.execute_read(
        f"EXPLAIN SELECT id FROM {pg.table()} WHERE id = 1"
    )
    assert result.columns == ("QUERY PLAN",)
    assert len(result.rows) >= 1


# ---------------------------------------------------------------------------
# Server error messages reach the caller for self-correction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undefined_column_error_carries_server_message(pg: _Fixture) -> None:
    with pytest.raises(PlatformSqlPortError) as excinfo:
        await pg.adapter.execute_read(f"SELECT no_such_column FROM {pg.table()}")
    assert excinfo.value.sqlstate == "42703"
    assert "no_such_column" in str(excinfo.value)
