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

## 2 Phase 5A - Bootstrap Convergence

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

## 3 Phase 5B - No-Security Personal-Only Baseline

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

### 4.4 Backend Hardening Tasks Recommended Before Or During Phase 5A

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

## 5 Phase 5C - Managed Agent Surface

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

---

### 5.3 Current Mismatch

Managed chat already prepares execution through control-plane, but the agent
selection surface is still split:

- managed chat uses `agent_instance_id`
- the team agent page still reads legacy agent lists from `agentic-backend`
- legacy authoring/update flows still shape the page model

This keeps the entry point to Phase 4 transport work inconsistent.

---

### 5.4 Tasks

- [x] Replace team agent listing with control-plane managed instances
- [x] Replace enrollable catalog listing with control-plane agent templates
- [x] Use `agent_instance_id` as the route and selection identity everywhere in
  the managed path
- [ ] Decide which legacy authoring/editing capabilities remain supported during
  migration and which are intentionally deferred
- [x] Keep the page usable when no runtime templates are currently reachable
- [x] Define the empty/loading/error states for:
  - no enrolled managed instances
  - no reachable templates
  - runtime unavailable but shell healthy

---

### 5.5 Validation

- [x] selecting an agent from the team page always yields one
  `agent_instance_id`
- [x] no managed-agent page depends on legacy raw agent identifiers
- [x] the page still renders a useful state if runtime template discovery fails

---

## 6 Phase 5D - Session And Chat Shell Convergence

### 6.1 Goal

Make session list, chat entry, and managed runtime history follow the same
ownership model as the execution path.

Source of truth for session identity: [`docs/design/SESSION-IDENTITY-CONTRACT.md`](../docs/design/SESSION-IDENTITY-CONTRACT.md)

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
      **Decision: omitted intentionally until control-plane slice exists**
- [x] Ensure managed chat history loading uses prepared runtime `messages_url_template` only
      — implemented in `ManagedChatPage`: calls `prepare-execution` on mount when `?session=<id>`
      is present, expands `{session_id}` in the template, fetches history with bearer token
- [x] Define one supported managed chat entry flow from team page to chat page
- [ ] Implement control-plane session metadata creation at `prepare-execution` time:
      `POST /control-plane/v1/sessions` with `{ session_id, team_id, agent_instance_id }`
- [ ] Implement `GET /control-plane/v1/sessions` for sidebar session list
- [ ] Wire sidebar to control-plane session list once the endpoint exists
- [x] Frontend generates `session_id` (UUID) before first turn and passes it in
      `RuntimeExecuteRequest.session_id` — `ManagedChatPage` generates UUID upfront in `handleSend`
      if sessionId is null, persists it in URL query params (`?session=<uuid>`)
- [ ] Ensure `session_id` is never labeled `thread_id` anywhere in frontend code or UI

---

### 6.5 Validation

- [ ] no managed chat screen requires legacy websocket/session APIs
- [ ] session/history behavior follows the ownership split in §6.2
- [ ] sidebar shows an intentional empty state when session metadata does not
      exist yet — not a partial legacy fallback
- [ ] message history loads from the runtime `messages_url_template` only
- [ ] `session_id` is consistently used as the conversation identifier in all
      frontend state, route params, and API calls

---

## 7 Phase 5E - Knowledge-Flow And Shared Shell Alignment

### 7.1 Goal

Keep non-chat pages compatible with the same active-team/bootstrap model.

---

### 7.2 Tasks

- [x] Review knowledge/resource pages for dependence on `/control-plane/v1/user`
  as bootstrap
- [ ] Ensure personal-team-only mode does not break knowledge-flow navigation
- [x] Ensure shared UI properties come from the converged bootstrap path, not
  legacy agentic config endpoints

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

These are concrete migration signals already visible in the codebase:

- `frontend/src/common/config.tsx` now only handles the tiny pre-auth
  `/config.json` bootstrap, but bootstrap failure handling is still not
  converged into one typed recovery path
- `frontend/src/pages/Chat.tsx` still lists legacy raw agents from
  `agentic-backend`
- `frontend/src/components/chatbot/ChatBot.tsx` still reads legacy session
  metadata from `agentic-backend`
- the managed sidebar currently uses an intentional placeholder for session
  metadata until the control-plane session slice is implemented
- the personal-only shell still leaves some collaborative/discovery UI decisions
  open, especially marketplace visibility
- backend hardening for the synthetic `personal` team remains open and should be
  closed before treating the no-security baseline as fully robust

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

## 11 Proposed Phase 5 Order

1. **Phase 5A - Bootstrap convergence**
2. **Phase 5B - No-security personal-only baseline**
3. **Backend readiness gates closed enough to remove ambiguity**
4. **Phase 5C - Managed agent surface**
5. **Phase 5D - Session and chat shell convergence**
6. **Phase 5E - Knowledge-flow and shared shell alignment**

Security-enabled hardening should come after the no-security baseline is clean.
