# Legacy SQL-Backed Tabular Store

This page describes the historical tabular mode where ingested CSV/Excel data is persisted as SQL tables through
`storage.tabular_stores`.

## Status

This mode is legacy.

Use it only when you must preserve compatibility with an older deployment or caller that still expects persistent SQL
tables.

For new work, prefer [Parquet Object Store + DuckDB](./PARQUET_OBJECT_STORE_DUCKDB.md).

## What It Is

In this mode:

- tabular ingestion normalizes the file into a pandas `DataFrame`
- the output processor writes the resulting rows into a SQL table
- the table lives in a configured backend such as DuckDB, SQLite, or PostgreSQL
- reads happen against that persistent SQL backend

This is supported through:

- `knowledge-flow-backend/knowledge_flow_backend/application_context.py`
- `knowledge-flow-backend/knowledge_flow_backend/core/processors/output/tabular_processor/tabular_processor.py`
- `fred-core/fred_core/store/sql_store.py`

## Configuration

The legacy mode is enabled through `storage.tabular_stores`.

Illustrative example:

```yaml
storage:
  tabular_stores:
    base_database:
      type: "sql"
      driver: "postgresql+psycopg2"
      mode: "read_and_write"
      host: "localhost"
      port: 5432
      database: "data"
      path: null
      username: "tabular"
```

The newer top-level `tabular` block must not be declared at the same time.

## Ingestion Process

When a tabular file is ingested in legacy mode, `TabularProcessor.process(...)` does the following:

1. detect that the file is handled by a tabular input processor
2. parse the extracted CSV content into a pandas `DataFrame`
3. sanitize column names
4. detect likely datetime columns and coerce them
5. compute the row count
6. resolve the writable legacy SQL store through `ApplicationContext.get_csv_input_store()`
7. derive a safe SQL table name from the document name
8. write the `DataFrame` into the target SQL backend
9. remove any stale dataset-centric `tabular_v1` artifact metadata from the document
10. mark `ProcessingStage.SQL_INDEXED` as done

In this mode, the tabular result is a persistent SQL table, not a Parquet artifact in object storage.

## Strengths

- simple compatibility path for callers expecting durable SQL tables
- works with file-based engines or remote relational databases
- easy to inspect manually with external SQL tools

## Limits

- not the preferred security model for document-scoped access
- harder to keep strict segregation between teams when many datasets share one backend
- not the main runtime used by current dataset-centric tabular MCP flows
- does not provide the same clean ReBAC alignment as the document-scoped Parquet runtime

## When To Use It

Use this mode only if at least one of the following is true:

- an older deployment already depends on `storage.tabular_stores`
- an external integration explicitly expects durable SQL tables
- migrating to the dataset-centric mode is not yet possible operationally

Otherwise, use [Parquet Object Store + DuckDB](./PARQUET_OBJECT_STORE_DUCKDB.md).
