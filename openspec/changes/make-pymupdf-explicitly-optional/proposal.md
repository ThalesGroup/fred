## Why

Knowledge Flow currently requires the PyMuPDF family even when deployments select other extraction engines. [Issue #3159](https://github.com/ThalesGroup/fred/issues/3159) requires a functional default PDF/PPTX distribution without that family and an explicit, supported opt-in, including its transitive dependencies.

## What Changes

- Move PyMuPDF/PyMuPDF4LLM and their exclusive dependency closure behind the `pymupdf` extra; exclude it from ordinary development installs and standard API/worker images.
- Reuse pypdf for page-aware fast PDF text extraction and metadata, retain MarkItDown's whole-document path and Docling's advanced extraction, and use pypdfium2 for PPTX slide images.
- Preserve page selection, source page numbers, truncation and normalization contracts. Specify and measure intentional formatting/table differences before accepting the replacement.
- Keep PyMuPDF processors selectable through explicit configuration and a separate image build option, independent of Chroma. Reject missing-extra selections before API/worker readiness and remove implicit PyMuPDF fallbacks.
- **BREAKING**: the default advanced PDF extractor becomes Docling; existing PyMuPDF configurations require the extra/image variant or an explicit switch to the default path. Standard Helm/worker fast profiles move off the PyMuPDF4LLM processor.
- Align generated schemas, configurations, processing guidance, licensing inventory and operator migration instructions. Validate actual installed packages and final image SBOMs, independently of the lockfile.
- Add both-profile CI and a reproducible corpus comparison with the proposed acceptance gates in `design.md`, subject to developer confirmation before implementation.

## Capabilities

### New Capabilities

- `document-extraction`: PDF/PPTX engine selection, page-aware extraction and rendering, optional dependency distribution and startup validation. Existing document-import specs cover UI/conflicts and tabular documents, not these extraction contracts.

### Modified Capabilities

None. Import orchestration, progress, permissions and retrieval interfaces remain outside this change.

## Impact

Knowledge Flow dependencies/lockfile, PDF processors and tests, PPTX rendering, shared API/worker configuration validation, Docker build and CI workflows, bundled YAML, backend/Helm schemas, README and processing/licensing documentation. No database migration or new plugin framework. Existing stored documents are not automatically re-ingested; future ingestion may produce different chunks, which the comparison and migration note must explain.

This change extends the optional-image mechanism already merged for Chroma; it does not change Chroma's development defaults or revive historical PRs. Implementation and release publication are not performed by this planning change.
