---
name: fred-performance-reviewer
description: Review requested Fred runtime or database changes for performance, concurrency and async correctness. Trace concrete hot paths, SQL access and shared state; prioritize model latency and tool latency for agent turns. Read-only unless fixes are requested; does not launch a benchmark campaign.
---

# Fred performance review

Read `AGENTS.md`, relevant arc42/source references and
[fred-reconstruction-method](../fred-reconstruction-method/SKILL.md) for design
capacity targets and the schema/concurrency method. Do not use historical Swift
replica counts or user counts as current sizing assumptions. Connected sessions,
active HTTP requests, admitted turns, model calls and document workers are distinct
loads. SQL catalog capacity and model/provider capacity are separate problems.

Establish the requested scope, actual comparison base/HEAD and dirty files.
Inspect before judging. Do not edit code or run traffic unless requested. A
performance concern needs a concrete mechanism and call path, not "might be slow."
Distinguish proven blocking/contention from a hypothesis requiring measurement.

## Agent and service paths

Prioritize model-call latency, then tool latency, then other turn overhead. Trace
actual calls rather than inferring async safety from `async def` or `.await`.
Check blocking I/O, CPU work on an event loop, sequential independent operations,
unbounded fan-out, deadlines, cancellation and pool exhaustion. Bound concurrency
and respect genuine ordering dependencies.

Reuse configured clients/pools; inspect whether differing configurations are
actually respected. Do not create a new shared-client abstraction when the existing
one can be extended. Never hold SQL transactions or synchronous locks over network
calls or human waits. New queues, locks, caches and counters need an explicit owner
and replica scope; process-local state cannot prove distributed correctness.

Trace metrics through actual producers, sinks, exporters and dashboards. Inspect
`libs/fred-core/fred_core/kpi/prometheus_kpi_store.py` and runtime middleware when
relevant; a recorded metric is not automatically observable. Preserve privacy and
bounded cardinality: user, session and team IDs must not become Prometheus labels.
KPI/log delivery must not perform blocking network work on the hot path. Reuse the
existing instrumentation instead of adding a parallel timer or export path.

Respect the admitted turn's fixed authority lifetime. Do not propose per-tool or
per-model authorization refreshes as a performance/security fix. Preserve separate
resource checks, cancellation, terminal-state enforcement and execution limits.

## SQL and document paths

Start with the business invariant and schema/transaction owners, then concrete
queries. Inspect rows read/written, selectivity, indexes, page/batch bounds, lock
order/duration, contention, retry effects and accumulated maintenance cost.
Particularly examine organization counters, quota reservations, publication,
reprocessing, move/process/delete races and hierarchy purges.

Check partial indexes against both live reads and purge/FK checks. Justify each
index by an actual access path and account for writes/storage. PostgreSQL indexes
and search indexes are distinct. Do not default to sharding, partitioning, caches,
distributed counters or repair systems. Challenge needless work and duplicate
mechanisms before adding optimization code.

## Verification and report

Use available measurements with their exact revision, dataset, concurrency and
configuration. A synthetic plan or a small mock campaign establishes only that
envelope, not the design targets. If a requested experiment uses a campaign skill,
verify that its endpoint and authentication contract match this checkout. A legacy
Swift runner is not automatically a Weaver benchmark; never bypass its guards.

For each actionable finding, give file/line, trigger and call/query path, observed
or inferred impact, minimal correction and the evidence needed to verify it.
Distinguish code removal/reuse from unavoidable additions. Report actual checks,
remaining uncertainties and scope limits. Do not create a separate permanent
performance finding corpus or claim a capacity gain from instrumentation alone.
