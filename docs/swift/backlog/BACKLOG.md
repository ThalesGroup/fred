# Runtime Migration Backlog

## 0 Overview

### 0.1 Goal

Replace the frontend-facing role of `agentic-backend` with a **clear, secure, and strongly-typed execution architecture** based on:

- `fred-runtime` for **team-scoped agent execution**, SSE streaming, HITL, checkpoints, and runtime history
- `control-plane-backend` as the **single authority for product, tenancy, and authorization**, including teams, permissions, and managed agents
- the existing `frontend`, adapted to **HTTP SSE (`fetch`) instead of WebSocket**, and operating only on **control-plane-approved execution contexts**

In this model:

- **All agent execution is team-scoped** — every request is executed on behalf of a user within a team
- **Agents are executed via managed `agent_instance_id`**, not raw agent names
- **Runtime pods are execution surfaces only**, not tenancy or authorization authorities
- **Control-plane is the only component aware of available agentic pods and agent enrollment**

At the end of this migration, `agentic-backend` is fully removed from the frontend runtime path and is no longer required for:

- frontend chat transport
- frontend chat type generation
- session sidebar data
- agent catalog / team agent management
- MCP server management
- feedback submission
- frontend config / permissions

---

### 0.2 Core Decision

For the Fred frontend, use the **Fred-native SSE runtime API** as the primary execution protocol:

- `POST /agents/execute/stream`
- `POST /agents/execute`
- `GET /agents/sessions/{session_id}/messages`

These endpoints operate on **team-scoped, authorized execution requests**, including:

- `agent_instance_id` (managed execution target)
- `session_id` (continuity)
- optional `checkpoint_id` (resume)
- a **control-plane-issued execution authorization context**

Keep OpenAI-compatible endpoints in `fred-runtime` as a **secondary interface** for external tools:

- `GET /v1/models`
- `POST /v1/chat/completions`

#### 0.2.1 Why

- the Fred-native runtime protocol natively supports:
  - `RuntimeEvent`
  - `HumanInputRequest` (HITL)
  - `ui_parts` (structured UI rendering)
  - checkpoint and resume semantics
  - explicit execution context

- the OpenAI compatibility layer:
  - is useful for interoperability
  - but does not yet express team-scoped execution, authorization, or HITL semantics cleanly enough for the Fred frontend

---

### 0.3 Target Architecture

#### 0.3.1 `fred-runtime`

Owns **execution only**:

- agent execution engine
- SSE streaming
- HITL pause/resume
- checkpoints
- runtime history
- runtime event contracts
- frontend-facing runtime types (via OpenAPI)

Constraints:

- MUST validate execution authorization (team, user, agent instance)
- MUST NOT own:
  - team definitions
  - permissions
  - agent enrollment
  - pod discovery

---

#### 0.3.2 `control-plane-backend`

Owns **product, tenancy, and authorization**:

- frontend configuration
- permissions and access control
- team management (personal and collaborative)
- agent template discovery and aggregation
- managed agent instance lifecycle (`agent_instance_id`)
- mapping of agent instances to runtime pods
- session metadata and preferences
- attachment metadata
- feedback
- MCP server administration

Responsibilities:

- is the **only component aware of agentic pods**
- resolves execution targets (which pod serves which agent)
- issues **execution authorization contexts (grants)** used by the frontend to call runtime pods securely

---

#### 0.3.3 `frontend`

Uses:

- generated types from `fred-runtime` for **runtime execution contracts**
- generated types from `control-plane-backend` for **product/session/admin APIs**
- `fetch()` + SSE parsing instead of WebSocket

Behavior:

- selects a **team-scoped managed agent instance**
- obtains a **control-plane-approved execution context**
- calls runtime SSE endpoints **directly but securely**
- renders:
  - streaming responses
  - HITL interactions
  - `ui_parts` (links, maps, etc.)

---

### 0.4 Migration Rules

1. **Do not recreate `agentic-backend` inside `fred-runtime`.**  
   Runtime must remain focused on execution only.

2. **Enforce team-scoped execution everywhere.**  
   Every execution must be attributable to:
   - `user_id`
   - `team_id`
   - `agent_instance_id`

3. **Control-plane is the sole authority for:**
   - agent enrollment
   - runtime pod registry
   - permission validation
   - execution authorization

4. **Runtime pods must validate, not decide.**  
   They execute only authorized requests and reject invalid ones.

5. **Keep one source of truth for runtime contracts:**  
   `libs/fred-sdk` and `libs/fred-runtime`

6. **Keep one source of truth for product/admin/session APIs:**  
   `control-plane-backend`

7. **Prefer small, incremental PRs that keep the system runnable.**

8. **Cut frontend codegen away from `agentic-backend` early.**

---

### 0.5 Phase 0 - Lock The Direction

#### 5.1 Deliverable

A short architectural note in `docs/rfc/AGENTIC-POD-RFC.md` confirming:

- Fred frontend uses **native runtime SSE as the primary protocol**
- **All execution is team-scoped and managed**
- `agent_instance_id` is the preferred execution target
- **control-plane owns all product, tenancy, and authorization concerns**
- runtime pods are **execution-only and stateless with respect to teams**
- OpenAI compatibility remains secondary

IMPORTANT: Prefer Kubernetes-native primitives over custom Fred code whenever the concern is routing, discovery, exposure, balancing, or topology. Only keep security, authorization, and business semantics in Fred code.

#### 5.2 Tasks

- [x] Add a "Migration direction" section to the RFC
- [x] Explicitly state that `agentic-backend` is no longer a convergence layer
- [x] Explicitly define the split between:
  - runtime execution state (fred-runtime)
  - product/session/authorization metadata (control-plane)
- [x] Add a clear statement:
  - "All agent execution is performed within a team context"
- [x] Add a clear statement:
  - "Control-plane is the only authority for agentic pod discovery and agent enrollment"

#### 5.3 Validation

- [x] RFC reviewed locally and aligned with architecture goals

---

## 1 Phase 1 — Runtime Execution Contract Freeze

### 1.1 Goal

Establish **fred-sdk** and **fred-runtime** as the single, authoritative source of truth for **secure, team-scoped execution contracts** between the frontend and agentic runtime pods.

This phase freezes not only chat/runtime payloads, but also:

- execution identity (`user_id`, `team_id`)
- managed agent targeting (`agent_instance_id`)
- authorization context
- session / checkpoint continuity
- traceability metadata
- runtime event contracts

This phase must also enforce a key architectural constraint:

> **Fred code must never reimplement concerns that are better handled by native Kubernetes capabilities or standard platform components.**

In particular, Fred code must **not** grow custom logic for:

- runtime pod discovery
- dynamic routing across pods
- service-to-pod resolution
- topology-aware failover logic
- in-app load balancing
- custom execution mesh behavior

These concerns must be handled by:

- Kubernetes `Service`
- Ingress / Gateway
- DNS / service naming
- namespace isolation
- deployment configuration
- GitOps / Argo CD / platform automation

Fred application code should remain responsible only for:

- endpoint protection
- RBAC checks (Keycloak)
- REBAC checks (OpenFGA)
- team-scoped managed agent authorization
- issuance / validation of execution context
- runtime execution contracts
- history / checkpoint access validation

---

### 1.2 Core Principles

- **All execution is team-scoped**
  - Every execution MUST occur on behalf of a user within a team
  - `team_id` is mandatory and explicit

- **Managed execution is the default**
  - `agent_instance_id` is the primary execution target
  - Raw agent names are secondary and reserved for internal/dev compatibility only

- **Control-plane is the authority**
  - Defines teams, permissions, and managed agent enrollment
  - Knows which runtime endpoints exist
  - Resolves which runtime endpoint serves a managed agent instance
  - Issues execution authorization

- **Runtime pods are execution-only**
  - They execute requests
  - They validate authorization
  - They consume checkpoint/history state
  - They do NOT own tenant membership, permissions, or routing discovery

- **Frontend → Runtime is direct but secured**
  - Frontend may call runtime endpoints directly
  - Only with a control-plane-approved execution context
  - Runtime must reject invalid, expired, or inconsistent requests

- **Kubernetes handles routing**
  - Fred code must not implement platform routing behavior already provided by Kubernetes
  - Runtime exposure and stable URLs should come from K8-native configuration

---

### 1.3 Deliverable

A complete, typed, frontend-facing runtime execution contract including:

- execution identity (`user_id`, `team_id`)
- managed execution target (`agent_instance_id`)
- authorization envelope (`ExecutionGrant`)
- session continuity (`session_id`)
- checkpoint resume (`checkpoint_id`)
- runtime event streaming models
- typed UI rendering parts (`ui_parts`)
- traceability metadata

Exposed via **fred-runtime OpenAPI**, without reliance on `agentic-backend`.

---

### 1.4 Scope

#### 1.4.1 In Scope

- Runtime execution contract definition in `fred-sdk`
- OpenAPI exposure via `fred-runtime`
- Team-scoped authorization + identity modeling
- Session + checkpoint access semantics
- Runtime event and UI part typing
- Minimal OpenAI compatibility alignment
- Explicit architectural rule that Fred code must not implement K8-native routing/discovery behavior

#### 1.4.2 Out of Scope

- Frontend SSE transport migration
- WebSocket removal
- Control-plane API migration
- Session/sidebar/admin migration
- Full OpenAI protocol redesign
- Custom runtime routing/discovery logic inside Fred code

---

### 1.5 Tasks

#### 1.5.1 A. Freeze Execution Identity and Authorization Models (`fred-sdk`)

- [x] Define `ActorContext`
  - `user_id`
  - optional principal / subject metadata

- [x] Define `TeamContext`
  - `team_id`
  - optional team type (`personal`, `collaborative`)

- [x] Define `ExecutionTarget`
  - `agent_instance_id` (primary)
  - optional underlying agent reference for diagnostics only

- [x] Define `TraceContext`
  - `request_id`
  - `trace_id`
  - `correlation_id`
  - optional `session_id`
  - optional `checkpoint_id`

- [x] Define `ExecutionGrant`
  - issued by control-plane
  - includes:
    - `user_id`
    - `team_id`
    - `agent_instance_id`
    - allowed action (`execute`, `resume`)
    - audience (runtime service / endpoint)
    - expiry / issued-at
    - optional scopes / permissions
    - trace identifiers
    - optional logical storage scope if needed

- [x] Explicitly document:
  - `ExecutionGrant` authorizes access to **logical execution scope**
  - it must never contain infrastructure secrets or database connection details

---

#### 1.5.2 B. Freeze Runtime Request and Event Contracts (`fred-sdk`)

- [x] Define `RuntimeExecuteRequest`
  - `input`
  - `session_id`
  - optional `checkpoint_id`
  - optional `resume_payload`
  - optional `runtime_context`
  - `execution_grant` for managed execution

- [x] Ensure:
  - `session_id` remains the primary continuity key
  - `checkpoint_id` enables precise resume
  - `agent_instance_id` is carried through managed authorization semantics

- [x] Define runtime event models:
  - `RuntimeEvent`
  - `HumanInputRequest`
  - `RuntimeContext`

- [x] Define UI rendering models:
  - `UiPart`
  - `LinkPart`
  - `GeoPart`

- [x] Add an explicit persistence notification event if useful, for example:
  - `HistorySyncEvent`
  - or `TurnPersistedEvent`
  - as a runtime notification that persistence completed successfully

---

#### 1.5.3 C. Define Checkpoint and History Access Semantics

- [x] Explicitly document that `fred-runtime` is a **consumer** of persisted checkpoint state, not the ownership authority

- [ ] Require runtime to validate: _(documented; enforcement deferred to Phase 2–3, requires control-plane integration)_
  - `session_id` is authorized by the `ExecutionGrant`
  - `checkpoint_id`, when provided, belongs to the authorized `session_id`
  - `checkpoint_id` is resumable when used for resume
  - if resuming HITL, checkpoint is in a waiting state compatible with `resume_payload`

- [x] Explicitly separate:
  - **checkpoint state** = runtime-facing graph persistence
  - **history state** = UI-facing / audit-facing typed interaction history

- [x] Ensure persistence infra details remain runtime-environment concerns and are never exposed in frontend-facing contracts

---

#### 1.5.4 D. Bind Runtime Routes to Contracts (`fred-runtime`)

- [x] Update:
  - `POST /agents/execute`
  - `POST /agents/execute/stream`

- [ ] Ensure:
  - [x] request uses `RuntimeExecuteRequest`
  - [ ] all request/response/event models are OpenAPI-visible _(Phase 2: generate-openapi)_

- [ ] Ensure runtime event schemas are exposed via OpenAPI _(Phase 2)_

- [ ] Add a schema helper route only if strictly required _(deferred — not required for Phase 1)_

- [ ] Remove dependency on `agentic-backend /schemas/echo` _(Phase 2–5)_

---

#### 1.5.6 E. Enforce Authorization and Validation Semantics

- [x] Runtime MUST validate `ExecutionGrant`
- [x] Runtime MUST verify:
  - user
  - team
  - managed agent binding
  - intended audience / runtime endpoint
  - expiry / issuance validity
  - [ ] session / checkpoint consistency _(deferred — requires control-plane integration, Phase 2–3)_

- [x] Runtime MUST reject:
  - missing grant
  - invalid or expired grant
  - mismatched team / agent instance
  - [ ] invalid resume against non-waiting checkpoint state _(deferred, Phase 2–3)_

- [x] Control-plane and runtime endpoints MUST remain protected by:
  - RBAC via Keycloak
  - REBAC via OpenFGA

- [x] Explicitly document:
  - runtime pods do NOT own permission logic
  - control-plane is the sole authority for managed enrollment and runtime endpoint selection

---

#### 1.5.7 F. Enforce the Kubernetes-Native Platform Boundary

- [x] Add an architectural note stating that Fred code must not implement:
  - pod discovery
  - service discovery
  - custom routing logic
  - in-app balancing/failover topology
  - runtime endpoint topology management beyond configured endpoint references

- [x] Explicitly state that these concerns belong to:
  - Kubernetes `Service`
  - Ingress / Gateway
  - namespace configuration
  - DNS / stable service names
  - Argo CD / GitOps / deployment descriptors

- [x] Restrict Fred code responsibilities to:
  - authorization
  - contract validation
  - endpoint protection
  - managed execution semantics
  - history/checkpoint validation

---

#### 1.5.8 G. Align OpenAI Compatibility Layer

- [x] Replace `dict[str, Any]` for `fred.awaiting_human` with typed model (`HumanInputRequest`)
- [x] Add typed `ui_parts` to OpenAI-compatible metadata (`FredChunkMetadata.ui_parts`)
- [x] Replace `dict[str, Any]` for `tool_calls` with typed `OpenAIToolCall` / `OpenAIToolCallFunction`
- [x] Keep OpenAI compat aligned with runtime semantics, but not as the primary contract source

#### 1.5.9 H. Keep the Runtime CLI as a First-Class Contract Consumer

- [x] Update `fred-agents-cli` to use the Phase 1 runtime contracts without relying on legacy assumptions
- [x] Ensure the CLI can display:
  - current agent / execution target
  - current `session_id`
  - current `checkpoint_id` when relevant
  - stored history
  - execution context summary (`/context`)
- [x] Add a command for checkpoint inspection:
  - `/checkpoints` — list threads with sizes
  - `/checkpoint <thread_id>` — inspect all checkpoints for one thread
- [x] Add a command for execution context inspection: `/context`
- [x] Add interactive help assistant: `/help <question>` answers via the pod in the user's language
- [x] Detect malformed/unknown slash commands and show usage hints instead of forwarding to the agent
- [x] Ensure the CLI remains the easiest way for developers to inspect and validate runtime exchange semantics without using the frontend

---

### 1.6 Files to Inspect / Edit

- `libs/fred-sdk/fred_sdk/contracts/runtime.py`
- `libs/fred-sdk/fred_sdk/contracts/context.py`
- `libs/fred-sdk/fred_sdk/contracts/openai_compat.py`
- `libs/fred-runtime/fred_runtime/app/agent_app.py`
- `libs/fred-runtime/fred_runtime/app/openai_compat_router.py`

---

### 1.7 Validation

- [x] `make code-quality` in `libs/fred-sdk`
- [x] `make test` in `libs/fred-sdk`
- [x] `make code-quality` in `libs/fred-runtime`
- [x] `make test` in `libs/fred-runtime`
- [x] `fred-agents-cli` works against the updated runtime contracts
- [x] CLI can display session, history, and checkpoint information clearly
- [x] CLI can display a safe summary of execution context / authorization scope
- [x] A developer can understand and validate a managed execution flow from terminal only

- [x] OpenAPI includes:
  - `RuntimeExecuteRequest`
  - execution identity models
  - authorization models
  - runtime event models
  - UI part models

- [ ] No frontend schema generation depends on `agentic-backend` _(Phase 2–5)_

- [x] No Phase 1 code introduces custom runtime routing/discovery logic better handled by Kubernetes

---

### 1.8 Exit Criteria

- [x] Every execution is traceable to:
  - `user_id + team_id + agent_instance_id`

- [x] Runtime contract includes:
  - authorization context (`ExecutionGrant`)
  - session continuity (`session_id`)
  - checkpoint resume (`checkpoint_id`)

- [ ] Runtime validates session / checkpoint authorization before resume _(deferred — Phase 2–3, requires control-plane integration)_

- [x] RBAC and REBAC protections remain explicit on all relevant endpoints

- [x] Frontend runtime typing can be generated from `fred-runtime`

- [ ] `agentic-backend` is no longer required as a schema source _(Phase 2–5)_

- [x] No Fred code path depends on custom pod discovery or runtime routing logic
- [x] Runtime CLI is fully aligned with the frozen execution contract
- [x] Developers can inspect session, checkpoint, and execution context behavior without the frontend

---

### 1.9 Key Rules

- **`team_id` is mandatory and explicit**
- **`agent_instance_id` is the default execution target**
- **execution must include a verifiable authorization context**
- **runtime validates — control-plane decides**
- **checkpoint access must be authorized at session scope**
- **Fred code must not rebuild native Kubernetes routing/discovery behavior**
- **contracts are frozen before transport migration**

## 2 Phase 2 - Runtime OpenAPI And Frontend Codegen

### 2.1 Goal

Generate frontend runtime types from `fred-runtime`, not `agentic-backend`.

### 2.2 Tasks

- [x] Add `make generate-openapi` support for `libs/fred-runtime`
- [x] Produce `libs/fred-runtime/openapi.json`
- [x] Add a new frontend codegen config for runtime APIs
- [x] Generate a new slice, for example:
  - `apps/frontend/src/slices/runtime/runtimeOpenApi.ts`
- [x] Keep old `agenticOpenApi.ts` temporarily during migration

### 2.3 Status Note

Phase 2 now generates the runtime slice and exposes the important runtime component schemas (`RuntimeEvent`, `ExecutionGrant`, `RuntimeExecuteRequest`, `ChatMessage`, UI parts) through `fred-runtime` OpenAPI.

Important nuance:

- RTK Query codegen still produces `any` for SSE mutation responses (`/agents/execute/stream`, `/v1/chat/completions`) because the transport remains `text/event-stream`
- this is acceptable for the migration because Phase 4 will parse SSE frames manually with `fetch()` and can use the generated component types from `runtimeOpenApi.ts`
- assistants should fix missing types in `fred-sdk` / `fred-runtime` first, then regenerate OpenAPI and `runtimeOpenApi.ts`; do not hand-maintain parallel frontend DTOs
- the documentation handoff for continuing this migration now lives in:
  - `docs/design/RUNTIME-EXECUTION-CONTRACT.md`
  - `docs/rfc/AGENTIC-POD-RFC.md`
  - `AGENTS.md`
  - `CLAUDE.md`

### 2.4 Files to inspect / edit

- `libs/fred-runtime/Makefile`
- `apps/frontend/Makefile`
- `apps/frontend/src/slices/agentic/agenticOpenApiConfig.json`

### 2.5 Validation

- [x] Runtime OpenAPI file generates locally
- [x] New RTK Query slice generates successfully
- [x] `npm` frontend typecheck/build still passes after generation

---

## 3 Phase 3 - Control Plane Product Surface And Managed Agent Selection

### 3.1 Goal

Move the frontend-facing **product, tenancy, and managed agent selection surface**
off `agentic-backend` and into `control-plane-backend`, without recreating
runtime execution transport there.

### 3.2 Readiness Note

Phase 3 is **not** a single endpoint-porting exercise.

Before broad implementation, freeze the smallest control-plane product
contracts so we do not:

- recreate `agentic-backend` DTOs in a new backend
- mix session metadata with runtime history
- keep legacy `agent_id` semantics where managed `agent_instance_id` is required
- start the frontend SSE rewrite before the managed product surface exists

Source of truth for this phase:

- `docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`
- `docs/platform/PLATFORM_RUNTIME_MAP.md`
- `docs/design/RUNTIME-EXECUTION-CONTRACT.md`

### 3.3 Core Rule

The primary purpose of Phase 3 is to freeze the **smallest clean product
contract** that allows the frontend to select a **team-scoped managed execution
target** before the SSE runtime transport migration begins.

### 3.4 Configuration Minimality Rule

> **The only static configuration for the product surface is the list of runtime
> pod references (`runtime_catalog_sources`).** Each entry has:
>
> - `runtime_id` — stable pod identity
> - `base_url` — cluster-internal URL for server-side template discovery
> - `ingress_prefix` — ingress-relative URL prefix returned to the browser
>
> Nothing else belongs in deployment YAML. Agent catalog, enrollment, and team
> assignment are entirely runtime/DB concerns.

### 3.5 Template Discovery Model

Every agent advertised by a configured runtime pod is visible to every team.
No per-team whitelist or filtering exists at this layer.

Teams discover available templates via `GET /teams/{team_id}/agent-templates`,
which aggregates the live catalog from all enabled pods. Any discovered template
can be enrolled for any team via the UI.

Admin-level visibility control (preventing a specific team from seeing a
specific agent) is explicitly deferred. It should be implemented as a config or
DB whitelist when the need arises — not pre-emptively.

### 3.6 Product Identity Rules

#### 3.6.1 Agent Template

An `AgentTemplate` is a capability discovered from a runtime pod.

Rules:

- `template_id` is the stable product identity (`{runtime_id}:{source_agent_id}`)
- `source_agent_id` is kept in the public summary because enrollment requires it
  (the system must know which agent on which pod to wire up)
- any discovered template can be enrolled for any team — no admin approval needed
- enrollment is the only gate between "available in catalog" and "executable"

#### 3.6.2 Managed Agent Instance

A `ManagedAgentInstance` is what gets created when a team enrolls a template.
It is the team-scoped executable product object selected in the frontend.

Rules:

- `agent_instance_id` is the primary frontend execution identity
- frontend MUST use `agent_instance_id` for managed execution
- frontend MUST NOT use raw `source_agent_id` as the execution target
- instances live in the DB, never in deployment config

#### 3.6.3 Runtime Binding

A `RuntimeBinding` is the internal control-plane mapping from one enrolled
instance to the runtime pod and agent it uses.

Rules:

- control-plane resolves `agent_instance_id → source_runtime_id → ingress_prefix`
- runtime binding is an internal control-plane concern
- frontend never receives cluster-internal runtime details

#### 3.6.4 Lifecycle And Availability Rules

This section freezes the simple managed-agent lifecycle model.

Rules:

- `AgentTemplate` means a live-discovered runtime capability and nothing more
- `ManagedAgentInstance` means a DB-backed team enrollment created from one
  template
- deleting or unbinding a managed instance is a control-plane DB operation, not
  a runtime operation
- template discovery availability and enrolled instance availability are
  different states and MUST NOT be conflated

If a runtime pod becomes unavailable after enrollment:

- its templates may disappear from `GET /teams/{team_id}/agent-templates`
- already enrolled instances remain in
  `GET /teams/{team_id}/agent-instances`
- `prepare-execution` fails only if the runtime source is no longer configured,
  disabled, or missing ingress data
- if the source remains configured but the pod itself is down, the current
  implementation may still return `ExecutionPreparation` and fail later on the
  browser-to-runtime call
- unbinding must continue to work because it does not depend on runtime liveness

Frontend implication:

- the user must still see the enrolled managed instance
- the UI must be able to communicate that the instance exists but the runtime is
  currently unavailable
- delete / unbind remains available when permissions allow it

### 3.7 Phase 3a - Contract Freeze And Bootstrap Surface

#### 3.7.1 Deliverable

A small, typed control-plane product surface that lets the frontend:

- bootstrap frontend settings and permissions from `control-plane-backend`
- discover agent templates
- list team-scoped managed agent instances by `agent_instance_id`
- prepare for later session metadata migration without pulling runtime history into control-plane

#### 3.7.2 Status Note

Phase 3a now has a concrete read-only backend surface in `control-plane-backend`
and regenerated frontend typing from `apps/control-plane-backend/openapi.json`.

Implemented public read-only endpoints:

- `GET /frontend/bootstrap`
- `GET /teams/{team_id}/agent-templates`
- `GET /teams/{team_id}/agent-instances`

Important nuance:

- `PermissionSummary` is currently exposed inside `FrontendBootstrap`, not as a separate public endpoint
- managed instance listing endpoints exist and are typed; the registry is empty until Phase 3c DB CRUD lands
- `GET /agent-instances/{agent_instance_id}/runtime` exists as a control-plane-owned runtime resolution helper, but it is not a primary frontend product contract
- Phase 3a still does **not** move session metadata, feedback, or MCP CRUD

**Architectural boundary clarified after Phase 3a:**

`PlatformConfig` (deployment YAML) contains ONLY `runtime_catalog_sources` — references
to runtime pods. Managed agent instance enrollment (`agent_instance_id`, `team_id`) is
ALWAYS DB-backed, never static config. The runtime pod advertises its own agent catalog
via `/agents/templates`; the control-plane discovers it dynamically. Tenant enrollment
(which team has which agents) is operational data that belongs in the DB.

#### 3.7.3 Tasks

- [x] Add a Phase 3a architecture/design note for control-plane product contracts
- [x] Freeze typed frontend bootstrap contracts in `control-plane-backend`
- [x] Freeze typed permission summary contracts
- [x] Freeze typed agent template summary contracts
- [x] Freeze typed managed agent instance contracts using `agent_instance_id`
- [x] Add `GET /frontend/bootstrap` in `control-plane-backend`
- [x] Add read-only agent template aggregation endpoint
- [x] Add read-only team-scoped managed agent instance listing endpoint
- [x] Regenerate `apps/control-plane-backend/openapi.json`
- [x] Regenerate frontend `controlPlaneOpenApi.ts`

#### 3.7.4 Validation

- [x] Phase 3a contracts are documented and locally reviewed
- [x] No Phase 3a contract proxies runtime execution through control-plane
- [x] No Phase 3a contract exposes runtime history as control-plane metadata
- [x] No Phase 3a public model depends on `agentic-backend` runtime transport DTOs
- [x] `make code-quality` in `control-plane-backend`
- [x] `make test` in `control-plane-backend`
- [x] frontend control-plane codegen regenerates successfully
- [x] `npm` frontend build still passes after control-plane regeneration

### 3.8 Scope

- `control-plane-backend`
- `frontend`

### 3.9 Key Rules

- New control-plane responsibilities

- frontend settings
- user permissions
- agent template discovery
- managed agent instance CRUD
- team-scoped agent listing
- session metadata CRUD
- session preferences
- attachment metadata
- feedback
- MCP server CRUD

### 3.10 Tasks

> This section is a structural index. Detailed tasks and status live in the
> sub-phases below. Do not use this list as an operational checklist.

- [ ] Expand bootstrap/config surface only if `FrontendBootstrap` becomes insufficient
- [ ] Add permissions endpoint if frontend still needs a flat permission list
- [x] Add agent template aggregation endpoint (→ Phase 3a)
- [x] Extend `AgentTemplateSummary` with `mcp_servers: list[ManagedMcpServerRef]` — enriched with `display_name` from runtime MCP catalog (→ 2026-04-28)
- [x] Extend `ManagedMcpServerRef` with `display_name` + `config_fields` for Phase 2 MCP configuration (→ 2026-04-28)
- [x] Populate `ManagedMcpServerRef.config_fields` from `mcp_catalog.yaml` — tool-declared capability options (RFC: `docs/rfc/MCP-CATALOG-CONFIG-FIELDS-RFC.md`, done 2026-05-06):
  - [x] Add `config_fields: list[FieldSpec] = []` to `MCPServerConfiguration` in `fred-sdk`
  - [x] Extend `mcp_catalog.yaml` format: add `config_fields` entries to `mcp-knowledge-flow-mcp-text` and `mcp-knowledge-flow-corpus`
  - [x] Extend control-plane product service enrichment loop to copy `config_fields` from catalog entries into `ManagedMcpServerRef`
  - [x] Remove `chat_options.*` `FieldSpec` declarations from `fred-agents` agent templates (`general_assistant.py`, `rag_expert.py`)
  - [ ] Frontend: render `ManagedMcpServerRef.config_fields` beneath active server checkboxes in `AgentFormBody` Tools tab
- [x] Add agent instance CRUD endpoints (→ Phase 3c — POST enroll + DELETE unenroll done)
- [ ] **CTRLP-06** — Atomic enrollment: collect all validation errors (tuning fields, MCP server IDs,
      MCP config values) before returning; structured 422 body `[{field, message}]` per error.
      Atomicity already guaranteed (single `store.create()` after all validation). Remaining: fail-last
      collection + structured response shape. Ref: kea #1601 (partial fix).
- [x] Add read-only team-scoped agent instance listing endpoint (→ Phase 3a)
- [x] Add session create + list endpoints (→ Phase FRONT-04 — `POST/GET /teams/{team_id}/sessions`); delete deferred
- [ ] Add session preference get/update endpoints (→ Phase 3b)
- [ ] Add feedback CRUD endpoints (→ Phase 3b)
- [ ] Add MCP server CRUD endpoints (→ Phase 3b)
- [ ] Decide whether attachment upload is proxied by control-plane or remains direct to another backend

### 3.11 Locked MCP servers on specialized agent templates — **CTRLP-07**

**Status:** done 2026-05-22

- [x] Add `locked: bool = False` to `MCPServerRef` in `fred-sdk` contracts
- [x] Add `locked: bool = False` to `ManagedMcpServerRef` in `control_plane_backend/config/models.py`
- [x] Forward `locked` in the MCP catalog enrichment loop (`product/service.py`)
- [x] Set `locked=True` on the Sentinel (Monitoring assistant) `MCPServerRef`
- [x] Regenerate `controlPlaneOpenApi.ts`
- [x] Render toggle as disabled in `McpServerCard` when `server.locked === true`; show "required" badge

RFC: `docs/swift/rfc/MCP-CATALOG-CONFIG-FIELDS-RFC.md §7`

### 3.12 Important note

Do **not** move runtime execution itself to control-plane.
Control-plane should orchestrate metadata and ownership, while execution stays in `fred-runtime`.

Additional Phase 3 guardrails:

- control-plane session APIs are metadata-oriented; runtime message history stays in `fred-runtime`
- managed agent APIs must use `agent_instance_id` as the primary frontend identity
- runtime binding stays an internal control-plane concern unless the frontend has a proven need for a specific projection
- do not port `AgentSettings` wholesale as the public control-plane contract
- defer binary attachment upload routing until explicitly decided

### 3.12 Files to inspect

- `apps/control-plane-backend/control_plane_backend/main.py`
- `docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`
- `agentic-backend/agentic_backend/core/agents/agent_controller.py`
- `agentic-backend/agentic_backend/core/chatbot/chatbot_controller.py`
- `agentic-backend/agentic_backend/core/mcp/mcp_controller.py`
- `agentic-backend/agentic_backend/core/feedback/feedback_controller.py`

### 3.13 Validation

- [x] `make code-quality` in `control-plane-backend`
- [x] `make test` in `control-plane-backend`

### 3.14 Tool-declared behavioral contracts (agent_instructions) — **CTRLP-08**

**Status:** done (2026-05-22) — owner: Simon
**RFC:** `docs/swift/rfc/MCP-CATALOG-CONFIG-FIELDS-RFC.md §8`

**Problem:** Citation rules and other mandatory tool behaviors are currently
encoded in agent template system prompts. An operator who writes a custom
`prompts.system` silently removes them. This is fragile, duplicated across
templates, and assigns ownership to the wrong layer — behavior that belongs
to the tool lives in the agent prompt.

**Solution:** Each MCP server catalog entry can declare an `agent_instructions`
field. The runtime appends these fragments to the effective system prompt
whenever that server is active, after the operator's custom prompt, unconditionally.

**Implementation tasks:**

_`mcp_catalog.yaml` (fred-agents):_

- [x] Add `agent_instructions` block to the `mcp-knowledge-flow-mcp-text` entry
      with citation rules (inline format, Sources section, no URLs/links/IDs)

_`fred-sdk` (`MCPServerConfiguration`):_

- [x] Add `agent_instructions: str | None = None` to `MCPServerConfiguration`
      in `fred_sdk/contracts/models.py`

_`fred-runtime` (`agent_app.py`):_

- [x] Pass the loaded catalog (`list[MCPServerConfiguration]`) into
      `_apply_runtime_tuning` as an additional parameter
- [x] After resolving `system_prompt_template` (current lines 887–891), iterate
      active `mcp_servers`; for each server with a non-empty `agent_instructions`
      in the catalog, append the fragment to the effective system prompt
- [x] Update the two call sites (lines ~955 and ~1011) to pass the catalog

_`fred-agents` (`react_rag_mcp.py`):_

- [x] Remove citation rules from `_SYSTEM_PROMPT` — they now live in the catalog

_Validation:_

- [x] Offline unit test: `_apply_runtime_tuning` with a catalog entry that has
      `agent_instructions`; assert fragment is present in `system_prompt_template`
      regardless of the operator's custom prompt
- [x] Offline unit test: server inactive → fragment absent
- [x] `make code-quality && make test` in `fred-runtime` and `fred-sdk`

---

## 3b Phase 3b - Backend Completeness Gate

### 3b.1 Goal

Before the frontend transport/admin cutover, make the backend path complete,
team-scoped, and fully observable end-to-end across:

- `fred-runtime`
- `control-plane-backend`
- the runtime CLI (`fred-agents-cli`)

This phase exists so the frontend does **not** become the first place where we
discover backend gaps in:

- managed execution scope
- session/checkpoint authorization
- runtime binding completeness
- traceability / KPI / metrics enrichment
- Langfuse metadata quality

### 3b.2 Status Note

Phase 3b is now underway.

Concrete slices now landed:

- `fred-agents-cli` supports `/team`, `--team-id`, and scenario overrides for
  explicit team-scoped backend validation
- runtime resume paths now require `ExecutionGrant.action=resume` for managed
  HITL resumes
- runtime locally validates `session_id` + `checkpoint_id` consistency before
  resuming and now propagates `checkpoint_id` into execution plumbing
- runtime graph KPI dims, KF client/tool KPI dims, and Langfuse span metadata
  now preserve managed execution identity fields available at runtime
- `fred-runtime` now boots a concrete `KPIWriter`, restores Prometheus export
  when `observability.metrics=prometheus`, and emits process/SQL pool KPIs
  without requiring Grafana/Prometheus deployment just to expose the metrics
- `fred-agents-cli` now supports `/kpi [pattern]` and can inspect the runtime
  Prometheus surface directly for local KPI validation and laptop benchmarks

Remaining focus before frontend work:

- validate one complete managed execution flow from `fred-agents-cli` against
  the control-plane-approved path, not just pod-local execution
- validate one managed HITL resume end-to-end with the same session/checkpoint
  identity set preserved
- verify that one capability reachable through raw `agent_id` still behaves
  correctly when invoked through team-scoped managed execution
- finish the remaining audit of non-runtime log/KPI sinks so the same managed
  identity set is preserved everywhere

### 3b.3 Core Rule

Even when a runtime pod exposes an agent capability outside team semantics
(for example a raw `agent_id` template for dev/internal use), the same pod must
still behave correctly for a **team-scoped managed call** resolved through
`agent_instance_id` + `ExecutionGrant`.

The managed path is the authoritative product path.

### 3b.4 Required Backend Invariants

- every managed execution remains attributable to:
  - `user_id`
  - `team_id`
  - `agent_instance_id`
- the same managed identity must flow through:
  - runtime execution
  - session history
  - checkpoint access and resume
  - logs
  - KPI rows
  - metrics dimensions
  - tracing payloads
  - Langfuse metadata
- `template_agent_id` may still exist for diagnostics/runtime lookup, but it must not replace `agent_instance_id` as the primary managed identity
- `fred-agents-cli` must remain able to validate managed team-scoped execution without the frontend

### 3b.5 Observability Enrichment Contract

At minimum, backend observability should preserve when relevant:

- `user_id`
- `team_id`
- `agent_instance_id`
- `template_agent_id`
- `session_id`
- `checkpoint_id`
- `trace_id`
- `correlation_id`
- runtime identity (`runtime_id`, service name, or equivalent)
- execution mode / action (`execute`, `resume`, HITL wait/resume)

This enrichment requirement applies equally to:

- local logs
- KPI persistence
- metrics
- trace/span metadata
- Langfuse exports or queries

### 3b.6 Tasks

- [x] Freeze and document the backend observability enrichment contract
- [ ] Ensure managed team-scoped execution works correctly even when the same pod also exposes raw `agent_id` access for dev/internal use
- [x] Ensure runtime validates session/checkpoint authorization consistently for managed resume flows
- [ ] Ensure control-plane runtime resolution + authorization context is sufficient for managed team-scoped execution
- [x] Ensure `fred-agents-cli` can validate managed execution context, history, and checkpoint behavior without frontend dependencies
- [x] Ensure Langfuse traces preserve managed execution identity and correlation metadata
- [x] Restore the runtime Prometheus/KPI exporter wiring needed for local scrapes and laptop benchmarks
- [x] Add a runtime CLI KPI inspection command on top of the restored scrapeable metrics surface
- [ ] Ensure KPI/metrics/logging preserve the same managed execution identity set (→ Phase 7)
- [x] Add backend-focused tests for managed team-scoped execution and observability enrichment

#### 3b.6 SSE Contract Corrections (discovered April 2026) — ✅ Fixed

These gaps were found while implementing an external SSE bench client.
All four fixed in commit `eedbc610`. Full analysis and resolution status in
`docs/design/RUNTIME-EXECUTION-CONTRACT.md` Section 8.

- [x] **Formalize the error signal** — `RuntimeErrorEvent(kind="execution_error",
message=str)` added to `fred-sdk`, wired in `agent_app.py`, OpenAPI and
      `runtimeOpenApi.ts` regenerated.

- [x] **`TurnPersistedEvent` decision** — explicitly documented as not emitted
      over SSE. `final` is the only reliable end-of-turn signal. Type kept for
      future use.

- [x] **SSE stream termination** — documented in `/agents/execute/stream`
      docstring and `RUNTIME-EXECUTION-CONTRACT.md` section 0.

- [x] **Direct-mode `runtime_context.user_id`** — documented in
      `RuntimeExecuteRequest.runtime_context` description and section 0.1 of
      `RUNTIME-EXECUTION-CONTRACT.md`.

#### 3b.8 Standalone / No-Security Defaults

In no-security mode (`security_enabled=false`), the current direct execution
path requires the caller to pass `runtime_context.team_id = "personal"`
explicitly. If omitted, `team_id` is absent from all KPI dims, checkpoints,
and history rows — breaking identity even in the simplest single-user
deployment (laptop, SOC workstation, airgapped instance).

The fix is small and self-contained.

**Rule:**

> When `security_enabled=false` and no `execution_grant` is present,
> `team_id` MUST default to `"personal"` in the runtime execution context
> without any caller action.

- [x] In `fred-runtime` `_stream()`: resolve `team_id` once at the top and
      propagate `resolved_team_id` to `_iterate_runtime_event_payloads`,
      `_emit_turn_completed`, and `_write_turn_history`. When security is disabled
      and no team_id is provided, default to `"personal"`.
      (`libs/fred-runtime/fred_runtime/app/agent_app.py`)

- [x] In `fred-agents-cli` CLI: when security is disabled (no `--keycloak`
      flag / no token), default the active team to `personal` automatically —
      no `--team-id` required. Startup banner now prints active team identity.
      (`libs/fred-runtime/fred_runtime/client.py`)

- [x] Two unit tests: (1) `_stream()` resolves `team_id="personal"` before
      calling `_iterate`; (2) full end-to-end: `PortableContext.team_id=="personal"`.
      (`libs/fred-runtime/tests/test_agent_app.py`)

- [x] Updated `RUNTIME-EXECUTION-CONTRACT.md` section 0 with a dedicated
      "Standalone / no-security mode" paragraph covering the `team_id` default,
      CLI banner, and what each subsystem receives.

#### 3b.9 Checkpoint Retention Policy (Standalone)

In standalone mode (SQLite at `~/.fred/pod/pod.sqlite3`) checkpoints accumulate
indefinitely — one pointer row per graph step per session. A 10-turn conversation
with a ReAct agent writes roughly 20-40 checkpoint rows. There is no automatic
pruning.

**Current state:**

- Manual `DELETE /agents/checkpoints/{session_id}` exists and works.
- `GET /agents/checkpoints/_stats` and `GET /agents/checkpoints` let an admin
  see growth.
- No TTL, no background sweeper, no auto-purge on session close.

**Design decision needed (not a bug, record it now):**

> Should checkpoints be kept after a session's `final` event is emitted?

- **Keep indefinitely (current):** user can resume sessions across restarts.
  Storage grows. Suitable while HITL resume is a first-class feature.
- **Purge on session close:** lighter storage, no resume after exit. Would
  require a session-closed signal the runtime currently doesn't emit.
- **TTL (e.g. 30 days):** background sweeper deletes threads not touched in N
  days. Reasonable default for production standalone.

**Recommended path:** add a `storage.checkpoint_ttl_days` config knob (default
`null` = keep forever) and a background sweeper that runs on pod startup. No
implementation until the TTL policy is agreed.

- [ ] Agree on TTL default for standalone (`null` / 30 / 90 days)
- [ ] Add `storage.checkpoint_ttl_days: int | null` to `PodStorageConfig`
- [ ] Implement background sweeper in `create_agent_app` lifespan
- [ ] Expose `/agents/checkpoints/purge` (dry_run=true by default) for ops teams

#### 3b.10 Standalone pod Uvicorn concurrency cap (`RUNTIME-03`) — ✅ Done 2026-05-21

Small mechanical parity port from the historical `1534` branch, scoped only to
the modern runtime pod (`apps/fred-agents` + `libs/fred-runtime`).

This is **not** a new public execution contract and does **not** require a new
RFC. It only exposes one optional Uvicorn startup knob through the existing pod
configuration schema.

- [x] Add `app.limit_concurrency: int | null` to `PodAppConfig`
- [x] Add `limit_concurrency: null` to `apps/fred-agents/config/configuration*.yaml`
- [x] Pass `config.app.limit_concurrency` to `uvicorn.run(...)` in `python -m fred_agents`
- [x] Cover config loading for explicit value and omitted-field default
- [x] Add an offline entrypoint test proving `main()` forwards `limit_concurrency`
- [x] Document the config knob in `libs/fred-runtime/README.md`

**Deferred follow-up (not part of `RUNTIME-03`):**
When a dedicated `fred-agents` chart exists on this branch, add the Helm-side
`--limit-concurrency` wiring there and re-evaluate TCP probes under saturation.

#### 3b.11 fred chart migration to the modern runtime topology (`OPS-01`) — ✅ Done 2026-06-04

RFC ref: `docs/swift/rfc/FRED-CHART-MODERNIZATION-RFC.md`
Execution: GitHub issue `#1685`

This chart task is now unblocked; `OPS-02` and `OPS-03` closed on
2026-06-03.
Current target (2026-06-03): use this track for the internal Swift deployment
on GCP / GKE Autopilot. Do not open a parallel backlog item for the same chart
work.

- [x] Update `deploy/charts/fred` so the base chart deploys the modern runtime
      topology (`fred-agents`, `control-plane-backend`,
      `knowledge-flow-backend`, `frontend`) instead of the legacy
      `agentic-backend` runtime path
- [x] Add `RUNTIME-03` support to the `fred-agents` chart values: expose
      `app.limit_concurrency`, ensure the canonical `python -m fred_agents`
      entrypoint forwards it to Uvicorn, and re-evaluate liveness/readiness
      probe strategy under saturation (TCP probes if HTTP probes become
      unreliable)
- [x] Align frontend ingress/upstream wiring and control-plane
      `platform.runtime_catalog_sources` with the `/fred/agents/v2` runtime
      base path
- [x] Update local Helm overlays (`deploy/local/k3d/*.yaml`) so they target the
      same modern runtime topology as the base chart
- [x] Confirm chart defaults and values overlays stay compatible with the first
      internal GCP / GKE Autopilot deployment target

Closed on 2026-06-04 after migrating the Helm runtime topology to
`fred-agents`, wiring `/fred/agents/v2` through ingress and control-plane
runtime discovery, refreshing the local `k3d` overlays, and validating with
`helm template`, `make code-quality`, and `make test`.

#### 3b.12 CI adaptation for the modern deployment architecture (`OPS-02`) — ✅ Done 2026-06-03

RFC ref: `docs/swift/rfc/FRED-CHART-MODERNIZATION-RFC.md`
Execution: GitHub issue `#1663`

- [x] Remove or replace CI jobs that still treat `agentic-backend` as the
      primary runtime artifact for build, publish, scan, or validation
- [x] Add CI coverage for the modern deployment artifact set
      (`fred-agents`, `control-plane-backend`, `knowledge-flow-backend`,
      `frontend`)
- [x] Ensure Helm/chart validation jobs render and validate the modern
      `deploy/charts/fred` topology used on this branch
- [x] Publish image/chart metadata that matches the modern runtime naming and
      deployment flow

#### 3b.13 Dockerfile and image packaging alignment (`OPS-03`) — ✅ Done 2026-06-03

RFC ref: `docs/swift/rfc/FRED-CHART-MODERNIZATION-RFC.md`
Execution: GitHub issue `#1664`

- [x] Provide or align production Dockerfiles for `apps/fred-agents` with the
      expectations of `deploy/charts/fred`
- [x] Update image names, build contexts, and startup commands so deployed
      images expose the `/fred/agents/v2` runtime base path
- [x] Remove legacy `agentic-backend` packaging assumptions from deployment
      defaults and local Helm overlays
- [x] Confirm the modern images still mount external config/catalog files via
      the standard `ENV_FILE` / `CONFIG_FILE` startup contract
- [x] Confirm the Dockerfiles and startup contract are usable as-is for the
      first internal GCP / GKE Autopilot deployment

#### OPS-04 Unified task event stream and migration cockpit

RFC ref: `docs/swift/rfc/TASK-EVENT-STREAM-RFC.md`
Execution: waived GitHub issue for local session

**P1 — Shared infrastructure (fred-core + both backends)**

- [ ] Add `fred_core/tasks/` module: `TaskEvent`, `TaskLogEvent`, `TaskState`, `IEventBus`, `IScheduler`
- [ ] Implement `MemoryEventBus` (asyncio queues) and `PostgresEventBus` (LISTEN/NOTIFY) in `fred-core`
- [ ] Lift `IScheduler` protocol to `fred-core`; `MemoryScheduler` and `TemporalScheduler` implementations
- [ ] Add `task_run` + `task_event_log` Alembic migrations to `fred_swift` (control-plane) and `knowledge_flow` (knowledge-flow)
- [ ] Add `POST /api/v1/tasks`, `GET /api/v1/tasks/{id}/events`, `POST /api/v1/tasks/{id}/cancel` to both backends
- [ ] SSE endpoint: replay from `Last-Event-ID` + `seq`, heartbeat every 30 s, terminal state closes stream

**P2 — Migration cockpit (control-plane + frontend)**

- [ ] Implement five migration activities: `preflight`, `copy_tables`, `personal_teams`, `migrate_agents`, `validate`
- [ ] Agent mapping table: `v2.react.basic` → `fred.github.assistant`, `v2.production.sql_analyst` → `fred.github.sql_expert`
- [ ] Step-ordering enforcement: `POST /tasks` returns 409 if prerequisite step not `succeeded`
- [ ] Frontend atoms: `TaskStateBadge`, `ProgressBar` (pulse when `progress=null`), `LogLine`
- [ ] Frontend molecules: `BatchStepCard` (badge + bar + log + Run; cancel affordance optional per consumer)
- [ ] Frontend hook: `useTaskStream(taskId)` — owns SSE connection, handles reconnect
- [ ] Cockpit page `/admin/cockpit` — owner-only, 5 × `BatchStepCard` in order

**P3 — Knowledge-flow migration**

- [ ] Keep `BaseScheduler` public API; delegate backend dispatch internally to `IScheduler`
- [ ] Replace `get_progress()` poll-based pattern with `TaskEvent` emission from activities
- [ ] `record_workflow_status` and `record_current_document` activities emit `TaskEvent` via `IEventBus`
- [ ] Ingestion UI panels consume `useTaskStream` — live per-document progress replaces polling
- [ ] Deprecate `sched_workflow_tasks` table (superseded by `task_run`)

**Task reconciliation — durable execution binding + sweeper (RFC §2.8)**

- [ ] Add `executor` + `execution_id` columns to `task_run` (typed, no JSONB); submitter binds them before `scheduler.submit` using a pre-generated workflow id (no clobber race)
- [ ] Extend `IScheduler` with `get_status(execution_id) -> ExecutionStatus | None` (`TemporalScheduler` via `describe`; `None` = unreachable)
- [ ] `TaskService.reconcile_task` / `reconcile_stale`: map executor status → terminal `failed` `TaskEvent`; `running` / `None` leave untouched (never false-fail)
- [ ] Sweeper: Temporal scheduled workflow per task-owning worker calls `reconcile_stale(grace, limit)`; optional read-time reconcile on SSE subscribe
- [ ] Tests: reconcile decision matrix (failed / timed_out / completed / running / None) + integration (stuck task → terminal without the original worker)

#### OPS-05 Object storage naming cleanup

RFC ref: `docs/swift/rfc/OBJECT-STORAGE-NAMING-RFC.md`
Execution: `TBD`

Problem: several file names, comments, and docs still imply that Fred uses
MinIO as the platform storage contract. In practice the contract is S3-compatible
object storage or generic object storage. SeaweedFS has already been wired by
changing ports only, which confirms that MinIO is one implementation detail, not
the product architecture.

- [ ] Audit file names, comments, Helm/config keys, and docs that mention
      `minio`, `MinIO`, or presigned MinIO URLs
- [ ] Rename MinIO-specific file names only when they expose a generic storage
      abstraction and the code path is not actually tied to the MinIO Python
      client or MinIO-only behavior
- [ ] Replace docs/comments with `S3-compatible object storage`, `S3`, or
      `object storage` when that is the accurate contract
- [ ] Keep `MinIO` wording where it identifies a concrete implementation,
      local-development service, dependency, SDK adapter, env var, or chart value
- [ ] Confirm SeaweedFS-compatible configuration remains documented as a normal
      S3/object-storage deployment, with port/endpoint differences only
- [ ] Update deployment and operations docs so RUNTIME-01/object storage is not
      described as MinIO-only

### 3b.7 Validation

- [ ] one managed execution works end-to-end from `fred-agents-cli`
- [ ] one managed HITL resume flow works end-to-end from `fred-agents-cli`
- [ ] one runtime capability reachable through raw `agent_id` also works correctly through team-scoped managed execution
- [ ] managed execution metadata remains consistent across runtime history, checkpoints, logs, KPI, and traces
- [ ] Langfuse-visible trace metadata includes the required managed execution identity fields
- [x] one runtime pod can expose a scrapeable Prometheus metrics surface again when configured
- [x] one developer can inspect pod KPIs locally from `fred-agents-cli` without Grafana/Prometheus dashboards
- [x] no frontend code is required to validate these backend guarantees — VALID-01 scenarios run via `make test-integration-only`

**VALID-01 scenario automation (2026-04-26):**

- `run_scenario_file()` extended: `${env:VAR}` substitution → `ScenarioSkipped`; `history_has_messages` and `kpi_turn_recorded` check kinds; `agent_instance_id` propagation; `hitl` step type (two-phase pause/resume)
- `apps/fred-agents/tests/scenarios/s1_raw_echo.yaml` — raw `agent_id` path, no env var required
- `apps/fred-agents/tests/scenarios/s1_managed_echo.yaml` — managed path, requires `FRED_AGENT_INSTANCE_ID`
- `apps/fred-agents/tests/scenarios/s1_hitl_resume.yaml` — HITL two-phase flow with `fred.github.test_assistant`
- `test_scenarios.py` catches `ScenarioSkipped` → `pytest.skip()`

**VALID-02 — Admin self-test harness** (RFC: `docs/swift/rfc/ADMIN-SELF-TEST-HARNESS-RFC.md`, **Amendment A** = UI-driven, real-pipeline)

- [x] architecture redesigned to UI-driven over the real pipeline; control-plane backend harness module removed (Amendment A)
- [x] deterministic self-test RAG agent `fred.github.self_test` (real retrieval, no LLM) + offline unit tests
- [x] frontend reusable pipeline engine (`features/pipeline/`): actions + scenarios + generic `usePipelineRun` (reusable for eval-demo seeding)
- [x] self-test scenario: create folders → ingest → real agent turns scoped A/B → assert marker → delete (auto-provisions + deletes its own agent instance)
- [x] agent visibility: internal agents (`AgentDefinition.public=False`) hidden from the create-agent catalog; harness enrolls via `include_non_public` (RFC: `AGENT-VISIBILITY-RFC.md`)
- [x] prompt-delivery journeys (deterministic, no-LLM): the self-test agent echoes the prompts it received so the harness asserts *delivery* end-to-end —
  - [x] **system prompt (tuning):** enroll the instance with a run-scoped `prompts.system` marker → assert it is echoed back (enrollment → tuning → runtime → agent)
  - [x] **context/marketplace prompt:** create a personal prompt → create a session → attach prompt to session → prepare-execution resolves `context_prompt_text` → assert it is echoed back (the self-test agent is the first consumer of `context_prompt_text`)
- [ ] Phase 2 — complete campaign:
  - [ ] search-mode journeys: hybrid / strict / semantic, with corpus terms crafted so each mode's result differs (extends VALID-03)
  - [ ] drive the *real* chat widgets (`ContextPromptPicker`, search-mode control, library scoper) rather than constructing `RuntimeContext` directly
  - [ ] attachment journey
- [ ] Phase 3 — unattended: headless mode + ~2h K8s CronJob on the live GKE release (service-account auth, reuse VALID-01 runner)
- [x] first live docker-compose run caught + fixed a platform-wide RAG index mismatch (KF API `embeddinggemma` vs worker `vector-index-mistral`)
- [x] prompt journeys caught + fixed a second platform gap: runtime dropped `context_prompt_text` when rebuilding `RuntimeContext` (`agent_app.py`), so selected marketplace/library prompts never reached any agent (RUNTIME-EXECUTION-CONTRACT §8.5; regression `test_execute_forwards_context_prompt_text_to_agent_binding`)
- Execution: GitHub issue #1828 (branch `1828-valid-02-…`)

---

## 3c Phase 3c - Execution Preparation And Secure Runtime Reachability

### 3c.1 Goal

Unblock the frontend SSE migration with a **strong, standard, and secured**
runtime reachability model that allows the frontend to:

- discover enrollable agent templates from `control-plane-backend`
- list already-enrolled managed agent instances for the current team
- enroll a template for the current team (creates a DB-backed instance)
- obtain a **control-plane-approved execution preparation**
- call the correct runtime pod **directly over HTTP SSE**
- do so **without learning Kubernetes internal topology**
- do so **without turning control-plane into a streaming proxy**

This phase is the last mandatory backend/product phase before the frontend SSE
connector can start safely.

> **Sequencing note:** Phase 3c backend contract and endpoint implementation
> may proceed in parallel with Phase 3b CLI validation work.
> Phase 3b validation gates Phase 4 start, not Phase 3c implementation.

### 3c.2 Security Clarification - Browser To Runtime Authentication

For browser-originated runtime execution on secured platforms, the runtime
request MUST carry:

- the authenticated user bearer token (for example Keycloak-issued access token)
- the control-plane-issued `ExecutionGrant`

The `ExecutionGrant` supplements authorization and managed target binding.
It MUST NOT replace authenticated user context.

Therefore, for frontend → runtime execution:

- user authentication remains mandatory
- `ExecutionGrant` remains mandatory
- `fred-runtime` MUST validate both

This is the required posture for standard secured Kubernetes deployments and
avoids weak trust-by-network or trust-by-grant-only patterns.

#### 3c.2.1 ExecutionGrant Trust Posture (Phase 3c Transition)

Until `ExecutionGrant` cryptographic signing is implemented, runtime grant
validation is structural only (expiry, field consistency). NOTE (2026-06-26
audit): the previously documented "audience prefix match" is **not** actually
performed by the runtime — see `RUNTIME-07` finding F3.

This is acceptable for Phase 3c only because:

- all browser traffic passes through HTTPS via ingress
- the authenticated Keycloak bearer token is independently validated
- grant lifetime is short (≤ 5 minutes)

Cryptographic signing MUST be implemented before production hardening. This is
now tracked in full as `RUNTIME-07` below (supersedes the original one-line
"Phase 3c Task A" follow-up).

#### 3c.2.2 `RUNTIME-07` — Runtime authz hardening (C3 readiness)

> ⚠️ **DESIGN REVERSED — rev. 2, 2026-06-27 (RFC §13, decision D5).** The signed
> `ExecutionGrant` (Phases 2–3 below, delivered on PR #1857) is **abandoned**: making
> the control-plane a proprietary cryptographic root of trust is an unnecessary C3/ANSSI
> homologation burden. The new target is the model already homologated on `main`,
> re-instantiated for 3 pods — each agent pod is a **Keycloak OAuth2 resource server**
> (strict JWT, already wired) authorizing every request with a **pod-side OpenFGA check**
> (shared `fred_core.security.rebac`). **KEEP** the multi-pod packaging and HTTPS/SSE
> transport. The phases below are retained as history; the active worklist is the
> **Target (rev. 2)** checklist immediately after them.

**Target (rev. 2) — IMPLEMENTED 2026-06-28 on branch 1853 (awaiting review + local-Docker
validation). Decision: "Option Kept" — managed instances + per-team tuning are RETAINED;
the signed grant is removed; the pod authorizes via OpenFGA and resolves template+tuning
from a team-scoped, ReBAC-gated control-plane endpoint (forwarding the user JWT; M2M is a
trivial future swap). All suites green: fred-core 203 / fred-sdk 186 / fred-runtime 379 /
control-plane 174 / fred-agents 33 / frontend tsc 0.**

- [x] T1 — Pod-side **OpenFGA check** in the common execute/stream/evaluate(+resume) path
      (`_authorize_execution_or_raise`, `agent_app.py`); `CAN_READ` on the caller's team,
      fail-closed 403; identity-only when the engine is Noop (dev). ✅
- [x] T2 — Per-agent **Keycloak audience**: each pod validates JWT `aud` against its own
      `security.user.client_id` (strict under `profile: c3`). Code supports it; each pod
      deployment overrides `client_id` (documented in `apps/fred-agents/config/configuration_prod.yaml`).
      Realm audience mappers + Helm per-release client_id are a deployment step (not code). ✅ (code/doc)
- [x] T3 — Pod OpenFGA check is **fail-closed** under C3: `apply_security_profile` now
      requires `security.rebac.enabled` (no permissive Noop in c3). ✅
- [x] T4 — **Grant layer removed**: fred-sdk `ExecutionGrant`/`grant_signing`; fred-core
      `keyless_signer`/`GrantSigningConfig`; control-plane signing + `/.well-known/grant-jwks`
      + old admin resolution endpoint; runtime verify/resolve-from-grant; `gen-grant-key` +
      Makefile target + `.gitignore` + config blocks + JSON schemas (regenerated). Frontend
      clients regenerated; `useChatSse`/pipeline no longer send a grant (team_id now travels
      in `runtime_context`). ✅
- [ ] T5 — NetworkPolicies (ingress→pod, pod→OpenFGA, pod→Keycloak, deny inter-agent) +
      end-to-end TLS to the pod. **Deployment infra (fred-deployment-factory / chart) — not
      in this branch.**
- [x] T6 — C3 profile reworked: dropped `grant_signing`; keeps `STRICT_*` + `user/m2m
      enabled` + requires OpenFGA ReBAC (fail-closed). `test_security_profile.py` rewritten. ✅
- [x] T7 — **Resolution = team-scoped ReBAC endpoint** (supersedes the earlier D5b "drop
      managed instances"). New `GET /teams/{team_id}/agent-instances/{id}/runtime`
      (`CAN_READ` + `store.get_for_team`) returns template+tuning (config only); the runtime
      cross-checks resolved owner-team vs claimed team. Managed instances + per-team tuning
      are KEPT. **Fixes F2** (member resolves; no cross-tenant reach). ✅

**Review hardening (rev. 2.1, 2026-06-28 — Codex tight review; all confirmed valid).**

- [x] F-A — `/v1/chat/completions` (OpenAI-compat) was unauthenticated-by-team: now
      `app.openai_compat` defaults **False**; when enabled, the route runs the same
      Keycloak JWT + OpenFGA team gate (requires `X-Fred-Team-Id`); the **c3 profile
      fails closed at startup** if it is enabled (it executes by agent_id). ✅
- [x] F-B — identity is the **validated JWT**, never the body: `_authorize_and_resolve`
      overwrites `runtime_context.user_id` with `authenticated_user.uid` and **neutralizes
      body-supplied `access_token`/`refresh_token`** (the pod uses the header bearer). ✅
- [x] F-C — **private-per-owner sessions**: new `session_exists` history oracle +
      `_enforce_session_ownership` rejects (403) any request whose session exists but is
      not owned by the caller — closes intra-team resume/inject of another user's session. ✅
- [x] F-D — managed execution with ReBAC active and **no team → 403**; **direct `agent_id`
      execution forbidden under c3** (audited `direct_execution_forbidden`). ✅
- [x] F-E — JWT strict is now idiomatic under c3: PyJWT enforces **exact `issuer` +
      `audience` with `verify_aud=True`** on the verified payload (RS256 pinned); prefix
      issuer attack rejected. ✅
- [x] F-F — `security.profile` description corrected (no "signed grants"); **schemas +
      chart regenerated**. C3 activation = set `security.profile: c3` per release (Helm). ✅
- [ ] F-G — **3 real agent pods in the chart** + per-pod Keycloak client_id + NetworkPolicies.
      **Deployment infra (fred-deployment-factory / chart) — separate from this branch.**

Tests added: pod OpenFGA (managed-no-team 403, direct agent_id c3 403 / non-c3 skip),
session-ownership (4), JWT-identity stamping (1), strict-JWT (4), `session_exists` oracle.
Suites green: fred-core 207 / fred-sdk 186 / fred-runtime 386 / control-plane 174 /
fred-agents 33.

**Pre-PR convergence (rev. 2.2, 2026-06-28).**

- [x] **knowledge-flow honors `c3`**: `knowledge_flow_backend/main.py` now calls
      `apply_security_profile` (was missing) — the document plane also fails closed under
      `profile: c3`. C3 now enforced by **control-plane + fred-agents + knowledge-flow**. ✅
- [x] **Chart surfaces the knob**: `deploy/charts/fred/values.yaml` exposes `security.profile`
      (commented, with the c3 contract) on the 3 request-authority blocks; new
      "Security profiles & classification tiers" section in `deploy/README.md`. ✅
- [x] **Self-test fix**: harness sent the bare alias `"personal"` as `runtime_context.team_id`;
      the pod OpenFGA check needs the canonical `personal-<uid>` (control-plane aliases both, the
      pod does not). `usePipelineRun.ts` now canonicalizes via `personalTeamId(GetUserId())`. ✅
- [x] **Frontend generated-client hygiene**: `pipeline/actions.ts` consumes generated
      `ExecutionPreparation` + `RuntimeExecuteRequest` (removed hand-rolled `PreparedExecution`);
      runtime OpenAPI regenerated (OpenAI-compat endpoints dropped, no dangling refs). ✅
- [x] **Docs converged to rev. 2**: `RUNTIME-EXECUTION-CONTRACT.md` (§0–§3 rewritten, §8.11
      supersession entry), `CONTROL-PLANE-PRODUCT-CONTRACT.md`, `ARCHITECTURAL-SECURITY-REPORT.md`
      (rewritten as the current model), `ops/AGENT_POD_RUNTIME_PROTOCOL.md` (§2.3 authorization). ✅
- [ ] **`fred-samples` API-break check**: verified read-only — no break. Pods consume only
      `create_agent_app` (security fully internal); only the sample MCP server calls
      `decode_jwt`/`initialize_user_security` (signatures unchanged). No announcement needed.

---

**History (rev. 1, signed-grant approach — superseded by the Target above).**

RFC: `docs/swift/rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md`. Audit of the
direct browser→runtime SSE grant flow found 7 issues (F1–F7); authorization is
currently enforced only at grant *issuance*, not at execution. Phased, each phase
a testable revertible commit:

- [x] Phase 0 — Baseline (2026-06-27). 5 characterization tests pin current behavior:
      F1 grant unsigned + fabricated grant accepted, F3 audience not checked, F4 team_id
      not checked (`libs/fred-sdk/tests/test_execution_contracts.py::test_char_f1/f3/f4`);
      F2 resolution endpoint gates on global admin — non-admin member refused 403 (too
      strict) AND non-member admin resolves any team's binding 200 (too loose,
      unscoped store.get) (`apps/control-plane-backend/tests/test_main.py::test_char_f2_runtime_resolution_gates_on_global_admin_today`).
      Empirical finding: with security enabled a normal team member IS refused at
      resolution → managed path currently works only for the two global admins (or where
      that check is bypassed). These tests flip to prove-the-fix in Phases 1–3.
- [x] Phase 1 — Enforce `audience` (F3) and `grant.team_id == owner_team_id` (F4)
      (2026-06-27). sdk `validate_for_execution`/`validate_execution_grant` gain
      `expected_audience`; runtime passes its own `platform.audience` (new optional
      `PodPlatformConfig`/`RuntimeConfig` field, opt-in). New `_validate_grant_team_binding`
      rejects (403) team mismatch after resolution on all three execute endpoints.
      Char tests flipped to prove-the-fix + new runtime test
      `test_managed_execution_rejects_grant_with_mismatched_team`. Contract §2.2/§2.4 +
      §8.9 updated. fred-sdk 55 + fred-runtime 375 green, code-quality clean.
- [x] Phase 2 — **Self-contained signed grant (F1 + F2 + per-turn load).** ✅ DONE 2026-06-27.
      2a sdk envelope + resolution claims + `fred-core/security/keyless_signer.py` (f206ca0e);
      2b sign/verify glue (1bc611a9) + CP signs+embeds+JWKS endpoint (c183ea9b); 2c runtime
      verifies signature observe/enforce (48defbf0); 2d enforce runs from the verified grant
      and DROPS the per-turn callback (a19049b2). Local-keypair + CP-served JWKS is the
      first-class path (local Docker Keycloak+SeaweedFS / on-prem); GCP signBlob is the GKE
      option. Tests assert zero control-plane calls in enforce mode. Contract §8.10. The
      original Phase-2 text (kept below for history) described the plan.
      The grant becomes a CP-signed token carrying authz AND resolution (`template_agent_id`,
      `owner_team_id`, inline `tuning`); the runtime verifies the signature locally and runs
      from the grant — **eliminating the per-turn `_resolve_agent_instance` callback**. This
      fixes F2 by elimination: members no longer hit `require_admin` (bug gone), admins lose
      the cross-tenant reach (authz baked in at issuance), and CP per-turn load disappears.
      2a sdk envelope (`key_id`/`jti`/`signature` + resolution claims) + `fred-core/security/
      keyless_signer.py`; 2b CP signs + embeds at `prepare-execution`; 2c runtime verify in
      `observe` (verify + still callback, log mismatch); 2d `enforce` (drop callback). The
      old `require_admin` endpoint stays as operator/CLI inspection only.
- [x] Phase 3 — JWT strictness + fail-closed C3 profile (F5, F6). ✅ DONE 2026-06-27
      (a0bcffba). `SecurityConfiguration.profile='c3'` + `apply_security_profile()`: forces
      strict JWT issuer/audience, refuses startup unless user+m2m enabled and grant signing
      enabled in enforce mode (fail closed). Runtime enforce mode also fails closed when the
      verifier is unavailable. Wired into runtime + control-plane startup.
- [ ] Phase 4 — (deferred) Replay resistance (`jti` one-time resume, token binding) +
      durable audit (F7).

Decisions (rev. 2026-06-27): D1 = asymmetric keyless via GCP IAM `sign_blob` (reuses
FILES-06 pattern; `LocalKeypairSigner` fallback). **D2 REVISED** = trust the signed
self-contained grant and **eliminate the per-turn callback** (supersedes the earlier
"signed grant + live ReBAC re-check", which would keep per-turn CP load and defeat the
offload intent); revocation bounded by ≤5-min TTL. D3 = Phases 0–3 this iteration (Phase 4
deferred). D4 = inline tuning in the grant (fully autonomous runtime). See RFC §10.

F2 severity (deployment fact, 2026-06-27): exactly **two** platform admins exist;
all other users are non-admin. So the `require_admin` resolution callback means the
managed path is **active cross-tenant risk for those two admin accounts** (they can
resolve/execute any team's instance via unscoped `store.get`, beyond their own team
memberships), and is **403-blocking for every normal user** — Phase 0 must establish
how normal-user managed execution currently succeeds at all (runtime `security.user`
state) before Phase 2 replaces the gate with per-user team ReBAC.

Execution: GitHub issue `#1853` → PR `#1857` (base `swift`). Phases 0–3 delivered; awaiting
local-Docker validation (RFC §12) + review.

### 3c.3 - Enrollment Model (Simplification Decision)

The enrollment model is intentionally minimal:

- Every agent advertised by a configured runtime pod is discoverable by every team.
- A team member selects a template from the catalog and enrolls it for their team.
- Enrollment creates a DB-backed `ManagedAgentInstance` record for that team.
- No admin approval, no whitelist, no per-pod or per-team filtering exists at this stage.

Future work (explicitly deferred):

- Admin or config-driven visibility rules (e.g. prevent team X from seeing agent Y)
- Enrollment approval flows

The control-plane configuration remains minimal: only runtime pod references
(`runtime_catalog_sources`). All enrollment data lives in the DB.

---

### 3c.4 Security Position

This phase MUST be designed for a **secured platform posture**.

In particular:

- the browser MUST NOT receive Kubernetes Service DNS names, Pod IPs, namespace-internal URLs, or cluster topology
- runtime pods MUST remain protected by standard platform controls
- control-plane MUST stay the sole authority for:
  - team-scoped eligibility
  - managed agent resolution
  - execution authorization
- runtime pods MUST validate, never decide
- the frontend MUST receive only:
  - team-authorized managed instances
  - ingress-safe relative execution URLs
  - short-lived execution authorization material

This phase MUST avoid weak approaches such as:

- exposing cluster-internal runtime URLs to the frontend
- making the frontend derive routing from K8 internals
- using raw `agent_id` as the main frontend execution identity
- relying on trust-by-network alone without grant validation
- relying on grant-only execution without authenticated user context
- pushing runtime SSE through control-plane as a convenience shortcut

---

### 3c.5 Core Architectural Rule

The frontend MUST NOT resolve runtime pods from a global pod registry on its own.

Instead, the frontend MUST:

1. list team-scoped managed agent instances from control-plane
2. select one `agent_instance_id`
3. call a dedicated control-plane preparation endpoint
4. receive an **opaque ingress-relative execution target**
5. call runtime directly using:
   - the authenticated user bearer token
   - the prepared `ExecutionGrant`

This keeps:

- Kubernetes responsible for routing and exposure
- control-plane responsible for product/tenancy/authorization
- runtime responsible for execution only

---

### 3c.6 Kubernetes And Platform Boundary

Fred code MUST continue to rely on standard Kubernetes/networking primitives for
network reachability and traffic routing.

Relevant platform primitives:

- Kubernetes `Service` provides a stable network endpoint for backend pods
- Ingress or Gateway provides browser-facing HTTP routing to runtime Services
- `NetworkPolicy` provides namespace/pod-level traffic restriction
- standard identity and ingress controls remain platform-managed concerns

Architectural consequence:

- control-plane may know runtime internal `base_url` values for server-side calls
- frontend MUST receive only ingress-safe relative paths
- runtime Services remain internal platform objects, not frontend contract elements
- browser-visible runtime paths are public ingress aliases, not K8 topology

---

### 3c.7 Core Deliverable

A control-plane product/security contract centered on:

- `GET /teams/{team_id}/agent-templates`
- `GET /teams/{team_id}/agent-instances`
- `POST /teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution`

The first two expose the product surface.

The third endpoint is the critical bridge that makes direct frontend-to-runtime
SSE both possible and secure.

---

### 3c.8 Product Identity Rules

#### 1. Agent Template

`AgentTemplate` remains a catalog capability available for enrollment.

Rules:

- `template_id` is the stable product/catalog identity
- `source_agent_id` remains technical/runtime-facing only
- templates are used for enrollment, not direct managed execution

#### 2. Managed Agent Instance

`ManagedAgentInstance` remains the only primary frontend execution identity.

Rules:

- `agent_instance_id` is the primary execution target in the frontend
- the frontend MUST NOT execute using raw `source_agent_id`
- listing and selection flows MUST remain team-scoped

#### 3. Runtime Binding

`RuntimeBinding` remains an internal control-plane concern.

Rules:

- control-plane resolves `agent_instance_id -> runtime binding`
- runtime binding MUST NOT be exposed as raw cluster topology
- frontend consumes only the output projection of execution preparation

---

### 3c.9 New Contract - `ExecutionPreparation`

#### Purpose

`ExecutionPreparation` is the minimal control-plane contract that gives the
frontend everything required to call the correct runtime pod securely, without
learning cluster internals and without requiring control-plane to proxy runtime
streaming.

#### Public Model

`ExecutionPreparation`

Minimum required fields:

- `agent_instance_id`
- `team_id`
- `runtime_id`
- `execution_transport` = `"sse"`
- `execute_url`
- `execute_stream_url`
- `messages_url_template`
- `execution_grant`
- `supports_streaming`
- `supports_hitl`
- `supports_ui_parts`
- `expires_at`

Optional but recommended:

- `runtime_display_name`
- `grant_refresh_required`
- `max_session_idle_seconds`
- `trace_context`

#### URL Rules

The following fields:

- `execute_url`
- `execute_stream_url`
- `messages_url_template`

MUST be:

- relative
- ingress-facing
- opaque to the frontend
- stable for the duration of the prepared execution window

They MUST NOT be:

- `*.svc.cluster.local`
- Pod IPs
- namespace-internal URLs
- direct Service names
- platform topology disclosures

Valid example:

    /runtime/agents-v2/agents/execute/stream

Forbidden example:

    http://agents-v2-svc.fred.svc.cluster.local/runtime/agents-v2/agents/execute/stream

---

### 3c.10 New Endpoint

#### `POST /teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution`

#### Purpose

Prepare one authorized runtime execution context for one managed agent instance.

#### Responsibilities

`control-plane-backend` MUST:

- authenticate the user
- validate team membership / authorization
- validate that `agent_instance_id` belongs to the requested team scope
- validate that the managed instance is enabled and executable
- resolve the runtime binding for this managed instance
- mint or attach a short-lived `ExecutionGrant`
- return only ingress-safe relative runtime URLs
- return only the minimal execution capability flags needed by the frontend

`control-plane-backend` MUST NOT:

- proxy runtime SSE
- execute the request
- transform runtime streaming events
- expose cluster-internal topology

#### Status note

The current implementation already guarantees the control-plane-owned parts of
the lifecycle:

- team enrollment is DB-backed
- managed instance listing is DB-backed
- unbinding is DB-backed

The remaining gap is availability clarity:

- runtime catalog discovery is live
- runtime liveness is not yet projected as a separate explicit managed-instance
  availability state to the frontend
- when a configured runtime pod is down, the failure may surface only on the
  runtime call after `prepare-execution`

---

### 3c.11 Execution Grant Rules

`ExecutionGrant` remains the authoritative runtime execution authorization envelope.

For this phase:

- grant lifetime SHOULD be short
- grant MUST include:
  - `user_id`
  - `team_id`
  - `agent_instance_id`
  - allowed action (`execute`, `resume`)
  - audience
  - issuance time
  - expiry
- grant MUST be verifiable by runtime
- grant MUST NOT contain infrastructure secrets
- grant MUST be scoped narrowly enough for secured platform expectations

Recommended security stance:

- short-lived grant
- audience-bound to the intended runtime surface
- explicit action binding
- reject-on-expiry
- reject-on-team mismatch
- reject-on-instance mismatch

---

### 3c.12 Standard Secure Kubernetes Deployment Pattern

#### Internal runtime exposure

Each runtime pod/app SHOULD be exposed internally through:

- one Kubernetes `Deployment`
- one internal `Service`
- one stable internal server-side `base_url` used by control-plane only

#### External/browser reachability

Browser traffic SHOULD reach runtimes through the standard platform entrypoint:

- Ingress if this is the current platform standard
- Gateway if that is the platform standard target architecture

#### Required URL pattern

Runtime URLs returned to the frontend SHOULD follow one stable ingress-relative
prefix per runtime, for example:

    /runtime/{runtime_id}

Example:

    /runtime/agents-v2/agents/execute/stream

#### Required deployment convention

Runtime applications SHOULD be mounted under the same external prefix they are
served from, so that routing does not depend on fragile rewrite rules.

Example:

- runtime app `base_url`: `/runtime/agents-v2`
- edge route prefix: `/runtime/agents-v2`
- backend Service: `agents-v2-svc`

This keeps the contract simple and explicit.

#### Sidecar / proxy note

Sidecar or service-mesh patterns MAY exist on the platform, but Fred MUST NOT
depend on a custom sidecar protocol as part of its public frontend contract.

If sidecars are present, they remain deployment/runtime concerns under platform
control, not frontend-visible contract elements.

---

### 3c.13 Network Security Requirements

On a secured platform, runtime pods MUST NOT rely on public openness.

Minimum posture:

- ingress to runtime pods SHOULD be restricted using `NetworkPolicy`
- namespace default-deny ingress SHOULD be applied where platform policy allows it
- runtime pod ingress SHOULD be allowed only from:
  - the ingress/gateway controller path
  - explicitly approved control-plane flows if needed
- runtime Services SHOULD remain internal platform objects

---

### 3c.14 Frontend Flow

#### 1. Bootstrap

Frontend calls:

    GET /control-plane/v1/frontend/bootstrap

Used for:

- current user
- current team
- permissions
- feature flags

Bootstrap SHOULD NOT expose full runtime endpoint catalogs for browser-side routing.

#### 2. Team product discovery

Frontend calls:

    GET /control-plane/v1/teams/{team_id}/agent-templates
    GET /control-plane/v1/teams/{team_id}/agent-instances

Used for:

- showing enrollable templates
- showing already-enrolled managed instances

#### 3. Execution preparation

When the user selects one managed instance, frontend calls:

    POST /control-plane/v1/teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution

Receives:

- relative execution URLs
- `ExecutionGrant`
- runtime capability flags

#### 4. Direct runtime SSE execution

Frontend calls:

    POST {execute_stream_url}

with:

- authenticated user bearer token
- `RuntimeExecuteRequest`
- embedded `execution_grant`

#### 5. Runtime history

Frontend reads runtime history directly from runtime using:

    GET {messages_url_template}

This preserves the architecture rule:

- control-plane owns product/session metadata
- runtime owns runtime history

---

### 3c.15 Runtime Validation Requirements

For requests coming from the frontend prepared path, `fred-runtime` MUST validate:

- authenticated user context according to runtime endpoint protection rules
- `ExecutionGrant` integrity
- grant expiry
- audience
- `team_id`
- `agent_instance_id`
- allowed action
- session/checkpoint consistency when applicable

`fred-runtime` MUST reject:

- missing bearer authentication when required by platform policy
- missing grant
- invalid grant
- expired grant
- mismatched audience
- mismatched team
- mismatched managed instance
- invalid resume against unauthorized or non-resumable checkpoint state

This remains consistent with the architectural rule:

- control-plane decides
- runtime validates

---

### 3c.16 Public Contract Rules For This Phase

#### Allowed frontend-visible runtime information

The frontend MAY receive:

- `runtime_id`
- ingress-safe relative execution URLs
- runtime capability flags
- grant expiry
- execution transport info

#### Forbidden frontend-visible runtime information

The frontend MUST NOT receive:

- Service DNS names
- Pod IPs
- cluster-internal hostnames
- internal control-plane resolution data
- platform routing tables
- topology-specific failover logic

---

### 3c.17 Relationship With Existing Phase 3a Contracts

This phase does NOT replace Phase 3a.

It builds on:

- `FrontendBootstrap`
- `AgentTemplateSummary`
- `ManagedAgentInstanceSummary`

The only essential new public contract is:

- `ExecutionPreparation`

This is the correct bridge between:

- control-plane product selection
- frontend transport
- runtime execution

---

### 3c.18 NewScope

#### In Scope

- `ExecutionPreparation` public model
- preparation endpoint in `control-plane-backend`
- secure runtime reachability contract
- ingress-relative runtime URL strategy
- validation rules for runtime execution preparation flow
- deployment convention for runtime `base_url`
- frontend preconditions for Phase 4 SSE work

#### Out Of Scope

- control-plane streaming proxy
- runtime event transformation in control-plane
- custom frontend pod registry logic
- browser visibility into Kubernetes internal endpoints
- replacing Kubernetes routing with Fred code

---

### 3c.19 Tasks

#### A. Freeze `ExecutionPreparation`

- [x] Fix `/agent-instances/{agent_instance_id}/runtime` authorization gap:
      restricted to `require_admin()` — this endpoint is internal-only
- [x] Add `ExecutionPreparation` model in `control-plane-backend`
- [x] Freeze required fields:
  - `agent_instance_id`
  - `team_id`
  - `runtime_id`
  - `execution_transport`
  - `execute_url`
  - `execute_stream_url`
  - `messages_url_template`
  - `execution_grant`
  - `supports_streaming`
  - `supports_hitl`
  - `supports_ui_parts`
  - `expires_at`
- [x] Specify `messages_url_template` as RFC 6570 Level 1 URI Template syntax
      (example: `/runtime/{runtime_id}/agents/sessions/{session_id}/messages`)
- [x] Set `execution_grant.audience` to the ingress-relative runtime prefix
      (example: `/runtime/{runtime_id}`) and document this convention
- [x] Define `ExecutionGrant` signing mechanism:
      current posture (structural validation + Keycloak bearer + user_id correlation)
      is explicitly documented as acceptable without signing in
      `docs/design/ARCHITECTURAL-SECURITY-REPORT.md` §8.
      HMAC signing is the named planned hardening step.
- [x] `AgentTemplateSummary.source_agent_id` kept in public summary:
      the UI needs it to create an enrollment record that maps back to the
      correct agent on the correct pod (`source_runtime_id` + `source_agent_id`)

#### B. Add execution preparation endpoint

- [x] Implement `POST /teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution`
- [x] Enforce Keycloak + OpenFGA checks at control-plane level (via `get_team_by_id`)
- [x] Resolve runtime binding internally
- [x] Return only relative ingress-safe runtime URLs
- [x] Return short-lived execution authorization material (5-minute grant)

#### C. Enforce secure runtime URL convention

- [ ] Adopt one stable ingress-relative runtime prefix convention, for example:
  - `/runtime/{runtime_id}`
- [ ] Update runtime `base_url` conventions to match the exposed prefix
- [ ] Ensure deployment manifests expose runtime endpoints through the standard ingress/gateway path
- [ ] Avoid path rewriting where possible by aligning app `base_url` with external route prefix

#### D. Harden secured deployment posture

- [ ] Ensure runtime Services remain internal-only platform objects
- [ ] Ensure ingress/gateway is the only browser-facing runtime path
- [ ] Add or verify `NetworkPolicy` restrictions for runtime pods
      (Owner: platform/ops. Ref: `deploy/charts/fred/values.yaml`.
      Verify: `kubectl describe networkpolicy -n <namespace>`)
- [ ] Ensure no cluster-internal URLs appear in any frontend-facing payload
- [ ] Ensure runtime grants are short-lived and audience-bound
- [x] Ensure browser-originated runtime execution requires authenticated user bearer token in addition to `ExecutionGrant`
- [x] Enforce bearer-token / grant user_id correlation check in `fred-runtime` execute endpoints
      (see `docs/design/ARCHITECTURAL-SECURITY-REPORT.md` §3 "Correlation Check")

#### E. Regenerate contracts

- [x] Regenerate `apps/control-plane-backend/openapi.json`
- [x] Regenerate frontend `controlPlaneOpenApi.ts`
- [x] Verify the frontend receives typed `ExecutionPreparation`

#### F. Prepare frontend Phase 4 safely

- [ ] Confirm frontend can list managed instances by `agent_instance_id`
- [ ] Confirm frontend can prepare one managed execution target without any K8 topology knowledge
- [ ] Confirm runtime history remains runtime-owned
- [ ] Confirm no control-plane proxy path is introduced

---

### 3c.20 Validation

- [ ] `make code-quality` in `control-plane-backend`
- [ ] `make test` in `control-plane-backend`
- [ ] one team-scoped managed instance can be selected from the frontend product surface
- [ ] `prepare-execution` returns only ingress-relative runtime URLs
- [ ] `prepare-execution` returns a valid short-lived `ExecutionGrant`
- [ ] no frontend-facing payload contains Service DNS, Pod IP, or internal URL
- [ ] runtime can validate one prepared managed execution end-to-end
- [ ] runtime rejects mismatched team or `agent_instance_id`
- [ ] runtime rejects expired or audience-invalid grants
- [ ] runtime rejects execution without valid authenticated user context when required by platform policy
- [ ] runtime remains reachable from the browser only through approved ingress/gateway paths
- [ ] `NetworkPolicy` or equivalent platform controls prevent unintended direct pod access
- [ ] no frontend code is required to know Kubernetes Service names or cluster topology

---

### 3c.21 Exit Criteria

- [ ] frontend can list team-scoped managed agent instances from `control-plane-backend`
- [ ] frontend can list enrollable templates from `control-plane-backend`
- [ ] frontend can obtain a typed `ExecutionPreparation` for one selected `agent_instance_id`
- [ ] `ExecutionPreparation` contains only safe ingress-relative runtime URLs
- [ ] runtime direct SSE is reachable through standard platform routing
- [ ] runtime grant validation is sufficient for secured platform expectations
- [ ] browser-originated runtime execution requires both authenticated user context and `ExecutionGrant`
- [ ] no control-plane streaming proxy is needed
- [ ] Phase 4 can start without redefining routing, identity, or security semantics

---

### 3c.22 Phase 4 Precondition

**Do not start the frontend SSE connector until all of the following are true:**

- [ ] managed agent instance listing is stable
- [ ] execution preparation is implemented and code-generated
- [ ] runtime URL convention is fixed
- [ ] ingress/gateway routing to runtime pods is deployed and verified
- [ ] secure platform controls are in place:
  - authenticated frontend calls
  - short-lived execution grant
  - runtime validation
  - ingress/gateway-only browser path
  - network restriction at pod level
- [ ] no frontend-facing contract leaks Kubernetes internals

---

### 3c.23 Key Rules

- **`agent_instance_id` remains the only primary frontend execution identity**
- **the frontend MUST receive an execution preparation, not infer routing**
- **control-plane decides; runtime validates**
- **browser-visible URLs MUST be ingress-relative and topology-safe**
- **browser-originated runtime execution MUST carry both authenticated user context and `ExecutionGrant`**
- **Kubernetes/Ingress/Gateway handle routing; Fred code handles authorization and business semantics**
- **secured deployment posture is mandatory before Phase 4 starts**

## Phase 3d — Pod Catalog Exposure, Agent Configuration, and Drift Detection

### 3d.1 Goal

Allow team admins to configure each managed agent instance with a specific
subset of tools and a model profile drawn from the pod's own deployment
catalogs (`mcp_catalog.yaml`, `models_catalog.yaml`). Ensure that any
mismatch between a stored instance configuration and the current live pod
catalog is surfaced to the user as a clear, actionable error — not a silent
runtime failure.

**Do not implement** until Phase 3c is fully closed. This phase is the
prerequisite for the agent form's tool-selection and model-picker UI.

---

### 3d.2 Design Principles

- **Pod catalogs are the single source of truth** for what is available at
  runtime. The UI never hardcodes server IDs or model names.
- **Enrollment freezes the selection**, not the catalog. An instance stores
  which server IDs and which model profile the admin chose. The catalog can
  change after enrollment; the stored selection is what gets executed.
- **Catalog drift = clear user error, not silent skip.** If the pod is
  reachable at listing time and a stored server ID or model profile ID no
  longer appears in the live catalog, the instance surfaces a
  `catalog_warnings` list. The UI must show this prominently so the admin
  knows they must delete and recreate the agent.
- **Pod unreachability ≠ drift.** If the pod is down, the instance shows
  `runtime_unavailable`; drift warnings are only emitted when the pod IS
  reachable but the stored IDs are missing from its catalog.
- **No auto-heal.** The platform never silently drops unavailable servers
  or substitutes a fallback model. Broken = visible, always.
- **Keep tuning families separate.** Agent-authored field values stay limited to
  `prompts.*`, `settings.*`, and `chat_options.*`. Model profile selection and
  MCP server selection are platform-owned selectors and must use dedicated typed
  contract fields rather than ad hoc generic tuning keys.

---

### 3d.3 New Runtime Endpoints (fred-runtime)

Two new read-only endpoints on the agent pod. Both require no auth in
no-security mode; in secured mode they use the same m2m token as other
control-plane → pod calls.

#### `GET /agents/mcp-catalog`

Returns the full list of MCP servers declared in `mcp_catalog.yaml`,
including disabled ones, so the control-plane can distinguish
"never configured" from "configured but disabled".

```json
{
  "servers": [
    {
      "id": "mcp-knowledge-flow-mcp-text",
      "name": "mcp.servers.search_documents.name",
      "description": "mcp.servers.search_documents.description",
      "enabled": true,
      "transport": "streamable_http"
    },
    ...
  ]
}
```

Response model: `McpCatalogResponse` (new, in `fred-runtime`).  
Fields per entry: `id`, `name`, `description`, `enabled`, `transport`.  
Do **not** expose `url`, `auth_mode`, or credentials — those are runtime-internal.

#### `GET /agents/model-profiles`

Returns the model profiles declared in `models_catalog.yaml`, grouped by
capability. The frontend uses this to offer a model picker on the agent form.

```json
{
  "profiles": [
    {
      "profile_id": "default.chat.mistral",
      "capability": "chat",
      "description": "Default balanced chat model."
    },
    ...
  ],
  "default_by_capability": {
    "chat": "default.chat.mistral",
    "language": "default.language.mistral"
  }
}
```

Response model: `ModelProfilesResponse` (new, in `fred-runtime`).  
Fields per profile: `profile_id`, `capability`, `description`.  
Do **not** expose `provider`, `base_url`, `api_key`, or raw model settings.

---

### 3d.4 Control-Plane Aggregation Changes

#### Extended `AgentTemplateSummary`

Add two new fields populated at template-listing time by calling the two
new pod endpoints alongside the existing `/agents/templates` call:

```python
available_mcp_servers: list[ManagedMcpServerRef]   # already exists — no change
available_model_profiles: list[ManagedModelProfileRef]  # NEW
```

`ManagedModelProfileRef` (new, in `control_plane_backend/config/models.py`):

```python
class ManagedModelProfileRef(BaseModel):
    profile_id: str
    capability: str          # "chat" | "language"
    description: str = ""
    is_default: bool = False
```

The control-plane fetches `/agents/mcp-catalog` and `/agents/model-profiles`
in the same request fan-out as `/agents/templates` for each enabled
`runtime_catalog_source`. Failures on the new endpoints are logged and
result in empty lists — template discovery itself must not fail.

#### Extended create/update request bodies

`CreateAgentInstanceRequest` gains two optional fields:

```python
mcp_server_ids: list[str] | None = None
# If None → inherit the template default selection (all declared servers active).
# If []   → activate no MCP servers.
# If list → use exactly this subset (validated against available_mcp_servers).
# Unknown IDs are rejected with HTTP 422, not silently dropped.

mcp_config_values: dict[str, dict[str, TuningValue]] | None = None
# Dedicated per-server MCP configuration keyed by server id then config-field key.
# Only selected or inherited-active servers may be configured.
# Unknown server ids or config keys are rejected with HTTP 422.

model_profile_id: str | None = None
# If None → runtime uses its default_by_capability["chat"] profile.
# If present → validated against available_model_profiles; 422 on unknown.
```

`UpdateAgentInstanceRequest` gains the same two fields with patch semantics:

- omitted field → leave current value unchanged
- `mcp_server_ids = null` → reset to template default selection
- `mcp_server_ids = []` → activate no MCP servers
- `mcp_server_ids = [...]` → activate exactly that subset
- `mcp_config_values = null` → clear all stored MCP config
- `mcp_config_values = {...}` → replace the stored MCP config map

Validation rule: if an ID is supplied that does not appear in the live
template's available catalog, the control-plane returns HTTP 422 with a
message naming the unknown ID. Do **not** create or update the instance.

#### Enrollment service

When creating or patching an instance, the service:

1. Fetches the live template catalog to validate supplied IDs.
2. Stores the resolved `mcp_server_ids` and `model_profile_id` in
   `ManagedAgentTuning` (new fields: `selected_mcp_server_ids`,
   `mcp_config_values`, `model_profile_id`).
3. The runtime receives these in `ExecutionPreparation` tuning and applies
   them in `_apply_runtime_tuning`.

---

### 3d.5 Drift Detection

When `GET /teams/{team_id}/agent-instances` is called, the control-plane:

1. Calls `GET /agents/mcp-catalog` and `GET /agents/model-profiles` on the
   bound pod (same fan-out, cached per request).
2. For each instance, compares `stored.selected_mcp_server_ids` against the
   live catalog's `enabled` servers:
   - any stored ID absent from the live catalog → add to `catalog_warnings`
   - any stored `model_profile_id` absent from the live catalog →
     add to `catalog_warnings`
3. If the pod is unreachable (HTTP error / timeout), sets
   `runtime_status = "unavailable"` and emits **no** drift warnings.

Extended `ManagedAgentInstanceSummary`:

```python
runtime_status: Literal["ok", "unavailable"] = "ok"
catalog_warnings: list[str] = []
# e.g. ["MCP server 'mcp-knowledge-flow-corpus' is no longer in the pod catalog",
#        "Model profile 'default.chat.mistral' is no longer in the pod catalog"]
```

The UI contract for warnings:

- `runtime_status = "unavailable"` → show a "pod unreachable" badge, no action needed
- `catalog_warnings` non-empty → show a prominent warning banner on the AgentCard
  with message: "This agent's configuration is out of sync with the pod catalog.
  Delete and recreate to restore it." — no edit button, no chat link.
- Both conditions can coexist.

---

### 3d.6 Runtime Execution Side

`_apply_runtime_tuning` (fred-runtime) extended to:

- filter `default_mcp_servers` to only the IDs in `tuning.selected_mcp_server_ids`
  (when not `None`; `None` = keep template default selection, `[]` = activate none)
- select the model profile by `tuning.model_profile_id` via the model router
  (when set; unset = keep current default routing)

---

### 3d.7 Tasks

**fred-runtime:**

- [x] Add `McpCatalogResponse` model and `GET /agents/mcp-catalog` endpoint
- [ ] Add `ModelProfilesResponse` model and `GET /agents/model-profiles` endpoint — deferred
- [x] Extend `_apply_runtime_tuning` to filter MCP servers by `selected_mcp_server_ids` (model profile deferred)
- [x] `make code-quality && make test` in `fred-runtime`

**control-plane-backend:**

- [ ] Add `ManagedModelProfileRef` to `config/models.py` — deferred
- [ ] Extend `AgentTemplateSummary` with `available_model_profiles` — deferred
- [x] Extend `CreateAgentInstanceRequest` / `UpdateAgentInstanceRequest` with
      `mcp_server_ids` (`model_profile_id` deferred)
- [x] Extend `ManagedAgentTuning` with `selected_mcp_server_ids` (`model_profile_id` deferred)
- [x] Extend `ManagedAgentTuning` with dedicated `mcp_config_values`
- [x] Extend `ManagedAgentInstanceSummary` with `runtime_status` and
      `catalog_warnings`
- [x] Extend `ManagedAgentInstanceSummary` / `ExecutionPreparation` with
      `mcp_config_values` and typed `effective_chat_options`
- [x] Enrollment service: validate supplied IDs against live catalog, store
      selection, reject unknown IDs with 422
- [x] Validate and persist per-server MCP config; reject unknown server ids and
      config keys with 422
- [x] Drift detection in `list_managed_agent_instances`: compare stored IDs
      against live catalog per instance
- [x] Regenerate `controlPlaneOpenApi.ts`
- [x] `make code-quality && make test` in `control-plane-backend`

**frontend:**

- [x] Replace read-only MCP list in `AgentFormBody` with a checkbox multi-select
      populated from `AgentTemplateSummary.mcp_servers`
- [ ] Add model profile picker to `AgentFormBody` — deferred
- [x] Wire `mcp_server_ids` into `AgentFormPayload` and the create/update mutation calls
      (`model_profile_id` deferred)
- [x] `AgentCard`: show "pod unreachable" badge when `runtime_status = "unavailable"`
- [x] `AgentCard`: show MCP drift warning banner when `catalog_warnings` is non-empty
- [x] `McpServerCard` reads/writes per-server `configValues` keyed by `config_fields[].key`; `AgentFormBody` passes server-scoped slices via `mcpConfigValues`; `AgentFormModal` stores `mcpConfigValues` separately from `tuningValues` and preserves tri-state selection (`[]` ≠ `null`); `TeamAgentsPage` forwards `mcp_config_values` in create/update requests (2026-05-06)
- [x] `useChatSse` exposes `effectiveChatOptions` captured from each `prepare-execution` response; `AgentOptionsPanel` gates library/search/scope sections on the options prop; `ManagedChatPage` syncs search defaults from agent config on first turn (2026-05-06)
- [x] `tsc --noEmit` + `npm run build` pass in frontend

---

### 3d.8 Validation

- [ ] `GET /agents/mcp-catalog` returns all servers from `mcp_catalog.yaml`
      (enabled and disabled), without URLs or credentials
- [ ] `GET /agents/model-profiles` returns all profiles from `models_catalog.yaml`
      with `is_default` correctly set from `default_by_capability`
- [ ] Creating an instance with a valid subset of `mcp_server_ids` stores the
      subset and the runtime executes with only those servers active
- [ ] Creating an instance with `mcp_server_ids = []` stores "activate none"
      and the runtime executes with no MCP servers active
- [ ] Creating an instance with an unknown `mcp_server_id` returns HTTP 422
      naming the unknown ID
- [ ] Creating or patching an instance with unknown `mcp_config_values` server
      ids or config keys returns HTTP 422 naming the offending entry
- [ ] `prepare-execution` returns typed `effective_chat_options` resolved from
      `mcp_config_values` plus any agent-authored chat affordances
- [ ] After disabling a server in `mcp_catalog.yaml` and restarting the pod,
      a previously enrolled instance that used that server shows a `catalog_warnings`
      entry in `GET /teams/{team_id}/agent-instances`
- [ ] The drift warning renders on `AgentCard` with the correct message; edit
      and chat links are disabled for that agent
- [ ] When the pod is down, `runtime_status = "unavailable"` and
      `catalog_warnings` is empty (no false drift alarms)
- [ ] `make code-quality && make test` pass in `fred-runtime` and
      `control-plane-backend`

### 3d.9 Prompt Safety — Safe Rendering + Validation at Persistence

**RFC**: `docs/rfc/PROMPT-SAFETY-RFC.md` — Slices A + B + C implemented (2026-05-07).

**Problem**: `str.format_map()` in `react_prompting.py` crashed on `{toto.toto}`
(AttributeError) and code braces `{ ... }` (ValueError). No validation happened
at save time — the agent was created successfully but broke on the first message.

**Implemented (2026-05-07)**:

- [x] `fred_sdk.contracts.prompt_utils` — new module: `PROMPT_SAFE_TOKENS` canonical
      registry, `PromptTemplateError` model, `validate_prompt_template()` validator
- [x] `fred_runtime/react/react_prompting.py` — renderer replaced: `str.format_map()` +
      `_LiteralFriendlyDict` removed; regex-based substitution replaces only
      `{simple_identifier}` patterns present in the token map; code braces and dotted
      notation are preserved as literals and never crash
- [x] `control_plane_backend/product/service.py` — `_validate_tuning_field_values`
      calls `validate_prompt_template` for `"prompt"` type fields; any unknown
      `{token}` → 422 before DB write; error message names the bad pattern and lists
      all supported tokens
- [x] 26 offline tests added: `fred_sdk/tests/test_prompt_utils.py` (clean/invalid/
      edge cases) + 4 new tests in `control_plane_backend/tests/test_main.py`
      (create-then-reject, valid tokens, code braces, patch rejection)
- [x] `make code-quality && make test` pass in `fred-sdk` (189), `fred-runtime` (302),
      `control-plane-backend` (106)

**Supported template tokens** (canonical whitelist — single source of truth in
`PROMPT_SAFE_TOKENS`):

| Token                 | Injected value                               |
| --------------------- | -------------------------------------------- |
| `{today}`             | ISO-8601 date at execution time              |
| `{response_language}` | Human-readable language (English, français…) |
| `{session_id}`        | Active session identifier                    |
| `{user_id}`           | Authenticated user identifier                |
| `{agent_id}`          | Agent definition identifier                  |

**Remaining (next slices, in order)**:

---

**Slice PROMPT-02 — backend CRUD (PROMPT-02) · Done 2026-05-08 — Codex**

- [x] `PromptRow` ORM model (`prompt_models.py`) — `team_id`, `name`, `description`, `text`, `created_by`, timestamps
- [x] `PromptStore` full CRUD (`prompts/store.py`)
- [x] Alembic migration `9c4e1a2b3d4f_add_prompt_table.py`
- [x] Pydantic schemas: `PromptSummary`, `PromptDetail`, `CreatePromptRequest`, `UpdatePromptRequest`
- [x] API endpoints: `POST/GET /teams/{id}/prompts`, `GET/PUT/DELETE /teams/{id}/prompts/{pid}`

---

**Slice PROMPT-03 — backend extension: versioning + analytics + context integration (PROMPT-03) · Done 2026-05-10 — Dimitri**

**Design**: `docs/swift/design/PROMPTS.md` — current prompt-system authority for shipped slices.

- [x] Alembic migration: add `version int DEFAULT 1`, `import_count int DEFAULT 0`,
      `session_count int DEFAULT 0`, `score float NULLABLE`, `avg_input_tokens int NULLABLE`,
      `avg_output_tokens int NULLABLE` to `prompt` table
- [x] Alembic migration: add `prompt_refs_json TEXT NULLABLE` to `agent_instance` table
- [x] Alembic migration: add `context_prompt_id varchar NULLABLE` to `session_metadata` table
- [x] `PromptStore.update()` auto-increments `version` on every call
- [x] `PromptStore.increment_import_count(prompt_id, team_id)` — atomic counter update
- [x] `PromptStore.increment_session_count(prompt_id, team_id)` — atomic counter update
- [x] `PromptStore.list_context_prompts(personal_team_id, team_id)` — union query returning `ContextPromptSummary`
- [x] `ProductService` session PATCH: accept `context_prompt_id`; call `increment_session_count`
- [x] `ProductService` prepare_execution: resolve `context_prompt_text` from `context_prompt_id`
- [x] New endpoint: `GET /teams/{id}/prompts/context` → union personal + team, ordered by `session_count DESC`
- [x] New endpoint: `POST /teams/{id}/prompts/{pid}/promote` → copy-by-value to target team; 409 on name conflict
- [x] New endpoint: `PATCH /teams/{id}/prompts/{pid}` → score update only (range 0.0–5.0)
- [x] Extended schemas: `PromptSummary` gains `version`, `import_count`, `session_count`, `score`, `avg_input_tokens`, `avg_output_tokens`
- [x] New schemas: `ContextPromptSummary`, `PromptScoreUpdateRequest`, `PromptPromoteRequest`
- [x] `ExecutionPreparation` response gains `context_prompt_text: str | null`
- [x] `controlPlaneOpenApi.ts` regenerated
- [x] `make code-quality && make test` in `control-plane-backend`
- Note: `prompt_refs` write on agent import deferred to PROMPT-04 (frontend carries the ref in UpdateAgentInstanceRequest)

---

**Slice PROMPT-04 — frontend: PromptsPage + AgentFormModal (PROMPT-04)**

_Depends on: PROMPT-03 (OpenAPI regenerated)_

- [x] `PromptsPage` — core CRUD (2026-05-10, Dimitri)
  - table: name, description, version, score columns
  - create/edit modal: name (required), description, text textarea
  - delete with confirmation dialog
  - deferred: score star picker, "Promote to team" action, import_count/session_count/updated_at columns
- [x] Route + nav entry for `PromptsPage` (2026-05-10, Dimitri)
- [ ] `AgentFormModal` — `[Import from library]` button on every `prompt`-type field
  - `PromptPickerModal`: shows team library (name, version, session_count, score), search by name, preview panel, `[Use]` → copies text + stores `prompt_ref`
- [ ] `AgentFormModal` — `[Save as prompt]` button on every `prompt`-type field
  - `SavePromptModal`: name + description → `POST /teams/{id}/prompts`
- [ ] `AgentFormModal` — version drift badge when `prompt_ref` exists:
  - version matches current → green "Imported from [name] v2"
  - version stale → amber "Imported from [name] v2 — current is v5" + `[Review]` action
- [ ] `AgentFormModal` — inline 422 error list below each prompt textarea
- [x] `tsc --noEmit` + Prettier pass (2026-05-10, Dimitri)

---

**Slice PROMPT-05 — multi-prompt chat context picker (PROMPT-05) · Done 2026-06-19 — Dimitri**

_Depends on: PROMPT-03 · Execution: branch `1779-fully-wire-prompts-in-the-chat-ui-page` · Contract: [PROMPTS.md](../design/PROMPTS.md) §5 + CONTROL-PLANE-PRODUCT-CONTRACT §13_

Backend (multi-prompt — supersedes the single `context_prompt_id` design):

- [x] Ordered association table `session_context_prompts` (Alembic `e7f8a9b0c1d2`; backfills scalar → `position=0`, drops `session_metadata.context_prompt_id`)
- [x] `UpdateSessionRequest` / `SessionListItem`: `context_prompt_id` → `context_prompt_ids: list[str]` (full ordered replacement; `[]`/present-null clears; absent leaves unchanged via `model_fields_set`)
- [x] `prepare_execution` resolves attached ids in order (library + `default:{cat}`), skips stale, concatenates `\n\n` into existing scalar `context_prompt_text` (fred-sdk/fred-runtime untouched)
- [x] `session_count` increments on **first attach** only; `GET /prompts/context` gains `category`
- [x] Store + endpoint unit tests; `make test` (167) + `make code-quality` green

Frontend:

- [x] `Prompts` row in `SearchConfig` (always shown) → multi-select `ContextPromptPicker` (personal/team/default groups, category icon, score stars, usage count)
- [x] Source: `GET /teams/{team_id}/prompts/context` (union personal + team + defaults)
- [x] Active prompts as removable `ContextPromptChips` in composer `aboveTextSlot`; selection → `PATCH /sessions/{id} { context_prompt_ids }`; empty list clears
- [x] Rehydrate pills from `SessionListItem.context_prompt_ids` on session open; `useChatSse` passes `session_id` to `prepare-execution`
- [x] Unit tests for `ContextPromptPicker` (groups/selection/stars/empty + pure `nextContextPromptSelection`) and `ContextPromptChips`
- [x] `tsc --noEmit` + Prettier pass; 253 vitest tests green

---

**Slice D-F — token cost KPI integration (PROMPT-07) · DEFERRED**

_Depends on: EVAL-01 evaluation track + fred-core KPI store changes (coordinate with Simon)_

- [ ] Add `context_prompt_id` label to KPI turn events in `fred-core` KPI store
- [ ] Add `agent_prompt_version` label to KPI turn events (correlates system prompt version)
- [ ] Background aggregation job or Langfuse query → writes `avg_input_tokens` / `avg_output_tokens` to `PromptRow`
- [ ] Requires its own RFC amendment before implementation starts
- Improvement RFC: [`PROMPT-SYSTEM-HARDENING-RFC.md`](../rfc/PROMPT-SYSTEM-HARDENING-RFC.md)
- Fields `avg_input_tokens` / `avg_output_tokens` exist in DB and schema; UI shows "N/A" until this lands.

### 3d.10 Prompt Marketplace — Global Published Prompts

**Goal**: after 3d.9 lands, expose a global prompt catalog without conflating
team library records and marketplace records.

**Design rules**:

- `Prompt` and `PublishedPrompt` are separate control-plane resources
- team prompt → marketplace is an explicit publish-by-copy flow
- editing or deleting a team prompt must never silently mutate already-published
  marketplace entries or existing agent instances
- importing from the marketplace is copy-based, not a live binding

**Tasks**:

- [ ] Freeze typed published-prompt contracts (`PublishedPromptSummary`,
      `PublishedPromptDetail`, publish/unpublish request surface)
- [ ] Add the minimal control-plane publish + list/detail + unpublish surface
- [ ] Add a frontend global prompt marketplace page
- [ ] Add `Publish to marketplace` from the team/personal `Prompts` page
- [ ] Add marketplace import into the prompt-management flow after the read surface lands

**Starts only after**: 3d.9 prompt CRUD + dedicated `Prompts` page +
`AgentFormModal` import/save ergonomics are merged.

---

### 3d.11 Fred Team Configuration — RFC-First Track

**Goal**: define team configuration as a first-class Fred product surface before
starting implementation work. This track must freeze ownership, policy objects,
routing semantics, prompt-library scope, and implementation sequencing first.

**Direction RFC set**:

- `docs/swift/rfc/FRED-TEAM-CONFIG-RFC.md`
- `docs/swift/rfc/TEAM-PLATFORM-POLICY-RFC.md`
- `docs/swift/rfc/TEAM-ROUTING-POLICY-RFC.md`
- `docs/swift/design/PROMPTS.md` for current prompt-library scope
- `docs/swift/rfc/PROMPT-SYSTEM-HARDENING-RFC.md` for follow-up prompt hardening

#### TEAM-01 — RFC set and backlog sequencing

**Owner**: Dimitri

- [x] Create one umbrella RFC for team configuration ownership, product objects,
      authorization boundaries, and sequencing
- [x] Create one RFC for team platform policy
- [x] Create one RFC for team routing policy
- [x] Consolidate prompt-library scope into the current prompt design doc and
      track remaining governance hardening in the prompt hardening RFC
- [x] Add the implementation breakdown below before any product work starts

**Hard rule**: TEAM-02 through TEAM-07 do not start until TEAM-01 is reviewed by
the team.

#### TEAM-02 — Authorization hardening prerequisites

**Goal**: fix the existing team-scoped authorization gaps before layering new
configuration UI and policy writes on top.

- [ ] Require explicit team write permissions on agent-instance writes
- [ ] Require explicit team write permissions on prompt CRUD, prompt score, and
      prompt promotion
- [ ] Require explicit team authorization on session list/detail routes
- [ ] Remove unscoped personal-prompt lookups from auth-sensitive paths
- [ ] Add owner / manager / member / public-team tests for the corrected
      behavior

#### TEAM-03 — Team platform policy product surface

**Goal**: store platform-enforced team guardrails as a typed control-plane
object. Full model specified in `docs/swift/rfc/TEAM-PLATFORM-POLICY-RFC.md`.

- [ ] Add `TeamPlatformPolicy` Pydantic model to `fred-core` (storage, ingestion,
      size, deletion_retention, model_guardrails, tool_guardrails)
- [ ] Add `TeamPolicyDefaults` to `configuration.yaml` schema (separate `regular`
      and `personal` blocks)
- [ ] Add `team_platform_policy` persistence store in control-plane
- [ ] `GET /teams/{team_id}/platform-policy` — returns resolved policy
      (deployment default merged with team override)
- [ ] `PATCH /teams/{team_id}/platform-policy` — full replacement; owner only
- [ ] Validate positive limits, unique allowlists, deployment-ceiling constraints,
      and `team_storage_bytes_total >= max_user_object_bytes_total`
- [ ] Reject `max_users != 1` writes on personal teams
- [ ] Reject policy writes that would invalidate already stored team
      configuration without remediation
- [ ] `POST /control-plane/v1/teams` — create team, assign team admin, write
      initial platform policy (atomic: Keycloak group + DB row + ReBAC relations)
- [ ] Personal team auto-creation uses `personal` defaults with immutable
      `max_users = 1`

#### TEAM-04 — Platform policy enforcement

**Goal**: make team platform policy effective at runtime and upload boundaries.

- [ ] Enforce `storage.max_object_upload_bytes` on team-scoped object uploads
- [ ] Enforce `storage.max_user_object_bytes_total` before persisting new
      objects
- [ ] Enforce `ingestion.max_source_file_bytes` before ingestion temp-file
      creation
- [ ] Enforce `ingestion.max_batch_file_count` on multi-file ingestion requests
- [ ] Enforce model-profile and MCP-server allowlists during managed-agent
      configuration
- [ ] Return explicit product errors for policy violations

#### TEAM-05 — Team routing policy

**Goal**: expose one simple team-owned routing surface based on team defaults
and operation overrides.

- [ ] Add `TeamRoutingPolicy` persistence and typed store
- [ ] Add `GET /teams/{team_id}/routing-policy`
- [ ] Add `PATCH /teams/{team_id}/routing-policy`
- [ ] Validate all referenced profiles against `TeamPlatformPolicy`
- [ ] Extend execution preparation with a team routing snapshot
- [ ] Extend runtime resolution to merge team snapshot over pod deployment
      defaults
- [ ] Fail closed on unknown or drifted profile IDs

#### TEAM-06 — Prompt-library scope and governance realignment

**Goal**: make personal prompts truly personal and shared team prompts truly
team-governed.

- [x] Personal prompts stored under `personal-{uid}` — full isolation via CTRLP-10 team routing
- [x] `/teams/personal/prompts` route family works; `"personal"` alias resolved server-side to `personal-{uid}`
- [x] Prompt CRUD endpoints use `team.id` (resolved canonical ID) — no raw path parameter reaches the DB
- [ ] Align prompt score and promotion authorization with manager / owner curation
- [ ] Implement `prompt_refs` write / clear semantics on agent import
- [ ] Increment `import_count` when a library prompt is imported into an agent
- [ ] Add full tests for personal-versus-team prompt visibility and writes

#### TEAM-06b — Prompt library UX (delivered 2026-06-02)

**Goal**: make the prompt library page discoverable, categorised, and useful on first visit.

- [x] `PromptCategory` enum (9 functional categories) — backend source of truth, OpenAPI generated
- [x] `PromptSummary` extended: `category`, `emoji`, `tags`, `text_preview`, `is_default`
- [x] Alembic migrations: `c5d6e7f8a9b0` (emoji + tags), `d6e7f8a9b0c1` (category)
- [x] System default prompts: 9 injected at query time, translated per `?lang=fr/en`, never stored per-user
- [x] `FieldSpec` / `AgentDefinition`: `description_by_lang` + `default_by_lang` — bilingual agent prompt defaults
- [x] `GeneralAssistantDefinition`: FR/EN system prompt and description, `required=False`
- [x] `CategoryPicker` component — 3-col grid, 6 visible + expand, selected state per spec
- [x] `PromptCard` redesign — category icon + colour, description body, session_count + author footer
- [x] `PromptsPage`: search bar (constrained 360px, Material icon), category filter chips (+N expand), 3-col grid, read-only modal for defaults, i18n modal titles

#### TEAM-07 — Frontend team configuration and prompt UX

**Goal**: expose the frozen backend contracts through explicit UI only after the
policy and authorization layers are stable.

- [ ] Platform admin: team creation page (`/admin/teams/new`) — name, admin user
      picker, optional platform policy overrides
- [ ] Platform admin: team settings page (`/admin/teams/{id}/settings`) — full
      `TeamPlatformPolicy` editable + `TeamRoutingPolicy` read-only
- [ ] Team admin: team settings page (`/settings/team`) — `TeamPlatformPolicy`
      read-only panel + `TeamRoutingPolicy` editable panel
- [ ] Add prompt-library improvements in agent creation (`prompt_refs`, drift,
      import/save ergonomics)
- [ ] Align session context picker with personal-plus-team prompt visibility
- [ ] Ensure frontend permissions match backend-enforced role boundaries
- [ ] Add tags UI to prompt create/edit form (tags field removed from form for now)
- [ ] Promote prompt from default to personal (copy-on-edit flow)

**Do not start** until TEAM-02 through TEAM-06 have frozen the backend
contracts.

_(Team data-governance console — retention + governed evaluation — folded into the
single 2.0.2 RGPD-ready increment: see §6.4.H Workstream B and
`docs/swift/rfc/FRED-2.0.2-RGPD-READY-RFC.md`.)_

### 3d.12 Dynamic frontend routing for discovered runtimes — **CTRLP-09**

- **Status:** proposed — RFC written, implementation not started
- **Owner:** Simon
- **RFC:** `docs/swift/rfc/DISCOVERED-RUNTIME-ROUTING-RFC.md`

**Problem:** `platform.runtime_catalog_sources` is already enough for
control-plane template discovery and `prepare-execution`, but local frontend
execution still depends on hardcoded reverse-proxy prefixes in
`apps/frontend/vite.config.ts`. A newly configured runtime such as
`dt-agents` (`ingress_prefix: /dt/agents/v1`) can appear in the frontend agent
catalog yet remain non-executable until a developer patches the frontend proxy
map manually.

**Frozen constraints:**

- `platform.runtime_catalog_sources` stays the single product-side source of
  truth for runtime exposure
- control-plane must not proxy SSE execution traffic
- frontend bootstrap must not become a runtime-routing registry
- onboarding a new runtime prefix must not require a frontend code edit

**Tasks:**

- [ ] Freeze the config-driven routing approach in
      `DISCOVERED-RUNTIME-ROUTING-RFC.md`
- [ ] Generate local Vite proxy rules from enabled
      `runtime_catalog_sources[*].ingress_prefix` entries instead of maintaining
      a handwritten prefix list
- [ ] Match exact `ingress_prefix` values (for example `/dt/agents/v1`) instead
      of relying on manually curated top-level shorthands such as `/dt`
- [ ] Fail fast on duplicate or overlapping generated ingress prefixes
- [ ] Document the external-runtime local development workflow in
      `docs/swift/platform/PLATFORM_RUNTIME_MAP.md`
- [ ] Decide whether `apps/frontend/dockerfiles/docker-entrypoint.sh` ships in
      the same slice or as an explicit follow-up

**Validation:**

- [ ] Adding a new runtime source with a unique `ingress_prefix` requires no
      edit to `apps/frontend/vite.config.ts`
- [ ] Managed template discovery and managed execution both work for a
      non-first-party runtime such as `dt-agents`
- [ ] Existing first-party prefixes (`/fred/agents/v2`,
      `/samples/agents/v1`) continue to execute correctly
- [ ] No control-plane endpoint proxies SSE traffic

---

## Phase 4 - Frontend SSE Connector

### Goal

Replace WebSocket chat transport with authenticated HTTP SSE using the
control-plane-prepared execution path.

### Core Rule

Phase 4 MUST consume `ExecutionPreparation`.

The frontend MUST NOT:

- infer runtime routing from bootstrap
- construct runtime URLs from pod metadata
- know Kubernetes Service names
- know cluster-internal topology

The frontend MUST:

- select a team-scoped managed `agent_instance_id`
- obtain `ExecutionPreparation` from control-plane
- call runtime directly using the prepared ingress-relative URLs
- send:
  - authenticated user bearer token
  - `RuntimeExecuteRequest`
  - embedded `ExecutionGrant`

### Tasks

- [x] Create a new chat transport hook `useChatSse` (`apps/frontend/src/hooks/useChatSse.ts`)
- [x] Use `fetch()` streaming, not `EventSource`
- [x] Call `POST /teams/{team_id}/agent-instances/{agent_instance_id}/prepare-execution` before runtime SSE execution
- [x] Send runtime requests to the prepared `execute_stream_url`
- [x] Preserve `session_id` continuity (passed in; bound from `turn_persisted`)
- [x] Send `resume_payload` for HITL resume (via `sendHitlResume()`)
- [x] Parse SSE frames into typed runtime events
- [x] Map runtime events to the frontend message timeline (`assistant_delta`, `final`, `tool_call`, `tool_result`, `turn_persisted`, `node_error`, `awaiting_human`)
- [x] Preserve existing HITL UI behavior (`AwaitingHumanRuntimeEvent` → `AwaitingHumanEvent` adapter)
- [x] Preserve `GeoPart` rendering (ui_parts forwarded as `ChatMessage.parts`)
- [x] Preserve sources / token usage rendering (mapped in `final` → `ChatMetadata`)
- [x] Ensure bearer authentication is forwarded on runtime calls
- [x] Ensure `ExecutionGrant` is attached on runtime calls
- [x] Use `agent_instance_id` when the user selected a managed agent — implemented in
      `ManagedChatPage` (`apps/frontend/src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`),
      which gets `agentInstanceId` from URL params and passes it to `useChatSse`.
      `TeamAgentsPage` lists enrolled instances and links to `/team/:teamId/managed-chat/:agentInstanceId`.
      Route registered in `apps/frontend/src/common/router.tsx`. **Not wired into legacy `ChatBot.tsx` by design.**
- [x] Ensure history loading uses the prepared runtime history URL pattern —
      `ManagedChatPage` calls `prepare-execution` on mount when `?session=<id>` is in URL,
      expands `{session_id}` in `messages_url_template`, fetches history with bearer token.
      `session_id` is generated upfront before first send and persisted in URL query params.

### Frontend files

- `apps/frontend/src/hooks/useChatSse.ts` — SSE transport hook
- `apps/frontend/src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx` — managed chat UI
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/TeamAgentsPage.tsx` — agent enrollment + selection
- `apps/frontend/src/common/router.tsx` — route definitions

### Validation

- [x] frontend build passes
- [ ] one normal streamed answer works end-to-end via `ManagedChatPage`
- [ ] one HITL choice flow works
- [ ] one HITL free-text flow works
- [ ] one `GeoPart` map renders correctly
- [x] frontend does not derive runtime routing from bootstrap or K8 metadata
- [x] runtime execution uses prepared ingress-relative URLs only
- [x] runtime execution forwards both bearer auth and `ExecutionGrant`

## Phase 5 - Frontend Adaptation

### Goal

Converge the frontend on one coherent bootstrap, identity, permissions, and
managed-agent model before continuing with page-level fixes.

### Reference

See [`FRONTEND-BACKLOG.md`](./FRONTEND-BACKLOG.md) for the dedicated frontend
plan.

### Initial Priority

The first required operating mode for Phase 5 is:

- frontend boots without `agentic-backend`
- no-security mode works cleanly
- only the `personal` team is assumed
- control-plane bootstrap becomes the application source of truth
- managed execution keeps using prepared runtime access

## Current Status

| Phase                              | State                         | Notes                                                                                                                                                                                                                   |
| ---------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0 – Direction RFC                  | ✓ Complete                    |                                                                                                                                                                                                                         |
| 1 – Runtime contracts              | ✓ Complete                    | `fred-sdk` + `fred-runtime`                                                                                                                                                                                             |
| 2 – OpenAPI / codegen              | ✓ Complete                    | `runtimeOpenApi.ts` generated                                                                                                                                                                                           |
| 3a – Control-plane product surface | ✓ Complete                    | bootstrap, templates (+ `mcp_servers`), instances endpoints                                                                                                                                                             |
| 3b – Backend completeness gate     | Code ✓; validation items open | Run in parallel — not blocking Phase 4                                                                                                                                                                                  |
| 3c – Execution preparation         | Partial                       | A + B + C + D + E all done; ingress URL convention + deployment hardening remain (parallel, non-blocking). `AgentTuning.values` forwarding + `prompts.system` application in `_apply_runtime_tuning` done (2026-05-04). |
| 4 – Frontend SSE                   | ✓ Complete                    | `useChatSse` + `ManagedChatPage` + `TeamAgentsPage`; session_id upfront; history from `messages_url_template`; build passes                                                                                             |
| 5 – Frontend adaptation            | In progress                   | FRONT-01 bootstrap ✓; FRONT-02 no-security baseline ✓; FRONT-03 managed agent surface ✓; FRONT-04 session/chat convergence ✓ — see `FRONTEND-BACKLOG.md`                                                                |

### Phase 3c Remaining

Items 2 and 3 are hardening work that can run in parallel with Phase 4. Item 1 is complete.

1. ~~**DB enrollment endpoint**~~ ✓ **Done**
   - DB schema + migration: `alembic/versions/e1f2a3b4c5d6_add_agent_instance.py`
   - `POST /teams/{team_id}/agent-instances` implemented in `product_controller.py`
   - `DELETE /teams/{team_id}/agent-instances/{id}` implemented
   - `ApplicationContext.get_agent_instance_store()` is DB-backed via `AgentInstanceStore`
   - Tests cover create, delete, team-scope enforcement, malformed template_id, unknown runtime

2. **Runtime ingress URL convention** (hardening, parallel)
   - Align `base_url` and ingress prefix to `/runtime/{runtime_id}` pattern
   - Currently using `/agentic/v1` which works but does not follow the intended convention

3. **Deployment hardening** (ops, parallel)
   - NetworkPolicy for runtime pods
   - Verify no cluster-internal URLs leak to browser

### Phase 4 Gate

Phase 4 is fully unblocked. All gate criteria are met.

- [x] `ExecutionPreparation` endpoint implemented and code-generated
- [x] Runtime validates bearer token + `ExecutionGrant` (correlation check done)
- [x] Frontend receives typed `ExecutionPreparation` and runtime types
- [x] DB-backed enrollment endpoint exists; managed instances can be created via API

Phase 3b validation runs in parallel and does not block Phase 4.

---

## Phase 6 - Session Admin Observability And Retention Foundation

### 6.1 Goal

Make every active conversation fully observable and manageable from the CLI
and control-plane without the frontend. This phase is the prerequisite for
any future retention policy, audit, or compliance work.

Source of truth: `docs/swift/design/SESSION-IDENTITY-CONTRACT.md` _(planned — file not yet written)_

### 6.2 Core Rule

**`session_id` is the only public identity for a conversation.** The term
`thread_id` must never appear in any public-facing API field, CLI label, log
line shown to users, or documentation. It is a LangGraph internal detail
isolated in the adapter layer (`react_message_codec.py`).

### 6.3 Completed In This Phase (foundation)

- [x] `ExecutionConfig.thread_id` renamed to `session_id` in `fred-sdk`
- [x] Checkpoint API response models (`_CheckpointThreadSummary`,
      `_CheckpointThreadDetail`) use `session_id`
- [x] Checkpoint endpoints renamed:
  - `GET /agents/checkpoints/{session_id}`
  - `DELETE /agents/checkpoints/{session_id}`
- [x] CLI (`fred-agents-cli`) uses `session_id` in all labels and commands:
  - `/checkpoint <session_id>` (was `/checkpoint <thread_id>`)
  - `/checkpoints` listing shows `session_id` column
- [x] `session_history` table extended with `team_id` and `agent_instance_id`
      columns (nullable, indexed)
- [x] History write path passes `team_id` and `agent_instance_id` from
      execution context on every managed turn

### 6.4 Remaining Tasks

#### A. Admin Session List Endpoint

- [ ] Make `user_id` optional in `GET /agents/sessions`:
  - with `user_id`: return sessions for that user (existing behavior)
  - without `user_id`: return all sessions across all users (admin only,
    guarded by `require_admin()`)
  - add optional query params: `team_id`, `agent_instance_id`, `limit`, `offset`
  - return a richer object per session (not just session_id string):
    `{ session_id, user_id, team_id, agent_instance_id, message_count, first_at, last_at }`
- [ ] Add CLI command `/sessions --all` (all users, admin) and
      `/sessions --team <team_id>` and `/sessions --agent <agent_instance_id>`
- [x] Add CLI command to purge checkpoint state for a session → `/delete-checkpoint [id]`
      (done 2026-04-26; see §6.4.G)

#### B. Session History Purge (Fixed 2026-04-26)

- [x] Added `delete_session(session_id) -> int` to `BaseHistoryStore`, `NoOpHistoryStore`,
      `PostgresHistoryStore`, and `HistoryStorePort` (fred-sdk Protocol)
- [x] Added `DELETE /agents/sessions/{session_id}` → removes all `session_history` rows,
      returns `{"deleted": N}` (203 on success, 503 when no history store configured)
- [x] History delete and checkpoint delete are deliberately separate operations:
      `/delete-session` touches only history; `/delete-checkpoint` touches only checkpoint;
      `/purge-session` does both — see §6.4.G for CLI details

#### C. Bulk Retention Purge

- [ ] Add `POST /agents/sessions/purge` accepting:

  ```json
  { "older_than_days": 90, "team_id": "personal", "dry_run": true }
  ```

  - `dry_run=true` returns the count of sessions that would be deleted
  - actual purge deletes both `session_history` rows AND checkpoint state
  - requires admin authorization

#### D. Control-Plane Session Metadata (→ Phase FRONT-04 — partially done)

- [x] Control-plane session metadata record created from the frontend on first turn:
      `POST /teams/{team_id}/sessions` with `{ session_id, agent_instance_id, title? }` —
      `ManagedChatPage` calls this (fire-and-forget) after generating `session_id`.
      Backend: `session_metadata` table + `SessionMetadataStore` + Alembic migration `f1a2b3c4d5e6`.
- [x] `GET /teams/{team_id}/sessions` — team-scoped session list for the sidebar (newest first).
      `ChatList.tsx` consumes this with 30s polling and renders links to managed chat pages.
- [ ] `PATCH /control-plane/v1/sessions/{session_id}` — update title, status (deferred)
- [x] Freeze how control-plane session metadata freshness is updated after each
      managed turn, without making control-plane proxy or read runtime message
      history.
      Requirement:
  - sidebar ordering and last-activity metadata must remain control-plane-owned
  - runtime message content must remain runtime-owned
  - the solution must preserve control-plane as a management-plane component,
    not a conversation-history serving plane
    Decision:
  - Phase CHAT-01 uses the smallest control-plane metadata refresh path:
    `PATCH /control-plane/v1/teams/{team_id}/sessions/{session_id}` with
    `{ "updated_at": "<ISO datetime>" }`.
  - The frontend calls it after a completed managed turn. The endpoint updates
    only `session_metadata.updated_at`; it does not read, proxy, cache, or serve
    runtime message history.
  - **Done (2026-04-27)**: `ManagedChatPage` wires `onTurnPersisted` → `refreshSession`
    on every `turn_persisted` SSE event via `usePatchTeamSession...Mutation`.
  - Inline title/status editing remains deferred to the later session PATCH
    scope.
- [ ] `DELETE /control-plane/v1/sessions/{session_id}` — mark deleted, trigger
      runtime purge via the purge queue (deferred)

#### E. Legacy Purge Queue Cleanup

- [ ] Document that `session_purge_queue` in `control-plane-backend` is a
      **legacy agentic-backend artifact** unrelated to `session_history`
- [ ] Either remove it or repurpose it as the control-plane-initiated purge
      request queue that feeds the runtime bulk purge endpoint above; do not mix
      the two concerns until a concrete policy is defined

#### F. Session Endpoint User-Ownership Enforcement (Security Hardening)

Current status (2026-06-01): CTRLP-10 delivered per-user personal-team
isolation (`personal-{uid}`), ReBAC alignment, runtime ownership hardening,
and control-plane session PATCH/DELETE ownership enforcement.

`POST`, `PATCH`, and `DELETE /teams/{team_id}/sessions/{session_id}` all check
`CAN_READ` team membership (Keycloak + ReBAC) and scope queries to `team_id`.
However, none of them verify that `session.user_id == current_user.username`.
Any team member with `CAN_READ` can currently patch or delete another member's
session.

Fix: pass `user_id` into `SessionMetadataStore.update_metadata` and
`SessionMetadataStore.delete` and add a `WHERE user_id = :user_id` clause.
The `POST` (create) already writes `user_id`; the read path (list) is read-only
and scoped to the team so it is not affected.

- [x] `store.update_metadata`: add `user_id` filter; return `None` (→ 404) when
      the session belongs to another user
- [x] `store.delete`: add `user_id` filter; return `False` (→ 204 with no-op) or
      raise 403 when the session belongs to another user
- [x] `product/service.py`: thread `user.username` through both call sites
- [x] Add offline test: patching/deleting a session owned by a different user
      returns the appropriate error code

#### G. CLI Developer Ergonomics (Fixed 2026-04-26; extended 2026-05-06)

A series of `fred-agents-cli` improvements to make the CLI fully self-contained for
developer testing and devops session management.

**Session navigation:**

- [x] `/sessions` — now shows message count, first user message preview, and last bot
      reply preview per session; refreshes the tab-completion index for session IDs
- [x] `/session` (bare) — shows current session + usage hint (was a no-op)
- [x] `/session <N>` — switches by 1-based index from last `/sessions` list (was broken:
      used the literal string `"2"` as session ID)
- [x] `/session <id>` — switches by exact ID (unchanged)
- [x] `/session-new` — generates a fresh `dev-session-<hex8>` and switches to it
- [x] `/session-info [id]` — shows session metadata derived from history: title (first user
      message), created_at, last_at, exchange count, message count, HITL gate count, agents
      used, models used, total token usage (input/output)
- [x] Tab-completion for `/session ` prefix — populated after each `/sessions` call

**Identity & context:**

- [x] `/whoami` — now shows a full structured identity panel: user, auth mode, team, agent,
      session, execution mode, pod URL
- [x] Standalone-mode warning: shows that CLI stores history under the Unix username
      (`getpass.getuser()`) while the UI may use a different user_id (e.g. `admin`); suggests
      `--user-id admin` to align

**History inspection:**

- [x] `/history --raw [id]` — dumps the full `ChatMessage[]` JSON payload exactly as the UI
      receives it from `GET {messages_url_template}`, one message per labelled block
- [x] HITL gate rendering in `/history`: box-drawing style with numbered choices and `[id]`
      labels; `hitl_response` shows `✓ label [choice_id]`
- [x] `[HITL ask]` channel label renamed to `[HITL gate]` for clarity

**Cleanup (irreversible — all prompt `Type 'yes' to confirm`):**

- [x] `/delete-session [id]` — deletes all `session_history` rows; checkpoint kept
- [x] `/delete-checkpoint [id]` — purges checkpoint state via `DELETE /agents/checkpoints/{id}`; history kept
- [x] `/purge-session [id]` — deletes BOTH history rows and checkpoint state
- [x] After a successful delete, the session is removed from the in-memory tab-completion index
- [x] `delete_session_messages()` and `delete_checkpoint()` added to `AgentPodClient`

**Template inspection + direct tuning (2026-05-06):**

- [x] `GET /agents/templates` → `list_templates()` in `AgentPodClient`; returns full template
      list including `kind`, `description`, `default_tuning.fields`, `available_mcp_servers`
- [x] `/inspect` — renders the current agent's FieldSpec table grouped by `ui.group`, with
      key, type, required, default, range, description, and available MCP servers
- [x] `/run <scenario>` — sends scenario keyword directly as message text; tab-completes the 8
      `fred.github.test_assistant` scenario keywords; falls through to the normal send path
- [x] `/tune key=value` — sets a session-local tuning override (parsed to bool/int/float/str);
      `/tune key=` clears a specific override; stored in `current_inline_tuning` dict
- [x] `/tuning` — renders active in-session overrides as a key→value table in green
- [x] Prompt badge `~N` (ANSI yellow) shown when N overrides are active
- [x] `inline_tuning` field added to `RuntimeExecuteRequest` (fred-sdk) and `_AgentExecuteRequest`
      (fred-runtime); direct-template path in `_resolve_agent_instance` applies inline overrides
      via `_apply_runtime_tuning` — intended for CLI dev tooling, not production frontend
- [x] `TuningScalar` + `TuningValue` typed aliases replace all `Dict[str, Any]` in the tuning
      surface (`FieldSpec.default`, `AgentTuning.values`, `GraphNodeContext.tuning_values`,
      `_GraphNodeExecutionContext.tuning_values`)
- [x] `tuning_values` moved from `GraphAgentDefinition` to base `AgentDefinition`; all agent
      families carry it and `_apply_runtime_tuning` sets it unconditionally
- [x] ReAct silent-drop gap closed: non-`prompts.system` tuning values reach
      `render_prompt_template` as `extra_tokens` (keys dot→underscore transformed) so prompt
      templates may reference e.g. `{prompts_planning}`

#### F. History Schema — HITL and Sources (Fixed 2026-04-26)

Two gaps in `_write_turn_history` were identified and closed:

**Sources were dropped from history.**
The `final` SSE event carries `sources: VectorSearchHit[]` but the persistence code
never extracted them. `make_assistant_final` was called without `sources=`, so
`ChatMetadata.sources` was always empty. Fixed: `final` payload now extracts
`sources`, deserializes them as `VectorSearchHit`, and passes them to
`make_assistant_final`.

**HITL choices were not stored.**
`awaiting_human` was stored as a flat `system_note` text (question only); the
structured choices list was silently dropped. This broke audit trails and prevented
the UI from reconstructing the HITL card from history. Fixed with a proper design:

- [x] Added `Channel.hitl_request` and `Channel.hitl_response` to `fred_core.history.history_schema.Channel`
- [x] Added `HitlChoiceRecord(id, label)` model
- [x] Added `HitlRequestPart(type="hitl_request", stage, title, question, choices)` — full gate definition
- [x] Added `HitlResponsePart(type="hitl_response", choice_id, label)` — user's selection
- [x] Both added to the `MessagePart` discriminated union
- [x] Added `make_hitl_request(...)` and `make_hitl_response(...)` factory helpers
- [x] `awaiting_human` events now stored as `Role.system / Channel.hitl_request / HitlRequestPart`
- [x] HITL resume turns now stored as `Role.user / Channel.hitl_response / HitlResponsePart`
- [x] `resume_payload` threaded into both `_write_turn_history` call sites (SSE stream + sync execute)
- [x] CLI `print_history` renders `hitl_request` parts (question + options list) and `hitl_response` parts (selected choice)
- [x] `make code-quality` and `make test` green in `fred-core` and `fred-runtime`

**Audit coverage after the fix:**
Every HITL exchange now produces two history rows per gate:

1. `[system / hitl_request]` — what was asked + all choices presented
2. `[user / hitl_response]` — which choice the user made (or typed text for free-text gates)

---

#### H. Fred 2.0.2 — RGPD-Ready Increment (`CTRLP-12`)

RFC ref: `docs/swift/rfc/FRED-2.0.2-RGPD-READY-RFC.md`
Execution: TBD (RFC proposed — ONE GitHub issue "Fred 2.0.2 — RGPD-ready" gates this)

The single release increment that makes Fred RGPD-ready, as 2.0.1 made it C3-ready.
All core capabilities exist; this wires them together. **One RFC, one issue.** Two
workstreams below: **(A) complete provable erasure** and **(B) team governance
console**. The former TEAM-08 (team data-governance) is folded in here. This section
subsumes the §6.4.C bulk-purge draft and coordinates §3b.9 (checkpoint TTL) and §6.4.E
(legacy purge queue).

**2.0.2 also bundles two additive document features** (knowledge-flow; no shared code
with A/B, each tracked in its own RFC): **DOC-RENAME** — rename a document's display name
post-ingestion (`DOCUMENT-RENAME-RFC.md`); **DOC-TAGS** — user-defined business *labels*
on documents (not ReBAC tags; `DOCUMENT-TAGS-RFC.md`, v1 implemented, 2.0.2 ships the
add-label UI). Full release scope: `FRED-2.0.2-RGPD-READY-RFC.md §0`.

**Workstream A — complete, provable erasure.**

Today, deleting a conversation touches a single store
(`lifecycle_actions.py` → one `session_store.delete`); checkpoint blobs,
object-store attachment files, vector embeddings, and KPI rows survive.

Two defects:

- **D1 — no erasure fan-out:** no single operation erases a conversation (or a
  user) across all stores; erasure is manual, multi-call, and partial.
- **D2 — checkpoint has no owner:** `langgraph_checkpoint*` is keyed by
  `thread_id` only (no `user_id`, no age index), so checkpoint state cannot be
  erased per-subject or swept by retention.

Scope discipline: **add only what is missing.** Most per-store delete primitives
already exist and are reused unchanged — `delete_session`, `adelete_thread`,
`SessionMetadataStore.delete`, `delete_for_session`, the content/vector backend
deletes, and crucially **`delete_document_and_artifacts(document_uid)`** (a ready,
currently-unused knowledge-flow strong-delete that removes vectors + content +
tabular + metadata in one call). Only two things are genuinely new.

New code (the two missing pieces):

- [ ] `checkpoint_thread_owner(thread_id, user_id, team_id, created_at, last_activity_at)`
      side table; populate best-effort on every `aput` (never fails a turn); backfill
      from `session_history`; add a per-user checkpoint purge endpoint (runtime Alembic
      migration + standalone self-init)
- [ ] KPI delete/anonymise method on the KPI store (the only store with no delete
      primitive) — null `user_id`/`session_id`/`exchange_id` by default, hard-delete optional

Glue (wrap existing primitives, no new deletion logic):

- [ ] `ConversationErasureService` + per-store `StoreEraser` registry returning a typed,
      auditable `ErasureReceipt` (control-plane)
- [ ] Thin knowledge-flow endpoint exposing the existing `delete_document_and_artifacts`;
      `AttachmentEraser` = `delete_for_session(session_id)` + that endpoint per
      session-owned attachment (+ `delete_object(storage_key)` only if a distinct raw object)
- [ ] Switch the lifecycle purge action from a single `session_store.delete` to
      `erase_team_member(...)` (flag-guarded for one release)
- [ ] `deleted_at` (nullable) column on `session_metadata`; sidebar list filters
      `deleted_at IS NULL` (soft-hide for team deferred delete)
- [ ] Rewire the **delete button** handler (`DELETE …/teams/{team_id}/sessions/{session_id}`,
      today metadata-only). As shipped (A5), **both spaces defer** when a window is
      configured, differing only in the window *source* via `is_personal_team_id`:
      **personal** → platform `personal_delete_grace` (NOT user-overridable; unset →
      immediate `erase_session`, "delete means delete"); **team** → effective
      `team_delete_grace`. When a window applies: set `deleted_at` (hide now) + enqueue
      a `USER_DELETED` purge due at `now + window`, so `session_history` survives the
      eval window and is erased after (erase-at-expiry = A6, pending).
- [ ] Retention knobs in `conversation_policy_catalog.yaml` (global default + per-team
      `rules` override): `team_delete_grace` (deferred team-delete window, e.g. `P30D`) and
      `max_idle` (standing idle cap, default `null`). Add `LifecycleTrigger.USER_DELETED`
      and `IDLE_EXPIRED`. The periodic scheduler pass drains due `USER_DELETED` entries and
      erases idle sessions (`session_metadata.updated_at < now − max_idle(team)`) via
      `erase_session`, with a dry-run preview. Personal deletes ignore both grace knobs.
      Per-team values editable from a team-admin UI = named follow-on, not in this item.
- [ ] Admin erasure endpoints `POST /control-plane/v1/erasure/sessions/{id}` and
      `/erasure/users/{id}` (`dry_run=true` default); update
      `CONTROL-PLANE-PRODUCT-CONTRACT.md`; regenerate frontend client if surfaced

Safety boundary (over-reach guard): the orchestrator strong-deletes **only**
`document_uid`s present in the erased session's `session_attachments` rows (per-session
fast-ingest uploads). It must **never** delete library/corpus/workspace documents the
conversation merely referenced as RAG context.

Reconcile / coordinate:

- [ ] Point the §3b.9 sweeper at `checkpoint_thread_owner.last_activity_at`
- [ ] Fold the §6.4.C bulk-purge draft; reconcile the §6.4.E `session_purge_queue` legacy artifact
- [ ] Coordinate the checkpoint side table with `MEMORY-02` (Marc)

**Workstream B — team governance console** (folds former TEAM-08; first concrete
`TeamPlatformPolicy` slice; extends the existing `TeamSettingsPanel`).

- [ ] `team_policy_override(team_id, team_delete_grace, max_idle, updated_at, updated_by)`
      table + store (control-plane Alembic)
- [ ] Resolver: `team_override ?? yaml_rule ?? yaml_default`, clamped ≤ platform cap
      (reuses `evaluate_purge_policy` for the cap)
- [ ] `GET` / `PATCH /control-plane/v1/teams/{team_id}/retention` → `TeamRetentionView`
      (`platform_max` / `team_value` / `effective` / `source`); authz `CAN_READ` (view) /
      `CAN_UPDATE_INFO` (edit, owner); PATCH validates `≤ cap` (422 otherwise)
- [ ] Evaluation authz (EVAL-01 §8.4, currently none): `CAN_READ` list/get,
      `CAN_UPDATE_AGENTS` create/cancel, `CAN_READ_CONVERSATIONS` for real-conversation campaigns
- [ ] `TeamSettingsRetention.tsx` tab + `TeamSettingsMenuPanels.RETENTION` entry; regenerate
      control-plane client (`make update-control-plane-api`); governance copy (RGPD/AI-Act)

Acceptance (RGPD-ready DoD): (A) a completeness fixture (text turn + tool call + uploaded
attachment + ≥2 checkpoint steps) erased via `erase_session` returns 0 rows on re-query in
**every** store, and `erase_user` removes one user's data without touching another's;
(B) owner edits per-team retention bounded by a read-only platform cap (PATCH above cap →
422), a manager can run evaluation but not edit retention, and a team-deleted conversation
stays readable by evaluation for the configured window then is erased.

---

### 6.5 CLI Display Standard (mandatory for all session/checkpoint commands)

Every session listing shown by the CLI must include these columns in this order:

```
session_id            user_id      team_id     agent_instance_id  last_active      msgs  pend
<36-char UUID>        alice        personal    inst-abc123        2026-04-19 13:40    12     0 ◀
```

- `◀` marks the currently active session
- `pend > 0` shown in yellow (indicates a crashed turn with uncommitted writes)
- `user_id = "unknown"` shown in dim (no-security mode)
- truncate `agent_instance_id` to 12 chars if needed for terminal width

### 6.6 Validation

- [ ] `GET /agents/sessions` returns all sessions when called without `user_id`
      from an admin context
- [ ] `GET /agents/sessions?team_id=personal` returns only sessions for that team
- [ ] CLI `/sessions --all` renders the full table with all required columns
- [ ] CLI `/checkpoint delete <session_id>` purges checkpoint state and confirms
- [ ] `DELETE /agents/sessions/{session_id}` removes message history only
- [ ] A full session purge (history + checkpoint) can be performed from CLI
      without connecting to the database directly
- [ ] `make code-quality` and `make test` pass in `fred-runtime` and `fred-sdk`

---

### 6.7 Admin Maintenance Stats Surface (spec only)

#### Goal

Add a compact, admin-only maintenance view for the two components that own the
current migration state:

- `control-plane-backend`
- `fred-runtime`

This surface exists to help operators and developers understand system size and
data growth without opening a database, tracing through multiple tables, or
reading sensitive content.

This is **not** a product analytics endpoint, not a dashboard API, and not a
cross-component aggregation layer.

#### Endpoint Rule

- [ ] `GET /control-plane/v1/admin/stats`
- [ ] `GET /pod/v1/admin/stats` or equivalent runtime-base-path endpoint
- [ ] Both endpoints require admin access when security is enabled.
- [ ] Both endpoints must remain read-only and offline-friendly.
- [ ] No endpoint may call the other component; each reports only data it owns.

#### Data Rule

Return maintenance statistics only:

- counts
- grouped counts
- oldest/newest timestamps
- queue sizes
- storage/backend reachability and coarse size indicators when cheap locally

Never return sensitive content:

- no message text
- no prompt text
- no tool payloads
- no checkpoint payloads
- no document excerpts
- no full conversation titles if they could leak user intent

#### Control-Plane Stats

Initial control-plane stats should include:

- [ ] team count
- [ ] managed agent instance count
- [ ] managed agent instances by status
- [ ] session metadata count
- [ ] session metadata count by team
- [ ] oldest/newest `session_metadata.created_at`
- [ ] oldest/newest `session_metadata.updated_at`
- [ ] `session_purge_queue` count if the legacy table still exists
- [ ] oldest/newest purge queue item timestamp if the legacy table still exists

#### Runtime Stats

Initial runtime stats should include:

- [ ] `session_history` row count
- [ ] distinct runtime session count
- [ ] session count by `team_id` when present
- [ ] session count by `agent_instance_id` when present
- [ ] oldest/newest history timestamp
- [ ] checkpoint row count
- [ ] distinct checkpoint session count
- [ ] oldest/newest checkpoint timestamp when available
- [ ] pending or resumable checkpoint count if this can be computed without
      loading checkpoint payloads

#### Response Shape

Use one small typed response per component. Keep the top-level shape similar,
but do not force a shared DTO until both implementations prove it useful.

Minimum shape:

```json
{
  "component": "fred-runtime",
  "generated_at": "2026-04-23T12:00:00Z",
  "storage": {
    "backend": "sqlite",
    "reachable": true
  },
  "counts": {},
  "groups": {},
  "oldest": {},
  "newest": {}
}
```

#### Implementation Order

1. `fred-runtime` first, because session history and checkpoints can grow
   silently and are hardest to inspect safely.
2. `control-plane-backend` second, focused on product metadata and purge queue
   visibility.

#### Validation

- [ ] Non-admin users are denied when security is enabled.
- [ ] Default/offline tests require no Keycloak, OpenFGA, Postgres, MinIO,
      OpenSearch, Prometheus, or runtime peer service.
- [ ] Stats queries do not load message/checkpoint content payloads.
- [ ] `make code-quality` and `make test` pass in each touched project.

---

## Phase 7 - Per-Turn KPI And Structured Observability

### 7.1 Goal

Close the gap between what the observability contract mandates (Section 3b.5)
and what is actually emitted. Today:

- tool-call latency and failure KPIs are emitted correctly via `ContextAwareTool`
- process and SQL pool KPIs are emitted at startup
- **no per-turn or per-exchange KPI event exists** — the most important
  observability unit (one user request → one assistant response) is invisible
- LLM call latency is not emitted at the KPI level (`log_llm()` is defined in
  `KPIWriter` but never called from the runtime)
- `exchange_id` is never added to any KPI dims despite being available in
  session history
- `runtime_id` / service name is absent from all KPI dims despite being
  required by 3b.5
- `session_id` and `user_id` are Prometheus label dimensions, which creates
  unbounded cardinality in production deployments

This phase hardens the observability stack so that any turn can be traced from
the CLI using `session_id` as the primary key — end-to-end, without requiring
Grafana or Prometheus.

### 7.2 Audit Summary (April 2026)

| Signal                                             | Source                                            | Status                                                             |
| -------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------ |
| Tool call latency (`agent.tool_latency_ms`)        | `ContextAwareTool._kpi_base_dims()`               | ✅ emitted                                                         |
| Tool failure counter (`agent.tool_failed_total`)   | `ContextAwareTool`                                | ✅ emitted                                                         |
| Graph phase latency (`app.phase_latency_ms`)       | `graph_runtime._graph_phase_timer()`              | ✅ emitted with full identity dims                                 |
| Process / SQL pool metrics                         | `fred-runtime` boot                               | ✅ emitted (system-level, no identity needed)                      |
| LLM call latency (`agent.llm_latency_ms`)          | `KPIWriter.log_llm()` defined                     | ❌ never called                                                    |
| Per-turn exchange summary (`agent.turn_completed`) | `agent_app._emit_turn_completed()`                | ✅ emitted from both SSE and non-streaming paths                   |
| `exchange_id` in tool KPI dims                     | `_kpi_base_dims()`, injected via `RuntimeContext` | ✅ emitted                                                         |
| `runtime_id` / service name in any KPI dim         | `_kpi_base_dims()`                                | ✅ emitted                                                         |
| `session_id` as Prometheus label                   | `ContextAwareTool` + `_graph_phase_timer`         | ✅ removed (cardinality fix)                                       |
| `user_id` as Prometheus label                      | `ContextAwareTool` + `_graph_phase_timer`         | ✅ removed (cardinality fix)                                       |
| `exchange_id` in Langfuse trace metadata           | `LangfuseTracerAdapter.start_span()`              | ✅ propagated via `context.baggage`                                |
| Security audit log channel                         | `fred.security.audit` logger + ring buffer        | ✅ grant_validated / grant_validation_failed / grant_user_mismatch |
| KF client HTTP call KPIs (phase latency)           | `kf_base_client`                                  | ✅ fixed — carries full identity dims                              |
| ReAct runtime phase latency                        | `react_runtime`                                   | ✅ added `app.phase_latency_ms` timer                              |

**Note on KF client:** `kf_base_client._kpi_dims()` is well-implemented (captures `session_id`, `user_id`,
`team_id`, `agent_instance_id`, etc.) but is **never called** — it is dead code. The `phase_timer`
imported from `kpi_phase_metric` only receives `(kpi, phase_name)` and emits `{phase: "..."}` only.

**Note on ReAct vs Graph:** `GraphRuntime` wraps every node execution in `_graph_phase_timer()` with full
identity dims. `ReActRuntime` and its `react_tool_loop` have zero KPI instrumentation.

### 7.3 Cardinality Policy

Prometheus labels must remain **low-cardinality**. High-cardinality identity
fields (`session_id`, `user_id`, `team_id` when many teams exist) must follow
this split:

| Label               | Prometheus                          | Structured KPI store (OpenSearch / log) |
| ------------------- | ----------------------------------- | --------------------------------------- |
| `tool_name`         | ✅ yes                              | ✅ yes                                  |
| `agent_step`        | ✅ yes                              | ✅ yes                                  |
| `phase`             | ✅ yes                              | ✅ yes                                  |
| `agent_instance_id` | ✅ yes (bounded by managed agents)  | ✅ yes                                  |
| `team_id`           | ✅ yes (bounded by teams)           | ✅ yes                                  |
| `template_agent_id` | ✅ yes (bounded)                    | ✅ yes                                  |
| `runtime_id`        | ✅ yes (bounded by pods)            | ✅ yes                                  |
| `error_code`        | ✅ yes                              | ✅ yes                                  |
| `session_id`        | ❌ no — remove from Prometheus dims | ✅ yes (log/OpenSearch only)            |
| `user_id`           | ❌ no — remove from Prometheus dims | ✅ yes (log/OpenSearch only)            |
| `exchange_id`       | ❌ no                               | ✅ yes (log/OpenSearch only)            |

### 7.4 Required KPI Event: `agent.turn_completed`

Every completed turn (one user input → one final assistant response) must emit
a structured KPI event with the following fields. This event is the
**primary observability unit** for per-session analysis.

```
event:       agent.turn_completed
session_id:  <UUID>            # primary key for per-session queries
exchange_id: <UUID>            # unique per turn
user_id:     <str>
team_id:     <str>
agent_instance_id: <str | None>
template_agent_id: <str | None>
runtime_id:  <str>             # pod / service name
model_name:  <str | None>
finish_reason: <str | None>
total_latency_ms: <int>        # wall time from first token in → final event out
llm_latency_ms:  <int | None>  # sum of LLM call latencies within the turn
tool_count:  <int>             # number of tool calls in the turn
input_tokens:  <int | None>
output_tokens: <int | None>
```

This event must be emitted from `fred-runtime` at the point where a
`FinalRuntimeEvent` is processed and written to `session_history`.

### 7.5 Required KPI Event: `agent.llm_call`

Every LLM call (model invocation) must emit a structured KPI event:

```
event:         agent.llm_call
session_id:    <UUID>
exchange_id:   <UUID>
agent_step:    <str>          # e.g. "react_step_1"
model_name:    <str>
latency_ms:    <int>
input_tokens:  <int | None>
output_tokens: <int | None>
finish_reason: <str | None>
team_id:       <str>
agent_instance_id: <str | None>
runtime_id:    <str>
```

This maps to the existing `KPIWriter.log_llm()` method which is currently
never called. The call site is the ReAct/Graph executor at model invocation
time.

### 7.6 Tasks

#### A. Add `exchange_id` and `runtime_id` to tool KPI dims

- [x] Add `exchange_id` to `_kpi_base_dims()` in
      `libs/fred-runtime/fred_runtime/common/context_aware_tool.py`
      — `exchange_id` is now generated at turn start in `_stream()`, injected into
      `RuntimeContext`, and propagated to all tool calls within that turn
- [x] Add `runtime_id` to `_kpi_base_dims()` — populated from `RuntimeConfig.service_name`
      which is set at pod startup from `config.app.name`
- [x] Remove `session_id`, `user_id`, and `exchange_id` from Prometheus label
      dimensions in the shared `PrometheusKPIStore` — keep them on the original
      KPI event so structured delegates (log / OpenSearch) retain per-turn identity

#### B. Add `agent.turn_completed` event emission

- [x] Emit `agent.turn_completed` from `fred-runtime` `agent_app.py` via
      `_emit_turn_completed()` called at the end of `_stream()` after the SSE loop
      — carries `session_id`, `exchange_id`, `user_id`, `team_id`,
      `agent_instance_id`, `template_agent_id`, `runtime_id`, `model_name`,
      `finish_reason`, `total_latency_ms`, `tool_count`, `input_tokens`,
      `output_tokens`
- [x] `exchange_id` generated at turn start in `_stream()`, propagated into
      `RuntimeContext` via `_iterate_runtime_event_payloads()`, and passed to
      `_write_turn_history()` (no longer generated independently there)
- [x] Same emission added to the **non-streaming `execute()` path**: `exchange_id`
      generated at turn start, passed to `_iterate_runtime_event_payloads()` and
      `_write_turn_history()`, `_emit_turn_completed()` called after the loop
- [x] `KpiLogStore.index_event()` fixed: was a silent no-op (`pass`); now logs
      a structured JSON line at INFO level for all three structured event names
      (`agent.turn_completed`, `agent.turn_error_total`, `agent.tool_failed_total`)
- [x] `exchange_id` propagated to **Langfuse trace metadata** via
      `context.baggage.get("exchange_id")` in `LangfuseTracerAdapter.start_span()`
- [x] **`Quantities` model fixed** (`fred_core/kpi/kpi_writer_structures.py`): added
      `tool_count`, `input_tokens`, `output_tokens` fields (all `Optional[int] = None`);
      changed existing `bytes_in/bytes_out/chunks/vectors` from `= 0` to `= None` so
      `model_dump(exclude_none=True)` correctly omits unset fields — turn KPI quantities
      were previously silently discarded and replaced with zeroed pipeline fields
- [x] `_emit_audit_event(level, name, **fields)` helper centralises all audit
      event emission: builds timestamped event, appends to `_AUDIT_EVENTS_BUFFER`, and
      calls `_audit_logger.<level>` — replaces all duplicated inline blocks
- [x] `grant_validation_failed` events now correctly appear in `_AUDIT_EVENTS_BUFFER`
      (ring buffer was missing from both `execute()` and `execute_stream()` audit paths)
- [x] `datetime.utcnow()` → `datetime.now(timezone.utc)` at all 4 sites in `agent_app.py`
- [x] `asyncio.ensure_future` → `asyncio.create_task` for history write background task

#### C. Wire `KPIWriter.log_llm()` for LLM call KPIs

- [ ] Identify the model invocation call sites in the ReAct runtime
      (`libs/fred-sdk/fred_sdk/react/`) and Graph runtime
      (`libs/fred-sdk/fred_sdk/graph/`)
- [ ] Add `log_llm()` calls at each LLM invocation boundary, passing
      `session_id`, `exchange_id`, `agent_step`, `model_name`, `latency_ms`,
      `input_tokens`, `output_tokens`, `finish_reason`
- [ ] Ensure `exchange_id` is available in execution context at model call time

#### D. CLI per-session KPI view

- [x] Added `/kpi [limit]` CLI command (default limit 30): shows the last N
      `agent.turn_completed` events from the pod-side in-memory ring buffer
      (200-event deque); columns: Timestamp, ms, model, tools, in tok, out tok,
      status, session (current session row highlighted with ◀)
- [x] `/kpi prom [pattern]` continues to show Prometheus aggregate view
- [x] Added `GET /agents/kpi-turns` pod endpoint returning the ring buffer
- [ ] Add `/kpi session <session_id>` command querying structured KPI log store
      (deferred — requires OpenSearch/log-store query support not yet wired)

#### D. Fix `kf_base_client` identity dims (dead-code `_kpi_dims`)

- [x] Replaced `phase_timer(self._kpi, phase_name)` (which lost all identity dims)
      with `self._kpi.timer("app.phase_latency_ms", dims={..._kpi_dims()..., "phase": ...})`
      — KF client HTTP latency now carries `session_id`, `team_id`, `agent_instance_id`
      and all other managed execution identity fields
- [x] Removed dead `from fred_core.kpi.kpi_phase_metric import phase_timer` import

#### E. Add ReAct runtime phase latency KPI

- [x] Added `app.phase_latency_ms` timer around the full `stream()` execution
      in `_TransportBackedReActExecutor` (`react_runtime.py`) with dims
      `phase="react_stream"`, `agent_id`, `agent_step`, `session_id`, `team_id`,
      `agent_instance_id`, `template_agent_id` — gives parity with Graph runtime

#### G. Documentation

- [ ] Update `docs/design/RUNTIME-EXECUTION-CONTRACT.md` Section on KPI/metrics
      to list the mandatory KPI events, their fields, and the cardinality policy
- [ ] Update `docs/design/SESSION-IDENTITY-CONTRACT.md` to reference
      `exchange_id` as a required field in every KPI emission (not just
      `session_history`)

### 7.7 Security Audit Channel

Security-relevant events are separated from technical KPIs through a dedicated
audit logging channel so that SIEM tools, log shippers, and operations teams
can filter them independently of debug or KPI output.

**Implementation (completed 2026-04-26):**

- [x] Dedicated logger `fred.security.audit` (`_audit_logger`) in
      `agent_app.py` — distinct from the `fred.runtime` technical logger
- [x] Module-level in-memory ring buffer `_AUDIT_EVENTS_BUFFER` (200 events,
      thread-safe with `_AUDIT_EVENTS_LOCK`) — CLI-queryable without log file access
- [x] Audit events emitted at all authentication/authorization boundaries:
  - `grant_user_mismatch` — execution grant user != authenticated user (logged + ring buffer)
  - `grant_validation_failed` — grant validation raised an exception (logged + ring buffer)
  - `grant_validated` — execution grant passed user correlation check (logged + ring buffer)
  - `grant_user_correlated` — user correlation confirmed at `_validate_grant_user_correlation()` (logged + ring buffer)
- [x] `GET /agents/audit-events` pod endpoint returning the ring buffer
- [x] `/audit [limit]` CLI command in `fred-agents-cli` — shows table of recent
      security audit events with columns: Timestamp, event (red=failure, green=success),
      user_id, agent_instance_id, execution_action, reason

**Audit event schema:**

```json
{
  "ts": "2026-04-26T12:00:00Z",
  "audit_event": "grant_validated",
  "user_id": "alice",
  "agent_instance_id": "inst-abc",
  "team_id": "team-xyz",
  "execution_action": "prepare_execution",
  "reason": "grant user matches authenticated user"
}
```

**Log channel separation:**

| Logger                | Purpose                | Sink                                  |
| --------------------- | ---------------------- | ------------------------------------- |
| `fred.runtime`        | Technical / debug logs | Standard app logging                  |
| `KPI`                 | Structured KPI events  | KPI store (log/Prometheus/OpenSearch) |
| `fred.security.audit` | Security audit events  | Dedicated audit sink (+ ring buffer)  |

To route `fred.security.audit` to a dedicated SIEM sink, configure the Python
logging handler for this logger name in the pod's logging config.

### 7.9 Observability Completion Target and Deferred Work

**Current completion target (this phase):**

| Layer              | Target                                                                                       |
| ------------------ | -------------------------------------------------------------------------------------------- |
| Local dev          | CLI `/kpi` and `/kpi session <id>` against structured KPI log store                          |
| K8s production     | Prometheus scrape (`observability.metrics: prometheus`) — pull-based, no push agent required |
| Distributed traces | Structured JSON logs → fluentbit/filebeat DaemonSet → OpenSearch or Loki → Grafana           |

The tracer backends `null`, `logging`, and `langfuse` are the supported backends today.
The log-based trace path (JSON structured logs exported via a standard log shipper DaemonSet)
is the **production target** for Phase 7. No OTLP push endpoint is required to complete this phase.

**Explicitly deferred — OTLP push (future phase):**

OTLP (OpenTelemetry Protocol) is a push-based wire standard for traces, metrics, and logs.
Fred does **not** wire OTLP today — the OTLP warnings visible in test output originate from
LangSmith's own transitive dependency, not Fred's tracer.

A future OTLP phase would require:

- New `TracerBackend.otlp` and `MetricsBackend.otlp` config keys
- OTel Collector or compatible endpoint (Grafana Alloy, MLflow, Jaeger, etc.)
- Push endpoint URL in `configuration.yaml`

OTLP is **not a dependency for Phase 7 completion**. Do not block the current observability
revamp on OTLP. Open a dedicated backlog phase when needed.

### 7.10 Validation

- [x] `/kpi [limit]` in `fred-agents-cli` shows `agent.turn_completed` rows from
      the pod-side ring buffer with ms, model, tools, token counts, and session highlight
- [x] `/audit [limit]` in `fred-agents-cli` shows security audit events from the
      pod-side ring buffer with event name colour-coded (red=failure, green=success)
- [x] `make code-quality` and `make test` pass in `fred-core` (31 tests) and
      `fred-runtime` (62 tests), including:
  - `test_emit_audit_event_populates_ring_buffer` — `_emit_audit_event` fills buffer, filters None
  - `test_ring_buffer_endpoints_return_seeded_events` — `/agents/kpi-turns` and `/agents/audit-events` endpoints
  - `test_emit_turn_completed_populates_kpi_turns_buffer` — `/execute` adds record to ring buffer
  - `test_index_event_logs_structured_json_for_turn_completed` — `KpiLogStore` structured log output
  - `test_index_event_logs_structured_json_for_turn_error` — `agent.turn_error_total` log
  - `test_index_event_ignores_unknown_event_names` — unknown events not logged
- [x] `Quantities` model correctly produces `{"tool_count": N, "input_tokens": N, "output_tokens": N}`
      (verified by `make test` in fred-core — no zeroed pipeline fields in turn KPI dumps)
- [ ] After one managed execution, `/kpi [limit]` shows at least one
      `agent.turn_completed` row for the active session (live stack validation pending)
- [ ] `/audit [limit]` after a successful execution shows `grant_validated` row
      (live stack validation pending)
- [ ] After a tool-call-heavy turn, `agent.tool_latency_ms` histogram in `/kpi prom`
      does not expose unbounded identity labels; `exchange_id` remains structured KPI-only
- [ ] After a multi-tool turn, `agent.llm_call` rows appear in the structured
      KPI log for every model invocation within that turn (deferred — `log_llm()` not yet called)
- [ ] Structured JSON logs confirm `agent.turn_completed` and security audit events
      appear in the log-based trace path (verifiable via local log grep)

---

## Phase UX — UI/UX Consolidation

### UX-1 Full visual audit and design review — **UX-01**

**Status:** open — owner: Dimitri — reviewer: Maxime (UX referent, mandatory sign-off)
**Tracker:** `docs/swift/ux/COMPONENT-UX.md`

**Scope:** Every implemented page and component in `apps/frontend/src/rework/`:
agent creation form, team agents page, agent card grid, MCP tool cards,
chat UI (all molecules and organisms), agent options panel, search policy
and RAG scope controls, session sidebar.

**Ownership model:** Dimitri implements all fixes. Maxime reviews and validates —
no issue can move to `Resolved` in `COMPONENT-UX.md` without Maxime's explicit
sign-off. Design decisions belong to Maxime; implementation decisions to Dimitri.

**What this is not:** A code refactor or migration task. Dimitri touches code only
to fix issues that Maxime identifies or validates. Design decisions first,
implementation second.

**Process:**

1. **Design review session** — Dimitri + Maxime walk through every rework page
   live. Issues are noted directly in `COMPONENT-UX.md` under the relevant
   component with severity (blocking / minor / polish).
2. **Triage** — Dimitri sorts issues into: quick fix (< 1h), component redesign
   (needs Figma update first), product decision (needs PM alignment).
3. **Fix iterations** — Dimitri picks up quick fixes; Maxime signs off each one
   before it moves to `Resolved`. Redesigns are scheduled as sub-items.

**Known issues to bring to the review session (non-exhaustive):**

- [ ] **Tooltip overflow — search policy select** (`McpServerCard.tsx`,
      `useEnumOptionDescriptions`): option descriptions (`t("search.strictDescription")` etc.)
      render as single long lines inside a tooltip or select dropdown. Long text
      is truncated with no wrapping. Fix: multi-line description placement below the
      option label, or a proper tooltip with `white-space: normal` and a `max-width`.

- [ ] **Tooltip overflow — RAG scope select** (`McpServerCard.tsx`): same issue for
      `chatbot.ragScope.tooltipCorpus` / `tooltipHybrid` / `tooltipGeneral` values.
      Long French strings overflow the select option description area.

- [ ] **All open issues in `COMPONENT-UX.md`** — 20+ items flagged across
      `ThoughtTrace`, `TraceEntryRow`, `SourcesPanel`, `AgentCard`,
      `AgentFormModal`, `InlineDrawer`, `ContextualPicker`, `RichInputField`,
      `SourceCard` — review and prioritise each.

**Validation:**

- [ ] All `COMPONENT-UX.md` items have a status: `Approved`, `Needs revision`
      (with a fix scheduled), or `Deferred` (with a reason).
- [ ] Tooltip issues above are resolved and verified in browser (both themes,
      both languages if i18n is in scope).

---

## Phase QUALITY — knowledge-flow parity and migration

### QUALITY-02 Knowledge-flow quality parity with control-plane + move under apps/

**Status:** in progress — assigned 2026-05-30, deadline 2026-06-06
**Owner:** Florian
**Ref benchmark:** `apps/control-plane-backend`
**Scope:** current `knowledge-flow-backend/` codebase migrated to `apps/knowledge-flow-backend/`

**Why this exists:**

- Current quality gates are green in both services, but quality depth is not comparable yet.
- Measured baseline on 2026-05-25:
      - `apps/control-plane-backend`: coverage `79%`
      - `knowledge-flow-backend`: coverage `48%`
      - baseline debt size:
            - `apps/control-plane-backend/.baseline/bandit-baseline.json`: ~20 lines
            - `knowledge-flow-backend/.baseline/bandit-baseline.json`: ~2706 lines

**Goal:** reach equal or better practical quality than control-plane for knowledge-flow,
while preserving behavior and keeping default tests offline.

**Execution slices (must be delivered in order):**

- [ ] **Q2.1 Baseline and migration prep**
      - [ ] Create migration branch and move service from `knowledge-flow-backend/` to `apps/knowledge-flow-backend/`
      - [ ] Keep all existing make targets usable from the new root
      - [ ] Preserve CI/offline behavior (`-m "not integration"`, socket restrictions, no external services)
      - [ ] Produce before/after quality report (coverage, failing modules, baseline counts)

- [ ] **Q2.2 Gate parity (must stay green throughout)**
      - [ ] `make code-quality` passes in `apps/knowledge-flow-backend`
      - [ ] `make test` passes in `apps/knowledge-flow-backend`
      - [ ] No increase in basedpyright baseline entries
      - [ ] No increase in bandit baseline entries

- [ ] **Q2.3 Coverage uplift by risk-first targeting**
      - [ ] Raise total coverage from `48%` to `>= 65%` (milestone A)
      - [ ] Raise total coverage from `>= 65%` to `>= 75%` (milestone B)
      - [ ] Stretch target: `>= 80%` (parity+ target)
      - [ ] Prioritize modules under `40%` coverage first (processors/stores/common hotspots)
      - [ ] Add deterministic offline unit tests only for default gates

- [ ] **Q2.4 Baseline debt burn-down**
      - [ ] Reduce `bandit` baseline footprint by at least `40%` vs 2026-05-25 snapshot
      - [ ] Reduce `basedpyright` baseline footprint by at least `30%` vs 2026-05-25 snapshot
      - [ ] Document each retained baseline suppression with a short rationale in code or baseline comments

- [ ] **Q2.5 Close-out and proof pack**
      - [ ] Attach final metric table (coverage total, top 20 weakest files before/after, baseline counts before/after)
      - [ ] Confirm service is fully runnable from `apps/knowledge-flow-backend`
      - [ ] Update any path-sensitive docs and scripts impacted by the move

**Definition of done (hard gates):**

- [ ] `apps/knowledge-flow-backend` is the canonical location
- [ ] `make code-quality` and `make test` are green from the new location
- [ ] Coverage `>= 75%` minimum, `>= 80%` targeted
- [ ] Baseline debt is strictly lower than initial snapshot
- [ ] No behavior regression in existing offline test suite

### QUALITY-03 Knowledge-flow new PDF processor rollout and validation

**Status:** done (2026-05-27)
**Owner:** Timothé
**Scope:** `knowledge-flow-backend` PDF fast path, extraction behavior, and supporting docs/tests

**Why this exists:**

- The incoming feature introduces a new lightweight PDF processor in the
  knowledge-flow ingestion path.
- This processor is meant to provide fast, offline-safe PDF to Markdown
  extraction for the default fast profile and attachment text path.
- We need one tracked item to validate the effective behavior, document the
  intended routing, and prove the new processor is safe to keep as the
  canonical fast-path PDF implementation.

**Execution slices:**

- [x] **Q3.1 Processor routing and defaults**
      - [x] Confirm `.pdf` routes to the new fast processor in the attachment fast-path registry
      - [x] Confirm the fast/default PDF profile stays offline-safe (`do_ocr: false`, `do_table_structure: false`)
      - [x] Confirm unsupported suffixes still fail fast with a clear error instead of falling back silently

- [x] **Q3.2 Functional validation**
      - [x] Validate whole-document PDF to Markdown extraction on representative samples
      - [x] Validate page-aware behavior (`page_range`, `return_per_page`, `add_page_headings`)
      - [x] Validate truncation, whitespace normalization, and metadata shaping remain predictable for downstream indexing

- [x] **Q3.3 Docs, tests, and close-out**
      - [x] Update processing docs so the fast PDF path and its constraints are explicit
      - [x] Add or confirm offline unit coverage for the new processor and representative PDF fixtures
      - [x] Record any known limitations versus richer PDF processors (tables, OCR, image-heavy documents)

**Definition of done (hard gates):**

- [x] The new PDF processor is the explicit fast-path implementation for `.pdf`
- [x] Fast-profile PDF extraction remains offline-safe and deterministic
- [x] Representative tests and docs cover the processor's supported behavior and limitations

---

## Phase AGENTS — pod showcase agents

### AGENTS — Document comparison agent — **FILES-03**

RFC: [`SIMILARITY-COMPARISON-AGENT-RFC.md`](../rfc/SIMILARITY-COMPARISON-AGENT-RFC.md).
First public-pod consumer of the targeted `similarity_search` primitive
([KF-SIMILARITY-SEARCH](../rfc/KNOWLEDGE-FLOW-SIMILARITY-SEARCH-RFC.md)).

- [x] New `fred.dt.comparison.graph` GraphAgent in `apps/fred-agents` comparing two
      picked documents → concordances / contradictions / lacunae, deterministic
      pairing with the LLM only judging. Declares the Text MCP server; calls
      `similarity_search` via `invoke_runtime_tool`. No new MCP service / `TOOL_REF`.
      Execution: branch `1772-…-kf-similarity-search`.
- [x] Registered in `fred_agents/registry.py`; offline tests (graph wiring + pair
      judging with mocked tool + seeded model). `make code-quality` + `make test` green.

---

## Phase STORAGE — native object-storage backends

### FILES-06 — Native Google Cloud Storage backend (ADC / Workload Identity)

Adds a `gcs` backend to both object-storage abstractions, selectable purely via
the `type:` config discriminator. MinIO/S3 and local backends are unchanged.
Registry: [`id-legend.yaml`](../data/id-legend.yaml) FILES-06 (parent FILES-04).
Guide: [`DEPLOYMENT_GUIDE_GKE.md`](../platform/DEPLOYMENT_GUIDE_GKE.md).
RFC: [`GCS-TABULAR-SIGNED-URL-RFC.md`](../rfc/GCS-TABULAR-SIGNED-URL-RFC.md).
Execution: branch `1795-…-native-google-cloud-storage-backend`; GitHub issue #1795.

- [x] `GcsFilesystem(BaseFilesystem)` in fred-core + `google-cloud-storage` dep + export.
- [x] `GcsContentStore(BaseContentStore)` (17 methods) + `GcsFileStore` in knowledge-flow.
- [x] `GcsStorageConfig` / `GcsFilesystemConfig` config models + union/factory wiring.
- [x] ADC / Workload Identity auth (no JSON key); buckets referenced lazily.
- [x] Signed URLs: app-level HMAC default for browser-facing share/download.
- [x] Tabular guardrail: unsupported GCS tabular reads fail cleanly until internal
      signed URLs are implemented.
- [x] Signed URLs for tabular: implement backend-internal GCS V4 signed URLs via
      Workload Identity + `iam.serviceAccounts.signBlob` (keyless); `GcsStorageConfig`
      gains `signing_service_account_email` with fail-fast-at-startup validation.
- [x] URL-leak redaction: signed URLs stripped from DuckDB/`httpfs` read errors
      before they reach logs or API responses.
- [x] Unit tests (mocked client) for filesystem + content store; MinIO/local untouched.
- [x] `configuration_postgres.yaml`, `values-gcp.yaml`, `DEPLOYMENT_GUIDE_GKE.md`,
      `ENV_VARIABLES.md` updates; config + chart values JSON schema regenerated.
- [ ] Live-bucket acceptance on GKE (VFS round-trip + ingestion smoke under Workload Identity).
- [ ] §1bis validation gate: DuckDB reads a Parquet artifact through a live GCS V4
      signed URL under Workload Identity (merge gate — see RFC §1bis).

---

## Acceptance Checklist

- [ ] runtime SSE is the main frontend chat transport
- [x] runtime contracts come from `fred-sdk` / `fred-runtime`
- [x] `ExecutionPreparation` contract exists and is code-generated in the frontend
- [x] bearer-token + `ExecutionGrant` dual-auth enforced at runtime (correlation check done)
- [ ] frontend no longer depends on `agentic-backend` chat schemas
- [ ] control-plane owns agent/session/admin/product APIs
- [ ] backend managed execution is fully team-scoped and trace-enriched before frontend cutover
- [x] every turn emits `agent.turn_completed` with session_id, exchange_id, latency, token usage
- [x] Prometheus labels contain no unbounded-cardinality dims (session_id, user_id removed)
- [ ] frontend runtime reachability comes from `ExecutionPreparation`, not bootstrap-side routing inference
- [ ] `agentic-backend` is no longer on the critical frontend path

---

## §INGEST — Extensible Document Processor Architecture

**ID:** INGEST-01 | **Owner:** Timothé | **Status:** not started — RFC complete, awaiting developer confirmation
**RFC:** `docs/swift/rfc/EXTENSIBLE-DOCUMENT-PROCESSOR-RFC.md`

- [ ] INGEST-01 — Developer confirmation before implementation begins
- [ ] INGEST-01 — Register `BaseProcessor` unified lifecycle contract (`extract_metadata`, `extract_content`, `vectorize`, `delete`)
- [ ] INGEST-01 — Implement block registry and startup validation (`OcrBlock`, `ImageDescriberBlock`, `MarkdownNormalizerBlock`)
- [ ] INGEST-01 — Implement trigger resolution engine (suffix, filename_pattern, custom predicate, specificity ordering)
- [ ] INGEST-01 — Dynamic processor registration loop in `main_worker.py`
- [ ] INGEST-01 — Migrate `worker_policy` timeout/retry to global config; remove per-profile timeout config
- [ ] INGEST-01 — Implement `TransientProcessingError` / `StructuralProcessingError` / `ResourceProcessingError` classification
- [ ] INGEST-01 — Implement `@timed_task` decorator and RAM observability hooks
- [ ] INGEST-01 — Ship `BaseProcessorTest` harness with `NullOcrBlock`, `FixtureImageDescriberBlock`, `StubVectorStore`
- [ ] INGEST-01 — Remove `mode` field from ingestion API and configuration
- [ ] INGEST-01 — Deprecate `processing.profiles` in `configuration.schema.json`

### INGEST-03 — Legacy/OpenDocument Office support (.doc, .ppt, .odt)

**ID:** INGEST-03 | **Owner:** Simon | **Status:** in progress (parent: INGEST-01)
**Execution:** https://github.com/ThalesGroup/fred/issues/1878 (branch `more-procs`)
**Approach:** Convert `.doc → .docx` / `.ppt → .pptx` / `.odt → .docx` with headless LibreOffice (shared `legacy_office.py`, mirroring the existing `pptx_slide_renderer` soffice pattern), then reuse the existing DOCX/PPTX extractors. No new dependency — LibreOffice already ships in both Dockerfiles.

- [x] INGEST-03 — Shared `legacy_office` converters (`convert_doc_to_docx` / `convert_ppt_to_pptx` / `convert_odt_to_docx`) + OLE magic-byte and ODF/zip validity guards
- [x] INGEST-03 — Corpus ingestion: `DocMarkdownProcessor` / `PptMarkdownProcessor` / `OdtMarkdownProcessor` (convert → delegate)
- [x] INGEST-03 — Chat attachments: `FastLiteDocProcessor` / `FastLitePptProcessor` / `FastLiteOdtProcessor` registered in the fast-text default registry
- [x] INGEST-03 — Lite markdown service: `LiteDocToMdProcessor` / `LitePptToMdExtractor` / `LiteOdtToMdProcessor` dispatch for `.doc`/`.ppt`/`.odt`
- [x] INGEST-03 — Register `.doc`/`.ppt`/`.odt` in all `config/configuration*.yaml` profiles and Helm `values.yaml` anchors
- [x] INGEST-03 — Unit tests (validity guards, convert→delegate, identity relabelling, registry coverage)

---

## Notes

- Prefer `agent_instance_id` for managed execution from the frontend.
- Treat enriched observability as part of the backend contract, not as optional polish.
- Validate managed execution with `fred-agents-cli` before treating the frontend as the primary consumer.
- Keep `session_id` stable across normal turns and HITL resumes.
- Add `checkpoint_id` support now if cheap; it will save a second protocol cleanup later.
- Do not let OpenAI compatibility become the blocking work item for the Fred frontend migration.
- **Observability completion target**: CLI `/kpi`, K8s Prometheus scraping, structured JSON logs via fluentbit DaemonSet → OpenSearch/Loki. OTLP push is explicitly deferred to a future phase — it is not required for Phase 7.
