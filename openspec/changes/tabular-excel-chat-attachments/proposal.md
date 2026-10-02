## Why

Excel files attached to a conversation currently expose a clipped text preview instead of the queryable tables produced by corpus ingestion. This can give incomplete answers and makes the tabular tools unusable for an attachment the user owns. The resource pack now keeps tabular tools enabled in attachments-only mode, so its Excel path must offer the same table extraction and queries as the corpus path.

Tracking: https://github.com/ThalesGroup/fred/issues/2734. Delivered alongside https://github.com/ThalesGroup/fred/issues/2837 in PR #2838.

## What Changes

- Process new `.xls`, `.xlsx`, and `.xlsm` chat attachments through the existing corpus Excel extraction and table registration processors. Preserve every detected table as a queryable Parquet dataset, persist the corpus-generated `output.md` table roadmap, and return `tabular_available=true` without indexing a clipped text preview.
- Authorize explicitly named Excel attachment datasets by their uploader, as CSV attachments are authorized today. Include all tables in schema, search, and SQL operations while keeping attachment datasets out of blind listings.
- Reject an unreadable workbook or one with no queryable table rather than accepting an unusable attachment. Clean up all Parquet objects and metadata on deletion or failed ingestion.
- Direct the agent to use tabular tools for new spreadsheet attachments. Preserve access to older Excel attachments that were ingested as text, and make document-reading failures on tabular-only attachments explicit instead of implying a successful full read.
- Update the attachment, tabular, and agent-form guidance and add focused ingestion, authorization, deletion, and prompt tests.

## Capabilities

### New Capabilities

- `tabular-chat-attachments`: Full-table ingestion, authorized query and lifecycle behavior for CSV and Excel conversation attachments.

### Modified Capabilities

None. The current `tabular-document-description` spec already covers authorized Excel tables; this change makes attached Excel tables available under that contract.

## Impact

Knowledge Flow fast ingestion, Excel processor reuse, tabular authorization and cleanup, runtime attachment guidance, frontend Help Center copy, tests, and operational documentation. No stored-agent migration or new public endpoint is planned. Newly uploaded Excel attachments use the SQL path; existing text-backed attachments retain their stored representation.
