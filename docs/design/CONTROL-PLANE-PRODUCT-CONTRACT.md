# Control Plane Product Contract — Phase 3a

This document is the authoritative design reference for the first
control-plane product migration slice.

Its purpose is to make Phase 3 codable without improvisation:

- keep `fred-runtime` focused on execution
- move only product/session/admin concerns to `control-plane-backend`
- freeze the smallest typed contracts the frontend needs next
- avoid copying `agentic-backend` DTOs or behavior into a new place

**Read this before touching:**

- `docs/platform/PLATFORM_RUNTIME_MAP.md`
- `docs/design/RUNTIME-EXECUTION-CONTRACT.md`
- `BACKLOG.md`
- `control-plane-backend/control_plane_backend/main.py`
- `frontend/src/common/config.tsx`
- `frontend/src/rework/components/pages/TeamAgentsPage/TeamAgentsPage.tsx`
- `frontend/src/rework/components/shared/organisms/ChatList/ChatList.tsx`

---

## 1. Goal

Define the minimum typed product surface that `control-plane-backend` must own
before the frontend can leave `agentic-backend`.

Phase 3a is a contract-and-boundary slice, not a full migration.

It exists to freeze:

- what belongs in control-plane
- what must stay in runtime
- which typed frontend-facing models should exist first
- which pieces are still intentionally deferred

---

## 2. Boundary Freeze

### 2.1 `control-plane-backend` owns

- frontend bootstrap/configuration
- user permission summary
- agent template discovery
- managed agent instance metadata
- team-scoped managed agent instance CRUD
- session metadata list/create/delete
- session preferences
- feedback metadata
- MCP server administration
- attachment metadata only

### 2.2 `fred-runtime` still owns

- execution itself
- SSE streaming
- HITL pause/resume
- checkpoints
- runtime history messages
- runtime event contracts
- `RuntimeExecuteRequest`
- `ExecutionGrant` validation during execution

### 2.3 `control-plane-backend` must not own

- `POST /agents/execute`
- `POST /agents/execute/stream`
- runtime history payloads returned from `/agents/sessions/{session_id}/messages`
- custom pod discovery or routing logic
- topology-aware runtime failover behavior

### 2.4 `agentic-backend` must not regain

- new frontend product/admin/session APIs
- new execution convergence behavior
- new schema-generation responsibility for migrated paths

---

## 3. Phase 3a Contract Freeze

Phase 3a now has an implemented read-only surface. The models below are the
frozen public shape unless a concrete frontend blocker proves them insufficient.

### 3.1 Frontend bootstrap

Phase 3a uses one control-plane-owned bootstrap payload:

- `FrontendBootstrap`
  - `current_user`
  - `active_team`
  - `available_teams`
  - `gcu_version`
  - `feature_flags`
  - `ui_settings`
  - `permissions`

Permissions are exposed via:

- `PermissionSummary`
  - `items`
  - flattened booleans such as `can_manage_team_agents`
  - no raw RBAC/REBAC graph internals

Keep this contract small and frontend-oriented. If it becomes insufficient,
extend `FrontendBootstrap`; do not add parallel bootstrap DTOs.

### 3.2 Managed agent discovery

Freeze two distinct concepts:

- `AgentTemplateSummary`
  - describes what can be instantiated
  - template/reference metadata only
- `ManagedAgentInstanceSummary`
  - describes a team-scoped managed instance
  - must use `agent_instance_id` as the primary identifier

Recommended minimum fields for `ManagedAgentInstanceSummary`:

- `agent_instance_id`
- `team_id`
- `template_id`
- `display_name`
- `description`
- `status`
- `created_at`
- `updated_at`
- `created_by`

Do not expose runtime pod URLs or Kubernetes topology to the frontend.

### 3.3 Runtime binding stays internal

`RuntimeBinding` is not a primary frontend product contract.

It exists so control-plane can resolve:

- one `agent_instance_id`
- one runtime-facing agent reference
- one runtime identity/binding payload

Use it for runtime resolution and backend validation only.

### 3.4 Managed agent instance writes

Freeze typed write payloads before implementing CRUD:

- `CreateAgentInstanceRequest`
- `UpdateAgentInstanceRequest`
- `DeleteAgentInstanceResponse` only if a non-empty response is needed

These requests should describe product intent, not runtime wiring internals.

### 3.5 Session metadata

Freeze session metadata as a control-plane contract separate from runtime
history:

- `SessionListItem`
- `CreateSessionRequest`
- `CreateSessionResponse`
- `DeleteSessionResponse` if needed
- `SessionPreferences`
- `UpdateSessionPreferencesRequest`

`SessionListItem` may include:

- `session_id`
- `team_id`
- `title`
- `updated_at`
- `created_at`
- `agent_instance_id`
- lightweight attachment metadata if already required by the UI

It must not inline full message history.

### 3.6 Feedback

Feedback must align with managed execution semantics:

- use `agent_instance_id`, not only legacy `agent_id`
- stay product/audit oriented
- do not depend on runtime transport DTOs

### 3.7 MCP server administration

MCP endpoints belong in control-plane, but this migration should not drag the
entire legacy agent authoring model with them.

Prefer a neutral control-plane contract over direct reuse of
`agentic_backend.core.agents.agent_spec.MCPServerConfiguration` if reuse would
keep a hard dependency on `agentic-backend`.

### 3.8 Attachment metadata

Only metadata belongs in this phase by default.

Binary upload routing is a separate decision and may remain deferred until the
team chooses between:

- upload through control-plane
- direct upload to another backend with control-plane-owned metadata

---

## 4. Implemented Phase 3a Surface

Implemented public read-only endpoints:

- `GET /frontend/bootstrap`
- `GET /teams/{team_id}/agent-templates`
- `GET /teams/{team_id}/agent-instances`

Implemented internal runtime helper:

- `GET /agent-instances/{agent_instance_id}/runtime`

Phase 3a intentionally remains:

- read-only
- metadata/product-oriented
- independent from runtime message transport

---

## 5. Source Of Truth Map

| Concern | Source of truth | Notes |
|---|---|---|
| Runtime execution contracts | `docs/design/RUNTIME-EXECUTION-CONTRACT.md` + `libs/fred-sdk` | Do not redefine in control-plane |
| Product/session/admin migration sequence | `BACKLOG.md` | Phase order and next slice |
| API ownership | `docs/platform/PLATFORM_RUNTIME_MAP.md` | Architecture boundary |
| Phase 3a control-plane contracts | this document | Product-surface source of truth |
| Generated frontend runtime types | `frontend/src/slices/runtime/runtimeOpenApi.ts` | Generated; never hand-edit |
| Generated frontend control-plane types | `frontend/src/slices/controlPlane/controlPlaneOpenApi.ts` | Generated; never hand-edit |

---

## 6. What Not To Do

Do not:

- proxy runtime execution through control-plane
- recreate `agentic-backend` WebSocket behavior in control-plane
- move runtime message history into control-plane
- expose pod URLs, service names, or routing details to the frontend
- copy `AgentSettings` wholesale as the control-plane public contract
- preserve `/schemas/echo`-style hacks for migrated product APIs
- add new abstraction layers "for later"

If a frontend type is missing, add or strengthen the source control-plane
contract and regenerate codegen.

Do not add parallel handwritten frontend DTOs.

---

## 7. Explicitly Deferred

The following remain outside the first Phase 3a implementation slice:

- `ExecutionGrant` issuance endpoint design
- managed runtime endpoint resolution payloads exposed to the frontend
- runtime history migration details beyond linking to `fred-runtime`
- binary attachment upload routing decision
- frontend SSE transport migration
- removal of legacy `agentic-backend` code paths
- feedback, MCP, and session metadata CRUD

---

## 8. Backend Completeness Gate Before Frontend

Before frontend rewiring begins, the backend path must be complete enough to
validate managed execution without browser assumptions.

That gate must cover:

1. Team-scoped managed execution remains authoritative even when a runtime pod
   also exposes the same capability through raw `agent_id` or template listing.
2. A team-scoped call resolved through `agent_instance_id` behaves correctly
   end-to-end for execution, history, checkpoints, and resume.
3. The runtime CLI (`fred-agent-chat`) remains a first-class validation
   consumer for managed team-scoped flows, not only raw template calls.
4. Runtime observability is enriched consistently for logs, KPI, metrics, and
   tracing payloads, including exports to Langfuse.

Required observability identity set:

- `user_id`
- `team_id`
- `agent_instance_id`
- `template_agent_id` when known
- `session_id`
- `checkpoint_id` when relevant
- `trace_id`
- `correlation_id`
- runtime identity (`runtime_id` or equivalent pod/service discriminator)

If these guarantees are not yet true in code, do not bypass them by starting
the frontend SSE migration early.

---

## 9. Continuation Gate After Phase 3a

Phase 3a is now implemented as a read-only product surface.

Further coding should continue only if these gates remain true:

1. New control-plane APIs describe product metadata, not runtime execution.
2. Managed agent APIs use `agent_instance_id` as the primary frontend identity.
3. Session APIs in control-plane stay metadata-only; history remains in runtime.
4. No new control-plane DTO depends on `agentic-backend` runtime transport
   types.
5. Frontend rewiring stays blocked until the Phase 3b backend completeness gate
   is green.
6. The next control-plane slices stay minimal and typed before broad CRUD or
   frontend rewiring.

If any of these are not true, stop and update this document and `BACKLOG.md`
before adding more code.
