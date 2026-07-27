# PERF-03 — capability catalog awaits independent runtime fetches serially

- **GitHub issue:** parent
  [#2110](https://github.com/ThalesGroup/fred/issues/2110); dedicated issue not
  yet created
- **Priority:** P2
- **Verdict:** confirmed
- **Owner:** unassigned

## Production impact

Capability catalog aggregation awaits enabled runtime sources one after
another. Within each source it also awaits the installed-tool/template
projection, the agent-template projection, and the model catalog in sequence,
although none consumes another's result.

This path serves capability administration and also runs during control-plane
lifespan startup before the application yields. Slow or unreachable runtime
pods therefore add their timeout budgets rather than overlapping them.

## Exact call chain

```text
aggregate_capability_catalog
  for each enabled runtime source, sequentially:
    await available capabilities/templates (10 s timeout)
    await agent templates (10 s timeout; may be request-scope deduplicated)
    await models catalog (5 s timeout)

startup lifespan
  -> seed registration defaults
    -> await aggregate_capability_catalog
  -> yield application
```

## Evidence

- `apps/control-plane-backend/control_plane_backend/capabilities/catalog.py:60-88`
  contains the source loop and three sequential awaits.
- `apps/control-plane-backend/control_plane_backend/product/service.py:429-436`
  fetches runtime templates using a newly-created `httpx.AsyncClient` with a
  10-second timeout.
- `apps/control-plane-backend/control_plane_backend/product/service.py:551-570`
  and lines 608-655 show that the first two catalog projections both fetch
  templates.
- `apps/control-plane-backend/control_plane_backend/product/service.py:671-700`
  performs the model-catalog request with a newly-created client and a
  5-second timeout.
- `apps/control-plane-backend/control_plane_backend/main.py:122-135,157-163`
  awaits aggregation during lifespan initialization before `yield`.
- `apps/control-plane-backend/control_plane_backend/capabilities/service.py:225-248`
  runs top-level admin-page work concurrently and request-scope-deduplicates
  template fetching, but the internal source loop and the model fetch remain
  serial.
- `deploy/charts/fred/values.yaml:1721-1725` configures one runtime source in
  the reference chart.
- `apps/control-plane-backend/config/configuration_prod.yaml:93-108`
  configures four enabled sources for local production-style operation.

## What is proven

- Independent per-source operations are awaited sequentially.
- Enabled sources are processed sequentially.
- Each outbound call has a bounded timeout.
- The code constructs new HTTP clients for these fetches rather than using a
  process-wide shared client.
- Startup waits for the aggregation to finish.

Without request-scope memoization, one completely unavailable source can spend
up to approximately 25 seconds across two 10-second template fetches plus the
5-second model fetch. Four serial sources can therefore expose roughly 100
seconds of aggregate timeout budget. Inside `_template_fetch_scope`, the
template work is deduplicated, reducing the rough upper bound to 15 seconds
per source or 60 seconds across four sources. These are code-derived timeout
ceilings, not measured production durations.

## What is not proven

- Observed startup or admin-page p95/p99 latency.
- Whether production always uses only the single reference-chart source.
- Whether the runtime endpoints or connection setup dominate normal,
  non-timeout latency.
- The correct concurrency limit if deployments configure many sources.

## Minimal fix direction

Run independent fetches for one source concurrently with `asyncio.gather`,
preserving the current best-effort result for each projection. Run enabled
sources concurrently as well, with a small explicit concurrency bound if the
configuration can grow beyond a handful of sources.

Reuse a process-wide shared `httpx.AsyncClient` with explicit timeout and pool
settings. Preserve template-fetch memoization so the two projections do not
create duplicate requests.

## Rejected alternatives

- **Increase all timeouts:** this makes serial worst-case latency longer.
- **Make registration seeding fire-and-forget without defining readiness
  semantics:** it changes startup correctness and can race early requests.
- **Remove best-effort handling:** an unavailable optional runtime should not
  make the whole catalog fatal.
- **Add a cache first:** concurrency and client reuse remove known waste
  without introducing freshness or replica-consistency semantics.

## Acceptance criteria

- Independent projection fetches for one source do not add their wall times.
- Enabled sources do not add their wall times without a documented concurrency
  or ordering reason.
- The current best-effort behavior and later-registration collision semantics
  remain covered.
- HTTP clients are shared and use explicit bounded timeouts/pool settings.
- Startup behavior has an explicit maximum budget compatible with readiness.

## Tests and load scenario

- Fake three endpoints with deterministic delays and assert one source
  completes near the maximum delay, not the sum.
- Fake four sources and assert aggregate wall time is near the slowest source,
  subject to the chosen concurrency limit.
- Cover one failed projection alongside two successful projections; successful
  capability kinds must remain present.
- Exercise startup with unreachable sources and record time to readiness.
- Measure client connection reuse and pool saturation during repeated admin
  catalog requests.

## Decision log

- **2026-07-26:** recorded as confirmed P2. Existing #2089 concurrency around
  the outer admin operation does not remove serialization inside catalog
  aggregation.

## Resolution evidence

Not resolved. Add the dedicated issue, implementation commit, focused test
results, and measured startup/admin wall-time comparison here.
