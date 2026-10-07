## Context

See proposal.md - Why. Corpus Excel ingestion already runs `ExcelProcessor` and `ExcelTableRegistrationProcessor` to produce `tabular_multi_v1` table artifacts; fast attachment ingestion instead runs `FastSpreadsheetProcessor`, stores a clipped text preview in session vectors, and has no tabular metadata. CSV attachments already invoke the corpus `TabularProcessor` directly after fast preview extraction, skip vectors, and use uploader-owned metadata for explicit tabular access. The current uploader-owned resolver and deletion classifier recognize only `tabular_v1`.

## Goals / Non-Goals

**Goals:** Reuse the same Excel table extraction and registration as corpus ingestion; keep fast-ingest ownership and cleanup semantics; support old text-backed attachments without a data migration.

**Non-Goals:** Move attachments into corpus libraries or grant them ReBAC tuples; change corpus Excel extraction; promise that a bounded tabular preview is a full verbatim or exhaustive read.

## Decisions

### Run the corpus Excel processors inside fast ingest

Call the existing input processor on the uploaded file in a temporary output directory, then the existing registration processor on its `output.md` and `tables.json`. Offload blocking conversion and artifact I/O from the event loop. Use one tagless fast-ingest metadata row with the upload uid and uploader; persist only after all table descriptors are available. Reject zero-table results. Skip vector chunking, as for CSV, so the model has one authoritative route for exact table answers. Upload the generated `output.md` through the same content-store `save_output` layout used by corpus Excel, so `describe_documents` can return it with the table schemas. Retain a bounded UI preview, separate from retrieval.

The alternative of extending `FastSpreadsheetProcessor` into another table extractor would duplicate workbook detection and produce different answers from corpus Excel files.

### Extend ownership and cleanup to multi-table artifacts

Resolve an explicitly named `tabular_multi_v1` attachment after verifying fast-ingest source, empty tags and uploader identity, then expand every table through the existing tabular service. Keep the ReBAC-disabled blind-list exclusion. Classify multi-table metadata in the fast-delete authorization gate and remove the whole document artifact prefix and metadata. Compensate a failed metadata save by deleting uploaded artifacts.

### Keep old attachments and reader claims accurate

The prompt cannot infer storage format from an Excel filename because older attachments are vector-backed. Prefer the tabular route when available and explain the text fallback for a missing dataset. Make absence of a tabular artifact recoverable for an owned legacy attachment. Keep summary/verbatim/extraction selected for text attachments, but do not make their tabular-only preview look exhaustive. Scope any reader changes to an explicit error or bounded-preview wording.

## Risks / Trade-offs

- Full workbook extraction can outlast the old fast preview. Run it off the event loop and retain upload failure visibility; measure request timeout and resource use in focused validation.
- Excel table export and `output.md` upload write multiple objects before metadata persistence. On any later failure, delete the document prefix; test this compensation and deletion.
- Filename-based prompt guidance cannot distinguish legacy from new uploads. Give a recoverable fallback for old workbooks and avoid claiming SQL availability solely from the suffix.
- The resource pack includes reading tools for PDFs and text files, but table analysis must use the tabular tools. Document help must state this file-type boundary.

## Migration Plan

New Excel uploads use the tabular path after deployment. Existing Excel attachments keep their vector-backed text and are not rewritten. Rollback leaves new multi-table attachments stored; the old version will not expose their SQL data, so deployments should retain the prior image until active conversations expire or roll forward. Update the PR migration note for this operational behavior.
