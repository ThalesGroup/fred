 # Temporal metrics exposed by this module

 ## Overview
 This module emits 4 main metrics related to Temporal activities and workflows.

 1. `temporal.system.activity_queue_wait_ms`
 2. `temporal.system.activity_duration_ms`
 3. `temporal.ingestion.documents_total`
 4. `temporal.ingestion.workflows_total`

 These metrics are used to observe:

 - how long an activity task waits in the Temporal queue before a worker starts it
 - how long an activity actually runs
 - how many ingestion documents are processed
 - how many workflows complete, and with what final status

 ## `temporal.system.activity_queue_wait_ms`

 ### Type
 Timer metric, exported as a histogram family in Prometheus, typically with _bucket, _sum, _count, and sometimes _created

 ### What it means
 Measures how long an activity task stayed queued in Temporal before a worker started executing it.

 The value is computed from:

 started_time - scheduled_time

 and emitted in milliseconds.

 ### Why it is useful
 This metric helps detect scheduling delay, worker saturation, queue backlog, or task routing issues.

 If this metric increases, it usually means activities are not being picked up quickly enough by workers.

 ### Emission conditions
 It is emitted only when the code is running inside a Temporal activity.

 ### Dimensions
 - phase: logical ingestion phase, for example metadata
 - activity_type: Temporal activity type
 - task_queue: Temporal task queue name
 - workflow_type: Temporal workflow type, or unknown
 - attempt: activity retry attempt number as a string

 ### Prometheus series you typically get
 - `temporal_system_activity_queue_wait_ms_bucket`
 - `temporal_system_activity_queue_wait_ms_sum`
 - `temporal_system_activity_queue_wait_ms_count`
 - `temporal_system_activity_queue_wait_ms_created`

 ### How to read it
 - `_count` = number of queue wait observations
 - `_sum` = total accumulated wait time in milliseconds
 - `_bucket` = histogram buckets used for percentiles
 - `_created` = metric series creation timestamp

 ## `temporal.system.activity_duration_ms
`
 ### Type
 Timer metric, exported as a histogram family in Prometheus

 ### What it means
 Measures the execution duration of an activity itself.

 The value is computed from:

`time.perf_counter() - started_at_monotonic`

 and emitted in milliseconds.

 This is runtime duration, not queue delay.

 ### Why it is useful
 This metric helps identify slow activities, expensive processing phases, retries with long runtimes, and performance regressions in ingestion steps.

 ### Emission conditions
 It is emitted only when the code is running inside a Temporal activity.

 It is emitted by `emit_temporal_activity_result_kpis(...)`.

 ### Dimensions
 - `phase`: logical ingestion phase
 - `status`: outcome such as success or failure
 - `error_code`: exception class name, or none
 - `activity_type`: Temporal activity type
 - `task_queue`: Temporal task queue name
 - `workflow_type`: Temporal workflow type, or unknown
 - `attempt`: retry attempt number as a string
 - `file_type`: normalized file format such as pdf, docx, txt, or other
 - `source_type`: ingestion mode such as push, pull, or unknown
 - `source_tag`: connector or source identifier, or unknown

 ### Prometheus series you typically get
 - `temporal_system_activity_duration_ms_bucket`
 - `temporal_system_activity_duration_ms_sum`
 - `temporal_system_activity_duration_ms_count`
 - `temporal_system_activity_duration_ms_created`

 ### How to read it
 - use `_sum` / `_count` for average runtime
 - use `_bucket` with histogram_quantile(...) for p50, p95, p99
 - split by `phase`, `status`, `activity_type`, or `task_queue` to find bottlenecks

 ## `temporal.ingestion.documents_total`

 ### Type
 Counter

 ### What it means
 Counts activity-level ingestion document outcomes.

 Despite the name, this counter is incremented whenever `emit_temporal_activity_result_kpis(...)` is called, with the current activity result dimensions attached.

 In practice, it behaves like a count of processed activity results for ingestion documents.

 ### Why it is useful
 This metric helps measure throughput and outcome volume, for example:

 - how many documents were processed
 - how many succeeded
 - how many failed
 - which phase or source generates the most failures

 ### Emission conditions
 It is emitted only when the code is running inside a Temporal activity.

 It is incremented by 1 each time `emit_temporal_activity_result_kpis(...)` runs.

 ### Dimensions
 It uses the same dimensions as `temporal.system.activity_duration_ms`:

 - `phase`
 - `status`
 - `error_code`
 - `activity_type`
 - `task_queue`
 - `workflow_type`
 - `attempt`
 - `file_type`
 - `source_type`
 - `source_tag`

 ### Important interpretation note
 Because this counter is emitted at activity-result level, it may not represent "unique business documents" unless each document maps cleanly to one emitted result in your pipeline.

 If one document goes through multiple activities that each emit this counter, the metric counts activity outcomes, not strictly one unique document.

 ## `temporal.ingestion.workflows_total`

 ### Type
 Counter

 ### What it means
 Counts workflow-level status events for ingestion workflows.

 This metric is intended to signal final or recorded workflow status from the parent workflow perspective.

 ### Why it is useful
 This metric helps distinguish workflow-level outcomes from activity-level outcomes.

 It can answer questions such as:

 - how many workflows completed successfully
 - how many workflows failed
 - whether failures are correlated with certain task queues or workflow types
 - whether workflows often end with an attached error signal

 ### Emission conditions
 It is emitted only when the code is running inside a Temporal activity.

 It is incremented by `emit_temporal_workflow_status_kpi(...)`.

 ### Dimensions
 - `status`: workflow final status in lowercase
 - `task_queue`: Temporal task queue name
 - `workflow_type`: Temporal workflow type, or unknown
 - `has_error`: true if an error string is present, else false
 - `has_document_uid`: true if a document UID exists, else false
 - `has_filename`: true if a filename exists, else false
 - `workflow_id_prefix`: prefix extracted from workflow_id.split("-", 1)[0], or unknown

 ### Important interpretation note
 `workflow_id_prefix` is a normalization strategy to avoid using the full workflow ID as a dimension, which would create very high cardinality.

 This keeps the metric safer for Prometheus while still preserving a rough workflow family grouping.

 ## Supporting dimension semantics

 ### `phase`
 Logical step in the ingestion pipeline, for example metadata, input, or another internal phase name.

 Useful for identifying where time or failures happen.

 ### `status`
 Outcome attached to an activity result or workflow status, typically values such as success, failure, or workflow terminal states.

 ### `error_code`
 Normalized failure code derived from the Python exception class name.

 Examples:
 - `none`
 - `ValueError`
 - `TimeoutError`
 - ...

 This avoids raw exception-message cardinality explosion.

 ### `file_type`
 File type normalization derived from:

 1. metadata file type if present
 2. metadata document name extension
 3. file display name extension
 4. file external path extension
 5. fallback to other

 ### `source_type`
 Describes whether ingestion came from:

 - push
 - pull
 - unknown

 The code prefers normalized metadata and otherwise infers pull when external_path exists.

 ### `source_tag`
 Normalized connector or source identifier.

 This allows dashboards to compare ingestion behavior across sources without using highly specific per-document identifiers.

 ### `attempt`
 Temporal activity retry attempt number, stored as a string dimension.

 Useful to separate first-try behavior from retry behavior.

 ## Relationship between the metrics

 ### Queue wait vs duration
 - `temporal.system.activity_queue_wait_ms` measures time before execution starts
 - `temporal.system.activity_duration_ms` measures time spent executing

 A high queue wait with normal duration usually suggests worker capacity or scheduling pressure.

 A normal queue wait with high duration usually suggests slow business logic or downstream dependency latency.

 ### Activity counters vs workflow counters
 - `temporal.ingestion.documents_total` is activity-result oriented
 - `temporal.ingestion.workflows_total` is workflow-status oriented

 Use the first for per-phase throughput and failures.

 Use the second for end-to-end workflow outcome tracking.

 ## Cardinality considerations
 This module is intentionally designed to keep dimensions relatively stable and low cardinality.

 Good practices visible in the code:

 - using exception class names instead of raw error messages
 - using workflow_id_prefix instead of full workflow ID
 - normalizing file type and source type
 - using a system actor instead of end-user identity

 Potentially higher-cardinality dimensions still present:

 - `task_queue`
 - `activity_type`
 - `workflow_type`
 - `source_tag`
 - `attempt`

 These are usually acceptable if the number of distinct values stays bounded.

 ## Practical dashboard meaning

 ### Use `temporal.system.activity_queue_wait_ms` to answer
 - Are workers picking up tasks quickly?
 - Is a queue backing up?
 - Which task queue has scheduling delay?

 ### Use `temporal.system.activity_duration_ms` to answer
 - Which activities are slow?
 - Which phase got slower over time?
 - Are retries slower than first attempts?

 ### Use `temporal.ingestion.documents_total` to answer
 - How many ingestion operations were processed?
 - What is the success vs failure volume?
 - Which source or phase contributes most to failures?

 ### Use `temporal.ingestion.workflows_total` to answer
 - How many workflows finished successfully?
 - How many workflows failed?
 - Are failures concentrated in a workflow family or queue?

 ## Summary
 This module instruments Temporal ingestion at two levels:

 - activity scheduling and execution behavior
 - workflow final outcome behavior

 The four metrics mean:

 - `temporal.system.activity_queue_wait_ms`: queue delay before an activity starts
 - `temporal.system.activity_duration_ms`: execution time of an activity
 - `temporal.ingestion.documents_total`: count of activity-level ingestion results
 - `temporal.ingestion.workflows_total`: count of workflow-level status events