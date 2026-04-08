# Configuration Guide for Knowledge Flow Backend

This folder contains all the configuration files needed to run the Knowledge Flow backend in different environments.

## TL;DR – Which file do I use?

| Config File                  | Purpose                                                                 |
|-----------------------------|-------------------------------------------------------------------------|
| `configuration_dev.yaml`    | ✅ Default: local dev mode, in-memory vector store, local disk storage. |
| `configuration_postgres.yaml` | 📦 Persistent without OpenSearch: PostgreSQL (incl. `pgvector`) for metadata + vectors, local/minio for files. |
| `configuration_prod.yaml`   | 🛠️ Production-style: uses MinIO + OpenSearch. Requires Docker Compose.  |
| `configuration_worker.yaml` | ⚙️ Worker mode: runs **only** as a Temporal worker (no FastAPI).        |
| `configuration.yaml`        | 🔁 Default entrypoint. Aliased to `configuration_dev.yaml`.             |

---

## Details

### `configuration_dev.yaml`

- Default for local development.
- Uses in-memory vector store and local file storage.
- **No data persistence** — restarting the app will wipe everything.

> Good for quick tests, debugging, and development without external dependencies.

---

### `configuration_prod.yaml`

- Production-style configuration.
- Uses:
  - 🗃️ **MinIO** for file storage.
  - 🔍 **OpenSearch** for metadata and vector index.
- Requires Docker Compose (or external services) to be running.
- Recommended for more realistic tests and production deployments.

---

### `configuration_postgres.yaml`

- Production-like persistence **without** OpenSearch.
- Uses:
  - 🗄️ **PostgreSQL + pgvector** for metadata and vector index.
  - 📂 Local filesystem by default for file storage (can be pointed to MinIO/S3 if desired).
- Good for teams that want to avoid OpenSearch while keeping durable storage.

---

### `configuration_worker.yaml`

- Runs the backend as a **Temporal worker** only.
- No FastAPI server.
- Use this when running the ingestion workers separately from the API.

---

### `configuration.yaml`

- Default entrypoint used by the app.
- Just an alias — by default it points to `configuration_dev.yaml`, but you can switch it.

---

## Environment Variables

Environment-specific secrets and credentials are **not hardcoded** in these files.

- Use `.env` to set environment variables.
- A sample is provided in `.env.template` — copy it to `.env` and fill in the required values.

```bash
cp .env.template .env
```

You'll need to provide values for:

- LLM API keys / tokens
- Access credentials for PostgreSQL (and optionally MinIO, OpenSearch, Temporal, etc.)

---

## Tabular SQL Storage Modes

Knowledge Flow supports two ways to expose tabular data through SQL:

| Mode | Main config | Stores data in | Query engine | Status |
|------|-------------|----------------|--------------|--------|
| Dataset-centric runtime | `content_storage` + top-level `tabular` | Versioned Parquet artifacts | DuckDB | Recommended |
| SQL-backed tabular store | `storage.tabular_stores` | Persistent SQL tables | The backing SQL store | Legacy compatibility |

### Recommended mode: dataset-centric runtime

- CSV ingestion writes one versioned Parquet artifact per document into the shared `content_storage`.
- Read-only SQL queries run in ephemeral DuckDB sessions against the datasets authorized for the current user.
- This is the mode used by the current repository configuration files and Helm values.
- When neither `tabular` nor `storage.tabular_stores` is declared, Knowledge Flow enables this mode with the built-in defaults.

The two configuration blocks that matter are:

- `content_storage`
  - Chooses where raw files and tabular Parquet artifacts are stored.
  - `local` works for zero-dependency local development.
  - `minio`/S3-compatible backends are used when you want shared object storage.
- `tabular`
  - Tunes tabular artifact layout and query limits.
  - Does not define a separate SQL backend.

Example:

```yaml
content_storage:
  type: local
  root_path: ".fred/data/content"

tabular:
  artifacts_prefix: "tabular/datasets"
  format: "parquet"
  compression: "snappy"
  query:
    engine: "duckdb"
    access_mode: "presigned_url"
    presigned_ttl_seconds: 900
    default_max_rows: 200
    max_rows: 1000
```

Behavior by storage backend:

- `content_storage.type = local`
  - DuckDB reads Parquet artifacts directly from disk.
- `content_storage.type = minio`
  - Knowledge Flow generates short-lived presigned URLs and DuckDB reads them through `httpfs`.
  - The runtime image should ship DuckDB `httpfs` for offline/containerized deployments.

### Legacy mode: SQL-backed tabular stores

- `storage.tabular_stores` remains supported for older deployments that still expect the historical SQL-table contract.
- This mode persists normalized tabular data into SQL tables instead of Parquet artifacts.
- It can target local file-backed engines such as DuckDB/SQLite or remote engines such as PostgreSQL/MySQL/MariaDB.
- Use it only when you must preserve an older integration or user workflow.
- This mode is exclusive with the top-level `tabular` block: when `storage.tabular_stores` is present, dataset-centric defaults are not injected and `TabularProcessor` writes SQL tables again.

Illustrative snippet:

```yaml
tabular_stores:
  base_database:
    type: "sql"
    mode: "read_and_write"
    driver: "postgresql+psycopg2"
    host: "localhost"
    port: 5432
    database: "data"
    path: null
    username: "fred"

```

Guidance:

- Prefer `content_storage` + `tabular` for new deployments and new features.
- Keep `storage.tabular_stores` only to avoid breaking older callers that still rely on persistent SQL tables.

---

## Tips

- To run in **dev mode**, nothing external is needed — just launch the app.
- To run in **prod mode**, make sure you start the required services (e.g., via `docker-compose up`).
- To run the **worker**, use the appropriate entrypoint and make sure Temporal is reachable.

---
