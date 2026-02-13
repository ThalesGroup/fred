# Bench snapshot (2026-02-11)

This captures the current local bench state so future work can restart from known numbers.

## Setup
- Laptop: Dell, 32 GB RAM, single Agentic pod (uvicorn single worker), mock LLM fixed ~3 s latency.
- Config deltas (bench):
  - `pool_size=20`, `max_overflow=10`, `pool_timeout=100`, `synchronous_commit=off` inside persist.
  - Fire-and-forget persist (async task), but still measuring persist timings.
  - Ramp-up: 10 s across all clients (default in ws_bench now).
  - HTTP client limits: chat model max_connections=100 (keepalive disabled).
- Instruments added:
  - Gauges: `persist_pool_wait_ms`, `persist_sql_ms`, `event_loop_lag_ms` (shown in KPI summary).
  - Per-run detailed logging is at DEBUG.

## WS bench results
Mode: per-client; each client reuses its session for N turns; create/delete session per client.

### 10 clients × 3 turns (illustrative)
- Requests/sec: ~20
- Latency (p95): ~3.0 s (essentially the mock LLM floor)
- persist_tx avg: ~3 ms
- CPU ~7%, RSS ~312 MB

### 100 clients × 20 turns
- Requests/sec: 21.4
- Latency ms (min/avg/p50/p95/p99/max): 3049 / 4125 / 4125 / 4618 / 5455 / 6448
- persist_tx (KPI): avg ~1.1–1.6 s (see instrumentation section for breakdown)

### 150 clients × 20 turns
- Requests/sec: 22.1
- Latency ms (min/avg/p50/p95/p99/max): 3045 / 6136 / 6315 / 7271 / 7592 / 8087
- Earlier run (150×10) after fire-and-forget: p95 ~7.9 s, p99 ~9.4 s

## Persist breakdown (instrumented)
- At high load (150 clients):
  - `persist_pool_wait_ms` avg ~90–170 ms (max ~1.3 s)
  - `persist_sql_ms` avg ~440–980 ms (max ~1.7 s)
  - `persist_tx` timer aligns with these (~0.7–1.6 s avg)
- At low load (10 clients):
  - pool_wait ~0 ms, sql_ms ~0.6–1.0 ms; persist_tx ~3 ms

## Postgres sanity (pg_stat_statements)
After a 150-client run:
- `INSERT INTO session_history … ON CONFLICT …`  mean ~0.098 ms (max 0.47 ms) over 1 500 calls
- `INSERT INTO session … ON CONFLICT …`         mean ~0.077 ms (max 0.58 ms) over 1 650 calls
- `SELECT count(*) FROM session WHERE user_id…`  mean ~0.057 ms
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

| queryid | calls | mean_ms | min_ms | max_ms | rows | snippet |
| --- | --- | --- | --- | --- | --- | --- |
| 7637388399052348591 | 1500 | 0.098 | 0.026 | 0.466 | 3000 | INSERT INTO session_history … |
| 6356258841006377401 | 1650 | 0.077 | 0.024 | 0.584 | 1650 | INSERT INTO session … |
| 6271241136561251085 | 150  | 0.057 | 0.011 | 0.184 | 150  | SELECT count(*) FROM session WHERE … |
| -5035404056216960644| 150  | 0.039 | 0.014 | 0.101 | 150  | DELETE FROM session … |
| 813870921486209613  | 150  | 0.029 | 0.011 | 0.087 | 0    | SELECT session_history … |
| -8455873564438631297| 150  | 0.018 | 0.005 | 0.077 | 0    | SELECT session_attachments … |
| -3843513667560893647| 150  | 0.006 | 0.002 | 0.014 | 0    | DELETE FROM session_attachments … |

Notes: pg_stat_statements was enabled via shared_preload_libraries; we reset stats, ran the bench, then ran the query above. These timings confirm the DB itself is not the source of the 700–1300 ms “persist” wall time seen in the app (that is event-loop contention).

Conclusion: DB execution is sub-ms; the ~700–1000 ms “sql” wall time is event-loop/scheduling/queuing, not Postgres.

## Current instrumentation
- Gauges emitted and now in KPI summary: `persist_pool_wait_ms`, `persist_sql_ms`, `event_loop_lag_ms`.
- Persist block still sets `SET LOCAL synchronous_commit TO OFF`.
- Loop-lag probe runs every 100 ms.

## Next investigative steps (if resumed)
- Compare with uvloop or multi-worker uvicorn to see impact on persist_* times.
- Split LLM invoke into queue vs roundtrip if needed (not yet done).
- Consider batching history rows (currently one upsert per row) if backend changes are allowed.
