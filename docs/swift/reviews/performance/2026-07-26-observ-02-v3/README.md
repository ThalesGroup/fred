# OBSERV-02 v3 — performance review findings

Review date: 2026-07-26

Branch:
`2110-observ-02-v3-role-based-dashboards-greencarbon-metrics-models-as-capability-persisted-task-ack`

Reviewed commit: `70437e09`

Parent tracking issue:
[#2110](https://github.com/ThalesGroup/fred/issues/2110)

This directory is the durable evidence and hand-off record for the independent
performance review of OBSERV-02 v3. GitHub remains the source of truth for
priority, assignment, implementation status, and closure. These files must not
become a parallel backlog.

No dedicated GitHub issue existed for any finding when this review was written.
Before implementing a fix, create or select the dedicated issue, link it from
the corresponding dossier, and use that issue for ownership and status.

## Findings

| ID | Priority | Verdict | Hot path | Summary | Dossier |
|---|---:|---|---|---|---|
| PERF-01 | P1 | confirmed | Dashboard KPI reads | Synchronous OpenSearch searches run inline in async preset handlers | [Evidence](./PERF-01-opensearch-sync-in-async-presets.md) |
| PERF-02 | P1 | needs-load-test | Agent turn, before LLM | Model authorization adds one OpenFGA `ListObjects` round-trip per managed turn | [Evidence](./PERF-02-model-authz-openfga-hot-path.md) |
| PERF-03 | P2 | confirmed | Capability catalog and startup | Independent runtime-catalog fetches and sources are awaited sequentially | [Evidence](./PERF-03-capability-catalog-serial-fetches.md) |
| PERF-04 | P2 | confirmed | LLM/tool latency telemetry | Emitted dimensions are filtered out before Prometheus/Grafana | [Evidence](./PERF-04-prometheus-latency-dimensions.md) |
| PERF-05 | P3 | confirmed | Task acknowledgement | One acknowledgement request performs three reads of the same task row | [Evidence](./PERF-05-task-ack-redundant-reads.md) |

Priority is assigned from likely production impact, not implementation effort.
`confirmed` means the code shape is directly established by static inspection;
it does not claim a measured production latency regression.
`needs-load-test` means the added work is established, but its operational
severity has not been measured under representative concurrency.

## Hot-path map

| Entry point | Critical call chain | Remote or blocking work | Concurrency property | Visibility |
|---|---|---|---|---|
| KPI preset request | async preset → `OpenSearchKPIStore.client.search` | Synchronous OpenSearch HTTP | Blocks the control-plane event loop | Request/turn aggregates do not isolate the stall |
| Managed agent turn | execution authorization → model-capability lookup → model routing → LLM | Two OpenFGA operations before the LLM; the second is new model lookup | Async and bounded, but one extra request per turn | No dedicated model-authz latency/error KPI |
| Capability catalog | source loop → tools/templates/models fetches | Up to three runtime HTTP fetches per source | Independent fetches and sources are serial | Logs failures; no wall-time budget is enforced |
| LLM/tool middleware | timer → KPI writer → Prometheus label filter | Non-blocking resilient sink | Safe emission path | Several useful dimensions are discarded |
| Task acknowledgement | route read → authorization → service read → store read/write | Three async database reads, optional ReBAC access check | Non-blocking but redundant | No query-count regression guard |

## Working protocol for Claude and Codex

1. Work on one dossier at a time. Read its evidence, rejected alternatives,
   acceptance criteria, and latest decision-log entry before changing code.
2. Create or select a dedicated GitHub issue and add its URL to the dossier.
   Record owner and status in GitHub, not only in this directory.
3. Append decisions; do not silently replace earlier evidence. If the code has
   moved, add current `file:line` evidence and retain enough history to explain
   why the conclusion changed.
4. Keep `confirmed` separate from `needs-load-test`. Static inspection can prove
   a blocking call, sequential awaits, redundant reads, or a filtered label; it
   cannot prove p95/p99 impact.
5. A fix is complete only when its acceptance checks and relevant quality/tests
   pass. Put commands and observed results under **Resolution evidence**, then
   close the dedicated GitHub issue.
6. Update this index only for a verdict, priority, or dossier-link change. Do
   not duplicate implementation diaries here.

## Review verification

The review used the existing focused correctness suites as supporting context:

- `libs/fred-runtime`: 13 tests passed
  (`tests/test_model_enforcement.py`,
  `tests/test_models_catalog_projection.py`).
- `apps/control-plane-backend`: 15 tests passed
  (`tests/test_model_capability_projection.py`, `tests/test_kpi_scope.py`,
  `tests/test_kpi_storage_and_activity.py`).
- `libs/fred-core`: 13 tests passed
  (`fred_core/tests/tasks/test_acknowledge.py`).

These 41 passing tests establish functional coverage only. No representative
concurrency or latency load test was run, so they do not close PERF-01,
PERF-02, PERF-03, or PERF-05.
