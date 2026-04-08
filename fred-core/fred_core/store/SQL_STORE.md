# Tabular data & SQL Store Configuration

> ⚠️ Important
>
> The current Knowledge Flow tabular runtime defaults to one Parquet artifact per document in `content_storage` plus
> read-only DuckDB queries over authorized datasets.
>
> `storage.tabular_stores` is still accepted as a legacy compatibility contract for older deployments, but new shipped
> configs and Helm values use the dataset-centric `content_storage` + top-level `tabular` settings.

## Where This Fits In Fred

Fred currently supports two tabular data modes that can be queried with SQL:

| Mode | Main config | Storage model | Status |
|------|-------------|---------------|--------|
| Dataset-centric runtime | `content_storage` + top-level `tabular` | Parquet artifacts + DuckDB queries | Recommended |
| SQL-backed tabular store | `storage.tabular_stores` | Persistent SQL tables | Legacy compatibility |

This document is about the second mode only: the generic SQL store helper used by the legacy compatibility path.

## 🚀 Introduction

This helper provides SQL table support for both:

- local file-backed engines such as DuckDB and SQLite
- server-based engines such as PostgreSQL and MySQL/MariaDB.

In Knowledge Flow, that now mainly matters for the legacy `storage.tabular_stores` path, not for the recommended
dataset-centric tabular runtime.

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

| Database	        | driver value          |
|-------------------|-----------------------|  
| DuckDB	        | duckdb                | 
| SQLite	        | sqlite                | 
| PostgreSQL	    | postgresql+psycopg2   | 
| MySQL/MariaDB	    | mysql+pymysql         | 

Ensure the driver is installed and supported by SQLAlchemy.

## ✅ Connection Logs

When a connection is established, you will see a message like:

```bash
✅ Successfully connected to the SQL database: test_db_postgre_sql
```

For debugging, host and driver info can also be printed if needed.

# 🧾 Best Practices
✅ Never commit .env files containing secrets.

✅ Use path only for file-based databases (DuckDB/SQLite).

✅ Use host, port, database, username, password for server databases when your caller builds the remote DSN target.

✅ The driver field must match a valid SQLAlchemy dialect+driver combination.

# Next

- If you are working on Knowledge Flow tabular querying, prefer the dataset-centric Parquet + DuckDB runtime rather than introducing a new persistent tabular SQL database.
