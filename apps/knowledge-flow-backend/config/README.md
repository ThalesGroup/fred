# Configuration Guide for Knowledge Flow Backend

This folder contains the Knowledge Flow runtime configurations.
The [ingestion architecture](../../../docs/swift/design/INGESTION.md) defines the
worker roles, queue routing and shared-storage requirements.

## Choose the execution mode

| File | Use |
| --- | --- |
| `configuration.yaml` | Default local API configuration; inspect its actual stores and scheduler before using it for a test |
| `configuration_prod.yaml` | Deployment-style API settings; infrastructure endpoints and credentials must match your environment |
| `configuration_worker.yaml` | Configuration used by `make run-worker`; the worker entrypoint starts no API |
| `configuration_test.yaml` | Test configuration |

A filename does not select the execution engine: `scheduler.backend` does.
Local storage/SQLite data can persist across restarts; “local” does not mean disposable.
The default configuration is a real YAML file, not an alias to `configuration_dev.yaml`.

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

## Start locally

- Start the infrastructure required by your selected configuration first.
- API: `make run`, or `CONFIG_FILE=/path/to/config.yaml make run` to select a configuration.
- Local mode may still need authentication services and remote model access; inspect the configuration rather than assuming an infrastructure-free setup.
- `make run-worker` starts one process; with the default `scheduler.worker_roles`, it serves all four ingestion roles.
- For separate processes, run `make run-worker-role ROLE=common`, then the same command with `fast`, `medium` and `rich`. Role configurations are derived under `target/worker-roles/`; metrics ports are 9112–9115.
- These commands may prepare dependencies and download missing models. Docker Compose supplies infrastructure, not the worker processes started by these commands.
- For a Temporal test, the API must also use `scheduler.backend: temporal` and the same namespace, base queue and shared stores as the workers. The standalone memory/local-storage API configuration is not suitable for this test.

---

## Ingestion timeouts and retries

Set these under `processing.profiles.fast`, `.medium` or `.rich` in the **API's**
configuration. The API snapshots them when submitting a document; existing runs
keep their original policy. These settings apply to the Temporal scheduler.

| Field | Default | Meaning |
| --- | --- | --- |
| `push_metadata_activity_timeout` | `5m` | Uploaded-document metadata lookup, per attempt |
| `pull_metadata_activity_timeout` | `30m` | Source download and metadata creation, per attempt |
| `input_activity_timeout` | `1h` | Extraction, per attempt |
| `output_activity_timeout` | `1h` | Indexing, per attempt |
| `activity_heartbeat_timeout` | `5m` | Maximum silence between extraction/indexing heartbeats; can fail an attempt earlier |
| `retry_maximum_attempts` | `6` | Maximum attempts **per stage**, including the first; `1` disables retries |
| `retry_initial_interval` | `30s` | Delay before the first retry |
| `retry_backoff_coefficient` | `2.0` | Multiplier for successive retry delays |
| `retry_maximum_interval` | `10m` | Maximum delay between attempts |
| `retry_non_retryable_error_types` | `[]` | Additional application error types that fail without retry |

Defaults are model defaults; a deployment's YAML may override them. The same
retry policy applies to metadata, extraction and indexing. Progress-event writes
have a separate short internal retry policy. Explicitly non-retryable failures
can end a stage before its attempt count is exhausted.

Example: with a `2m` stage timeout, `3` attempts and retry delays `10s`, `20s`,
that stage has at most `6m30s` of attempt time plus backoff. **This is not a
wall-clock completion guarantee:** queue waiting, workflow scheduling and terminal
event persistence are outside that calculation. There is no overall document
budget; a queue without consumers can wait indefinitely.

Inspect `[INGESTION POLICY]` in common-worker logs for the submitted policy and
Temporal activity history for effective attempts, errors and timeouts. Outcome
logs tagged `[INGESTION ATTEMPT]` supplement that history where instrumented;
a killed worker cannot emit its final log.
