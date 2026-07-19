# Configuration Guide for Knowledge Flow Backend

This folder contains all the configuration files needed to run the Knowledge Flow backend in different environments.

## TL;DR – Which file do I use?

Two run-time profiles only — no other variant is maintained:

| Config File                 | Purpose                                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------------------- |
| `configuration.yaml`         | ✅ Standalone dev mode: SQLite/local storage, Chroma in-process vector store. No external services required. |
| `configuration_prod.yaml`    | 🛠️ Deployment-representative: PostgreSQL, MinIO, OpenSearch (metadata, vectors, KPI/logs). Requires Docker Compose (or equivalent) to be running. |

Two more files exist for other processes, not as alternate ways to run the API server:

| Config File                  | Purpose                                                              |
| ----------------------------- | --------------------------------------------------------------------- |
| `configuration_test.yaml`    | Used by the pytest suite (`make test`) — infrastructure-free.        |
| `configuration_worker.yaml`  | Runs the backend as a **Temporal worker** only, no FastAPI server.   |

---

## Details

### `configuration.yaml`

- Default for local development.
- Uses local disk storage and an in-process Chroma vector store.
- **No data persistence** — restarting the app will wipe everything.

> Good for quick tests, debugging, and development without external dependencies.

---

### `configuration_prod.yaml`

- Deployment-representative configuration.
- Uses:
  - 🗄️ **PostgreSQL** for metadata/resources/tags.
  - 🗃️ **MinIO** for file storage.
  - 🔍 **OpenSearch** for the vector index, KPI, and (when `storage.log_store.type: opensearch`) generic application logs.
- Requires Docker Compose (or external services) to be running.
- Recommended for realistic local tests before a deployment.

---

### `configuration_test.yaml`

- Used exclusively by the pytest suite (`make test`).
- Kept infrastructure-free so tests don't depend on a running stack.

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

## Tabular Data Runtime

Knowledge Flow exposes tabular data through one dataset-centric runtime:

| Runtime                 | Main config                                 | Stores data in              | Query engine | Status      |
| ----------------------- | ------------------------------------------- | --------------------------- | ------------ | ----------- |
| Dataset-centric runtime | `content_storage` + `storage.tabular_store` | Versioned Parquet artifacts | DuckDB       | Recommended |

### Dataset-centric runtime

- CSV ingestion writes one versioned Parquet artifact per document into the shared `content_storage`.
- The primary ingestion path inspects delimiter and encoding once, converts CSV to Parquet directly with DuckDB, and
  reads row count and schema back from the generated Parquet artifact instead of materializing a full pandas
  DataFrame.
- Read-only SQL queries run in ephemeral DuckDB sessions against the datasets authorized for the current user.
- Query validation is dataset-scoped: only read-only `SELECT`/`WITH` statements against authorized mounted datasets are
  allowed.
- This is the mode used by the current repository configuration files and Helm values.
- When `storage.tabular_store` is omitted, Knowledge Flow enables the built-in defaults automatically.

The two configuration blocks that matter are:

- `content_storage`
  - Chooses where raw files and tabular Parquet artifacts are stored.
  - `local` works for zero-dependency local development.
  - `minio`/S3-compatible backends are used when you want shared object storage.
  - For MinIO/S3-compatible deployments, keep `endpoint` on the internal address used by backend pods/workers and use
    `public_endpoint` only for browser-facing links.
- `storage.tabular_store`
  - Tunes artifact layout and query limits for the dataset-centric runtime.
  - `query.internal_presigned_ttl_seconds` controls the lifetime of backend-internal object-storage URLs used by
    DuckDB.

Example:

```yaml
content_storage:
  type: local
  root_path: ".fred/data/content"

storage:
  tabular_store:
    artifacts_prefix: "tabular/datasets"
    format: "parquet"
    compression: "snappy"
    query:
      engine: "duckdb"
      access_mode: "presigned_url"
      internal_presigned_ttl_seconds: 3600
      default_max_rows: 200
      max_rows: 1000
```

Behavior by storage backend:

- `content_storage.type = local`
  - DuckDB reads Parquet artifacts directly from disk.
- `content_storage.type = minio`
  - Knowledge Flow generates short-lived internal presigned URLs and DuckDB reads them through `httpfs`.
  - The runtime image should ship DuckDB `httpfs` for offline/containerized deployments.

Compatibility note:

- `storage.tabular_store.query.presigned_ttl_seconds` is no longer supported.
- Use `storage.tabular_store.query.internal_presigned_ttl_seconds` instead.

Guidance:

- Prefer `content_storage` + `storage.tabular_store` for new deployments and new features.

---

## Tips

- To run in **dev mode**, nothing external is needed — just launch the app.
- To run in **prod mode**, make sure you start the required services (e.g., via `docker-compose up`).
- To run the **worker**, use the appropriate entrypoint and make sure Temporal is reachable.

---
