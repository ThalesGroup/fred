# RFC: Rework Knowledge Workspace — Robust Resource Browser

**Status:** proposed — RFC/workplan created 2026-06-18; phases A/C/D shipped as `TeamResourcesPage`
**Author:** Dimitri Tombroff
**Date:** 2026-06-18
**Amended:** 2026-07-25 — Maxime Daragon (§13 — Resources dashboard v2: tab navigation, rich
table, usage cards; supersedes parts of §4.1/§4.2, see note there)
**Amended:** 2026-07-27 — Maxime Daragon (§13.8/§13.9 — rename support, bulk actions bar;
extends the FRONT-09.G/H/I workplan with FRONT-09.J/K)
**Amended:** 2026-07-29 — Maxime Daragon (§13.12 — Mon espace/Espace d'équipe/Agents
gated behind a platform-wide feature flag, off by default; Corpus d'équipe only ships
reachable until the team is confident in the other three)
**Amended:** 2026-07-29 — Maxime Daragon (§13.13 — row/bulk "Download" action,
client-side ZIP for multi-select, documented interim state pending a possible
server-side move)
**ID:** FRONT-09
**Issue:** https://github.com/ThalesGroup/fred/issues/2128 (§13.7/§13.11 phases G-K)
**Backlog:** `docs/swift/backlog/FRONTEND-BACKLOG.md §15`
**Related:** `docs/swift/design/FILESYSTEM.md`, `docs/swift/backlog/CHAT-UI-BACKLOG.md §4.5`
**Contract impact:** may add Knowledge Flow browse endpoints; no control-plane binary ownership

---

## 1. Problem

The Swift frontend has a modern `src/rework` component system, but the knowledge/resource
area still relies on old MUI-heavy pages:

- `apps/frontend/src/pages/KnowledgeHub.tsx`
- `apps/frontend/src/pages/KnowledgePage.tsx`
- `apps/frontend/src/components/documents/libraries/*`
- `apps/frontend/src/components/resources/*`

The current rework entry point, `KnowledgeHubPage`, is only a health-check shell that
delegates back to the old `KnowledgeHub`.

That old surface works, but it mixes too many concerns:

- visual layout and orchestration state live in the same component
- folder tree, document list, selection, search, upload, refetch, task refresh, preview,
  download, and bulk actions are tightly coupled
- several paths still use MUI and old shared UI primitives
- broad list paths still assume it is acceptable to load large sets into the browser
- personal resources, team documents, user assets, chat contexts, prompts, templates, and
  operations appear through one historical "knowledge hub" shape

Some Fred users already have hundreds of files. The v2 resource browser must therefore
be designed around server pagination, lazy folder loading, and simple state ownership from
the start. A visual-only rewrite would be risky because it would preserve the current
"fetch a lot, render a lot, then filter locally" pressure.

---

## 2. Goals

Build a rework-native Knowledge Workspace that is:

- simple enough for users to understand as a filesystem-like workspace
- robust for hundreds of files and many folders
- professional and consistent with the rework design system
- incremental, so the old resource pages remain available until parity is reached
- backend-friendly: all heavy listing/filtering/pagination happens server-side
- aligned with the MCP filesystem-first direction without forcing that backend refactor into
  the first UI slice

Success means:

- opening `/team/:teamId/resources` is fast even when the team has hundreds of files
- the browser never needs `limit=10000` document/resource fetches for normal rendering
- expanding a folder fetches only what is needed for that folder
- document rows are paginated and stable under refresh/task updates
- upload/processing feedback stays integrated with the existing task tray
- old pages can be removed once the v2 page reaches parity

---

## 3. Non-Goals

FRONT-09 does not implement:

- the MCP filesystem backend described by `docs/swift/design/FILESYSTEM.md`
- anonymous/public file sharing links
- a full document processing graph or analytics console
- a new control-plane binary proxy
- a complete rewrite of prompt marketplace or agent prompt governance
- deletion of old knowledge/resource pages before the v2 route is validated

---

## 4. Product Model

### 4.1 One workspace, typed views

> **Superseded by §13 (2026-07-25).** This table predates FILES-04, which has since shipped
> all four roots natively (`docs/swift/design/FILESYSTEM.md`). "Agent/User Files" is no
> longer a future item — it, "Espace partagé", and "Espace perso" are live today alongside
> Documents/Corpus. Kept below for history; see §13.1 for the current product model.

The user-facing mental model is a workspace with typed views:

| View | Primary content | First release |
| --- | --- | --- |
| Documents | uploaded/ingested files in libraries | yes |
| Agent/User Files | generated or uploaded assets intended for exchange with agents | later, after FILES-01 backend path |
| Chat Contexts | curated reusable chat context resources | later |
| Templates | reusable business templates | later |
| Prompts | should stay primarily in `PromptsPage`; only link from workspace if needed | later/optional |
| Operations | processing/admin operations | not in the main workspace v1 |

Documents are the first implementation target because they are the highest-volume area
and already have upload, processing, preview, and task status behavior.

### 4.2 Recommended layout

> **Superseded by §13.2 (2026-07-25).** The 3-pane layout below is what phases A/C/D shipped
> as `TeamResourcesPage` (tree on the left, all four roots expandable at once). §13.2 proposes
> replacing the left tree with a tab switcher (one root at a time) plus a breadcrumb
> drill-down inside the selected root.

Use an application workspace layout, not a landing-page or card dashboard:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Header: title, storage usage, primary actions                        │
├───────────────┬─────────────────────────────────────┬───────────────┤
│ Library tree  │ File list / table                    │ Detail drawer │
│               │ Search + filters + selection actions │ optional      │
│               │ Paginated rows                       │               │
└───────────────┴─────────────────────────────────────┴───────────────┘
```

Rules:

- left pane is for folders/libraries only
- center pane is the only place where many files render
- detail/preview drawer is optional and lazy
- upload/create actions are near the header or selected folder context
- no nested cards; use full-height panels and dense rows
- no MUI in `src/rework`

### 4.3 Route strategy

Initial route:

- keep the old route as default
- add a v2 route or flag for testing:
  - `/team/:teamId/resources-v2`
  - or `/team/:teamId/resources?variant=rework`

After validation:

- make v2 the default `/team/:teamId/resources`
- keep old route hidden behind `/team/:teamId/resources-legacy` for one release
- remove old route and old components after parity and sign-off

Use `/resources` as the canonical spelling. Keep `/ressources` only as a compatibility
redirect if needed.

---

## 5. Frontend Architecture

### 5.1 Page boundary

Add:

```
apps/frontend/src/rework/components/pages/KnowledgeWorkspacePage/
```

The page owns:

- route params and query params
- selected tab/view
- selected team/personal context
- high-level loading/error states
- composition of organisms

The page must not own row-level API orchestration. That belongs in hooks.

### 5.2 Hooks

Add hooks under:

```
apps/frontend/src/rework/features/knowledgeWorkspace/
```

Recommended hooks:

| Hook | Responsibility |
| --- | --- |
| `useKnowledgeWorkspaceRouteState` | parse/update `view`, `folder`, `q`, `page`, `sort` query params |
| `useLibraryTree` | fetch visible folder tree/summary for a team/personal scope |
| `usePagedDocuments` | fetch one page for selected folder/search/sort/filter |
| `useDocumentSelection` | local selection state for current result set |
| `useDocumentWorkspaceActions` | preview, download, toggle retrievable, remove from library |
| `useDocumentTaskRefresh` | react to task completion without refetching the world |
| `useStorageUsage` | storage usage and quota display |

The hooks should return plain view models so components do not need to know the raw
Knowledge Flow DTO shape.

### 5.3 Components

Use rework hierarchy from `FRONTEND_CODING_GUIDELINES.md`.

Atoms, only if missing:

- `FileTypeIcon`
- `StatusDot` or reuse existing `IndicatorDot`

Molecules:

- `WorkspaceBreadcrumb`
- `KnowledgeToolbar`
- `LibraryTreeRow`
- `DocumentRow`
- `DocumentProcessingPills`
- `SelectionActionBar`
- `PaginationControls`
- `StorageUsageMeter` or reuse `StorageProgressBar` if it is generic enough

Organisms:

- `KnowledgeWorkspaceLayout`
- `LibraryTreePanel`
- `DocumentListPanel`
- `DocumentDetailDrawer`
- `WorkspaceUploadDrawer` wrapper around existing `DocumentUploadDrawer`

Existing reusable components:

- `SearchField`
- `FilterChips`
- `Button`
- `IconButton`
- `InlineDrawer`
- `PageEmptyState`
- `ServiceNotice`
- `TaskIndicator`
- `TaskTray`
- `DocumentUploadDrawer`

### 5.4 State rules

- selected folder lives in route query params when practical
- current page/sort/filter lives in route query params
- expanded tree state can live in local storage
- selection state is local to the current result set and clears when folder/search changes
- row actions must be idempotent and invalidate only the affected page/folder
- uploads register task IDs and refresh the selected folder when the task succeeds

---

## 6. Backend Contract

The v2 UI should use existing endpoints only where they meet the performance contract.
Backend adaptation is allowed and expected where the existing API shape encourages
client-side bulk loading.

### 6.1 Existing useful endpoints

Already useful:

- `GET /knowledge-flow/v1/tags?type=document&ownerFilter=...&teamId=...`
- `POST /knowledge-flow/v1/documents/metadata/browse`
- upload/process endpoints used by `DocumentUploadDrawer`
- document preview/download command endpoints used by existing document commands

Risky for the v2 page if used naively:

- `limit=10000` tag loads for every render
- tag responses with large `item_ids` arrays when the UI only needs counts
- broad `POST /documents/browse` because it currently fetches/filter/sorts full sets in
  service/controller before slicing
- `GET /resources?kind=...` because it returns all resources for a kind

### 6.2 Required browse contracts

Add or adapt Knowledge Flow endpoints so the UI can stay paginated.

#### Library tree summary

Preferred:

```
GET /knowledge-flow/v1/libraries/tree
  query:
    type=document|chat-context|template|prompt
    owner_filter=personal|team
    team_id?: string
    path_prefix?: string
    include_counts=true

Response:
{
  nodes: [
    {
      id: string,
      name: string,
      path: string,
      parent_path: string | null,
      direct_count: number,
      subtree_count: number,
      permissions: string[],
      owner_id?: string,
      updated_at?: string
    }
  ]
}
```

Rules:

- do not include full `item_ids` arrays by default
- counts must be cheap enough for hundreds of files
- permissions are included so the UI does not perform per-folder permission probes
- stable sort by path/name

Alternative if a new endpoint is too much:

- extend existing tag listing with `include_item_ids=false` and `include_counts=true`

#### Paged documents

Preferred:

```
POST /knowledge-flow/v1/documents/metadata/browse
Body:
{
  tag_id: string,
  offset: number,
  limit: number,
  query?: string,
  sort?: [{ field: "name"|"updated_at"|"size"|"processing_status", direction: "asc"|"desc" }],
  filters?: {
    retrievable?: boolean,
    processing_stage?: string,
    mime_prefix?: string
  }
}

Response:
{
  documents: DocumentMetadata[],
  total: number,
  next_offset: number | null
}
```

Rules:

- default page size: 50
- maximum page size: 200
- sort is stable, deterministic, and applied before pagination
- search/filter happens in the backend before pagination
- response includes `total` and `next_offset`
- no page should require fetching documents from sibling folders

The current `browse_metadata_in_tag` store path already paginates by tag in Postgres.
FRONT-09 should harden sort/search/filter there instead of returning full sets to the
browser.

#### Paged resources

Existing `GET /resources?kind=...` returns the full list. Add:

```
POST /knowledge-flow/v1/resources/browse
Body:
{
  kind: "chat-context"|"template"|"prompt",
  tag_id?: string,
  offset: number,
  limit: number,
  query?: string,
  sort?: [{ field: "name"|"updated_at", direction: "asc"|"desc" }]
}

Response:
{
  resources: Resource[],
  total: number,
  next_offset: number | null
}
```

This can wait until the documents slice is stable if documents are the first v2 view.

---

## 7. Performance Contract

The frontend must obey these rules:

- never fetch all documents for a team only to render one folder
- never fetch all resources of a kind for routine rendering
- never request `limit=10000` in the v2 workspace path
- do not prefetch every folder's first page on initial mount
- load folder counts through summary endpoints, not by loading file rows
- cache pages per `teamId + folderId + query + filters + sort`
- abort or ignore stale requests when users switch folders quickly
- render only the current page; use virtualization only if a later view intentionally
  supports page sizes above 200
- task completion refreshes the current folder/page, not the whole tree unless the task
  changes folder membership

Initial budgets:

| Scenario | Target |
| --- | --- |
| Open workspace with 500 files across folders | one tree-summary request + one document page |
| Switch folder | one document page request |
| Search within folder | debounced request, no tree refetch |
| Upload completes | one current-folder page refresh + storage usage refresh |
| Toggle retrievable | optimistic row update + single row/page invalidation |

---

## 8. UX Contract

The first screen should feel like a focused operations tool:

- compact header with title, storage usage, and upload/create actions
- no marketing hero or oversized cards
- folder tree remains visible while browsing
- document list is dense but readable
- row actions use icons with tooltips
- processing status is visible without forcing the user into a separate operations page
- bulk actions appear only when selection is active
- empty states are concise and action-oriented
- mobile can stack tree/list/detail, but desktop is the primary workflow for v1

Accessibility:

- tree rows are keyboard navigable
- row actions have labels
- selection controls use native checkbox semantics
- pagination controls expose current page and disabled states

---

## 9. Workplan

> §13 (2026-07-25) adds phases G/H/I below: tab navigation + breadcrumb, a rich `DataTable`
> row (size/created/modified/author/status columns), search/sort, and usage dashboard cards.

### FRONT-09.A — RFC, route, and shell

- [ ] Add route-gated `KnowledgeWorkspacePage` under rework.
- [ ] Keep legacy resource pages as default.
- [ ] Add v2 route or variant query for manual testing.
- [ ] Render loading/error/empty shell using rework `ServiceNotice` and `PageEmptyState`.
- [ ] No MUI imports in new rework files.

Acceptance:

- v2 page can be opened without affecting the old route
- no data-heavy calls happen before the shell has team context

### FRONT-09.B — Backend browse hardening

- [ ] Add library tree summary or extend tag listing with counts and no `item_ids`.
- [ ] Harden document browse by tag with server-side search/filter/sort and `next_offset`.
- [ ] Add tests for pagination stability with 250+ documents.
- [ ] Add tests proving tag counts do not require returning all item IDs.
- [ ] Add resources browse endpoint if chat-context/template v2 views are included in this slice.
- [ ] Regenerate Knowledge Flow OpenAPI types.

Acceptance:

- document list can render a folder with 500 files using bounded requests
- backend tests prove page 1/page 2 do not overlap and total is stable

### FRONT-09.C — Read-only documents v2

- [ ] Implement `useLibraryTree`.
- [ ] Implement `usePagedDocuments`.
- [ ] Implement `KnowledgeWorkspaceLayout`, `LibraryTreePanel`, and `DocumentListPanel`.
- [ ] Add folder selection, search, sort, pagination, and document row rendering.
- [ ] Add preview/download actions using existing document commands.

Acceptance:

- user can browse documents without upload/edit/delete
- no `limit=10000` document request appears in the v2 path
- frontend tests cover folder switch, search, loading, empty, and pagination states

### FRONT-09.D — Mutations and task integration

- [ ] Add create-library flow.
- [ ] Reuse or wrap `DocumentUploadDrawer`.
- [ ] Add task registration and refresh-on-success for the current folder.
- [ ] Add toggle retrievable.
- [ ] Add remove-from-library and bulk remove.
- [ ] Add storage usage refresh after upload/delete.

Acceptance:

- upload/process shows task feedback and refreshes only the affected view
- bulk remove does not refetch unrelated folders

### FRONT-09.E — Detail drawer and polish

> Native PDF rendering and an assistant side panel for the drawer's preview/open action
> are tracked separately as `FRONT-13` (`docs/swift/rfc/DOCUMENT-VIEWER-AI-PANEL-RFC.md`) —
> wire the preview action to that shared `DocumentViewer` component once it lands, rather
> than building a second one here.

- [ ] Add `DocumentDetailDrawer`.
- [ ] Show metadata, processing stages, summary/keywords, size, dates, owner, and actions.
- [ ] Make row and drawer states consistent after mutations.
- [ ] Add responsive behavior for narrow screens.
- [ ] Record UX review notes in `COMPONENT-UX.md`.

Acceptance:

- dense list remains usable for repeated work
- detail view does not force navigation away from the workspace

### FRONT-09.F — Resource views and legacy retirement

- [ ] Add paged chat-context/template resource views if product still wants them in the workspace.
- [ ] Keep prompts primarily in `PromptsPage`; link rather than duplicate unless product decides otherwise.
- [ ] Switch `/team/:teamId/resources` to v2 after documents are validated.
- [ ] Keep `/team/:teamId/resources-legacy` for one release.
- [ ] Remove old MUI resource/document library components after parity.

Acceptance:

- old route can be retired without losing document workflows
- users with hundreds of files have better performance than the old page

---

## 10. Test Plan

Frontend:

- hook unit tests for route state, pagination cache keys, and selection clearing
- component tests for tree panel, document list, empty/error/loading states
- integration tests with mocked RTK Query responses for:
  - open workspace
  - switch folder
  - search
  - page next/previous
  - upload task success refresh
  - bulk selection clear/remove

Backend:

- Knowledge Flow tests for:
  - tree summary counts
  - permissions on tree nodes
  - document browse pagination with 250+ docs
  - stable sort under duplicate names/dates
  - query/filter applied before pagination
  - resource browse pagination if implemented

Manual:

- validate with a seed set of at least 500 documents across at least 20 folders
- verify first paint and folder switch request counts in browser devtools
- verify no old route regressions while v2 is behind route/flag

---

## 11. Open Decisions

1. Should chat contexts and templates stay in the same workspace or move to dedicated
   rework pages like prompts?
2. Should v2 use `/resources-v2` or a query flag while testing?
3. Do we want cursor-based pagination now, or is offset pagination sufficient for the first
   v2 release?
4. Should "User Assets" become part of the MCP filesystem view from `FILES-01` instead of
   the document-library/tag model?

Recommendation for decision 3: start with offset pagination plus stable sort, because the
existing backend already has an offset path. Revisit cursor pagination only if concurrent
mutation churn makes page stability poor in real use.

---

## 12. Rollout And Removal Gate

Do not delete old pages until:

- document browse parity is validated
- upload/process parity is validated
- delete/remove/toggle parity is validated
- large-library validation passes
- UX review accepts the desktop workflow
- the route switch has spent one release with a legacy fallback

Removal candidates after gate:

- `apps/frontend/src/pages/KnowledgeHub.tsx`
- `apps/frontend/src/pages/KnowledgePage.tsx` legacy wrapper portions
- `apps/frontend/src/components/documents/libraries/*` once no route imports them
- `apps/frontend/src/components/resources/*` once resource views are replaced or retired

---

## 13. Amendment (2026-07-25) — Resources dashboard v2: tab navigation, rich table, usage cards

**Status:** proposed — triggered by review of a UI mockup for `TeamResourcesPage`; not yet
scheduled or implemented. Written against the codebase as it stands today (phases A/C/D of
this RFC already shipped `TeamResourcesPage`, `DocumentWorkspace`, `TeamFilesystemBrowser`,
`AgentFilesystemBrowser` — none of that is being redone here, only extended).

### 13.1 Updated product model (supersedes §4.1's Documents/Agent-User-Files split)

FILES-04 has shipped all four roots natively since this RFC was written. The current,
accurate model:

| View | Primary content | Status |
| --- | --- | --- |
| Corpus d'équipe | ingested documents, RAG-indexed (formerly "Documents") | live — `DocumentWorkspace` |
| Espace perso | user's private files inside the team | live — `TeamFilesystemBrowser` |
| Espace partagé | team-shared files; hidden for personal teams (`isPersonalTeam`) | live — `TeamFilesystemBrowser` |
| Agents | per-agent-instance generated files, grouped by agent | live — `AgentFilesystemBrowser` |
| Chat Contexts / Templates / Prompts / Operations | unchanged from §4.1 | still later/out of scope |

### 13.2 Updated layout (supersedes §4.2's 3-pane tree)

Replace the always-expanded left tree with a tab switcher — one root visible at a time,
matching the four rows above — plus a breadcrumb drill-down inside the selected root:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Header: title, subtitle      [📊 chip] Stockage (team quota) 4.2/5 Go│
├─────────────────────────────────────────────────────────────────────┤
│ Usage cards (§13.5, 120px), only rendered while the chip is active   │
├─────────────────────────────────────────────────────────────────────┤
│ [Corpus d'équipe] [Espace perso] [Espace partagé] [Agents]           │
├─────────────────────────────────────────────────────────────────────┤
│ Breadcrumb: Ressources > Dossier 1 > Dossier 2      [+] [↑] [search] │
│ DataTable (§13.3), paginated                                         │
└─────────────────────────────────────────────────────────────────────┘
```

Revised 2026-07-27: the team storage quota (existing `TeamStorageResponse`, no new
backend) sits top-right of the page header, next to the title/subtitle — always visible.
**Revised again 2026-07-27** (second pass, developer request): the stats section's
show/hide control is a `SettingChip` immediately to the quota's left in that same header
row, not a button inside the cards' own row — see §13.5. `TeamResourcesPage` conditionally
renders `ResourceStatsCards` on that chip's state; the cards row itself carries no chrome
of its own beyond the two 120px cards.

Reuse the existing `Breadcrumb` molecule
(`shared/molecules/Breadcrumb/Breadcrumb.tsx`) — already built and tested. The optional
detail drawer (§5.1/§5.4) is unaffected.

Open question (see §13.6 decision 7): does dropping "all roots expanded at once" regress
any workflow that relied on seeing two roots side by side? No such workflow exists in the
current code, but that doesn't rule out expected demand — needs a UX pass before this
lands, not an assumption baked into the plan.

### 13.3 Rich table rows — adopt `DataTable`, retire single-line rows

`shared/molecules/DataTable/DataTable.tsx` already has the exact pagination footer this
amendment needs (rows-per-page 20/50/100, first/prev/page-number/next/last), built and
shipped separately from this RFC.

**Revised 2026-07-27, from mockup review** (supersedes the original §13.3 column list —
no longer Création+Dernière MAJ as two 2-line date+author columns, and no longer a
dedicated Statut column):

Columns: Name (folder/file-type icon + name), Taille, **Création** (date + time only),
**Auteur** (single flat column — the user who added the document/created the folder;
**not** two-line, and **not** paired with a "Dernière MAJ" column, which is dropped from
the table entirely), an unlabeled status-chip cell, and one action cell (Preview icon +
`⋮` more menu).

- **Corpus d'équipe:** zero backend change. `DocumentMetadata` already carries every field
  needed: `file.file_size_bytes`, `identity.created`/`identity.author`.
  **Revised 2026-07-27 — `identity.author` is the wrong field for the Auteur column.**
  It's populated from the file's own embedded metadata (e.g. a .docx's "Author" core
  property, see `docx_markdown_processor.py`), not from the Fred/Keycloak user who
  uploaded it. `identity.last_modified_by` isn't a substitute either — it's a mix of the
  same embedded-metadata field and, on later in-app mutations (rename, retag), the acting
  Fred user's uid; it is never stamped with the uploader at ingestion time. No field for
  "who uploaded this" exists on `Identity` today. **Decision (developer-confirmed
  2026-07-27):** add it properly — see decision 10 and FRONT-09.L below. Until that field
  ships, the Auteur cell renders `—` for documents rather than showing the wrong person.
  **Revised 2026-07-28 — `identity.created` was also the wrong field for Création, same
  root cause as Auteur:** it's the file's own embedded "created" metadata (e.g. a .docx's
  core property) when a processor extracts one at all — the PDF processor doesn't even
  try, so `identity.created` is always empty for a PDF (`pdf_markdown_processor.py`'s
  `extract_file_metadata` only returns title/author/page_count). Unlike Auteur, no new
  field was needed: `SourceInfo.date_added_to_kb` already exists, is already exposed to
  the frontend (`knowledgeFlowOpenApi.ts`), and is already stamped correctly — its Pydantic
  `default_factory` sets it to ingestion time whenever `base_input_processor.py` builds a
  document's `SourceInfo` without passing one explicitly. Fixed by pointing the Création
  column at `doc.source.date_added_to_kb` instead of `doc.identity.created` — a frontend-
  only change, landed 2026-07-28.
- **Espace perso / Espace partagé / Agents:** `FilesystemResourceInfoResult` (the `/fs` DTO)
  only carried `size`, `modified`, `created_by` before this RFC — no separate `created`
  timestamp. Added in `mcp_fs_service.py`'s `_stamp_provenance` (workplan phase H) —
  **v1 approximation**: local/MinIO/GCS track no creation time distinct from mtime, so
  `created` mirrors `modified`. `modified_by` was also added (mirrors `created_by`) but,
  per the 2026-07-27 mockup review, **is not surfaced as a column** — the data stays on
  the DTO for a later "Dernière MAJ" pass if one gets scheduled, not wasted, just unused
  for now.

**Status chip (replaces the Statut column):** no chip at all for the common case
(ingested/ready — silence, not a green checkmark). A chip only appears for a state that
needs attention: `processing` → tertiary ("Traitement..."), `raw`/pending → warning ("En
attente"), `failed` → error ("Erreur"). This is a rendering change only — reuses
`DocStatusBadge`'s existing color mapping (§ already updated 2026-07-25) but as a Chip,
not the dot+label pattern, and returns nothing for `ready` instead of a colored dot. Build
as a small new presentational piece (not a `DocStatusBadge` prop toggle) so the existing
dot+label rendering used elsewhere is untouched.

**"by AI" chip:** reuses the existing `origin === "agent_generated"` provenance signal
(`provenance.py`, already computed for Espace perso/partagé/Agents by `_stamp_provenance`).
**Does not apply to Corpus** — ingestion is never agent-driven in the current provenance
model (`derive_provenance` returns `ORIGIN_INGESTED`/`PRODUCER_INGESTION` for `/corpus`,
never `agent_generated`), so Corpus rows never show this chip in v1, even though the
mockup shows one on a Corpus row — treated as a mockup/reality mismatch, not a new
tracking requirement, per developer confirmation 2026-07-27.

**Unified Preview action:** the row's eye icon is the only preview affordance — no second
"markdown preview" icon. It opens `shared/organisms/DocumentViewer/DocumentViewer.tsx`
(already built, FRONT-13), extended with an in-viewer "Fichier"/"Raw" toggle so the user
can switch to the extracted-markdown view even for a file `DocumentViewer` would otherwise
auto-render natively (e.g. a PDF) — today it silently picks one strategy per file type with
no user-facing choice. New optional prop, default off, so `DocumentViewerPage` and the
current `DocumentWorkspace` preview drawer keep their existing behavior unless they opt in.

**Team storage quota in the page header:** reuses the existing control-plane
`TeamStorageResponse`/`max_resources_storage_size` quota already wired for `TeamUsagePage`
— no new backend. Shown once per page (team-wide), not per-tab.

### 13.4 Search + sort

No search input or sort control exists in any of the three current browser components —
folders/files are alphabetically pre-sorted client-side only. §6.2's
`POST /documents/metadata/browse` contract already specs `query?` and `sort?` fields; they
were anticipated but never wired to a UI control for Corpus. The `/fs/ls` endpoint backing
the other three roots has no equivalent params yet — see §13.6 decision 6 for whether that
gap needs closing in this same phase.

### 13.5 Usage dashboard cards

- **Histogram, files by type:** `shared/molecules/BarChart/BarChart.tsx` already exists
  (used on `DataHub`/`TeamUsagePage`). Backed by a new `FileTypeBucket` enum
  (`fred_core.documents.document_structures`, 5 buckets: pdf/text/ppt/excel/other) and
  `file_type_bucket(name)` mapper, shared by both new stats endpoints below.
- **Size by type — revised 2026-07-27, developer request: not a pie chart.** A new
  `SizeByTypeBar` (`TeamResourcesPage/ResourceStatsCards/SizeByTypeBar.tsx`) — one
  full-width horizontal bar split into colored segments proportional to each type's
  share of total size, legend inline below it inside the same card (nothing renders
  outside the card's bounds). Deliberately not a `PieChart` variant: a single stacked
  row with a fixed legend fits the compact card footprint below in a way a donut +
  external legend does not. Colors are an explicit, meaning-carrying assignment, not
  the generic sequential `SERIES_COLORS` slice used for the histogram: orange = PDF,
  blue = Texte, red = PPT, green = Excel/CSV, grey = Autres — reusing
  `MultiSeriesLineChart`'s existing `SERIES_COLORS` values (already vetted for both
  themes) rather than picking new hex codes. `PieChart.tsx` itself reverted to its
  pre-FRONT-09 state — its `colors`/`compact` props, added then made unused by this
  swap, would have been dead code.
- **Card footprint — revised 2026-07-27:** both cards fixed at 120px tall, 8px border
  radius, 12px padding (down from the initial 220px/16px/24px pass) — `compact` prop
  on `BarChart`, dedicated sizing on `SizeByTypeBar`. The quota/limit total
  (`control_plane_backend/teams/service.py:1203` `max_resources_storage_size`) is
  unchanged and rendered separately in the page header (§13.2), not composed into
  either card.
- **Toggle — revised 2026-07-27:** the show/hide control for this whole section moved
  out of the cards' own row (it displaced them vertically) into the page header, as a
  `SettingChip` (icon `bar_chart`, `activeColor="secondary"` — a new opt-in prop,
  default `"primary"`, so every other `SettingChip` caller is unaffected) placed left
  of the storage quota. `ResourceStatsCards` no longer owns open/close state — the
  parent conditionally renders it.
- **Corpus:** `GET /tags/stats?team_id=...` (`tag_controller.py`) — computed on read by
  `TagService.get_corpus_type_stats`, unioning `get_document_metadata_in_tag` over every
  team-authorized library tag, deduped by `document_uid`. Not an incrementally-maintained
  counter (unlike `_adjust_team_storage`'s running total) — simpler and can't drift, and
  team library counts are bounded, so an on-read scan stays cheap.
- **Espace perso / Espace partagé / Agents:** `GET /fs/stats/{path:path}`
  (`mcp_fs_controller.py`) — recursively lists files under the given writable path via
  `WorkspaceFilesystem.list_recursive_files` (reuses the same recursive listing
  `list(...)` already gets from storage, without the direct-children collapsing) and
  buckets by extension. 400s if pointed at `/corpus` — corpus stats are a distinct
  aggregate over `DocumentMetadata`, not raw filesystem entries.
- **Tokens consumed by ingestion, + evolution graph:** **no tracking exists today.**
  `TeamUsagePage` already tracks LLM token usage over time/by-agent/by-model
  (`useUserTokenUsageOverTimeQuery` and siblings), but that is chat/agent inference usage —
  not tokens spent by the ingestion pipeline's own LLM calls (summarization, embedding).
  Verified: no token accounting exists anywhere in `knowledge_flow_backend`'s ingestion
  path. This needs new instrumentation at the LLM/embedding call sites used during
  ingestion — a different layer than the Resources UI. See §13.6 decision 5.

### 13.6 New open decisions (extends §11)

5. Should ingestion-time token tracking be its own tracked item (likely an `OBSERV-xx` ID,
   since it's metrics/instrumentation, not a browser feature) rather than part of FRONT-09's
   UI scope? **Recommendation: yes** — it touches LLM call instrumentation, not the
   resources browser, and shouldn't block phases G/H/I below.
6. Do Espace perso / Espace partagé / Agents get server-side search/sort in this same
   phase, or does client-side sorting stay acceptable there given smaller expected tree
   sizes? **Recommendation: defer** — ship search/sort for Corpus first (already spec'd in
   §6.2), revisit the other three roots once real usage data shows tree sizes justify it.
7. Does replacing the always-expanded tree with tabs regress a workflow that benefited
   from seeing multiple roots at once? Needs a UX pass before §13.2 is implemented.

### 13.7 Workplan additions

#### FRONT-09.G — Tab navigation + breadcrumb

- [ ] Replace `TeamResourcesPage`'s always-expanded root tree with a tab switcher (Corpus
      d'équipe / Espace perso / Espace partagé / Agents), keeping the existing
      `isPersonalTeam` rule that hides Espace partagé.
- [ ] Wire the existing `Breadcrumb` molecule to drive drill-down inside the selected root.
- [ ] Update `docs/swift/ux/COMPONENT-UX.md` with the new navigation model, noting it
      supersedes the tree description.

Acceptance: switching tabs and drilling into folders never triggers a request for a
sibling root's content.

#### FRONT-09.H — Rich table + search/sort

- [x] Add `created`/`modified_by` to `FilesystemResourceInfoResult` in Knowledge Flow;
      regenerate the OpenAPI client (landed, commit `d8639314`).
- [x] Replace `DocRow`/`FsEntry` single-line rows with `DataTable` (columns: Name, Taille,
      Création, Auteur, an unlabeled status-chip cell, Preview + `⋮` actions — revised
      2026-07-27, no Dernière MAJ column, no dedicated Statut column) — landed on all four
      tabs (Corpus d'équipe: commit `e480c027`; Espace perso / Espace partagé / Agents:
      the "other three tabs" plan below, complete as of Step 3 2026-07-29).
      `TeamFilesystemBrowser`/`AgentFilesystemBrowser` and their old single-line rows are
      deleted.
- [x] Build the status-chip cell: nothing for `ready`; a Chip (tertiary/warning/error) for
      processing/pending/failed. New small piece, not a `DocStatusBadge` variant
      (`StatusChip.tsx`, commit `162dd8cb`). Wired on Corpus; not yet on the other 3 tabs.
- [x] Build the "by AI" chip cell from `origin === "agent_generated"` (`ByAiChip.tsx`,
      commit `162dd8cb`) — Corpus rows never show it (no agent-generated concept there
      today). Not yet wired anywhere, since it only applies to the 3 tabs not started.
- [x] Collapse the row's two preview icons into one: `DocumentViewer` gained
      `showRawToggle` (commit `162dd8cb`), wired on Corpus's preview drawer.
- [x] Add the team storage quota (existing `TeamStorageResponse`) to the page header,
      top-right, always visible (commit `d9cc6b05`).
- [x] Wire `DataTable`'s pagination footer to Corpus's server-side offset/limit contract
      (§6.2), not full-set client pagination — **landed 2026-07-28**. `DataTable` gained a
      `serverPagination` prop (`totalCount`/`offset`/`limit`/`onOffsetChange`/optional
      `onLimitChange`) alongside the existing client-side `pageSize` mode; the two are
      mutually exclusive, `serverPagination` wins. The old `ResourcePagination` widget
      (a separate component below the table) is deleted — Corpus now uses the same
      always-visible footer as the members table, permanently shown (not conditional on
      total > page size). `DocumentWorkspace`'s rows-per-page is now dynamic
      (`loadTagPage`'s `limit` param, default 50) instead of the fixed `PAGE_SIZE`
      constant. Espace perso / Espace partagé / Agents pass neither `pageSize` nor
      `serverPagination` to `ResourceExplorer` — `DataTable` renders the full unpaginated
      list for these three tabs (§13.6 decision 6 — documented interim state, no `/fs`
      server pagination contract yet).
- [ ] Add a search input wired to `POST /documents/metadata/browse`'s existing `query`
      field for Corpus.
- [ ] Add a "Trier par" sort control wired to the existing `sort` field for Corpus.

**Corpus-only interim gaps, landed with the DataTable rewrite (commit `e480c027`),
not regressions — the old tree never had a "current folder" concept to compare against:**
dropping OS files now only works directly on a folder row (not anywhere inside its
formerly-expanded subtree, since folders no longer nest visually); per-folder aggregate
"N processing / N failed" badges are dropped from folder rows (each document's own status
chip is still visible one level down).

Acceptance: all four tabs show the same column set with real data, no `limit=10000`
fetches; search/sort round-trip through the backend for Corpus; the other three tabs at
minimum keep working with client-side sort as a documented interim state (§13.6 decision 6).

**Progress 2026-07-29 (Step 1 of the "other three tabs" plan):** the card+toolbar+table
shell — back button, breadcrumb, caller-supplied toolbar actions, an optional search box,
loading/empty states, `DataTable` — is extracted from `DocumentWorkspace.tsx` into a new
generic `ResourceExplorer<T>` (`shared/organisms/ResourceExplorer/`), and Corpus rewired
onto it with zero visible/behavioral regression (all 3 pre-existing `DocumentWorkspace`
test files pass unmodified). `ResourceExplorer` has no knowledge of tags/documents/`/fs` —
columns, rows, and every cell's rendering stay 100% caller-supplied, so it carries no
Corpus-specific assumption that would block reuse. Decided before starting (developer
confirmation): the other three tabs will adopt breadcrumb drill-down (replacing today's
always-expanded tree) when their turn comes; `/fs` gets client-side pagination for now
(no backend contract change). Espace perso / Espace partagé / Agents are **not yet wired**
onto `ResourceExplorer` — that's the next step(s), done separately.
**Superseded 2026-07-29 (Step 3):** the original plan for Agents — one
`ResourceExplorer` instance mounted per agent, each independently expandable — was
replaced before implementation by a developer correction: a single unified table for the
whole Agents tab instead (see Step 3 note below).

**Progress 2026-07-29 (Step 2 — Mon espace / Espace d'équipe):** new
`FilesystemWorkspace.tsx` (`TeamResourcesPage/FilesystemWorkspace/`) brings both
tabs onto `ResourceExplorer` with breadcrumb drill-down, replacing the old
always-expanded `TeamFilesystemBrowser` tree for these two tabs specifically.
`TeamFilesystemBrowser.tsx` itself is untouched — `AgentFilesystemBrowser` still
depends on its always-expanded-tree shape (`baseDepth`) until Agents gets its
own migration step. Beyond the table swap, developer-confirmed additions: rename
wired (`POST /fs/rename/{path}`, already existed but unused; `RenameModal` reused
as-is), a client-side search box, and multi-select + bulk delete (`BulkActionsBar`
reused as-is, `onExcludeFromSearch` simply omitted — Corpus-only concept). Uses
the real generated `FilesystemResourceInfoResult` type directly (no third
hand-typed `FsEntry` duplicate) — `ls`'s `response_model` gap (`LsApiResponse =
any`) is cast at the query boundary, not fixed backend-side this step. File-type
icon logic (`fileIconSpec`) extracted from `DocumentWorkspace.tsx` into a shared
`rework/utils/fileIconSpec.ts`, imported by both, so file-type colors now match
across every Resources tab. `WorkspaceRoot`'s root-only "+" (`FsRootAddMenu`) is
dropped for these two tabs — `FilesystemWorkspace` owns its own current-folder-
aware upload/new-folder toolbar instead (mirroring Corpus); `FsRootAddMenu` had
no remaining callers after that and was deleted. Zero remaining test regressions
(`TeamFilesystemBrowser.test.tsx` untouched, still covers Agents' engine;
`TeamResourcesPage.test.tsx` mocks updated to the new component; new
`FilesystemWorkspace.test.tsx` covers write-action gating and breadcrumb
navigation). Agents (step 3) not started.

**Progress 2026-07-29 (Step 3 — Agents, complete):** new `AgentsWorkspace.tsx`
(`TeamResourcesPage/AgentsWorkspace/`) replaces `AgentFilesystemBrowser.tsx`, and with it
the last old always-expanded tree. Per explicit developer correction to the first draft of
this step's plan, Agents is **one single table**, not N independent per-agent panels: its
root is virtual (not a real `/fs` path) — each agent instance with files is a folder row
at that root, named after the agent (falling back to "Removed agent" for an orphaned
instance id, same dedup-suffix logic `AgentFilesystemBrowser` already had for duplicate
display names). Clicking a row swaps in `FilesystemWorkspace` — reused as-is, not
duplicated — pointed at that agent's real filesystem
(`teams/{team}/agents/{instance}/users/{uid}`, the same shortcut the old code used to
skip exposing `agents/{id}/users/{uid}` as separate navigable levels). `FilesystemWorkspace`
gained one additive prop, `onNavigateAboveRoot?: () => void`, called by its back button
when already at `root` — lets a host compose it as one level of a larger virtual hierarchy;
zero behavior change for Mon espace/Espace d'équipe, which don't pass it. Cascading
cleanup: `AgentFilesystemBrowser.tsx`+`.module.css` and `TeamFilesystemBrowser.tsx`+
`.module.css`+`.test.tsx` deleted (both fully orphaned — `FolderRow`/`DocRow` are not,
`LibraryTreePlayground.tsx` still imports them independently). `WorkspaceRoot` still wraps
the Agents tab in `TeamResourcesPage.tsx` (out of scope, unlike the header removal already
done for Mon espace/Espace d'équipe in Step 2). All three steps of the "other three tabs"
plan are now landed — every Resources tab is on `ResourceExplorer`.

**Progress 2026-07-29 (later still):** the Agents tab's `WorkspaceRoot` header row
(icon + title + hint tooltip) is dropped too, same polish already applied to Mon
espace/Espace d'équipe in Step 2 — `TeamResourcesPage.tsx` now renders `AgentsWorkspace`
directly with no wrapper. `WorkspaceRoot.tsx`+`.module.css` had no remaining callers
after that (Corpus and the other two `/fs` tabs had already moved off it) and are
deleted. Every Resources tab now presents the same header-less card+table look.

#### FRONT-09.I — Usage dashboard cards

- [x] Add a per-team, per-file-type count aggregate (files-by-type histogram) — `GET
      /tags/stats` + `GET /fs/stats/{path}` (commit `d8639314`).
- [x] Add a per-team, per-file-type size aggregate alongside the existing quota/total-usage
      numbers — same two endpoints. **Not a pie chart** — see §13.5's 2026-07-27 revision:
      rendered as `SizeByTypeBar`, a stacked horizontal bar, per developer request.
- [x] Render with `BarChart` (histogram, `compact` prop) and the new `SizeByTypeBar`
      (commits `f869a611`, `1c640dbd`) — not `PieChart`, superseded per the above.
- [ ] Ingestion token-consumption card: out of scope for this phase — track separately per
      §13.6 decision 5.

Acceptance: both cards render from real per-team data with no client-side aggregation over
unbounded file lists.

### 13.8 Rename (new — not covered by phases G/H/I)

Prompted by the dashboard-v2 mockup review, which adds a "Renommer" row action
(`drive_file_rename_outline`) across all four tabs.

- **Corpus d'équipe, folder (tag) rename:** already supported —
  `PUT /tags/{tag_id}` (`tag_controller.py:155`) accepts a `TagUpdate` with
  `name`/`path`, explicitly documented as "Update a tag (can rename/move via
  name/path)". No backend change needed; only frontend wiring.
- **Corpus d'équipe, document rename:** **not supported today, but no new
  field needed.** `Identity.title` (`document_structures.py:87`, "Human-friendly
  title for UI") already exists and is unused end-to-end — reuse it instead of
  adding `display_name`. `PUT /document/metadata/{document_uid}` is
  single-purpose (retrievable toggle, `metadata/controller.py:155`); rather
  than overload it with a second unrelated query param, add a sibling
  `PUT /document/metadata/{document_uid}/title` sharing the same
  `DocumentPermission.UPDATE` check.
- **Espace perso / Espace partagé / Agents (`/fs`):** **not supported at
  all** — `mcp_fs_controller.py` has no PATCH/PUT/move verb. Needs a new
  endpoint, e.g. `POST /fs/rename/{path:path}` taking a `{new_name}` body,
  following the existing per-path-segment convention used by
  `mkdir`/`delete`/`upload`.

Rename is a mutation, not a table-shape change, so it does not belong in
FRONT-09.H — tracked as its own phase (§13.7 addition below).

### 13.9 Bulk actions bar

Prompted by the same mockup: a "select all" checkbox column drives a
contextual bulk-actions bar (outlined buttons with icon, rendered to the left
of the existing create-folder/add-file icon buttons) exposing bulk delete and
bulk "exclure de la recherche".

- **`DataTable` has no row-selection support today** (`shared/molecules/DataTable/DataTable.tsx`
  — confirmed no `checkbox`/`selection` prop). This is a shared-molecule
  extension, not a page-local hack: add an optional `selectable` mode
  (checkbox column + `onSelectionChange`) to `DataTable` itself so any future
  table (not just Resources) can opt in.
- Bulk delete reuses each tab's existing single-delete mutation, invoked per
  selected row (Corpus: `DELETE /tags/{tag_id}` cascade already exists for
  folders, per-document delete via `removeFromLibrary`; `/fs`: `DELETE
  /fs/delete/{path}` per entry). No new bulk-specific backend endpoint —
  the bar issues N requests client-side, consistent with how cascade delete
  already behaves for a single folder today.
- Bulk "exclure de la recherche" reuses `PUT
  /document/metadata/{document_uid}` (`retrievable=false`) per selected
  document; only meaningful for Corpus (the other three tabs have no
  retrievable concept), so the bar's "exclure" action is Corpus-only —
  hidden, not disabled, on the other three tabs.

### 13.10 New open decisions (extends §11/§13.6)

8. Should bulk delete show per-row progress/partial-failure state (N of M
   succeeded) or an all-or-nothing spinner? **Recommendation:** per-row
   status, consistent with the existing 3s processing-status poll pattern
   already used elsewhere on this page — a bulk op is not meaningfully
   different from N concurrent single ops.
9. Corpus document rename — does `display_name` participate in vector search
   metadata (e.g. shown in citations), or is it purely a browser-cosmetic
   field over the underlying ingested filename? **Resolved 2026-07-27:**
   cosmetic only for v1 — `display_name` is browser-display-only, citations
   keep using the ingested filename, no ingestion/citation code changes.
   **Follow-up (out of scope for FRONT-09.J):** a later phase should
   propagate `display_name` into citations and backfill it onto documents
   ingested before this field existed. Not tracked under a dedicated ID yet —
   raise a new backlog/id-legend entry when that phase is scheduled.
10. Auteur column data source (raised 2026-07-27): add `Identity.uploaded_by:
    Optional[str]`, stamped with `user.uid` at ingestion time (`base_input_processor.py`
    or the ingestion controller, wherever the acting user is already in scope — see
    `ingestion_controller.py`'s existing `created_by=user.uid` task-creation call for the
    identity plumbing already available at that call site). Leaves `identity.author`
    (file's own metadata) and `identity.last_modified_by` (mutation actor) untouched —
    this is a new, unambiguous field, not a repurposing of either. Pre-existing documents
    have no `uploaded_by` (nullable, no backfill) — Auteur renders `—` for those, same as
    today. **Resolved 2026-07-27, developer-confirmed:** implement as its own backend
    change (RFC-covered here, not deferred) — see FRONT-09.L.

### 13.11 Workplan additions (extends §13.7)

#### FRONT-09.J — Rename

- [ ] Wire "Renommer" (folder) to existing `PUT /tags/{tag_id}` for Corpus.
- [ ] Add `PUT /document/metadata/{document_uid}/title`, reusing the existing
      unused `Identity.title` field; wire "Renommer" (file) for Corpus.
      Cosmetic only (decision 9) — do not touch ingestion, vectorization, or
      citation code.
- [ ] Add `POST /fs/rename/{path:path}` to `mcp_fs_controller.py`; wire
      "Renommer" for Espace perso / Espace partagé / Agents.
- [ ] Regenerate `knowledgeFlowOpenApi.ts`.

Acceptance: renaming a folder or file in any of the four tabs updates the row
in place with no full-table refetch; renaming a Corpus document does not
break existing citations pointing at its `document_uid`.

#### FRONT-09.K — Bulk actions bar

- [ ] Add optional row-selection mode to `DataTable` (checkbox column,
      `onSelectionChange`), documented as a general-purpose molecule
      capability, not Resources-specific.
- [ ] Add the contextual bulk-actions bar (outlined buttons, left of the
      create-folder/add-file icon buttons) to `TeamResourcesPage`, wired to
      per-row delete / per-row `retrievable=false` (Corpus only) as described
      in §13.9.
- [ ] Update `docs/swift/ux/COMPONENT-UX.md` with the new selection + bulk
      action pattern.

Acceptance: selecting rows across a paginated table only affects rows on the
current page (no "select all N across all pages" ambiguity in this phase);
bulk delete surfaces per-row failures instead of silently dropping them.

#### FRONT-09.L — Auteur column: `uploaded_by` field (new — decision 10)

- [x] Add `uploaded_by: Optional[str] = None` to `Identity` (`fred-core`
      `document_structures.py`), alongside `author`/`last_modified_by`.
- [x] Stamp it with `user.uid` at ingestion — landed 2026-07-28 in
      `ingestion_service.py`'s `extract_metadata`, right after
      `processor.process_metadata()` returns (that method already receives
      `user: KeycloakUser`, no new plumbing needed; simpler than the
      `ingestion_controller.py` `created_by` route originally sketched,
      since it stamps every upload path — sync, Temporal-deferred, and
      pull — from one place instead of duplicating it per controller route).
- [x] Regenerate `knowledgeFlowOpenApi.ts` (`make update-knowledge-flow-api`).
- [x] Wire the Auteur column in `DocumentWorkspace.tsx`: `uploaded_by` is a
      uid, resolved to "Prénom Nom" via a batched `useUsersByIdsQuery` (same
      #2096 pattern as TeamAgentsPage's audit-user resolution) and the
      shared `userDisplayName()` util (#1952 pattern — full name, else
      username, else the raw uid). Falls back to `—` for documents ingested
      before this field existed (no backfill) and for folders (no uploader
      concept).

Acceptance: a freshly uploaded Corpus document shows the uploader's name/id
in the Auteur column; a document ingested before this field existed still
renders `—` (no backfill, no crash). Landed 2026-07-28.

## 13.12 Amendment (2026-07-29) — Resource spaces gated behind a feature flag

Product decision, not a technical one: the team isn't yet confident Mon
espace/Espace d'équipe/Agents (the three `/fs`-backed tabs, §13.7 steps 2-3)
pull their weight next to Corpus d'équipe. Rather than remove the code —
all three are fully implemented, tested, and landed — the Resources page
ships with **only Corpus d'équipe reachable**, and the other three sit
behind a platform-wide, off-by-default feature flag so they can be turned
back on later without a code change.

- New flag `enableAllResourceSpaces` on `FrontendFeatureFlags`
  (`control_plane_backend/config/models.py`), default `False`. Served on
  the existing authenticated bootstrap (`platform.frontend.feature_flags`
  → `build_frontend_bootstrap`, `product/service.py`) — no new backend
  wiring, this mechanism already existed (`enableK8Features`/
  `enableElecWarfare` predate this) and simply gains a third key.
- Confirmed with the developer: **global to the platform instance**
  (one `configuration.yaml` value), not a per-team setting — this is a
  company-wide product-maturity call, not something a given customer
  toggles for their own team.
- `TeamResourcesPage.tsx`: `rootTabs` only includes `"mine"`/`"team"`/
  `"agents"` when `enableAllResourceSpaces` is on; the tab switcher
  (`ButtonGroup`) itself is hidden entirely when there's nothing to switch
  between (Corpus d'équipe stays reachable either way — it's never gated).
  Every other piece of the three tabs — `FilesystemWorkspace`,
  `AgentsWorkspace`, their tests, their translations, the `mine`/`team`
  usage-stats queries — is untouched, simply unreachable while the flag is
  off.
- Considered and rejected: extending the OTHER candidate mechanism,
  `apps/frontend/public/config.json` + `isFeatureEnabled()`/`FeatureFlagKey`
  (`common/config.tsx`) — that one is fully wired frontend-side but dead:
  the real `config.json` carries no `feature_flags` key today and nothing
  populates one. `configuration.yaml`'s `FrontendFeatureFlags` is the real,
  already-populated mechanism.

Issue: https://github.com/ThalesGroup/fred/issues/2165

## 13.13 Amendment (2026-07-29) — Row/bulk "Download" action, client-side ZIP

Neither table had a full download story: `FilesystemWorkspace` had a
per-row download icon but no multi-select download; `DocumentWorkspace`
(Corpus) had no download action wired into its row at all (the command
existed in `useDocumentCommands` but wasn't connected to the table).
Landed:

- Per-row "Télécharger" `IconButton` added to `DocumentWorkspace`'s
  actions column, matching `FilesystemWorkspace`'s existing pattern
  exactly (same icon/size/color). That column is a **fixed** width
  (deliberately, so the header and body grids agree — see the comment
  above it), sized for 2 icon buttons; widened `6rem` → `8rem` for the
  3rd (preview + download + more-menu).
- New bulk "Télécharger" action in `BulkActionsBar` (new optional
  `onDownload?: () => void` prop, same "omit to hide" convention as
  `onExcludeFromSearch`) — one file downloads directly, 2+ files download
  as a single ZIP. On `FilesystemWorkspace`, a mixed folder+file selection
  silently zips just the files (no recursive folder download); the button
  hides entirely when the selection is folders-only.
- **Explicitly client-side** (developer-confirmed direction): new shared
  `downloadManyAsZip`/`fetchAuthedBlob` in `apps/frontend/src/utils/downloadUtils.tsx`,
  built on the `jszip` package (new dependency) — every file's blob fully
  round-trips through the browser before zipping, no streaming, no backend
  change. Chosen because every existing download in this app (Corpus'
  `raw_content` blob query, `/fs/download`) was already a full in-memory
  fetch, not streamed — client-side zipping is the smaller lift, not a
  new class of limitation.
- **Documented interim state, not a closed decision:** if usage shows
  people regularly bulk-downloading many/large files, this should move to
  a server-side streaming-zip endpoint instead (client-side means every
  byte of every selected file transits the browser's memory before the
  zip is even built). No such endpoint exists anywhere in the codebase
  today — the only prior art is the unrelated platform config-export zip
  (`control_plane_backend/import_export/exporter.py`, a DB/config
  snapshot, not file content). Revisit if this becomes a real pain point;
  not tracked as a separate GitHub issue while it's still speculative.
- `useDocumentCommands`'s `download` refactored to share a new `fetchBlob`
  (fetch without saving) with the bulk path, both exported from the hook.

**Follow-up (2026-07-29, same day):** the "every byte round-trips through
the browser first" cost above isn't just a future-scaling concern — it's a
real, immediate UX problem: clicking bulk "Télécharger" gave no feedback
while the zip was being fetched/built, reading as a dead/unresponsive
button until the browser's save dialog eventually appeared. Fixed with a
new `loading?: boolean` prop on the shared `IconButton` atom
(`shared/atoms/IconButton/IconButton.tsx`) — swaps the icon for a `Spinner`
sized to match, disables the button, sets `aria-busy`. `BulkActionsBar`
gained a matching `downloadLoading` prop; both `DocumentWorkspace` and
`FilesystemWorkspace` now track a `bulkDownloading` state around their
`await downloadManyAsZip(...)` call (`try`/`finally`). `loading` is a
generic addition to `IconButton` itself (not Resources-specific) since any
async icon-button action can reuse it.

**Follow-up (2026-07-29, later same day):** the per-row "Télécharger" icon
moved from a standalone button into the "more" menu, right under
"Renommer", on both tables — one action fewer competing for space in the
fixed-width actions column (reverted `DocumentWorkspace`'s column back to
`6rem`/2 buttons; `FilesystemWorkspace`'s to `4rem`/1 button, both now just
preview-or-nothing + the "more" trigger). Read-only-safe: `download` is a
non-mutating action, so both `moreOptionsForEntry`
(`FilesystemWorkspace.tsx`) and `moreOptionsForDoc` (`DocumentWorkspace.tsx`)
were restructured to always include it for files regardless of
`canWrite`/`canCreateFolder` — previously those functions returned `[]`
entirely for a read-only user, which would otherwise have silently taken
download away from users who only lost the ability to rename/delete/etc.
