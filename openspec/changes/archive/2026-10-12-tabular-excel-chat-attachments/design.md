## Context

See proposal.md - Why. Completed ingestion work runs `ExcelProcessor` and `ExcelTableRegistrationProcessor` for Excel attachments and the corpus `TabularProcessor` for CSV. Both keep uploader-owned, tagless metadata and skip vector indexing. `_resolve_owned_attachment_datasets` batch-resolves either artifact format for explicit description, search and SQL calls, but `list_documents` uses only `_resolve_authorized_datasets` and therefore omits attachments.

Text retrieval already combines session and corpus branches in `VectorSearchService.search`, using `get_vector_search_scopes` and the document-access source ceilings. `ContextAwareTool` injects source flags and corpus selectors into supported MCP arguments. Text discovery is narrower: `list_document_tree` still lists only corpus documents. Tabular discovery should reuse the retrieval scope semantics, not this tree limitation or its relevance ranking/quota.

`get_attachment_uids` reads the current runtime attachment context. This is a scope hint, not proof of session membership. Tabular attachment metadata records the uploader but not the session; the control-plane's existing `list_session_attachments` validates session ownership and reads the persisted attachment association.

## Goals / Non-Goals

**Goals:** Reuse the existing tabular resolvers, document grouping, MCP binding and document-source semantics for common discovery; preserve completed ingestion and legacy-reader behavior.

**Non-Goals:** Move attachments into corpus libraries or grant them ReBAC tuples; change extraction, vector search or the text tree; introduce a generic multi-source discovery framework; promise that a bounded preview is exhaustive.

## Decisions

### Run the corpus Excel processors inside fast ingest

Call the existing input processor on the uploaded file in a temporary output directory, then the existing registration processor on its `output.md` and `tables.json`. Offload blocking conversion and artifact I/O from the event loop. Use one tagless fast-ingest metadata row with the upload uid and uploader; persist only after all table descriptors are available. Reject zero-table results. Skip vector chunking, as for CSV, so the model has one authoritative route for exact table answers. Upload the generated `output.md` through the same content-store `save_output` layout used by corpus Excel, so `describe_documents` can return it with the table schemas. Retain a bounded UI preview, separate from retrieval.

The alternative of extending `FastSpreadsheetProcessor` into another table extractor would duplicate workbook detection and produce different answers from corpus Excel files.

### Extend ownership and cleanup to multi-table artifacts

Resolve an explicitly named `tabular_multi_v1` attachment after verifying fast-ingest source, empty tags and uploader identity, then expand every table through the existing tabular service. Keep the ReBAC-disabled blind-list exclusion. Classify multi-table metadata in the fast-delete authorization gate and remove the whole document artifact prefix and metadata. Compensate a failed metadata save by deleting uploaded artifacts.

### Keep old attachments and reader claims accurate

The prompt cannot infer storage format from an Excel filename because older attachments are vector-backed. Prefer the tabular route when available and explain the text fallback for a missing dataset. Make absence of a tabular artifact recoverable for an owned legacy attachment. Keep summary/verbatim/extraction selected for text attachments, but do not make their tabular-only preview look exhaustive. Scope any reader changes to an explicit error or bounded-preview wording.

### Extend the existing listing and context binding

Keep `list_tabular_documents` and its document-level list response. In `TabularService.list_documents`, combine the existing corpus resolver with `_resolve_owned_attachment_datasets` for a bounded set of authorized conversation attachment UIDs. Reuse `_group_datasets_by_document` and existing table summaries; deduplicate documents by UID, never filename. Do not add a metadata-wide attachment scan or read Parquet rows for inventory.

At the runtime MCP binding seam, obtain the active session from private runtime context and reuse the existing control-plane owned-session attachment route. Use its persisted document UIDs, constrained by the active attachment context where needed, rather than trusting model-supplied UIDs or session IDs. Supply the resulting attachment UID set automatically to the existing tabular listing via an optional attachment selector. Knowledge Flow rechecks uploader ownership with its existing batch resolver. Direct explicit-UID access retains its existing uploader authorization; it does not establish membership in a conversation. No new session store or duplicate attachment registry belongs in Knowledge Flow.

Runtime-owned scope arguments must be hidden from the model's tool schema and enforced at invocation, including when a model submits forged extra arguments. Reuse the schema-aware MCP wrapper; extend it narrowly for tabular scope rather than adding a second tool. Do not persist conversation context in shared MCP discovery/cache objects. A missing or refused authoritative session lookup must not widen attachment scope or silently claim complete discovery.

### Apply the same source boundaries across the tabular flow

Reuse `get_vector_search_scopes` for turn source choices, intersected with the active document-access `attachments` and `team_documents` ceilings. `general_only` permits neither source; the existing `corpus_only` wire value means document evidence and permits both enabled document sources. Source flags cannot be widened by model arguments.

Keep personal/team, library and document selectors on the corpus branch. Apply attachment membership and uploader checks on the attachment branch, so corpus library selections cannot exclude tagless attachments. Reuse this effective scope at the existing list, describe, query and value-search invocation seams; an attachment excluded from discovery must not become reachable by guessing its UID. Test the shared ReAct/Deep path and affected Graph MCP consumers.

### Carry provenance without a second response envelope

Add a `source_kind` field to each existing list entry: `corpus` or `conversation_attachment`. Derive it from the authorized branch, not the filename or `source_tag` alone. Expose existing `tag_names` for corpus entries when available, so library provenance does not need a new lookup. CSV entries still omit table schemas; Excel entries keep every table identity.

Keep one short provenance note in the existing tabular instructions: corpus files come from accessible libraries; attachments belong to the current conversation. Remove the attachment prompt's prohibition on listing and preserve schema inspection before SQL and the text fallback for older attachments. Per-entry prose notes and a second discovery tool would duplicate this information.

## Risks / Trade-offs

- Full workbook extraction can outlast the old fast preview. Run it off the event loop and retain upload failure visibility; measure request timeout and resource use in focused validation.
- Excel table export and `output.md` upload write multiple objects before metadata persistence. On any later failure, delete the document prefix; test this compensation and deletion.
- Filename-based prompt guidance cannot distinguish legacy from new uploads. Give a recoverable fallback for old workbooks and avoid claiming SQL availability solely from the suffix.
- The resource pack includes reading tools for PDFs and text files, but table analysis must use the tabular tools. Document help must state this file-type boundary.
- Session membership is absent from tabular metadata. Reuse the authoritative owned-session attachment route, then batch-resolve tables; fail explicitly on lookup failure rather than introducing a second persisted association.
- Cached MCP clients can be shared across turns. Bind scope at invocation and verify that consecutive conversations cannot reuse each other's attachment inventory.
- Library/document selectors can accidentally filter the attachment branch. Keep the branches separate until document grouping and cover mixed-source selections end to end.

## Migration Plan

New Excel uploads use the tabular path after deployment. Existing Excel attachments keep their vector-backed text and are not rewritten. Rollback leaves new multi-table attachments stored; the old version will not expose their SQL data, so deployments should retain the prior image until active conversations expire or roll forward. Update the PR migration note for this operational behavior.

The discovery follow-up changes only additive arguments/fields on existing routes and runtime binding/instructions. Regenerate affected API clients and deploy compatible Knowledge Flow, runtime and prompt packages together. Rollback restores the separate attachment discovery path; no stored-data rewrite is required. Record this follow-up's migration declaration in its PR.
