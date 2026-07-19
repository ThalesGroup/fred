# Bench snapshots

Running log of local bench sessions against the mock LLM (`mock-openai-server`). Newest first.

---

## Bench snapshot (2026-07-08) — swift / fred-runtime (preliminary)

First bench pass on the swift architecture (`fred-agents` + `fred-runtime`, SSE transport)
since the kea-branch numbers below were recorded on the old `agentic-backend` (WS transport).
Not a like-for-like re-run of kea — flagged as preliminary because a real kea instance is
being stood up separately for a direct side-by-side. Purpose here was narrower: confirm swift
isn't structurally regressed before that comparison lands.

### Setup

- Same laptop/mock-LLM approach as the 2026-02-11 snapshot below.
- Foundation: `fred-deployment-factory` Docker Compose (`STACK=base`) — Postgres, Keycloak,
  SeaweedFS, OpenSearch, OpenFGA, Temporal.
- `fred-agents` single uvicorn worker, `CONFIG_FILE` pointed at Postgres (`storage.postgres.host/port/database/username`,
  matching `configuration_prod.yaml`'s shape), security disabled (`m2m`/`user`/`rebac` all off —
  full-auth pass deferred, needs real Keycloak JWT + OpenFGA tuples for the bench client).
- Mock LLM: `mock-openai-server` (fork at `github.com/fred-agent/mock-openai-server`), port 8383,
  no artificial response delay (`responseDelay.enable: false`) — unlike kea's fixed ~3s floor, so
  latencies below are NOT directly comparable to the 2026-02-11 numbers without subtracting kea's
  floor first (see the per-table notes).
- Bench client: `developer_tools/benchmarks` Go client, `-protocol sse` against
  `/fred/agents/v2/agents/execute/stream`.
- Agent under test: `fred.github.assistant` (7 default MCP tool schemas: KF text/corpus/fs/tabular/
  opensearch-ops/prometheus-ops + a GitHub tool) unless noted as the zero-tool baseline, for which a
  throwaway `bench.georges`-style agent (zero `default_mcp_servers`, zero `declared_tool_refs`) was
  registered temporarily and removed after the comparison — no equivalent zero-tool agent exists in
  the current registry (every registered ReAct agent declares at least one MCP server/tool ref by
  default), so a genuinely tool-free comparison point had to be added by hand.

### Three fixes found and shipped this round

1. **Redundant MCP tool-discovery round trip.** `get_connected_mcp_client_for_agent`
   (`libs/fred-runtime/fred_runtime/common/mcp_utils.py`) already fetches each server's tools once
   while validating the connection; `MCPRuntime._run_lifecycle`
   (`libs/fred-runtime/fred_runtime/common/mcp_runtime.py`) was calling `get_tools()` a *second*
   time right after, across all servers again. Fixed by returning and reusing the
   already-fetched tools — cuts the per-turn MCP round trips roughly in half.
2. **No cross-turn caching of MCP connections/tool schemas at all.** Every single agent turn
   reconnected and re-listed tools against all configured MCP servers from scratch, even though
   `MultiServerMCPClient` holds no persistent resources to justify that (sessions are opened/closed
   per call regardless). Added a process-local, TTL-bound (5 min) cache of `(client, tools)` keyed
   by `(agent_id, sorted server ids, access_token)`. Kept swift's stateless-per-request model fully
   intact for the caller — `_build_runtime_services`/`FredMcpToolProvider`/`MCPRuntime` are still
   rebuilt fresh every request, no new conversation-scoped lifecycle class reintroduced (that
   complexity existed in kea and was deliberately dropped in swift). On a cache hit, the current
   request's own live `ExpiredTokenRetryInterceptor` is swapped into the cached client **in place**
   (verified against `langchain_mcp_adapters==0.3.0`: tool calls read `tool_interceptors`/`headers`
   live off the client instance at call time, not a snapshot frozen at discovery time) — so auth
   freshness is a property of every request, not of whichever request happened to populate the
   cache. One accepted, narrow residual: two truly concurrent requests for the *same* identity could
   have request A's in-flight call pick up request B's interceptor instance instead of its own —
   never a cross-user leak (different identities never share a cache key), at worst a harmless
   same-identity mix-up. Closing that fully would need a lock held for an entire turn's
   tool-calling phase, which would serialize concurrent turns for the same user.
3. **`log_level: debug`.** By far the largest single win, found last. Synchronous debug-level
   logging under real concurrency cost more than either MCP fix above.

### fred.github.assistant (7 tools), 10 clients × 3 turns

| Stage | req/s | latency ms (min/avg/p50/p95/p99/max) |
| --- | --- | --- |
| Baseline | 1.79 | 2611/5058/4828/6969/7239/7239 |
| Fix 1 (dedupe) | 2.82 | 1710/3283/3188/4679/4896/4896 |
| Fix 2 (cache, cold) | 4.79 | 116/1894/628/5549/5995/5995 |
| Fix 2 (cache, warm) | 8.34 | 112/914/456/2469/2914/2914 |
| Fix 2b (cache, warm, auth-safe) | 9.15 | 105/859/664/2562/2992/2992 |

Fix 2b (the auth-safety correction to fix 2) cost nothing measurable — confirms the interceptor
swap is free.

### 100 clients × 20 turns — kea vs swift

kea's row is copied verbatim from the 2026-02-11 snapshot below (Georges, zero tools, Postgres,
fixed ~3.0s mock floor — the `min` column cleanly shows the floor, so treat this row as precise,
not the illustrative 10×3 row further down). "Real overhead" = latency minus the 3.0s floor, for
comparison against swift's numbers, which have no floor to subtract.

| Run | req/s | errors | latency ms (min/avg/p50/p95/p99/max) | real overhead ms (p50/p95) |
| --- | --- | --- | --- | --- |
| kea, Georges (0 tools), Postgres, 3s floor | 21.4 | 0 | 3049/4125/4125/4618/5455/6448 | 1125 / 1618 |
| swift, `fred.github.assistant` (7 tools), SQLite, debug | 8.55 | 165 (8.25%) | 205/10353/10164/13586/15631/17404 | 10164 / 13586 |
| swift, zero-tool baseline, SQLite, debug | 12.67 | 1 (0.05%) | 139/7383/7384/9774/10911/14731 | 7384 / 9774 |
| swift, zero-tool baseline, Postgres, debug | 11.70 | 0 | 105/7881/7629/13429/16422/21409 | 7629 / 13429 |
| **swift, zero-tool baseline, Postgres, `log_level: warning`** | **21.45** | **0** | **38/4110/3947/7284/9286/11926** | **3947 / 7284** |

Reading this:

- Postgres vs SQLite, holding everything else fixed: reliability improved (errors → 0) but latency
  did **not** improve — contradicts the initial hypothesis that persistence contention explained the
  gap. (Kept the Postgres alignment anyway — it matches kea's setup and the 0-errors result is a
  real win independent of the latency question.)
- `log_level: debug → warning` alone: **+83% throughput**, latency roughly halved at every
  percentile. This was the single largest lever found.
- **Aggregate throughput now matches kea almost exactly** (21.45 vs 21.4 req/s) at the identical
  100×20 shape — a strong signal swift is not structurally slower than kea.
- **Per-request tail latency is still ~3.5x kea's**, even with the floor-free comparison (3947ms vs
  kea's floor-adjusted 1125ms at p50). Throughput capacity matches; per-turn cost does not yet.
  Open question for the next round, best answered once real kea numbers are available to diff
  against directly rather than reasoning from the recorded 2026-02-11 snapshot.

### Known gaps in this round

- No real-auth pass (Keycloak JWT + OpenFGA) — security was disabled throughout. The interceptor
  freshness fix (item 2 above) is specifically about not breaking real auth once it's turned back
  on; it has not yet been bench-tested *with* real auth in the loop.
- `fred.github.assistant`'s 7-tool payload at scale (8.25% error rate even after both MCP fixes)
  wasn't fully explained — the zero-tool baseline recovered almost all of the gap, but not 100% of
  it. Worth a closer look once the log-level and persistence questions above are settled.
- Single sample per configuration, no repeated trials — some of the run-to-run spread (e.g. Postgres
  making the tail slightly worse than SQLite) could be partly noise rather than signal.

---

## Bench snapshot (2026-02-11) — kea / agentic-backend

This captures the current local bench state so future work can restart from known numbers.

### Setup

- Laptop: Dell, 32 GB RAM, single Agentic pod (uvicorn single worker), mock LLM fixed ~3 s latency.
- Config deltas (bench):
  - `pool_size=20`, `max_overflow=10`, `pool_timeout=100`, `synchronous_commit=off` inside persist.
  - Fire-and-forget persist (async task), but still measuring persist timings.
  - Ramp-up: 10 s across all clients (default in ws_bench now).
  - HTTP client limits: chat model max_connections=100 (keepalive disabled).
- Instruments added:
  - Gauges: `persist_pool_wait_ms`, `persist_sql_ms`, `event_loop_lag_ms` (shown in KPI summary).
  - Per-run detailed logging is at DEBUG.

### Working Locally versus deployed

Use `configuration_prod.yaml` on both the agentic and knowledge-flow sides — their dedicated bench variants
(`configuration_bench_postgres.yaml`, `configuration_bench.yaml`) were retired. Each app now only carries
`configuration.yaml` and `configuration_prod.yaml` as run-time profiles, plus `configuration_test.yaml`/
`configuration_worker.yaml` (knowledge-flow and control-plane only) for the test suite and Temporal worker.
Not that the yaml parameters actavate KPI so-called summary logs that quickly tells you whats going on.

For example using the Rico benchmark on the agentic side you see something like

```
ARNING  2026-02-13 07:42:48 | WARNING | [pid=3945351 MainThread/Task-13] | [KPI][SUMMARY] cpu_pct=14.19 rss_mb=282.36 rss_pct=0.89 vms_mb=1733.68 open_fds=61                                                                                                    kpi_process.py:164
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] gauge event_loop_lag_ms count=98 last=0.0326 avg=0.06 min=0.01 max=1.46                                                                                                   kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=kf_vector_search count=89 avg=1911.87 min=1305.00 max=2420.00                                                                            kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=vector_search count=89 avg=1912.17 min=1306.00 max=2420.00                                                                               kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=answer_with_sources count=89 avg=127.37 min=104.00 max=290.00                                                                            kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=stream_agent_response count=89 avg=2048.43 min=1423.00 max=2543.00                                                                       kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=persist_tx count=89 avg=18.13 min=2.00 max=156.00                                                                                        kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] gauge persist_pool_wait_ms count=89 last=0.0617 avg=4.66 min=0.06 max=123.02                                                                                              kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] gauge persist_sql_ms count=89 last=8.4231 avg=8.62 min=2.46 max=38.82                                                                                                     kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=stream_total count=89 avg=2067.63 min=1431.00 max=2641.00                                                                                kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=agent_init count=81 avg=0.00 min=0.00 max=0.00                                                                                           kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=attachments_list_on_delete count=8 avg=4.38 min=1.00 max=15.00                                                                           kpi_writer.py:331
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3945351 MainThread/Task-13] | [KPI][SUMMARY] cpu_pct=17.10 rss_mb=301.20 rss_pct=0.95 vms_mb=2111.96 open_fds=54                                                                                                    kpi_process.py:164

```

and knowledge flow:

```
WARNING  2026-02-13 07:42:44 | WARNING | [pid=3947654 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=vector_search count=45 avg=1163.69 min=619.00      kpi_writer.py:331
         max=1722.00
WARNING  2026-02-13 07:42:48 | WARNING | [pid=3947654 MainThread/Task-15] | [KPI][SUMMARY] cpu_pct=72.66 rss_mb=1088.09 rss_pct=3.42 vms_mb=5331.96 open_fds=92             kpi_process.py:164
WARNING  2026-02-13 07:42:54 | WARNING | [pid=3947654 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=vector_search count=92 avg=2010.42 min=837.00      kpi_writer.py:331
         max=2410.00
WARNING  2026-02-13 07:42:58 | WARNING | [pid=3947654 MainThread/Task-15] | [KPI][SUMMARY] cpu_pct=73.77 rss_mb=1107.47 rss_pct=3.48 vms_mb=5403.61 open_fds=96             kpi_process.py:164
WARNING  2026-02-13 07:43:04 | WARNING | [pid=3947654 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=vector_search count=42 avg=2345.40 min=1266.00     kpi_writer.py:331
         max=6553.00
WARNING  2026-02-13 07:43:08 | WARNING | [pid=3947654 MainThread/Task-15] | [KPI][SUMMARY] cpu_pct=22.56 rss_mb=1108.41 rss_pct=3.48 vms_mb=5403.02 open_fds=55             kpi_process.py:164
WARNING  2026-02-13 07:43:14 | WARNING | [pid=3947654 kpi-summary/Sync] | [KPI][SUMMARY] timer app.phase_latency_ms|phase=vector_search count=21 avg=2015.29 min=646.00      kpi_writer.py:331
         max=6398.00
```

These logs corresponds to what you will observe on Grafana. They basically indicate the ltency of each critical 'phase' that will quickly tell you who is the bottleneck.

### Agentic backend

To test the agentic a first simple test consist in benching Georges that only invokes the LLM. No vector search, no knowledge flow calls in the path.
This allows to already have a good view of the main uviconr/async event loop.

#### 10 clients × 3 turns (illustrative)

- Requests/sec: ~20
- Latency (p95): ~3.0 s (essentially the mock LLM floor)
- persist_tx avg: ~3 ms
- CPU ~7%, RSS ~312 MB

#### 100 clients × 20 turns

- Requests/sec: 21.4
- Latency ms (min/avg/p50/p95/p99/max): 3049 / 4125 / 4125 / 4618 / 5455 / 6448
- persist_tx (KPI): avg ~1.1–1.6 s (see instrumentation section for breakdown)

#### 150 clients × 20 turns

- Requests/sec: 22.1
- Latency ms (min/avg/p50/p95/p99/max): 3045 / 6136 / 6315 / 7271 / 7592 / 8087
- Earlier run (150×10) after fire-and-forget: p95 ~7.9 s, p99 ~9.4 s

### Persist breakdown (instrumented)

- At high load (150 clients):
  - `persist_pool_wait_ms` avg ~90–170 ms (max ~1.3 s)
  - `persist_sql_ms` avg ~440–980 ms (max ~1.7 s)
  - `persist_tx` timer aligns with these (~0.7–1.6 s avg)
- At low load (10 clients):
  - pool_wait ~0 ms, sql_ms ~0.6–1.0 ms; persist_tx ~3 ms

### Postgres sanity (pg_stat_statements)

After a 150-client run:

- `INSERT INTO session_history … ON CONFLICT …` mean ~0.098 ms (max 0.47 ms) over 1 500 calls
- `INSERT INTO session … ON CONFLICT …` mean ~0.077 ms (max 0.58 ms) over 1 650 calls
- `SELECT count(*) FROM session WHERE user_id…` mean ~0.057 ms
- Reads/deletes similarly sub-ms

Query used:

```
SELECT queryid,
       calls,
       mean_exec_time AS mean_ms,
       min_exec_time  AS min_ms,
       max_exec_time  AS max_ms,
       rows,
       left(query, 120) AS snippet
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname='fred')
  AND (query ILIKE '%session_history%' OR query ILIKE '% session%')
ORDER BY mean_exec_time DESC
LIMIT 10;
```

Result snapshot:

| queryid              | calls | mean_ms | min_ms | max_ms | rows | snippet                               |
| -------------------- | ----- | ------- | ------ | ------ | ---- | ------------------------------------- |
| 7637388399052348591  | 1500  | 0.098   | 0.026  | 0.466  | 3000 | INSERT INTO session_history …         |
| 6356258841006377401  | 1650  | 0.077   | 0.024  | 0.584  | 1650 | INSERT INTO session …                 |
| 6271241136561251085  | 150   | 0.057   | 0.011  | 0.184  | 150  | SELECT count(\*) FROM session WHERE … |
| -5035404056216960644 | 150   | 0.039   | 0.014  | 0.101  | 150  | DELETE FROM session …                 |
| 813870921486209613   | 150   | 0.029   | 0.011  | 0.087  | 0    | SELECT session_history …              |
| -8455873564438631297 | 150   | 0.018   | 0.005  | 0.077  | 0    | SELECT session_attachments …          |
| -3843513667560893647 | 150   | 0.006   | 0.002  | 0.014  | 0    | DELETE FROM session_attachments …     |

Notes: pg_stat_statements was enabled via shared_preload_libraries; we reset stats, ran the bench, then ran the query above. These timings confirm the DB itself is not the source of the 700–1300 ms “persist” wall time seen in the app (that is event-loop contention).

Conclusion: DB execution is sub-ms; the ~700–1000 ms “sql” wall time is event-loop/scheduling/queuing, not Postgres.

#### Current instrumentation

- Gauges emitted and now in KPI summary: `persist_pool_wait_ms`, `persist_sql_ms`, `event_loop_lag_ms`.
- Persist block still sets `SET LOCAL synchronous_commit TO OFF`.
- Loop-lag probe runs every 100 ms.

### Agentic + Knowledge Flow

#### Early synchronous design

The knowledge-flow was up to this release suffering from synchronous rerank and search REST APIs. Here is a test that examplifies the
issue:
WIth one client all goes well

```
WS BENCH SUMMARY
Outcome: OK
Target: ws://localhost:8000/agentic/v1/chatbot/query/ws
Agent ID: Rico
Total requests: 10
Concurrent clients: 1
Requests per client: 10
Success: 10 (100.00%)
Errors: 0
Elapsed: 8.539s
Requests/sec: 1.17
Latency ms (min/avg/p50/p95/p99/max): 697/850/803/1034/1034/1034
```

But with 20:

```
WS BENCH SUMMARY
Outcome: OK
Target: ws://localhost:8000/agentic/v1/chatbot/query/ws
Agent ID: Rico
Total requests: 200
Concurrent clients: 20
Requests per client: 10
Success: 200 (100.00%)
Errors: 0
Elapsed: 2m27.81s
Requests/sec: 1.35
Latency ms (min/avg/p50/p95/p99/max): 976/14055/14214/18655/19242/26306
```

As you can see knowkedge-flow makes all caller sequentially blocked.

#### Current Design

Starting from this release knowledge-flow is improved by using async pattern but this is not yet fully
implemented using the latest langchain and opensearch native async connectors. We plan to deliver a fully async
knowledge flow shortly.

```
WS BENCH SUMMARY
Outcome: OK
Target: ws://localhost:8000/agentic/v1/chatbot/query/ws
Agent ID: Rico
Total requests: 200
Concurrent clients: 20
Requests per client: 10
Success: 200 (100.00%)
Errors: 0
Elapsed: 31.816s
Requests/sec: 6.29
Latency ms (min/avg/p50/p95/p99/max): 757/2072/1877/6402/6637/6690
```

This is much better but far being good enough of course. WIth two workers (i.e. two knowledge-flow instance) you get:

```
WS BENCH SUMMARY
Outcome: OK
Target: ws://localhost:8000/agentic/v1/chatbot/query/ws
Agent ID: Rico
Total requests: 200
Concurrent clients: 20
Requests per client: 10
Success: 200 (100.00%)
Errors: 0
Elapsed: 28.259s
Requests/sec: 7.08
Latency ms (min/avg/p50/p95/p99/max): 701/1504/1254/2161/6401/6464
```

As expected the latency is better of course. So bootom line the current fred architecture is ok, but will be only fully production ready
after knowledge-flow will be fully async up to langchain adapters and opensearch (and others) clients.
