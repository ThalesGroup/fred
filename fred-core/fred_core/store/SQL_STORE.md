# SQL Table Store Configuration

> ⚠️ Legacy notice
>
> This document describes the legacy SQL-backed tabular mode kept for backward compatibility.
>
> For new work, prefer the dataset-centric tabular runtime based on Parquet artifacts in `content_storage` queried with
> DuckDB. That newer mode is the recommended path because it aligns tabular access with document-level ReBAC and avoids
> exposing one shared persistent SQL catalog across teams.
>
> See:
>
> - `docs/design/TABULAR_DATA_STORE.md`
> - `docs/design/tabular_data_store/SQL_STORE.md`
> - `docs/design/tabular_data_store/PARQUET_OBJECT_STORE_DUCKDB.md`

## 🚀 Introduction

This module provides SQL support for `tabular_store`, allowing you to connect seamlessly to local or server-based
databases. Configuration is handled via a YAML file, with optional secure credential loading from a `.env` file.

---

## ⚙️ Supported Databases

- ✅ DuckDB (local file-based)
- ✅ SQLite (local file-based)
- ✅ PostgreSQL
- ✅ MySQL / MariaDB

The system builds the connection string (DSN) automatically based on the provided configuration.

---

## 📁 Example Configuration (`config.yaml`)

### 🔹 DuckDB (local)

```yaml
tabular_stores:
  type: "sql"
  driver: "duckdb"
  path: "~/.fred/knowledge-flow/db.duckdb"
```

### 🔹 PostgreSQL (remote)

```yaml
tabular_stores:
  base_database:
    type: "sql"
    driver: "postgresql+psycopg2"
    host: "localhost"
    port: 5433
    database: "test_db_postgre_sql"

    # These override the values from the .env file if set
    username: "my_username"     # pragma: allowlist secret
    password: "my_password"     # pragma: allowlist secret
```

## 🔐 Credential Management (.env)

You can define environment-based credentials using a `.env` file at the project root:

```env
SQL_USERNAME=admin
TABULAR_POSTGRES_PASSWORD=secret123
```

If both the YAML file and `.env` define username or password, the YAML value takes precedence.

## 🔌 Supported Drivers

| Database | driver value |
|----------|--------------|
| DuckDB | duckdb |
| SQLite | sqlite |
| PostgreSQL | postgresql+psycopg2 |
| MySQL/MariaDB | mysql+pymysql |

Ensure the driver is installed and supported by SQLAlchemy.

## ✅ Connection Logs

When a connection is established, you will see a message like:

```bash
✅ Successfully connected to the SQL database: test_db_postgre_sql
```

For debugging, host and driver info can also be printed if needed.

## 🧾 Best Practices

1. Never commit `.env` files containing secrets.
1. Use `path` only for file-based databases (DuckDB/SQLite).
1. Use `host`, `port`, `database`, `username`, `password` for server databases.
1. The `driver` field must match a valid SQLAlchemy dialect+driver combination.

## Next

- Keep this mode only for older deployments that still depend on persistent SQL tables.
- Prefer the new dataset-centric tabular mode for any feature that must respect ReBAC and data segregation by access
  rights.
