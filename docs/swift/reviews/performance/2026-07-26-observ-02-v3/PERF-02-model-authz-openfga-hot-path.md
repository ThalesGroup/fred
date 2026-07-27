# PERF-02 — model authorization adds OpenFGA work before every managed LLM turn

- **GitHub issue:** parent
  [#2110](https://github.com/ThalesGroup/fred/issues/2110); dedicated issue not
  yet created
- **Related issue:**
  [#2091](https://github.com/ThalesGroup/fred/issues/2091) optimizes a different
  admin capability-listing fan-out and explicitly excludes execution checks
- **Priority:** P1
- **Verdict:** needs-load-test
- **Owner:** unassigned

## Production impact

Every team-scoped managed turn now performs a model-capability
`ListObjects` request before model routing and before the first remote LLM
call. This is in addition to the existing execution authorization check.
At 200 concurrent turns, this creates 200 additional OpenFGA requests at the
same point in the critical path.

The implementation is async and its client has a bounded default timeout, so
static inspection does not prove an event-loop defect. The unresolved risk is
OpenFGA capacity, time-to-first-token, timeout rate, and poor attribution when
this pre-LLM step fails or slows down.

## Exact call chain

```text
managed agent request
  -> execution authorization Check
  -> _iterate_runtime_event_payloads
    -> usable_model_capability_ids(team_id)
      -> RebacEngine.lookup_resources(...)
        -> OpenFGA client.list_objects(...)
  -> capability/runtime construction
  -> model routing
  -> remote LLM call
```

## Evidence

- `libs/fred-runtime/fred_runtime/app/agent_app.py:1423-1426` performs the
  existing team execution authorization.
- `libs/fred-runtime/fred_runtime/app/agent_app.py:2524-2535` performs one
  additional usable-model lookup for every team-scoped turn.
- `libs/fred-runtime/fred_runtime/model_routing/authz.py:77-103` implements the
  lookup as `rebac.lookup_resources` for `CapabilityPermission.CAN_USE` and
  filters model capability IDs client-side.
- `libs/fred-core/fred_core/security/rebac/openfga_engine.py:216-226` maps that
  operation to OpenFGA `client.list_objects`.
- `libs/fred-core/fred_core/security/structure.py:111-117` gives OpenFGA calls a
  5,000 ms default timeout; `openfga_engine.py:321-329` passes it to the SDK
  client.
- `libs/fred-runtime/fred_runtime/app/agent_app.py:2630` starts the generator's
  main `try` block after the model-capability lookup.
- `libs/fred-runtime/fred_runtime/react/middleware/tracing_kpi.py:103-123`
  measures the LLM handler only; it cannot attribute time spent in the
  preceding authorization lookup.
- `libs/fred-runtime/fred_runtime/app/agent_app.py:2037-2092` can emit total
  successful turn duration, but not a dedicated model-authz duration.

## What is proven

- A second OpenFGA operation is added before the LLM for every team-scoped
  managed turn.
- The new operation is asynchronous and normally bounded by a 5-second
  timeout.
- The LLM latency timer excludes the authorization lookup.
- The lookup happens before the main generator `try`, so its failure does not
  follow the same turn-completion/error-emission path as later runtime errors.

## What is not proven

- That OpenFGA is currently saturated or violates a latency SLO.
- The p95/p99 cost at 200 concurrent turns.
- Whether an authorization cache would be safe under revocation requirements.
- Whether the existing overall request telemetry captures every early failure
  through a higher-level route or middleware.

## Minimal fix direction

Measure before changing the authorization model. Add a dedicated,
low-cardinality timer and error counter around the model-capability lookup,
using the existing KPI machinery. Ensure early lookup failures follow the
normal bounded error/turn-completion observability path.

Then load-test the current design. If the results violate the agreed
time-to-first-token or OpenFGA capacity budget, reduce remote work through an
authorization-preserving design reviewed with the ReBAC owners. Any cache
must state its revocation semantics and whether it is pod-local or shared
across the four `fred-agents` replicas.

## Rejected alternatives

- **Declare the path safe because it is async:** async avoids blocking the
  event loop but does not remove remote latency, service load, or pool
  contention.
- **Speculatively add an unbounded or long-lived cache:** stale authorization
  can permit a model after access is revoked; correctness requirements must
  define TTL/invalidation first.
- **Fold duration into `llm.call_latency_ms`:** the lookup occurs before the
  LLM and must remain distinguishable from gateway/model latency.
- **Reuse issue #2091 without review:** that issue explicitly excludes
  per-action execution checks and targets an admin listing/reporting surface.

## Acceptance criteria

- A bounded, privacy-safe metric exposes model-authorization latency and
  errors without team, user, session, or agent-instance labels.
- Lookup failures produce the same terminal/error visibility guarantees as
  failures after runtime construction.
- A representative load test demonstrates the OpenFGA and time-to-first-token
  budget, or a follow-up optimization is agreed and tracked.
- Any cache or memoization design documents revocation behavior, maximum
  staleness, replica scope, and failure posture.
- Authorization remains fail-closed when ReBAC is enabled.

## Tests and load scenario

- Run 200 concurrent team-scoped managed turns against a controlled OpenFGA
  fixture, without needing to complete expensive LLM generations.
- Record `ListObjects` request rate, p50/p95/p99, timeout/error rate, OpenFGA
  CPU and pool utilization, end-to-end time-to-first-token, and LLM client-pool
  wait time.
- Inject delayed and failing OpenFGA responses to verify bounded failure and
  terminal telemetry.
- Compare ReBAC-disabled and ReBAC-enabled baselines to isolate the added
  critical-path cost.

## Decision log

- **2026-07-26:** recorded as P1 `needs-load-test`. The extra per-turn call is
  confirmed; harmful production latency is not claimed without measurements.

## Resolution evidence

Not resolved. Add the dedicated issue, agreed latency/capacity budget,
instrumentation commit, load-test setup, results, and any approved design
decision here.
