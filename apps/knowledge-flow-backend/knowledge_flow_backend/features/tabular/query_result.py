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

"""Consume SQL previews without retaining data beyond the model context budget."""

from dataclasses import dataclass

import duckdb
from pydantic import TypeAdapter

from knowledge_flow_backend.features.tabular.execution import DuckDBAbortHandle
from knowledge_flow_backend.features.tabular.utils import dataframe_to_records

_ROW_JSON = TypeAdapter(dict[str, object])
_CONTEXT_NOTICE = "The data volume was limited to avoid saturating the model context. Use more targeted queries to retrieve additional relevant data."


@dataclass(frozen=True)
class QueryPreview:
    rows: list[dict]
    matched_rows: int | None
    row_limit: int | None
    chars_truncated: bool

    @property
    def truncated(self) -> bool:
        return self.chars_truncated or (self.row_limit is not None and self.matched_rows is not None and self.matched_rows > self.row_limit)

    @property
    def message(self) -> str | None:
        returned = len(self.rows)
        if self.chars_truncated:
            message = f"{returned} rows were returned. Additional rows were omitted."
            if not self.rows:
                message += " The first row exceeds the character budget. Select fewer columns or shorten large fields."
            return f"{message} {_CONTEXT_NOTICE}"
        if self.truncated:
            return f"{returned} rows were returned. The result is truncated at the requested row limit; additional rows match the query. Use SQL aggregates for totals."
        if not self.rows:
            return "Query executed successfully: 0 rows matched the conditions."
        return None


def read_query_preview(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    *,
    row_limit: int | None,
    max_output_chars: int,
    handle: DuckDBAbortHandle,
) -> QueryPreview:
    # Even empty JSON objects need 3 characters per row plus one.
    # One extra row proves overflow without materializing unlimited SQL.
    execution_rows = (max_output_chars - 1) // 3 + 1
    if row_limit is not None:
        execution_rows = min(row_limit + 1, execution_rows)
    handle.raise_if_aborted()
    cursor = connection.execute(f"SELECT * FROM ({sql}) AS fred_result LIMIT {execution_rows}")  # nosec B608 - validated read-only SQL; integer-only wrapper limit.
    rows: list[dict] = []
    matched_rows = 0
    output_chars = 2  # JSON array delimiters.
    while True:
        handle.raise_if_aborted()
        # One DuckDB vector per batch preserves existing DataFrame value conversion.
        frame = cursor.fetch_df_chunk(1)
        if frame.empty:
            break
        for row in dataframe_to_records(frame):
            handle.raise_if_aborted()
            matched_rows += 1
            # One extra row proves a partial result, including at an exact boundary.
            if row_limit is not None and matched_rows > row_limit:
                return QueryPreview(rows, matched_rows, row_limit, False)
            row_chars = len(_ROW_JSON.dump_json(row).decode("utf-8")) + bool(rows)
            if output_chars + row_chars > max_output_chars:
                return QueryPreview(rows, None, row_limit, True)
            rows.append(row)
            output_chars += row_chars
    return QueryPreview(rows, matched_rows, row_limit, False)
