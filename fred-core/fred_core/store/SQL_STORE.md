# SQL Table Store Configuration

## 🚀 Introduction

This module provides SQL support for `tabular_store`, allowing you to connect seamlessly to local or server-based databases. Configuration is handled via a YAML file, with optional secure credential loading from a `.env` file.

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
tabular_store:
  type: "sql"
  driver: "duckdb"
  path: "~/.fred/knowledge-flow/db.duckdb"
```


### 🔹 PostgreSQL (remote)

```yaml
tabular_store:
  type: "sql"
  driver: "postgresql+psycopg2"
  host: "localhost"
  port: 5433
  database: "test_db_postgre_sql"

  # These override the values from the .env file if set
  username: "my_username"     # pragma: allowlist secret
  password: "my_password"     # pragma: allowlist secret
```
```

## 🔐 Credential Management (.env)
You can define environment-based credentials using a .env file at the project root:

```env
SQL_USERNAME=admin
TABULAR_POSTGRES_PASSWORD=secret123
```
If both the YAML file and .env define username or password, **the YAML value takes precedence.**

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

✅ Use host, port, database, username, password for server databases.

✅ The driver field must match a valid SQLAlchemy dialect+driver combination.

# Next

- Update the CSV processing pipeline to save the processed data to a separate database from the one loaded.


