# ISSUE-010 - fred-core: KPIEvent.labels (Iterable[str]) creates a reference cycle via pydantic-core's ValidatorIterator

Status: done (fix + regression test; pending live validation on fredlab)
Owner: Dimitri Tombroff
Target window: same day as ISSUE-006/007/008/009, root cause of the reference-cycle growth ISSUE-009 mitigated but didn't explain

## Problem
`KPIEvent.labels` (`libs/fred-core/fred_core/kpi/kpi_writer_structures.py:170`) was typed
`Iterable[str]`. pydantic-core does not eagerly cast `Iterable[X]` fields to a concrete
collection — it wraps *any* input, including an already-materialized `list`, in a
`ValidatorIterator` that validates lazily as consumed. `KPIWriter.emit()`
(`libs/fred-core/fred_core/kpi/kpi_writer.py:208`) always passes `labels=list(labels or [])` — a
real list — so the lazy-iterable typing bought nothing here and cost a reference cycle on every
`KPIEvent` construction.

Found via a `gc.DEBUG_SAVEALL` diagnostic (`SIGUSR2` handler, `ISSUE-009`) triggered live on
fredlab: a fresh sample of collected-but-uncollectable-by-refcounting garbage showed `Metric` and
`ValidatorIterator` in exactly matching counts (24 each), alongside matching `dict`/`list`/
`list_iterator`/`set` counts — one `KPIEvent` (containing one `Metric`) is built per KPI emission,
and each construction manufactured exactly one `ValidatorIterator` for `labels`.

## Why it matters
- This is the root cause `ISSUE-009` mitigated but did not identify: real, live-confirmed
  reference-cycle garbage (`0 uncollectable in gc.garbage`, i.e. genuinely freed by `gc.collect()`
  every time, never a hard leak) that scaled with KPI-emission volume — which scales with
  document/activity volume, matching every growth pattern observed today.
- `emit()` is called from many activity/document-scoped sites (confirmed:
  `knowledge_flow_backend/features/scheduler/kpi_utils.py:60,241`,
  `knowledge_flow_backend/features/ingestion/ingestion_controller.py:634` — once per ingested
  document) — this is fred-core, shared by every app (control-plane, fred-agents,
  knowledge-flow, evaluation), so the same cycle fires on every KPI emission across the whole
  platform, not just knowledge-flow's ingestion path.

## Current evidence
- Live `SIGUSR2` type breakdown (fredlab, 2026-07-31, worker pod
  `knowledge-flow-worker-67c88cfbb8-glcml`):
  `dict(26), ValidatorIterator(24), Metric(24), list(24), list_iterator(24), set(24), ...`
- `libs/fred-core/fred_core/kpi/kpi_writer_structures.py` (pre-fix, line 170):
  `labels: Iterable[str] = Field(default_factory=list)`.
- `KPIEvent.to_doc()` (same file, ~line 180) already does `list(self.labels or [])` when
  serializing — the field is materialized into a concrete list at BOTH construction time
  (`emit()`) and read time (`to_doc()`); the `Iterable` typing was never exercised as an actual
  lazy iterable anywhere in this codebase.
- Regression test added: constructing 200 `KPIEvent`s and calling `gc.collect()` returned 0
  before nothing was left to free (post-fix) vs. 48 objects reclaimed by a forced collection with
  the field reverted to `Iterable[str]` (confirmed by manually reverting and re-running the test,
  then restoring the fix).

## Scope
- Active paths: every `KPIEvent` construction, i.e. every `KPIWriter.emit()`/`.counter()`/
  `.gauge()`/`.timer()` call across every fred app using `fred-core`'s KPI writer — not scoped to
  knowledge-flow-backend.
- Not in scope: whether other `fred-core` models have the same `Iterable[X]`-typed-but-always-
  passed-a-list pattern elsewhere — not audited here, worth a follow-up grep
  (`grep -rn "Iterable\[" libs/fred-core`) if this class of bug is suspected to recur.

## Proposed fix
- Applied: `KPIEvent.labels` retyped `Iterable[str]` -> `List[str]`
  (`libs/fred-core/fred_core/kpi/kpi_writer_structures.py:170-177`). Zero behavior change — every
  call site already passed a concrete list; this only changes pydantic-core's validation strategy
  from lazy (iterator-wrapped) to eager (direct list validation), which is what was already
  happening in practice at both ends.
- Regression tests added (`libs/fred-core/fred_core/tests/kpi/test_kpi_writer_structures.py`):
  one asserting `type(event.labels) is list`, one asserting `gc.collect()` finds nothing to
  reclaim after constructing and dropping 200 `KPIEvent`s — the direct regression test for the
  cycle itself, not just the type.

## Acceptance checks
- [x] New regression tests pass post-fix, fail pre-fix (manually verified both directions).
- [x] Full `fred-core` test suite passes (399/399).
- [x] Full `knowledge-flow-backend` test suite passes (717/717) with the updated `fred-core`.
- [ ] Live validation on fredlab: deploy as a hotfix on top of `ISSUE-006`/`007`/`008`/`009`
      (same branch, `fix/gcs-content-store-cache`), confirm via `SIGUSR1`/`SIGUSR2` that the
      reference-cycle growth is gone or substantially reduced, and that
      `KF_WORKER_GC_INTERVAL_SEC`'s periodic mitigation now finds little-to-nothing to collect —
      at which point it can be turned back off, since it was explicitly a stopgap for this.

## Promotion
Promoted to: none — fix implemented and unit-tested, live validation in progress. This is the
first of today's five fixes/mitigations expected to actually close the loop (006/007/008 fixed
real-but-partial leaks, 009 was an explicit mitigation, this one is the root cause of what 009's
diagnostics kept finding). Once confirmed live, `ISSUE-009`'s periodic GC mitigation
(`KF_WORKER_GC_INTERVAL_SEC`) should be reconsidered — it may no longer be needed, or needed at a
much longer interval — rather than left permanently on for a leak that's actually fixed.
Notes: Companion to `ISSUE-006` through `009` — this whole investigation reads best in order.
