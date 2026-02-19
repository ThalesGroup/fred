# Document Processing Guide (Fast / Medium / Rich + Fast Attachments)

This guide documents the current processing architecture in Knowledge Flow, with emphasis on:
- profile-driven ingestion (`fast`, `medium`, `rich`)
- attachment fast path behavior
- unstructured status
- Docker/runtime dependencies
- offline and air-gapped constraints

It reflects the current code and config layout where processors are configured under:
`processing.profiles.<profile>.input_processors`

Legacy root `input_processors` is no longer supported.

---

## 1) Processing Architecture

There are two distinct ingestion paths:

1. Library ingestion (full pipeline)
- Endpoints like `/upload-process-documents`
- Uses `IngestionProcessingProfile` (`fast` / `medium` / `rich`)
- Selects processors from `processing.profiles.<profile>.input_processors`
- Then runs output processors (chunking, embeddings, vector store, optional summary)

2. Attachment fast path (chat attachments)
- Endpoints `/fast/text` and `/fast/ingest`
- Uses `BaseFastTextProcessor` adapters
- Designed for quick extraction + scoped vectorization
- Separate registry via `attachment_processors` (optional) or built-in fallback map

---

## 2) Current Profile Matrix (Library Ingestion)

Current production and worker templates define:
- `default_profile: fast`
- `generate_summary: false` in all profiles

### Fast
- PDF: `LitePdfMarkdownProcessor` (lightweight path)
- DOCX: `DocxMarkdownProcessor`
- PPTX: `PptxMarkdownProcessor`
- Plus CSV/TXT/MD/XLSM/JSONL processors
- `process_images: false`
- `do_ocr: false`, `do_table_structure: false`

### Medium
- PDF: `PdfMarkdownProcessor` (Docling) with OCR/table AI disabled by config
- DOCX/PPTX same as above
- `process_images: false`

### Rich
- PDF: `PdfMarkdownProcessor` (Docling) with OCR/table AI enabled
- DOCX/PPTX same as above
- `process_images: true` (image descriptions via configured vision model)

Note:
- Even in `medium`, PDF uses `PdfMarkdownProcessor` in production templates.
- If you want fully lightweight DOCX/PPTX for library ingestion too, you can switch class paths to:
  - `LiteDocxMarkdownProcessor`
  - `LitePptxMarkdownProcessor`
  They implement the same `BaseMarkdownProcessor` contract.

---

## 3) Attachment Fast Path Registry (Current Behavior)

If `attachment_processors` is not configured, built-in fallback is:

- `.pdf` -> `FastLitePdfProcessor`
- `.docx` -> `FastLiteDocxProcessor`
- `.pptx` -> `FastLitePptxProcessor`
- `.csv` -> `FastLiteCsvProcessor`

Important:
- Wildcard fallback to unstructured is intentionally disabled.
- Unsupported suffix now fails fast with clear error:
  `No fast text processor configured for '.ext'`

This is deliberate to avoid silently routing unsupported formats to heavier/less reliable behavior.

---

## 4) Unstructured Status

Current status:
- `FastUnstructuredTextProcessingProcessor` still exists in codebase.
- It is not used by default attachment fallback.
- It is not referenced in current active config templates.
- It remains available for explicit opt-in (or benchmark usage), but not part of the default trusted path.

Practical implication:
- The runtime behavior is now deterministic per suffix for fast attachments.
- If unstructured is not wanted at all, remove it from dependency and image layers as a separate cleanup task.

---

## 5) Processor Dependency Matrix

| Processor | Typical Path | External Binaries | Model/Network Risk |
| :--- | :--- | :--- | :--- |
| `LitePdfMarkdownProcessor` / `FastLitePdfProcessor` | Fast profile PDF + fast attachments | None required | Low (no OCR model download path) |
| `PdfMarkdownProcessor` (Docling) | Medium/Rich PDF | None strictly required by processor itself | Medium/High if OCR/table/image options enabled and models are not pre-cached |
| `DocxMarkdownProcessor` | All profiles DOCX (default) | `pandoc` required, `inkscape` needed for `.emf` -> `.svg` | Low (no LLM/model downloads) |
| `PptxMarkdownProcessor` | All profiles PPTX (default) | None | Low |
| `LiteDocxToMd`/`FastLiteDocxProcessor` | Fast attachment DOCX | None | Low |
| `LitePptxToMd`/`FastLitePptxProcessor` | Fast attachment PPTX | None | Low |
| `FastLiteCsvProcessor` | Fast attachment CSV | None | Low |

Additional runtime/model dependencies:
- Cross-encoder reranker may download from Hugging Face unless configured offline.
- Vision model is used when `process_images: true` (rich profile PDF image descriptions).
- Chat/embedding/vision providers pointing to external APIs (e.g. OpenAI) require network access.

---

## 6) Docker Dependencies: What You Really Need

### Required for current default processors
- `pandoc` (DOCX heavy processor)
- `inkscape` (DOCX EMF conversion support)
- Python deps for lite/heavy processors (already in environment)

### Present in current prod Dockerfile but not always required for default fast path
- `poppler-utils`
- `ffmpeg`
- `tesseract-ocr` (+ language packs)
- `libmagic1`

These are useful for optional/legacy/advanced paths and troubleshooting, but they increase image weight.

If image size reduction is a priority:
1. Confirm which processors are truly enabled in profiles and attachments.
2. Remove unused Python deps (notably unstructured stack if fully deprecated).
3. Remove unused system packages from Dockerfile accordingly.

---

## 7) Offline / Air-Gapped Hardening Checklist

1. Use profile-based config only
- Keep processors under `processing.profiles.<profile>.input_processors`
- Do not use legacy root `input_processors`

2. Prefer deterministic lightweight paths where possible
- `fast` profile for ingestion
- fast attachment map with explicit suffixes

3. Control Docling model-dependent features
- Set per-profile PDF flags explicitly:
  - `do_ocr: false`
  - `do_table_structure: false`
- Keep `process_images: false` if no vision model is available offline

4. Handle cross-encoder offline
- Configure:
  - `crossencoder_model.settings.online: false`
  - `crossencoder_model.settings.local_path: <preloaded path>`
- Pre-bake model artifacts into image or mounted volume

5. Ensure model/provider availability
- If using OpenAI endpoints, offline operation is not possible
- For offline operation, use local/self-hosted providers and preloaded model assets

6. Preload tokenization/cache assets during build
- Keep tiktoken/crossencoder pre-download steps in image build when running without internet

---

## 8) Recommended Configuration Snippets

### A) Explicit attachment fast map (no wildcard)

```yaml
attachment_processors:
  - suffix: ".pdf"
    class_path: knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_pdf_processor.FastLitePdfProcessor
  - suffix: ".docx"
    class_path: knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_docx_processor.FastLiteDocxProcessor
  - suffix: ".pptx"
    class_path: knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_pptx_processor.FastLitePptxProcessor
  - suffix: ".csv"
    class_path: knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_csv_processor.FastLiteCsvProcessor
```

### B) Offline-safe PDF profile defaults

```yaml
processing:
  default_profile: fast
  profiles:
    fast:
      process_images: false
      pdf:
        do_ocr: false
        do_table_structure: false
```

---

## 9) Troubleshooting

### Unsupported attachment extension
Symptom:
- 400 error with message:
  `No fast text processor configured for '.ext'`

Action:
- Add suffix mapping in `attachment_processors`, or use supported suffixes.

### DOCX conversion fails
Symptom examples:
- invalid DOCX zip
- pandoc conversion error
- EMF image not converted

Action:
1. Validate file is a real DOCX archive.
2. Ensure `pandoc` is installed.
3. Ensure `inkscape` is installed if EMF media is expected.

### Unexpected model/network calls in offline setup
Action:
1. Check profile flags (`do_ocr`, `do_table_structure`, `process_images`).
2. Check model providers (chat/embedding/vision).
3. Ensure cross-encoder is configured for offline local path.
