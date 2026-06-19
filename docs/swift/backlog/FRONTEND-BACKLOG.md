# Frontend Adaptation Backlog

This backlog tracks the remaining frontend migration work for Swift.

It is intentionally compact. Historical phase detail that is already closed has
been collapsed into status summaries; use git history and the referenced RFCs for
implementation archaeology.

## 0 Current Target

The frontend target is now:

- pre-auth static bootstrap reads only `/config.json` for `frontend_basename`
- auth mode is loaded from `GET /control-plane/v1/frontend/config` (FRONT-08)
- application bootstrap comes from `GET /control-plane/v1/frontend/bootstrap`
- shell-critical state comes from control-plane, not `agentic-backend`
- domain pages call their owning domain APIs after bootstrap:
  - control-plane for teams, managed agents, execution preparation, sessions
  - knowledge-flow for documents, resources, libraries, files
  - runtime for execution and runtime history via prepared URLs
- `apps/frontend/src/rework` is the target UI surface
- new rework code uses atoms/molecules/organisms, CSS modules/design tokens, and
  no MUI imports

The default development loop for frontend work is:

- `control-plane-backend`
- `knowledge-flow-backend`
- `frontend`
- optionally one reachable runtime pod for runtime-backed features

The frontend shell must still boot when no runtime pod is available.

## 1 Completed Convergence Baseline

These items are kept only as a compact record. Do not add new work under this
section; create or update the active task sections below instead.

| ID | Status | Result | Residual work |
| --- | --- | --- | --- |
| FRONT-01 | Done | Bootstrap converged around `/config.json` + control-plane bootstrap. Shell no longer needs legacy agentic config/permissions. | Typed bootstrap recovery screen remains minor/deferred. |
| FRONT-02 | Substantially done | No-security personal-team baseline works as the intended developer mode. | Two smoke checks remain useful: active team after hard refresh and navigation with one available team. |
| Backend readiness gates | Partial | Personal-team and bootstrap ownership are mostly converged in control-plane. | Bootstrap permission coverage, reserved/system-team documentation, and one no-security bootstrap regression test remain useful hardening. |
| FRONT-03 | Done | Managed agent pages use control-plane templates/instances and `agent_instance_id`. | Better unavailable-runtime messaging for enrolled instances remains polish. |
| FRONT-04 | Done | Managed session metadata belongs to control-plane; runtime owns message history. Sidebar reads control-plane sessions; chat history reads runtime prepared URLs. | Metadata freshness/reorder path remains optional. |

Frozen frontend invariants:

- no boot-time dependency on `/agentic/*`
- no frontend runtime-topology resolution
- no raw `agent_id` execution path in managed chat
- `session_id` is the frontend/runtime/control-plane conversation identity
- control-plane session metadata does not serve full runtime message history

## 2 Live Frontend Work

| ID | Owner | Status | Backlog section | Execution |
| --- | --- | --- | --- | --- |
| FRONT-05 | Dimitri | Partial | §7 | TBD |
| FRONT-08 | Simon | In progress, implemented on branch and pending review | §14 | GitHub issue #1748 / branch `1748-front-08-frontend-auth-config` |
| FRONT-09 | Dimitri | RFC proposed | §15 | TBD |

Recommended order:

1. Land FRONT-08 or confirm its final contract.
2. Keep FRONT-05 narrow: remove remaining `agenticOpenApi` usage without reviving
   deprecated surfaces.
3. Start FRONT-09 with a v2 route and backend browse hardening; keep old
   resource/library pages until parity.

## 3 Explicit Non-Goals

Do not spend migration time on:

- restoring every legacy team collaboration flow before the rework shell is clean
- perfecting security-enabled UX before no-security mode remains stable
- preserving legacy agent authoring behavior outside the control-plane managed
  instance model
- fixing old resource/library pages cosmetically when FRONT-09 is replacing them
- duplicating prompt/resource functionality across multiple pages without a
  product decision

## 4 Related Backlogs And RFCs

- [`CHAT-UI-BACKLOG.md`](./CHAT-UI-BACKLOG.md) — managed chat UI, attachments,
  rendering, and FILES-01 MCP filesystem work.
- [`FRONTEND-AUTH-CONFIG-ENDPOINT-RFC.md`](../rfc/FRONTEND-AUTH-CONFIG-ENDPOINT-RFC.md)
  — FRONT-08 auth config target.
- [`KNOWLEDGE-WORKSPACE-REWORK-RFC.md`](../rfc/KNOWLEDGE-WORKSPACE-REWORK-RFC.md)
  — FRONT-09 rework resource browser target.
- [`CONTROL-PLANE-PRODUCT-CONTRACT.md`](../design/CONTROL-PLANE-PRODUCT-CONTRACT.md)
  — control-plane product/session/admin contracts.
- [`RUNTIME-EXECUTION-CONTRACT.md`](../design/RUNTIME-EXECUTION-CONTRACT.md)
  — runtime execution/history contracts.

## 7 Phase FRONT-05 — Agentic-Backend Removal From Frontend

**ID:** FRONT-05  **Owner:** Dimitri  **Status:** Partial
**Execution:** TBD

Goal: remove all frontend imports from the legacy agentic generated API slices:

- `agenticOpenApi.ts`
- `agenticInspectionApi.ts`
- `agenticSourceApi.ts`

Context:

- `agentic-backend` has been removed from the active monorepo.
- The new managed/rework path should use `runtimeOpenApi.ts`,
  `controlPlaneOpenApi.ts`, or knowledge-flow APIs depending on ownership.
- Legacy chat components and routes were already deleted on 2026-05-21.

Remaining high-value tasks:

- [ ] Migrate remaining rework path imports from `agenticOpenApi` to runtime or
      local view-model types.
- [ ] Migrate remaining shared hooks (`useAgentSelector.ts`, `common/agent.ts`)
      or delete them if no active route uses them.
- [ ] Delete `agenticOpenApi.ts` once all imports are cleared.
- [ ] Delete `agenticInspectionApi.ts` and `agenticSourceApi.ts` once consumers
      are removed.

Already completed:

- [x] Deleted legacy `pages/Chat.tsx`.
- [x] Deleted `components/chatbot/`.
- [x] Deleted `hooks/useChatSocket.ts` and `hooks/useGroupMessages.ts`.
- [x] Deleted legacy `features/libraries/ChatDocument*`.
- [x] Migrated `hooks/useChatSse.ts` to `rework/core/hooks/useChatSse.ts`.
- [x] Migrated `UserInputSearchPolicy` to the rework `SearchPolicySelect`.

Acceptance:

- [ ] `rg "agenticOpenApi|agenticInspectionApi|agenticSourceApi" apps/frontend/src`
      returns no active imports.
- [ ] frontend code-quality passes.
- [ ] no removed legacy surface is reintroduced to satisfy type imports.

## 13 Phase FRONT-07 — Rework UI Architecture Compliance

**ID:** FRONT-07  **Owner:** Dimitri  **Closed:** 2026-06-02
**Execution:** GitHub issue #1668 / branch `1668-rework-frontend-ui-architecture-compliance`

Closed summary:

- [x] Added shared `SearchField`, `FilterChips`, and `TagInput` molecules.
- [x] Migrated `PromptsPage` to the new molecules.
- [x] Migrated `TuningFieldRenderer` enum/array controls to design-system
      molecules.
- [x] Added missing `--outline-variant` semantic color token.
- [x] Updated `COMPONENT-UX.md`.
- [x] Validated with frontend `make code-quality`.

Do not reopen FRONT-07 for new design-system work. Create a new FRONT or UX item
if a future migration slice needs additional primitives.

## 14 Phase FRONT-08 — Backend-Driven Frontend Auth Config

**ID:** FRONT-08  **Owner:** Simon  **Status:** In progress, implemented on branch and pending review
**RFC:** `docs/swift/rfc/FRONTEND-AUTH-CONFIG-ENDPOINT-RFC.md`
**Execution:** GitHub issue #1748 / branch `1748-front-08-frontend-auth-config`

Goal: move the frontend "is user security enabled?" decision out of
`apps/frontend/public/config.json` and onto a public control-plane endpoint.

Target contract:

- `/config.json` keeps only `frontend_basename`
- `GET /control-plane/v1/frontend/config` returns `user_auth`
- `security.user` in backend configuration is the source of truth
- the endpoint is public/unauthenticated because it is needed before deciding
  whether to initialize Keycloak

Implementation checklist:

- [x] Add `FrontendUserAuthConfig` and `FrontendConfig` schemas.
- [x] Add public `GET /control-plane/v1/frontend/config`.
- [x] Update frontend `loadConfig()` to fetch `user_auth` from control-plane.
- [x] Remove `user_auth` from `apps/frontend/public/config.json`.
- [x] Remove `user_auth` from Helm frontend `config_json`.
- [x] Regenerate control-plane OpenAPI types.
- [x] Document the public pre-auth surface in
      `CONTROL-PLANE-PRODUCT-CONTRACT.md §3.1`.
- [x] Validate `make code-quality` and `make test` in control-plane and
      frontend.

Remaining:

- [ ] Review/merge branch `1748-front-08-frontend-auth-config`.

## 15 Phase FRONT-09 — Rework Knowledge Workspace

**ID:** FRONT-09  **Owner:** Dimitri  **Status:** In progress — A/C/D landed 2026-06-18
**RFC:** `docs/swift/rfc/KNOWLEDGE-WORKSPACE-REWORK-RFC.md`
**Execution:** branch `1772-...-kf-similarity-search` (TeamResourcesPage)

Build a rework-native replacement for the old KnowledgeHub/resource/library
pages. This is a product and performance migration, not a cosmetic rewrite.

> **Landed 2026-06-18 (A/C/D).** Official page `TeamResourcesPage` at
> `/team/:teamId/resources` (decision: own the canonical route directly instead
> of a `resources-v2` shadow; old hub kept reachable at `/knowledge`).
> Documents-only (chat contexts now live under Prompts; the user-assets
> filesystem is not surfaced here yet). Folder tree
> (`FolderRow`) + server-paginated list (`DocRow`/`DocStatusBadge`,
> `deriveDocStatus` unit-tested) on `/documents/metadata/browse`, with upload
> drawer, new-folder drawer, download, preview, delete, toggle-searchable, and
> reprocess wired. **Deferred:** search/sort + tree-summary counts + `next_offset`
> (need FRONT-09.B backend); document **rename** (no backend endpoint); detail
> drawer (FRONT-09.E). **Needs live verification:** upload + reprocess paths
> against a running knowledge-flow backend.

### Scope

- [ ] Add a temporary v2 route, for example `/team/:teamId/resources-v2`, that can
      be tested next to the old `/team/:teamId/resources` page.
- [ ] Implement `apps/frontend/src/rework/components/pages/KnowledgeWorkspacePage/`.
- [ ] Keep the first production slice focused on documents/files.
- [ ] Reuse the existing rework upload drawer/task pattern.
- [ ] Keep old pages available until read-only browse, upload, delete, task
      refresh, empty/error states, and pagination reach parity.

### Backend And Performance Contract

- [ ] Never fetch every file/resource to render the main workspace.
- [ ] Do not use `limit=10000` or broad client-side filtering in the v2 page.
- [ ] Add or harden paginated document browse with `offset`, `limit`, `query`,
      `sort`, and filters; default page size 50, max 200.
- [ ] Add or harden a lightweight library/tree contract that returns nodes and
      counts, not every child item ID.
- [ ] Add paginated resource browse before migrating chat contexts, templates, or
      other resource kinds into the workspace.
- [ ] Ensure Postgres paths sort/filter before pagination and return `total` or
      `next_offset`.

### Workplan

#### FRONT-09.A — Route And Shell

- [x] Register the route and entry point. _(Owns `/team/:teamId/resources` directly, not a v2 shadow.)_
- [x] Create the workspace page with header, tab selector, and document list.
      _(Named `TeamResourcesPage`; detail-drawer slot deferred to FRONT-09.E.)_
- [ ] Add route-state helpers for folder, query, filters, sort, page, and
      selected document. _(Only the tab `?view=` is in the URL today; folder/page is local state.)_
- [x] Add typed loading, empty, and error states. _(Permission-denied minimal.)_

#### FRONT-09.B — Backend Browse Hardening

- [ ] Choose one canonical document browse endpoint for the v2 page.
- [ ] Add backend tests proving pagination is applied in the store/query layer
      for the Postgres path.
- [ ] Add tests for page-size clamping, stable sort, empty page, query filter, and
      permission-scoped results.
- [ ] Update generated frontend API types after the contract is stable.

#### FRONT-09.C — Read-only Document Workspace

- [x] Add hooks for library tree loading and paged document browsing.
      _(`buildTree` + `useListAllTags` + `useBrowseDocumentsByTag`.)_
- [x] Add design-system atoms/molecules for file type, status, rows, and
      pagination. _(`DocStatusBadge`, `DocRow`, `FolderRow`, `ResourcePagination`; breadcrumb/storage deferred.)_
- [x] Render only the current page; do not preload all folders or rows.
- [x] Cache pages by folder/tag. _(By tag id; query/sort caching N/A until FRONT-09.B.)_
- [ ] Ignore or abort stale responses when users switch folders/search quickly.

#### FRONT-09.D — Mutations And Task Refresh

- [x] Wire upload through the existing rework drawer/task pattern. _(`DocumentUploadDrawer`.)_
- [x] Refresh the active folder/page after upload, delete, or reprocess. _(Move/rename deferred.)_
- [ ] Preserve selection and scroll position when safe.
- [x] Surface task progress without polling the whole library tree.
      _(`DocRow` reads `selectActiveTaskForTarget`.)_

#### FRONT-09.E — Detail Drawer And UX Polish

- [ ] Add a document detail drawer with metadata, tags/folder, processing status,
      source/download/open actions, and destructive actions.
- [ ] Verify keyboard navigation for rows, drawer close, pagination, search, and
      primary actions.
- [ ] Check responsive behavior for mobile and desktop.
- [ ] Validate empty library, hundreds of files, upload in progress, failed
      processing, and permission-denied scenarios.

#### FRONT-09.F — Resource Kinds And Legacy Retirement

- [ ] Migrate chat contexts/templates/resources only after a paginated resource
      browse endpoint exists.
- [ ] Switch sidebar/navigation from old page to v2 after parity.
- [ ] Keep `/resources-legacy` or equivalent fallback for one short validation
      window.
- [ ] Remove old MUI resource/library components once v2 is default and tested.

### Acceptance

- [ ] Users with hundreds of files can browse, search, upload, and inspect files
      without loading all documents/resources into the browser.
- [ ] The v2 page uses rework atoms/molecules/organisms and imports no MUI.
- [ ] Backend tests cover pagination, sort, filters, page-size limits, and
      permission-scoped results.
- [ ] Frontend tests cover route state, loading/empty/error states, pagination,
      and mutation refresh behavior.
- [ ] Old resource/library pages remain untouched until the v2 page reaches
      functional parity.

## 16 Progress Snapshot

| Area | Status | Next useful action |
| --- | --- | --- |
| Bootstrap/auth | Mostly converged | Merge/review FRONT-08. |
| Agentic frontend removal | Partial | Finish FRONT-05 import cleanup and delete generated legacy API slices. |
| Rework design-system migration | FRONT-07 closed | Add new primitives only inside specific feature slices. |
| Knowledge/resource pages | RFC proposed | Start FRONT-09 with backend browse hardening and a temporary v2 route. |
