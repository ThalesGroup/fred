## Why

Excel attachment ingestion now reuses corpus extraction and exposes queryable tables. Discovery still lists only corpus documents, forcing the agent to find attachment UIDs through a separate prompt path; one listing should expose both enabled sources with explicit provenance.

Discovery follow-up: https://github.com/ThalesGroup/fred/issues/3007. Ingestion groundwork: https://github.com/ThalesGroup/fred/issues/2734, delivered alongside https://github.com/ThalesGroup/fred/issues/2837 in PR #2838. Completed ingestion tasks and their verification remain recorded in tasks.md.

## What Changes

- Process new `.xls`, `.xlsx`, and `.xlsm` chat attachments through the existing corpus Excel extraction and table registration processors. Preserve every detected table as a queryable Parquet dataset, persist the corpus-generated `output.md` table roadmap, and return `tabular_available=true` without indexing a clipped text preview.
- Authorize explicitly named Excel attachment datasets by their uploader, as CSV attachments are authorized today. Include all tables in schema, search, and SQL operations while keeping attachment datasets out of blind listings.
- Reject an unreadable workbook or one with no queryable table rather than accepting an unusable attachment. Clean up all Parquet objects and metadata on deletion or failed ingestion.
- Direct the agent to use tabular tools for new spreadsheet attachments. Preserve access to older Excel attachments that were ingested as text, and make document-reading failures on tabular-only attachments explicit instead of implying a successful full read.
- Update the attachment, tabular, and agent-form guidance and add focused ingestion, authorization, deletion, and prompt tests.
- Extend `list_tabular_documents` to union authorized corpus documents with ready CSV/Excel attachments of the current authorized conversation. Supply conversation scope automatically, retain source ceilings and corpus selections, and keep unscoped attachment enumeration forbidden.
- Add `source_kind` (`corpus` or `conversation_attachment`) to listing entries. Reuse available library names for corpus provenance and one short instruction explaining the two origins. Keep distinct same-name files by UID and retain every Excel table.
- Align listing, description, SQL and value search with that effective scope and remove the instruction to bypass listing for attachments. Preserve the legacy text fallback.

## Capabilities

### New Capabilities

- `tabular-chat-attachments`: Full-table ingestion, discovery across enabled corpus and conversation sources, authorized query and lifecycle behavior for CSV and Excel conversation attachments.

### Modified Capabilities

None. The current `tabular-document-description` spec already covers authorized Excel tables; this change makes attached Excel tables available under that contract.

## Impact

Knowledge Flow's existing tabular service/controller/response models, runtime MCP context binding, tabular and attachment instructions, affected generated APIs, tests and operational documentation. Reuse the control-plane's existing owned-session attachment listing. No new tool, endpoint family, capability, ingestion path or stored-data migration is planned. Existing text-backed attachments retain their representation.
