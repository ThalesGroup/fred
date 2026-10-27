# Sources and provenance

This is an original Fred procedure, distributed under the repository's
Apache-2.0 license. No third-party skill or restricted spreadsheet resource is
copied into this directory.

Consulted on 2026-10-27:

- [DuckDB aggregate functions](https://duckdb.org/docs/stable/sql/functions/aggregates):
  row counts and non-null counts differ; aggregation has defined missing-value
  and empty-group semantics. The procedure requests checks instead of assuming
  missing observations are zero.
- [DuckDB grouping](https://duckdb.org/docs/stable/sql/query_syntax/groupby):
  grouping determines the grain at which results are aggregated.

Fred's existing MCP tabular capability owns discovery, schema, query-alias and
read-only SQL rules. This skill adds an analysis workflow and does not replace
or duplicate those access instructions. Actual tools and permissions are
determined by the current agent request.
