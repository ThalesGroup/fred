# Resources Dashboard

## Purpose

`TeamResourcesPage` (`apps/frontend/src/rework/components/pages/TeamResourcesPage/`) is
the one page for browsing, uploading, and managing every file a team can see. It replaced
the old always-expanded MUI tree (`KnowledgeHub`) and the later per-tab single-line-row
browsers (`TeamFilesystemBrowser`/`AgentFilesystemBrowser`), both fully retired.

**As-built record.** This doc describes the shipped shape only — no workplan checklists,
no commit hashes, no change history. Tracked under GitHub issue #2128.

## Product model

Four tabs, one shared table shell:

| Tab | Content | Data source |
| --- | --- | --- |
| Corpus d'équipe | Ingested, RAG-indexed documents, organized by library (tag) | `DocumentMetadata` via `POST /documents/metadata/browse` |
| Mon espace | The user's private files inside the team | `/fs` under `teams/{team}/users/{uid}` |
| Espace d'équipe | Team-shared files; hidden entirely for a personal team | `/fs` under `teams/{team}/shared` |
| Agents | Per-agent-instance generated files, one virtual folder row per agent | `/fs` under `teams/{team}/agents/{instance}/users/{uid}` |

**Feature flag:** Mon espace/Espace d'équipe/Agents are gated behind
`enableAllResourceSpaces` (`FrontendFeatureFlags`, `configuration.yaml`, platform-wide,
default off) — a product-maturity call, not a technical limitation. All three are fully
built, tested, and reachable via the API/MCP `/fs` boundary regardless of the flag; **the
flag only hides their tab in the UI**, it is not a backend access control. The actual
team-scoping gap on that boundary is tracked separately as issue #2113 (Critical).

See `docs/swift/design/FILESYSTEM.md` for the virtual path layout and the full `/fs`
route table.

## Layout

Header (title, storage quota, a stats-toggle chip) → optional usage-stats cards → tab
switcher → breadcrumb + toolbar (search, create-folder/upload or the bulk-actions bar) →
paginated `DataTable`. Every tab is built on the same generic shell,
`shared/organisms/ResourceExplorer/ResourceExplorer.tsx`, which has no notion of
"document" or "tag" — rows, columns, and cell rendering are entirely caller-supplied.

## Table contract

Columns: Name (folder/file-type icon + name), Taille, Création, Auteur, an unlabeled
status chip (nothing for `ready`; a chip only for a state needing attention), and a
preview + "more" actions cell.

- **Auteur** is the uploading/creating identity — `Identity.uploaded_by` (Corpus) or
  `created_by` (`/fs`) — never the file's own embedded author metadata
  (`identity.author`), which reflects the document's internal properties, not who put it
  in Fred. A document ingested before `uploaded_by` existed renders `—` (no backfill).
- **Création** is `source.date_added_to_kb` (Corpus) or `created` (`/fs`) — when the file
  reached Fred, not the file's own embedded creation metadata (often absent, e.g. PDFs).
- File-type icon color/shape (`rework/utils/fileIconSpec.ts`) mirrors fred-core's
  `FileTypeBucket` grouping (PDF/Texte/PPT/Excel/Autres) used by the usage-stats cards, so
  a given extension reads the same color everywhere on the page.
- **Rename:** every tab supports it through one shared `RenameModal`. Corpus document
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
  blob's own (stale) name. `canonical_name`/`version` (the "name (1)" draft-version
  machinery) are left untouched by a rename — a known, non-corrupting edge case. Folder
  rename and `/fs` rename are plain metadata/filesystem operations with no extension lock.
- **Bulk actions** (row-selection checkbox column): delete, download (client-side ZIP for
  2+ files, direct download for one), and — Corpus only — exclude/include from search.
  Selection is scoped to the current page.

## Usage-stats cards

Files-by-type histogram + size-by-type stacked bar, both bucketed via fred-core's
`FileTypeBucket`. Two backend sources, matching the table's own split: `GET
/tags/stats?team_id=...` for Corpus (aggregates `DocumentMetadata`, deduped by
`document_uid` across every readable library), `GET /fs/stats/{path}` for Mon
espace/Espace d'équipe (recursive file listing under that path, bucketed by extension).
Agents has no stats source — its root is virtual, not one `/fs` path.

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
  (`POST /documents/metadata/browse`) but isn't wired to a UI control yet; the other
  three tabs have no equivalent `/fs` search contract at all. Deferred until real usage
  data justifies the backend work.
- Bulk download zips client-side (every file's blob round-trips through the browser
  before zipping) — fine at today's usage, revisit with a server-side streaming-zip
  endpoint if that changes.
- No ingestion-token-consumption card — token tracking exists for chat/agent inference,
  not for the ingestion pipeline's own LLM calls (summarization, embedding). Separate,
  unstarted instrumentation work, not a Resources UI gap.
- The "by AI" provenance badge (agent-generated files) never appears on Corpus rows —
  ingestion is never agent-driven in the current provenance model.

## Open product questions

- Should chat contexts and templates stay outside this workspace (as today, e.g.
  `PromptsPage` for prompts) or move into a dedicated rework page per kind?
- Should "Mon espace" become part of the MCP filesystem view (FILES-01) instead of the
  document-library/tag model it uses today?
