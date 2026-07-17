# RFC: Rework Knowledge Workspace — Robust Resource Browser

**Status:** proposed — RFC/workplan created 2026-06-18
**Author:** Dimitri Tombroff
**Date:** 2026-06-18
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
