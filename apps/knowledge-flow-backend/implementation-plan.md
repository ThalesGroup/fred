# Implementation Plan — Adaptive PDF Extraction Strategy

**Issue:** ThalesGroup/fred#1191  
**Branch:** `feature/1191-adaptive-pdf-extraction`  
**Date:** 2026-06-24  
**Status:** In progress

---

## 1. Problem Statement

The existing `PdfMarkdownProcessor` applies a single, statically-configured PDF
pipeline to every document it processes.  The active processing profile
(`fast` / `medium` / `rich`) is chosen at the call-site — by a human operator or
ingestion API caller — not by the processor itself based on what the document
actually contains.

This static approach causes three observable failure modes:

| Failure mode | Cause | Impact |
|---|---|---|
| Extraction failures for scanned PDFs | OCR is not activated; pypdf returns empty strings for image-only pages | Chunks contain no text; RAG quality degrades to zero for those documents |
| Resource waste on simple text PDFs | Docling layout analysis + table detection + OCR run on born-digital files that need none of it | 3-5× longer ingestion time, increased pod memory consumption |
| Garbled output for complex layouts | Fast/light path skips table structure detection; column merging produces nonsensical prose | Downstream chunk retrieval returns corrupted context |

---

## 2. Current Behaviour

```
Ingestion request
  → choose profile (fast / medium / rich) by caller
      → PdfMarkdownProcessor.convert_file_to_markdown()
          → apply fixed PdfPipelineConfig from chosen profile
              → Docling pipeline
```

`PdfMarkdownProcessor._resolve_effective_options()` reads the profile from
`get_configuration()` and the request-level context.  There is no feedback from
the document itself.

---

## 3. Expected Behaviour

```
Ingestion request
  → AdaptivePdfMarkdownProcessor.convert_file_to_markdown()
      → PdfDocumentAnalyzer.analyze()          ← NEW: pre-flight check
          → PdfNature: TEXT_NATIVE | SCANNED | COMPLEX_LAYOUT
      → override PdfPipelineConfig for detected type
      → PdfMarkdownProcessor (parent) handles the rest unchanged
```

The processor dynamically selects the extraction path most suited to the
document's actual structure.  The ingestion profile's other settings (image
description, text splitter, retry policy) are preserved unchanged.

---

## 4. Solution Overview

### 4.1 Pre-flight Diagnostic (`PdfDocumentAnalyzer`)

A lightweight, read-only scan using **pypdf** (already a dependency):

1. Sample up to 5 evenly-spaced pages.
2. For each sample page: extract text with `pypdf.PdfReader.pages[i].extract_text()`.
3. Count unique `/Font` resource names from the page dictionary.
4. Compute `avg_chars_per_page` across sampled pages.
5. Apply classification rules (see §4.3).

Total overhead: negligible — no rendering, no model inference, no new library.

### 4.2 Classification: `PdfNature` enum

| Value | Meaning |
|---|---|
| `TEXT_NATIVE` | Born-digital PDF; simple text flow |
| `SCANNED` | Image-only or near-empty text extraction |
| `COMPLEX_LAYOUT` | Selectable text + rich typography or table-heavy layout |

### 4.3 Routing Rules

| PdfNature | `do_ocr` | `do_table_structure` | `force_full_page_ocr` | Notes |
|---|---|---|---|---|
| `TEXT_NATIVE` | `False` | `False` | — | Enables Docling `force_backend_text` shortcut (highest speed) |
| `COMPLEX_LAYOUT` | `False` | `True` | — | Text is selectable; enable table parsing only |
| `SCANNED` | `True` | `True` | `True` | Full OCR on every page; table reconstruction also enabled |

### 4.4 Classification Thresholds

| Parameter | Default | Notes |
|---|---|---|
| `chars_per_page_scanned_threshold` | 80 | Pages averaging fewer chars → SCANNED |
| `font_count_complex_threshold` | 6 | Unique fonts ≥ threshold → COMPLEX_LAYOUT |
| `sample_pages` | 5 | Maximum pages inspected |

Thresholds are class-level constants on `PdfDocumentAnalyzer` — trivially
overridable in tests and subclasses without touching configuration schema.

### 4.5 Fallback Behaviour

If `PdfDocumentAnalyzer.analyze()` raises for any reason (corrupted file,
unexpected pypdf exception), `AdaptivePdfMarkdownProcessor._adapt_config()`
logs a warning and returns the original `base_pdf_config` unchanged.  The parent
`PdfMarkdownProcessor` then runs normally.  No ingestion job is aborted due to
analysis failure.

---

## 5. Assumptions

1. `pypdf` is already present in `pyproject.toml` (confirmed: it is imported in
   the existing `PdfMarkdownProcessor`).
2. No new dependencies are introduced.
3. The feature is delivered as a drop-in processor class, not as a modification
   to existing classes.  Operators opt-in by updating
   `processing.profiles.<name>.input_processors[.pdf]` in their YAML.
4. Thresholds are intentionally conservative defaults suited to typical
   born-digital technical documents.  They should be tuned per corpus using the
   existing benchmark harness (`pdf_medium_docling`, etc.).

---

## 6. Impacted Modules / Components

| File | Change type | Description |
|---|---|---|
| `knowledge_flow_backend/core/processors/input/pdf_markdown_processor/pdf_document_analyzer.py` | **New** | `PdfNature`, `PdfAnalysisResult`, `PdfDocumentAnalyzer` |
| `knowledge_flow_backend/core/processors/input/pdf_markdown_processor/adaptive_pdf_processor.py` | **New** | `AdaptivePdfMarkdownProcessor` + config builder helpers |
| `tests/processors/input/pdf_markdown_processor/test_adaptive_pdf_processor.py` | **New** | 20 unit tests covering analyzer and adaptive routing |
| `implementation-plan.md` | **New** | This document |

No existing files were modified.

---

## 7. Implementation Steps

| Step | Description | Status |
|---|---|---|
| 1 | Create feature branch `feature/1191-adaptive-pdf-extraction` | Done |
| 2 | Implement `PdfDocumentAnalyzer` in `pdf_document_analyzer.py` | Done |
| 3 | Implement `AdaptivePdfMarkdownProcessor` in `adaptive_pdf_processor.py` | Done |
| 4 | Write unit tests in `test_adaptive_pdf_processor.py` | Done |
| 5 | Syntax validation (no venv available in dev environment) | Done |
| 6 | Write this implementation plan | Done |
| 7 | Commit + push to fork | Pending |
| 8 | Add post-processing: register processor in benchmark registry | Optional |

---

## 8. Testing Strategy

### 8.1 Unit tests (offline, no dependencies)

All tests use `monkeypatch` to avoid real PDF I/O except where a sample fixture
is used.

| Test class | What is tested |
|---|---|
| `TestSelectSampleIndices` | Boundary conditions for sample index selection |
| `TestClassify` | All three `PdfNature` categories + threshold boundaries |
| `TestAnalyze` | Missing file, empty PDF, no-text PDF, rich-text PDF; real fixture smoke test |
| `TestConfigBuilders` | Immutability of base config + correct flag values per nature |
| `TestAdaptConfig` | Correct routing for each `PdfNature`; graceful fallback on analysis error |
| `TestAdaptiveConvertFileToMarkdown` | End-to-end path with mocked `DocumentConverter`; OCR flag verified; `_resolve_effective_options` restored after exception |

### 8.2 Integration tests (`@pytest.mark.integration`)

Not added in this PR — existing `test_pdf_processor_end_to_end` in
`test_pdf_markdown_processor.py` already covers the parent class with a real
sample PDF.  An integration test for `AdaptivePdfMarkdownProcessor` would
duplicate it and require a running Docling stack.

### 8.3 Benchmark harness

To compare adaptive vs fixed routing on a real corpus:

```python
# Add to apps/knowledge-flow-backend/knowledge_flow_backend/features/benchmark/procbench/registry.py
ProcessorSpec(
    id="pdf_adaptive",
    kind="standard",
    factory=AdaptivePdfMarkdownProcessor,
    display_name="PDF → MD (Adaptive / auto-route)",
    file_types=[".pdf"],
)
```

This lets the benchmark runner compare `pdf_adaptive` against
`pdf_medium_docling` and `pdf_fast_lite` head-to-head.

---

## 9. Risks and Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Threshold too aggressive — classifies complex PDFs as TEXT_NATIVE | Medium | Poor table extraction | Start conservative; expose thresholds as class constants for easy tuning; use benchmark harness to validate |
| pypdf text extraction returns garbage on some encodings → wrong classification | Low | Incorrect routing | Fallback to base config on any analysis exception |
| Very large PDFs with 1000+ pages incur measurable sampling overhead | Low | Slower ingestion start | Only 5 pages are sampled; worst case <50ms |
| `_resolve_effective_options` method-level monkey-patch is fragile | Low | Unexpected config leak | `try/finally` in `convert_file_to_markdown` guarantees restoration even on exception; verified by test |

---

## 10. Acceptance Criteria

- [ ] `PdfDocumentAnalyzer.analyze()` classifies a born-digital sample PDF as
  `TEXT_NATIVE` or `COMPLEX_LAYOUT` (never `SCANNED`).
- [ ] `PdfDocumentAnalyzer.analyze()` classifies a zero-text PDF (all pages return
  empty text) as `SCANNED`.
- [ ] `AdaptivePdfMarkdownProcessor` routes a `SCANNED` document to a pipeline
  with `do_ocr=True` and `force_full_page_ocr=True`.
- [ ] `AdaptivePdfMarkdownProcessor` routes a `TEXT_NATIVE` document to a pipeline
  with `do_ocr=False` and `do_table_structure=False`.
- [ ] When `PdfDocumentAnalyzer.analyze()` throws, conversion still completes using
  the base profile config.
- [ ] All 20 unit tests pass.
- [ ] No existing tests are broken.
- [ ] No new runtime dependencies are introduced.
- [ ] `_resolve_effective_options` is always restored after `convert_file_to_markdown`
  returns or raises.

---

## 11. How to Wire the Adaptive Processor

Update your `configuration.yaml`:

```yaml
processing:
  default_profile: medium
  profiles:
    medium:
      input_processors:
        - suffix: ".pdf"
          class_path: >-
            knowledge_flow_backend.core.processors.input
            .pdf_markdown_processor.adaptive_pdf_processor
            .AdaptivePdfMarkdownProcessor
          description: "Adaptive PDF processor — auto-detects document type"
```

No other configuration changes are required.
