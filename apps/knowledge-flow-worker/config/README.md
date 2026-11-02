# Knowledge Flow worker configuration

The worker has its own configuration and generated schema. `configuration.yaml`
and `configuration_worker.yaml` provide the local processor settings; neither
supplies deployment-specific `manager_processing` endpoints or credentials.
Choose a configuration with `CONFIG_FILE`, and environment references with
`ENV_FILE`. Copy `.env.template` locally and supply the required values.

Configure Temporal, outgoing workload identity, the immutable artifact bucket,
and OpenSearch/pgvector under `manager_processing`. The API reader must use the
same corpus and query embedding model. Use the [processing overlay](../../../deploy/charts/fred/examples/document-processing.yaml)
and [k3d contract export](../../../deploy/k3d/README.md) for the deployment setup.
The API’s HTTP security, published reads and reranker settings are independent.
E0 PostgreSQL roles and grants are unchanged by this split.

From `apps/knowledge-flow-worker`, `make run` starts the worker. For separate
processes, use `make run-worker-role ROLE=common`, then `fast`, `medium`, `rich`.
The role target derives configuration from `config/configuration_worker.yaml`
under `target/worker-roles/` and uses metrics ports 9112–9115. These run targets
prepare dependencies and ingestion models; they have not been executed for E1.

Workers write CSV/Excel Parquet artifacts and `metadata.json` with the existing
schema. Control Plane owns publication; the API resolves and reads the published
generation. No KF relational catalog or migration command is added.

## Ingestion timeouts and retries

Set these under `processing.profiles.fast`, `.medium` or `.rich` in the worker
configuration and re-export the contract to Control Plane; existing runs
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
indexing activity. Trusted maintenance paths are excluded. Invalid enabled configuration prevents worker startup.

From `apps/knowledge-flow-worker`, start the worker with:

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
  per-attempt timeout. For example, set the worker profile's
  `input_activity_timeout: 2m`, re-export its processing contract to Control Plane, then submit a
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
