# RFC: Rework Knowledge Workspace — Robust Resource Browser

**Status:** Implemented, as `TeamResourcesPage` — see `docs/swift/design/RESOURCES-DASHBOARD.md`
for the as-built product model, table contract, and known limitations. §§4-6/9/10 below
describe the original 2026-06-18 proposal, which shipped in a materially different shape
(tab switcher instead of a 3-pane tree, `ResourceExplorer`/`DataTable` instead of the
`LibraryTreePanel`/`DocumentListPanel` hooks-and-components split) — kept only for §1-3's
still-valid rationale and §7/§8/§11's still-applicable principles/open items. §12
(2026-07-25 through 2026-07-30's three amendments) is compacted to a pointer for the
same reason — its content is now `RESOURCES-DASHBOARD.md`.
**Author:** Dimitri Tombroff
**Date:** 2026-06-18
**ID:** FRONT-09
**Issue:** https://github.com/ThalesGroup/fred/issues/2128
**Related:** `docs/swift/design/RESOURCES-DASHBOARD.md` (as-built), `docs/swift/design/FILESYSTEM.md`,
`DOCUMENT-RENAME-RFC.md`

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

## 4. Product Model (original proposal — superseded, see `RESOURCES-DASHBOARD.md`)

The original mental model was a workspace with typed views (Documents first, then
Agent/User Files, Chat Contexts, Templates, Prompts, Operations later), a 3-pane layout
(library tree / file list / detail drawer), and a `/resources-v2` route strategy.

What actually shipped: all four roots (Corpus, Mon espace, Espace d'équipe, Agents) live
natively behind one tab switcher with a breadcrumb drill-down, in place at
`/team/:teamId/resources` — no parallel v2 route was needed. Chat Contexts/Templates/
Prompts/Operations stayed out of this workspace (Prompts has its own `PromptsPage`); that
question (open decision 1 below) is still open. See `RESOURCES-DASHBOARD.md` for the
current product model and table.

---

## 5. Frontend Architecture (original proposal — superseded)

Proposed a `KnowledgeWorkspacePage` page with dedicated hooks
(`useLibraryTree`/`usePagedDocuments`/...) and components
(`LibraryTreePanel`/`DocumentListPanel`/`WorkspaceBreadcrumb`/...) under a new
`features/knowledgeWorkspace/` tree.

None of that was built as specified. What shipped instead: `TeamResourcesPage` composes
per-tab workspace components (`DocumentWorkspace`, `FilesystemWorkspace`,
`AgentsWorkspace`) built on one shared, content-agnostic organism,
`shared/organisms/ResourceExplorer/`, itself built on the general-purpose
`shared/molecules/DataTable/`. See `RESOURCES-DASHBOARD.md`.

---

## 6. Backend Contract (original proposal — superseded)

Proposed a dedicated `GET /libraries/tree` summary endpoint and a `POST
/resources/browse` endpoint alongside a hardened `POST /documents/metadata/browse`.

What shipped instead: no dedicated tree-summary endpoint — the frontend fetches every tag
for the team in one bounded call (folders are a small, cheap set, unlike documents) and
builds the tree client-side; `/resources/browse` was never needed (Chat
Contexts/Templates/Prompts stayed out of this workspace). `POST
/documents/metadata/browse` (offset/limit, `total`) is the real paginated document
contract in use — its `query`/`sort` fields are specced but not yet wired to a UI control
(open decision 3 below). The three `/fs`-backed tabs use Knowledge Flow's `/fs` routes
directly; see `docs/swift/design/FILESYSTEM.md` for that route table, and
`RESOURCES-DASHBOARD.md` for how each tab maps to its backend source.

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

## 9. Workplan (original proposal — superseded)

Proposed six phases (route shell, backend browse hardening, read-only documents,
mutations, detail drawer, legacy retirement). What actually shipped covered the same
ground in a different shape and order, tracked entirely on GitHub issue #2128 rather than
a checklist here — no in-place `/resources-v2` route or legacy-fallback period was needed
since the existing route was upgraded directly. `docs/swift/design/RESOURCES-DASHBOARD.md`
is the as-built record.

## 10. Test Plan (original proposal — superseded)

The actual coverage lives with the code: `DocumentWorkspace`/`FilesystemWorkspace`/
`AgentsWorkspace`'s own `*.test.tsx` files (rendering, selection, rename, bulk
actions, search, pagination), plus each backend feature's own test module
(`knowledge_flow_backend/tests/`). No dedicated tree-summary or resources-browse
tests were needed — those endpoints were never built (§6).

---

## 11. Open Decisions

Still genuinely open:

1. Should chat contexts and templates stay in the same workspace or move to dedicated
   rework pages like prompts?
2. Should "User Assets" become part of the MCP filesystem view from `FILES-01` instead of
   the document-library/tag model?
3. Should Espace perso/Espace d'équipe/Agents get server-side search/sort, or does
   client-side filtering stay acceptable given their typically smaller trees? Deferred
   until real usage data justifies the backend work.
4. Ingestion-time token tracking (LLM calls during summarization/embedding, not chat/agent
   inference) — a separate instrumentation track, not part of this workspace's scope.
5. Bulk download is client-side ZIP (every file's blob round-trips through the browser).
   Revisit with a server-side streaming-zip endpoint if usage shows this is a real pain
   point at scale.

Resolved by shipping, no longer open: cursor vs. offset pagination (offset, per the
original recommendation); a dedicated `/resources-v2` route (not needed — the existing
route was upgraded in place).

---

## 12. Resources Dashboard v2 (2026-07-25 through 2026-07-30)

Three stacked amendments (tab navigation/rich table/usage cards; rename/bulk actions;
feature-flag gating and client-side ZIP download) shipped everything described in them.
The as-built product model, table contract, and known limitations now live in
`docs/swift/design/RESOURCES-DASHBOARD.md` — this section is intentionally not
reproduced here to avoid the same document holding two competing descriptions of the
same shipped feature. Anything still genuinely open from this work is folded into §11.

Tracked on GitHub issue #2128 (workplan phases FRONT-09.G through FRONT-09.L, all
closed) and issue #2165 (feature-flag gating decision).
