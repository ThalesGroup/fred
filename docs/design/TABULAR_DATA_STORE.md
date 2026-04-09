# Tabular Data Store

This page is the entry point for Fred tabular data storage and query design.

Fred currently supports two tabular modes:

1. Recommended mode: one Parquet artifact per document in object storage, queried on demand with DuckDB.
2. Legacy mode: persistent SQL tables behind `storage.tabular_stores`.

Use the dedicated design pages below:

- [Parquet Object Store + DuckDB](./tabular_data_store/PARQUET_OBJECT_STORE_DUCKDB.md)
- [Legacy SQL Store](./tabular_data_store/SQL_STORE.md)

Guidance:

- Prefer the Parquet + object-storage + DuckDB mode for new work.
- Use the legacy SQL-store mode only to preserve older deployments or integrations.
- The recommended mode is the one that aligns tabular access with document-level ReBAC and team/library scoping.
