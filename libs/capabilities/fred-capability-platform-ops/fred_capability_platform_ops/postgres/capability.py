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
`PlatformPostgresCapability` (OPSCAP-01-PG) — read-only SQL over the platform
database, spec `docs/swift/rfc/admin-ops-capabilities/PLATFORM-POSTGRES.md`.

Doctrine summary:
- **Tier B**: the capability reuses the pod's own `storage.postgres`
  credentials through `RuntimeServices.platform_sql` (a `PlatformSqlPort`,
  fred-sdk). The DSN is a credential, so per the hard split it never enters
  this package — the credentialed executor and ALL read-only enforcement
  (single statement by construction, READ ONLY transaction, session-level
  read-only default, 200-row cap, timeout clamp) live in the fred-runtime
  adapter. This module owns declaration, tools, and result shaping only.
- **The admin team roster is the trust boundary**: `team_scope` stays the
  ADMIN_GATED default, and there is no table filtering — operators grant this
  capability only to teams whose members already hold direct psql access.
- **No SQL string validator here** (deliberate, spec §3): a Python-side parser
  is the only layer that could wrongly reject legitimate queries and is never
  the guarantee; the server-side stack is.
- Tool signatures carry ONLY LLM arguments; config and the port come through
  the `CapabilityContext` closure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Sequence

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import FieldSpec
from fred_sdk.contracts.runtime import (
    PLATFORM_SQL_TIMEOUT_DEFAULT_S,
    PLATFORM_SQL_TIMEOUT_MAX_S,
    PLATFORM_SQL_TIMEOUT_MIN_S,
    PlatformSqlPort,
    SqlQueryResult,
)
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# The tool-result `tool_ref` stamped on this capability's artifacts.
PLATFORM_POSTGRES_TOOL_REF = "platform_postgres"

# Result-shaping caps (spec §4) — hard-coded, applied in order so truncation
# preserves structure. The 200-row cap is the adapter's (server side, it sets
# `row_limit_hit`); these two are capability-side.
_CELL_CHAR_CAP = 1_000
_TOTAL_CHAR_CAP = 40_000

# The adapter re-clamps server-side; clamping here too keeps the forwarded
# value honest even if a stored config predates the FieldSpec bounds. Bounds
# come from the SDK contract so form, capability, and adapter cannot drift.
_TIMEOUT_BOUNDS_S = (PLATFORM_SQL_TIMEOUT_MIN_S, PLATFORM_SQL_TIMEOUT_MAX_S)

# Canned catalog query behind `postgres_list_tables` — through the SAME
# `execute_read` port as everything else, never a separate DB path. One row
# per table (columns aggregated in SQL): user tables / partitioned tables /
# materialized views, with free planner row estimates.
_LIST_TABLES_SQL = """\
SELECT n.nspname AS schema_name,
       c.relname AS table_name,
       GREATEST(c.reltuples, 0)::bigint AS approx_rows,
       COALESCE(
         string_agg(
           a.attname || ' ' || format_type(a.atttypid, a.atttypmod),
           ', ' ORDER BY a.attnum
         ),
         ''
       ) AS columns
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attribute a
  ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE c.relkind IN ('r', 'p', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY n.nspname, c.relname, c.reltuples
ORDER BY n.nspname, c.relname
"""


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    low, high = bounds
    return max(low, min(value, high))


def _sql_tool_failure(
    *,
    action: str,
    exc: Exception,
    elapsed_s: float,
) -> tuple[str, ToolInvocationResult]:
    """Turn a platform SQL tool-call failure into a non-empty, actionable
    error message plus an ``is_error=True`` artifact (same doctrine as
    `document_access`'s ``_document_tool_failure``).

    The runtime surfaces ``ToolInvocationResult.is_error`` directly, so a
    failing tool MUST return such a result instead of raising — and the text
    carries the server's own message (syntax error, undefined column,
    statement-timeout cancel) so the agent fixes its query instead of
    retrying it unchanged. Failure detail arrives via the SDK-typed
    `PlatformSqlPortError` attributes read with `getattr` — this module never
    imports the adapter's driver stack.
    """

    err_type = type(exc).__name__
    raw = str(exc).strip()
    timed_out = bool(getattr(exc, "timed_out", False))
    sqlstate = getattr(exc, "sqlstate", None)
    structured = timed_out or sqlstate is not None

    # Server-side log. Spec §6 / OBSERVABILITY-AND-AUDIT.md content exclusion:
    # a structured server failure's message can quote SQL fragments ('syntax
    # error at or near "DELETE"'), so it is logged metadata-only — the full
    # message still reaches the LLM below (that is the designed surface, and
    # the SQL itself is durably visible as a tool call in session history).
    # Only an UNEXPECTED failure (no server shape) keeps the stack: without
    # it, a programming error caught by the broad handlers would degrade into
    # a plausible "call failed" and never surface anywhere a developer looks.
    if structured:
        logger.error(
            "Platform SQL tool failure (%s, %.1fs) — error_class=%s sqlstate=%s "
            "timed_out=%s; degraded to an is_error artifact.",
            action,
            elapsed_s,
            err_type,
            sqlstate,
            timed_out,
        )
    else:
        logger.error(
            "Platform SQL tool failure (%s, %.1fs) — degraded to an is_error artifact.",
            action,
            elapsed_s,
            exc_info=exc,
        )

    if timed_out:
        cause = f"the server cancelled the query on statement timeout after {elapsed_s:.0f}s"
    elif sqlstate is not None:
        cause = f"the database rejected the query (SQLSTATE {sqlstate})"
    else:
        cause = f"the database call failed after {elapsed_s:.0f}s"

    # Unlike the document ports' structured branch, the server message is kept
    # even when the failure is identified: it IS the self-correction signal
    # ("column \"foo\" does not exist"), not a redundant transport detail.
    detail = f": {raw}" if raw else ""
    if structured:
        message = f"Could not {action}: {cause}{detail}. Fix the query and retry."
    else:
        message = f"Could not {action}: {cause} [{err_type}{detail}]."
    # `blocks` carries the same diagnostic as `content` (CAPAB-02): a Graph
    # agent's plain-dict invocation keeps only the artifact half of a
    # `content_and_artifact` return.
    return message, ToolInvocationResult(
        tool_ref=PLATFORM_POSTGRES_TOOL_REF,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def _normalize_cell(value: object) -> tuple[object, int | None]:
    """JSON-ready cell plus its true rendered length when it was truncated.

    Short scalars pass through; JSON containers (jsonb decoded to dict/list)
    are kept structural but round-tripped through ``default=str`` so nested
    driver types are already JSON-native; anything else (datetime, Decimal,
    UUID, memoryview reprs…) becomes its string rendering. A rendering longer
    than the per-cell cap is cut in place with an explicit marker — the row
    stays structurally intact and the marker tells the model to re-query
    narrower instead of reasoning over a fragment (spec §4).
    """

    if value is None or isinstance(value, (bool, int, float)):
        return value, None
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
        if len(text) <= _CELL_CHAR_CAP:
            return json.loads(text), None
    else:
        text = value if isinstance(value, str) else str(value)
        if len(text) <= _CELL_CHAR_CAP:
            return text, None
    true_len = len(text)
    return f"{text[:_CELL_CHAR_CAP]}…[truncated, {true_len} chars]", true_len


def _build_envelope(result: SqlQueryResult) -> dict[str, object]:
    """Shape one `SqlQueryResult` into the spec §4 JSON envelope.

    Caps applied in order: rows are already capped at 200 by the adapter
    (`row_limit_hit`); each cell is capped at ~1000 chars in place; the total
    is backstopped at ~40 KB by dropping trailing WHOLE rows (never mid-cell),
    reported as `rows_dropped`. `row_count` counts the rows actually present
    in `rows`; `truncated_cells` counts markers among those rows only.
    """

    normalized: list[tuple[list[object], int]] = []
    for row in result.rows:
        cells: list[object] = []
        row_truncated = 0
        for cell in row:
            norm, true_len = _normalize_cell(cell)
            if true_len is not None:
                row_truncated += 1
            cells.append(norm)
        normalized.append((cells, row_truncated))

    kept: list[list[object]] = []
    truncated_cells = 0
    # Character-length budget over the serialized rows (the "~" in ~40 KB:
    # column names and envelope metadata are small and not counted).
    used = 0
    dropped = 0
    for cells, row_truncated in normalized:
        row_size = len(json.dumps(cells, ensure_ascii=False, default=str)) + 2
        if used + row_size > _TOTAL_CHAR_CAP:
            dropped = len(normalized) - len(kept)
            break
        used += row_size
        kept.append(cells)
        truncated_cells += row_truncated

    return {
        "columns": list(result.columns),
        "rows": kept,
        "row_count": len(kept),
        "row_limit_hit": result.row_limit_hit,
        "rows_dropped": dropped,
        "truncated_cells": truncated_cells,
    }


def _format_table_lines(result: SqlQueryResult) -> str:
    """Render the canned catalog query as plain-text lines —
    ``schema.table (~rowcount): col type, col type, …`` — under the same
    total-size backstop as query results (trailing whole lines dropped)."""

    if not result.rows:
        return "No user tables found in the platform database."
    lines: list[str] = []
    used = 0
    omitted = 0
    for row in result.rows:
        schema_name, table_name, approx_rows, columns = row
        line = f"{schema_name}.{table_name} (~{approx_rows}): {columns}"
        if used + len(line) + 1 > _TOTAL_CHAR_CAP:
            omitted = len(result.rows) - len(lines)
            break
        used += len(line) + 1
        lines.append(line)
    if omitted:
        lines.append(
            f"…[{omitted} more tables omitted — query pg_class/pg_attribute "
            "directly for the rest]"
        )
    return "\n".join(lines)


class PlatformPostgresConfig(BaseModel):
    """Agent-creation / stored config of the `platform_postgres` capability.

    One knob only (spec §1): the server-side statement timeout. Everything
    else — row cap, truncation caps, table visibility — is hard-coded; no
    `StoredConfigModel`, no `validate_config` override (the FieldSpec bounds
    are the whole validation, and Tier B credentials are the pod's own,
    proven at boot).
    """

    statement_timeout_s: float = PLATFORM_SQL_TIMEOUT_DEFAULT_S


class PlatformPostgresCapability(
    AgentCapability[PlatformPostgresConfig, PlatformPostgresConfig, EmptyModel]
):
    """Read-only SQL over the platform database, through
    `RuntimeServices.platform_sql` (Tier B — see the module docstring for the
    doctrine and the spec pointer)."""

    manifest = CapabilityManifest(
        id="platform_postgres",
        version="0.1.0",
        name="capability.platform_postgres.name",
        description="capability.platform_postgres.description",
        icon="database",
        kind="tool",
        config_fields=[
            FieldSpec(
                key="statement_timeout_s",
                type="number",
                title="capability.platform_postgres.fields.statement_timeout_s.title",
                description="capability.platform_postgres.fields.statement_timeout_s.description",
                default=PLATFORM_SQL_TIMEOUT_DEFAULT_S,
                min=PLATFORM_SQL_TIMEOUT_MIN_S,
                max=PLATFORM_SQL_TIMEOUT_MAX_S,
            ),
        ],
        # team_scope stays the ADMIN_GATED default (spec §1) and
        # execution_models stays the react+graph default — a tools()-only
        # capability runs on both.
    )
    ConfigModel = PlatformPostgresConfig

    def tools(
        self,
        ctx: CapabilityContext[PlatformPostgresConfig, EmptyModel],
    ) -> Sequence[BaseTool]:
        """Build the two tools (spec §2), bound to the turn's typed context.

        Hard split: the tool signatures carry ONLY LLM arguments; the clamped
        timeout and the port come from this closure. Same
        `content_and_artifact` return convention as `document_access` (see
        its `tools()` docstring for the Phase-1 rationale).
        """

        services = ctx.services
        timeout_s = _clamp(ctx.config.statement_timeout_s, _TIMEOUT_BOUNDS_S)

        def _require_port() -> PlatformSqlPort:
            port = services.platform_sql
            if port is None:
                # No platform port injected (e.g. a bare test harness). Fail
                # LOUD rather than silently returning nothing.
                raise RuntimeError(
                    "platform_postgres: RuntimeServices.platform_sql is not "
                    "available on this execution path."
                )
            return port

        @tool("postgres_list_tables", response_format="content_and_artifact")
        async def postgres_list_tables() -> tuple[str, ToolInvocationResult]:
            """List every user table in the platform database, with columns and sizes.

            Call this BEFORE your first query of a session to ground yourself
            in the actual schema. Each line reads
            `schema.table (~rowcount): column type, column type, …` — row
            counts are planner estimates, not exact. System catalogs
            (pg_catalog, information_schema) are excluded. For anything
            deeper (exact counts, constraints, indexes), use
            postgres_run_query with a catalog query.
            """

            port = _require_port()
            started = time.monotonic()
            try:
                result = await port.execute_read(_LIST_TABLES_SQL, timeout_s=timeout_s)
            except Exception as exc:
                return _sql_tool_failure(
                    action="list the platform tables",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            text = _format_table_lines(result)
            artifact = ToolInvocationResult(
                tool_ref=PLATFORM_POSTGRES_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
            )
            return text, artifact

        @tool("postgres_run_query", response_format="content_and_artifact")
        async def postgres_run_query(sql: str) -> tuple[str, ToolInvocationResult]:
            """Run exactly ONE read-only SQL statement against the platform database.

            The database is PostgreSQL; writes are rejected server-side.
            Single statement only — multi-statement scripts fail. WITH/CTEs
            and EXPLAIN (without ANALYZE) work; anything multi-step is
            several tool calls.

            Results come back as a JSON envelope: `columns`, `rows` (arrays,
            positionally aligned with `columns`), `row_count`,
            `row_limit_hit`, `rows_dropped`, `truncated_cells`. Rows are
            capped at 200 — hitting the cap (`row_limit_hit: true`) means
            the query should aggregate in SQL instead (GROUP BY / count /
            avg), never page through raw rows. A cell ending in
            `…[truncated, N chars]` (or `rows_dropped` > 0) means you saw a
            fragment: re-query narrower (explicit columns, `->>` into JSON)
            instead of reasoning over it. On an error, read the server's
            message, fix the query, and retry — never retry unchanged.
            """

            port = _require_port()
            started = time.monotonic()
            try:
                result = await port.execute_read(sql, timeout_s=timeout_s)
            except Exception as exc:
                return _sql_tool_failure(
                    action="run the SQL query",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            # Off the event loop: 200 rows of multi-MB jsonb/blob cells make
            # rendering+truncation real CPU work; inline it would stall every
            # concurrent turn on the replica.
            envelope = await asyncio.to_thread(_build_envelope, result)
            # `default=str` is a safety net: cells are already JSON-native
            # after `_normalize_cell`, but driver types must never take the
            # tool down at serialization time.
            content = json.dumps(envelope, ensure_ascii=False, default=str)
            artifact = ToolInvocationResult(
                tool_ref=PLATFORM_POSTGRES_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data=envelope),),
            )
            return content, artifact

        return [postgres_list_tables, postgres_run_query]
