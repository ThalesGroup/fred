# Chat model picker — runtime-binding load test and 5,000-user extrapolation

- **Date:** 2026-10-09
- **Branch:** `feat/chat-model-and-reasoning-picker` (#3029), OpenSpec change
  `chat-model-and-reasoning-picker`, tasks 7.7 and 7.7b
- **Verdict:** PASS WITH FINDINGS. The branch is faster than `swift` on every
  measured axis. The remaining finding (F1) predates the branch.
- **Status:** evidence recorded. F1 and F2 are tracked in #3031; this branch
  does not change them.

## Context

The control plane runs `get_runtime_binding_for_team`
(`product/service.py`) once per managed agent turn: the pod calls it, the
control plane reads the database, and the result returns to the pod. Three
shapes were compared:

| Shape | Where it comes from | Pooled sessions per turn | Critical path |
|---|---|---:|---|
| OLD-4 | `origin/swift` | 5 (1 instance read, then 4 reads in parallel) | 2 stages |
| OLD-5 | branch before B7 (added the `team_routing_policy` PK read) | 6 (1, then 5 in parallel) | 2 stages |
| NEW-2 | current branch (B7) | 2 in parallel, 3 sequential reads each | 1 stage |

Opening a chat also runs the §41 effective-chat-model read once. The branch
adds `selectable_models` to that read, which is in-memory work only. The
`team_routing_policy` read was already in the §41 read on `swift`. The branch
runs it in parallel with `usable_capability_ids`, which removes one sequential
step.

## Method

The full managed-SSE campaign (`fred-performance-campaign-runner`) could not
run on this machine: there is no mock LLM server, no Go and no token. The
owner approved this targeted test instead.

- **Real:**
  - the control-plane async engine, built by `fred_core`'s
    `create_async_engine_from_config` from the developer's control-plane
    config;
  - the real store classes and their queries;
  - the dev `fred` Postgres (`app-postgres`), using all 24 real
    `agent_instance` rows.
- **NEW-2:** calls the real `get_runtime_binding_for_team`. The deps object
  contains only the collaborators that function uses. Its session factory is
  `make_session_factory(engine)`, the same as `build_product_service_dependencies`.
- **OLD-4 and OLD-5:** reproduce the old shapes using the same store methods
  without a shared session. Each read opens its own pooled session, as on
  `swift`. Both build the same `ManagedAgentRuntimeBinding`.
- **Not exercised (the same for all shapes):**
  - the pod → control-plane HTTP hop;
  - the endpoint's OpenFGA check (TURN-01);
  - other control-plane traffic that shares the pool.
- **Read-only:** every connection sets `default_transaction_read_only=on`, so
  the test cannot write to the database.
- **Instrumentation:**
  - pool acquisition time, including queue wait and new connections, by
    wrapping `QueuePool._do_get`;
  - peak connections in use, from the `checkout`/`checkin` events;
  - new connections, from the `connect` event;
  - pool timeouts.
- **Load shapes:**
  - bursts of N ∈ {1, 10, 25, 50, 100, 200, 500} simultaneous turns, 3
    repetitions after a warm-up (tables show the median);
  - Poisson arrivals at λ ∈ {5, 17, 50, 100} turns/s for 30 s each.
- **Network delay:** a separate-process TCP proxy adds latency, for a
  pessimistic-RTT replay. Its calibrated effective added RTT is **+3.3 ms**
  (measured with a cached `SELECT 1`), above the requested 1–2 ms because of
  event-loop timer granularity. The 1–2 ms case is derived from round-trip
  counts in the Extrapolation section below.
- **Microbenchmark:** the post-I/O block of the §41 read, using the real
  `resolve_effective_chat_profile`, `SelectableChatModel` and
  `EffectiveChatModel`, plus JSON serialization.
- **Artifacts:** scripts and raw JSON are in the session scratchpad (`perf3029/`:
  `loadtest.py`, `rtt_proxy.py`, `results_*.json`), not committed.

## Environment

These are facts about the test machine, not production.

- One laptop: 8 cores, 31 GB RAM, about 31% available during the runs, with
  swap nearly full. Postgres 250 `max_connections` in Docker, reached through
  the published port.
- Direct database round trip: 0.25 ms. A new pooled connection costs 20 ms
  alone and about 100 ms when 10 open at once.
- Pool settings are the production values: the control-plane config and the
  chart set no override, so `fred_core` defaults apply.
  - `pool_size=5`
  - `max_overflow=10` (15 connections at most)
  - `pool_timeout=30` s
  - `pool_pre_ping=True`
  - `recycle=-1`
- Chart defaults: control-plane `replicaCount: 1`, a single uvicorn process.

## Results

All latencies are for one binding call, in ms. There were no errors and no
pool timeouts in any run. The peak was the pool ceiling: 15 connections by
default, 25 with `pool_size=15`.

Single call, no concurrency (300 calls):

| Shape | p50 | p95 |
|---|---:|---:|
| OLD-4 | 9.0 | 12.2 |
| OLD-5 | 7.9 | 12.9 |
| **NEW-2** | **5.6** | **7.4** |

Bursts, production pool (5+10). Each cell is p99 ms, then turns/s in
parentheses:

| N | OLD-4 | OLD-5 | NEW-2 |
|---:|---:|---:|---:|
| 10 | 153 (64) | 159 (62) | 169 (59) |
| 50 | 271 (174) | 341 (138) | **222 (224)** |
| 200 | 738 (259) | 874 (220) | **517 (381)** |
| 500 | 1696 (286) | 2030 (231) | **1210 (407)** |

At N ≥ 10 every shape needs more than the pool's 15 connections and opens
overflow connections, so the bursts measure queueing.

Sustained Poisson load. Each cell is p95 / p99 ms; the acquire wait and peak
connections are for NEW-2:

| λ (turns/s) | Pool | OLD-4 | OLD-5 | NEW-2 | NEW-2 acquire p99 | NEW-2 peak conns |
|---:|---|---:|---:|---:|---:|---:|
| 5 | 5+10 | 70 / 84 | 106 / 115 | **25 / 28** | 0.03 | 4 |
| 17 | 5+10 | 104 / 140 | 143 / 171 | **36 / 77** | 31 | 6 |
| 50 | 5+10 | 152 / 183 | 169 / 199 | **111 / 140** | 86 | 15 |
| 100 | 5+10 | 141 / 175 | 150 / 186 | **130 / 149** | 101 | 15 |
| 17 | 15+10 | 37 / 46 | — | **25 / 31** | 0.02 | 6 |
| 50 | 15+10 | 58 / 125 | — | **29 / 36** | 0.02 | 10 |
| 100 | 15+10 | 135 / 163 | — | **48 / 93** | 31 | 22 |

With +3.3 ms RTT added by the proxy (two runs, shown as ranges):

| Case | OLD-4 | OLD-5 | NEW-2 |
|---|---:|---:|---:|
| Single call, latency added by the RTT | +28–30 (~8.5 round trips) | +35–41 | **+20.5 (~6.2 round trips)** |
| λ=17, pool 15+10, p95 / p99 | 61–72 / 89–136 | 78–84 / 104–117 | **43–50 / 48–52** |
| λ=50, pool 15+10, p95 / p99 | 131–163 / 162–191 | 161–178 / 190–209 | **45–52 / 52–66** |
| λ=17, pool 5+10, p95 / p99 | 195 / 213 | 212 / 249 | **103 / 133** |
| λ=50, pool 5+10, p95 / p99 | 191 / 225 | 219 / 245 | **153 / 169** |

The §41 microbenchmark is in-memory work on one chat open, not on a turn:

| Models in the pod catalog | Branch (µs) | `swift`-like (µs) | Added (µs) | Response bytes |
|---:|---:|---:|---:|---:|
| 5 | 9.9 | 2.7 | 7.2 | 935 |
| 20 | 27.7 | 3.8 | 23.9 | 2,961 |
| 50 | 62.5 | 5.9 | 56.6 | 6,885 |

## Round trips and RTT sensitivity

These counts are derived from the code and confirmed by the RTT replay.

A session that runs its own reads costs these round trips: pre-ping, `BEGIN`,
one round trip per query, then `COMMIT`.

| Shape | Round trips on the critical path | Round trips in total | Connection time per turn at 2 ms RTT |
|---|---|---:|---:|
| OLD-4 | 8 (4 for the instance read + 4 for the parallel stage) | 20 | ~40 conn·ms |
| OLD-5 | 8 | 24 | ~48 conn·ms |
| NEW-2 | 6 (pre-ping, `BEGIN`, 3 reads, `COMMIT`) | 12 | ~24 conn·ms |

The hypothesis was that "sequential reads are more RTT-sensitive". It does not
hold here. NEW-2 replaces the old sequential instance stage, so it adds
**+6 ms at 1 ms RTT and +12 ms at 2 ms**. OLD-4/5 add +8 ms and +16 ms. The
replay at +3.3 ms measured about 6.2 vs about 8.5 round trips.

## Extrapolation to 5,000 online users

All figures in this section are derived values. The assumptions are
conservative.

| # | Assumption | Value |
|---|---|---|
| A1 | Share of online users in an active conversation | 20% → 1,000 users |
| A2 | Turns per active user per minute (includes reading and streaming) | 1 |
| A3 | Burst factor for a p99 minute / a stress peak | ×3 / ×6 |
| A4 | Control-plane replicas, uvicorn processes, pool per process | 1, 1, 5+10 (chart and `fred_core` defaults) |
| A5 | fred-agents replicas | 4. All of them call the same control plane, so this changes nothing for this pool |
| A6 | Other control-plane traffic on the same pool | Not measured, so keep at least 2× headroom |

These give:

- **average:** 1,000 turns/min ≈ **17 turns/s**;
- **p99 burst:** **50 turns/s**;
- **stress:** **100 turns/s**.

Reading these rates against the measurements, with the production pool (5+10):

- **17 turns/s:** NEW-2 has p95 36 ms and p99 77 ms. Its peak is already 6
  connections, so it uses the overflow and pays for new connections in the
  tail. OLD-4 was at 104 ms and 140 ms.
- **50 turns/s:** the pool is saturated (15 connections). NEW-2 has an acquire
  p99 of 86 ms and a binding p99 of 140 ms, with no timeouts: the 30 s
  `pool_timeout` is far away.
- **100 turns/s:** every shape converges at about 130–150 ms p95.
- **With 1–2 ms network RTT:** add +6–12 ms to NEW-2's critical path. Each
  connection is held for about twice as long. At λ=50 that is about 1.2
  connections busy on average before burstiness, about 2.0 for OLD-4.
- **With `pool_size=15`:** NEW-2 stays without waits up to 50 turns/s (p99
  36 ms locally, 52–66 ms at +3.3 ms RTT). At 100 turns/s it reaches p99 93 ms.

Compared with an LLM turn that takes several seconds, even the saturated case
is small (< 0.2 s). The real risk is that the binding call shares the pool
with the rest of the control plane (A6). There, overflow churn and saturation
make other routes wait.

## Findings

These go in priority order. None of them blocks this branch.

- **F1 — control-plane pool sizing (P2, existed before the branch,
  configuration only).**
  - **Problem:** the defaults of 5+10 are below steady demand from about
    17 turns/s. QueuePool closes each overflow connection when it is returned,
    so the pool opens and closes connections all the time. Each new connection
    costs 20–100+ ms on the event loop, including SCRAM and asyncpg codec
    setup.
  - **Fix:** set `storage.postgres.pool_size` to about 15–20 (keep
    `max_overflow` at 10) for the control plane, in the chart values and the
    schema.
  - **Check first:** Postgres `max_connections` across all replicas and
    services.
  - **Tracking:** #3031 (separate issue and PR, scope discipline).
  - **Related:** TURN-06 covers the same concern on the pod side.
- **F2 — one control-plane replica takes every turn's binding (P2, existed
  before the branch).**
  - **Problem:** one process and one pool serve the 4 fred-agents replicas.
  - **Fix:** size the replica count and the pool together, from a
    representative campaign.
- **F3 — the dominant per-turn cost was not measured here (P1, existed before
  the branch).**
  - **Problem:** TURN-01's ReBAC fan-out (about 21 OpenFGA operations per
    binding) and the HTTP hop sit in front of these database reads.
  - **Next step:** the managed-SSE campaign on a machine with the mock LLM
    server is still the evidence to collect for a 5,000-user claim. The
    owner decided it is not needed for this change.
- **Kept as is: NEW-2.** It is no regression. Compared with OLD-4, NEW-2 has:
  - 2.5× fewer connections per turn;
  - about 40% more burst throughput;
  - lower p95/p99 at every λ;
  - 2 fewer round trips on the critical path.

  OLD-5 would have been a regression of about +10–50% at p95.

## Static review (task 7.7, `fred-performance-reviewer` checklist)

| Code path | Async end-to-end? | New I/O | KPI/label change | Verdict |
|---|---|---|---|---|
| Runtime-binding read (per turn) | yes | +1 PK read, inside the 2 shared sessions | none | healthy (measured above) |
| `agent_app` pass-through of `team_disabled_model_ids` / recommendation | yes | none | none | healthy |
| `RoutedChatModelFactory.select` / `_accepted_choice` (pod, per turn) | pure | none (tuple/set lookups) | log source values only, no Prometheus label | healthy |
| §41 effective-chat-model (chat open) | yes | none new; the policy read now runs in parallel with `usable_capability_ids` | none | improved |
| Disable-impact (admin) | yes | 1 team-scoped query + the deduplicated catalog fetch | none | healthy |
| Policy write (admin) | yes | 1 UPDATE per cleared row, team-scoped `FOR UPDATE` | none | acceptable (rare admin action) |
| `apply_model_revocation` (platform admin) | yes | sequential per-team OpenFGA check and write; `LIKE` scan on `team_routing_policy` | none | P3 note: N+1 across teams, admin-only and rare |

The checklist found the following:

- no blocking call, `time.sleep`, `.result()` or new HTTP client in the diff;
- no new module-level state;
- `PROMETHEUS_ALLOWED_LABELS` is unchanged.

The row locks taken by the policy write do not block the per-turn binding,
which uses a plain MVCC `SELECT`. There is no blocking or hot-path N+1
finding.
