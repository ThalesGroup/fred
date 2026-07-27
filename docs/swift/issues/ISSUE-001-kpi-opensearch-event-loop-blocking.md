# ISSUE-001 - KPI OpenSearch write can block async hot paths

Status: resolved (2026-07-18, issue #2009)
Owner: TBD
Target window: Constellation (2.x) runtime/pod hardening window

**Resolution.** `KPIWriter.emit()` still calls `store.index_event(event)`
inline, but `store` is now a `ResilientSinkStore`
(`libs/fred-core/fred_core/kpi/kpi_factory.py`) whose `index_event` is a
non-blocking `queue.put_nowait` — the real OpenSearch HTTP call
(`opensearch_kpi_store.py`) only runs in a background daemon thread behind a
circuit breaker (`libs/fred-core/fred_core/common/resilient_sink.py`). The
generic/audit log store is wrapped the same way
(`libs/fred-core/fred_core/logs/log_store_factory.py`). See
`docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` §9 ("A KPI/log sink outage
cannot fail or stall a business request — True today"). `ResilientSinkStore`
is now the canonical pattern for any new external sink on a hot path — see
the `fred-performance-reviewer` skill and `docs/CONVENTIONS.md
§Performance & concurrency`.

## Problem
KPI emission is synchronous in the shared writer. When the selected KPI store uses OpenSearch, the HTTP write is performed inline on the caller thread. In async runtime paths this can block the event loop during network round-trips.

## Why it matters
- Adds avoidable latency under concurrent sessions.
- Can create stacked delays in model/tool loops when KPI writes are frequent.
- Hard to detect in single-session tests; appears under load.

## Current evidence
- `libs/fred-core/fred_core/kpi/opensearch_kpi_store.py`: OpenSearch client uses `RequestsHttpConnection` and `index_event()` calls `self.client.index(...)` synchronously.
- `libs/fred-core/fred_core/kpi/kpi_writer.py`: `emit()` calls `self.store.index_event(event)` synchronously.
- `libs/fred-core/fred_core/kpi/kpi_writer.py`: `_TimerImpl.__exit__()` calls `self.svc.emit(...)` synchronously.
- `libs/fred-runtime/fred_runtime/react/react_model_adapter.py`: async `_wrap(...)` uses `with kpi.timer(...)` in model-call hot path.
- `knowledge-flow-backend/knowledge_flow_backend/application_context.py`: KPI store may be `OpenSearchKPIStore`, wrapped by `PrometheusKPIStore(delegate=store)`.

## Scope
- Active paths:
  - Shared KPI layer (`fred-core`) used by runtime and knowledge-flow.
  - Runtime async model wrapper when KPI writer is enabled.
  - Knowledge-flow when KPI backend is configured to OpenSearch.
- Not in scope:
  - Legacy `agentic-backend` call chain (no longer active in this workspace layout).
  - Langfuse span issue (track separately when deployed in production).

## Proposed fix
- Option A (preferred): make KPI writer non-blocking by enqueueing events and draining them in a background thread/worker owned by `KPIWriter`.
- Option B: keep sync writer API but offload `index_event` to executor/threadpool in the write path.

## Acceptance checks
- [ ] No synchronous OpenSearch HTTP call remains on runtime async hot paths.
- [ ] KPI order and at-least-once behavior are documented.
- [ ] Backpressure policy is defined (drop/block/overflow strategy).
- [ ] Runtime load test shows no event-loop stall attributable to KPI writes.
- [ ] Existing KPI call sites remain unchanged.

## Promotion
Promoted to: none
Notes: Keep this issue as pre-backlog until owner and rollout slice are agreed.
