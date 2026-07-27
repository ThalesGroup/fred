# TURN-06 — pod admission and SQL capacity have no demonstrated concurrency envelope

- **GitHub issue:** dedicated issue not yet created
- **Related issue:** [#1534](https://github.com/ThalesGroup/fred/issues/1534)
  concerned the removed legacy WebSocket service and does not validate the
  current SSE runtime
- **Priority:** P1
- **Verdict:** needs-load-test
- **Owner:** unassigned

## Production impact

The runtime exposes Uvicorn's concurrency limiter, but production configuration
leaves it unset. Checkpoint and history work share one async SQL engine whose
effective defaults are five pooled plus ten overflow connections with a
30-second pool wait.

An accepted wave of 200 turns can therefore queue SQL work behind a 15-connection
ceiling while continuing to hold SSE connections, runtime objects, model/tool
work, and history payloads. No tested relationship currently ties replicas,
Uvicorn admission, SQL capacity, LLM pool capacity, or OpenFGA capacity to a
target concurrency.

## Evidence

- `apps/fred-agents/fred_agents/__main__.py:34-42` passes
  `config.app.limit_concurrency` to Uvicorn.
- `apps/fred-agents/config/configuration_prod.yaml:8-10` and
  `deploy/charts/fred/values.yaml:612-622` set it to `null`.
- `libs/fred-runtime/fred_runtime/app/context.py:125-146` shares one SQL engine
  between checkpointer and history.
- `libs/fred-core/fred_core/sql/base_sql.py:226-286` applies defaults of
  `pool_size=5`, `max_overflow=10`, and `pool_timeout=30`.
- `libs/fred-runtime/fred_runtime/app/agent_app.py:1477-1479` checks an existing
  session with two sequential history-store calls; each maps to a SQL `COUNT`
  in
  `libs/fred-core/fred_core/history/postgres_history_store.py:354-384`.
- The fred-agents production configuration does not override those SQL pool
  values.

## Minimal fix direction

Establish a measured capacity model per pod, then configure an admission bound
that fails fast or queues deliberately before expensive turn initialization.
Tune SQL only from evidence; increasing the pool without database capacity can
move the bottleneck rather than solve it.

## Acceptance criteria

- A four-replica test defines the supported concurrent-turn envelope and
  overload behavior.
- Admission, SQL pool, OpenFGA, MCP, LLM pool, CPU, and memory limits are sized
  together.
- Pool wait and admission rejection are visible through low-cardinality
  metrics.
- Clients receive a typed/retryable overload response before expensive work.
- Configuration and the design document state the tested values and scenario.

## Decision log

- **2026-07-26:** recorded P1 `needs-load-test`; static defaults do not prove a
  failure, but there is no evidence for the requested 200-turn target.

## Resolution evidence

Not resolved.
