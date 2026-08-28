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
`PlatformSqlAdapter` — the fred-runtime side of `PlatformSqlPort` (OPSCAP-01-PG).

Read-only SQL over the platform's own Postgres, powering the
`platform_postgres` capability (spec:
`docs/swift/rfc/admin-ops-capabilities/PLATFORM-POSTGRES.md` §3). All policy
lives HERE, never in the SDK contract and never in capability code:

- **Dedicated engine/pool** (size 2, no overflow) built from the pod's
  `storage.postgres` config — never the app engine's pool, so a heavy
  analytical query can never starve the checkpointer/history hot path.
- **Enforcement stack**, all server-side (spec §3, deliberately no Python-side
  SQL string validator):
  1. *Single statement by construction* — every query goes through asyncpg's
     extended/prepared protocol (`Connection.prepare`), where the server's
     parse step accepts exactly one statement: `"SELECT 1; DELETE …"` is
     rejected before anything runs. We drop to the raw asyncpg connection
     because it is the only path that GUARANTEES the extended protocol (and a
     portal cursor for the row cap); no script/multi-statement API is ever
     used.
  2. *Explicit `READ ONLY` transaction* around every execution
     (`transaction(readonly=True)` → `BEGIN READ ONLY`) — the server rejects
     writes regardless of the role's read-write grants, per query, so even a
     session-level `SET default_transaction_read_only = off` smuggled through
     as a single statement cannot unlock a later query.
  3. *`default_transaction_read_only = on`* at connect time via
     `server_settings` — belt-and-suspenders for any future path that forgets
     layer 2.
- **Row cap**: hard-coded 200 rows (fetch 201 through a cursor, flag
  `row_limit_hit`). No config knob — an agent needing more should aggregate.
- **Timeout**: clamped to [1, 120] s (default 15), applied server-side via
  transaction-scoped `set_config('statement_timeout', ..., true)`,
  itself through the prepared path.
- **Error mapping**: server errors surface as `PlatformSqlPortError` carrying
  the SERVER's own message (syntax, undefined column, read-only violation,
  timeout cancel) so the agent can self-correct. Non-server failures are
  reduced to the exception type name — a driver/pool repr can embed the DSN,
  host, or port, and the message is rendered into the model-facing tool
  result and persisted in chat history (same redaction reasoning as
  `_wrap_document_port_error` in `integrations/v2_runtime/adapters.py`).
- **Observability** (spec §6): exactly one metadata-only INFO per query —
  duration, row count, `row_limit_hit`, error class — NEVER the SQL text at
  any level (the SQL is already durably visible as a tool call in session
  history). No Prometheus metric in v1.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, cast

import asyncpg
from fred_sdk.contracts.runtime import (
    PLATFORM_SQL_TIMEOUT_DEFAULT_S,
    PLATFORM_SQL_TIMEOUT_MAX_S,
    PLATFORM_SQL_TIMEOUT_MIN_S,
    PlatformSqlPort,
    PlatformSqlPortError,
    SqlQueryResult,
)
from sqlalchemy.exc import TimeoutError as PoolCheckoutTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from fred_core.common.structures import PostgresStoreConfig

logger = logging.getLogger(__name__)

# Row cap (spec §3): hard-coded, no knob. The adapter fetches one extra row
# through a portal cursor purely to learn whether more existed.
_ROW_CAP = 200

# Client-side grace over the server-side statement timeout: a dead network
# path (failover, half-open connection) means the server's cancel can never
# reach the client — without a client bound the await pins one of the two
# pool slots forever, and two such events brick the capability on the
# replica until restart.
_CLIENT_TIMEOUT_GRACE_S = 5.0

# SQLSTATE for `canceling statement due to statement timeout`.
_SQLSTATE_QUERY_CANCELED = "57014"


def clamp_timeout_s(timeout_s: float | None) -> float:
    """Clamp a caller-supplied timeout to the adapter's allowed band."""
    if timeout_s is None:
        return PLATFORM_SQL_TIMEOUT_DEFAULT_S
    return min(
        PLATFORM_SQL_TIMEOUT_MAX_S,
        max(PLATFORM_SQL_TIMEOUT_MIN_S, float(timeout_s)),
    )


def _find_server_error(exc: BaseException) -> asyncpg.PostgresError | None:
    """
    Walk an exception (and its `orig`/`__cause__` chain, as SQLAlchemy wraps
    driver errors) to the underlying asyncpg SERVER error, if any.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, asyncpg.PostgresError):
            return current
        # sqlalchemy.exc.DBAPIError carries the driver exception as `.orig`.
        orig = getattr(current, "orig", None)
        if isinstance(orig, asyncpg.PostgresError):
            return orig
        current = current.__cause__ or (
            orig if isinstance(orig, BaseException) else None
        )
    return None


def map_execution_error(exc: Exception) -> PlatformSqlPortError:
    """
    Map a driver/SQLAlchemy failure onto the SDK-typed `PlatformSqlPortError`.

    Server errors keep the server's own message verbatim — it is topology-free
    by construction (`syntax error at or near "DELETE"`, `cannot execute
    DELETE in a read-only transaction`, …) and it is exactly what the agent
    needs to self-correct. Anything else (pool timeout, connect failure,
    client-side interface error) is reduced to the exception TYPE name: those
    reprs can embed the DSN, host, or port, and this message reaches the LLM
    context and the persisted trace.
    """
    if isinstance(exc, PlatformSqlPortError):
        return exc
    server_error = _find_server_error(exc)
    if server_error is not None:
        sqlstate = getattr(server_error, "sqlstate", None)
        message = str(server_error).strip() or type(server_error).__name__
        return PlatformSqlPortError(
            message,
            timed_out=sqlstate == _SQLSTATE_QUERY_CANCELED,
            sqlstate=sqlstate,
        )
    if isinstance(exc, PoolCheckoutTimeoutError):
        # Pool checkout timed out — the query never ran. A distinct message
        # matters: the template tells the agent never to retry a FAILED query
        # unchanged, so an illegible pool error would make it "fix" a correct
        # query instead of simply retrying.
        return PlatformSqlPortError(
            "platform SQL connection pool is busy (all connections in use); "
            "the query was not executed — retry it unchanged shortly.",
            timed_out=False,
            sqlstate=None,
        )
    return PlatformSqlPortError(
        f"platform SQL execution failed: {type(exc).__name__}",
        timed_out=isinstance(exc, TimeoutError),
        sqlstate=None,
    )


class PlatformSqlAdapter(PlatformSqlPort):
    """Concrete `PlatformSqlPort` over a dedicated read-only-enforced engine.

    Pod-lifetime (like the checkpointer/KPI writer, NOT per-turn): built once
    by `PodApplicationContext.initialize_platform_sql()` and shared by every
    agent instance on the replica. Owns its engine — `dispose()` is called
    from the pod shutdown path.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def dispose(self) -> None:
        """Dispose the dedicated engine (pod shutdown only)."""
        await self._engine.dispose()

    async def execute_read(
        self,
        sql: str,
        *,
        timeout_s: float | None = None,
    ) -> SqlQueryResult:
        effective_timeout_s = clamp_timeout_s(timeout_s)
        started = time.perf_counter()
        row_count = 0
        row_limit_hit = False
        error_class: str | None = None
        try:
            # Client-side bound (server timeout + grace): covers pool checkout,
            # BEGIN, prepare, and fetch — the server-side cancel cannot reach a
            # dead network path, and an unbounded await would pin a pool slot.
            async with asyncio.timeout(effective_timeout_s + _CLIENT_TIMEOUT_GRACE_S):
                async with self._engine.connect() as sa_conn:
                    raw = await sa_conn.get_raw_connection()
                    # SQLAlchemy's asyncpg adapter exposes the real driver
                    # connection; we run the whole execution on it directly so the
                    # extended/prepared protocol (layer 1) and the READ ONLY
                    # transaction (layer 2) are guaranteed, not dialect-dependent.
                    driver_conn = cast(Any, raw.driver_connection)
                    async with driver_conn.transaction(readonly=True):
                        # Server-side timeout, transaction-scoped (SET LOCAL
                        # semantics via set_config(..., is_local=>true)). Runs
                        # through the same prepared/extended path as the query so
                        # this adapter NEVER touches asyncpg's script-capable
                        # simple-query API. The value is a clamped float of ours,
                        # never caller text.
                        timeout_ms = int(effective_timeout_s * 1000)
                        await driver_conn.fetchval(
                            "SELECT set_config('statement_timeout', $1, true)",
                            str(timeout_ms),
                        )
                        # Layer 1: prepare() parses through the extended protocol —
                        # a multi-statement string fails HERE, before execution.
                        statement = await driver_conn.prepare(sql)
                        cursor = await statement.cursor()
                        records = await cursor.fetch(_ROW_CAP + 1)
                        if len(records) > _ROW_CAP:
                            records = records[:_ROW_CAP]
                            row_limit_hit = True
                        columns = tuple(
                            attr.name for attr in statement.get_attributes()
                        )
                        rows = tuple(tuple(record) for record in records)
            row_count = len(rows)
            return SqlQueryResult(
                columns=columns, rows=rows, row_limit_hit=row_limit_hit
            )
        except Exception as exc:
            # Broad on purpose: the port contract is "any server/driver
            # failure raises PlatformSqlPortError" — mapped (never swallowed),
            # message redaction handled by map_execution_error.
            mapped = map_execution_error(exc)
            error_class = type(exc).__name__
            raise mapped from exc
        finally:
            # Spec §6: exactly one metadata-only INFO per query. Never the SQL
            # text, at any level.
            logger.info(
                "query executed — duration_ms=%d row_count=%d "
                "row_limit_hit=%s error_class=%s",
                int((time.perf_counter() - started) * 1000),
                row_count,
                row_limit_hit,
                error_class,
            )


def build_platform_sql_adapter(
    config: PostgresStoreConfig,
) -> PlatformSqlAdapter | None:
    """
    Build the pod's `PlatformSqlAdapter` from `storage.postgres`, or None.

    Postgres-only by design: when `sqlite_path` is set (laptop dev escape
    hatch) there is no server to enforce read-only against, so no adapter is
    built — the pod's `platform_sql` service stays None and the capability's
    missing-port guard fails loud at tool time.

    Deliberately NOT `create_async_engine_from_config`: that factory neither
    accepts pool overrides nor `server_settings`, and would silently fall back
    to SQLite. The dedicated engine here is small (pool 2, no overflow) and
    carries the connect-time read-only default (enforcement layer 3).
    """
    if config.sqlite_path is not None:
        logger.info(
            "storage.postgres uses the SQLite dev escape hatch "
            "(sqlite_path=%s) — platform SQL adapter not built; the "
            "platform_postgres capability will fail loud on its missing-port "
            "guard",
            config.sqlite_path,
        )
        return None
    if not config.password:
        # Mirrors create_async_engine_from_config: the password reaches
        # async_dsn() through PostgresStoreConfig.password, whose default is
        # the FRED_POSTGRES_PASSWORD environment variable at config load.
        raise RuntimeError(
            "FRED_POSTGRES_PASSWORD is required to build the platform SQL "
            "adapter (storage.postgres has no password)"
        )
    engine = create_async_engine(
        config.async_dsn(),
        pool_size=2,
        max_overflow=0,
        # Fail pool checkout fast (default 30s): with 2 slots and no
        # overflow, a busy pool should surface as a legible "retry shortly"
        # to the agent, not a half-minute silent wait inside tool latency.
        pool_timeout=5,
        pool_pre_ping=True,
        connect_args={
            # Enforcement layer 3 (spec §3): session-level read-only default
            # on every connection of this pool, set by the server at connect.
            "server_settings": {"default_transaction_read_only": "on"}
        },
    )
    return PlatformSqlAdapter(engine)
