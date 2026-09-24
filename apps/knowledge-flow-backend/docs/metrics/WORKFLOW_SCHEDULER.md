# Ingestion metrics: what is available

For worker roles and bottleneck examples, see [INGESTION.md](../../../../docs/swift/design/INGESTION.md).
This page describes current instrumentation, not a completed per-profile dashboard.

## Metrics and coverage

| KPI name | Meaning | Current coverage / limitation |
| --- | --- | --- |
| `temporal.system.activity_queue_wait_ms` | `started_time - scheduled_time`, in milliseconds | Called by push/pull metadata activities only; no extraction/indexing queue-wait emission yet |
| `temporal.system.activity_duration_ms` | Elapsed time until an instrumented activity outcome | Metadata, extraction and output call sites; not a complete document end-to-end duration |
| `temporal.ingestion.documents_total` | One count per instrumented activity outcome | Counts stages/attempts, **not unique documents** |
| `temporal.ingestion.workflows_total` | Helper for recording workflow status | Helper and unit test exist, but no production caller currently wires it into the pipeline |

Helpers emit only inside a Temporal activity. Emission failures are logged and do
not fail ingestion. Metadata coverage is not symmetric across every failure path;
absence of a sample is not evidence that an operation did not run or fail.

## KPI dimensions are not necessarily Prometheus labels

The helpers attach `phase`, `activity_type`, `task_queue`, `workflow_type` and
`attempt`. Activity outcomes also attach `status`, `error_code`, `file_type`,
`source_type` and `source_tag`. Structured KPI stores can retain these dimensions.

The Prometheus exporter uses an explicit allow-list. Among those dimensions,
**only `status`, `error_code` and `file_type` are currently allowed**.
In particular, `phase`, `task_queue`, `activity_type`, `workflow_type` and `attempt`
are dropped. Do not build a dashboard assuming these labels exist. Separate scrape
target labels may identify workers if the scrape configuration supplies them.

Prometheus replaces dots in metric names with underscores. Timers are histogram
families (`_bucket`, `_sum`, `_count`); values remain in milliseconds.
`rate(_sum) / rate(_count)` gives a mean over the same window and label selection.
Bucket quantiles are useful only if the configured buckets cover ingestion durations.

## Interpretation traps

- Queue wait is observed **when an activity starts**. A queue with no consumer
  emits no new observations; inspect Temporal queue/consumer state as well.
- Activity duration includes work around the extractor, such as restoring input
  and saving output. It is not pure PDF conversion time.
- Retries contribute additional activity outcomes. Do not sum the document counter
  across stages/attempts and present the result as the number of ingested files.
- A Completed parent workflow can contain failed documents. Use its result tally
  and Fred's document tasks for the business outcome.
- Per-image OCR/VLM timers currently do not emit from the spawned extraction child.
  Parent-process CPU/RAM alone also misses the heavy child: measure the full pod/process tree.

## Implementation references

- [KPI helpers](../../knowledge_flow_backend/features/scheduler/kpi_utils.py)
- [Prometheus label policy](../../../../libs/fred-core/fred_core/kpi/prometheus_kpi_store.py)
- [Remaining observability work](../../../../openspec/changes/isolate-ingestion-extraction-queues/tasks.md)
