---
schema: 1
title: "Make PyMuPDF explicitly optional for PDF processing"
impact: minor
configuration: production
configuration_reason: "Fast PDF defaults to pypdf and advanced PDF defaults to Docling; existing PyMuPDF class paths require the optional image or migration to the standard processors."
---
## Applicability

Knowledge Flow API and all ingestion workers, including separate fast, medium
and rich extraction deployments. No database or stored-document migration.

## Prerequisites

Inspect all `processing.profiles.*.input_processors` and `pdf.extractor` values,
including profiles not selected by `default_profile`. Decide whether to use
the standard distribution or retain the explicit PyMuPDF family.

## Configuration

Follow the [installation guide](../../../../apps/knowledge-flow-backend/README.md#optional-pymupdf-processing).
For the standard path, replace the fast `.pdf` class module `lite2_pdf_to_md_processor`
with `lite_pdf_to_md_processor`, retaining `LitePdfMarkdownProcessor`. Use
`docling` for the advanced processor's `pdf.extractor`. Bundled YAML and Helm
values already contain these defaults; existing overrides must be updated.
No new application configuration key is introduced.

For opt-in, select the `knowledge-flow-backend-pymupdf` image repository with
the same release tag and retain/select the PyMuPDF class or extractor. Apply
compatible images and configuration to the API, common worker and extraction
workers. Inspect explicit overrides that bypass Helm worker inheritance.
The Chroma build option remains independent.

## Upgrade

Drain in-flight ingestion before restarting workers, then deploy the matching
API/worker images and configuration together. Do not install dependencies into
running pods. Standard deployments need no custom image build; combining
optional Chroma and PyMuPDF requires a custom build with both arguments.

Existing indexed text and embeddings remain unchanged. Newly ingested PDFs can
have different text ordering, whitespace, Markdown and chunk boundaries.
Re-ingest only documents for which that new extraction is desired. Fast mode
does not OCR scanned PDFs; choose medium/rich Docling for those documents.

## Validation

Check startup succeeds for all enabled API/worker deployments. Ingest a
multipage PDF, a scanned PDF using Docling, and a PPTX with visual enrichment;
check previews, text, page references and retrieval. Inspect final-image
inventories: the standard image excludes all three PyMuPDF family packages,
while the optional image includes them. Selecting an optional processor in the
standard image must fail during configuration validation with a clear remedy.

## Rollback

Restore the previous images and matching configuration for API and workers
after draining current ingestion. Keep storage and database volumes. Documents
already re-ingested retain their new chunks until explicitly re-ingested again.
The previous image may reintroduce the optional family's license obligations.

## Limitations

Selecting an image does not select an engine. The optional family's licenses
include both AGPL/commercial and PolyForm Noncommercial terms. Removing that
family does not certify every other dependency or model license. Fast text
extraction preserves table values but does not promise Markdown table layout.
