# Tabular Data Store

This page is the entry point for Fred tabular data storage and query design.

Fred now supports one tabular runtime:

1. One Parquet artifact per document in object storage, queried on demand with DuckDB.

Use the dedicated design pages below:

- [Parquet Object Store + DuckDB](./tabular_data_store/PARQUET_OBJECT_STORE_DUCKDB.md)

Guidance:

- Prefer the Parquet + object-storage + DuckDB runtime for all new work and deployments.
- The runtime aligns tabular access with document-level ReBAC and team/library scoping.
