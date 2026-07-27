# PERF-04 — latency dimensions are emitted but discarded before Grafana

- **GitHub issue:** parent
  [#2110](https://github.com/ThalesGroup/fred/issues/2110); dedicated issue not
  yet created
- **Priority:** P2
- **Verdict:** confirmed
- **Owner:** unassigned

## Production impact

The priority latency KPIs exist, but some dimensions added by their emitters
are not in the Prometheus allow-list and therefore never reach Grafana.

`llm.call_latency_ms` can be decomposed by `model_name`, but its current
`agent_id` and `operation` dimensions are discarded. Tool latency retains
`tool_name` and `template_agent_id`, but discards `source`, so Grafana cannot
separate MCP and capability-native tool paths. This limits diagnosis of LLM
and tool regressions even though the raw KPI event carries the dimensions.

## Exact call chain

```text
TracingKpiMiddleware / ToolObservabilityMiddleware
  -> KPI event with dims
    -> PrometheusKPIStore
      -> keep only PROMETHEUS_ALLOWED_LABELS
        -> Prometheus scrape
          -> Grafana
```

## Evidence

- `libs/fred-runtime/fred_runtime/react/middleware/tracing_kpi.py:103-114`
  emits `agent_id`, `operation`, and optionally `model_name` on
  `llm.call_latency_ms`.
- `libs/fred-runtime/fred_runtime/react/middleware/tool_observability.py:123-147`
  emits `tool_name`, `source`, and, when present, `template_agent_id` on tool
  telemetry.
- `libs/fred-core/fred_core/kpi/prometheus_kpi_store.py:48-69` allows
  `template_agent_id`, `model_name`, and `tool_name`, but not `agent_id`,
  `operation`, or `source`.
- `libs/fred-runtime/fred_runtime/model_routing/provider.py:178-185` documents
  `operation` as free text with runtime-defined values.
- `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` section 3 permits bounded
  agent *type* but excludes configured agent instance, team, user, session,
  and per-call identity from Prometheus.

## What is proven

- The three dimensions absent from `PROMETHEUS_ALLOWED_LABELS` are filtered
  before they become Prometheus labels.
- `model_name`, `tool_name`, and `template_agent_id` are already permitted.
- Adding `agent_id` without clarifying its semantics can violate the
  operational-metrics privacy boundary or create unbounded cardinality.
- `operation` is not currently a closed vocabulary.

## What is not proven

- That every current runtime binding contains `template_agent_id`.
- The finite set and cardinality of present/future `source` values.
- Which Grafana panels should expose each safe dimension.
- Whether product analytics already answers a subset of the diagnostic
  questions outside Prometheus.

## Minimal fix direction

For LLM latency, emit the catalog blueprint/type as `template_agent_id`, which
is already allowed, instead of promoting the ambiguous `agent_id`. Keep
configured agent instance identity out of Prometheus.

If `source` is formally limited to a small vocabulary such as
`mcp|capability`, document that contract, allow-list it deliberately, and add
a label-filter regression test. Do not allow-list `operation` while it remains
free text; first map it to a closed, low-cardinality vocabulary or omit it.
Update the relevant Grafana dashboards only after the label contract is
accepted.

## Rejected alternatives

- **Add `agent_id`, `operation`, and `source` wholesale to the allow-list:**
  this bypasses the deliberate privacy/cardinality gate.
- **Use team or agent-instance labels for drill-down:** those belong to
  authorization-scoped product analytics, not wide-audience operational
  metrics.
- **Assume a dimension in the KPI event is already visible in Grafana:** the
  explicit allow-list proves otherwise.
- **Encode missing dimensions into metric names:** this creates an unbounded
  metric family and evades label governance.

## Acceptance criteria

- Grafana can decompose LLM latency by a bounded, non-instance agent type and
  by model.
- Grafana can decompose tool latency by source only after source is enforced as
  a finite vocabulary.
- No user, session, team, configured agent instance, or correlation identifier
  reaches Prometheus.
- Tests cover accepted and rejected label filtering, including future
  unrecognized values.
- Dashboard queries and label names are documented and verified against a
  scraped metric sample.

## Tests and load scenario

- Unit-test that `template_agent_id`, `model_name`, `tool_name`, and an approved
  bounded `source` survive sanitization while identity dimensions do not.
- Unit-test that an unknown source or operation cannot create an arbitrary
  label value if a closed mapping is introduced.
- Run one LLM call for two template agent types and one MCP plus one
  capability-native tool call; inspect the Prometheus exposition and Grafana
  query results.
- Track series count before and after deployment to verify the cardinality
  budget.

## Decision log

- **2026-07-26:** recorded as confirmed P2. Privacy decision: do not promote
  `agent_id`; prefer already-allowed `template_agent_id`. `source` and
  `operation` require an explicit bounded-vocabulary decision.

## Resolution evidence

Not resolved. Add the dedicated issue, accepted label vocabulary, code and
dashboard commits, exposition sample, tests, and series-count observation
here.
