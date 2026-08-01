# ISSUE-009 - knowledge-flow-worker: reference-cycle memory growth, confirmed via live gc.collect()+malloc_trim(0) tests

Status: open (mitigation deployed and live-validated; root cause — which object graph is
cyclic — not yet isolated)
Owner: Dimitri Tombroff
Target window: same day as ISSUE-006/007/008, found while live-validating those three fixes

## Problem
Even with `ISSUE-006`/`007`/`008` deployed together, the worker's memory still does not return
to a low baseline at idle, and the post-batch baseline climbs across repeated delete+re-ingest
cycles (matches Sébastien's report on a separately deployed, equally patched platform — see
`ISSUE-007`'s background). A `SIGUSR1` diagnostic handler (forces `gc.collect()` +
`malloc_trim(0)`, logs the RSS delta) was added and triggered live on fredlab twice:

- After ~1 document + idle: `gc.collect()` freed 1930 objects, `0 uncollectable in gc.garbage`,
  RSS 2310584Ki -> 2044420Ki (**~260MB freed**).
- After two batches (~30 documents total): `gc.collect()` freed 8803 objects, still
  `0 uncollectable`, RSS 4408952Ki -> 2713464Ki (**~1.65GB freed**).

`0 uncollectable in gc.garbage` both times is the key fact: this is not a hard leak (something
still holding a live reference forever) and not native/onnxruntime memory outside Python's reach
— it is genuine Python reference-cycle garbage that plain refcounting never frees, but a full
`gc.collect()` cleans up correctly every time it's asked to. The amount freed scales with
documents processed, matching the "grows with volume, not concurrency" signature from
`ISSUE-006`/`007`.

## Why it matters
- Confirms the three caching fixes (`006`/`007`/`008`) were real and necessary but not
  sufficient — something else on the ingestion path creates reference cycles at a rate
  proportional to document volume. Not yet identified *which* object graph.
- CPython's allocator does not return freed arenas to the OS on its own — `kubectl top`/cgroup
  RSS can keep climbing even while `gc.collect()` alone (without `malloc_trim`) is doing its job
  correctly. This nuance matters for any future diagnosis: don't conclude "GC isn't working" from
  RSS alone.

## Current evidence
- Live `SIGUSR1` trigger output (`knowledge_flow_backend/main_worker.py`, then
  `_debug_gc_and_trim`, since refactored into `_collect_and_trim`), fredlab, 2026-07-31, worker
  pod `knowledge-flow-worker-5774d7f88c-8ksb9`:
  ```
  [DEBUG][GC] SIGUSR1: gc.collect()=1930 freed, 0 uncollectable in gc.garbage, objects 1369042 -> 1365383, malloc_trim=True | RSS 2310584Ki -> 2044420Ki (delta 266164Ki)
  [DEBUG][GC] SIGUSR1: gc.collect()=8803 freed, 0 uncollectable in gc.garbage, objects 1376124 -> 1366851, malloc_trim=True | RSS 4408952Ki -> 2713464Ki (delta 1695488Ki)
  ```
- Live object count is large regardless (~1.37 million `gc.get_objects()`), of which only a
  small fraction (0.3-0.6%) is what `gc.collect()` reclaims each time — the cyclic garbage is a
  small, specific subset of a large live object graph, not "everything leaks."

## Scope
- Active paths: whatever on the medium-PDF ingestion path creates objects with reference cycles
  — not yet localized to a specific file/class. Candidates not yet ruled out: docling's own
  internal document graph (each `Document` object has parent/child references between
  pages/pictures/tables — a classic cycle shape — even though `del doc` is already called after
  export in `docling_processor.py:90`, `del` only drops one reference, it does not guarantee
  immediate collection of a cycle); Temporal SDK's own per-activity/per-workflow bookkeeping
  objects; asyncio task/future chains from `to_thread_with_heartbeat`.
- Not in scope: this issue does not attempt to identify the exact cyclic object graph — that is
  follow-up work. This issue covers the diagnostic proof and the interim mitigation only.

## Proposed fix (mitigation, not root cause)
- Applied: `_collect_and_trim()` + `SIGUSR1` handler (manual, always available) — see
  `ISSUE-008`'s branch history, extended here with **`_periodic_gc_loop()`**, an
  interval-driven background `asyncio.Task` in `main_worker.py`, matching the exact pattern
  already used for the two worker-side KPI tasks (`_start_worker_kpi_tasks`) in the same file.
- Opt-in via `KF_WORKER_GC_INTERVAL_SEC` (seconds; unset/`0` disables) — an env var, not YAML
  product config, matching `FRED_MODELS_CATALOG_FILE`'s precedent for deployment-level operational
  knobs vs. `app.*`/`observability.*` product configuration. Wired into
  `gcp-c1/argocd/fred-apps/templates/knowledge-flow-worker.yaml` as
  `knowledgeFlowWorker.gcIntervalSec`, set to `"300"` (5 min) on fredlab.
- Deliberately NOT gated on "worker idle" — this repo has no visibility into current activity
  concurrency from `main_worker.py`, and `gc.collect()`'s own cost is small next to a PDF
  conversion, so running unconditionally on a timer is simpler and was judged an acceptable
  trade-off over building idle-detection for a mitigation.

## Acceptance checks
- [x] Manual `SIGUSR1` trigger live-validated twice on fredlab, both times freeing substantial
      real memory with `0 uncollectable in gc.garbage`.
- [x] Full test suite passes (717/717) with the periodic task added.
- [ ] Periodic (5 min) automatic trigger not yet live-validated end-to-end on fredlab as of this
      writing (deploying now) — confirm it actually keeps the post-idle baseline flat across
      several more delete+re-ingest cycles, the same test that first surfaced this issue.
- [ ] Root cause: identify which object graph is cyclic. Candidate approach: `gc.collect(0)` /
      `gc.get_objects()` diffed before/after a single controlled document, or `objgraph`'s
      `show_backrefs`/`most_common_types` against the objects `gc.collect()` actually reclaims.

## Promotion
Promoted to: none — this is explicitly framed as a mitigation while the root cause is still open.
Once the cyclic object graph is identified and fixed at the source (removing the need for forced
GC entirely), `KF_WORKER_GC_INTERVAL_SEC` should default back to disabled and this periodic task
becomes dead code worth removing, not a permanent feature.
Notes: Companion to `ISSUE-006`/`007`/`008` — read together for the full day's investigation.
