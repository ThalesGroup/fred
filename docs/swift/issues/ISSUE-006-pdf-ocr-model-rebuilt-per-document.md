# ISSUE-006 - knowledge-flow-worker OOM: PaddleOCRmodel rebuilt per document instead of cached

Status: done (fix on branch `fix/memory-leak-1`, not yet merged to `swift`)
Owner: Dimitri Tombroff
Target window: fixed 2026-07-31, same day as reported

## Problem
`PdfMarkdownProcessor._extract_md()` built a fresh `PaddleOCRmodel()` — which loads two ONNX
Runtime inference sessions (detection + recognition) from disk — on every single document with
OCR-eligible images, instead of reusing one instance across documents. `DoclingPdfExtractor`,
built in the same class, was already correctly cached for the same reason. This is a separate bug
from the `fitz.Document` handle leak fixed in `569d08e6` (2026-07-30): that fix covers the
`pymupdf` extractor path; this one is in the OCR/VLM image loop shared by every extractor whenever
`use_ocr=True`.

## Why it matters
- Reproduced live on fredlab (`medium` profile, docling extractor, OCR on): worker memory grew
  with total documents processed, not with concurrency (`ingestion_max_concurrent_activities: 3`
  caps real parallelism, but memory kept climbing past 30+ documents regardless).
- OOMKilled the worker pod even after raising its memory limit 3Gi → 5Gi — the extra headroom only
  delayed the crash, `exitCode 137`/`OOMKilled` at 06:49:20Z 2026-07-31.
- Independent of the leak, rebuilding two ONNX sessions from disk per document is wasted latency on
  top of legitimate inference cost — a likely contributor to slow ingestion throughput.

## Current evidence
- `apps/knowledge-flow-backend/knowledge_flow_backend/core/processors/input/pdf_markdown_processor/pdf_markdown_processor.py`
  (pre-fix, line ~251): `ocr_model = PaddleOCRmodel()` inside `_extract_md`'s OCR/VLM loop, called
  once per document.
- Same file, `_get_extractor`/`_extractor_cache` (line ~154): the docling extractor equivalent,
  already lock-guarded and cached, with a comment explaining exactly why per-document rebuilds are
  costly — no equivalent existed for the OCR model.
- Live fredlab logs: two `Creating model: (...)` lines (`PP-OCRv6_tiny_det`,
  `latin_PP-OCRv5_mobile_rec`) per document during `image OCR/VLM loop starting`, for every
  document processed.
- `kubectl get pod -o json` on the OOMKilled pod: `lastState.terminated.reason: OOMKilled`,
  `exitCode: 137`, container ran 06:22:15Z→06:49:20Z.
- Live memory samples (`kubectl top pod`, 15s interval) across two batches show growth tracking
  total documents processed rather than concurrent workflow count (`running_wf` swung 6→38 without
  proportional memory swing).

## Scope
- Active paths:
  - `PdfMarkdownProcessor._extract_md()` OCR/VLM image loop — every PDF extractor
    (`docling`, `pymupdf`) whenever the processing profile has `pdf.do_ocr: true`.
- Not in scope:
  - `PyMuPdfExtractor`'s `fitz.Document` handle leak — separately fixed in `569d08e6`.
  - `DoclingPdfExtractor`'s own internal OCR pass (RapidOCR) — already cached via
    `_get_document_converter`, unaffected.

## Proposed fix
- Applied: added `_get_ocr_model()` to `PdfMarkdownProcessor`, mirroring `_get_extractor`'s
  lock-guarded single-instance cache. `_extract_md` now calls `self._get_ocr_model()` instead of
  instantiating `PaddleOCRmodel()` inline. Regression test added
  (`test_pdf_processor_builds_ocr_model_only_once_across_documents`) asserting the model is built
  once across multiple documents.

## Acceptance checks
- [x] Unit tests pass, including the new caching regression test (9/9,
      `tests/processors/input/pdf_markdown_processor/test_pdf_markdown_processor.py`).
- [x] Live validation on fredlab: hotfix image (built from this branch) deployed to
      `knowledge-flow-backend`/`knowledge-flow-worker`, same document batch re-ingested. Peak
      memory 4142Mi (80% of the 5Gi limit) with repeated real decreases during processing (e.g.
      -999Mi, -125Mi) — behavior never observed pre-fix, where memory only ever climbed. Batch
      completed at 3781Mi, zero restarts, no OOM.
- [ ] Longer-running / larger-batch validation (a third consecutive batch, or a genuinely large
      single batch) to confirm the plateau holds over more documents than tested so far.

## Promotion
Promoted to: none — fix already implemented and live-validated on fredlab; awaiting PR review/merge
of `fix/memory-leak-1` into `swift`, then a real release to replace the temporary Artifact-Registry
hotfix image (`gcp-c1/argocd/fred-apps/values-fredlab.yaml`, `knowledgeFlow`/`knowledgeFlowWorker`
currently point at a `europe-west1-docker.pkg.dev/.../knowledge-flow-backend:20260731-swift-fce260d6`
build off this branch — temporary, must revert to `ghcr.io` once officially released).
Notes: Full investigation timeline, raw monitoring samples, and root-cause analysis in the session
report (not committed — ask Dimitri if you need the original).
