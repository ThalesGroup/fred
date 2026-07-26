# RFC: Rework Knowledge Workspace — Robust Resource Browser

**Status:** proposed — RFC/workplan created 2026-06-18; phases A/C/D shipped as `TeamResourcesPage`
**Author:** Dimitri Tombroff
**Date:** 2026-06-18
**Amended:** 2026-07-25 — Maxime Daragon (§13 — Resources dashboard v2: tab navigation, rich
table, usage cards; supersedes parts of §4.1/§4.2, see note there)
**ID:** FRONT-09
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
│ Header: title, usage/quota cards (§13.5)                             │
├─────────────────────────────────────────────────────────────────────┤
│ [Corpus d'équipe] [Espace perso] [Espace partagé] [Agents]           │
├─────────────────────────────────────────────────────────────────────┤
│ Breadcrumb: Ressources > Dossier 1 > Dossier 2      [+] [↑] [search] │
│ DataTable (§13.3), paginated                                         │
└─────────────────────────────────────────────────────────────────────┘
```

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
shipped separately from this RFC. Columns: Name, Taille, Création (date + author),
Dernière MAJ (date + author), Statut, a preview action, and an actions menu.

- **Corpus d'équipe:** zero backend change. `DocumentMetadata` already carries every field
  needed: `file.file_size_bytes`, `identity.created`/`identity.author`,
  `identity.modified`/`identity.last_modified_by`.
- **Espace perso / Espace partagé / Agents:** `FilesystemResourceInfoResult` (the `/fs` DTO)
  only carries `size`, `modified`, `created_by` today — no separate `created` timestamp, no
  `modified_by` distinct from the original uploader. Add both fields (workplan phase H).

### 13.4 Search + sort

No search input or sort control exists in any of the three current browser components —
folders/files are alphabetically pre-sorted client-side only. §6.2's
`POST /documents/metadata/browse` contract already specs `query?` and `sort?` fields; they
were anticipated but never wired to a UI control for Corpus. The `/fs/ls` endpoint backing
the other three roots has no equivalent params yet — see §13.6 decision 6 for whether that
gap needs closing in this same phase.

### 13.5 Usage dashboard cards

- **Histogram, files by type:** `shared/molecules/BarChart/BarChart.tsx` already exists
  (used on `DataHub`/`TeamUsagePage`). Needs one new per-team, per-file-type count
  aggregate — a small addition grouping on the already-stored file type.
- **Pie chart, size by type + quota remaining:** `shared/molecules/PieChart/PieChart.tsx`
  already exists. The quota/limit and current total-usage-in-bytes numbers already exist
  server-side (`knowledge_flow_backend/features/ingestion/ingestion_controller.py:416`
  `_check_quota_before_upload`; `control_plane_backend/teams/service.py:1203`
  `max_resources_storage_size`) — but only as one aggregate total, not broken down by file
  type. Needs a new by-type size aggregate; an extension of the existing quota check, not a
  new subsystem.
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

- [ ] Add `created`/`modified_by` (naming TBD) to `FilesystemResourceInfoResult` in
      Knowledge Flow; regenerate the OpenAPI client.
- [ ] Replace `DocRow`/`FsEntry` single-line rows with `DataTable` (columns: Name, Taille,
      Création, Dernière MAJ, Statut, preview, actions) across all four tabs.
- [ ] Wire `DataTable`'s pagination footer to each tab's server-side offset/limit contract
      (§6.2), not full-set client pagination.
- [ ] Add a search input wired to `POST /documents/metadata/browse`'s existing `query`
      field for Corpus.
- [ ] Add a "Trier par" sort control wired to the existing `sort` field for Corpus.

Acceptance: all four tabs show the same column set with real data, no `limit=10000`
fetches; search/sort round-trip through the backend for Corpus; the other three tabs at
minimum keep working with client-side sort as a documented interim state (§13.6 decision 6).

#### FRONT-09.I — Usage dashboard cards

- [ ] Add a per-team, per-file-type count aggregate (files-by-type histogram).
- [ ] Add a per-team, per-file-type size aggregate alongside the existing quota/total-usage
      numbers (size-by-type + remaining-quota pie chart).
- [ ] Render both with the existing `BarChart`/`PieChart` molecules.
- [ ] Ingestion token-consumption card: out of scope for this phase — track separately per
      §13.6 decision 5.

Acceptance: both cards render from real per-team data with no client-side aggregation over
unbounded file lists.
