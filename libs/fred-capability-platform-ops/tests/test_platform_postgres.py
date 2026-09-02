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

"""Offline unit tests for the `platform_postgres` capability (spec §7.1).

The port is a stub `PlatformSqlPort` subclass recording the (sql, timeout_s)
it received, with an optional preset error — the capability's ONLY seam to
the database, so these tests never touch a driver. Tools are built from a
typed `CapabilityContext` (mirroring the ppt-filler package tests, which
build one without fred-runtime) and invoked through `ainvoke` with a ToolCall
dict — the runtime idiom — so `message.artifact` carries the
`ToolInvocationResult` (mirroring `test_capability_document_access_1906.py`).
"""

from __future__ import annotations

import datetime
import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fred_capability_platform_ops.postgres.capability import (
    PLATFORM_POSTGRES_TOOL_REF,
    PlatformPostgresCapability,
    PlatformPostgresConfig,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import ToolContentKind
from fred_sdk.contracts.runtime import (
    PlatformSqlPort,
    PlatformSqlPortError,
    RuntimeServices,
    SqlQueryResult,
)

# ---------------------------------------------------------------------------
# Stub port + context/tool assembly helpers
# ---------------------------------------------------------------------------


class StubSqlPort(PlatformSqlPort):
    """Stub `PlatformSqlPort` recording calls, with an optional preset error."""

    def __init__(
        self,
        result: SqlQueryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result if result is not None else SqlQueryResult()
        self._error = error

    async def execute_read(
        self,
        sql: str,
        *,
        timeout_s: float | None = None,
    ) -> SqlQueryResult:
        self.calls.append({"sql": sql, "timeout_s": timeout_s})
        if self._error is not None:
            raise self._error
        return self._result


def _ctx(
    *,
    port: StubSqlPort | None,
    config: PlatformPostgresConfig | None = None,
) -> CapabilityContext[PlatformPostgresConfig, EmptyModel]:
    return CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1"),
        config=config if config is not None else PlatformPostgresConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(platform_sql=port),
    )


def _tools(ctx: CapabilityContext[PlatformPostgresConfig, EmptyModel]):
    return {t.name: t for t in PlatformPostgresCapability().tools(ctx)}


async def _invoke(
    ctx: CapabilityContext[PlatformPostgresConfig, EmptyModel],
    name: str,
    args: dict[str, Any],
) -> Any:
    the_tool = _tools(ctx)[name]
    return await the_tool.ainvoke(
        {"type": "tool_call", "name": name, "args": args, "id": "call-1"}
    )


def _catalog_result() -> SqlQueryResult:
    return SqlQueryResult(
        columns=("schema_name", "table_name", "approx_rows", "columns"),
        rows=(
            ("public", "agents", 42, "id uuid, name text, created_at timestamptz"),
            ("public", "sessions", 1200, "id uuid, user_id text"),
        ),
    )


# ---------------------------------------------------------------------------
# Tool surface — the hard split
# ---------------------------------------------------------------------------


def test_tool_signatures_carry_only_llm_arguments() -> None:
    tools = _tools(_ctx(port=StubSqlPort()))
    assert set(tools) == {"postgres_list_tables", "postgres_run_query"}
    assert list(tools["postgres_list_tables"].args) == []
    assert list(tools["postgres_run_query"].args) == ["sql"]


# ---------------------------------------------------------------------------
# postgres_list_tables — happy path + formatting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tables_formats_one_line_per_table() -> None:
    port = StubSqlPort(result=_catalog_result())
    message = await _invoke(_ctx(port=port), "postgres_list_tables", {})

    assert message.content.splitlines() == [
        "public.agents (~42): id uuid, name text, created_at timestamptz",
        "public.sessions (~1200): id uuid, user_id text",
    ]
    # One canned catalog query through the SAME port path — never a separate one.
    assert len(port.calls) == 1
    assert "pg_class" in port.calls[0]["sql"]
    assert "pg_namespace" in port.calls[0]["sql"]
    assert port.calls[0]["timeout_s"] == 15
    # Artifact mirrors the content (CAPAB-02) under the capability tool_ref.
    assert message.artifact.tool_ref == PLATFORM_POSTGRES_TOOL_REF
    assert message.artifact.is_error is False
    assert message.artifact.blocks[0].kind is ToolContentKind.TEXT
    assert message.artifact.blocks[0].text == message.content


@pytest.mark.asyncio
async def test_list_tables_empty_database() -> None:
    port = StubSqlPort(result=SqlQueryResult(columns=("a", "b", "c", "d")))
    message = await _invoke(_ctx(port=port), "postgres_list_tables", {})
    assert "No user tables" in message.content
    assert message.artifact.is_error is False


@pytest.mark.asyncio
async def test_list_tables_total_backstop_drops_trailing_lines() -> None:
    # ~600 tables × ~110-char lines ≈ 66 KB — the ~40 KB backstop must cut at
    # line granularity and say how many were omitted.
    rows = tuple(
        ("public", f"table_{i:04d}", i, "id uuid, payload jsonb, " + "c text, " * 10)
        for i in range(600)
    )
    port = StubSqlPort(
        result=SqlQueryResult(
            columns=("schema_name", "table_name", "approx_rows", "columns"), rows=rows
        )
    )
    message = await _invoke(_ctx(port=port), "postgres_list_tables", {})

    lines = message.content.splitlines()
    assert len(lines) < 600
    assert "more tables omitted" in lines[-1]
    # Every listed line is a whole, intact line.
    assert all(line.startswith("public.table_") for line in lines[:-1])
    assert len(message.content) <= 41_000


# ---------------------------------------------------------------------------
# postgres_run_query — envelope correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_query_envelope_happy_path() -> None:
    port = StubSqlPort(
        result=SqlQueryResult(
            columns=("team", "members"),
            rows=(("acme", 12), ("globex", 7)),
        )
    )
    message = await _invoke(
        _ctx(port=port),
        "postgres_run_query",
        {"sql": "SELECT team, members FROM t"},
    )

    envelope = json.loads(message.content)
    assert envelope == {
        "columns": ["team", "members"],
        "rows": [["acme", 12], ["globex", 7]],
        "row_count": 2,
        "row_limit_hit": False,
        "rows_dropped": 0,
        "truncated_cells": 0,
    }
    assert port.calls[0]["sql"] == "SELECT team, members FROM t"
    assert message.artifact.tool_ref == PLATFORM_POSTGRES_TOOL_REF
    assert message.artifact.blocks[0].kind is ToolContentKind.JSON
    assert message.artifact.blocks[0].data == envelope


@pytest.mark.asyncio
async def test_run_query_empty_result() -> None:
    port = StubSqlPort(result=SqlQueryResult(columns=("id",)))
    message = await _invoke(_ctx(port=port), "postgres_run_query", {"sql": "SELECT 1"})
    envelope = json.loads(message.content)
    assert envelope["columns"] == ["id"]
    assert envelope["rows"] == []
    assert envelope["row_count"] == 0
    assert envelope["rows_dropped"] == 0
    assert envelope["truncated_cells"] == 0


@pytest.mark.asyncio
async def test_run_query_row_limit_hit_passthrough() -> None:
    port = StubSqlPort(
        result=SqlQueryResult(columns=("n",), rows=((1,),), row_limit_hit=True)
    )
    message = await _invoke(_ctx(port=port), "postgres_run_query", {"sql": "SELECT n"})
    assert json.loads(message.content)["row_limit_hit"] is True


@pytest.mark.asyncio
async def test_run_query_serializes_driver_types_via_default_str() -> None:
    stamp = datetime.datetime(2026, 8, 27, 12, 0, 0, tzinfo=datetime.timezone.utc)
    row = (Decimal("12.50"), uuid.UUID("12345678-1234-5678-1234-567812345678"), stamp)
    port = StubSqlPort(
        result=SqlQueryResult(columns=("amount", "id", "created_at"), rows=(row,))
    )
    message = await _invoke(_ctx(port=port), "postgres_run_query", {"sql": "SELECT *"})
    envelope = json.loads(message.content)
    assert envelope["rows"] == [
        ["12.50", "12345678-1234-5678-1234-567812345678", "2026-08-27 12:00:00+00:00"]
    ]


# ---------------------------------------------------------------------------
# Truncation edges (spec §4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_giant_cell_truncated_in_place_with_marker() -> None:
    blob = "x" * 5_000
    port = StubSqlPort(
        result=SqlQueryResult(columns=("id", "blob"), rows=((1, blob), (2, "small")))
    )
    message = await _invoke(_ctx(port=port), "postgres_run_query", {"sql": "SELECT *"})

    envelope = json.loads(message.content)
    cell = envelope["rows"][0][1]
    assert cell.endswith("…[truncated, 5000 chars]")
    assert cell.startswith("x" * 1_000)
    assert len(cell) == 1_000 + len("…[truncated, 5000 chars]")
    # Both rows survive structurally intact; only the one cell was cut.
    assert envelope["rows"][1] == [2, "small"]
    assert envelope["row_count"] == 2
    assert envelope["rows_dropped"] == 0
    assert envelope["truncated_cells"] == 1


@pytest.mark.asyncio
async def test_total_cap_drops_trailing_whole_rows_never_mid_cell() -> None:
    # 200 rows × ~900-char cells ≈ 180 KB — far past the ~40 KB backstop.
    rows = tuple((i, f"cell-{i}-" + "y" * 900) for i in range(200))
    port = StubSqlPort(result=SqlQueryResult(columns=("id", "payload"), rows=rows))
    message = await _invoke(_ctx(port=port), "postgres_run_query", {"sql": "SELECT *"})

    envelope = json.loads(message.content)
    kept = envelope["rows"]
    assert 0 < len(kept) < 200
    assert envelope["row_count"] == len(kept)
    assert envelope["rows_dropped"] == 200 - len(kept)
    # Never mid-cell: every kept row equals its original, uncut form.
    for row in kept:
        i = row[0]
        assert row == [i, f"cell-{i}-" + "y" * 900]
    # No per-cell markers here — the cells were under the per-cell cap.
    assert envelope["truncated_cells"] == 0
    assert len(message.content) <= 45_000


# ---------------------------------------------------------------------------
# Errors — is_error results carrying the server's message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_error_returns_is_error_result_with_server_message() -> None:
    port = StubSqlPort(
        error=PlatformSqlPortError('column "nme" does not exist', sqlstate="42703")
    )
    message = await _invoke(
        _ctx(port=port), "postgres_run_query", {"sql": "SELECT nme FROM t"}
    )
    assert message.artifact.is_error is True
    assert 'column "nme" does not exist' in message.content
    assert "42703" in message.content
    # The artifact carries the same diagnostic for Graph-path consumers.
    assert message.artifact.blocks[0].text == message.content


@pytest.mark.asyncio
async def test_timed_out_error_reported_as_statement_timeout() -> None:
    port = StubSqlPort(
        error=PlatformSqlPortError(
            "canceling statement due to statement timeout", timed_out=True
        )
    )
    message = await _invoke(_ctx(port=port), "postgres_run_query", {"sql": "SELECT 1"})
    assert message.artifact.is_error is True
    assert "statement timeout" in message.content


@pytest.mark.asyncio
async def test_list_tables_error_also_degrades_to_is_error() -> None:
    port = StubSqlPort(error=PlatformSqlPortError("connection refused"))
    message = await _invoke(_ctx(port=port), "postgres_list_tables", {})
    assert message.artifact.is_error is True
    assert "connection refused" in message.content


# ---------------------------------------------------------------------------
# Missing port + config forwarding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_port_fails_loud() -> None:
    ctx = _ctx(port=None)
    with pytest.raises(RuntimeError, match="platform_sql is not available"):
        await _invoke(ctx, "postgres_run_query", {"sql": "SELECT 1"})
    with pytest.raises(RuntimeError, match="platform_sql is not available"):
        await _invoke(ctx, "postgres_list_tables", {})


@pytest.mark.asyncio
async def test_default_timeout_forwarded_to_port() -> None:
    port = StubSqlPort(result=SqlQueryResult(columns=("n",)))
    await _invoke(_ctx(port=port), "postgres_run_query", {"sql": "SELECT 1"})
    assert port.calls[0]["timeout_s"] == 15


@pytest.mark.asyncio
async def test_custom_timeout_forwarded_and_clamped() -> None:
    port = StubSqlPort(result=SqlQueryResult(columns=("n",)))
    config = PlatformPostgresConfig(statement_timeout_s=42)
    await _invoke(
        _ctx(port=port, config=config), "postgres_run_query", {"sql": "SELECT 1"}
    )
    assert port.calls[0]["timeout_s"] == 42

    # Out-of-band stored values (predating FieldSpec bounds) are clamped to
    # the adapter's allowed band before forwarding.
    for stored, forwarded in ((999.0, 120.0), (0.1, 1.0)):
        port = StubSqlPort(result=SqlQueryResult(columns=("n",)))
        config = PlatformPostgresConfig(statement_timeout_s=stored)
        await _invoke(
            _ctx(port=port, config=config), "postgres_run_query", {"sql": "SELECT 1"}
        )
        assert port.calls[0]["timeout_s"] == forwarded
