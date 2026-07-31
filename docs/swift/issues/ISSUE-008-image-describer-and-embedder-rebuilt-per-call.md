# ISSUE-008 - knowledge-flow: image describer + embedder rebuilt per call (same pattern as ISSUE-006/007)

Status: open (fix implemented, pending live validation on fredlab)
Owner: Dimitri Tombroff
Target window: same day as ISSUE-006/007, found by a systematic audit of the whole medium-PDF
ingestion path after those two fixes

## Problem
Two more `get_*`/`build_*` factories construct a real provider client on every call instead of
caching one instance — the same shape as `ISSUE-006` (`PaddleOCRmodel`) and `ISSUE-007`
(`get_content_store()`):

1. `PdfMarkdownProcessor._extract_md()` called `build_image_describer(vision_model)` inline, in
   the **same method**, right below `_get_extractor()`/`_get_ocr_model()` — both already fixed
   for exactly this reason.
2. `ApplicationContext.get_embedder()` was the **one** `get_*` factory in that class with no cache
   slot — every sibling (`get_file_store`, `get_content_store`, `get_log_store`, `get_metadata_store`,
   `get_tag_store`, `get_resource_store`, `get_opensearch_client`, `get_task_service`,
   `get_filesystem`, `get_kpi_writer`, `get_rebac_engine`, `get_vector_store`, `get_pg_async_engine`)
   was already correctly cached.

Found via a dedicated audit agent asked to check every other `ApplicationContext` getter and walk
the full medium-PDF ingestion call graph for the same "should cache, doesn't" shape, prompted by
Sébastien's report that a separately deployed, patched (`v2.1.24`) platform ("S3NS") still shows a
slow, sustained memory rise ending in OOM — meaning `ISSUE-006` alone wasn't sufficient.

## Why it matters
- **Image describer**: for Vertex AI / Vertex AI Model Garden providers specifically, `fred-core`'s
  `get_model()` factory does not pass the shared process-wide `httpx` client pool the way it does
  for OpenAI/Azure — each Vertex-backed model construction builds its own auth + connection pool.
  Dormant under the shipped default (`process_images: false` in every bundled `medium` config), but
  one config flag away from firing on every single document — same real-client-per-call shape as
  the already-fixed `GcsContentStore` bug, just gated off today.
- **Embedder**: called per-activity from `fast_store_vectors`, `delete_vectors`, `get_chunk_count`,
  `delete_fast_vectors` and similar in `features/scheduler/activities.py` and
  `in_memory_scheduler.py` — not just once at startup. For Vertex-backed embedding configs, same
  construct-and-discard-a-real-client cost on every one of those activity invocations.

## Current evidence
- `apps/knowledge-flow-backend/knowledge_flow_backend/core/processors/input/pdf_markdown_processor/pdf_markdown_processor.py`
  (pre-fix, `_extract_md`, ~line 238): `image_describer = build_image_describer(vision_model)`,
  unconditional on `profile_cfg.process_images and vision_model`, called before extraction even runs
  — so once per `_extract_md` invocation, i.e. once per document processed.
- `libs/fred-core/fred_core/model/factory.py` (`get_model()`, ~lines 420-540): `ChatGoogleGenerativeAI`,
  `VertexModelGardenMistral`/`Llama`, `ChatAnthropicVertex` each build their own httpx/gRPC client +
  GCP auth on construction; no shared-pool kwarg is threaded through for these providers (contrast
  with the OpenAI/Azure path, which does reuse `get_shared_stack()` from
  `libs/fred-core/fred_core/model/http_clients.py`).
- `apps/knowledge-flow-backend/knowledge_flow_backend/application_context.py` (pre-fix,
  `get_embedder`, ~line 609): no cache check, called `get_embeddings(cfg)` directly every time.
  Every other `get_*_store`/`get_*_client`/`get_*_engine` method in the same class already checks
  a `self._xxx_instance` slot first (confirmed by a full read-through of every getter in the class).
- Call sites confirming per-activity (not per-pod) frequency: `features/scheduler/activities.py`
  (`fast_store_vectors`, `fast_delete_vectors`, `get_chunk_count`, `delete_vectors`) and
  `features/scheduler/in_memory_scheduler.py` (`store_fast_vectors`, `delete_fast_vectors`).

## Scope
- Active paths: `PdfMarkdownProcessor._extract_md()`'s image-describer construction (gated on
  `process_images`, currently off by default); `ApplicationContext.get_embedder()` (always active,
  called from multiple scheduler activities regardless of PDF vs. other file types).
- Not in scope / confirmed fine by the same audit (see its full report for detail): every other
  `ApplicationContext` getter (all correctly cached); `IngestionService` (proper singleton);
  `DoclingPdfExtractor`'s internal docling pipeline (vendored source confirmed it releases native
  pdfium handles per document, does not accumulate); temp-dir cleanup on the Temporal activities
  behind push/output processing (all use `with tempfile.TemporaryDirectory(...)`, cleaned up on
  every exit path).

## Proposed fix
- Applied: `_get_image_describer()` added to `PdfMarkdownProcessor`, exact same lock-guarded
  single-instance pattern as `_get_ocr_model()`/`_get_extractor()` in the same class.
- Applied: `ApplicationContext.get_embedder()` now checks/sets `self._embedder_instance`, same
  pattern as every sibling getter in the class.
- Regression tests added for both: `test_pdf_processor_builds_image_describer_only_once_across_documents`
  and `test_get_embedder_builds_once_and_reuses_the_instance`, both asserting identity across
  repeated calls, mirroring the tests already added for `ISSUE-006`/`ISSUE-007`.

## Acceptance checks
- [x] Targeted tests pass (14/14 across both touched test files); full-suite run still pending as
      of this writing (deploy-first, test-after per operator direction to save time — see Promotion).
- [ ] Live validation on fredlab: hotfix image built from this same branch
      (`fix/gcs-content-store-cache`, now carrying all three fixes — ISSUE-006 was already merged
      to `swift` before this branch was cut, ISSUE-007 and this issue are both on it), repeated
      delete+re-ingest cycles, watching whether the post-batch memory baseline stays flat across
      cycles.
- [ ] `process_images`/vision-model-enabled ingestion specifically not yet tested live anywhere
      (dormant under every bundled config) — worth an explicit test with that flag on, since it's
      the one finding here not exercised by today's default-config testing at all.

## Promotion
Promoted to: none — bundled into the same hotfix branch/deploy as `ISSUE-007`, live validation in
progress. Operator explicitly chose to deploy this build before running the full test suite
("mieux vaut peut-être déployer rapidement avec tous les fixes puis tester code quality etc
après") — full-suite confirmation to be added to this issue once run.
Notes: Companion to `ISSUE-006`/`ISSUE-007` — same root-cause family (uncached per-call factory
constructing a real client), found by deliberately auditing for repeats of that exact shape rather
than waiting for another live OOM to surface each one individually.
