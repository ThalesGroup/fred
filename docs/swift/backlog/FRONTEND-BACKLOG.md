# Frontend Adaptation Backlog

## 0 Overview

### 0.1 Goal

Define a dedicated **Phase 5 frontend adaptation plan** before fixing isolated
UI bugs.

This document exists to make the next frontend work explicit and ordered:

- freeze the **target frontend bootstrap**
- define the **minimum developer startup topology**
- prioritize a **no-security, personal-team-only** configuration first
- identify which current frontend dependencies are still legacy and must be
  removed intentionally

This is a planning and boundary document first. It should reduce improvisation
before more frontend coding starts.

---

### 0.2 Development Target For This Phase

The default development loop for frontend migration should be:

- `control-plane-backend`
- `knowledge-flow-backend`
- `frontend`
- optionally one reachable runtime pod

The frontend must no longer require `agentic-backend` to boot, render the shell,
or select the active execution context.

The optional runtime pod is needed only for runtime-backed capabilities such as:

- template discovery
- managed execution preparation
- chat execution
- runtime history retrieval

The frontend shell itself must still boot when no runtime pod is available.

---

### 0.3 Core Decision

Do not continue Phase 4 by fixing one page at a time against a mixed
architecture.

Instead, define **Phase 5** as the frontend convergence phase:

- one bootstrap model
- one active-team model
- one permissions model
- one managed-agent selection model
- one intentional no-security baseline

Phase 5 should remove the remaining frontend ambiguity between:

- legacy `agentic-backend` config/session/agent flows
- new `control-plane-backend` product flows
- new `fred-runtime` execution flows

---

## 1 Target Bootstrap

### 1.1 Bootstrap Rule

The frontend bootstrap must happen in **two explicit stages**:

1. **Pre-auth static bootstrap** from `/config.json`
2. **Application bootstrap** from `GET /control-plane/v1/frontend/bootstrap`

These two stages must stay small and have distinct purposes.

---

### 1.2 Stage 0 - Pre-auth Static Bootstrap

`/config.json` remains the only browser-readable static bootstrap input.

It should exist only to provide values needed **before** any protected API call,
such as:

- frontend basename
- any minimal public auth-bootstrap hint still required before login

It must not become a second product bootstrap payload.

It must not contain:

- team state
- permissions
- managed agent state
- runtime routing
- page-level feature decisions

---

### 1.3 Stage 1 - Auth Decision

After `/config.json` is loaded, the frontend decides whether user auth is
enabled.

Two supported modes are required:

- **security enabled**
  - initialize Keycloak
  - obtain bearer token
  - then load control-plane bootstrap
- **security disabled**
  - no Keycloak redirect/login
  - keep frontend booting in local/dev mode
  - then load control-plane bootstrap directly

For the no-security mode, the app must behave like a first-class supported
developer mode, not as a degraded fallback.

---

### 1.4 Stage 2 - Control-plane Application Bootstrap

After auth decision/login, the frontend loads exactly one application bootstrap
payload from control-plane:

- `GET /control-plane/v1/frontend/bootstrap`

This payload is the single source of truth for:

- current user
- active team
- available teams
- GCU version gating when the product enables it
- frontend feature flags
- frontend UI settings
- flattened permissions

The app shell must derive its initial state from this payload, not from a mix
of additional legacy endpoints.

---

### 1.5 Stage 3 - Domain Data After Bootstrap

Only after bootstrap is established should the frontend query domain APIs:

- control-plane for managed agent templates and instances
- control-plane for execution preparation
- knowledge-flow for content/resource pages
- runtime for execution and runtime history via prepared URLs

The bootstrap payload must not be stretched into a transport/routing registry.

---

### 1.6 Mandatory Bootstrap Invariants

- The frontend must boot without calling `/agentic/v1/config/frontend_settings`.
- The frontend must boot without calling `/agentic/v1/config/permissions`.
- The frontend shell must not require `/control-plane/v1/user` to determine the
  personal team.
- The frontend shell must not require `/control-plane/v1/teams` to determine the
  initial active team.
- The frontend must never derive runtime routing from bootstrap.
- The frontend must never require a runtime pod just to render the shell.

---

## 2 Phase FRONT-01 - Bootstrap Convergence

### 2.1 Goal

Make the frontend shell boot from one coherent model before reworking
individual pages.

---

### 2.2 Problems Visible Today

Current frontend startup is still mixed:

- `frontend/src/common/config.tsx` still fetches legacy frontend settings and
  permissions from `agentic-backend`
- `frontend/src/hooks/useFrontendProperties.ts` still reads display properties
  from `agentic-backend`
- `frontend/src/security/usePermissions.ts` still depends on the legacy
  permissions fetch
- several pages and navigation components still use
  `/control-plane/v1/user` and `/control-plane/v1/teams` as implicit bootstrap
  sources

This makes the app partially migrated but not converged.

---

### 2.3 Tasks

- [x] Freeze the intended content of `/config.json` for pre-auth bootstrap only
- [x] Freeze `GET /control-plane/v1/frontend/bootstrap` as the only application
  bootstrap payload
- [x] Introduce one frontend bootstrap state/container used by router, sidebar,
  permissions, and team context
- [x] Remove legacy shell dependency on `/agentic/v1/config/frontend_settings`
- [x] Remove legacy shell dependency on `/agentic/v1/config/permissions`
- [x] Stop using `/control-plane/v1/user` as the primary source of the personal
  team in the app shell
- [x] Stop using `/control-plane/v1/teams` as the primary source of the initial
  active-team selection
- [ ] Decide which bootstrap failures are fatal and which should render a typed
  recovery screen

---

### 2.4 Validation

- [x] hard reload boots with only `/config.json` plus control-plane bootstrap
- [x] no shell-critical bootstrap request hits `agentic-backend`
- [x] sidebar/header/team context come from one bootstrap state only
- [x] permissions checks use bootstrap permissions only

---

## 3 Phase FRONT-02 - No-Security Personal-Only Baseline

### 3.1 Goal

Make the frontend work cleanly when security is disabled and the only team is
the user's personal team.

This is the first required frontend operating mode.

---

### 3.2 Product Assumption For This Phase

When user security is disabled:

- no collaborative teams are assumed
- the only valid team is `personal`
- the default active team is `personal`
- collaborative team management flows are out of scope

If some collaborative/team UI remains visible temporarily, it must be treated
as explicitly deferred work, not as a partially supported default path.

---

### 3.3 Required Behavior

In no-security mode the frontend must:

- boot without Keycloak login
- load bootstrap successfully from control-plane
- receive a valid current user and personal team context
- render the shell with `personal` as active team
- navigate directly to personal-team routes
- use bootstrap permissions rather than legacy permission fetches
- tolerate `available_teams` containing only the personal team

In this mode the frontend must not assume:

- collaborative team membership
- team switching beyond the personal team
- team settings requiring owner/admin permissions
- Keycloak-backed user details endpoints for core shell rendering

---

### 3.4 First Rework Tasks

- [x] Ensure no-security startup never redirects to Keycloak
- [x] Ensure control-plane bootstrap is callable and useful with security
  disabled
- [x] Ensure bootstrap can represent exactly one personal team cleanly
- [x] Rework sidebar team selection to accept `available_teams = [personal]`
- [x] Rework active-team routing so `/team/personal/...` is the supported
  baseline route
- [x] Rework page guards so they rely on bootstrap permissions and do not wait
  on legacy permission fetches
- [x] Hide or explicitly disable collaborative-team UI paths that are not part
  of the personal-only baseline
- [x] Decide whether marketplace/team discovery stays visible in this phase or
  is intentionally hidden until collaborative teams are supported

---

### 3.5 Validation

- [x] with control-plane security disabled, frontend reaches the main shell
  without login
- [ ] active team is `personal` after refresh
- [x] no boot-time request to `/agentic/*` is required
- [x] no boot-time request to collaborative team endpoints is required
- [ ] personal-team navigation works with `available_teams` size 1

---

## 4 Backend Readiness Gates

### 4.1 Goal

Avoid frontend churn caused by unclear backend ownership.

Before Phase 5 implementation starts in earnest, the backend/product contract
must be explicit enough that the frontend does not have to guess where personal
team identity, permissions, and shell configuration come from.

---

### 4.2 Personal Team Robustness Rule

The default `personal` team is an acceptable and recommended baseline for the
first frontend slice, but it must be treated as an explicit control-plane
contract.

That means:

- `personal` must be available from control-plane bootstrap even when no
  collaborative teams exist
- the frontend shell must treat bootstrap as the source of truth for the
  personal team
- the frontend must not need a separate temporary `/user` endpoint just to learn
  the personal team identity
- the frontend must not infer personal-team behavior from the absence of
  collaborative teams

The synthetic personal team is fine.
The fragile part is duplicating its definition across multiple endpoints.

This contract should also be the seed for future reserved/system teams.
If the platform later introduces an `admin` workspace, it should reuse the same
mechanism rather than creating a second wave of special-case endpoint logic.

---

### 4.3 Backend Decisions That Must Be Frozen

- [ ] `GET /control-plane/v1/frontend/bootstrap` is the application bootstrap
  source of truth for:
  - current user
  - active team
  - available teams
  - permissions
  - frontend UI settings
- [ ] `/control-plane/v1/user` is either:
  - explicitly deprecated for shell bootstrap, or
  - redefined as a non-bootstrap helper endpoint only
- [x] `/control-plane/v1/teams` is explicitly defined as either:
  - collaborative teams only, or
  - all selectable teams including `personal`
- [ ] Freeze a generic reserved/system-team contract in control-plane, starting
  with `personal` and extensible to future reserved teams such as `admin`,
  while preserving the same `Team` / `TeamWithPermissions` API shapes
- [ ] the frontend shell will not depend on `/teams` to discover `personal`
- [ ] no-security mode remains a first-class supported control-plane mode, not
  an accidental side effect of disabled Keycloak

---

### 4.4 Backend Hardening Tasks Recommended Before Or During Phase FRONT-01

- [x] Remove duplicated personal-team shaping between bootstrap and temporary
  user-details endpoints
- [x] Centralize personal-team resolution so bootstrap, `/teams`,
  `/teams/{team_id}`, and temporary helper endpoints share the same backend
  source of truth
- [ ] Extend control-plane bootstrap/ui settings until the frontend no longer
  needs legacy `agentic` frontend settings for shell branding and labels
- [ ] Ensure bootstrap permissions are sufficient for frontend route guards
- [ ] Add one explicit offline test for:
  - security disabled
  - bootstrap returns `active_team = personal`
  - `available_teams` contains only `personal`
  - frontend-critical shell data is still present
- [x] Add one explicit offline test for the chosen `/teams` contract so the
  frontend does not depend on undocumented behavior
- [ ] Document whether team settings/actions are valid for the synthetic
  personal team or intentionally unavailable in the first slice

---

### 4.5 Validation

- [ ] the frontend can be implemented against bootstrap without consulting
  temporary user-details semantics
- [ ] the personal-team baseline is documented as product behavior, not only as
  test setup
- [x] backend tests cover no-security bootstrap with `personal` as the only
  team
- [ ] backend/UI settings are sufficient to remove shell-critical dependency on
  legacy `agentic` config endpoints

---

## 5 Phase FRONT-03 - Managed Agent Surface

### 5.1 Goal

Make team agent selection and managed execution use the new product model
consistently.

---

### 5.2 Managed Agent Selection Model

For the migrated frontend, the selectable product object is a **managed agent
instance**, not a raw runtime/template identifier.

The intended flow is:

1. control-plane exposes enrollable templates for one team context
2. a team, including the `personal` team, enrolls one template as a managed
   agent instance
3. the frontend lists and selects that managed instance by
   `agent_instance_id`
4. the frontend asks control-plane to prepare execution for that selected
   instance
5. control-plane resolves runtime binding and returns `ExecutionPreparation`
6. the frontend calls runtime using the prepared URLs and grant only

Frontend implication:

- the user selects "my team agent" or "my personal agent"
- the frontend does not execute a raw `agent_id`
- the frontend does not resolve runtime topology
- `agent_instance_id` is the stable route and execution identity

This model is considered sound for Phase 5 because it matches the target
architecture:

- team-scoped execution
- control-plane-owned product identity
- runtime-owned execution only
- no frontend dependency on Kubernetes or pod wiring

### 5.2.1 Managed Agent Availability Model

The frontend must present managed-agent availability using the same lifecycle
language as the control-plane product model.

Terms:

- `template` = live-discovered capability available for enrollment
- `managed agent instance` = enrolled team-scoped object stored in control-plane
- `runtime unavailable` = the managed instance still exists, but new execution
  cannot currently proceed

Required behavior:

1. if template discovery fails for one runtime, the page may show fewer
   templates for enrollment without implying that existing enrolled instances
   were deleted
2. if an enrolled managed instance still exists in control-plane but execution
   cannot proceed, the UI must keep showing the instance and present it as
   unavailable rather than silently hiding it
3. delete / unbind must remain available for managers even when execution is
   unavailable, because unbinding is handled by control-plane and does not
   require the runtime pod to be healthy
4. the UI must not force the user to infer lifecycle state from a generic chat
   failure

Current implementation note:

- the page already separates template discovery from managed instance listing
- the page does not yet surface a first-class "runtime unavailable" state for an
  enrolled instance
- the delete path already goes through control-plane and should remain usable

---

### 5.3 Status Note (Phase FRONT-03 complete)

The agent selection surface is now fully migrated:

- managed chat uses `agent_instance_id` via `ManagedChatPage`
- `TeamAgentsPage` reads managed instances from control-plane (no more `agentic-backend`)
- `agent_instance_id` is the route and execution identity throughout the managed path

Legacy authoring capabilities resolved: the `AgentFormModal` now reflects the control-plane model
(template browser → enrollment; edit mode pre-fills from instance). V1/V2 versioning, workspace files,
and raw MCP server selection are explicitly out-of-scope. Per `docs/rfc/AGENT-INSTANCE-FORM-RFC.md`.

---

### 5.4 Tasks

- [x] Replace team agent listing with control-plane managed instances
- [x] Replace enrollable catalog listing with control-plane agent templates
- [x] Use `agent_instance_id` as the route and selection identity everywhere in
  the managed path
- [x] Decide which legacy authoring/editing capabilities remain supported during
  migration and which are intentionally deferred — resolved: `AgentFormModal` refactored per RFC; legacy capabilities (V1/V2, workspace files, raw MCP selection) explicitly out of scope
- [x] Keep the page usable when no runtime templates are currently reachable
- [x] Define the empty/loading/error states for:
  - no enrolled managed instances
  - no reachable templates
  - runtime unavailable but shell healthy
- [ ] Make the managed instance list explicitly distinguish:
  - enrolled but currently unavailable for execution
  - removed/unbound
- [ ] Keep delete / unbind affordances available when one enrolled instance is
  currently unavailable because its runtime pod is down
- [ ] Add one user-facing unavailable state/message that explains:
  - the team still owns the instance
  - new execution is temporarily unavailable
  - delete remains possible

---

### 5.5 Validation

- [x] selecting an agent from the team page always yields one
  `agent_instance_id`
- [x] no managed-agent page depends on legacy raw agent identifiers
- [x] the page still renders a useful state if runtime template discovery fails

---

## 6 Phase FRONT-04 - Session And Chat Shell Convergence

### 6.1 Goal

Make session list, chat entry, and managed runtime history follow the same
ownership model as the execution path.

Source of truth for session identity: `docs/swift/design/SESSION-IDENTITY-CONTRACT.md` *(planned — file not yet written)*

---

### 6.2 Ownership Decision (Resolved)

**This decision is frozen. Do not reopen it.**

| Concern | Owner | Where stored |
|---|---|---|
| Message content (turns, tool calls, sources) | `fred-runtime` | `session_history` table on the pod |
| Session metadata (title, created_at, status) | `control-plane-backend` | control-plane DB |
| Checkpoint state (HITL resume, graph continuity) | `fred-runtime` checkpointer | LangGraph tables on the pod |

Consequences for the frontend:

- The frontend reads message history from runtime using the `messages_url_template`
  from `ExecutionPreparation` — never from control-plane.
- The frontend reads session list and metadata from control-plane — never from
  the runtime `GET /agents/sessions` endpoint (that endpoint is for admin/CLI).
- The sidebar session list requires control-plane session metadata to exist. Until
  it exists, the sidebar intentionally shows no session list. This is the correct
  default, not a bug.
- `session_id` is generated by the frontend before the first turn and passed to
  both the runtime (for execution) and control-plane (for metadata creation).
  The term `thread_id` must never appear in any frontend code or UI label.

### 6.2.1 Managed Session Lifecycle

The managed session flow is intentionally split between execution/history and
management metadata.

Lifecycle:

1. frontend generates one `session_id`
2. frontend calls `POST /teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution`
3. frontend registers session metadata in control-plane for sidebar ownership
4. frontend sends the managed turn directly to runtime
5. runtime persists message content in `session_history`
6. runtime serves later message-history reads for that `session_id`
7. control-plane serves session list / title / status only

Non-goals:

- control-plane does not serve full message history
- control-plane does not proxy runtime history for the chat page
- the sidebar must not query runtime history endpoints just to render the
  management shell

---

### 6.3 Current Mismatch

The managed execution hook is new, but the surrounding chat shell still depends
on legacy session APIs:

- the default team sidebar no longer calls the legacy session API, but session
  metadata is intentionally absent until the control-plane session slice exists
- the older chat surfaces still read legacy raw agents and session metadata
  from `agentic-backend`
- chat/session route assumptions still come from older chat surfaces

This creates a hybrid UX even when execution itself is migrated.

---

### 6.4 Tasks

- [x] Freeze which backend owns sidebar session metadata (see §6.2 above)
- [x] Remove default sidebar/session dependency on legacy agentic session APIs
- [x] Decide whether session metadata is moved to control-plane or omitted:
      **Decision: moved to control-plane — implemented in Phase FRONT-04**
- [x] Ensure managed chat history loading uses prepared runtime `messages_url_template` only
      — implemented in `ManagedChatPage`: calls `prepare-execution` on mount when `?session=<id>`
      is present, expands `{session_id}` in the template, fetches history with bearer token
- [x] Define one supported managed chat entry flow from team page to chat page
- [x] Implement control-plane session metadata creation:
      `POST /teams/{team_id}/sessions` with `{ session_id, agent_instance_id }` —
      called from `ManagedChatPage.handleSend` after generating the session_id (fire-and-forget).
      Backend: `session_metadata` table + `SessionMetadataStore` + `SessionMetadataRow` ORM +
      Alembic migration `f1a2b3c4d5e6`. Pydantic: `SessionListItem`, `CreateSessionRequest`.
- [x] Implement `GET /teams/{team_id}/sessions` for sidebar session list —
      returns sessions ordered by `updated_at DESC`, limit 50
- [x] Wire sidebar to control-plane session list —
      `ChatList.tsx` now fetches from `useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery`
      with 30s polling; renders links to `/team/:teamId/managed-chat/:agentInstanceId?session=<uuid>`
- [x] Frontend generates `session_id` (UUID) before first turn and passes it in
      `RuntimeExecuteRequest.session_id` — `ManagedChatPage` generates UUID upfront in `handleSend`
      if sessionId is null, persists it in URL query params (`?session=<uuid>`)
- [x] Ensure `session_id` is never labeled `thread_id` anywhere in frontend code or UI
- [ ] Keep sidebar freshness metadata-oriented:
      if the session list should reorder by recent activity, define and implement
      a control-plane metadata refresh path that does not require control-plane
      to read or serve runtime message history

---

### 6.5 Validation

- [x] no managed chat screen requires legacy websocket/session APIs
- [x] session/history behavior follows the ownership split in §6.2
- [x] sidebar shows sessions from control-plane, empty state when none exist
- [x] message history loads from the runtime `messages_url_template` only
- [x] `session_id` is consistently used as the conversation identifier in all
      frontend state, route params, and API calls

---

## 7 Phase FRONT-05 - Agentic-Backend Removal From Frontend

### 7.1 Goal

Remove all frontend imports from `agenticOpenApi.ts` and the two companion agentic
API slices (`agenticInspectionApi.ts`, `agenticSourceApi.ts`).

**Context:** `agentic-backend` has been removed from the active monorepo (archived to
`ignored/fred/agentic-backend`). The backend migration is complete. What remains is
purely a frontend cleanup: ~30 files still import types from `agenticOpenApi.ts`, a
file that was generated from the now-removed service's schema.

The types needed by the rework/managed path already exist in `runtimeOpenApi.ts`
(generated from `apps/fred-agents`). The old `components/` and `pages/` tree
(legacy chat, MCP hub, monitoring) is a lower priority — those surfaces will be
formally deprecated when the rework path is complete.

---

### 7.2 Files Still Importing From `agenticOpenApi`

**Rework path (highest priority — migrate to `runtimeOpenApi`):**
- `hooks/useChatSse.ts` — `AwaitingHumanEvent`, `ChatMessage` (RuntimeContext done)
- `rework/components/pages/ManagedChatPage/ManagedChatPage.tsx` — `AwaitingHumanEvent`, `ChatMessage`, `VectorSearchHit`
- `rework/components/pages/ManagedChatPage/MessageBubble/MessageBubble.tsx` — `ChatMessage`
- `rework/components/pages/ManagedChatPage/useSessionHistory.ts` — `ChatMessage`
- `rework/components/shared/molecules/ThoughtTrace/ThoughtTrace.tsx`
- `rework/components/shared/molecules/SourcesPanel/SourcesPanel.tsx`
- `rework/components/shared/molecules/SourcesPanel/SourceCard/SourceCard.tsx`
- `rework/components/shared/molecules/SourcesPanel/SourceDetailModal/SourceDetailModal.tsx`
- `rework/components/shared/molecules/HitlPrompt/HitlPrompt.tsx`
- `rework/components/shared/organisms/AssistantTurn/AssistantTurn.tsx`
- `rework/utils/traceUtils.ts`

**Shared hooks (used by both rework and legacy):**
- ~~`hooks/useChatSse.ts`~~ — **deleted (2026-05-21); migrated to `rework/core/hooks/useChatSse.ts`**
- `hooks/useAgentSelector.ts` — `ChatMessage`
- ~~`hooks/useGroupMessages.ts`~~ — **deleted (2026-05-21)**
- `common/agent.ts` — `Agent`

**Legacy surfaces (lower priority — deprecate with the surface):**
- ~~`pages/Chat.tsx`~~ — **deleted (2026-05-21)**
- ~~`hooks/useChatSocket.ts`~~ — **deleted (2026-05-21)**
- `hooks/useAgentUpdater.ts` — `Agent2`, live API call
- ~~`components/chatbot/`~~ — **deleted (2026-05-21)** (~40 files: `ChatBot`, `ChatBotUtils`, `citations`, `HitlInlineCard`, `MessageRuntimeContextHeader`, `MessageRuntimeContextPopover`, `MessagesArea`, `ReasoningStepBadge`, `ReasoningStepsAccordion`, `SourceDetailsDialog`, `Sources`, `SourceTile`, `tokenUsage`, `TraceDetailDialog`, etc.)
- ~~`features/libraries/ChatDocumentLibrariesWidget`, `ChatDocumentLibrariesSelectionCard`~~ — **deleted (2026-05-21)**
- `components/agentHub/` — `AgentToolsSelection`, `TuningForm`, `toolParamsRegistry`
- `components/mcpHub/` — `McpServerCard`, `McpServerForm`
- `components/monitoring/` — `KpiDashboard`, `TokenUsageChart`, `LogConsoleTile`

---

### 7.3 Tasks

- [ ] Migrate rework path files (11 files listed in §7.2) to `runtimeOpenApi` types
- [ ] Migrate remaining shared hooks (`useAgentSelector.ts`, `common/agent.ts`) to `runtimeOpenApi`
- [x] Delete legacy `pages/Chat.tsx`, `components/chatbot/`, `hooks/useChatSocket.ts`, `hooks/useGroupMessages.ts`, `features/libraries/ChatDocument*` (done 2026-05-21)
- [x] Migrate `hooks/useChatSse.ts` to `rework/core/hooks/useChatSse.ts` and delete old file (done 2026-05-21)
- [x] Migrate `UserInputSearchPolicy` → `rework/…/SearchPolicySelect` and remove old component (done 2026-05-21)
- [ ] Delete `agenticOpenApi.ts` once all imports are cleared
- [ ] Delete `agenticInspectionApi.ts` and `agenticSourceApi.ts` once consumers are removed

---

## 8 Explicit Non-Goals For The First Frontend Slice

Do not treat the following as Phase 5 starting requirements:

- restoring every legacy team collaboration flow immediately
- perfecting security-enabled UX before no-security mode is stable
- preserving all legacy agent authoring behavior if the new managed surface is
  not ready for it
- page-by-page bug fixing without first converging bootstrap and identity

---

## 9 Current Frontend Gaps To Use As Input

These are concrete migration signals still visible in the codebase (updated after Phase FRONT-04):

- `frontend/src/common/config.tsx` now only handles the tiny pre-auth
  `/config.json` bootstrap, but bootstrap failure handling is still not
  converged into one typed recovery path (open FRONT-01 task)
- ~~`frontend/src/pages/Chat.tsx` still lists legacy raw agents from `agentic-backend`~~ **Deleted (2026-05-21)** — legacy chat path fully removed.
- ~~`frontend/src/components/chatbot/ChatBot.tsx` still reads legacy session metadata from `agentic-backend`~~ **Deleted (2026-05-21)** — entire `components/chatbot/` tree removed.
- ~~the managed sidebar uses an intentional placeholder for session metadata~~
  **done**: `ChatList.tsx` now fetches from `GET /teams/{team_id}/sessions` (Phase FRONT-04)
- the personal-only shell still leaves some collaborative/discovery UI decisions
  open, especially marketplace visibility
- backend hardening for the synthetic `personal` team remains open and should be
  closed before treating the no-security baseline as fully robust
- FRONT-02 validation: `active team = personal` after hard refresh + navigation with
  `available_teams` size 1 — two smoke-test items still unconfirmed

These gaps should inform the sequencing, not trigger ad hoc fixes.

---

## 10 Acceptance Checklist For Phase 5 Start

Before detailed frontend coding resumes, the target should be clear enough that
we can answer "yes" to all of the following:

- [x] the frontend bootstrap sequence is frozen and documented
- [x] the no-security/personal-only baseline is explicitly defined
- [x] the backend readiness gates for bootstrap and personal-team ownership are
  explicit
- [x] the shell no longer depends on `agentic-backend` to start
- [x] the managed-agent selection surface target is explicit
- [x] the session/sidebar ownership decision is explicit
- [x] developers know which services must be started locally
- [x] remaining frontend work is organized by migration slice, not by random
  visible defects

---

## 11 Related Backlogs

- [`CHAT-UI-BACKLOG.md`](./CHAT-UI-BACKLOG.md) — Progressive build-out of the
  managed chat interface quality: component architecture, rendering, markdown,
  source citations, reasoning trace. Parallel to Phase 5 migration work.

---

## 12 Phase 5 Progress

| Sub-phase | Status | Remaining |
|---|---|---|
| FRONT-01 – Bootstrap convergence | ✓ Complete | Bootstrap failure recovery screen (minor, deferred) |
| FRONT-02 – No-security personal-only baseline | ✓ Substantially complete | 2 smoke-test validation items |
| Backend readiness gates | Partial | Bootstrap permissions for route guards; personal-team doc; offline test |
| FRONT-03 – Managed agent surface | ✓ Complete | Legacy authoring decision (intentionally deferred) |
| FRONT-04 – Session and chat shell convergence | ✓ Complete | PATCH/DELETE session endpoints (deferred to Phase 6) |
| FRONT-05 – Agentic-backend removal from frontend | 🔄 Partial (2026-05-21) | Legacy chatbot tree deleted (`components/chatbot/`, `pages/Chat.tsx`, `hooks/useChatSocket`, `hooks/useGroupMessages`, `features/libraries/Chat*`). `useChatSse` migrated to rework. `SearchPolicySelect` extracted to rework. Old chat routes removed from router. Remaining: rework path files (11) + shared hooks still importing `agenticOpenApi`; `agenticOpenApi.ts` deletion pending. |

Security-enabled hardening should come after the no-security baseline is clean.
