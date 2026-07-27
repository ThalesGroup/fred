# PERF-01 — synchronous OpenSearch reads in async KPI presets

- **GitHub issue:** parent
  [#2110](https://github.com/ThalesGroup/fred/issues/2110); dedicated issue not
  yet created
- **Priority:** P1
- **Verdict:** confirmed
- **Owner:** unassigned

## Production impact

The audited KPI handlers are coroutines, but they call the synchronous
OpenSearch client inline. While a search is in flight, the control-plane event
loop cannot serve other coroutines on that worker. Concurrent dashboard widget
requests can therefore serialize behind OpenSearch latency and delay unrelated
control-plane requests.

The reference chart currently runs one control-plane replica, so there is no
second replica to absorb an event-loop stall
(`deploy/charts/fred/values.yaml:1518-1523`).

## Exact call chain

```text
dashboard KPI HTTP request
  -> async preset handler
    -> OpenSearchKPIStore.client.search(...)
      -> OpenSearch(..., connection_class=RequestsHttpConnection)
        -> synchronous network round-trip on the event-loop thread
```

`team_activity_summary` executes this chain twice, sequentially. The other
three audited presets execute it once each, for five inline synchronous
searches across the four handlers.

## Evidence

- `libs/fred-core/fred_core/kpi/opensearch_kpi_store.py:150-167` constructs the
  shared store with `RequestsHttpConnection`.
- `apps/control-plane-backend/control_plane_backend/kpi/presets/team_activity_summary.py:46-54`
  declares an async handler; lines 85 and 101 call
  `store.client.search(...)` without offloading.
- `apps/control-plane-backend/control_plane_backend/kpi/presets/token_usage_by_agent.py:53-61`
  declares an async handler; line 97 performs the synchronous search.
- `apps/control-plane-backend/control_plane_backend/kpi/presets/token_usage_by_model.py:44-52`
  declares an async handler; line 85 performs the synchronous search.
- `apps/control-plane-backend/control_plane_backend/kpi/presets/token_usage_over_time.py:44-52`
  declares an async handler; line 94 performs the synchronous search.
- `token_usage_by_agent.py:49-50,84-107` requests as many as 10,000 buckets,
  materializes them, then sorts them in Python to return ten rows. This is a
  secondary CPU/payload concern; the confirmed P1 defect is the synchronous
  network call.

## What is proven

- A synchronous HTTP client is called inline from four async request handlers.
- `team_activity_summary` performs two independent searches sequentially.
- The reference deployment has a single control-plane replica.
- The earlier KPI-write event-loop issue is not a duplicate:
  `docs/swift/issues/ISSUE-001-kpi-opensearch-event-loop-blocking.md` is
  resolved by `ResilientSinkStore`; these are direct read queries and bypass
  that write queue.

## What is not proven

- Current production p95/p99 delay or event-loop lag.
- Whether OpenSearch response time, the 10,000-bucket aggregation, or Python
  sorting dominates end-to-end latency.
- The correct production pool size for an async client.

## Minimal fix direction

Use an async OpenSearch client for query paths, with an explicit bounded
timeout and a process-wide shared client. If the installed client cannot
provide the required async API, isolate the existing synchronous search with
`asyncio.to_thread` as the smallest safe bridge.

Run independent searches concurrently. For `team_activity_summary`, compare a
two-task gather with a single OpenSearch `_msearch` request and select the
smaller, clearer implementation after measurement. Push top-N ordering into
the aggregation instead of fetching and sorting 10,000 buckets if the response
shape permits it.

## Rejected alternatives

- **Do nothing because the handlers are `async def`:** the called client is
  synchronous; the coroutine declaration does not make the network I/O async.
- **Route reads through `ResilientSinkStore`:** it is a fail-open background
  queue for writes, not a request/response query mechanism.
- **Add replicas as the fix:** replicas can mask stalls but leave each worker
  vulnerable and multiply OpenSearch pressure.
- **Remove timeouts to avoid errors:** this increases the duration of an
  event-loop stall and violates the outbound-call convention.

## Acceptance criteria

- No direct synchronous OpenSearch network call remains inside an async KPI
  request handler.
- Every OpenSearch query has an explicit bounded timeout.
- The client is shared rather than created per request.
- Independent searches do not run sequentially without a documented ordering
  dependency.
- Existing authorization and response contracts remain unchanged.
- A regression test fails if the synchronous client is invoked on the event
  loop.

## Tests and load scenario

- Unit-test each preset with an async/fake query boundary.
- Add a delayed fake OpenSearch response and verify two independent
  `team_activity_summary` queries complete near the maximum individual delay,
  not their sum, unless `_msearch` replaces them.
- Run 25 concurrent mixed preset requests while polling a cheap control-plane
  endpoint. Record preset p50/p95/p99, cheap-endpoint p99, event-loop lag,
  OpenSearch pool saturation, and timeout/error rate.
- Use a representative high-cardinality agent dataset to compare the current
  10,000-bucket request with server-side top-N.

## Decision log

- **2026-07-26:** recorded as confirmed P1. Keep separate from resolved KPI
  write issue #2009 because this finding concerns synchronous reads.

## Resolution evidence

Not resolved. Add the fix commit, dedicated GitHub issue, test commands,
load-test parameters, and observed before/after measurements here.
