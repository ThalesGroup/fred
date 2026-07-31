# ISSUE-007 - knowledge-flow: get_content_store() rebuilt on every call instead of cached

Status: open (fix implemented, pending live validation on fredlab)
Owner: Dimitri Tombroff
Target window: same day as ISSUE-006, follow-up hypothesis while validating that fix

## Problem
`ApplicationContext.get_content_store()` builds a fresh storage backend (in production,
`GcsContentStore` — a real `storage.Client()` with its own auth + HTTP connection pool via
`build_gcs_client()`) on **every call**, instead of caching one instance. Its two siblings in the
same class, `get_file_store()` and `get_log_store()`, are both already correctly cached
(`self._file_store_instance` / `self._log_store_instance`, build-once-and-reuse). This is
structurally the same class of bug as `ISSUE-006` (`PaddleOCRmodel` rebuilt per document) — a
factory method that should cache like its neighbors, but doesn't.

## Why it matters
- Raised because a real, patched (`v2.1.24`, includes ISSUE-006's fix) deployment on a separate
  platform ("S3NS") is still reported (Sébastien) to show a slow, sustained memory rise ending in
  OOM — meaning ISSUE-006's fix alone is not sufficient to fully close the leak.
- `get_content_store()` sits on a **much hotter path** than the OCR loop: it's called from
  `ingestion_service.py`, `content_service.py`, `metadata/service.py`, `tabular/service.py`, and
  others, several of them at `__init__` time of classes that are themselves NOT cached across
  Temporal activities the way `PdfMarkdownProcessor`/`DoclingPdfExtractor` are (via
  `get_input_processor_instance`/`get_output_processor_instance`, which *are* cached — but not
  every consumer of `get_content_store()` goes through that path).
- Live fredlab logs (2026-07-31 morning session) show `"[CONTENT][GCS] Initialized
  GcsContentStore"` firing repeatedly within a single document's pipeline (once around
  `PUSH_INPUT_PROCESS` completion, again before the next activity's restore step) — consistent
  with a rebuild per Temporal activity, not per pod.

## Current evidence
- `apps/knowledge-flow-backend/knowledge_flow_backend/application_context.py`
  (pre-fix, `get_content_store`, ~line 524): no cache check, three branches (`MinioStorageConfig`,
  `GcsStorageConfig`, `LocalContentStorageConfig`) each `return`ed a freshly constructed backend.
- Same file, `get_file_store()` (~line 574) and `get_log_store()` (~line 511): both check
  `self._file_store_instance` / `self._log_store_instance` first and cache on first build — the
  pattern `get_content_store()` should have had all along.
- `core/stores/content/gcs_content_store.py:87`: `GcsContentStore.__init__` calls
  `build_gcs_client(project_id)`, which constructs a `google.cloud.storage.Client()` — real
  ADC/Workload-Identity auth plus an HTTP connection pool, not a cheap object.
- 16 call sites of `get_content_store()` across the codebase (`grep`-confirmed); most are in
  `__init__` of services/controllers, a couple (`in_memory_scheduler.py`, `excel_processor.py`)
  call it inline mid-method.

## Scope
- Active paths: `ApplicationContext.get_content_store()` — affects every code path that resolves
  the GCS/Minio/local content store (ingestion, content serving, tabular, metadata, monitoring
  health checks, benchmark harness).
- Not in scope: whether every *consumer* of `get_content_store()` (e.g. `IngestionService`) is
  itself appropriately cached/singleton across activities — not audited here; this issue only
  covers the factory method itself, which was unconditionally wrong regardless.

## Proposed fix
- Applied: added `_content_store_instance: Optional[BaseContentStore] = None` class attribute and
  a cache check at the top of `get_content_store()`, assigning to it in all three branches instead
  of returning directly — exact mirror of `get_file_store()`'s existing structure. Regression test
  `test_get_content_store_builds_once_and_reuses_the_instance` added
  (`tests/core/test_content_store_factory_gcs.py`), asserting identity across two calls.

## Acceptance checks
- [x] Unit tests pass, no regressions (715/715, full `knowledge-flow-backend` suite).
- [ ] Live validation on fredlab: deploy as a hotfix (branch `fix/gcs-content-store-cache`,
      already includes ISSUE-006's fix since branched off `swift` post-merge), repeat
      delete+re-ingest cycles, watch whether the worker's post-batch memory baseline stays flat
      across cycles instead of creeping up — the specific signature ISSUE-006's own validation
      didn't rule out (see its "Longer-running / larger-batch validation" open item).
- [ ] If growth persists even with both fixes: next suspects are the other 15 call sites of
      `get_content_store()` (check whether their *own* container class is cached across
      activities) and `IngestionService`'s own lifecycle, not yet audited here.

## Promotion
Promoted to: none — fix implemented and unit-tested, live validation in progress on fredlab
(hotfix path, see `gcp-c1/argocd/README.md`'s `bin/fredlab-hotfix.sh` section in
`fred-deployment-factory`). Will update to `done` once confirmed, or reopen scope if the leak
persists.
Notes: Companion to `ISSUE-006` — read together, not standalone. `ISSUE-006`'s "Promotion" section
notes fredlab's `values-fredlab.yaml` should point back at a real ghcr.io release once this ships;
same applies here once merged.
