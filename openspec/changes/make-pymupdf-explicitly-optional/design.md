## Context

See `proposal.md` for motivation and scope. Inspection baseline: `a8b4228eb8064b01d26fca48f72886b0544341a6` on the user-selected issue branch.

- `apps/knowledge-flow-backend/pyproject.toml` requires both PyMuPDF packages; its lockfile resolves PyMuPDF, PyMuPDF4LLM and pymupdf-layout to 1.27.2.3. pypdf 6.19.0 is direct; pypdfium2 5.10.1 is already transitive.
- `lite_pdf_to_md_processor.py` uses MarkItDown for whole documents and fitz for page-aware extraction, validation and metadata. `FastLitePdfProcessor` delegates to it. `lite2_pdf_to_md_processor.py` uses PyMuPDF4LLM and is selected by the Helm and worker fast profiles.
- `PdfMarkdownProcessor` eagerly imports its PyMuPDF extractor and falls back to it for unknown engine names. `PdfConfig.extractor` defaults to `pymupdf`, while bundled medium/rich profiles explicitly use Docling.
- PPTX rendering converts through the existing LibreOffice helper and rasterizes selected PDF pages with fitz at scale 2. API and worker both initialize `ApplicationContext`; existing configuration validation covers all processing profiles and attachment processors.
- Chroma already has an independent extra, `INSTALL_CHROMA` image build argument and CI installation checks. Its development group intentionally installs Chroma; that policy must not be copied for PyMuPDF.

## Goals / Non-Goals

**Goals:** make installed dependencies and engine selection explicit; preserve existing processor result shapes and usable citations; test real extraction and final artifacts.

**Non-Goals:** new processor/plugin framework, queue redesign, OCR engine replacement, changes to retrieval/permissions, blanket license remediation, automatic re-ingestion or edits to historical issues/PRs.

## Decisions

### Reuse the existing lightweight path

Replace fitz operations in the first lightweight processor with pypdf, keeping its public classes and `FastLitePdfProcessor` adapter. Use page-local extraction for page-aware requests; preserve inclusive 1-based ranges, clamping, headings, normalization and current truncation/per-page semantics. Retain MarkItDown only for whole-document requests where it cannot discard requested page attribution. Page-aware extraction errors must not silently return unpaginated content. Use pypdf for PDF validation/metadata in both lightweight wrappers.

Keep the second lightweight processor as the explicitly selected PyMuPDF4LLM implementation, with lazy optional imports. Configure default fast profiles to use the first processor. Fast table content remains readable text; structured tables and scanned-document OCR belong to Docling profiles. This intentionally does not promise identical Markdown layout to PyMuPDF4LLM.

pypdf is already direct and avoids introducing native rendering/threading constraints into fast text extraction. MarkItDown alone cannot satisfy the existing page-selection contract; making every fast call use Docling would change its latency/model requirements substantially. Evaluate the chosen path against the gates below rather than asserting equivalent quality.

### Preserve advanced processing and validate explicit selection

Set the advanced extractor model default to `docling` and remove unknown-engine fallback. Import the PyMuPDF extractor only for explicit `pymupdf` selection. Keep optional dependency failures outside broad document-extraction fallbacks so they retain an actionable cause.

Extend existing shared startup validation to inspect every selectable profile and configured legacy PyMuPDF4LLM processor, including attachment configuration where applicable. Reject missing packages before API readiness or worker polling, identifying the affected setting and `uv sync --extra pymupdf` / opt-in image remedy. Check only selected optional implementations; importing the ordinary application with no extra must succeed. Catch missing optional modules narrowly; broken binaries, unrelated missing imports and processor errors retain their actual cause. Installing the extra does not change engine selection.

### Isolate slide rasterization from concurrent native calls

Promote the already locked pypdfium2 version to an explicit dependency for the renderer. Keep LibreOffice conversion and the renderer's selected-slide mapping, PNG names, 1-based numbering, out-of-range behavior and scale 2 opaque images.

PDFium forbids concurrent calls even for different documents ([upstream threading and resource guidance](https://pypdfium2.readthedocs.io/en/stable/python_api.html)). Docling may also use it inside threaded ingestion. A renderer-only mutex cannot protect those calls. Run each deck's rasterization in a dedicated short-lived subprocess, using the current interpreter and a small internal module, with a bounded timeout and cleanup on failure. Do not create an executor framework or pool. Close page/bitmap/document resources explicitly inside the child and include child RSS in measurements. Validate simultaneous Docling/PPTX work; do not assume process isolation makes every existing Docling path safe.

### Keep installation options independent and auditable

Move existing PyMuPDF requirements into `[project.optional-dependencies].pymupdf`; regenerate the lockfile without upgrading unrelated packages. Never add this extra to dev defaults or use `--all-extras` in ordinary CI/Make targets. Add `INSTALL_PYMUPDF=false` alongside `INSTALL_CHROMA`, composing options instead of replacing one with the other. Document a distinct opt-in image tag/build invocation and select that same variant for API and workers through existing image settings.

Check all four Chroma/PyMuPDF combinations with dependency graph assertions; exercise default and PyMuPDF profiles in separate clean environments. Inventory clean `uv sync`, `make dev`, a built wheel installed without local sources, and final API/worker images. Derive exclusive dependencies from transitive reachability, retaining shared packages such as numpy/onnxruntime when other default dependencies need them. Audit final filesystem layers/caches as well as Python metadata so copied artifacts cannot conceal the family.

The lockfile retains optional packages for reproducibility; it is not proof they ship. Produce separate inventories/SBOMs for standard and opt-in artifacts, tied to image digests. Preserve license files and required notices; do not add scanner exceptions or remove metadata.

### Proposed corpus and acceptance gates

These thresholds are a proposal requiring developer confirmation before implementation, not measured results. Freeze fixture hashes and human-readable expected text/page/table facts before comparing branches. Use at least 12 redistributable documents: 2 simple text PDFs, 2 multipage PDFs (including a 100-page case), 2 table/layout PDFs, 2 Unicode/malformed-text PDFs, 2 scanned PDFs and 2 PPTX decks (including mixed text/vector/image slides). Reuse current PDF fixtures and generators; add small synthetic fixtures where coverage is missing. Record provenance and expected outcomes; no private corpus is needed by default.

| Dimension | Proposed acceptance |
| --- | --- |
| Correctness | 100% of page/range/count/truncation/normalization and selected-slide assertions pass; valid corpus documents complete; corrupt inputs fail with a useful cause. |
| Text | Case-sensitive whitespace-normalized token recall, computed per page with token multiplicity against reviewed reference text, is at least 98% on each born-digital PDF; all designated Unicode and citation anchor strings survive. Check reading order on the layout fixtures separately. |
| Tables / OCR | Fast extraction retains all designated table cell values without requiring Markdown table syntax. Docling preserves all designated cell relationships and achieves at least 95% token recall on each controlled scanned fixture. No OCR promise for fast mode. |
| PPTX images | Every requested valid slide produces a nonempty PNG at expected dimensions; designated text and graphics are present in a visual comparison. Raster antialiasing differences are allowed. |
| Latency / memory | On the same machine, compare each affected fast/PPTX fixture with the baseline configured counterpart: median wall time <= 2x and peak total process-tree RSS <= 1.5x baseline. Use one cold run reported separately, one warmup and five measured runs in fresh processes with warmed caches; include process startup and child memory. Repeat at 4 concurrent documents and require no crashes, wrong pages or leaked children/handles. Report throughput and contention separately. |

Run the baseline with its locked optional dependencies present, and compare both candidate profiles. Compare default Docling with unchanged baseline Docling for OCR/table checks. Record extraction text, page attribution, chunk counts and example citation anchors for both profiles; explain changed chunk boundaries instead of asserting byte identity. Failures require a correction or explicit revised acceptance, not silently relaxed thresholds. Model downloads and LibreOffice/image validation run in provisioned integration CI; offline tests remain service-free. Evidence and limitations belong in the existing tasks/PR and CI artifacts.

## Risks / Trade-offs

- pypdf can be slower or order text differently from MuPDF: enforce the corpus gates, document the fast/advanced distinction, and revisit the proposed engine if gates fail.
- Subprocess rasterization has startup cost: measure it end to end; its safety boundary avoids unsynchronized PDFium use alongside Docling.
- Existing chart fast profiles lose PyMuPDF4LLM table formatting: document the migration to Docling for structured tables or explicit opt-in for prior extraction behavior; preserve source page anchors.
- Package licensing differs within the family: [PyMuPDF licensing](https://pymupdf.io/licensing) and [pymupdf-layout 1.27.2.3 metadata](https://pypi.org/project/pymupdf-layout/1.27.2.3/) must be reconciled with exact shipped artifact metadata. Operators establish rights for every enabled component; selecting an extra is not legal clearance. Record pypdf, pypdfium2/PDFium, bundled third-party notices and remaining runtime dependencies separately.
- Cached models or optional wheels could survive a final image build: inspect actual images and dependency edges, not only imports or lockfile greps.

## Migration Plan

1. Update supported local YAML and Helm fast processor defaults, the advanced extractor default, and generated backend/Helm schemas together. Update README, `docs/swift/COPYLEFT-DEPENDENCIES.md`, processing guidance and stale feature descriptions only where affected.
2. Provide an English migration note with `impact: minor`, `configuration: production`. Operators either use standard images and non-PyMuPDF profiles, or deliberately build/select the extra image for API and workers and retain explicit PyMuPDF selections. Show both paths and their exact configuration.
3. Drain active ingestion before changing worker images/profiles. Validate startup and sample PDF/PPTX ingestion before resuming work. Existing indexed data stays intact; re-ingestion is optional to adopt new extraction output and may change chunks/citations.
4. Roll back matching previous images and configuration together. Do not automatically rewrite indexed content or assume rollback undoes documents ingested under the new engine. Publish paired code/chart versions through the normal release workflow; this PR does not tag releases.
