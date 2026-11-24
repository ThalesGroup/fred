# Fred Grafana dashboards

## Import a dashboard

In Grafana, open **Dashboards > New > Import**, upload the dashboard JSON linked
below, and select a Prometheus data source that meets the dashboard's requirements.

## Platform health

[`fred-platform-health.json`](fred-platform-health.json) uses Fred's
`agent_turn_completed_count`, `api_request_latency_ms_count`, and
`api_request_latency_ms_bucket` metrics. Use a source that scrapes the Python agent
runtimes, Knowledge Flow and the Control Plane. Missing series must not be
interpreted as zero errors.

The summary cards follow the selected time range. **Cluster** and **Namespace**
apply to all panels when the corresponding labels are available in Prometheus.
Keep **All** selected for labels your scrape pipeline does not supply.
**Chat runtime** applies to the chat metrics. Expand **HTTP route latency** to
investigate a route spike. The latency panels use 2xx and 3xx responses.

**Lookback** sets the rolling window for the detailed failed-turn rate, turn
volume, and HTTP 5xx rate by service. **Auto** uses Grafana's adaptive
Prometheus interval for each rate panel. Both chat charts share the same
resolved window. Fixed windows range from **5m** to **24h**.
Hover over the charts to see the window duration. The chat tooltips also show
the estimated failed and total counts at the same timestamp. Click **Failure
rate** in the chat legend to isolate it from the rolling 24-hour reference.

## Fred bench

[`fred-bench.json`](fred-bench.json) explains one benchmark run on the server side.
Set the time range to the run, from its first to its last measured turn: summary
panels average the whole range and have no campaign label. Choose one **Namespace**;
**Service** and **Agent template** filter the turn panels.

- **Turns**: rate, failures, mean and p95 duration of `agent_turn_completed`, the
  turn as its server times it (Agent Pod, or Control Plane for Ralph). The p95 stays empty while more than 5% of
  turns exceed the histogram's largest finite bucket.
- **Where a turn's time goes**: per service, the time of each source divided by the
  turns: model calls and their first chunk, the `turn_setup` and `history_write`
  stages, checkpoint SQL and pool wait, then the unattributed rest. The Agent Pod's
  timer starts after admission (authorization, runtime binding, conversation lease)
  and stops after the history write, the lease release and the final event. Model
  calls exclude the conversation-title call (`llm_role="title"`), which runs beside
  the first turn; the side tables count it, give binding as admission time, and
  split persistence by `store` and `op`. These means can overlap or include child
  runs; they are not a cascade, and the rest is not a phase.
- **CPU and memory**: per container from the kubelet's cAdvisor (factory job
  `containers`): the namespace, the benchmark mock and PostgreSQL, which is shared
  by all lines. CPU per turn divides by the namespace's measured turns, Ralph's included.
- **Tokens per turn**: input, output and cache-read tokens, without prices.

Ralph's series come from the Control Plane (service `control-plane`). Its turn runs
from the start of the event stream, after admission, to `final` or
`execution_error`; its model calls include the title call, and the first one the
conversation load. Ralph reports no tokens to Prometheus: the consumption registry
keeps them. The Control Plane does not relay Agent Pod streams; its HTTP metrics
cover only its own requests. **not measured** marks an absent series, never zero.

## Chat failure investigation

Import [`fred-chat-failure-investigation.json`](fred-chat-failure-investigation.json)
with the same Prometheus source as Platform health. From **Failed turn rate
over time**, open **Investigate chat failures** to carry across the time range,
Lookback, Cluster, Namespace, and Chat runtime. The **Weekend** annotation
marks Saturday and Sunday in Europe/Paris on both dashboards.

**Failed turns by reason** divides each reason's estimated count by all
recorded turns in the same rolling window. The tooltip includes the estimated
failed and total turns. Historical failures without a reason appear as
**Reason unavailable**.

**LLM invocation failures** uses the same rolling Lookback and can be
filtered by Model, Route, and Reason. The sortable tables summarize all
models, routes, and reasons in the selected time range, with a separate
exact upstream HTTP status breakdown. Each Fred retry
is a separate invocation. A successful retry adds a successful invocation
without adding a failed turn. See the
[telemetry coverage](../../docs/swift/platform/OBSERVABILITY-AND-AUDIT.md#llm-streaming-incident-diagnosis)
for the scope of these counters.

## Agent runtime

[`fred-agent-runtime.json`](fred-agent-runtime.json) uses a Prometheus data
source that scrapes the Fred agent runtimes. The dashboard does not require a
particular data-source UID or a live OpenSearch connection. Select one or more
values in the **Fred service** filter to narrow the panels to specific runtimes.

**Namespace** and **Pod** select scrape targets throughout the dashboard. Keep
**All** when your pipeline does not provide these labels: its `.*` matcher also
includes unlabeled series, so local metrics remain usable. The factory k3d scrape
configuration supplies both labels. Select one namespace to separate Swift from
Weaver, and match the time range to one benchmark step. **Fred service** applies
to runtime panels; **Selected admission stages** intentionally includes every
service in the selected namespace/pods so that Swift Control Plane is visible.

The recovery panels use `agent_tool_call_text_recovered_total`, emitted once per
valid Mistral tool-call proposal reconstructed by the ReAct or Deep middleware.
Its model label matches the model-call timer's configured model name when available;
the writer also adds its standard `service` and `actor_type` labels. A proposal
can still be blocked by approval or budget checks, so the count is not the
number of completed tool executions. The denominator panel uses
`llm_call_latency_ms_count`; “per 100 model calls” can exceed 100 if a response
contains several recovered calls.

The **Streams with corrected tool-call IDs** panel uses
`fred_tool_call_id_corrected_streams_total`. It counts each Chat Completions SSE
response on its first tool-call ID rewrite and shows a rolling one-hour total
across the selected namespaces and pods, independent of the Fred service filter
(the counter has no service label). It measures transport rewrites before SDK
assembly or tool execution.

The remaining panels use the existing model and tool latency histograms and
tool-failure counter. The recovery and failure panels show **No data** until
their first event has been scraped. If every panel is blank, check that the
selected Prometheus source scrapes the agent runtimes' metrics endpoints.

### Reading a conversation benchmark

Use the [client JSONL observations](../../developer_tools/benchmarks/README.md#reports-and-raw-format)
for first text, final and clean stream EOF, keeping preparation and history reads
separate. The model's first observed SDK chunk is not the client's first text.
Match time windows and exclude warm-up and unrelated traffic; these aggregates
have no campaign label. Do not subtract p95 values to estimate overhead. Short
steps or sparse samples may not support a useful histogram percentile, and a
rate window that crosses a step boundary mixes both steps.

The admission panel uses `runtime_stage_latency_ms` with the bounded
`runtime_stage` label. Python agent pods emit `pod_authz` and `runtime_binding`;
Swift's Python Control Plane also emits `runtime_binding_internal`. The latter
overlaps the caller's binding timer. These stages do not cover all admission work,
JWT validation or client preparation. Weaver's Rust Control Plane does not emit
the internal stage; its `api_request_latency_ms` times each route, not the same
decomposition. The same label also carries the turn stages `turn_setup` and
`history_write`, which this admission panel leaves out.

The persistence panels use `persist_pool_wait_ms` and `persist_sql_ms`. They are
**aggregate timing hints**, not a precise pool-versus-query breakdown:

- The closed `store` (`checkpoint`, `history`) and `op` labels separate the
  operations: checkpoint `get_tuple`, `put`, `put_writes`, `owner`, `hitl_claim`,
  `hitl_claim_start`, and history `save`. The metrics cover instrumented Python
  operations, not all database traffic or Control Plane SQLx.
- A turn's history `save` runs in a session the turn-lease fence already opened,
  so its pool wait is near zero; the `history_write` stage times the whole write.
  Checkpoint write acquisition timing includes the turn-fencing SQL check.
- Execution timing can contain application work. Transaction exit/commit coverage
  depends on the instrumented path and cannot be isolated in these aggregates.
  Failed operations are not guaranteed to emit either timer.

The process panels use `process_cpu_seconds_total` and
`process_resident_memory_bytes` from the Python Prometheus client, joined to
selected runtime targets by `job,instance`. CPU is percent of one core and may
exceed 100%; it is not CPU-limit utilization or throttling. Loop lag is a sampled
Python gauge and can miss short spikes; emission requires enabled process KPI
sampling. This dashboard makes no CPU-throttling or container-memory claim; per
container CPU and memory are in [Fred bench](#fred-bench). SQL pool gauges
named `process.db_pool.*` in the KPI pipeline are not Prometheus series: the
single-event exporter deliberately skips `process.*` KPIs.

Producers: [runtime stages](../../libs/fred-runtime/fred_runtime/app/agent_app.py),
[persistence](../../libs/fred-core/fred_core/kpi/kpi_persist_metric.py),
[history timing](../../libs/fred-core/fred_core/history/postgres_history_store.py),
[checkpoint timing](../../libs/fred-runtime/fred_runtime/runtime_support/sql_checkpointer.py),
[label/export rules](../../libs/fred-core/fred_core/kpi/prometheus_kpi_store.py),
and [process sampling](../../libs/fred-core/fred_core/kpi/kpi_process.py).
Source presence does not establish that a deployed image exposes or scrapes a
series. Empty panels mean missing evidence, not zero latency or no errors.
