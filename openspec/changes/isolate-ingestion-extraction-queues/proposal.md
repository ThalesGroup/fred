## Why

Every ingestion workflow runs on the single queue named by
`scheduler.temporal.task_queue`, so the same worker pods serve all three
processing profiles. A `rich` document holds an activity slot for a long time
and its CPU and memory footprint is large; with
`ingestion_max_concurrent_activities: 3` one pod can run three of them at once.
A `fast` or `medium` document that lands on that pod waits behind them, or dies
with them when the pod runs out of memory. Cheap ingestions are hostage to
expensive ones purely because they share a worker process.

Slowing `rich` down is acceptable. Letting it block or evict `medium` is not.

Tracked by GitHub issue #2762.

## What Changes

Delivered as one pull request in three commits, one per batch. Only batch 1 is
implemented at this point.

### Batch 1 — isolate extraction by profile (implemented)

- Route the two extraction activities, `push_input_process` and
  `pull_input_process`, to a per-profile Temporal queue derived from the base
  queue. Every workflow, including the per-file sub-workflows, and every other
  activity stay on the common queue.
- Give the worker program a role: the common role registers every workflow and
  every activity but extraction; an extraction role registers nothing but the
  two extraction activities and polls its profile's queue.
- Configure four worker deployments in the Helm chart, one per role, with their
  own replica count, resources and activity concurrency. A `rich` pod runs one
  extraction at a time. They share their Temporal connection, base queue,
  storage and image through render-time inheritance, so a values override of one
  reaches all four, and the chart refuses to render when the enabled workers
  leave a role unserved.
- Accept submissions that mix profiles: routing is per document, so nothing has
  to be refused. Validations unrelated to routing are unchanged.
- Log the role, the queue polled and the effective concurrency at worker start.

### Batch 2 — document robustness and independence (not implemented)

- Bounded document admission so `fast` documents do not wait behind `rich` ones
  inside a batch.
- Execution deadlines matched to each stage.
- Heartbeats and bounded retries.
- Idempotence of replayed operations.
- Cancellation that actually stops computation.
- Coherent terminal states on failure and on cancellation.

### Batch 3 — observability and load validation (not implemented)

- Explicit separation of waiting from running for each major stage.
- KPIs per queue, stage and profile.
- A dashboard that locates a blockage.
- CPU and memory measurements, restarts and OOM counts.
- A reproducible local campaign with representative documents.
- Initial sizing derived from those measurements, replacing the starting
  hypotheses this batch commits.
- Operating documentation and final OpenSpec artifacts.

## Capabilities

### New Capabilities

- `ingestion-extraction-routing`: how a document's processing profile decides
  which Temporal queue and which worker pods run its extraction, and what each
  worker role registers.

### Modified Capabilities

None.

## Impact

- Affected code: `knowledge_flow_backend/common/structures.py`,
  `features/scheduler/{scheduler_structures,scheduler_service,workflow,worker}.py`,
  `main_worker.py`.
- Affected deployment: `deploy/charts/fred/values.yaml` gains three worker
  deployments beside the existing one; `templates/main.yaml` resolves a new
  generic `inheritFrom` application key and a new template refuses an incomplete
  set of worker roles; `scripts/generate_chart_schema.py`, both generated schemas
  and the k3d overlay follow. A repeatable render check,
  `make check-chart-ingestion-workers`, joins the chart checks in CI.
- No API, no stored data format and no frontend state changes.
- Deployment constraint: in-flight workflows are not supported. A workflow
  already running when the new code is rolled out replays a history that never
  routed extraction, and its extraction activity would target a queue its
  recorded history does not carry. Drain ingestion before rolling out.
