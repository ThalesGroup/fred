# Configuration Guide for Knowledge Flow Backend

This folder contains the Knowledge Flow runtime configurations.
The [ingestion architecture](../../../docs/architecture/A9-documents.md) defines the
worker roles, queue routing and shared-storage requirements.

## Choose the entrypoint

| File | Use |
| --- | --- |
| `configuration.yaml` | Default local API configuration; inspect its actual stores and scheduler before using it for a test |
| `configuration_prod.yaml` | Deployment-style API settings; infrastructure endpoints and credentials must match your environment |
| `configuration_worker.yaml` | Optional dedicated-worker configuration; select explicitly with `CONFIG_FILE` |
| `configuration_test.yaml` | Test configuration |

Workers require Temporal and `manager_processing`; Control Plane dispatches every job.
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
- PostgreSQL/OpenSearch credentials, the worker workload identity and S3 artifact credentials

---

## Tabular Data Runtime

Workers convert CSV and Excel into attempt-local Parquet artifacts through
`LocalTabularArtifacts`. `manager_processing` publishes immutable generations to
S3; Control Plane owns their publication. The API uses `published_artifacts` to
read the published generation after SQL scope and visibility checks.

`storage.tabular_store` controls Parquet compression, pointer chunks and DuckDB
query limits. `query.internal_presigned_ttl_seconds` bounds the lifetime of
backend-internal S3 URLs; clients never receive those URLs.

Only OpenSearch and pgvector are supported vector projections. API
`storage.vector_store` and worker `manager_processing.vector_store` must refer to
the same corpus. Configure workload credentials and S3 coordinates as shown in
[the processing overlay](../../../deploy/charts/fred/examples/document-processing.yaml).
KF owns no relational catalog and has no database migration command.

## Start locally

- Start the infrastructure required by your selected configuration first.
- API: `make run`, or `CONFIG_FILE=/path/to/config.yaml make run` to select a configuration.
- Local mode may still need authentication services and remote model access; inspect the configuration rather than assuming an infrastructure-free setup.
- Set environment-specific `manager_processing` settings before starting a worker (see `deploy/charts/fred/examples/document-processing.yaml`); the base YAML files do not supply workload credentials or deployment endpoints.
- `make run-worker` uses the same `CONFIG_FILE` selection as the API (including `config/.env`), with a separate local metrics port (`KF_WORKER_METRICS_PORT=9112`). It starts one process; with the default `scheduler.worker_roles`, it serves all four ingestion roles.
- For separate processes, run `make run-worker-role ROLE=common`, then the same command with `fast`, `medium` and `rich`. Role configurations are derived under `target/worker-roles/`; metrics ports are 9112–9115.
- These commands may prepare dependencies and download missing models. Docker Compose supplies infrastructure, not the worker processes started by these commands.
- Match the Control Plane Temporal namespace/base queue and the worker corpus and artifact store.

---

## Ingestion timeouts and retries

Set these under `processing.profiles.fast`, `.medium` or `.rich` in the **API's**
configuration. The API snapshots them when submitting a document; existing runs
keep their original policy. These settings apply to the Temporal scheduler.

| Field | Default | Meaning |
| --- | --- | --- |
| `push_metadata_activity_timeout` | `5m` | Uploaded-document metadata lookup, per attempt |
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

## Manual fault injection for ingestion

These hooks are disabled unless `FRED_INGESTION_FAULT` is set on the worker.
They only run inside the Temporal push extraction activity and the normal
indexing activity. Direct API/in-memory processing and trusted maintenance are
excluded. Invalid enabled configuration prevents worker startup.

From `apps/knowledge-flow-backend`, start the worker with:

```bash
FRED_INGESTION_FAULT=activity_error \
FRED_INGESTION_FAULT_STAGE=extraction \
FRED_INGESTION_FAULT_FILE=demo-failure.pdf \
FRED_INGESTION_FAULT_DELAY_SECONDS=180 \
FRED_INGESTION_FAULT_ATTEMPTS=1 \
make run-worker
```

Then upload **demo-failure.pdf** through the UI. At the extraction hook, the first
attempt waits three minutes with heartbeats, then raises a retryable
`SimulatedIngestionFailure`. Later attempts run normally, subject to the profile's
retry policy. The activity's configured timeout must leave enough time for this
wait, otherwise a real timeout occurs before the simulated error.

| Variable | Values / behavior |
| --- | --- |
| `FRED_INGESTION_FAULT` | `activity_error`, `non_retryable_error`, `worker_crash`, `delay`; unset/empty disables injection |
| `FRED_INGESTION_FAULT_STAGE` | Required: `extraction` or `indexing` |
| `FRED_INGESTION_FAULT_FILE` | Required: exact original document filename, case-sensitive, no directory or wildcard matching |
| `FRED_INGESTION_FAULT_DELAY_SECONDS` | Seconds to wait at the hook, default `0` |
| `FRED_INGESTION_FAULT_ATTEMPTS` | Temporal activity attempt numbers, e.g. `1` (default), `1,2`, or `all` |

Change only the mode/selector to exercise these cases:

- **Transient failure then recovery:** `activity_error`, attempts `1`.
- **Retry exhaustion:** `activity_error`, attempts `all`; Temporal still applies
  the configured finite maximum number of attempts.
- **Immediate final failure after the wait:** `non_retryable_error`; no retry.
- **Worker loss:** `worker_crash`; exits the worker process abruptly with code 86.
  Restart the worker to let Temporal resume eligible work. With attempts `1`, the
  next attempt passes the hook even after restart. Other activities in the same
  process are interrupted too; a single local worker may serve all four roles.
- **Real execution timeout:** `delay`, with a wait longer than the configured
  per-attempt timeout. For example, set the API profile's
  `input_activity_timeout: 2m`, restart/reload the API configuration, submit a
  **new** extraction with a `180` second injected wait. Existing submissions keep
  their original policy. The hook keeps heartbeating (normally every five seconds),
  so keep the heartbeat timeout above that cadence to isolate execution timeout.
  If the wait completes first, `delay` simply continues normal processing.

The wait begins when the hook is reached, not when the upload is submitted.
Extraction pauses **before spawning its child**, indexing **before processing any
output batches**. These scenarios do not test orphaned running extractors or
partially written indexes. Filename selection matches every document with that
name; use a distinct test filename. Attempt numbers belong to each activity,
not a process-local counter; a new ingestion starts again at attempt 1.

Run the configured worker on the targeted stage's queue. With multiple replicas,
a hook applies only when an equipped worker receives the activity; configure all
consumers of that test queue for repeatable results. Startup and trigger logs carry
`[SIMULATED INGESTION FAULT]`. Activity failures explicitly say they are simulated;
a process crash is observed as worker loss/timeout, not a returned application error.
Stop that worker and relaunch without these variables to disable the hooks. Keep
this configuration in the test launch command rather than shared deployment YAML.
