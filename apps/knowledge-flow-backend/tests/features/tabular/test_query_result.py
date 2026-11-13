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

"""Character budgets are enforced against complete, serialized DuckDB rows."""

import asyncio
import json

import duckdb
import pytest

from knowledge_flow_backend.common.structures import TabularQueryConfig
from knowledge_flow_backend.features.tabular.execution import DuckDBAbortHandle, _AbortRequested, close_duckdb_connection, open_duckdb_connection, reset_execution_state_for_tests, run_duckdb_job
from knowledge_flow_backend.features.tabular.query_result import read_query_preview
from knowledge_flow_backend.features.tabular.structures import RawSQLResponse


def _preview(sql, *, limit=None, budget=50000, handle=None):
    with duckdb.connect(config={"threads": 1}) as connection:
        return read_query_preview(connection, sql, row_limit=limit, max_output_chars=budget, handle=handle or DuckDBAbortHandle())


def test_exact_serialized_boundary_with_unicode_escaping_and_typed_values():
    sql = "SELECT 'é😊' AS label, chr(10) || chr(34) || chr(92) AS escaped, CAST('2026-01-02' AS DATE) AS day, CAST(12.50 AS DECIMAL(9,2)) AS amount, NULL AS missing, false AS active"
    complete = _preview(sql)
    serialized = json.loads(RawSQLResponse(sql_query=sql, rows=complete.rows).model_dump_json())["rows"]
    budget = len(json.dumps(serialized, ensure_ascii=False, separators=(",", ":")))
    assert _preview(sql, budget=budget).rows == complete.rows
    assert _preview(sql, budget=budget).message is None
    too_small = _preview(sql, budget=budget - 1)
    assert too_small.rows == []
    assert "first row exceeds" in too_small.message


def test_unlimited_execution_is_bounded_before_fetching():
    observed = []
    with duckdb.connect(config={"threads": 1}) as connection:
        connection.create_function("observe", lambda i: observed.append(i) or i, ["BIGINT"], "BIGINT", side_effects=True)
        result = read_query_preview(connection, "SELECT observe(i) AS id FROM range(1000000) t(i)", row_limit=None, max_output_chars=100, handle=DuckDBAbortHandle())
    assert result.chars_truncated
    assert result.matched_rows is None
    assert len(observed) <= 4096  # A bounded execution vector, never the million-row result.
    assert len(json.dumps(result.rows, separators=(",", ":"))) <= 100


def test_explicit_sql_limit_and_empty_result_remain_complete():
    result = _preview("SELECT * FROM range(10000) LIMIT 3")
    assert len(result.rows) == 3
    assert result.message is None
    empty = _preview("SELECT 1 WHERE false")
    assert empty.message == "Query executed successfully: 0 rows matched the conditions."


def test_aborted_preview_does_not_start_execution():
    handle = DuckDBAbortHandle()
    handle.request_abort()
    with pytest.raises(_AbortRequested):
        _preview("SELECT 1", handle=handle)


@pytest.mark.asyncio
async def test_concurrent_unlimited_previews_stay_isolated_and_bounded():
    reset_execution_state_for_tests()
    config = TabularQueryConfig(max_concurrent_queries=2, max_queued_queries=6)

    def job(handle, marker):
        connection = open_duckdb_connection(handle, config=config)
        try:
            return read_query_preview(connection, f"SELECT {marker} AS marker, i AS id FROM range(1000000) t(i)", row_limit=None, max_output_chars=500, handle=handle)
        finally:
            close_duckdb_connection(handle, connection)

    try:
        results = await asyncio.gather(*(run_duckdb_job(lambda handle, marker=marker: job(handle, marker), config=config, operation="query") for marker in range(6)))
        for marker, result in enumerate(results):
            assert result.chars_truncated
            assert all(row["marker"] == marker for row in result.rows)
            assert len(json.dumps(result.rows, ensure_ascii=False, separators=(",", ":"))) <= 500
    finally:
        reset_execution_state_for_tests()
