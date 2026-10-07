# Resources Dashboard

> **Scope:** this document describes current behavior and its stated limitations.
> Proposed changes to corpus ownership, folder permissions and project context
> are defined in the [team/project authorization change](../../../openspec/changes/simplify-corpus-authorization/proposal.md),
> not implemented by this documentation update.

## Purpose

`TeamResourcesPage` (`apps/frontend/src/rework/components/pages/TeamResourcesPage/`) is
the page for browsing, uploading, and managing the searchable team corpus.

**As-built record.** This doc describes the shipped shape only — no workplan checklists,
no commit hashes, no change history. Tracked under GitHub issue #2128.

## Product model

Corpus d'équipe contains ingested, RAG-indexed documents organized by library
(tag), backed by `DocumentMetadata` via `POST /documents/metadata/browse`.
The former team-shared and agent-files tabs have been retired.

## Layout

Header (title, storage quota, a stats-toggle chip) → optional usage-stats cards →
breadcrumb + toolbar (search, create-folder/upload or the bulk-actions bar) →
paginated `DataTable` in `DocumentWorkspace`.

## Table contract

Columns: Name (folder/file-type icon + name), Taille, Création, Auteur, an unlabeled
status chip (nothing for `ready`; a chip only for a state needing attention), and a
preview + "more" actions cell.

- **Auteur** is the uploading identity — `Identity.uploaded_by` — never the file's own embedded author metadata
  (`identity.author`), which reflects the document's internal properties, not who put it
  in Fred. A document ingested before `uploaded_by` existed renders `—` (no backfill).
- **Création** is `source.date_added_to_kb` — when the file
  reached Fred, not the file's own embedded creation metadata (often absent, e.g. PDFs).
- File-type icon color/shape (`rework/utils/fileIconSpec.ts`) mirrors fred-core's
  `FileTypeBucket` grouping (PDF/Texte/PPT/Excel/Autres) used by the usage-stats cards, so
  a given extension reads the same color everywhere on the page.
- **Rename:** the corpus supports it through `RenameModal`. Document
  rename (`PUT /document/metadata/{document_uid}/name`, operation_id `rename_document`)
  is a *real* rename: it writes `Identity.document_name` and clears `title` (so a stale
  cosmetic title can never re-mask the new name), gated on `DocumentPermission.UPDATE`,
  human-only (no agent/MCP tool). It **locks the extension** (400 if the new name's
  extension differs) and **rejects on collision** (409, checked against sibling documents
  in the same tags) rather than auto-suffixing — the user stays in control of the final
  name. `document_uid`, storage keys, and embeddings never change; chunk **metadata**'s
  `document_name` field (a separate, denormalized copy of the display name kept alongside
  the embedding) is patched best-effort across all 5 vector backends, and the in-app
  preview/download `Content-Disposition` header reads the DB record instead of the stored
  blob's own (stale) name. Folder rename is a metadata operation.
- **Bulk actions** (row-selection checkbox column): delete, download (client-side ZIP for
  2+ files, direct download for one), and exclude/include from search.
  Selection is scoped to the current page.

## Usage-stats cards

Files-by-type histogram + size-by-type stacked bar, both bucketed via fred-core's
`FileTypeBucket`. `GET /tags/stats?team_id=...` aggregates `DocumentMetadata`,
deduped by `document_uid` across every readable library.

## Performance contract

The frontend must obey these rules — none of them are optional as the corpus grows:

- never fetch all documents for a team only to render one folder; never fetch all
  resources of a kind for routine rendering; never request `limit=10000` in this page
- do not prefetch every folder's first page on initial mount
- load folder counts through summary endpoints, not by loading file rows
- cache pages per `teamId + folderId + query + filters + sort`
- abort or ignore stale requests when users switch folders quickly
- render only the current page; virtualize only if a page size above 200 is
  intentionally supported later
- a completed task refreshes the current folder/page, not the whole tree, unless the
  task changed folder membership

Initial budgets: opening the workspace with 500 files across folders costs one
tree-summary request + one document page; switching folder costs one document page
request; search within a folder is a debounced request with no tree refetch; an upload
completing costs one current-folder page refresh + one storage-usage refresh; toggling
retrievable costs an optimistic row update + single row/page invalidation.

## Known, accepted limitations

- Search is a client-side filter over the current page's already-loaded rows, not a
  library-wide query — a real backend `query`/`sort` contract exists for Corpus
  (`POST /documents/metadata/browse`) but isn't wired to a UI control yet.
- Bulk download zips client-side (every file's blob round-trips through the browser
  before zipping) — fine at today's usage, revisit with a server-side streaming-zip
  endpoint if that changes.
- No ingestion-token-consumption card — token tracking exists for chat/agent inference,
  not for the ingestion pipeline's own LLM calls (summarization, embedding). Separate,
  unstarted instrumentation work, not a Resources UI gap.

## Open product questions

- Should chat contexts and templates stay outside this workspace (as today, e.g.
  `PromptsPage` for prompts) or move into a dedicated rework page per kind?
