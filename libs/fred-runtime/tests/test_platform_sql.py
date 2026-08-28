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

"""Offline tests for `fred_runtime.app.platform_sql` (OPSCAP-01-PG).

Everything here runs without a server: timeout clamping, the Postgres-only
factory gate (SQLite escape hatch → no adapter), and the error-mapping
redaction rules. The security claims themselves (single statement by
construction, READ ONLY transaction, row cap, server-side timeout) need a
real PostgreSQL and live in `test_platform_sql_postgres_integration.py`.
"""

from __future__ import annotations

from typing import Any, cast

import asyncpg
import pytest
from fred_core.common.structures import PostgresStoreConfig
from fred_runtime.app.platform_sql import (
    PlatformSqlAdapter,
    build_platform_sql_adapter,
    clamp_timeout_s,
    map_execution_error,
)
from fred_sdk.contracts.runtime import PlatformSqlPortError

# ---------------------------------------------------------------------------
# Timeout clamping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        (None, 15.0),  # adapter default
        (0.001, 1.0),  # below the floor
        (-5.0, 1.0),  # nonsense stays at the floor
        (1.0, 1.0),  # floor itself
        (30.0, 30.0),  # in-band passes through
        (120.0, 120.0),  # ceiling itself
        (10_000.0, 120.0),  # above the ceiling
    ],
)
def test_clamp_timeout_s(requested: float | None, expected: float) -> None:
    assert clamp_timeout_s(requested) == expected


# ---------------------------------------------------------------------------
# Factory: Postgres-only, dedicated engine
# ---------------------------------------------------------------------------


def test_sqlite_escape_hatch_builds_no_adapter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = PostgresStoreConfig(sqlite_path="/tmp/dev.db", password=None)
    with caplog.at_level("INFO"):
        assert build_platform_sql_adapter(config) is None
    assert any("SQLite dev escape hatch" in record.message for record in caplog.records)


def test_missing_password_fails_loud() -> None:
    config = PostgresStoreConfig(
        host="localhost", database="fred", username="fred", password=None
    )
    with pytest.raises(RuntimeError, match="FRED_POSTGRES_PASSWORD"):
        build_platform_sql_adapter(config)


@pytest.mark.asyncio
async def test_postgres_config_builds_dedicated_asyncpg_engine() -> None:
    config = PostgresStoreConfig(
        host="localhost",
        port=5432,
        database="fred",
        username="fred",
        password="secret",  # pragma: allowlist secret
    )
    adapter = build_platform_sql_adapter(config)
    assert isinstance(adapter, PlatformSqlAdapter)
    engine = adapter._engine
    try:
        # Engine creation is lazy — no socket was opened (this test runs
        # under --disable-socket).
        assert engine.url.drivername == "postgresql+asyncpg"
        # Dedicated small pool: never the app engine's defaults. `QueuePool`
        # attributes are untyped on the base `Pool`, hence the Any view.
        pool = cast(Any, engine.pool)
        assert pool.size() == 2
        assert pool._max_overflow == 0
    finally:
        await adapter.dispose()


# ---------------------------------------------------------------------------
# Error mapping: server message preserved, topology redacted
# ---------------------------------------------------------------------------


def test_server_error_message_and_sqlstate_are_preserved() -> None:
    exc = asyncpg.exceptions.PostgresSyntaxError(
        "cannot insert multiple commands into a prepared statement"
    )
    mapped = map_execution_error(exc)
    assert isinstance(mapped, PlatformSqlPortError)
    assert "multiple commands" in str(mapped)
    assert mapped.sqlstate == "42601"
    assert mapped.timed_out is False


def test_statement_timeout_cancel_maps_to_timed_out() -> None:
    exc = asyncpg.exceptions.QueryCanceledError(
        "canceling statement due to statement timeout"
    )
    mapped = map_execution_error(exc)
    assert mapped.timed_out is True
    assert mapped.sqlstate == "57014"
    assert "statement timeout" in str(mapped)


def test_wrapped_server_error_is_unwrapped_through_the_cause_chain() -> None:
    server = asyncpg.exceptions.ReadOnlySQLTransactionError(
        "cannot execute DELETE in a read-only transaction"
    )
    wrapper = RuntimeError("driver wrapper")
    wrapper.__cause__ = server
    mapped = map_execution_error(wrapper)
    assert "read-only transaction" in str(mapped)
    assert mapped.sqlstate == "25006"


def test_non_server_error_never_leaks_topology() -> None:
    exc = OSError(
        'connection to server at "db.fred.internal" (10.1.2.3), port 5432 failed'
    )
    mapped = map_execution_error(exc)
    message = str(mapped)
    assert "db.fred.internal" not in message
    assert "10.1.2.3" not in message
    assert "5432" not in message
    assert "OSError" in message
    assert mapped.sqlstate is None


def test_timeout_error_without_server_message_still_flags_timed_out() -> None:
    mapped = map_execution_error(TimeoutError("pool timeout for host db:5432"))
    assert mapped.timed_out is True
    assert "db:5432" not in str(mapped)


def test_pool_checkout_timeout_maps_to_a_retry_unchanged_message() -> None:
    from sqlalchemy.exc import TimeoutError as PoolCheckoutTimeoutError

    mapped = map_execution_error(PoolCheckoutTimeoutError("QueuePool limit"))
    assert mapped.timed_out is False
    assert mapped.sqlstate is None
    assert "retry it unchanged" in str(mapped)
    assert "was not executed" in str(mapped)


def test_already_typed_error_passes_through() -> None:
    original = PlatformSqlPortError("boom", timed_out=True, sqlstate="57014")
    assert map_execution_error(original) is original
