# Control Plane Product Contract — Phase 3a

> ✅ **`prepare-execution` issues no `ExecutionGrant` (RUNTIME-07 rev. 2, 2026-06-28 — RFC
> decision D5).** The control-plane is the **catalogue + display-filtering + resolution**
> authority: `prepare-execution` returns the runtime URLs and the session's resolved context,
> never an authorization token. Authorization happens at the agent pod (Keycloak JWT +
> pod-side OpenFGA on `runtime_context.team_id`). Any `ExecutionGrant` / grant-issuance /
> `.well-known/grant-jwks` mention left below is a historical record, marked as such. See
> [`RUNTIME-EXECUTION-CONTRACT.md`](./RUNTIME-EXECUTION-CONTRACT.md) §2.2 and §8.11.

> ✅ **Service-agent team gate — 2026-07-01 (EVAL-03 / RFC EVAL-AUTH, Solution A).**
> The shared team check `_validate_team_and_check_permission` now recognizes a **service
> identity** (`service_agent` role — the evaluation worker) for **read-only** team access
> (`can_read`), **scoped to the request `team_id`**, without any OpenFGA tuple. A **write**
> permission (e.g. `can_update_agents`) is NOT bypassed: it falls through to the normal
> ReBAC check and is therefore denied (the worker holds no team relation). Regular users
> are unchanged. This covers the `prepare-execution` path the async worker calls.

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
- `apps/control-plane-backend/control_plane_backend/main.py`
- `apps/frontend/src/common/config.tsx`
- `apps/frontend/src/rework/components/pages/TeamAgentsPage/TeamAgentsPage.tsx`
- `apps/frontend/src/rework/components/shared/organisms/ChatList/ChatList.tsx`

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
- team-scoped prompt library CRUD
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
- pod-side execution authorization (Keycloak JWT + OpenFGA on `runtime_context.team_id`)

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
    - `Team.my_relations` — **added 2026-08-08 (#2298).** Each `available_teams`
      entry now carries the caller's own folded role relations
      (`team_admin`/`team_editor`/`team_analyst`/`team_member`), the same
      unambiguous field `active_team`/`TeamWithPermissions` already exposed.
      Moved onto the base `Team` model (it is caller-specific, exactly like the
      pre-existing `Team.is_member`) so the Home team list can render per-team
      role labels without a per-team refetch. Costs **no extra ReBAC read**: the
      value is sliced from the `roles_by_user` fold `_bulk_team_membership`
      already computes per team (it was previously discarded). Empty list for
      the personal/system space and for any team the caller is not a member of.
  - `gcu_version`
    - optional Terms of Use / CGU gating switch exposed by deployment config
  - `feature_flags`
  - `permissions`
  - `upload_warning`
    - optional deployer-configured upload notice (severity + locale→message
      map) shown on upload surfaces — see Contract Note §23 (MIGR-01.01)

`FrontendBootstrap` must not carry deployment branding labels. Static branding
and frontend display strings (`siteDisplayName`, `siteTitle`, `siteSubtitle`,
agent nicknames, logos, favicons, banners, support links) are owned by the
frontend static configuration surface, `config.json` `properties`, so a
deployment has one branding source of truth. The former control-plane
`ui_settings` bootstrap block was removed; do not reintroduce a parallel
branding channel in control-plane.

Permissions are exposed via:

- `PermissionSummary`
  - `is_platform_admin`, `is_platform_observer` — the only fields, both
    OpenFGA-derived (organization `platform_admin`/`platform_observer`
    relations). See Contract Note §14 (AUTHZ-05 review item 11): the former
    `items` flattened-permission list and six unwired `can_*` booleans were
    removed — they were Keycloak-role-derived and had gone permanently empty
    once AUTHZ-05 removed Keycloak app roles.
  - no raw RBAC/REBAC graph internals

Org-level gating stops at these two booleans. Team-scoped gating (agents,
resources, member administration, evaluation, …) does not belong on
`PermissionSummary` at all — it is exposed per team on
`TeamWithPermissions.permissions` (`list[TeamPermission]`), already returned
by every team-fetching endpoint. Permission booleans/lists must reflect the
product actor model defined in `docs/swift/platform/REBAC.md §Product
authorization model`. In particular: `team_admin` and `team_editor` are
orthogonal — a flag true for one must not imply it is also true for the
other.

Keep this contract small and frontend-oriented. If it becomes insufficient,
extend `FrontendBootstrap`; do not add parallel bootstrap DTOs.

Terms-gating behavior and current deployment limitations are documented in
[`docs/platform/TERMS_OF_USE.md`](../platform/TERMS_OF_USE.md).

#### 3.1.1 Public pre-auth config (FRONT-08)

`FrontendBootstrap` is authenticated and answers post-login product questions. It
**cannot** carry the "is user security enabled?" decision: the frontend must make
that decision *before* it can authenticate (chicken-and-egg). That single pre-auth
value is served by a separate **public (unauthenticated)** surface:

- `GET /control-plane/v1/frontend/config` → `FrontendConfig`
  - `user_auth` → `FrontendUserAuthConfig`
    - `enabled`
    - `realm_url` — emitted only when `enabled`
    - `client_id` — emitted only when `enabled`
  - `gcu_version` — **added 2026-06-22 (FRONT-10)** — active Terms-of-Use / CGU
    version the deployment requires, or omitted/`null` when gating is off. This
    is the **authoritative** source the frontend GCU guard reads.
  - `info_banner` — **added 2026-08-19** — optional deployer-configured
    global announcement banner (`platform.frontend.info_banner`), rendered
    full-width above the app on every page. Omitted/`null` → nothing
    rendered. See §42 for why it is pre-auth.

The handler derives `user_auth` directly from `fred_core` `SecurityConfiguration.user`
(`security.user`), the same config that drives backend JWT validation — so the backend
is the single source of truth and the frontend `config.json` no longer pins it. This
restores the production (`main`) pattern (`…/config/frontend_settings`). The surface is
intentionally minimal: **only** the public values the frontend needs before login —
the OIDC client values and the CGU gating switch. It must not grow into a second
bootstrap payload — no secrets (client secret, M2M, ReBAC internals), no
team/session/product state. Those stay on the authenticated `FrontendBootstrap`.

**Why `gcu_version` lives here and not (only) on the bootstrap.** The CGU version
is a pre-auth value for the same reason `user_auth` is: the GCU guard must decide
whether to show the acceptance page *before* the user has accepted, but
`/frontend/bootstrap` is `get_current_user`-gated and **403s with
`user_not_accept_gcu` until acceptance** — it cannot deliver the version needed to
render its own acceptance page (chicken-and-egg, FRONT-10). `build_frontend_config`
reports the **effective** value (mirroring the `get_current_user` predicate): `null`
whenever `security.user.enabled` is false or `app.gcu_version` is unset, so no-CGU
and standalone/dev deployments are never routed to the acceptance screen.
`FrontendBootstrap.gcu_version` is kept as a post-auth informational mirror (control-plane
CLI display) and must **not** be used to gate the UI. See
`docs/swift/platform/TERMS_OF_USE.md`.

#### 3.1.2 Root platform-admin bootstrap (AUTHZ-07, added 2026-07-13, revised 2026-07-15)

- `POST /control-plane/v1/bootstrap/platform-admin` → `BootstrapPlatformAdminResponse`
  - Request: `{ token: str }`, `min_length=16` (422 below the floor) — no
    `identifier` field. The grant always targets the calling JWT's own
    `sub`; this endpoint cannot promote a third party under any input.
  - Response: `{ user_id: str, username: str }` — the caller's own identity,
    now `platform_admin`.

**Requires authentication** (`get_current_user` — a valid Keycloak JWT) **and**
the deploy-time secret. Neither alone is sufficient: the JWT proves a real
identity in this realm, the secret proves legitimate deploy-time access. This
does not reopen the bootstrap chicken-and-egg — Keycloak authentication
depends on nothing Fred/OpenFGA owns, only *authorization* did, and there is
none here. The secret is never generated or logged by Fred, in any
environment: it is supplied externally, via `bootstrap_token_env_var` (an
environment variable sourced from a Kubernetes Secret — the deployment's
existing secrets pipeline, RFC-0001 §6) or `bootstrap_token_file` (local dev
only, created explicitly with `make bootstrap-token`).

Permanently refuses (409) once root bootstrap has ever completed — a durably
persisted marker (`PlatformBootstrapStore`), **not** a live count of
`platform_admin` relations. Removing every `platform_admin` later must not
silently reopen this endpoint; that is a separate, deliberate break-glass
recovery procedure, not a side effect of bootstrap. Refuses (503) if ReBAC is
disabled in this deployment — checked before the durable marker is written,
since granting would otherwise be a silent no-op that still burns the
one-time completion. Also refuses (503) if authentication (Keycloak/OIDC) is
disabled in this deployment — checked even before the ReBAC guard, since a
mocked identity would make the JWT proof meaningless (same shape as
Kubernetes' cluster-admin bootstrap, ArgoCD's `argocd-initial-admin-secret`,
Rancher's bootstrap password, and Keycloak's own `KC_BOOTSTRAP_ADMIN_*`
variables) — replaces the config-seeded
`platform_admin_subjects`/`platform_observer_subjects` path entirely (removed
from `security.rebac` config, AUTHZ-07 Step 6). No path grants a platform
role from deployment config anymore; the only other path is the declarative
platform import (§27).
Endpoint authorization matrix entry:
`docs/swift/platform/authz-endpoint-matrix.yaml` (`external_or_public`).

**`FrontendConfig` gating fields (revised 2026-07-15).** `GET /frontend/config`
(§3.1.1) carries two distinct root-bootstrap booleans — do not conflate them:

- `root_bootstrap_completed` — the truthful **durable historical marker**.
  True once `POST /bootstrap/platform-admin` has ever succeeded, permanently,
  per §3.1.2 above (`PlatformBootstrapStore`). Never reinterpreted based on
  live `security.user`/ReBAC state.
- `root_bootstrap_required` — the **authoritative frontend gating decision**
  for `BootstrapGuard`. Computed by `build_frontend_config()` as
  `security.user.enabled AND security.rebac.enabled AND NOT
  root_bootstrap_completed`.

These necessarily diverge on deployments where user authentication or ReBAC is
disabled: `root_bootstrap_completed` stays `false` on a fresh database (no one
has ever bootstrapped it), but `POST /bootstrap/platform-admin` deliberately
refuses with 503 there (auth-disabled and ReBAC-disabled guards above), so the
bootstrap form can never succeed. Before this revision, `BootstrapGuard` gated
directly on `NOT root_bootstrap_completed` and was permanently trapped on that
unusable form on such deployments (the default insecure/dev configuration
included). `root_bootstrap_required` is the fix: the frontend must gate on it
exclusively and must not re-derive the auth/ReBAC predicate itself.

### 3.2 Managed agent discovery

Two distinct concepts:

**`AgentTemplateSummary`** — what can be instantiated (read-only, derived from runtime pod catalog):

- `template_id` — composite `"{source_runtime_id}:{source_agent_id}"`
- `source_runtime_id`, `source_agent_id`
- `display_name`, `description`, `category`
- `tags`, `capabilities`, `team_instantiable`, `status`
- `default_tuning_fields: list[ManagedAgentFieldSpec]` — field descriptors the frontend renders dynamically at enrollment
- `default_capability_ids: list[str]` — **added 2026-08-28 (#2458).** The
  capability ids the template activates by default, verbatim from the pod's
  `definition.default_mcp_servers`. Deliberately NOT filtered by the team's
  `can_use`, unlike `available_capabilities` beside it — see §45.
- `mcp_servers: list[ManagedMcpServerRef]` — MCP tool references advertised by the template; `display_name` enriched from the pod's MCP catalog; `config_fields` for per-instance tool configuration declared by the tool catalog

The control plane is a **pure proxy** for these values — it does not interpret them. The runtime pod is the author; the control plane aggregates and forwards.

**`ManagedAgentInstanceSummary`** — a team-scoped enrolled instance (DB-backed):

- `agent_instance_id` — primary identifier
- `team_id`, `template_id`
- `display_name`, `description`, `status`
- `role: str` — **added 2026-07-23 (#2076).** Short one-line summary of what
  the agent does, distinct from the longer `description`; shown on the agent
  card. Independently settable via `CreateAgentInstanceRequest.role` /
  `UpdateAgentInstanceRequest.role` (both optional); server-defaults to
  `display_name` when omitted at creation, and is left unchanged on update
  when omitted.
- `usage_statement: str` — **added 2026-07-24 (#2105).** User-authored
  statement of the agent's intended use (purpose, target/impacted users,
  data handled, outputs, error impact), captured by the agent form's
  Engagement tab and used to screen for platform/organization risk. Stored
  inside the `ManagedAgentTuning` JSON blob (`tuning_json` column) like
  `role`/`description` — no dedicated DB column, no migration.
  Hard-required (`min_length=1`) on `CreateAgentInstanceRequest`. Optional
  on `UpdateAgentInstanceRequest` (omit = leave unchanged, same convention
  as `role`) so partial updates that don't touch content — e.g. the
  enable/disable toggle, which PATCHes only `status` — are unaffected.
  Requiredness for pre-#2105 agents (whose stored value defaults to `""`)
  is enforced by the agent edit form blocking Save when empty, the same
  pattern already used for `display_name`, not by the API contract itself.
- ~~`effective_chat_options: EffectiveChatOptions`~~ — **REMOVED 2026-07-11 (CAPAB-01 #1976).** `EffectiveChatOptions` is retired; chat controls are a session-prep projection shipped on `ExecutionPreparation.chat_controls`, not a listing-surface field. The composer fetches them via an eager prepare-execution at chat open.
- `created_at`, `updated_at`, `created_by`
- `tuning_field_values: dict[str, TuningValue]` — frozen snapshot of user-set
  agent tuning values at enrollment; keys constrained to
  `ManagedAgentFieldSpec.key`
- `mcp_config_values: dict[str, dict[str, TuningValue]]` — per-server MCP
  configuration keyed by server id then config-field key
- `selected_mcp_server_ids: list[str] | null`
  - `null` = inherit template default selection (all declared servers active)
  - `[]` = activate no MCP servers
  - non-empty list = activate exactly that subset

Do not expose runtime pod URLs or Kubernetes topology to the frontend.

**`ManagedAgentFieldSpec`** — field descriptor (shared between tuning fields and MCP `config_fields`):

- `key`, `type`, `title`, `description`, `required`, `default`, `enum`, `min`, `max`, `pattern`, `item_type`
- `ui: ManagedAgentUiHints` — `hide`, `group`, `multiline`, `textarea`, `max_lines`, `placeholder`, `markdown`

#### Managed tuning taxonomy

`ManagedAgentFieldSpec.key` values are not one undifferentiated bag.

For the first `swift` release, treat them as three distinct families:

- `prompts.*`
  - author-defined instructions
  - `prompts.system` is the broad per-instance system prompt override
  - `prompts.<step_or_operation>` is a narrower phase-specific prompt
- `settings.*`
  - typed business or runtime behavior knobs
  - thresholds, limits, booleans, delays, verbosity flags
- `chat_options.*`
  - frontend-only chat configuration hints
  - whether the UI exposes attachments, library pickers, document pickers, and similar affordances

This split is intentional:

- the control plane remains a pure proxy for field descriptors and stored values
- the frontend may render all three families
- the runtime should only interpret the families that belong to execution
- on create/update, control-plane validates known values against the declared
  field contract (type, enum, min/max, pattern) before persisting them
- when the frontend imports a saved prompt, the prompt text is copied into the
  matching `prompts.*` key; managed agent instances do not store a `prompt_id`
  or any other live prompt-library reference
- MCP `config_fields` are **not** stored in `tuning_field_values`; they live in
  dedicated `mcp_config_values` keyed by server id

Do not model platform-owned selectors as generic tuning fields. In particular:

- MCP server selection belongs in typed managed-agent contract fields such as
  `selected_mcp_server_ids`
- model selection belongs in typed managed-agent contract fields such as
  `model_profile_id` and the model-routing policy surface

**`ManagedMcpServerRef`** — MCP tool reference in a template:

- `id` — logical server id
- `display_name` — human label (enriched from runtime MCP catalog at proxy time)
- `require_tools: list[str]` — tool names the agent requires
- `config_fields: list[ManagedAgentFieldSpec]` — configurable parameters owned by the MCP tool and persisted via `mcp_config_values`

### 3.3 Runtime binding stays internal

`RuntimeBinding` is not a primary frontend product contract.

It exists so control-plane can resolve:

- one `agent_instance_id`
- one runtime-facing agent reference
- one runtime identity/binding payload

Use it for runtime resolution and backend validation only.

**Field value forwarding:** `ManagedAgentTuning.values` (the user-set field values
dict) is forwarded verbatim as `AgentTuning.values` in the runtime binding
response. `ManagedAgentTuning.mcp_config_values` is forwarded separately as
`AgentTuning.mcp_config_values`.

Execution semantics:

- all known values are forwarded for all agent types so the runtime or frontend
  can read them through the normal typed surfaces
- `prompts.system` is special:
  - ReAct/Deep runtime also mirrors non-blank `prompts.system` onto
    `ReActAgentDefinition.system_prompt_template`
  - blank value means "keep the author-defined default prompt"
  - Fred's shared global base prompt (the Mermaid output contract) is **not**
    part of this editable value or the author-defined default. It is appended by
    the runtime at execution time, after the effective/overridden prompt
    (RUNTIME-09; see RUNTIME-EXECUTION-CONTRACT §8.12), so it applies uniformly
    even when an operator overrides `prompts.system` and never appears in the
    agent editor.
- Graph agents read prompt and setting values through `context.tuning_values`
- tool-owned chat affordances are computed on the pod by
  `capability.chat_controls(config)` and shipped as
  `ExecutionPreparation.chat_controls` (CAPAB-01 #1976; the old
  `mcp_config_values → effective_chat_options` resolution is retired)

This contract is intentionally narrow:

- prompt fields describe instructions
- settings fields describe agent behavior
- chat-time UI affordances are computed capability controls
  (`ExecutionPreparation.chat_controls`, RFC §3.3/§3.7), not a stored option set
- MCP/model selection stays in dedicated typed product/runtime contracts

### 3.4 Managed agent instance writes

Freeze typed write payloads before implementing CRUD:

- `CreateAgentInstanceRequest`
- `UpdateAgentInstanceRequest`
- `DeleteAgentInstanceResponse` only if a non-empty response is needed

These requests should describe product intent, not runtime wiring internals.

### 3.5 Session identity, metadata, and observability

_This section supersedes `SESSION-IDENTITY-CONTRACT.md` (deleted 2026-05-11 — content merged here)._

#### 3.5.1 The one identifier: `session_id`

**`session_id` is the only public identity for a conversation.**

It is a caller-supplied or frontend-generated UUID that uniquely identifies one
multi-turn conversation between a user and an agent.

Rules:

- `session_id` is the primary key used in every public API, every CLI command, every log line, and every metric dimension that refers to a conversation.
- `session_id` must never be called `thread_id`, `conversation_id`, or any other synonym in any public-facing surface (API, CLI, docs, UI).
- `session_id` is generated by the frontend (or CLI) before the first message is sent and remains stable for the lifetime of the conversation.
- For one-shot calls with no `session_id`, the runtime generates a per-request UUID. That UUID is ephemeral and not tracked by any registry. One-shot calls produce checkpoint state that will never be resumed.

**`thread_id` implementation note (internal only):**

Internally, LangGraph requires a key named `thread_id` in its `configurable` dict to address checkpoint state. Fred maps `session_id → thread_id` at the adapter boundary in `react_message_codec.py`:

```python
configurable["thread_id"] = config.session_id
```

This mapping is a **private implementation detail of the LangGraph adapter**. It must never appear in any public API response field, CLI command name, documentation, or log line shown to end users. The LangGraph checkpoint tables store the value under a column named `thread_id` — this is also an implementation detail.

#### 3.5.2 Complete conversation record

A complete conversation record requires the following fields. All must be available for admin queries, retention policies, and audit.

| Field               | Source                            | Stored in                                 | Required        |
| ------------------- | --------------------------------- | ----------------------------------------- | --------------- |
| `session_id`        | Frontend / CLI                    | `session_history` (PK), checkpoint tables | ✅ always       |
| `user_id`           | Keycloak token / `ctx["user_id"]` | `session_history` (PK)                    | ✅ always       |
| `team_id`           | Execution context                 | `session_history`                         | ✅ managed exec |
| `agent_instance_id` | `RuntimeExecuteRequest`           | `session_history`                         | ✅ managed exec |
| `created_at`        | First message timestamp           | derivable from `MIN(rank)` row            | derived         |
| `last_active_at`    | Last message timestamp            | derivable from `MAX(rank)` row            | derived         |
| `exchange_id`       | Per-turn UUID                     | `session_history`                         | ✅ per message  |

For no-security / dev mode: `user_id` defaults to `"unknown"` and `team_id` defaults to `"personal"`. These must still be persisted so queries remain consistent.

#### 3.5.3 Data ownership split

The two types of conversation data have distinct owners and must never be merged.

**Session History (Message Content) — owned by `fred-runtime`**

Stored in the `session_history` table. Contains every message (user, assistant, tool calls, tool results), exchange grouping, timestamps, model metadata, token usage, sources, `team_id`, and `agent_instance_id`.

Accessed via:

- `GET /agents/sessions/{session_id}/messages` — full message list for one session
- `GET /agents/sessions` — session list for one user (or all users for admin)

**Control-plane must not proxy or cache message content.** If the frontend needs message history, it calls runtime directly using the `messages_url_template` from `ExecutionPreparation`.

**Session Metadata — owned by `control-plane-backend`** _(target state — implementation pending Phase 3b/FRONT-04)_

Will contain: session title (user-editable or auto-generated), creation timestamp, last activity timestamp, status (active, archived, deleted), preferences (language, display settings), `agent_instance_id` and `team_id` for sidebar grouping.

Session metadata is created by control-plane at `prepare-execution` time or on first turn. It is never stored in `fred-runtime`.

`session_metadata` also carries an internal-only `source_runtime_id` (captured from the
agent instance at `create_session` time, immutable, never returned by any API model). It
lets `ConversationErasureService` resolve the owning runtime for checkpoint/history erasure
even after the session's `agent_instance_id` row is later deleted — resolving solely through
the live instance row let an agent-instance deletion permanently block erasure of any session
that had used it (issue #2089, §35).

Until control-plane session metadata is implemented, the sidebar omits session listing. The intentional placeholder (no session list in sidebar) is acceptable. Adding a session list before the backend is ready is not.

**Checkpoint State — owned by `fred-runtime` checkpointer**

Stored in LangGraph tables (`checkpoints`, `blobs`, `writes`). Contains serialized graph state enabling HITL resume and multi-turn continuity. Keyed internally by `session_id` (stored in LangGraph's `thread_id` column).

Checkpoint state and message history are independent — deleting one does not delete the other.

#### 3.5.4 Session metadata contract models

Freeze session metadata as a control-plane contract separate from runtime history:

- `SessionListItem`
- `SessionAttachmentSummary`
- `CreateSessionRequest`
- `CreateSessionAttachmentRequest`
- `CreateSessionResponse`
- `DeleteSessionResponse` if needed
- `SessionPreferences`
- `UpdateSessionPreferencesRequest`

`SessionListItem` may include: `session_id`, `team_id`, `title`, `updated_at`, `created_at`, `agent_instance_id`, `context_prompt_ids` (ordered chat-context prompts — see §13).

`SessionAttachmentSummary` is the dedicated persisted attachment projection for the
managed chat drawer. Freeze it as:

- `attachment_id`
- `name`
- `mime`
- `size_bytes`
- `summary_md`
- `document_uid`
- `storage_key`
- `created_at`
- `updated_at`

Session attachment routes live under the existing session surface:

- `GET /teams/{team_id}/sessions/{session_id}/attachments`
- `POST /teams/{team_id}/sessions/{session_id}/attachments`
- `DELETE /teams/{team_id}/sessions/{session_id}/attachments/{attachment_id}`

It must not inline full message history.

#### 3.5.5 Admin observability requirements

The following capabilities are **mandatory** for any operator or system admin managing a Fred deployment. They must be achievable from the CLI without the frontend.

| Requirement                           | CLI command                | API endpoint                                    |
| ------------------------------------- | -------------------------- | ----------------------------------------------- |
| List all sessions for a user          | `/sessions [user_id]`      | `GET /agents/sessions?user_id=<id>`             |
| List all sessions across all users    | `/sessions --all`          | `GET /agents/sessions` (no filter, admin guard) |
| List all sessions for a team          | _(pending)_                | `GET /agents/sessions?team_id=<id>`             |
| List all sessions for a managed agent | _(pending)_                | `GET /agents/sessions?agent_instance_id=<id>`   |
| Read conversation messages            | `/history <session_id>`    | `GET /agents/sessions/{session_id}/messages`    |
| List checkpoint state                 | `/checkpoints`             | `GET /agents/checkpoints`                       |
| Inspect checkpoints for one session   | `/checkpoint <session_id>` | `GET /agents/checkpoints/{session_id}`          |
| Purge checkpoint state for a session  | _(CLI pending)_            | `DELETE /agents/checkpoints/{session_id}`       |
| Pod storage stats                     | `/stats`                   | `GET /agents/checkpoints/_stats`                |

The CLI must show for `/checkpoints` and `/sessions` listings: `session_id`, `user_id`, `team_id`, `agent_instance_id`, `latest_created_at`, a `◀` marker on the active session, and a `pending` warning when checkpoint writes are uncommitted (indicates a crashed turn).

**What admin must never need to know:** LangGraph's internal `thread_id` column name, checkpoint blob structure or serialization format, physical DB paths, or pod-internal service names.

#### 3.5.6 Retention and purge model

- **Retention policy is owned by control-plane**, not by `fred-runtime`.
- **Purge execution targets runtime APIs**, not direct DB access.
- `session_history` and checkpoint state are purged independently.

Planned purge surfaces:

| Target                           | Planned endpoint                                             |
| -------------------------------- | ------------------------------------------------------------ |
| Checkpoint state for one session | `DELETE /agents/checkpoints/{session_id}` ✅ exists          |
| Message history for one session  | `DELETE /agents/sessions/{session_id}` _(pending)_           |
| All data for one session         | Combined call to both above _(pending)_                      |
| Bulk purge by team / age         | `POST /agents/sessions/purge` with policy filter _(pending)_ |

**`session_purge_queue` — deferred-delete scheduler (CTRLP-12, §35):** The *scheduler* for governed deferred deletes: the delete button hides the conversation (`session_metadata.deleted_at`) and enqueues a `USER_DELETED` entry due at `now + window`. The queue is only a timer — the retention *mechanism* is `ConversationErasureService.erase_session` (which fans out over the runtime purge endpoints above plus KPI anonymise, attachments, and metadata). The lifecycle worker (`scheduler/lifecycle_actions.py`) invokes `erase_session` at expiry and marks the queue entry done only on `receipt.ok` — see §35 for the full contract.

**Soft-deleted session read contract (CTRLP-12 A5):** During the deferred-delete window a soft-deleted conversation is hidden from the session *list* (`list_by_team` filters `deleted_at IS NULL`) but remains directly fetchable by id (`SessionMetadataStore.get` does not filter `deleted_at`) and its attachments remain listable — intentional, to support a bounded post-incident / evaluation read. The row is fully erased only at window expiry. `DELETE /teams/{id}/sessions/{session_id}` returns 404 for a missing or non-owned session.

#### 3.5.7 Session lifecycle

```
Frontend / CLI
  │  1. generate session_id (UUID)
  │  2. call prepare-execution → ExecutionPreparation
  │  3. POST /agents/execute/stream  { session_id, agent_instance_id, ... }
Fred Runtime
  │  4. persist turn to session_history  { session_id, user_id, team_id, agent_instance_id }
  │  5. persist checkpoint state         { thread_id=session_id (internal) }
  │  6. emit TurnPersistedEvent          { session_id }
  │  ... subsequent turns reuse the same session_id ...
Control-plane  (target state)
  │  7. create session metadata record at prepare-execution or first turn
  │     { session_id, user_id, team_id, agent_instance_id, created_at, title }
```

#### 3.5.8 Open tasks — session admin

- [ ] `GET /agents/sessions` admin endpoint (no required `user_id`, filterable by `team_id`, `agent_instance_id`, date range)
- [ ] `DELETE /agents/sessions/{session_id}` to purge message history
- [ ] `POST /agents/sessions/purge` for bulk retention-policy execution
- [ ] Control-plane session metadata CRUD (Phase 3b / Phase FRONT-04)
- [ ] CLI `/sessions --all` and `/sessions --team <team_id>` commands
- [ ] CLI `/checkpoint delete <session_id>` command
- [ ] SQLite → Postgres migration path for existing `session_history` tables

#### 3.5.9 Open tasks — per-turn KPI observability

`exchange_id` is the per-turn identity that bridges session history and the KPI layer. It must appear in every KPI emission for a turn so that tool calls, LLM calls, and the final turn summary can all be correlated back to a single user request.

- [ ] `exchange_id` added to `_kpi_base_dims()` in `ContextAwareTool`
- [ ] `runtime_id` added to all KPI dims
- [ ] `session_id` and `user_id` removed from Prometheus label dimensions (high-cardinality — emit only via structured log/OpenSearch)
- [ ] `agent.turn_completed` KPI event emitted per turn with `session_id`, `exchange_id`, `user_id`, `team_id`, `agent_instance_id`, `total_latency_ms`, `llm_latency_ms`, `tool_count`, `input_tokens`, `output_tokens`, `model_name`, `finish_reason`
- [ ] `agent.llm_call` KPI event emitted per model invocation via `KPIWriter.log_llm()` (currently defined but never called)
- [ ] CLI `/kpi session <session_id>` command renders per-turn KPI table

### 3.6 Prompt library

Freeze prompt management as a first-class control-plane contract separate from
managed agent instances:

- `PromptSummary` (includes `published: bool`, PROMPT-06)
- `PromptDetail`
- `CreatePromptRequest`
- `UpdatePromptRequest`
- `PromptCategorySummary`
- `CreatePromptCategoryRequest`
- `UpdatePromptCategoryRequest`
- `MarketplacePromptSummary` (PROMPT-06 — `PromptSummary` + `team_id` +
  author `team_name`; preview only, no full text)
- `MarketplacePromptDetail` (PROMPT-06 — `PromptDetail` + `team_name`; full text)
- `MarketplaceImportRequest` / `MarketplaceImportResponse` (PROMPT-06)

Rules:

- prompt ownership is team-scoped
- the reserved system team `personal` is the personal prompt library; do not
  introduce a parallel user-scoped prompt API
- prompt `text` uses the same template-validation contract as agent
  `prompts.*` tuning values
- importing or saving a prompt from the agent form is a control-plane workflow,
  but the managed agent instance stores only copied `prompts.*` text, never a
  live prompt reference
- prompt categories are team-owned content (`category_id`, PROMPT-09) — there
  is no platform-wide category taxonomy and no platform default-prompt
  catalog; see §32 for the full contract change

The global prompt marketplace shipped 2026-08-10 (PROMPT-06, #2317) as a
**live visibility flag**, not a snapshot (this supersedes the earlier
snapshot-only requirement; see §33 and `PROMPTS.md` §6.1 for the rationale):

- publishing sets `PromptRow.published` on the team's own row — the marketplace
  shows that live record, so edits and the shared `session_count` usage counter
  propagate immediately; publishing never changes team ownership
- nothing persistently references the published row: *use* is a clipboard copy,
  *import* is copy-by-value (a fresh row via `promote`, counter reset to 0), so
  no agent instance or team prompt record ever points at a marketplace row
- only real team prompts are publishable; personal-space prompts stay private
- endpoints: `POST .../prompts/{id}/publish` and `.../unpublish`
  (`can_update_resources` on the author team), `GET /marketplace/prompts`
  (any authenticated user), `POST /marketplace/prompts/{id}/use` (open, published
  only), `POST /marketplace/prompts/{id}/import` (per-target
  `can_update_resources`, `_imported-N` naming)

### 3.7 Feedback

Feedback must align with managed execution semantics:

- use `agent_instance_id`, not only legacy `agent_id`
- stay product/audit oriented
- do not depend on runtime transport DTOs

### 3.8 MCP server administration

MCP endpoints belong in control-plane, but this migration should not drag the
entire legacy agent authoring model with them.

Prefer a neutral control-plane contract over direct reuse of
`agentic_backend.core.agents.agent_spec.MCPServerConfiguration` if reuse would
keep a hard dependency on `agentic-backend`.

### 3.9 Attachment metadata and file upload routing

**2026-06-18 — Decision refreshed (AGENT-FILESYSTEM):** Binary upload and agent
file exchange route through `knowledge-flow-backend`, not through the control-plane.

```
POST /knowledge-flow/v1/storage/user/upload   (knowledge-flow-backend, existing endpoint)
  Auth: Keycloak bearer token
  Body: multipart/form-data  { file }
  Response: { download_url, key, file_name, size, … }
```

The control-plane does not proxy or store binary content. File identity is a path in
the Knowledge Flow virtual filesystem. Users see four team-scoped roots:
`Resources`, `Mon espace`, `Espace d'equipe`, and `Agents`. Those map server-side to
canonical paths such as `/corpus/...`,
`/teams/{team}/users/{uid}/...`, `/teams/{team}/shared/...`, and
`/teams/{team}/agents/{agent_instance_id}/users/{uid}/...`. The agent uses the Knowledge
Flow MCP filesystem to read/write those paths through the simplified SDK/MCP
surface. The control-plane's role is session and instance management only; file
storage is `knowledge-flow-backend`'s responsibility.

This boundary is intentionally simple so that future skills can treat files as a
basic filesystem capability rather than a special control-plane feature. A skill
should only need to know the path model and the MCP filesystem primitives; it should
not need to learn a second storage abstraction owned by control-plane.

Implementation note: the system must stay compatible with open-source storage stacks
without hard-coding MinIO, OpenSearch, or any other specific vendor service into the
contract. Browser-facing download references remain Fred/Knowledge Flow links represented
as `LinkPart`; storage-provider URLs and credentials are implementation details.

Attachment metadata (filename, size, MIME type) may appear in `SessionListItem`
as display-only fields once CHAT-04 (attachment picker) is implemented.
See `docs/swift/design/FILESYSTEM.md`.

---

## 4. Implemented Surface (Phase 3a + 3c)

**Agent template discovery (read-only, runtime proxy):**

- `GET /teams/{team_id}/agent-templates` → `AgentTemplateSummary[]`
  - Aggregates live catalogs from all configured `runtime_catalog_sources`
  - `mcp_servers` enriched with `display_name` from runtime MCP catalog
  - Optional `?include_non_public=true` query (default false) — honored **only for
    platform admins**; lists internal (`AgentDefinition.public=False`) templates that are
    otherwise hidden from the create-agent catalog

> **2026-06-25 (VALID-02):** internal (`public=False`) agents are
> hidden from non-admins across control-plane paths. **Managed path** — listing honors
> `include_non_public` only for admins; `enroll_agent_instance` resolves with the caller's
> privilege, so a non-admin who guesses a hidden `template_id` gets 404, an admin may enroll.
> Enforcement is completed at the runtime, which refuses direct execution of
> non-public agents (`RUNTIME-EXECUTION-CONTRACT.md`).
>
> **2026-06-26 (VALID-02, amends the above):** the **direct path** is closed to non-public
> agents for *everyone*. `prepare_runtime_agent_execution` now resolves with
> `include_non_public=False` unconditionally → a hidden `agent_id` is 404 even for admins.
> Reason: the runtime refuses direct execution of non-public agents regardless of caller, so
> an admin direct-prepare would resolve an **unusable** target. Non-public agents are reachable
> only via the managed (enrollment) path; the direct/evaluation path serves public agents only.

**Agent instance CRUD (DB-backed, team-scoped):**

- `GET /teams/{team_id}/agent-instances` → `ManagedAgentInstanceSummary[]`
- `POST /teams/{team_id}/agent-instances` → `ManagedAgentInstanceSummary`
- `PATCH /teams/{team_id}/agent-instances/{id}` → `ManagedAgentInstanceSummary`
- `DELETE /teams/{team_id}/agent-instances/{id}` → 204

> **2026-07-17 (CAPAB-01, PR review finding — closes an unmet #1980 acceptance
> criterion).** `capability_ids` omitted (or explicitly `null`) on
> `POST`/`PATCH` no longer means "inherit the template's default MCP servers
> live, unchecked." It is resolved **once, at save time**, into an explicit
> list — the template's default capability ids narrowed to what the team
> currently `can_use` (ReBAC-filtered, no 403 for this implicit-default case)
> — and that resolved list is always what gets persisted in
> `ManagedAgentTuning.selected_capability_ids`; it is never left `null`.
> Previously a `null` selection skipped the `can_use` ReBAC check entirely at
> every layer (save, session prep, and the runtime's MCP-server activation),
> letting a team obtain an admin-gated capability for free by submitting no
> selection. Fixed with a required one-off backfill for instances persisted
> before this change.

**Execution preparation:**

- `POST /teams/{team_id}/agent-instances/{id}/prepare-execution` → `ExecutionPreparation`

**Session metadata:**

- `GET /teams/{team_id}/sessions`, `POST`, `PATCH`, `DELETE`

**Bootstrap:**

- `GET /frontend/bootstrap` → `FrontendBootstrap`

**Internal runtime helper (admin/ops only):**

- `GET /agent-instances/{agent_instance_id}/runtime` → `ManagedAgentRuntimeBinding`

All public endpoints are product/metadata-oriented and independent of runtime message transport.

---

## 5. Source Of Truth Map

| Concern                                  | Source of truth                                               | Notes                            |
| ---------------------------------------- | ------------------------------------------------------------- | -------------------------------- |
| Runtime execution contracts              | `docs/design/RUNTIME-EXECUTION-CONTRACT.md` + `libs/fred-sdk` | Do not redefine in control-plane |
| Product/session/admin migration sequence | `BACKLOG.md`                                                  | Phase order and next slice       |
| API ownership                            | `docs/platform/PLATFORM_RUNTIME_MAP.md`                       | Architecture boundary            |
| Phase 3a control-plane contracts         | this document                                                 | Product-surface source of truth  |
| Generated frontend runtime types         | `apps/frontend/src/slices/runtime/runtimeOpenApi.ts`               | Generated; never hand-edit       |
| Generated frontend control-plane types   | `apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts`     | Generated; never hand-edit       |

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

- managed runtime endpoint resolution payloads exposed to the frontend
- runtime history migration details beyond linking to `fred-runtime`
- frontend SSE transport migration
- prompt marketplace **moderation** surface (publication itself shipped
  2026-08-10, PROMPT-06 — see §39; only moderation remains deferred)
- removal of legacy `agentic-backend` code paths
- feedback CRUD and full MCP server administration surface

---

## 8. Backend Completeness Gate Before Frontend

Before frontend rewiring begins, the backend path must be complete enough to
validate managed execution without browser assumptions.

That gate must cover:

1. Team-scoped managed execution remains authoritative even when a runtime pod
   also exposes the same capability through raw `agent_id` or template listing.
2. A team-scoped call resolved through `agent_instance_id` behaves correctly
   end-to-end for execution, history, checkpoints, and resume.
3. The runtime CLI (`fred-agents-cli`) remains a first-class validation
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

---

## 10. Contract Notes — CHAT-08 (May 2026)

### `/documents/:uid` frontend route

A new frontend route `/documents/:uid` was registered in `router.tsx` (CHAT-08).
It renders `MarkdownDocumentViewer` using the Keycloak session token to call
`GET /knowledge-flow/v1/markdown/{uid}` — no signed URL or additional contract
changes are required.

`VectorSearchHit.citation_url` (schema unchanged) now has a valid navigation
target. The `SourceDetailModal` renders a conditional "Open document ↗" link to
`/documents/{source.uid}` when `source.uid` is known and non-empty.

---

## 11. Contract Notes — OPS-04 (June 2026)

### Task event stream — new product/admin surface

Three new endpoints added to `control-plane-backend` as part of OPS-04 (unified
task event stream). These are **product/admin surface** — they belong to
control-plane, not to the runtime execution contract.

```
POST   /api/v1/tasks
       Body:     StartTaskRequest  (oneOf discriminated by kind; see RFC §2.7)
                 kind="migration"  → params: { step_id, dry_run }
                 kind="ingestion"  → params: { resource_ids, profile }
       Response: 202  { task_id: uuid }
       no generic duplicate-task detection in P1
  Auth:     platform owner for kind="migration";
                 authenticated user for kind="ingestion"

GET    /api/v1/tasks/{task_id}/events
       Response: text/event-stream  (TaskEvent discriminated union, see RFC §2.1)
                 Replays task_event_log WHERE seq > Last-Event-ID, then streams live
                 Terminal state (succeeded | failed | cancelled) closes the stream
       Auth:     view rule — task creator, platform owner, or a CAN_READ_MEMBERS
                 member of the task's team (identical to GET /tasks; RFC §7.2).
                 Single owner: fred_core.tasks.authz.authorize_task_access.

POST   /api/v1/tasks/{task_id}/cancel
       Response: 202  (idempotent — no-op if task is already terminal)
                 404  if task_id not found
       409  if the task kind does not support cancellation
       Auth:     mutation rule — task creator or platform owner ONLY (deliberately
                 stricter than the view rule: a team reader may watch a task but not
                 cancel it). Single owner: authorize_task_mutation.
```

All request/response types are Pydantic models in `fred-core`; the frontend uses
generated `controlPlaneOpenApi.ts` types — no hand-written DTOs. Adding a new `kind`
requires model extension + OpenAPI + codegen regeneration (see RFC §2.5 for the rule).

For OPS-04 P2, migration tasks are treated as non-cancellable in the cockpit UI.
The generic cancel endpoint remains part of the product/admin surface for future
task kinds that support cooperative cancellation.

### Persistence

**One pair of tables per task-producing backend, prefixed by its owner** (settled
2026-08-14, issue #2170 — supersedes the "dedicated database per backend" design
in `TASK-EVENT-STREAM-RFC.md` rev. 4 §2.9, which was confirmed but never built):

| Owner           | Tables                              | Alembic tree           |
| --------------- | ----------------------------------- | ---------------------- |
| control-plane   | `cp_task_run`, `cp_task_event_log`  | `alembic_version_control_plane` |
| knowledge-flow  | `kf_task_run`, `kf_task_event_log`  | `alembic_version_knowledge_flow` |
| evaluation      | `task_run`, `task_event_log`        | its own database (provisioned 2026-07-07) |

- `<prefix>task_run` — current-state summary (one row per task, updated in place)
- `<prefix>task_event_log` — append-only event journal (one row per `TaskEvent`, source of truth for SSE replay)

Column definitions live once, in `fred_core.tasks.orm_models`, as declarative
mixins (`TaskRunColumns` / `TaskEventLogColumns`); each backend declares the
concrete pair on **its own** `Base` and hands the pair to `TaskStore` /
`TaskService.build` as a `TaskTables`. fred-core maps nothing itself.

**Why prefixes rather than a database per backend.** control-plane and
knowledge-flow share the `fred` database, and both mapped the *same* `task_run`
on the shared `CoreBase`. Nothing scoped either backend's `GET /tasks` to the
rows it created, so each returned the other's and the Activity page — which
queries every backend and merges client-side, by design — listed every task
twice. Distinct names per owner fix that at the schema layer with no new
infrastructure, no second engine, and no `RemoteTaskClient`-style coupling. They
also take these two tables out of the shared-`CoreBase` ownership ambiguity of
issue #2314: each pair now appears in exactly one backend's metadata, which is
what `make_alembic_env`'s `include_name` filter reads to decide what a tree owns.

Postgres scopes index names per schema, so **every** index and constraint name
embeds its table name (`ix_cp_task_run_kind`, `uq_kf_task_event_log_task_seq`, …)
— built by `task_run_table_args` / `task_event_log_table_args`, never hand-written.
`import_export/api.py` derives the single-active-migration index name it matches
in an `IntegrityError` from `single_active_migration_index_name` for the same reason.

Task rows are progress bookkeeping, so the split ships with **no backfill**. It
also does **not drop** the old shared `task_run`/`task_event_log`: they are left
orphaned for a later release. The two Temporal workers have no `migration:` block
in `deploy/charts/fred/values.yaml`, so they get no scale-down hook and keep
running old code — which writes the shared table through an unguarded activity
that is the first step of every push-file ingestion. Dropping it mid-deploy would
fail those workflows outright and lose the document, not just its task row.
Expand now, contract in a later release.

### Ownership boundary

`/api/v1/tasks*` is product/admin surface. It must never proxy runtime execution,
expose pod internals, or duplicate runtime authorization concerns. The task system
tracks job metadata and progress; it does not replace the runtime SSE contract
defined in `RUNTIME-EXECUTION-CONTRACT.md`.

RFC: `docs/swift/rfc/TASK-EVENT-STREAM-RFC.md`

---

## 12. Evaluation API Surface — EVAL-01 (June 2026)

### Ownership

The Control Plane owns campaign authorization, target resolution, task lifecycle,
canonical result persistence, and the product API consumed by the frontend.
The evaluation worker (a separate process/image) owns batch orchestration and scoring.
`fred-runtime` owns agent execution and `EvalTrace` production only.

### Models

```
EvaluationCampaign       — campaign record with operational state, verdict, and aggregates
EvaluationCaseResult     — per-case record with outcome, verdict, metrics, and errors
EvaluationMetricResult   — per-metric score, threshold, verdict, and explanation
EvaluationTarget         — discriminated union: ManagedInstanceTarget | RuntimeAgentTarget
```

Schema version field (`schema_version: Literal["1"]`) is mandatory on all models.

### Endpoints

```
POST   /control-plane/v1/evaluation-campaigns                        — create and start a campaign
GET    /control-plane/v1/evaluation-campaigns                        — list campaigns (scope, state, target filters)
GET    /control-plane/v1/evaluation-campaigns/{campaign_id}          — campaign detail
GET    /control-plane/v1/evaluation-campaigns/{campaign_id}/cases    — paginated case results
GET    /control-plane/v1/evaluation-campaigns/{campaign_id}/cases/{case_id}
```

Task progress and cancellation reuse generic task endpoints:
```
GET    /control-plane/v1/tasks/{task_id}/events
POST   /control-plane/v1/tasks/{task_id}/cancel
```

### Authorization

| Operation | Required permission |
| --- | --- |
| List/read team campaigns and results | `TeamPermission.CAN_READ` |
| Create a campaign for a team | `TeamPermission.CAN_UPDATE_AGENTS` |
| Cancel a running campaign | campaign creator, platform owner, or `CAN_UPDATE_AGENTS` on campaign team |
| Read own campaign | campaign creator |

No new OpenFGA relation is introduced in the MVP.

### Target resolution

The frontend never supplies raw runtime URLs or bearer tokens.
`runtime_id` must resolve via configured `runtime_catalog_sources`.
`agent_instance_id` must resolve via the existing managed instance model.
Unknown IDs are rejected with `422 Unprocessable Entity`.

### Server-side limits (strict — requests may choose lower values)

| Limit | Default | Hard max |
| --- | ---: | ---: |
| Cases per campaign | 50 | 200 |
| Concurrent cases | 3 | 10 |
| Agent execution timeout | 600 s | 900 s |
| Judge timeout per metric | 120 s | 300 s |
| Input size per case | 32 KiB | 64 KiB |

### RFC reference

`docs/swift/rfc/AGENT-EVALUATION-RFC.md` — EVAL-01 v2

## 13. Contract Notes — PROMPT-05 (June 2026)

> **Superseded in part by §32 (PROMPT-09, 2026-07-30):** every `lang`
> parameter and `default:{category}` prompt id described below no longer
> exists — the platform default-prompt catalog they served was removed. This
> section stays a historical record of the ordered-context-list decision
> itself, which is otherwise still current.

### Multi-prompt chat context — session context becomes an ordered list

**2026-06-19 — Decision (PROMPT-05 / `PROMPTS.md` §5):** a conversation
may have **0, 1, or many** prompts attached as chat context, cumulative and ordered.
This supersedes the single scalar `context_prompt_id` introduced in May 2026.

Backend changes (control-plane only; `fred-sdk` / `fred-runtime` untouched):

- **Persistence** — new ordered association table `session_context_prompts`
  (`session_id`, `prompt_id`, `position`, PK `(session_id, prompt_id)`,
  FK → `session_metadata.session_id` `ON DELETE CASCADE`). The scalar
  `session_metadata.context_prompt_id` column is dropped; the migration backfills
  each non-null scalar as the `position=0` row.
  (Alembic `e7f8a9b0c1d2_multi_prompt_chat_context`.)
- **`UpdateSessionRequest`** — `context_prompt_id` + `clear_context_prompt` are
  replaced by `context_prompt_ids: list[str] | None`. Semantics: a **present**
  field is a full ordered-set replacement (the server diffs, detaches removed ids,
  attaches new ones, rewrites `position`); `[]` or a present `null` **clears**; an
  **absent** field leaves the context unchanged (so freshness-only PATCHes never
  wipe attached prompts).
- **`SessionListItem`** — `context_prompt_id: str | null` → `context_prompt_ids:
  list[str]` (ordered; empty when none attached). Rehydrates the composer pills on
  session open.
- **`ExecutionPreparation.context_prompt_text`** — **unchanged scalar type**.
  Control-plane resolves each attached id in `position` order (library prompts via
  `PromptStore`, `default:{category}` via the platform defaults), skips
  stale/deleted ids silently, and concatenates with `\n\n` into the existing
  single field. Blast radius stays inside control-plane + frontend.
  **Scope (2026-07-06, PROMPT-08):** library-prompt resolution uses
  `PromptStore.get_for_team` over the caller's active team **and** personal team
  (the union the picker surfaces), not a raw primary-key `get(prompt_id)`. An id
  outside that scope is treated like a stale id — skipped, never resolved — so a
  session cannot pull another team's prompt text into its context.
- **`POST …/prepare-execution` `lang` query param** (added 2026-06-19) —
  optional, `default="en"`, mirroring `GET …/prompts/context`. Localizes
  `default:` prompt resolution so a French user gets the French default text shown
  in the picker; library prompts stay language-agnostic (stored text). The client
  sends the same UI lang it passes to `/prompts/context`. Back-compatible: absent
  ⇒ English. (`KeycloakUser` carries no locale, so lang must be threaded from the
  request.)
- **Usage** — `PromptRow.session_count` (and `default_prompt_usage`) increments on
  **first attach only** (id present in the new set, absent from the previous set);
  re-sending an attached id does not double-count; removing never decrements.

`controlPlaneOpenApi.ts` was regenerated (breaking field rename on
`UpdateSessionRequest` and `SessionListItem`). Shipped 2026-06-19 (PROMPT-05);
`ContextPromptSummary` also gained `category`. Authoritative design:
[`PROMPTS.md`](PROMPTS.md) §5.

## 14. Contract Notes — AUTHZ-05 review item 11 (2026-07-11)

### `PermissionSummary` shrunk to its two OpenFGA-derived booleans

**2026-07-11 — Decision (AUTHZ-05 post-implementation review, item 11):**
`PermissionSummary` dropped `items: list[str]` and six always-empty booleans
(`can_view_team_agents`, `can_manage_team_agents`, `can_manage_mcp_servers`,
`can_view_feedback`, `can_submit_feedback`, `can_create_sessions`). Both were
populated by `list_display_permissions()` (`fred_core/security/permission_catalog.py`,
now deleted), which iterated **Keycloak app roles** — removed platform-wide by
AUTHZ-05 review item 8a, so every seeded user had `app_roles: []` and these
fields were permanently empty/`false` for everyone, including `platform_admin`.
Live impact before the fix: 6 frontend routes and 3 in-page controls were
unreachable/disabled for all users.

`PermissionSummary` now carries exactly `is_platform_admin` and
`is_platform_observer` — unchanged, already OpenFGA-derived since review item
4. Team-scoped gating was never this field's job; it goes through
`TeamWithPermissions.permissions` (`list[TeamPermission]`), already returned
by every team-fetching endpoint and unaffected by this change.

`controlPlaneOpenApi.ts` was regenerated (`PermissionSummary` loses the 7
removed fields; no other change). Frontend consumption pattern documented in
[`docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md`](../platform/FRONTEND-AUTHZ-PATTERN.md).

## 15. Contract Notes — AUTHZ-06, cumulative team roles (2026-07-12)

### `TeamMember.relation` (singular) → `relations` (list)

**2026-07-12 — Decision:** a team member may now hold `team_admin`, `team_editor`, and
`team_analyst` on the same team simultaneously (e.g. a small team's sole
admin who is also its editor and evaluator) — the product's write path
previously enforced exactly one role per user per team. `schema.fga` did not
change: OpenFGA already permitted multiple relation tuples per user per
object; the exclusivity was a service-layer convention only.

`TeamMember.relation: UserTeamRelation` becomes
`TeamMember.relations: list[UserTeamRelation]` — the full set of roles the
member currently holds, priority-ordered (`team_admin` first, then
`team_editor`, then `team_analyst`, falling back to `[team_member]` when none
of the three elevated roles apply). Returned by `GET /teams/{team_id}/members`
and by `control_plane_backend/cli/main.py`'s member table.

### `PATCH /teams/{team_id}/members/{user_id}` retired

Replaced by two granular endpoints — grant/revoke one role at a time, never a
bulk role-set replace, so every change stays an individually
permission-checked, auditable action (same principle applied throughout this
RFC):

- `POST /teams/{team_id}/members/{user_id}/roles` — body
  `{"relation": UserTeamRelation}` (`GrantTeamMemberRoleRequest`, replaces
  `UpdateTeamMemberRequest`). Grants one additional role. Checked against
  `can_administer_{admins,editors,analysts,members}` for the granted role,
  exactly as before.
- `DELETE /teams/{team_id}/members/{user_id}/roles/{relation}` — revokes one
  role, leaving any other role the member holds untouched. Refuses to revoke
  a role not currently held (`404`) or a member's only remaining role
  (`409`, `TeamMemberLastRoleError` — that is a removal, not a role change;
  use `DELETE /teams/{team_id}/members/{user_id}` instead). The "team must
  keep at least one `team_admin`" guard applies exactly when `team_admin` is
  the role being revoked, by either this endpoint or a full member removal.

`AddTeamMemberRequest` (`POST /teams/{team_id}/members`, for a brand-new
member) and `DELETE /teams/{team_id}/members/{user_id}` (full removal) are
unchanged.

`controlPlaneOpenApi.ts` regenerated (`make update-control-plane-api`):
`TeamMember.relation` → `relations`, `UpdateTeamMemberRequest` replaced by
`GrantTeamMemberRoleRequest`, the PATCH member-role hook replaced by grant/
revoke hooks. `TeamSettingsMembersTable.tsx` (the only frontend consumer)
updated in the same change. Design detail: RFC Part 7 (§33-39).

## 16. Contract Notes — AUTHZ-07 Step 3, `TaskSummary.detail` (2026-07-14)

**Decision:** `TaskSummary` (`GET /tasks`) gains an optional `detail` field —
the last persisted per-kind detail (`IngestionDetail | EvaluationDetail |
TaskLogDetail | MigrationDetail | ErasureDetail | None`), typed per the
sibling `kind` field exactly like the existing per-kind `TaskEvent` union.
`None` for a kind with no detail model (`log`) or a task recorded before this
field existed — backward compatible, no migration. Rationale and full
backend/frontend design: §27 above,
`AUTHZ-MIGRATION-BACKLOG.md` Step 3.

`MigrationDetail.result: MigrationResult | None = None` is populated only on
the terminal `succeeded` event of a platform import — a typed projection of
the import's internal `MigrationReport` (every counter named in
`AUTHZ-MIGRATION-BACKLOG.md`'s Step 3 exit gate, plus `warnings: list[str]`).
A non-empty `warnings` list is what distinguishes a partial reconciliation
from full success; the task `state` stays `succeeded` either way — no new
`TaskState` value.

**`POST /import-export/import` — `ImportLaunchResponse.target: TaskTarget`
(2026-07-14, close-out amendment):** the launch response now returns the
exact `TaskTarget` the backend created the task with
(`type="platform_import"`, `id=import_id`, `label=` trimmed operator label →
uploaded filename → `"Platform import"` fallback — computed once in
`_import_target()`, never re-derived). Frontend consumers must register the
task with this returned `target` value, not reconstruct one locally — the
backend is the single source of truth for the target's precedence rules.

`controlPlaneOpenApi.ts` regenerated (`make update-control-plane-api`): new
`MigrationResult`/`MigrationDetail`/`ErasureDetail` schemas, `TaskSummary.detail`,
`ImportLaunchResponse.target`. Frontend: `TaskActivity.tsx` (the shared task/
activity surface, OPS-04 §3.4) narrows `detail` on `task.kind === "migration"`
to render the result; `launchPlatformImport.ts`/`MigrationPage.tsx` consume
`ImportLaunchResponse.target` directly (no hand-built duplicate).

**`POST /import-export/import` + new `POST /import-export/reset-full`
(2026-07-24, MIGR-05.18):** `POST
/import-export/import`'s multipart body gains an optional second field,
`realm_file` (a standalone Keycloak realm export JSON), which — when present
— the importer uses in place of the zip's own `keycloak/realm.json`. New
`POST /import-export/reset-full` (`ResetLaunchResponse`, same shape as
`/reset`) wipes the full platform configuration graph — Postgres, every
OpenFGA tuple, every Keycloak user — back to bootstrap-only state, preserving
only `platformbootstrap.completed_by` and the calling operator. Distinct
endpoint from `/reset`, which keeps its narrow data-only scope unchanged.
Both `/import` and `/reset-full` (and `/reset`) now reject (`409`) with an
active migration task already running/pending. `controlPlaneOpenApi.ts`
regenerated: `BodyImportSnapshotControlPlaneV1ImportExportImportPost.realm_file`,
`useResetPlatformFullControlPlaneV1ImportExportResetFullPostMutation` (aliased
`useResetPlatformFullMutation` in `controlPlaneApiEnhancements.ts`). Frontend:
`MigrationPage.tsx` gains a second optional dropzone (realm.json) and a
distinct "Full teardown" button/confirmation, never sharing a click target
with "Reset platform". New authz-endpoint-matrix.yaml row for `POST
/import-export/reset-full` (`pending_review`, matching its sibling rows).

## 17. Contract Notes — CAPAB-01 (July 2026)

### Admin capability-enablement routes

**2026-07-11 — Routes fixed (CAPAB-01, backend #1980, admin dashboard #1981).** The Tier 3 admin surface over the
capability enablement model. All routes are platform-admin-gated: the mutations
check `capability#can_manage` (the capability is anchored first, idempotently);
the aggregate list checks the equivalent `organization#can_manage_platform`.
Structural FGA tuples (`enabled` / `disabled` / `default_on`) are written **only**
through this surface — every other caller checks the computed `can_use`.
Implemented in `control_plane_backend/capabilities/api.py`, mounted under
`/control-plane/v1`.

**2026-07-16 — `can_use` subject corrected to the team.** No route shape
changed, but the enforcement semantics did: `can_use` is now checked with the
TEAM in the URL as subject (RFC §8.1 amendment). Consequence visible on this
surface: `GET /teams/{team_id}/agent-templates` filters each template's
`available_capabilities` to what THAT team can use — a capability enabled for
another of the caller's teams no longer appears (and can no longer be saved,
403) outside its enabled team.

| Method + path | Request | Response | Effect |
| --- | --- | --- | --- |
| `GET /admin/capabilities` | — | `CapabilityEnablementList` | Aggregated pod catalog with, per capability: `id`, `name` (i18n key), `version`, `icon`, `team_scope` (`default_on` \| `admin_gated`), `default_on`, `enabled_team_ids`, `team_settings_fields` (the enable-with-settings form specs), `default_capability_ids` (2026-08-25, see below). |
| `PUT /admin/capabilities/{capability_id}/teams/{team_id}` | `EnableTeamCapabilityRequest` (`settings`) | `TeamCapabilityEnablementResult` | Enable-with-settings: validates `settings` against `team_settings_fields`, writes the settings row then the `enabled` tuple. |
| `DELETE /admin/capabilities/{capability_id}/teams/{team_id}` | — | `TeamCapabilityEnablementResult` (`suspended_instances`) | Revoke: deletes the `enabled` tuple (writes a `disabled` opt-out for a default-on cap), reconciles dependent instances → suspension. |
| `PUT /admin/capabilities/{capability_id}/default-on` | `SetCapabilityDefaultOnRequest` (`default_on`) | `CapabilityDefaultOnResult` (`suspended_instances`) | Toggle the platform-wide `default_on` marker; turning it off revokes inherited access team-by-team and may suspend instances. |

`suspended_instances` on the two revoking mutations is the **delta** the action
caused (#1975 reconciliation), surfaced by the #1981 dashboard as post-action
feedback. Frontend consumes the generated hooks via the friendly aliases
`useAdminCapabilitiesQuery` / `useEnableTeamCapabilityMutation` /
`useDisableTeamCapabilityMutation` / `useSetCapabilityDefaultOnMutation` in
`controlPlaneApiEnhancements.ts`; the dashboard lives at `/admin/capabilities`.

**2026-07-16 — personal-space class scope (CAPAB-01 / #1961 amendment).** The personal-space capability class
is now pure FGA runtime state, admin-toggleable like `default_on` — replacing the
withdrawn config-only `platform.capabilities.personal_defaults` first-touch
seeding. One new route (org-admin-gated on `capability#can_manage`, same as
`/default-on`), and one new field on the aggregate list item.

| Method + path | Request | Response | Effect |
| --- | --- | --- | --- |
| `PUT /admin/capabilities/{capability_id}/personal-scope` | `SetCapabilityPersonalScopeRequest` (`scope: "enabled" \| "disabled" \| "default"`) | `CapabilityPersonalScopeResult` (`scope`, `suspended_instances`) | Set the personal-space class tri-state: `enabled` writes the `personal_on` org tuple (usable by ALL personal spaces), `disabled` writes `personal_disabled` (blocked for all), `default` clears both. Idempotent. A transition that loses access for personal spaces (enabled→disabled, enabled→default without default_on, default→disabled with default_on) suspends dependent **personal-space** instances whose team lacks an explicit `enabled` grant. `enabled` is rejected (409) for a capability with a required team setting, mirroring `default_on`. |

The `GET /admin/capabilities` item gains **`personal_scope`** (`"enabled" \|
"disabled" \| "default"`), derived from the two org-subject class tuples, and
**`total_personal_space_count`** (the realm user count — one personal space per
user; `0` = user directory unavailable, read as "unknown" like
`total_team_count`), the denominator the dashboard uses to render personal-class
reach as an `X personal space(s)` line under the team count. Precedence
across the whole matrix: a team's explicit `enabled`/`disabled` beats the
personal-class position, which beats `default_on`. Frontend consumes the
`useSetCapabilityPersonalScopeMutation` friendly alias; the team-matrix drawer
renders the class as a synthetic pinned "All personal spaces" first row and drops
the admin's own personal team from the ordinary per-team rows.

**2026-07-17 — agent templates join this surface (CAPAB-01).** `CapabilityEnablementItem` and
`CapabilityCatalogEntry` gained `kind: "tool" | "agent"` (defaults `"tool"`,
so existing rows are unchanged). `GET /admin/capabilities` now also lists a
`kind="agent"` row per registered agent template (control-plane-side
projection — never a runtime pod change), enabled/disabled through the exact
same `PUT`/`DELETE .../teams/{team_id}` and gated the exact same way. The
frontend (`FeaturesPage.tsx`) filters the one dataset by `kind` (a
"Tools"/"Agents" toggle) rather than adding a second page or route. Also
newly gated on `can_use`, using the same `capability` object space with id
`f"{runtime_id}__{agent_id}"`: `GET /teams/{team_id}/agent-templates` (hides
a template the team isn't granted, not just its nested
`available_capabilities` as before) and `POST /teams/{team_id}/agent-instances`
(404 on an ungranted `template_id`, matching the existing non-public-template
anti-guessing convention).

**Known gaps (deferred, tracked on #1975 / a future enablement-list extension):**
no **resting** per-capability suspended-instance count (only the mutation delta
exists — the suspension row records a typed reason, not the causing capability
id). The config-only `platform.capabilities.personal_defaults` list was removed
by the 2026-07-16 §8.4 amendment (replaced by the `personal-scope` route above).

**2026-07-16 (merge with swift) — `can_manage` re-anchored to `platform_admin`.**
AUTHZ-05 removed the legacy Keycloak `admin`/`editor`/`viewer` organization-role
bridge before this branch merged; `capability#can_manage` (`schema.fga`) is
updated in the same change from `admin from organization` to `platform_admin
from organization`, matching every other org-admin-tier capability. No route
shape or request/response change — enforcement now resolves through
`platform_admin` instead of the retired `admin` relation.

**2026-07-19 — `depends_on` gate for `kind="agent"` capabilities (GitHub
#2004, CTRLP-14).**
`CapabilityCatalogEntry` gained `default_capability_ids: tuple[str, ...]`
(the template's default tool/MCP capabilities, empty for `kind="tool"`).
`PUT /admin/capabilities/{capability_id}/teams/{team_id}` and
`PUT .../personal-scope` (`scope="enabled"`) now also 409 for a `kind="agent"`
entry when the team (or, for personal-scope, every personal space) isn't
already `can_use` on all of its `default_capability_ids` — prevents enabling
an agent whose tools aren't granted yet. `PATCH /teams/{team_id}/agent-instances/{id}`
now 403s once the instance's own template grant is revoked (previously only
*tool* capability selections were re-checked on update; unenroll is still
always allowed).

**2026-07-26 — `kind="model"`, a third projection (CAPAB-01/OBSERV-02).**
`CapabilityCatalogEntry`/`CapabilityEnablementItem.kind` widens to `"tool" |
"agent" | "model"`. A model entry is a **catalog projection, not an authored
manifest** — like `kind="agent"`, no one hand-writes a `kind="model"`
`CapabilityManifest`; `models_catalog.yaml` (fred-agents, loaded by
`fred_runtime.model_routing.catalog`) stays the sole source of truth for
routing. Every mechanism already built for `kind="tool"`/`kind="agent"` —
schema, `can_use`, the enablement write path, the admin dashboard — governs
`kind="model"` uniformly; `FeaturesPage.tsx` needed only a widened
`KIND_FILTERS` value and one i18n key, no `kind`-specific branch anywhere
else (the team matrix, health column, and default-on toggle are all
kind-agnostic).

**Catalog projection, cross-pod.** `fred-runtime` exposes
`GET /agents/models-catalog`, projecting `catalog.profiles` into one entry
per distinct `(provider, name)` pair — not per `profile_id` (a concrete model
has one enablement decision even if different typed consumers eventually use
it) — and deriving the id itself
(`model_capability_id(provider, name)`, fred-sdk). Control-plane
(`product/service.py::_model_capabilities_for_source`) fetches that endpoint
per runtime source as a third catalog fetch alongside the existing tool and
agent fetches (same best-effort contract — `None` on an unreachable pod),
under the reserved-prefix collision guard `MODEL_CAPABILITY_NAMESPACE_PREFIX`
(`model__`). **Multi-pod collision is a union, not last-write-wins**: on an id
collision across pods, `aggregate_capability_catalog` unions
`model_profile_ids`/`model_thinking_profile_ids` rather than letting the last
pod fetched overwrite the entry (fixed 2026-08-01 — the original
last-registration-wins shape silently dropped profiles from whichever pod
lost the race).

**`CapabilityCatalogEntry` is not a uniform shape across kinds — it is a
tagged union in practice.** `model_profile_ids: tuple[str, ...]`,
`model_chat_profile_ids: tuple[str, ...]`, and
`model_thinking_profile_ids: tuple[str, ...]` (REASON-01, §33) are real
fields carried **only** for `kind="model"` — empty for `tool`/`agent`, never
the reverse. `config_fields`, `team_settings_fields`, `assets`, and
`default_capability_ids` are conversely always empty for `kind="model"`.
Treat `kind` as the discriminator when reading this type; a per-kind field
being present or empty is the contract, not an implementation detail to
paper over. `model_profile_ids` preserves every profile for model enablement;
`model_chat_profile_ids` is its explicitly typed chat subset and is the only
subset the V1 team-routing picker/write path consumes. Capability is never
inferred from a profile-id prefix.

**Runtime enforcement is fail-closed and differs by kind, deliberately.**
`kind="tool"`/`kind="agent"` enforce at **write time** —
`can_team_use_capability`
gates tool selection and template enrollment, and both suspend/revive
dependent agent instances on revocation/grant (`enablement.py`, `impact.py`).
`kind="model"` has no equivalent write-time surface (model choice is a
per-turn runtime decision), so it enforces **per turn** instead:
`usable_model_capability_ids(rebac, team_id)` — the pod's own local OpenFGA
`ListObjects` query, computed once per turn at the same point
`_authorize_execution_or_raise` runs (not inside model routing itself) —
threads through `BoundRuntimeContext.usable_model_ids` (`None` = ReBAC
disabled, no restriction; a non-`None` tuple = exactly what's allowed).
`RoutedChatModelFactory.build_for_chat` checks the resolved model against it
and fails closed (`ModelNotUsableError`), never silently substituting. The
query itself lives in one place —
`fred_core.security.rebac.capability_authz.usable_capability_ids` (moved
2026-08-03; control-plane's `capabilities/authz.py` re-exports it,
fred-runtime's `usable_model_capability_ids` wraps it with the
ReBAC-disabled tolerance and `kind="model"`-prefix filter that are
runtime-specific) — not two independently-maintained copies.

**No auto-seeding migration, by design.** No team holds an explicit
`can_use` grant on any `model__*` capability until a `platform_admin`
opts one in via the existing kind-agnostic `PUT
/admin/capabilities/{id}/default-on` (`team_scope` for `kind="model"` stays
`ADMIN_GATED`, same as the other kinds). Consequence: on a deployment where
ReBAC is already active for a team, the platform_admin must toggle
default-on for the desired model(s) in the same deploy window ReBAC
enforcement reaches that team, or that team's chat fails closed until the
toggle is flipped — a deploy-runbook step, not a code gap.

**2026-08-25 — the enablement 409s become visible before the click (GitHub
#2408).** Activating some capabilities from the admin dashboard failed with a
bare HTTP 409: the gates were enforced server-side but invisible to the UI,
which offered the action anyway and then showed a generic "could not enable"
toast. One field added, no route, exception, or error-shape change.

`GET /admin/capabilities` items gain **`default_capability_ids: list[str]`** —
a verbatim projection of `CapabilityCatalogEntry.default_capability_ids`
(itself added by the 2026-07-19 `depends_on` entry above), empty for
`kind="tool"`/`kind="model"` by construction, following the tagged-union rule
stated for the other per-kind fields. This is the missing half of the
2026-07-19 gate: the write path already 409'd
(`AgentCapabilityDependencyNotSatisfied`) when an agent's default tool
capabilities were not usable by the target team, but the list contract carried
no way for the dashboard to know it.

Client-side consequences (`FeaturesPage.tsx`,
`CapabilityTeamMatrixDrawer.tsx`, predicates in `capabilityEnablement.ts`):
the drawer disables "Enable" and names the blocking dependencies for a team
that cannot use them; the personal-space class row does the same against the
org-level personal-access rule (`(personal_on OR default_on) AND NOT
personal_disabled`); the default-on Switch is disabled for a capability with a
required team setting (`DefaultOnNotAllowed`), while turning it OFF stays
possible. The predicates **fail open** on a dependency id absent from the list
— the backend remains the sole authority, and the client gate is a
better-error affordance, never an enforcement point. Residual 409s (stale
client, concurrent admin) are mapped through `normalizeApiError` to an
explanatory toast detail instead of being swallowed.

**Error contract unchanged.** These routes still answer a plain-string
`detail` and no `error_code`; the per-endpoint 409 semantics are unambiguous
on their own, so the frontend disambiguates by which mutation failed plus its
own locally-computed reason.

**Known caveat (accepted).** With ReBAC disabled, `usable_capability_ids`
returns `None` and the backend applies no dependency scoping at all, but the
client predicate still reads the (empty) grant lists and can render an agent
row as blocked. The team matrix is already decorative in that mode, so the
mismatch is cosmetic and not worth a second code path.

**2026-08-28 — the `depends_on` gate reaches the platform-wide switch, and the
UI offers to satisfy it (GitHub #2470).** Three write paths grant a
`kind="agent"` capability; only two of them enforced the 2026-07-19 gate.
`PUT /admin/capabilities/{capability_id}/default-on` had **no dependency check
at all** — so turning an agent template default-on handed it to *every* team
while its `default_capability_ids` stayed ungranted, enrolling a
non-functional agent platform-wide with no error at any point. Surfaced by the
`platform_ops` template (#2458), the first shipped template that declares a
dependency.

**Behaviour change on an existing route.** `PUT .../default-on` with
`default_on: true` now 409s (`AgentCapabilityDependencyNotSatisfied`, the same
exception the other two paths raise) when the entry is `kind="agent"` and any
id in its `default_capability_ids` is not **itself `default_on`**. Turning
default-on **off** is never gated — a template already on whose dependency was
revoked afterwards must stay switchable off, or the admin is trapped in the
very state this prevents. No new field, exception type, or error shape; the
route's error contract is unchanged (plain-string `detail`, no `error_code`).

`default_on` is the only satisfying marker here, deliberately stricter than
the personal-scope rule (`(personal_on OR default_on) AND NOT
personal_disabled`): default-on reaches every team *present and future*, so a
dependency merely granted to the teams that exist today would still leave
tomorrow's team inheriting a template it cannot use.

Client-side consequences (`FeaturesPage.tsx`,
`CapabilityTeamMatrixDrawer.tsx`, `missingAgentDependenciesForPlatform` in
`capabilityEnablement.ts`): the 2026-08-25 entry's disabled "Enable" segment
is **replaced by an "Enable all" confirmation** on all three paths. The
segment stays clickable (a disabled segment is also keyboard-dead, which left
the admin with no in-place way forward); clicking it names the missing
dependencies and offers to grant them **at the same scope** as the template —
per team, personal-class, or default-on — before granting the template itself.
There is deliberately no "enable the template anyway": all three paths now
refuse it consistently. `selectChoice`/`submitEnable`/`onToggleDefault` remain
what keep an ungated grant off the wire, so the client gate is still a
better-error affordance and never an enforcement point.

**Not transactional, and ordered on purpose.** "Enable all" issues one write
per dependency and then the template, sequentially. A dependency that fails
aborts the sequence *before* the template, so a partial failure always leaves
"dependency granted, template not" — never the inverse, which is the broken
state being fixed. The failing dependency is named in the error toast.

**Two consequences of that ordering, both deliberate.** (1) The client-side
#2408 pre-check in `submitEnable` is **skipped** for the final template write
of an "Enable all" run: `allCapabilities` comes from the RTK Query cache,
which has not refetched at that instant, so the pre-check would still see the
just-granted dependencies as missing and refuse the write the admin confirmed.
The backend re-checks either way, so nothing is weakened — the client gate
remains a better-error affordance, never an enforcement point. (2) When the
template itself declares `team_settings_fields`, the team-row flow grants the
dependencies and then **opens the settings form** rather than enabling
outright; the dialog says so up front, since the run stops there until the
form is saved.

## 18. Contract Notes — team-scoped candidate-member search (2026-07-20)

**New endpoint:** `GET /teams/{team_id}/candidate-members?query=<string>` →
`list[UserSummary]`. Gated on `can_administer_members` for `team_id` (owner-only,
no platform escalation).
`query` is required, `min_length=2`, enforced server-side. Returns Keycloak users
matching the query, excluding anyone already holding any role on the team.

**Why:** the existing `GET /users` listing is intentionally `platform_admin`-only
(`§24.9`); team admins need a way to find someone to invite without widening that
org-wide listing to every team admin. `TeamSettingsMembers.tsx`'s "add member"
search now calls this endpoint (`useSearchCandidateTeamMembersQuery`) instead of
`useListUsersQuery` — previously it called the `platform_admin`-gated listing
unconditionally and silently showed zero results for any team-admin-only caller.

`controlPlaneOpenApi.ts` regenerated (`make update-control-plane-api`). No other
route or schema changed.

## 19. Contract Notes — audit-name resolution + `updated_by` (2026-07-20, #1952)

**New endpoint:** `GET /users/by-ids?ids=<uid>&ids=<uid>` → `list[UserSummary]`
(max 100 ids). Open to any authenticated user — it only exposes display identity
(name/username/email), never roles or credentials. Every requested id yields
exactly one entry, in request order, deduplicated; unknown ids (or a disabled
Keycloak M2M client) degrade to an id-only summary so callers can always fall
back to rendering the uid. Wraps the pre-existing internal service
`users/service.py::get_users_by_ids`. The frontend agent-edit footer resolves
`created_by`/`updated_by` through it (`useUsersByIdsQuery`) instead of showing
raw uids (#1952); the unpaginated `platform_admin`-only `GET /users` stays
untouched.

**Schema:** `ManagedAgentInstanceSummary.updated_by: str | null` (read-only,
server-authoritative). Backed by a new nullable `agent_instance.updated_by`
column (Alembic `0285dc3a0cdc`, plain ADD COLUMN, SQLite-compatible), stamped
with the acting user's uid on every `PATCH
/teams/{team_id}/agent-instances/{id}`. NULL means never user-edited
(seed/startup saves have no acting user).

`controlPlaneOpenApi.ts` regenerated (`make update-control-plane-api`).

## 20. Contract Notes — prompts-context personal scoping (2026-07-20, #2023)

**Behavior change:** `GET /teams/{team_id}/prompts/context` no longer merges
the caller's personal prompts into a non-personal team's context (#2023) — a
team space returns only the team's own prompts; the personal space returns
only the caller's prompts (scope `personal`). Response shape unchanged.
Already-attached personal prompts keep resolving at prepare-execution (see
`design/PROMPTS.md` §5/§6). *(2026-07-30, PROMPT-09: "+ platform defaults" no
longer applies — the platform default-prompt catalog this note originally
described is removed, see §32.)*

## 21. Contract Notes — personal team isolation rule (CTRLP-10 / AUTHZ-08)

**Personal team isolation rule:** the personal team ID is `personal-{user.uid}`
(`fred_core.common.personal_team_id`) — no two users share a personal team.
Every team-scoped session, agent-instance, and prompt endpoint enforces
isolation by team membership; no additional per-resource `user_id` filter is
required or maintained for personal-space resources. The `"personal"` string
accepted on some routes is a bootstrap-era URL alias resolved server-side to
the caller's own canonical ID — it is never itself a stored value. Full
authorization mechanism (self-provisioned ReBAC tuple, write-guarded):
[`platform/REBAC.md` § Personal
teams](../platform/REBAC.md#personal-teams--self-provisioned-never-admin-writable-authz-08).

## 22. Contract Notes — #1903 capability asset uploads (2026-07-17)

### Multipart companion routes for agent saves that carry capability assets

An asset-bearing capability (first: `ppt_filler`)
needs its uploaded file to travel INSIDE the atomic agent save so the pod's
`validate_config` can parse it, store the binary, and persist the derived
config in one step. Two additive routes relay that multipart; the existing
JSON routes are unchanged and remain the path for every save without uploads:

- `POST /teams/{team_id}/agent-instances/with-assets`
- `PATCH /teams/{team_id}/agent-instances/{agent_instance_id}/with-assets`

Body (`multipart/form-data`):

| Field | Meaning |
| --- | --- |
| `request` | The corresponding JSON request (`CreateAgentInstanceRequest` / `UpdateAgentInstanceRequest`) as a JSON object string |
| `asset_slots` | One `{capability_id}:{slot_key}` reference per uploaded file, aligned by index with `asset_files` |
| `asset_files` | The uploaded binaries |

Semantics: control-plane is a pure relay — it never opens the bytes. Files are
grouped per capability and forwarded to the pod's
`POST /agents/capabilities/{id}/validate-config` as multipart fields keyed by
slot key; the pod's declared `AssetSlot` gate (cardinality, extension) and the
capability's own content validation both run pod-side, and their 422 wording
propagates verbatim (the uniform-422 convention of §17). Mismatched
`asset_slots`/`asset_files` lengths and malformed slot references are rejected
422 before any pod call. Files addressed to a capability that is not active in
the save are ignored, mirroring the config-values policy. Responses and
authorization (`CAN_UPDATE_AGENTS`) are identical to the JSON routes.

## 23. Contract Notes — upload warning banner (MIGR-01.01, 2026-07-23, #2077)

`FrontendBootstrap` gains one optional field, `upload_warning`
(`UploadWarning`: `severity: info|warning|error|success` + `messages: {locale
→ string}`), sourced from control-plane deployment config
`platform.frontend.upload_warning`. When set, the frontend renders one shared
banner (`UploadWarningBanner`) on upload surfaces — the document upload
drawer and the chat session-attachments drawer — resolving the message from
the active i18next locale with `en` fallback. `null`/omitted → nothing
rendered, the pre-#2077 behavior.

Ported from the main-branch `Properties.uploadWarning` (#1597, #1634), whose
serving surface (agentic-backend frontend properties) no longer exists on
swift.

Boundary rationale (§3.1): this is **not** a branding label — it is a
deployer *policy/compliance notice* (e.g. "do not upload classified
documents"), structured (severity + locale map), which the static
`config.json` `properties` surface (`Record<string, string>`) cannot express.
It follows the `gcu_version` precedent: deployment-config-owned policy
exposed on the authenticated bootstrap. Deliberately not on the pre-auth
`FrontendConfig`, which stays minimal — upload surfaces only render
post-auth.

## 24. Contract Notes — TEAM-09, joining_mode replaces is_private (2026-07-23)

**`Team.is_private: bool` is removed; `Team.joining_mode: JoiningMode` is
added** (`Team`, `TeamWithPermissions`, `UpdateTeamRequest`). `JoiningMode` is
a 4-value enum: `open`, `request_only`, `invite_only`, `closed`. Full design:
`rfc/FRED-TEAM-CONFIG-RFC.md` §5.1.1.

Why a boolean was replaced rather than extended: `is_private` was being asked
to answer two different questions — is this team even discoverable, and how
does someone become a member — and could only answer one. Marketplace
discovery is now unconditional for every team regardless of `joining_mode`
(every team gets the ReBAC `public` relation, granting only the existing
profile/discovery `can_read` — never conversation access); `joining_mode`
governs solely whether/how a user can become a member. Existing teams migrate
to `request_only` on upgrade (Alembic `a4b5c6d7e8f9`) regardless of their
prior `is_private` value — that field never actually gated the marketplace's
former mailto-based join, so `request_only` changes no team's real-world
joinability on migration day.

**New endpoint — `POST /teams/{team_id}/join`.** Self-service: the caller
grants themselves `team_member` and only `team_member`, only when the
team's stored `joining_mode` is `open` (checked server-side, 403
`TeamNotOpenForJoiningError` otherwise — the client's belief about the mode
is never trusted). Every other membership-write route
(`add_team_member`/`grant_team_member_role`/`revoke_team_member_role` and
siblings) remains team-admin-gated; `remove_team_member` gains its own
same-identity, non-admin-gated path in `§25` below.

`request_only` and `invite_only` currently have identical server-side
enforcement (both simply reject self-join) — they differ only in marketplace
presentation (a disabled "Request" affordance vs. no affordance at all) until
a notification system exists to route `request_only` asks to team admins.

## 25. Contract Notes — AUTHZ-09, self-service team leave (2026-07-23)

**No route or schema change.** `DELETE /teams/{team_id}/members/{user_id}`
(`RemoveTeamMemberResponse`, unchanged) already accepted any `user_id`; the
service-layer permission check now bypasses the admin-only
"administer"-permission gate when the caller's own id equals the target
(`user.uid == user_id` — a "leave team" call is the same request an admin
would send to remove that member, just self-directed).

Everything else about the operation is unchanged and applies identically to
a self-removal:

- the "team must keep at least one `team_admin`" invariant still fires
  unconditionally whenever the caller holds `team_admin` — the sole
  remaining admin cannot remove themselves;
- the same session/conversation retention-policy purge that runs for an
  admin-initiated removal runs for a self-removal (`RemoveTeamMemberResponse`
  reports the same `sessions_enqueued`/`scheduled_delete_at`/`policy_mode`
  fields either way) — leaving a team has the same conversation-lifecycle
  consequence as being removed from it.

**Frontend:** the team-settings entry point (gear icon, previously gated on
`canAdministerAdmins`) is now gated on `canReadMembers` — every team member
reaches a settings surface, scoped by their existing per-section capability
gates (a plain member sees a read-only Members list plus a new "Leave team"
action; elevated roles keep today's full panel plus the same action). No new
`TeamPermission` was added — see RFC Part 9 §45 for why.

## 26. Contract Notes — #2100, `TeamWithPermissions.my_relations`

**New field, additive only.** `TeamWithPermissions` (`GET /teams/{team_id}`,
`create_team`, `update_team`, and the bootstrap's `active_team`) gains
`my_relations: list[UserTeamRelation]` — the caller's own raw role relations
on that team (`team_admin`/`team_editor`/`team_analyst`/`team_member`), the
same set already exposed for other members via `TeamMember.relations`.

**Why `permissions` alone was not enough:** `can_run_evaluations` and
`can_manage_evaluation_corpus` are granted to both `team_analyst` and
`team_admin` (schema.fga union), so a plain `team_admin` with no explicit
`team_analyst` grant would already show those permissions — deriving an
"Analyst" role badge from `permissions` would mislabel every admin as an
analyst too. `team_admin` (`can_administer_admins`) and `team_editor`
(`can_update_agents`) remain independently and reliably derivable from
`permissions`, but `my_relations` is now the single unambiguous source for
all three, used by the frontend's team-role display (§ below).

Personal teams report the fixed literal `["team_editor"]` (matching their
already-hardcoded `permissions`) rather than a live ReBAC lookup — see
`teams/system.py::build_personal_team`.

**Frontend:**

- `TeamSelectionItem` (left team rail): a 14×14 Shield badge (bottom-right of
  the avatar) appears when the current user is listed in that team's
  `admins` (`Team.admins`, already present — no new data needed for this
  part; `my_relations` is not involved here since the rail only needs a
  boolean, not the full role set).
- `TeamContentNavbar` (team banner): the name/gear row moves to the top of
  the banner; a new bottom-left label lists every role the user holds,
  joined by " · " (e.g. "Administrateur · Analyste"), reusing the existing
  `rework.teamRoles.*` i18n labels, falling back to "Membre" when no
  elevated role is held. Hidden for the personal space and for a non-member
  merely browsing a public/marketplace team pre-join (`is_member`).

`controlPlaneOpenApi.ts` regenerated (`make update-control-plane-api`).

## 27. Contract Notes — platform import/export/reset

The Kea→Swift production cutover is complete; the kea-import path, its
identity/team reconciliation, and the temporary dry-run preview tool have
been removed (2026-09). The permanent, load-bearing facts below are the
canonical contract for the swift-native backup/restore mechanism that
remains.

**Endpoints** (`/control-plane/v1/import-export/`, all `require_admin` +
`CAN_MANAGE_PLATFORM`):

- `POST /import` — multipart zip → async task; atomic import.
- `GET /export` — download a swift-native snapshot, re-importable through the
  same endpoint.
- `POST /reset` — atomic wipe of agents+tags+metadata only (Keycloak/OpenFGA/
  team_metadata/prompts/object store untouched) — the narrow, repeatable
  export→reset→import dev/test cycle.
- `GET /stats` — platform overview (teams, members by role, agents, prompts)
  — powers the **Platform data** admin page.

`POST /import` (and `POST /reset`) reject (`409`) while another
`kind="migration"` task is running/pending (`TaskService.list_tasks(kind="migration",
exclude_terminal=True)`) — a best-effort, non-atomic guard sized for one
human operator driving an import by hand, not for concurrent automated callers.

**Bundle format:** `manifest.json` (`bundle.py::SnapshotManifest`,
Pydantic-validated — `open_bundle()` rejects any `format_version`/
`users_schema_version` outside the set it understands, `{1}` today, no
silent default) + `postgres/{agent_instance,tag,metadata,team_metadata,
team_routing_policy}.jsonl` + optional top-level `users.json`. `document_uid`
is the stable join key across control-plane's `document_metadata` rows, the
knowledge-flow content store, and the vector store — never regenerated by
import, carried through 1:1 (fresh-target only, idempotent by primary key,
no upsert/merge).

**Content honesty:** the bundle never carries document binaries or vector
embeddings — never transported, permanently out of scope. `content_keys`
(every exported `document_uid`) surfaces as a `report.warnings` count-only
reminder, not a per-document presence check.

**Stage-reconciliation rule:** on import, `importer.py::_reset_transported_stages`
resets every restored `metadata` row's `VECTORIZED` and `SQL_INDEXED` stage to
`NOT_STARTED` — these are never transported, so a `DONE` claim would be a lie.
`PREVIEW_READY` is left untouched (trusted present).

**`users.json` — declarative team/platform role provisioning:** one entry per
identity (`schemas.py::BundleUserEntry`: `username` required; `email`/
`first_name`/`last_name`/`password` optional identity fields; `teams`/
`team_roles`/`platform_roles` role fields). Two phases, always in this order,
fail-closed (`BundleProvisioningError` aborts the whole users phase, never a
silently-partial `succeeded`):

1. **Identity** — creates a Keycloak user only if no existing identity
   resolves by username (`importer.py::UserSubResolver`, one paginated bulk
   sweep of the target realm per run, followed by in-memory lookups) **and**
   the entry carries a `password`; no password means assumed to already exist.
2. **Role** — resolves `username` → Keycloak `sub`, then grants
   `platform_roles` (`"admin"`→`platform_admin`, `"observer"`→`platform_observer`,
   the only path that can grant a platform role to a third party) and
   `team_roles`/`teams` (direct `RebacEngine.add_relation`, bypasses the
   ordinary `team_admin`-gated grant API since the importer isn't expected to
   already hold `team_admin` on every touched team). Idempotent — re-running
   an already-reconciled bundle re-writes the same tuples with no error.

## 28. Contract Notes — MIGR-07, corpus re-vectorization (finalized 2026-07-25)

MIGR-07 backend is built (issue #2111). No knowledge-flow-backend equivalent
of this contract doc exists yet (checked `docs/swift/design/` and
`docs/swift/platform/` — nothing covers corpus/ingestion endpoint contracts);
this section is the interim canonical record for the shape below until one is
created — **flagged to Dimitri, not unilaterally created here.**

**Endpoint:** `POST /knowledge-flow/v1/corpus/revectorize` (admin/owner-only,
`RevectorizeCorpusRequestV1`: `scope` + `mode`/`force`) — starts a real
`task_run` (`kind="ingestion"`, not a new `"revectorize"` kind — reuses
`emit_ingestion_task_event`/`IngestionTaskEvent` verbatim so `TaskService`'s
terminal-event reconciliation emits the right event type) and a Temporal
workflow, `202 { task_id }`.

**Temporal workflow shape** (`features/scheduler/workflow.py`, mirrors the
`ProcessPull`/`ProcessPullFile` parent/child pattern):

- `RevectorizeCorpusWorkflow.run(payload)` — resolves `scope` to
  `document_uids` via the `list_documents_in_scope` activity, then batches
  `RevectorizeDocument` children at `scheduler.temporal.ingestion_workflow_parallelism`
  (reused, not a new request field), emitting one running/succeeded task
  event with `processed`/`total`/`failed` counts.
- `RevectorizeDocument.run(document_uid, options, user, task_id)` — skips a
  document already vectorized under `mode: incremental` + no `force`
  (`get_chunk_count` == 0 check); otherwise deletes existing vectors (if any)
  and re-runs `output_process` (reused verbatim — restores from the mirrored
  `output.md` in object storage, no re-extraction). Catches its own
  exceptions and returns `{"failed": true}` rather than raising, so one bad
  document cannot abort the whole corpus batch — the entire body from the
  initial `get_chunk_count` call onward must stay inside the `try` (a gap in
  the first cut, where `get_chunk_count` sat outside the `try`, was found and
  fixed in review — see PR #2106).
- `list_documents_in_scope` activity resolves a `CorpusScopeV1`-shaped dict:
  `document_uids` wins outright; otherwise `tag_ids`/`source_tag` query the
  raw metadata store directly (not per-user READ-filtered — the scope was
  already authorized at the platform/team level by
  `corpus_manager_controller._authorize_scope`).

**Scope semantics:** `mode: full` → delete + re-embed every in-scope doc.
`mode: incremental` → only docs with 0 vectors. `force: true` → always
re-embed regardless of mode. `embedding_model` is advisory only (not wired
into `prepare_revectorize_file`, which always uses
`IngestionProcessingProfile.medium` — the original ingestion profile isn't
recorded on `DocumentMetadata`). Migration default scope: all migrated
documents (by `source_tag`), `mode: full`.

**Authorization:** a `source_tag`-only scope spans arbitrary teams (it's the
migration's default scope) and requires `OrganizationPermission.CAN_MANAGE_PLATFORM`
— same gate as `/documents/audit` and the import-export reset endpoints — not
just per-tag/per-document ReBAC checks. Fixed alongside this build (the field
existed but wasn't authorized before).

**Remaining open item:** MIGR-07.04, the migration UI's "Rebuild embeddings"
final-step trigger button (reuse the same task atoms already used by import)
— a real future item, not yet built.

## 29. Contract Notes — TEAM-09 amendment, `joining_mode` narrowed to 2 states (2026-07-26, #2084)

**`JoiningMode` drops `request_only` and `closed`**, leaving `open` /
`invite_only` — see §24 for the original 4-value contract and
`FRED-TEAM-CONFIG-RFC.md` §5.1.1 for the full amendment rationale.
`request_only` depended on a notification system that was never built and
shipped with its marketplace affordance permanently disabled; `closed` never
enforced anything `invite_only` didn't (identical write-path gating, only
marketplace copy differed).

**Default changes.** `Team.joining_mode`'s default (`Team`, `TeamWithPermissions`,
the ORM column, and the personal-space synthetic team previously hardcoded to
`closed`) moves from `request_only` to `invite_only`. Every row currently in
`request_only` or `closed` is backfilled to `invite_only` by migration
`9ee7b44b0d57` — the conservative mapping, no team becomes self-service `open`
as a side effect.

**Import/export.** A platform bundle exported before this change may still
carry `request_only`/`closed` literally in its `team_metadata.joining_mode`
field; `importer.py`'s `_LEGACY_JOINING_MODES` normalizes both to
`invite_only` on import so the row never lands with a value the current
enum — and therefore any later read of it — would reject.

**Marketplace (`TeamCard`).** Collapses from 4 branches to 2: `open` shows
the self-service Join button; every other state (now only `invite_only`)
shows a static "Invite only" label. No behavior change to the `open` branch
or to `POST /teams/{team_id}/join`'s server-side gate (`joining_mode == open`,
unchanged).

## 30. Contract Notes — TEAM-10, team visibility (public/private) (2026-07-26)

**New field: `Team.visibility: TeamVisibility` (`public`/`private`, default
`public`)** — added to `Team`, `TeamWithPermissions`, `UpdateTeamRequest`.
Full design: `FRED-TEAM-CONFIG-RFC.md` §5.1.2. Gates marketplace
discoverability, a question `joining_mode` (§5.1.1/§24/§29) never answered —
`INVITE_ONLY` still means "listed, join needs an admin," not "does not
appear at all."

**Mechanism — the ReBAC `public` relation becomes conditional.** §24's
`ensure_team_public_relations` (unconditional for every team) is now called
only for `PUBLIC` teams; `PRIVATE` teams get the new, symmetric
`RebacEngine.revoke_team_public_relations` instead (same relation shape,
`delete_relations`). Both are idempotent and called from the same two
sites as before (`_list_teams` lazily on every listing, `create_team`/
`update_team` immediately) — `update_team` syncs the affected team's
relation the moment `visibility` changes, not on the next list call. A
private team is not merely unlisted: `can_read = team_member or public`
means a non-member's direct `GET /teams/{team_id}` now also 403s (no
`public`-relation path left) — `team_member`-gated access is completely
unaffected, so a private team behaves identically to a public one for its
own members.

**Interaction with `joining_mode` — downgrade, never reject.** A `PRIVATE`
team cannot be `OPEN` (self-service join onto an undiscoverable,
unreadable-to-non-members team is incoherent). `update_team` resolves the
patch's *resulting* `visibility`/`joining_mode` (an untouched field keeps
its current stored value) and, if that combination would be
`PRIVATE`+`OPEN`, silently rewrites `joining_mode` to `INVITE_ONLY` in the
same patch — never trusts which field the client "meant" to win, and never
returns a 4xx for this combination. Frontend enforcement
(`TeamSettingsParameters`) disables the joining-mode `ButtonGroup` entirely
while `visibility === private`, so the invalid combination is unreachable
from the UI in the first place; the server-side downgrade is the
authoritative backstop.

**Default and migration.** *(Superseded 2026-08-26 — new teams default to
`PRIVATE` since #2433, see §44; accurate for its own date below.)*
`PUBLIC` for both new and pre-existing teams
(migration `8092a626d4d0`, `server_default='public'`) — preserves every
team's current unconditional marketplace presence exactly; nothing becomes
private as a side effect of this rollout. A bundle exported before this
field existed has no `visibility` key at all; `importer.py` defaults the
row to `public` on import, same reasoning.

## 31. Contract Notes — `reset-full` and `reset-rebac` teardown endpoints removed (2026-09-05)

`POST /import-export/reset-full` (removed 2026-07-27) and
`POST /import-export/reset-rebac` (test/rehearsal teardown wiping
Postgres+OpenFGA, exposed only through the now-deleted kea-specific
`KeaMigrationPage.tsx`) are both gone — neither had a general-purpose UI
consumer once the Kea→Swift cutover finished. `POST /reset` (the narrow
agents+tags+metadata-only reset used for the export→reset→import dev/test
cycle) is unaffected and remains the only reset endpoint.

## 32. Contract Notes — PROMPT-09, team-owned prompt categories (2026-07-30)

**Platform default prompts and the global `PromptCategory` enum are removed.**
Every prompt returned by the API is now a real, persisted, editable team row
— there is no more synthetic `default:{category}` id, no `is_default` field on
`PromptSummary`/`ContextPromptSummary`, and no `default_prompt_usage` table
(usage is `PromptRow.session_count` for every prompt, uniformly).

**Categories are team-owned content**, not a platform-wide taxonomy:

- new table `prompt_category` (`category_id`, `team_id`, `name`), no DB-level
  FK to `prompt` (matches every other team-scoped table in this schema)
- `prompt.category` (free string, validated only against the old fixed enum at
  the API boundary) becomes `prompt.category_id: str | None`, referencing a
  `prompt_category` row scoped to the same team; nullable — an uncategorized
  prompt is valid
- new endpoints, all under `/teams/{team_id}/prompt-categories`: `GET`/`POST`
  (`CAN_USE_TEAM_AGENTS`/`CAN_UPDATE_RESOURCES` respectively), `PUT`/`DELETE`
  on `/{category_id}` (`CAN_UPDATE_RESOURCES`)
- `DELETE` returns **409** while any prompt in the team still references the
  category — a hard block, never an automatic reassignment of the orphaned
  prompt(s)
- `POST /teams/{team_id}/prompts/{prompt_id}/promote` (copy-by-value to
  `target_team_id`) carries over `emoji`/`tags` but never `category_id` —
  the source category belongs to the source team, so it cannot resolve in
  the target team; the copy lands uncategorized (2026-08-02)

**Team creation seeds a starter kit.** `create_team` now creates, right after
the ReBAC bootstrap succeeds: 4 categories ("Création agent", "Analyse et
synthèse", "Stratégie et idéation", "Communication") and one prompt per
category. From that point on the starter kit is normal team content — any
`team_editor` can rename, edit, or delete every part of it, including the
categories themselves. Seeding is **best-effort**: unlike the ReBAC relation
writes, a seeding failure logs a warning and does not fail team creation. The
personal prompt space is **not** seeded.

**Migration (`8ca7cafc292f`)** backfills the same starter kit into every
*existing* team that had zero prompt rows at migration time (teams that
already authored custom prompts are left untouched), migrates every existing
prompt's legacy `category` string into a real per-team category row named
after the old enum's French label, then drops `prompt.category` and
`default_prompt_usage`.

**Breaking changes:**

- `PromptSummary.category` / `ContextPromptSummary.category` /
  `CreatePromptRequest.category` / `UpdatePromptRequest.category`: the fixed
  `PromptCategory` enum becomes `category_id: str | None`
- `is_default` removed from `PromptSummary` / `ContextPromptSummary`
- `ContextPromptSummary.scope` narrows from `"personal" | "team" | "default"`
  to `"personal" | "team"`; the `text` field (only ever populated for
  `scope="default"`) is removed
- `GET /teams/{team_id}/prompts` and `GET .../prompts/context` drop the `lang`
  query param (it only ever localized the removed default-prompt catalog)
- `POST /teams/{team_id}/agent-instances/{id}/prepare-execution` drops the
  `lang` query param for the same reason

**Frontend.** Categories are fetched per-team
(`useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery`)
— the static `promptCategories.ts` catalog (fixed id → icon/color/i18n-label
map) is deleted. Category pills/tiles use a shared hash-based fallback palette
(`hashColorIndex`, same 5-family token set already used for uncategorized
prompts) instead of per-category curated icons — categories are free-form
team content now, not a curated taxonomy. `PromptCard`/`PromptsPage` drop the
`is_default` read-only branch entirely; `canManage` is computed from
`useTeamCapabilities(team).canUpdateResources` instead of `!prompt.is_default`
(which never reflected real permissions). New `ManageCategoriesDialog`
(Créer/Éditer/Supprimer, 409 surfaced as a toast) reachable from a button in
the category filter-chips row.

---

## 33. Contract Notes — REASON-01, per-model reasoning activation (2026-07-29, #2166)

Level 2 of REASON-01 (phase 1 = levels 1–2; levels
3–4 are phase 2 and not in this change).

### New route

`PATCH /admin/capabilities/{capability_id}/reasoning`, body
`SetModelReasoningRequest { reasoning_enabled: bool }`, returning
`ModelReasoningResult { capability_id, reasoning_enabled }`. Gated on
`capability#can_manage` (org admin), the same gate as the sibling `default-on`
and `personal-scope` routes it sits next to.

**409 when the capability is not a model, or is a model with no
thinking-capable profile** (`ReasoningNotSupported`). Aptitude is declared per
profile in `models_catalog.yaml` (`supports_thinking`) and no admin action can
grant it (RFC §5.3) — storing the row anyway would persist an activation that
could never take effect, and put a control in the UI that lies about what it
does.

### Why a table and not a ReBAC relation

Reasoning has **no subject**. It answers "does this model run with reasoning",
not "who may use this model" — so it is not a permission (RFC §5.1). Building
it as a grant would mean duplicating the `capability` type's seven-relation
enablement lattice for an axis with no per-subject semantics at all. It is one
row per `kind="model"` capability id in the new `model_reasoning` table
(migration `a7c3d91f2b40`), written only through the route above.

**Per-team model authorization is untouched.** ReBAC `can_use` on
`model__<provider>__<name>` still decides who may use a model; this decides how
it runs for whoever already may (RFC §5.4). The two axes share the admin screen
and must not be confused: on the models view, "Enabled for all" is access,
"Reasoning" is behaviour.

### Absent row = OFF (RFC §5.6)

Enabling a model and enabling its reasoning are two separate admin actions, in
that order; the second is never implied by the first. A stored `false` and no
row at all are indistinguishable by construction — the store's read side returns
only enabled ids.

**Consequence, deliberate:** a deployment that ran reasoning through
`models_catalog.yaml` alone **stops reasoning at this upgrade** until an
administrator switches it on (RFC §5.6.1). Release-noted, not silent. Chosen on
safety grounds — measured 10/10 turns
with duplicate tool calls on the profile this affects — and it puts the live
per-model off switch in place *before* levels 3–4 widen exposure to it (RFC §9).

### Contract additions

| Field | On | Meaning |
| ----- | -- | ------- |
| `CapabilityEnablementItem.thinking_profile_ids` | `GET /admin/capabilities` | The model's `supports_thinking` profile ids, from the pod. **Empty ⇒ the admin row shows no reasoning control at all** |
| `CapabilityEnablementItem.reasoning_enabled` | `GET /admin/capabilities` | Current activation; `false` when no row is stored |
| `CapabilityCatalogEntry.model_thinking_profile_ids` | catalog projection | Carried verbatim from `GET /agents/models-catalog`, same as `model_profile_ids`. Absent on a pre-REASON-01 pod ⇒ reads as "cannot reason", the safe direction |
| `ExecutionPreparation.reasoning_enabled_model_ids` | prepare-execution | The activation snapshot the runtime enforces against |

### Delivery to the runtime

`ExecutionPreparation.reasoning_enabled_model_ids` is still returned at session
prep, for the frontend to render the composer control's initial state. It is
**not**, however, what the runtime enforces against per turn (updated
2026-08-01): `ManagedAgentRuntimeBinding.reasoning_enabled_model_ids` — resolved
fresh on every turn's own `GET /teams/{team_id}/agent-instances/{id}/runtime`
call, from the same store — is what `RoutedChatModelFactory` strips reasoning
settings against. The runtime-binding call already happens once per turn to
resolve the instance's tuning and team-capability settings, so this piggybacks
on it rather than adding a new round trip. This closes a gap where a session
that stayed open past an admin's platform-wide toggle would keep reasoning
active for the rest of that session: the enforced value is now current as of
the next turn, not the next session.

`chat_default_profile_id`/`agent_profile_overrides` are unaffected by this
change and remain resolved once at session prep and forwarded by the frontend
unchanged — routing-profile choice is a cost/comfort lever already bounded by
the per-turn model authorization check, not an admin control, so the same
freshness requirement does not apply to it. The platform-wide `chat` model
binding (§40, issue #2365) is a fourth, unrelated field that *does* get the
freshness treatment — see `RUNTIME-EXECUTION-CONTRACT.md` §8.55.

### Addendum — REASON-01 phase 2, reasoning is an agent property (2026-07-30)

Levels 3-4 shipped (`RUNTIME-EXECUTION-CONTRACT.md` §8.30). Reasoning is **not**
a capability (RFC §15, Amendment A) — it was built as one and withdrawn before
release, because an agent does not *use* reasoning the way it uses a tool.

### Contract additions

| Field | On | Meaning |
| ----- | -- | ------- |
| `reasoning_enabled` | `CreateAgentInstanceRequest` (default `False`), `UpdateAgentInstanceRequest` (`None` = unchanged) | Level 3: does this agent offer the composer's reasoning toggle |
| `reasoning_enabled` | `ManagedAgentInstanceSummary` | Current setting, so the edit and duplicate flows can hydrate it |
| `reasoning_enabled` | `ManagedAgentTuning` | Where it is persisted — a plain agent property beside `role`/`description`, **not** a `capability_config` slice |
| `reasoning_disabled` | `CapabilityDefaultOnResult` | True when switching this **model** off also switched its reasoning off (RFC §5.7, 2026-07-30) |

`UpdateAgentInstanceRequest.reasoning_enabled` follows the same "omit means
unchanged" convention as `role` and `usage_statement`, so a partial update such
as the enable/disable toggle cannot silently switch an agent's reasoning offer
off.

**`reasoning_enabled` on the tuning is a security-relevant field, not a UI hint.**
The runtime resolves it server-side through
`GET /teams/{team_id}/agent-instances/{id}/runtime` and intersects it into the
reasoning ceiling it enforces (`RUNTIME-EXECUTION-CONTRACT.md` §8.30, RFC §14.5).
Dropping it from that binding response would silently re-open level 3.

### Switching a model off switches its reasoning off (RFC §5.7)

`PATCH /admin/capabilities/{id}/default-on` with `default_on: false` on a
`kind="model"` capability now also clears a stored `reasoning_enabled` for that
model, and reports it on `CapabilityDefaultOnResult.reasoning_disabled`. One
direction only — enabling a model still never enables its reasoning (§5.4). No
row is written when none existed: an absent row and a stored `false` are the same
state, so the cascade must not stamp `false` rows across the table.

### The composer control is emitted by the PLATFORM

`prepare-execution` appends the `reasoning_toggle` descriptor itself
(`_platform_reasoning_control`) instead of a capability producing it. Two
consequences worth stating:

1. **`ChatControlDescriptor.capability_id` now has a reserved value**,
   `PLATFORM_CHAT_CONTROL_OWNER = "platform"`. Before this, every chat control
   came from a capability (`docs/swift/capabilities/AUTHORING.md`); that statement is no
   longer true. The frontend needed no change — its registry already falls back
   to the capability-agnostic stock kit by widget id when no plugin claims the
   `(capability_id, widget)` pair.
2. **The value does not travel back on `turn_options`.** It rides
   `RuntimeContext.reasoning` like `search_policy` and `search_rag_scope`, which
   is what a per-turn platform chat option has always used.

### Addendum — REASON-01 Amendment B, the author seeds the toggle (2026-07-30, #2175)

`params.default` on the emitted `reasoning_toggle` descriptor was hardcoded
`False`; it is now the agent's own `reasoning_default_on` (RFC §16).

| Field | On | Meaning |
| ----- | -- | ------- |
| `reasoning_default_on` | `CreateAgentInstanceRequest` (default `False`), `UpdateAgentInstanceRequest` (`None` = unchanged) | Does a new conversation start with the composer's reasoning toggle already on |
| `reasoning_default_on` | `ManagedAgentInstanceSummary` | Current setting, so the edit and duplicate flows hydrate it like `reasoning_enabled` |
| `reasoning_default_on` | `ManagedAgentTuning` | Where it is persisted — beside `reasoning_enabled`, still not a `capability_config` slice |

**This is a seed, not a gate, and the distinction is the contract.** §8's gates
are evaluated first and unchanged: with the offer off, or no model reasoning
platform-wide, **no descriptor is emitted at all** regardless of this field. A
stored `true` under a withdrawn offer is inert, never a back door that leaves
reasoning on for users.

**The two reasoning fields never write each other.** `reasoning_enabled: false`
does not clear `reasoning_default_on` — deliberately, so an author who withdraws
the offer and later restores it recovers their default instead of silently
reverting to off. Clients submit both fields independently; the "omit means
unchanged" convention applies to each on `UpdateAgentInstanceRequest`.

Unlike `reasoning_enabled`, this field is **not** security-relevant: it never
reaches the runtime binding and cannot widen the enforced ceiling (levels 1-2 ∩
level 3). It only decides where a switch the user still controls starts.

### §8 diagnosability — the control is absent, never inert

RFC §8 requires the composer control to be **absent** whenever an upstream gate
is closed: four gates stand between a user and a reasoning turn and three are
invisible from the chat page, so a present-but-dead toggle produces the support
ticket "I turned reasoning on and nothing happened" with no way to tell which
gate blocked. `_platform_reasoning_control` returns `None` when the agent does
not offer reasoning, or when no model has its reasoning enabled platform-wide.

**No catalog fetch is needed on this send path**, because the write path already
guarantees the aptitude gate: `PATCH /admin/capabilities/{id}/reasoning` 409s
(`ReasoningNotSupported`) for a model with no `supports_thinking` profile, so a
stored enabled row can only ever name a reasoning-capable model.

**Deliberately not narrowed to the profile the turn will route to.** Routing
resolves a profile per *operation* at runtime while chat controls are computed
once per session (RFC §12 q3). Erring toward under-hiding — showing a control a
later operation might not honour — beats over-hiding one that would have worked.

### Addendum — the toggle's form location is the Capabilities tab (2026-08-02)

The level-3 offer toggle and Amendment B's `reasoning_default_on` render inside
the agent form's **Capabilities tab** (renamed from Tools), through the same
generalized `CapabilityCard` component every real capability uses (`name`/
`description`/`checked`/`onToggle` plus an optional `subForm` slot for the
nested default-on switch) — not a reasoning-specific component, and not the
General section it lived in briefly beforehand. This is a form-placement
change only: `AgentTuning.reasoning_enabled`/`reasoning_default_on` remain
plain agent properties (no `ConfigModel`, no `TurnOptionsModel`, no
middleware), enforced at the single `build_for_chat` point as before.

### Addendum — a template declares its reasoning defaults (2026-08-28, #2473)

Both reasoning fields were settable **per agent instance only**: whoever filled
in the creation form decided them, and a template had no way to say "this
agent's job needs reasoning". Amendment B's own title says "let an agent
**author** preselect reasoning ON", but the author had no surface to do it from
— the SDK's `AgentTuning` did not even declare `reasoning_default_on`. #2473
closes that gap.

| Field | On | Meaning |
| ----- | -- | ------- |
| `reasoning_enabled`, `reasoning_default_on` | `AgentDefinition` (fred-sdk) | What a template DECLARES; both default `False` |
| `reasoning_enabled`, `reasoning_default_on` | `AgentTuning` / pod `default_tuning` | How the declaration reaches control-plane — `_definition_to_agent_tuning` now projects both |
| `reasoning_enabled`, `reasoning_default_on` | `AgentTemplateSummary` | What the agent-creation form reads to pre-tick its Reasoning card |

**A seed, not a gate — the same contract Amendment B set.** The form pre-ticks
from the template exactly as `default_capability_ids` pre-ticks capabilities
(#1974); the operator may untick either before saving, and enrollment keeps
overwriting both from the request, so the form stays authoritative once shown.

**The pre-tick is unconditional, and that is deliberate.** It does not consult
`reasoning_enabled_model_ids`. This copies existing behaviour rather than adding
any: the form's Reasoning card is already rendered unconditionally and the form
has never read the platform gate. Levels 1-2 stay enforced live on the send path
(`_platform_reasoning_control`, `build_for_chat`), so a declared `True` on a
deployment where no model has its reasoning enabled is simply inert — no
descriptor emitted — precisely as a hand-ticked `True` is today, and the control
reappears if an admin later enables a model. Suppressing the pre-tick instead
would make it vanish according to platform state invisible from that form, which
is the confusion §8's absent-not-inert rule exists to prevent.

**No migration.** `ManagedAgentTuning` already carried both fields with `False`
defaults, so stored rows and pods predating #2473 deserialize unchanged and
report both `False`. Only NEW instances of a declaring template are affected;
existing instances do not gain their template's reasoning defaults retroactively
(the same boundary `materialize_default_capability_selections` draws for
capabilities).

First adopter: `platform_ops` (#2458) declares both `True` — a diagnostic agent
whose turns are inherently multi-step.

---

## 34. Contract Notes — `prepare_execution` session ownership check (2026-07-31)

**Gap found and closed.** `prepare_execution` (`product/service.py`) accepts
an optional `session_id` and, when present, resolves that session's
`context_prompt_ids` into `context_prompt_text` for the returned
`ExecutionPreparation`. The session row was loaded via
`SessionMetadataStore.get(session_id)` — a raw, unscoped primary-key fetch —
with **no check** that the resolved session belonged to the calling user,
the requested `team_id`, or the requested `agent_instance_id`. The sibling
`get_session` (same file) already guards its identical raw fetch with a
`record.team_id != team_id` check; `prepare_execution` never applied that
idiom. Exploitability was accidentally limited (prompt *text* resolution is
scoped to the caller's own team/personal team, not the session's team, so a
foreign-team session's prompt ids resolved to nothing) but the gap was real
and untested.

**Fix.** `prepare_execution` now rejects (`ExecutionPreparationError`, 404,
generic message — deliberately identical whether `session_id` is unknown or
belongs to another user/team/agent instance, so the error itself carries no
existence oracle) whenever a supplied `session_id` does not resolve to a
session owned by the same `user_id` and `team_id`, and — only when the
session was actually scoped to an instance at creation (`agent_instance_id`
is optional on `CreateSessionRequest`) — the same `agent_instance_id`. An
agent-agnostic session (created with no `agent_instance_id`) is unaffected
and matches any instance the same user/team requests.

**Behavior change to note:** previously, a `session_id` that did not resolve
at all (typo, deleted session, race with an in-flight creation) was silently
treated as "no context prompt" and the turn still executed. It now rejects
the whole `prepare_execution` call instead. This is intentional and expected
to be safe in practice: the frontend's session-write barrier
(`useManagedChat.ts`'s `flushSessionWrites`) is fixed in the same change to
block `send()` until the session row is confirmed created, so by the time
`prepare_execution` is called with a `session_id`, that session should
already exist.

---

## 35. Contract Notes — CTRLP-12, conversation erasure & team-governed retention (2026-07-24)

Deleting a conversation provably erases it across every store. A team may set a
retention window during which a deleted conversation survives — hidden from
users but available to the team for agent evaluation — after which it is
automatically and provably erased by an authenticated background worker.

**Erasure fan-out (`ConversationErasureService.erase_session`).** Store order
is fixed by dependency: attachments/Knowledge-Flow and KPI first
(independent), then the runtime **checkpoint before transcript** (the runtime
proves checkpoint ownership via the transcript), then the `session_metadata`
row **last** — so a retry can always re-resolve and finish. Returns an
`ErasureReceipt` (per store: count, ok, error); `receipt.ok` is true only when
every touched store erased cleanly. Idempotent and retry-safe: re-running
after a partial failure converges to full erasure, no store left orphaned, no
queue entry stuck.

**Two delete modes, one path.** The delete button and the lifecycle worker
both call `erase_session`. Immediate (default): the button runs full erasure
now, using the caller's identity. Deferred (when the conversation's space has
a window): the button hides the conversation (`session_metadata.deleted_at`)
and enqueues a `USER_DELETED` purge-queue entry due at `now + window`; the
lifecycle worker erases at expiry and marks the entry done only on
`receipt.ok` — a partial receipt leaves it queued for a later, convergent
retry.

**Retention is team-governed and bounded.** `team_delete_grace` and
`max_idle` are nullable columns on `team_metadata` (plus
`retention_updated_by` for audit) — no separate table — read/written through
the existing `GET`/`PATCH /teams/{id}`. Each value is clamped to a platform
cap (`> cap` → 422); the cap is a ceiling, not a default window — a team that
sets nothing deletes immediately. Personal-space conversations use a
platform-set `personal_delete_grace` (security/post-incident, not
user-shortenable). Retention round-trips through platform export/import
(`team_metadata` is bundled); conversation/runtime delete state
(`session_metadata.deleted_at`, checkpoint-owner rows) is explicitly excluded
— conversations are never platform-migrated.

**Server-initiated erasure is authenticated, never unauthenticated.** The
expiry worker has no user token, so the control-plane mints a
client-credentials service token for its own `control-plane` Keycloak service
account. The runtime checkpoint-delete, runtime history-delete, and
Knowledge-Flow delete endpoints recognize the org-level
`can_manage_platform` permission and waive the per-user **ownership** check
for that principal — authentication itself is never waived. This reuses the
existing platform-admin permission; it forks no second bypass.

**Runtime resolution survives agent-instance deletion (fixed 2026-07-24,
issue #2089).** `session_metadata` carries an internal-only
`source_runtime_id`, captured once at `create_session` time from the
(then-certainly-live) agent instance. `_resolve_runtime_base_url` resolves the
runtime from this stored column first, falling back to the live
agent-instance lookup only for pre-migration rows. Before this fix, deleting
an agent instance permanently orphaned erasure for every session that had
used it — resolution went exclusively through the instance row, which
`unenroll_agent_instance` (a local metadata delete) does not preserve and
never tears down the corresponding runtime checkpoint/history data itself.

**Member-removal erasure is observable (CTRLP-13, shipped).**
`remove_team_member` enqueues each removed user's conversations
(`LifecycleTrigger.MEMBER_REMOVED`) **and** calls `schedule_erasure_task`, so
the erasure surfaces on the admin task/activity surface exactly like a
user-initiated delete — no invisible scheduled work.

**Open (tracked as GitHub issue #2151, P0):** `max_idle` is validated,
clamped, stored, and displayed, but no sweeper enforces it yet — there is no
`IDLE_EXPIRED` `LifecycleTrigger`, no enqueue pass, and no production writer
for `last_activity_at`. The team-settings control for idle expiry does not
yet do anything.

**Evaluation authorization:** the evaluation endpoints enforce ReBAC —
`CAN_READ` to view, `CAN_UPDATE_AGENTS` to create/cancel,
`CAN_READ_CONVERSATIONS` to evaluate real conversations.

**Identity stays pseudonymized:** stored `user_id` is the Keycloak `sub`; no
email lands in any conversation store.

## 36. Contract Notes — KPI preset endpoints & authorization (OBSERV-02) (2026-07-26)

Product/business analytics (active users, sessions, agent usage, tokens,
storage) live entirely in `fred-control-plane`, backed by the shared
OpenSearch KPI store every user-facing backend writes to via a request
middleware (`api.request_latency_ms`, dims `user_id`/`route`/`method`/
`http_status`/`latency_ms`; no `team_id` or `groups` — team context is added
only at domain-level `KPIWriter` call sites that already have a stable
`team_id`, never parsed from the request body, which would break streaming
endpoints). Infrastructure/ops metrics (CPU, memory, cluster health) stay in
Grafana — explicitly out of scope here.

**Endpoint:** `GET /control-plane/v1/kpi-presets/<name>` — each preset is a
`PresetDef` auto-mounted by a registry (`control_plane_backend/kpi/`). The
client sends only a preset name + safe typed parameters (date range,
granularity, optional `team_id`); the backend owns all query logic and
returns shaped data, never raw OpenSearch response objects. Presets are an
explicit allow-list — an unknown name is 400.

**Authorization scope is injected server-side, never client-controlled:**

```
Platform-wide preset, no team_id:      Check(user, can_observe_platform, organization)
Platform-wide, admin-only widgets:     Check(user, can_manage_platform, organization)
Team-scoped preset, team_id given:     Check(user, can_read_members, team:<team_id>)
                                        → filter WHERE dims.team_id = team_id
Personal preset:                       inject WHERE dims.user_id = requesting_user.uid
                                        (no OpenFGA call needed)
```

`can_read_members` is already satisfied by `team_admin`/`team_editor`/
`team_analyst`; a plain `team_member` is not — the team dashboard is not part
of the plain-member experience (which still gets its own personal dashboard,
`user_id`-scoped). Existing platform-wide presets gained an optional
`team_id` parameter with this second authorization branch rather than being
forked into parallel `team_*` handlers — one query shape, two scopes.

**Green/cost metrics** ride the same token-usage presets, computed
server-side from a static, hand-maintained `model_impact_factors.yaml`
(`libs/fred-core`, keyed by `model_name`, `default` fallback row) alongside
the raw token count in one query: CO₂e and kWh are shown everywhere token
usage is shown (required columns); a $ estimate is optional/collapsible.
Both are labeled "estimated" — not billing- or measurement-grade.

**No new settings surface.** Storage quota
(`TeamMetadata.max_resources_storage_size`/`current_resources_storage_size`)
and retention (`team_delete_grace`/`max_idle`, §35) already existed before
this work — the `storage_by_team` preset reads `TeamMetadataStore` directly,
no new table or endpoint. The one narrow, non-blocking gap:
`max_resources_storage_size` is not yet in `TeamMetadataPatch`, so there is
no per-team UI override, only the platform-wide config default.

**No embedded Activités panel (reverted 2026-07-30).** An earlier iteration
embedded the `TaskActivity` organism inline in these dashboards
(`AnalyticsPage`'s admin section, `TeamUsagePage`'s editor/admin sections).
Live review found this duplicated the dedicated Activity surfaces one click
away (`/admin/tasks`, `/team/:teamId/settings/activity`) with no
acknowledgement affordance, so the embeds were removed — `TaskActivity`
itself and the two dedicated tabs are untouched; these dashboards link to
them rather than re-render them. See `TASK-EVENT-STREAM-RFC.md` §2.10 for the
task-acknowledgement mechanism the dedicated tabs use (`POST /tasks/{id}/ack`).
Models-as-capability (`kind="model"` catalog projection, model-routing
fail-closed enforcement) is specified above, not repeated here.

**`team_activity_summary` preset retired (2026-08-08).** Once the embedded
panel above was gone, this preset's only consumer (`TeamUsagePage`'s
Activités trend) had none left — endpoint, response model, and generated
client removed outright. The dedicated Activity surfaces (`/admin/tasks`,
`/team/:teamId/settings/activity`) remain the canonical, ack-capable place
for this data; no replacement preset was added.

**`top_agents_by_conversations` series carry their owning team (2026-09-03).**
Agent instance names are not unique across teams, and the chart's previous
tie-breaker was a truncated instance id - unreadable in a cross-team ranking.
Each series label is now `"<agent name> - <team name>"`, resolved through the
same `TeamMetadataStore` lookup `top_teams_by_sessions` uses (now shared as
`kpi.presets.team_names.resolve_team_names` - its own module, so `kpi/utils.py`
stays the stdlib-only leaf ten presets import for `resolve_interval`). A team
whose registry row is gone falls back to its raw id, logged so a store outage
is not mistaken for a deleted team. Personal spaces are never qualified: their
scope id embeds the owner's uid and has no registry row. A team-scoped request
keeps bare names. Response model and route are unchanged - only the string
values inside `series`/`rows`.

## 37. Contract Notes — TEAM-05, team routing policy (2026-07-30, issue #2118; simplified 2026-08, `llm-routing-simplify`)

**2026-08-16 — chat profile typing (#2365).** The pod catalog now projects
`model_chat_profile_ids` explicitly alongside the complete
`model_profile_ids` inventory. Team picker, universal multi-pod intersection,
and write validation consume the chat subset only. This closes the case where
a known non-chat profile could be saved into `chat_default_profile_id` and
then ignored by the runtime; profile-id naming remains non-semantic.

A team (or personal space) chooses which of the models already available to
it (`can_use`-enabled, see above) is the default for managed execution, and
may override that default for specific agents. This feature never grants new
model access — it only lets the holder of existing access express a
preference among it. Runtime-side merge/fail-closed rules are
`RUNTIME-EXECUTION-CONTRACT.md` §8.32; this section is the product/data/API
contract.

**Data model** (`TeamRoutingPolicy`): `team_id`, `version`,
`chat_default_profile_id: str | None`, `agent_profile_overrides: dict[str,
str]` — a flat `agent_id -> profile_id` map, one profile per agent. `null`
`chat_default_profile_id` means "use the runtime catalog default." There is
no separate rule/operation/purpose concept: a `dict` key is structurally
unique, so there is nothing to disambiguate at write time and nothing that
can collide.

**Resolution (deterministic two-step fallback, no specificity scoring):**
`agent_profile_overrides.get(agent_id)` if the agent has an override, else
`chat_default_profile_id` if set, else the runtime catalog default for
capability `chat`. `resolve_team_override` (fred-runtime) is exactly this
lookup — there is no tie to break, since a dict key maps to exactly one
value.

**Write-time validation** (`PATCH /teams/{team_id}/routing-policy`) rejects
any referenced profile (from `chat_default_profile_id` or any
`agent_profile_overrides` value) whose derived capability id
(`model_capability_id(provider, name)` — coarser-grained than a profile id,
since two profiles can share one `(provider, name)`) is not currently
`can_use`-enabled for the team, or not present on **every pod the team's own
agent instances actually run on**
(`capabilities/catalog.py::universally_available_chat_model_profile_ids`,
intersection — not the union this section's admission catalog uses, since
whichever of the team's own pods serves a turn must resolve the chosen
profile). Each `AgentInstance` is pinned to one pod for its life, so a pod
this team has no instance on is out of scope; a team with no instances yet
falls back to every enabled pod. The check is best-effort per relevant pod —
an unreachable pod is skipped, not treated as failing every team's write —
since genuine drift is still caught at the moment it would matter by
`RoutedChatModelFactory.select` (fred-runtime) failing closed with
`TeamRoutingProfileDriftError`. The same profile id must also map to the same
model capability id (`provider`, `name`) on every pod in scope; equal names
with different concrete meanings are excluded. Only ids in each pod's
explicit `model_chat_profile_ids` subset are eligible; a known
language/embedding/image profile is invalid for this chat-only policy. The
`available-models` picker (§ below) applies the same intersection filter, so
it never offers what the write would reject.

**Authorization:** read — `team_admin`, `team_editor`, `team_analyst` (a
plain `team_member` is denied); write — `team_editor` only.
`team_admin`/`team_editor` are orthogonal, not hierarchical
(`platform/REBAC.md`) — `team_admin` has zero write authority here and can
only constrain indirectly via model enablement (a platform-admin lever). A
personal team's owner already holds `team_editor` unconditionally, so the
same endpoint serves personal spaces with no special-casing.

**API:** `GET`/`PATCH /control-plane/v1/teams/{team_id}/routing-policy`
(`PATCH` is a full typed replacement); `GET
/teams/{team_id}/routing-policy/available-models` (#2167) — a team-facing
read endpoint distinct from the platform-admin-only
`CapabilityTeamMatrixDrawer` data, sharing the same `team_admin`/`team_editor`
read gate and the same catalog-aggregation + `usable_capability_ids`
building blocks the write path validates against.

**Frontend:** `TeamSettingsRouting` — one panel (team settings "Routing"
entry, gated on `canUpdateResources`/`team_editor`, reused unconditionally
for personal spaces), a picker for `chat_default_profile_id` plus
zero-or-more per-agent override rows, both scoped to
enabled+universally-available profiles. A profile referenced by a stored
policy that has since become unavailable still renders as a selectable
option, flagged rather than silently dropped. `team_admin` sees the same
panel with every input disabled (read-only), not a second component.

**Explicit non-goals (V1):** per-user routing inside a shared multi-member
team (distinct from personal-space support, which is just a team routing
policy scoped to a one-member team), model temperature/timeout tuning, a
per-message composer picker, direct `models_catalog.yaml` editing from the
product. Per-agent routing (`agent_profile_overrides`) is in scope, not a
non-goal.

## 38. Contract Notes — team image renamed banner → avatar (2026-08-08, #2300)

The per-team uploaded image is now a **square avatar**, not a wide banner.
The rename is API-surface deep but stops short of the database:

- **Read field:** `Team.avatar_image_url` (was `banner_image_url`) — on the base
  `Team`, so it rides on `bootstrap.available_teams`, `GET /teams`,
  `GET /teams/{id}` alike. Presigned URL (or a stored absolute URL) to the
  team's avatar object, or `null`.
- **Write field:** `UpdateTeamRequest.avatar_image_url` (was `banner_image_url`).
- **Upload route:** `POST /control-plane/v1/teams/{team_id}/avatar` (was
  `/banner`) — multipart, max 5 MB, JPEG/PNG/WebP. Handler `upload_team_avatar`,
  error `AvatarUploadError`.
- **Storage layer unchanged (Option A):** the DB column and the `fred_core`
  `TeamMetadata`/`TeamMetadataPatch` fields keep their legacy
  `banner_object_storage_key` / `banner_image_url` names — no migration. The
  control-plane `update_team` bridges the public `avatar_image_url` write field
  to the storage layer's `banner_image_url` before persisting. New avatar
  objects are stored under `teams/{id}/avatar-<uuid>.<ext>`.

The frontend uploads the image through an in-app square crop editor that
exports a bounded 512×512 WebP, so avatars are small regardless of the source
image (a backend image-resize safety net remains a follow-up).

---

## 39. Contract Notes — PROMPT-06, prompts marketplace (2026-08-10, #2317)

The global prompts marketplace ("Prompts de la communauté") shipped as a **live
visibility flag**, not a published snapshot. This is a deliberate change from
the original PROMPT-06 sketch (which proposed a separate frozen snapshot); the
snapshot machinery was unnecessary because nothing persistently references a
published row. Durable design: `docs/swift/design/PROMPTS.md` §6.1.

**Model.** New `PromptRow.published: bool` (default `false`; migration
`0dd1e72106af`, `server_default false`), surfaced on `PromptSummary` /
`PromptDetail`. Publishing shows the team's own live row on the marketplace:
edits propagate immediately and `session_count` is shared between origin-team
and external usage (total, global usage). Import resets the counter (copy-by-value).

**New types.** `MarketplacePromptSummary` (= `PromptSummary` + `team_id` +
`team_name`; preview only, no full text), `MarketplacePromptDetail`
(= `PromptDetail` + `team_name`; full text), `MarketplaceImportRequest
{ target_team_ids }`, `MarketplaceImportResponse { results: [{ team_id,
prompt?, error? }] }`.

**Endpoints.**

- `POST /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/publish` and
  `.../unpublish` — flip the flag; `can_update_resources` on the author team.
  Publishing a personal-space prompt is rejected (400).
- `GET /control-plane/v1/marketplace/prompts` — every published prompt across
  all teams, `session_count` DESC, each with `team_name`, **preview text only**
  (the listing payload stays small however many prompts are published). Any
  authenticated user; **not team-scoped** (the first prompt read that
  intentionally bypasses team membership, gated only on the `published` flag).
- `GET /control-plane/v1/marketplace/prompts/{prompt_id}` — one published
  prompt's full text (`MarketplacePromptDetail`), fetched on demand when a card
  is opened. Any authenticated user; published prompts only (else 404).
- `POST /control-plane/v1/marketplace/prompts/{prompt_id}/use` — increment the
  shared counter without team membership; published prompts only (else 404).
- `POST /control-plane/v1/marketplace/prompts/{prompt_id}/import` — copy-by-value
  into each `target_team_ids` the caller can edit. Targets are deduped and
  imported **concurrently**; each is authorized independently
  (`can_update_resources`), and an unauthorized/unknown target yields a
  per-target `error` rather than failing the whole request. Name collisions in a
  target team are avoided with an `_imported-N` suffix.

**Deferred:** no moderation surface in v1. Unpublish is available to editors of
the author team, including directly from the marketplace (UX convenience).

---

## 40. Contract Notes — runtime chat-input policy projection (2026-08-12, issue #2253)

`ExecutionPreparation.max_chat_input_chars: int | null` is an optional,
read-only projection of the selected runtime pod's deployment policy. Runtime
`/agents/templates` publishes the value per template because it is pod-scoped;
control-plane reads it from the same template response already used to resolve
capability metadata. One preparation therefore performs no additional runtime
request, stores no duplicate setting, and introduces no cache.

The field remains optional for rolling compatibility with older runtime pods.
When absent, control-plane omits it from the serialized preparation and managed
chat omits its counter; the runtime backend remains the enforcement boundary.
Control-plane does not interpret, override, or persist the value and does not
apply a second chat-message validator.

## 40. Contract Notes — platform-wide chat model binding (2026-08-15, issue #2365)

An org-admin can assert one authoritative `(provider, name, settings)`
binding for the `chat` capability that overrides whatever every runtime pod
would otherwise resolve locally — the concrete lever for a deployment where
the operator knows what's actually reachable/licensed and no pod's shipped
catalog does. Runtime-side precedence, ReBAC exemption, and the trusted
per-turn resolution channel are `RUNTIME-EXECUTION-CONTRACT.md` §8.55; this
section is the product/data/API/persistence contract.

**Chat-only in V1.** `PlatformModelBinding.model_capability` is a
route-local `Literal["chat"]` constant, not the global `ModelCapability`
enum — `language`/`embedding`/`image` have no production consumer and are
not representable through this API. At most one row ever exists, enforced
by a database `CHECK (model_capability = 'chat')` constraint (not just
application code), so the store/service path structurally cannot insert a
`language`/`embedding`/`image` row. An absent row means unset — there is no
natural "off" value for a `(provider, name)` pair, so "clear this binding"
is row deletion, not a stored `false`.

**Settings boundary** (`ModelBindingSettings`, `fred-sdk`). A strict, typed
allowlist (`extra="forbid"`) — every field is a named generation knob
evidenced by `fred_core.model.factory.get_model()`, never an open
`dict[str, Any]`. Guarantees, precisely: no credential-designated field
(`api_key`, `token`, ...) and no generic auth/header/cookie/client
passthrough container exist to receive one; any key outside the named
allowlist is rejected, and every URL-typed field rejects non-`http(s)`
schemes and userinfo (`user:pass@host`); numeric/boolean fields are strict
(no `"4096"` → `4096`, no `1` → `True`) and range-checked, never silently
coerced. What it does **not** do: inspect whether an arbitrary *value*
placed in an allowed field is itself a secret — operators must never place
a credential in an allowed value, this only closes the field-shape channel.
`provider` is restricted to `fred_core.model.models.ModelProvider` (closed
JSON Schema `enum`, published on the generated OpenAPI/TypeScript client —
never a hand-maintained duplicate list), and a provider with additional
required settings (`azure-openai`, `azure-apim`, `vertex-ai`,
`vertex-ai-model-garden`) is validated against those exact requirements
before persistence — a binding a provider could never actually construct
against is rejected at write time, not left to fail at runtime model
construction on every subsequent managed turn. `timeout`/`http_client_limits`
are deliberately absent (see §8.55); `request_timeout` is present and
applied fresh per model construction.

**Persistence** (`platform_model_binding` table,
`PlatformModelBindingStore`). Every read re-validates the row through
`ModelBinding` — a row that bypassed the store's own writer (or predates a
contract tightening) fails closed on `get()`, not just at write time. `set()`
retries once on the concurrent first-insert race (two admins, or a client
retry, both observing no row and both attempting an insert on the single-row
primary key) rather than surfacing a raw `IntegrityError` as a bare 500.

**Authorization:** `organization_authz.require_manage_capabilities`
(`organization#can_manage_capabilities`, §50), the same shared gate as
`GET /admin/capabilities` — no team dimension (this is a platform-wide
routing assertion, not a per-team permission, same reasoning as
`model_reasoning`).

**API:** `GET`/`PUT`/`DELETE /control-plane/v1/admin/platform/model-bindings`
— no `{model_capability}` path segment (chat-only, nothing to select
between). `GET`/`PUT`/`DELETE` all return `PlatformModelBinding`
(`binding: ModelBinding | None`, `updated_by`, `updated_at`);
`response_model_exclude_none=True` omits an unset `binding` rather than
serializing `null`. `PUT`'s body is `SetPlatformModelBindingRequest{binding:
ModelBinding}` — `ModelBinding`'s own validators (provider enum,
provider-required-settings, `ModelBindingSettings`) fire at request-parsing
time, before this route's authz even runs, so a 422 on a bad binding never
reaches the store.

**Frontend:** `PlatformModelBindingsPanel` — an `InlineDrawer` opened from
`FeaturesPage`'s Models tab, sibling to `CapabilityTeamMatrixDrawer`.
Renders exactly one row (chat), never a 4-capability list. Settings are
edited as raw JSON text (not a key/value rows editor, since
`ModelBindingSettings` is a strict typed shape a rows editor storing
`string` per row cannot represent without lossy coercion) — the editor
parses explicitly, reports invalid JSON inline, and only submits a parsed
JSON object; the server's strict settings contract remains the actual
security boundary, the editor does not re-implement a client-side
credential-key check. Component UX detail: `COMPONENT-UX.md`.

**Explicit non-goals (V1):** `language`/`embedding`/`image` capability
bindings, process-wide transport tuning through this binding (stays
pod-local in `models_catalog.yaml`), dynamic shared-client pool
replacement, a browser-forwarded or session-snapshot resolution channel —
the binding is trusted and resolved fresh per turn, server-to-server, by
design (§8.55), never forwarded through the client the way
`chat_default_profile_id`/`agent_profile_overrides` are.

## 41. Contract Notes — the composer's effective chat model (2026-08-17, issue #2387)

**Problem.** The composer named the model whose *reasoning* was enabled
platform-wide (§40 / REASON-01 §7), not the one the turn routes to. With a
platform binding or any override in force, it displayed a model that was not
answering.

The justification recorded in `_platform_reasoning_control`'s docstring rested
on two premises, both of which had become false: that routing "resolves per
*operation* at runtime" (operations were removed by #2365) and that "chat
controls are computed once per session" (prepare-execution returns a fresh
`chat_controls` on every send).

**New endpoint.**

    GET /control-plane/v1/teams/{team_id}/routing-policy/effective-chat-model
        ?agent_instance_id={id}
    → EffectiveChatModel

| Field | Meaning |
| ----- | ------- |
| `name` | The concrete model name. All model fields are `None` together, meaning nothing resolved. |
| `display_name` | Ops-authored label; `None` leaves the frontend on its name/id prettifying fallback. |
| `capability_id` | The `kind="model"` capability id, for joining against team enablement. |
| `enabled_for_team` | `false` when the resolved model is not `can_use`-enabled for this team, so the turn will fail with `ModelNotUsableError` before the LLM call. |
| `reasoning_enabled` | Whether reasoning actually runs on **this** model. The composer must not offer the reasoning toggle when `false`. |

**Scoped to what the composer renders.** It deliberately does not report which
precedence level won, or the winning profile id. That is POLICY detail, readable
only by an elevated team role (§37 / #2167), and no surface displays it —
returning it would mean either leaking the policy to a plain member or gating a
field nobody reads. `[V2][MODEL_ROUTING]` in the pod log remains where the
deciding level is visible.

**Authorization — plain membership (`can_read_members`), deliberately NOT the
elevated-role gate** §37's policy reads use. Anyone entitled to hold a
conversation with an agent is entitled to know which model answers them, and
that is safe precisely because the response carries no policy detail (above).
Editing the policy stays `team_editor`-only.

**`reasoning_enabled` and the reasoning toggle.** The `reasoning_toggle` control
on `ExecutionPreparation` answers "the platform enabled reasoning on *some*
model and this agent offers it" — it cannot answer "the model this turn routes
to is one of them", because that needs the pod catalog and the send path must
stay free of catalog fetches. So the composer combines the two: the control
decides whether a toggle could exist, `reasoning_enabled` decides whether it
would do anything. `RoutedChatModelFactory` STRIPS reasoning settings for a model
absent from `reasoning_enabled_model_ids` (§8.55 / REASON-01 §5.6.2), so
offering the toggle without this check meant offering an inert control — observed
in production with reasoning on `mistral-small-latest` and a team override
routing to `mistral-medium-latest`.

**Why its own read, not an `ExecutionPreparation` field.** Resolving the two
pod-owned precedence levels requires the pod's `/agents/models-catalog`
(`RUNTIME-EXECUTION-CONTRACT.md` §8.56). Prepare-execution runs on **every
send** and is contractually free of pod-catalog fetches, and
`aggregate_capability_catalog` is uncached — putting this there would fan out to
every pod per message. This endpoint is called per chat-page open instead, the
same cost profile as `available-models` beside it, and it is tagged under the
same `ControlPlaneRoutingPolicy`/`teamId` RTK entity as the policy read/write so
saving a policy refetches the label instead of leaving a stale model on screen.

**One deliberate widening, recorded.** When a platform binding is in force, this
endpoint reveals the bound model's `name` (and its derived `capability_id`) to
any team member, where §40's admin CRUD surface is org-admin only. No contract
made that identity confidential, and naming the model that answers is the whole
point of the feature — but it is a real change in who can observe it, so it is
written down rather than left implicit. `ModelBinding.settings` (base URLs,
Azure endpoints) is never returned; only the two identity scalars are.

Symmetrically, the read is scoped to a pod, not to the deployment-wide
intersection §37's picker uses. That is not a contradiction: the intersection
governs what a team may *select* (and is enforced at write time so a saved
choice means the same thing everywhere), while this answers what one pinned
instance will actually *run*. If a pod's catalog drifts after a write, the
per-pod answer is the truthful one.

**Pod scoping.** The pod consulted is the instance's own `source_runtime_id`,
never an aggregate: an `AgentInstance` is pinned to one pod for its whole life
and a turn is always prepared against that same pod, so another pod's catalog
has no say in what this agent will run.

**Degradation.** An unreachable pod, an unknown instance, a pod source that is
missing from the platform catalog **or disabled in it**, or team-policy drift (a stored profile the pod does
not advertise — the condition `TeamRoutingProfileDriftError` raises at turn time)
all return an all-`None` result rather than raising. A pod being down must not
break the chat page, and inventing a model would be worse than showing none.

**`enabled_for_team` is reported, not hidden.** The composer names the model and
flags it, so a user learns *why* a turn will fail instead of meeting an opaque
error — the same diagnosability rule REASON-01 §8 applies to the reasoning
control. Always `true` when a platform binding decided, which bypasses team
enablement by design (§40's ReBAC exemption).

**Explicit non-goals:** making the chip a model *picker* (it stays read-only),
surfacing the deciding precedence level in the UI, per-turn re-resolution, and
any non-chat capability — `embedding` has no
production consumer.

## 42. Contract Notes — global info banner (2026-08-19)

`FrontendConfig` (§3.1.1) gains one optional field, `info_banner`
(`InfoBanner`: `color` + `titles`/`messages` locale maps + `links: [{url,
labels}]` + `auto_hide_seconds`), sourced from control-plane deployment
config `platform.frontend.info_banner`. When set, the frontend renders one
full-width, non-dismissable announcement banner (`InfoBanner`, mounted once
at the app root) above the app content on **every** page, resolving texts
from the active i18next locale with `en` fallback and pushing content down
instead of overlaying it. Persistent by default; the optional
`auto_hide_seconds` (integer > 0) makes the banner remove itself that many
seconds after app load. `null`/omitted → nothing rendered — the shipped
default: `values.yaml` (prod) and `configuration*.yaml` (dev) carry only
commented-out example blocks.

Boundary rationale (§3.1.1 vs §23): unlike `upload_warning` (post-auth
surfaces only), the banner's whole point is to show on every page — the
GCU-acceptance and root-bootstrap screens included, which render *before*
the authenticated `/frontend/bootstrap` can succeed. So it follows the
`gcu_version` precedent, not the `upload_warning` one: a pre-auth field on
the public surface. It carries only deployer-authored announcement content
— never secrets or per-user state — keeping §3.1.1's "no second bootstrap
payload" rule intact. One deliberate scope note: on auth-enabled
deployments the login page itself is Keycloak-hosted (`login-required`
redirects away before the SPA renders), so the banner cannot cover the
login screen — pre-auth here means "before the authenticated bootstrap",
not "on the IdP's page".

## 43. Contract Notes — platform-role management, root-protected (2026-08-21, issue #2405)

Three routes give the product its first surface to grant/revoke the two
org-level platform roles (until now written only by root bootstrap, the
kea→swift migration, and the bundle importer):

- `GET /users/platform-roles` — every `platform_admin` / `platform_observer`
  holder, as `PlatformRolesResponse`: per-holder `UserSummary` + `relations`
  + `is_bootstrap_root`, plus a top-level `caller_is_bootstrap_root` display
  flag for the admin UI (the backend guards never rely on it).
- `POST /users/{user_id}/platform-roles` — body
  `{relation: platform_admin | platform_observer}`; 204, idempotent
  (`add_relation` ignores duplicates); 404 when Keycloak affirmatively does
  not know the target uid (a typo'd uid must not become a live tuple for
  whoever ever authenticates with that sub — skipped when Keycloak M2M is
  disabled, where existence cannot be verified).
- `DELETE /users/{user_id}/platform-roles/{relation}` — 204; 404 if the
  target does not hold the relation **as a direct tuple**.

Direct tuples only: `schema.fga` defines `platform_observer: [user] or
platform_admin`, so this surface reads via the direct-tuple primitives
(`list_direct_relations` / `has_direct_relation`), never expanded reads
(ListUsers) — an admin's computed observer membership is neither listed as a
holder entry nor revocable (no tuple exists to delete; the expanded read
would have 204'd a silent no-op). Revocations emit `authz.relation.revoked`
to the audit stream with `actor_uid`, symmetric to `add_relation`'s
`authz.relation.granted`.

All three gate on `can_administer_users`. The `platform_admin` relation
carries two additional service-layer rules (PLATFORM-ADMIN-DELEGATION-RFC.md
§3 — "root-managed admins, delegated observers"): granting **and** revoking
it require the caller to be the bootstrap root (the uid in
`platformbootstrap.completed_by`, the anchor §27's teardown already
preserves) — 403 otherwise; and a DELETE may never target that uid — 403
for every caller, the root itself included, because bootstrap never reopens.
If bootstrap never ran (row absent), both `platform_admin` routes return 409
— run `POST /bootstrap/platform-admin` first, which is still open in that
state by definition. `platform_observer` carries none of these
restrictions. No new ReBAC relation, no schema change, no DB migration.

Same-invariant guard on an existing route: `DELETE /users/{user_id}` now
403s when the target uid is `platformbootstrap.completed_by` — deleting the
root's Keycloak account would freeze the `platform_admin` population the
same irreversible way (the uid could never authenticate again while
bootstrap stays permanently closed).

## 44. Contract Notes — new teams are private by default (2026-08-26, issue #2433)

**Supersedes §30's "Default and migration" paragraph.** `Team.visibility`
now defaults to **`private`**: a brand-new team starts invisible to
non-members (no marketplace listing, `GET /teams/{id}` 403s for them) until
a team admin deliberately flips it to public in the team settings. §30's
mechanism is unchanged — only the starting value flipped.

**Where the default lives.** `TeamMetadataStore.create` inserts only
`(id, name)`, so the governing default is the ORM column default
(`TeamMetadataRow.visibility`, fred-core), mirrored by the `TeamMetadata`
and `Team` Pydantic defaults so the OpenAPI spec agrees. Migration
`0c70cb820802` aligns the DB `server_default` for raw-SQL inserts only.

**`create_team` grants nothing.** The immediate TEAM-09 `public`-relation
grant at creation is now conditional on the created metadata's visibility —
for a default (private) team no ReBAC `public` tuple is ever written, not
even transiently (a grant-then-lazy-revoke would leave the team readable by
anyone until the next `_list_teams` pass). The idempotent
grant/revoke backfill in `_list_teams` (§30) is unchanged and remains the
backstop. Corollary for the creator: a platform_admin who creates a team
without naming themselves in `initial_team_admin_ids` holds no `can_read`
on it once `create_team` returns (previously the unconditional `public`
grant kept it readable) — by design (RFC §24.2, the creator is not
necessarily a member), and the registry/admin surfaces they operate are not
`can_read`-gated.

**Existing rows are untouched — no data migration.** Migration
`0c70cb820802` moves the `server_default` only; every stored `visibility`
keeps its value, so no team already in the registry changes state. Hiding
one remains a per-team admin action.

**Where a row is *materialized* for a team that pre-dates it, the platform
default applies — nothing guesses a visibility.** Two paths can create a
registry row for a team that already exists in the wild: `create_team`
called by the bundle importer for a team referenced only from `users.json`,
and the knowledge-flow storage backfill (`backfill_storage_usage.py`).
Neither knows what discoverability that team's admin intended, so neither
states one: both take the platform default and land the team private.
Consequence to know before running the backfill on a legacy platform: a
team it materializes that *was* marketplace-listed loses that listing on
the next `GET /teams` (`_list_teams` revokes the ReBAC `public` relation
for any private team), and a team admin re-publishes it deliberately.
Publishing a team on a guess is the outcome this default exists to
prevent. The one place that still forces `public` is `importer.py`'s
`row.get("visibility", "public")` for a bundle exported *before the field
existed* — there the value is not a guess but the exporting platform's
actual behavior, since every team was unconditionally public then.

**Personal spaces now say so.** `build_personal_team` states
`visibility: "private"` explicitly (previously it inherited the schema
default and reported `"public"`) — truthful for a space that was never
marketplace-listed and never readable by non-members. Joining-mode UI
consequence (already shipped in #2398): a new team's settings show the
locked "manual only" joining state until it is made public.

---

## 45. Contract Notes — `AgentTemplateSummary.default_capability_ids` (2026-08-28, issue #2458)

**What changed.** `GET /teams/{team_id}/agent-templates` now returns
`default_capability_ids: list[str]` on every `AgentTemplateSummary`. Additive
and optional — an older client ignoring it is unaffected.

**Why.** The agent-creation form always submits an EXPLICIT `capability_ids`
whenever the template advertises any capability, and an explicit `[]` means
"select nothing" in `_apply_capability_selection` (§ capability selection;
RFC AGENT-CAPABILITY §8.1). The template-default path there only runs for a
`None` selection, so it was unreachable from the UI: a template's declared
defaults were silently dropped on every new instance, and the user had to
tick them by hand. Found on `platform_ops`, whose sole default is
`platform_postgres` (#2458); it affected every template with defaults,
including `general_assistant`'s `document_access`.

**The filtering asymmetry — deliberate.** `available_capabilities` on the same
payload IS narrowed to what the team `can_use` (CAPAB-01 / #1980);
`default_capability_ids` is NOT. The field describes what the *template*
declares, which is a static, non-secret property of a template the team was
already granted in order to see the summary at all. The client intersects the
two, so an admin-gated default a team is not enabled for is neither pre-ticked
nor rendered — the intersection, not the raw list, is the authorization
boundary. Filtering both would make the field misreport the template; filtering
neither would pre-tick a box whose save 403s.

**Applies to new instances only.** An instance enrolled before this field
existed persisted a genuine `selected_capability_ids: []`, which is
indistinguishable from a deliberate "no capabilities" — so
`materialize_default_capability_selections` skips it by design (it backfills
`None` rows only). Existing agents do not gain their template's defaults
retroactively and must be re-ticked by hand.

## 46. Contract Notes — team applications are runtime-registered, frame-hosted UIs (2026-08-31)

Fred has one generic V1 host for trusted applications a deployment registers.
Registration is deployment configuration, expressed like
`platform.runtime_catalog_sources`: a flat `platform.application_sources` list
whose entries carry `app_id`, browser-facing `ui_prefix`, `version`, `icon`,
localized `display_name` and `description`, and `enabled`. It registers no
proxy upstream: routing belongs to the frontend gateway, so `app_id` is the
only key the two registrations share. Duplicate `app_id` values are rejected
at config load, as is an own-origin `ui_prefix` that is not exactly
`/apps/<app_id>` — the gateway routes on that segment, so any other own-origin
path is a silent 404 the browser cannot distinguish from a cold service.
`enabled: false` parks an entry without deleting it, but withdraws it only
from the catalog; its gateway routes keep serving until that half is removed
too. Its existing team grants keep living as well: revoking one stays
available for a parked entry, while granting a new one does not. An entry
withdrawn from the catalog must still be unwindable, or the grants an operator
parked it to retire are stranded. Removing an entry makes the application
unavailable on the next config load, not on the next rebuild.

The typed deployment-wide `enableApplications` feature gate defaults to
`false`. It is an availability boundary, not an authorization relation. While
off, the team application endpoint returns a generic not-found response,
application entries are absent from the administration catalog, application
mutations cannot write relations, the frontend does not mount application
pages or navigation, and both `/apps` and `/app-services` paths return 404.
Registered entries and existing grants remain configured but dormant.
Effective access is therefore:

```text
enableApplications
AND user can_use_team_applications on team:<team_id>
AND team:<team_id> can_use capability:app__<app_id>
AND the frame answers the protocol handshake with an accepted version
```

Applications reuse capability enablement for coarse admission. A registered
`app_id` derives capability id `app__<app_id>`; `app__` is reserved for catalog
`kind="app"`. The discriminator exists only on the JSON-safe
`CapabilityCatalogEntry` and admin wire model: runtime `CapabilityManifest`
continues to accept `tool | agent | model` only. Every registered application
is `admin_gated`; registration alone grants no team access. The admin catalog
entry carries single-string labels, so the mandatory `"en"` display strings are
the ones projected there.

Existing platform-admin capability routes remain the only enablement writers.
Application rows support default-on and collaborative-team controls, but have
no personal-space control or generic team-settings JSON. App changes do not
enter agent dependency, impact, health, suspension, revival, reasoning, or
model-binding paths. Attempts to grant an app to a personal team are rejected;
revocation remains available to clean up a stale personal tuple.

The team discovery contract is:

```text
GET /control-plane/v1/teams/{team_id}/applications
  -> ApplicationList { schema_version: "1", items: ApplicationSummary[] }
```

`ApplicationSummary` carries `id`, `version`, `name` and `description` as
locale maps, validated `icon`, and `ui_prefix` — and nothing that would tie an
application to a Fred build. There is no catalog revision, no host API version
and no contract digest, because no application code is compiled into Fred for
them to describe. `name`/`description` are locale maps rather than translation
keys for the same reason: an independently deployed application has no entry in
Fred's translation bundle. `"en"` is always present and is the fallback.
`service_upstream` is deliberately absent from the wire: the browser reaches an
application API only through the proxy. The service canonicalizes the team id
and checks the user's `can_use_team_applications` permission before team or
application metadata. A collaborative team then sees only registered items for
which that team has `capability#can_use`. Personal teams return an empty list.
With ReBAC disabled, all registered items are returned for collaborative teams.

The frontend keeps two generic routes, `/team/:teamId/apps` and
`/team/:teamId/apps/:appId/*`. It resolves the authorized response before
anything else, so an unknown or unentitled id learns only `unavailable` and no
frame is created. A resolved application is rendered in an iframe whose `src`
comes from `ui_prefix` — validated to be `http(s)` before it can become a
`src`, with the frame's target origin derived from the same value. Host states
are `catalog-loading`, `unavailable`, `connecting`, `protocol-mismatch`,
`unreachable`, and `render`, and render failures are contained per app.

Parent and frame communicate only over `postMessage`, from the first message:

```text
frame -> host : fred:ready { protocolVersion }
host  -> frame: fred:context { protocolVersion, applicationId, context }
                fred:route { subPath }
                fred:response | fred:response-error { requestId, ... }
frame -> host : fred:navigate { path, replace }
                fred:open-chat { sessionId? }
                fred:request { requestId, path, method, headers, body }
```

The host accepts a *set* of protocol versions (currently `"1"`) because fork
teams release their UI images on their own cadence; a version outside that set
renders `protocol-mismatch` rather than a broken screen. Frame messages are
admitted only from a closed parser — unknown types, oversized header maps,
non-allowlisted methods, and malformed request ids are dropped before reaching
Fred state, the router, or diagnostics. A request id already in flight is
refused with `fred:response-error` rather than dropped: the id is the channel's
only correlation token, so admitting it twice would leave one frame request
answered twice and one call outside the concurrency bound. The context handed
over is plain cloneable data: team identity, base and sub path, locale.

`fred:navigate` moves the user only inside the application's own subtree: its
path is resolved against `basePath` and an absolute, traversing, or schemed
path throws, which the host swallows rather than reporting, so a frame cannot
probe the boundary.

`fred:open-chat` is the single exception, and it is deliberately narrow. It
names **no route** — the parser discards any path or team a frame attaches —
and the host builds the target from the team it is already rendering. Where an
application can send the user is therefore bounded by the host rather than
chosen by the frame. That bound is a runtime one, not a fixed set settled in
review, and the next paragraph is what establishes it.

Its one field, `sessionId`, is a **candidate rather than a destination**. The
host matches it against `GET /teams/{team_id}/sessions`, which is scoped to the
caller (`user_id=user.uid`), and takes the agent instance from the matched
record — never from the frame. So the most a compromised application can do is
reopen a conversation its own viewer already owns and can reach from the
sidebar. Anything else — an unknown id, a teammate's, one aged past the
listing's newest-50 window, or a listing that fails — falls back to a new
conversation with the team's only enabled agent, or to the agents surface when
that choice is ambiguous.

Nothing about the conversation travels on this message. An application that
wants a conversation to be about one of its records records that intent through
its own service, and its capability resolves it on the agent side from the
runtime identity — so the record never passes through a channel the model or
the frame could redirect.

The authenticated request adapter stays on the host side of that channel. It
derives `/app-services/<app_id>/teams/<team_id>/...`, owns token refresh and
one 401 retry, and rejects absolute, traversing, or protected-header inputs;
the frame supplies only a relative path and an ordinary payload over
`fred:request`. A 401 from an application service is that service's own
entitlement decision and never ends the Fred session; only a token refresh that
fails does, so one misconfigured application cannot log the user out. **No
application frame receives Fred's store, Keycloak object, or raw token**; the
backend service receives the caller's bearer only on the proxied request leg.
Keeping the credential out of frame code is the property that makes moving the
frame to a separate origin a configuration change rather than a redesign.

Two browser-facing prefixes exist, and only these:

```text
/apps/<app_id>/          -> the application's own UI service
/app-services/<app_id>/  -> the application's own API
```

Both are served by the frontend gateway from `FRONTEND_APPLICATIONS_JSON`,
which pairs each `app_id` with a server-side `ui_upstream` and optional
`service_upstream`. The gateway forwards the entire `/apps/<app_id>` prefix so
the bundle's own absolute asset URLs resolve, and strips `/app-services/<app_id>`
because the application constructs those paths itself. The three-state service
discipline is unchanged and now also covers the UI prefix: an unregistered
`app_id` is 404 in both namespaces, a registered application with no
`service_upstream` is 503 under `/app-services/`, and `service_required: true`
with no `service_upstream` fails container startup rather than serving a
permanent 503. The gateway applies a deployment-owned client body budget to
both namespaces (10 MiB by default) and disables intermediary request buffering
on the service leg. Application services remain responsible for equal or
smaller per-request limits, aggregate concurrency bounds, and authorization
before consuming a request body.

The gateway never authorizes. In the arm's-length tier the control plane is the
entitlement authority; in the first-party tier the application backend checks
entitlement locally through the narrow SDK described below. A gateway
registration with no matching `application_sources` entry still proxies both
prefixes, so the gateway list must stay a subset of the catalog.

`app__<app_id>` is derived by `application_capability_id` (fred-core), which
unlike `model_capability_id` does **not** normalize characters outside the id
charset. A registered `app_id` is already constrained to a subset of
`CAPABILITY_ID_PATTERN` at config load, so an id needing repair is one no
catalog accepted; normalizing it on an authorization path could resolve it
onto a neighbouring capability's id instead of failing closed.

### Two application trust tiers (2026-09-04)

An application backend authorizes each request in one of two ways, and the
tier is a deployment decision, not something the application selects:

| Boundary | Arm's-length | First-party |
| --- | --- | --- |
| Who | Independently deployed code, any language, with no Fred service or OpenFGA credential | A backend built and run inside the Fred perimeter; admission is an explicit devops act |
| Entitlement | Forward the caller's bearer to `GET /teams/{team_id}/applications` and require its own id in the response | Ask the named checks on a process-lifetime `RebacSdk` created by `rebac_sdk_factory` |
| Keycloak service identity | None required for entitlement | Its own enabled `security.m2m` client; this is for outbound service calls, not caller validation or OpenFGA |
| OpenFGA identity | None | Its own secret named by `security.rebac.token_env_var`, provisioned and revocable independently; never shared with another backend |

Both tiers verify the caller's bearer locally before entitlement. A first-party
backend runs with `security.profile: c3`, so the incoming JWT must carry the
exact audience in that backend's `security.user.client_id`. That resource-server
client is distinct from both the backend's outbound `security.m2m` identity and
its OpenFGA token.

`await rebac_sdk_factory(security_config, *, kpi_writer)` is the supported
first-party construction path. It fails startup unless the `c3` profile, user
and M2M authentication, and OpenFGA ReBAC are enabled, and unless
`create_store_if_needed` and `sync_schema_on_init` are both `false`, and the
OpenFGA timeout is between 1 ms and 30 seconds. The control plane remains the
store and authorization-model owner. The async factory also initializes
fred-core's process-local user JWT verifier from `security.user`, requires the
backend's process-level KPI writer, creates one private OpenFGA engine, and
resolves the configured store before startup completes. A backend reuses that
facade for requests and awaits `close()` during shutdown (or uses its async
context manager); it never constructs a client per request.

The facade exposes only `check_user_team_permission`,
`check_team_capability`, and `check_application_access`. These are
authorization gates: they return no data and raise on denial. The combined
application check asks team membership first, then the team's grant on
`app__<app_id>`. Every facade check rejects personal spaces before contacting
OpenFGA, so composing the two component checks cannot bypass the collaborative-
team-only application boundary or trigger personal-team self-healing writes.
It exposes no engine, tuple writer, general query, or raw OpenFGA client.

The SDK deliberately reads neither catalog state nor the application feature
gate. `enableApplications: false` still withdraws the normal browser path for
**both** tiers because the gateway returns 404 for `/apps` and
`/app-services`. Parking one catalog entry (`enabled: false`) is narrower: the
arm's-length endpoint stops returning it while the gateway route and team grant
remain, so a directly reachable first-party backend would still accept the
grant. Parking is catalog state, **not a security kill switch**. Revoke the
`app__<app_id>` team grant to withdraw entitlement from both tiers; for an
incident, also block or remove the gateway route. Remove both registration
halves to retire the application.

The planned first-party example intentionally carries no agent capability. It
demonstrates one boundary only — browser to host to application service, local
JWT verification, then the SDK check. Agent-pod writes are a separate delegated
downstream-auth problem; adding them would either retain the existing shared-key
side door or silently expand this work to solve that problem. Any future agent
integration needs its own design and may reuse the runtime's pod-to-pod JWT and
OpenFGA pattern.

Finally, trust does not confer datastore ownership. A first-party application
may own a dedicated store for its own data. Data owned by another Fred backend
must still be reached through that backend's API, bearer-forwarded for
user-scoped operations: the owning backend may enforce object-level ReBAC in
addition to team entitlement, and its schema is an internal detail rather than
a contract. `GET /teams/{team_id}/applications` remains unchanged; Fred's own
catalog and navigation depend on it regardless of tier.

`ui_prefix` is a path today and the frame is therefore same-origin with Fred.
A same-origin iframe is a rendering and lifecycle boundary, not a security
boundary: applications are trusted code a fork builds and deploys, on the same
footing as its agent pods, and the frame is not a sandbox for untrusted code.
The `postMessage` handshake is what keeps the eventual separate-origin move a
configuration edit — `ui_prefix` becomes an absolute `https` URL and nothing
else changes. Anything that would only work same-origin is a defect against
this contract. Durable installed/tombstoned registration, admin-visible
stale-grant cleanup after removal, and `pending_reactivation` on id
reappearance remain deferred lifecycle requirements.

---

## 47. Contract Notes — a team_admin may rename their own team (2026-09-03, issue #2516)

**`UpdateTeamRequest.name` (`PATCH /teams/{team_id}`), 1-180 chars.** A team's
name was set once by `POST /teams` (platform-admin only) and immutable
afterwards; a team_admin who mistyped it, or whose team was renamed in the real
world, had no way to fix it. It now rides the existing team PATCH surface, which
is gated on `can_update_info` — defined as exactly `team_admin` in `schema.fga`.
No new endpoint, no new permission, no governance capability: renaming is team
self-service, unlike creating or deleting a team. Deleting a team from the team
settings stays out of scope.

**`null` is a client error for this field, not "clear the value".** Every other
field on `UpdateTeamRequest` uses `exclude_unset` partial semantics where an
explicit `null` clears the stored value. A team always has a name, so `null` and
a whitespace-only string are both 422; the accepted value is stored trimmed.
`CreateTeamRequest.name` now trims the same way — uniqueness only means
something if both write paths agree, otherwise a team created as `"Ops "` and a
rename to `"Ops"` each clear the pre-check and the unique index and leave two
teams a reader cannot tell apart.

**A rename can 409.** `teammetadata.name` is globally unique (migration
`a8b9c0d1e2f3`), so `update_team` reuses `TeamAlreadyExistsError` exactly like
`create_team`: a `get_by_name` pre-check for the common case, and an
`IntegrityError` catch around the upsert for the concurrent-rename race the
pre-check cannot close. An `IntegrityError` on a patch that renames nothing is
re-raised untouched — `name` is the only unique-constrained column, and a
database failure must not be reported as a taken name. Renaming a team to the
name it already holds is a no-op, not a conflict.

**Personal spaces are not renameable, and need no guard to stay that way.** They
have no `teammetadata` row, so `update_team` already 404s for them through its
normal existence check.

**Consequence for bundle import.** `importer.py` reconciles teams by name, not
id. A bundle exported before a rename no longer matches the renamed team and
creates a new one on import. Accepted for now; the import surface is unchanged
by this issue.

## 48. Contract Notes — platform prompt and platform instructions (2026-08-28, renamed and extended 2026-08-31)

**What it is.** One org-admin-editable text that becomes the **first block** of
every agent's system prompt on the deployment, ahead of each agent's own
template. Runtime side, block ordering and trust boundary:
`RUNTIME-EXECUTION-CONTRACT.md` §8.70.

**Endpoints.**

| Method | Path | Permission |
| ------ | ---- | ---------- |
| GET | `/control-plane/v1/admin/platform/prompt` | `can_edit_platform_prompt` (`require_edit_platform_prompt`) |
| PUT | `/control-plane/v1/admin/platform/prompt` | `can_edit_platform_prompt` (`require_edit_platform_prompt`) |

Both are registered in `authz-endpoint-matrix.yaml`. The gate was
`can_manage_platform` until §50 carved this surface out of that catch-all so a
`prompt_editor` could hold it without import/export, tasks and platform reset.

**No DELETE, on purpose.** Unlike a `(provider, name)` model binding, a text
field has a natural "off" value, and `""` is it. Keeping `DELETE` would give
two ways to say "nothing" with two different meanings:

- **row absent** → `is_default: true` → the pod's `config/platform_prompt.json`
  applies;
- **row present, `text: ""`** → `is_default: false` → **no block at all**, and
  the pod default is deliberately *not* restored.

`PlatformPrompt.is_default` exists so the admin UI can tell the two apart, and
conflating them would silently reinstate the default for an admin who meant to
switch the block off.

**Write shape.** `SetPlatformPromptRequest` replaces the text wholesale,
`extra="forbid"`, capped at 20 000 characters at request parsing — the text is
re-sent on every model call of every agent, so an unbounded field would be
permanent context for the whole platform. `updated_by`/`updated_at` are echoed
back; updates overwrite rather than version (same as §40).

**Delivery to the runtime.** `resolve_platform_prompt_text` is called on the
per-turn `ManagedAgentRuntimeBinding` path and takes **no** `user` argument:
this is a platform assertion resolved server-side, exactly like
`resolve_platform_chat_model_binding`. It reaches the pod on
`ManagedAgentRuntimeBinding.platform_prompt` → `BoundRuntimeContext.platform_prompt`
and is readable from no client-forwarded field.

**Amendment (2026-08-31) — GET fetches the pod default, resolve does not.**
`GET /admin/platform/prompt` on a deployment with no row returns the pod's own
default with `is_default: true`, not `""`. It previously returned an empty
string, which made the admin page show a blank editor on a fresh deployment and
imply no platform prompt was in force when one was.

Both this route and `/admin/platform/instructions` now read the agent pod's
`config/platform_prompt.json` over `GET /agents/platform-prompt`
(`fetch_pod_platform_prompt_file`), because that file lives with the pod that
composes it and control-plane runs in a different container — the same fetch
shape `/agents/models-catalog` already uses. First reachable source wins; the
editor therefore opens on exactly what agents receive.

Both responses carry **`source_unavailable`**, true when no pod answered. `text`
is then empty for lack of an answer rather than because the block is empty, and
the UI must say so: it shows a warning instead of the text and disables Save,
since persisting the empty editor would suppress the platform prompt as though
an admin had chosen to. `source_unavailable` is always false when a row exists —
a stored value needs no pod.

`resolve_platform_prompt_text` keeps returning `None` for an absent row. The
asymmetry is deliberate: GET *describes the deployment to a human*, resolve
*carries an admin decision to the runtime*. Substituting the default there would
send the pod a value it already has on disk and would erase the `None` vs `""`
distinction that lets an admin suppress the block. `is_default: true` also keeps
Save enabled on an untouched default, since adopting it verbatim writes a row
and is a real state change.

**Amendment (2026-08-31).** Renamed from "master prompt", and paired with a
read-only sibling.

| Method | Path | Permission |
| ------ | ---- | ---------- |
| GET | `/control-plane/v1/admin/platform/prompt` | `can_manage_platform` |
| PUT | `/control-plane/v1/admin/platform/prompt` | `can_manage_platform` |
| GET | `/control-plane/v1/admin/platform/instructions` | `can_manage_platform` |

`/admin/platform/instructions` returns `PlatformInstructions` — the markdown
shipped in the `platform_instructions` field of the pod's
`config/platform_prompt.json`, the same file whose `platform_prompt` field seeds
the editable block, which
the runtime renders as the block immediately under the platform prompt for
every agent. **Read-only on purpose**: an admin can rewrite the platform prompt
wholesale, and the tool-usage discipline every agent depends on must not be
rewritable with it. There is no row, no `updated_by`, no PUT and no DELETE; it
changes only with a deployment. It is gated like its editable sibling — it
reveals nothing secret, but one permission for the whole `/admin/platform/`
surface is easier to reason about than two.

Both are read by the same admin page, which renders the instructions verbatim
under the editor with no input control, in the same order the runtime composes
them.

---

## 49. Contract Notes — team wiki (2026-09-06, issue #2571)

A per-team tree of Markdown pages, owned by control-plane. Design and rationale:
[`../rfc/TEAM-WIKI-RFC.md`](../rfc/TEAM-WIKI-RFC.md); this section records the
wire surface only.

**Why control-plane owns it and not the capability that will read it.** A
capability-owned table would live in the agent pod's own database, and there is
more than one agent pod: the same capability installed in two of them would give
one team two silent wikis. A capability's route base URL is also published only
on `ExecutionPreparation`, i.e. during a chat, while the Wiki page lives in the
team navigation and has no chat to be prepared. And a pod being down must not
take a team's written memory with it. The capability (slice 3) reaches this API
through a typed port, the way `platform_postgres` and `document_access` already
reach theirs.

| Method | Path | Permission |
| ------ | ---- | ---------- |
| GET | `/teams/{team_id}/wiki/availability` | `can_read_members` |
| GET | `/teams/{team_id}/wiki/pages` | `can_read_members` |
| POST | `/teams/{team_id}/wiki/pages` | `can_update_resources` |
| GET | `/teams/{team_id}/wiki/pages/{slug}` | `can_read_members` |
| PATCH | `/teams/{team_id}/wiki/pages/{page_id}` | `can_update_resources` |
| DELETE | `/teams/{team_id}/wiki/pages/{page_id}` | `can_update_resources` |
| PUT | `/teams/{team_id}/wiki/pages/{page_id}/content` | `can_update_resources` |
| POST | `/teams/{team_id}/wiki/pages/{page_id}/review` | `can_update_resources` |
| GET | `/teams/{team_id}/wiki/pages/{page_id}/revisions` | `can_read_members` |
| POST | `/teams/{team_id}/wiki/pages/{page_id}/revisions/{revision_id}/restore` | `can_update_resources` |
| GET | `/teams/{team_id}/wiki/rules` | `can_read_members` |
| PUT | `/teams/{team_id}/wiki/rules` | `can_update_resources` |
| POST | `/teams/{team_id}/wiki/proposals/page` | `can_read_members` |
| POST | `/teams/{team_id}/wiki/proposals/edit` | `can_read_members` |
| GET | `/teams/{team_id}/wiki/proposals/{proposal_id}` | `can_read_members` |
| POST | `/teams/{team_id}/wiki/proposals/{proposal_id}/publish` | `can_read_members` |

**Reads are `can_read_members`, deliberately not `can_read`.** `can_read` is
`team_member or public`, so on a team flagged public it would hand a team's
internal knowledge to non-members. Writes are `can_update_resources`
(`team_editor`), like every other team content surface — `team_admin` has no
write authority here, the roles being orthogonal rather than hierarchical.

**A team has a wiki only where the `team_wiki` capability is enabled**
(2026-09-07, issue #2573). Every route in the table above is refused with 404
when an admin has not enabled that agent capability for the team — one gate in
`_require_wiki_access`, so a route added later cannot forget it. 404 rather than
403 for the same reason a hidden agent template answers 404: to a team without
the capability, this wiki does not exist.

One switch covers the team's agents and its people on purpose. A wiki nothing
can read into a conversation is a document store, which the team space already
is; the point of the wiki is that agents work from it. `/wiki/availability` is
the one route NOT behind that gate — answering "no" is its whole purpose, and
the team navigation panel asks it to decide whether to offer the entry.

**Disabling never deletes anything.** The tables are untouched, and re-enabling
brings the wiki back exactly as it was, revisions and all. Revoking access is
not a destructive operation and must never become one.

**Agent writes are two steps, and member-level** (2026-09-07, issue #2574).
`propose_*` stores a revision at `status = "proposed"` — invisible in the tree,
absent from the page's history, changing nothing — and `publish` is what makes
it the page's current revision. The split exists because the platform's HITL
gate pauses a tool *before* it runs and carries only a truncated argument
preview: too little to diff a page, but ample for a proposal id, which is what
the approval card resolves to render the change.

The proposal routes are `can_read_members`, not `can_update_resources`. This is
deliberate (RFC §5.4, §9) and it has a consequence worth stating plainly: a plain
member can propose and publish, so the editor role does not gate wiki content the
way it gates the direct `PUT` routes. What makes that defensible is not a check
but two properties — every published proposal is stamped `author_kind = "agent"`
and leaves the page `needs_review`, and any editor can restore an earlier
revision. Contribution is open; the audit trail and reversibility are the
mitigation.

Three things no configuration reaches: the rules page (refused by its `kind` on
both propose paths), deletion, and renaming or moving — no tool and no endpoint
exists for an agent to do any of them. A `proposed` or `rejected` revision also
cannot be restored: doing so would publish an agent's draft as a human edit and
clear the review mark, undoing the very decision the statuses record.

Declining an approval leaves the proposal pending rather than marking it
refused — the runtime never runs the tool, so nothing reports the decision back.
A queue of pending proposals for editors stays deferred (RFC §12.2).

**A proposal's base is caller-supplied and checked twice (2026-09-08).**
`POST .../proposals/edit` requires `base_revision_id` — the `revision_id` a
prior read of the page returned — rather than assuming "whatever is current
now". It is refused with the same 409 shape as publishing (`current_revision_id`
+ `current_content_md`) unless it matches the page's current revision at that
instant, catching a stale read before a proposal is even stored. The store's
existing compare-and-swap at publish time is the atomic guarantee for a write
landing after the proposal is created; this is the earlier, best-effort half —
neither replaces the other. Before this, the server derived the base from
`current_revision_id` itself, so a write racing between an agent's read and its
propose call went undetected and could be silently overwritten.

**Content is append-only.** An edit inserts a revision and moves the page's
`current_revision_id`; it never updates content in place. History, restore and
conflict detection are consequences of that shape, not features layered on it —
which is why there is no content field on a page, and why `restore` publishes a
new revision rather than deleting the ones after it.

**A stale write is refused, and the refusal carries the current state.**
`UpdateWikiPageContentRequest.base_revision_id` is the revision the author
started from. If the page has moved on, the response is `409` with
`current_revision_id` and `current_content_md` in the body, because whoever
retries — a human in the editor or, from slice 4, an agent redoing its edit —
needs something to rebase onto, and a bare error costs a second round trip to
get it. That payload is read AFTER the failed write's transaction rolls back:
reading it inside would report the revision that transaction opened on — already
superseded under a real interleaving — sending a rebase-and-retry client round
the same loop forever.

**There is no unconditional overwrite.** Omitting `base_revision_id` on a page
that already has a revision is refused exactly like a stale one: a caller cannot
opt out of the check by leaving the field off. It is absent only when creating
the rules page for the first time.

**A proposal identical to the page it targets is refused** (2026-09-07,
WIKI-05, 409). Field evidence: asked to MOVE two pages, an agent used the only
write tool it has and re-proposed each page's existing text byte-for-byte. Both
published, both changed nothing, and the agent read "published" as "moved" —
then told the user a hierarchy that did not exist. A write that cannot change
anything is now a dead end rather than a silent success, and the refusal says
that content is the only thing an agent can change.

**Two pages under one parent cannot share a title** (2026-09-07, WIKI-05).
An agent addresses a page by its path — its titles from the root — so two
namesakes under one parent would give two pages the same address. Refused with
409 on create, rename, move, propose and publish; enforced under concurrent
writes by `uq_team_wiki_pages_sibling_title`, case-folded and
whitespace-collapsed, `NULLS NOT DISTINCT` so the rule reaches root pages too.
The migration renames existing collisions rather than failing. It is the one
part of this change a user can see: a refusal when they pick a title a sibling
already has.

**Every structural writer serializes per team** (2026-09-08, WIKI-05). Create,
move, delete, and proposal publication each run inside
`TeamWikiStore._structural_lock`: a Postgres transaction-scoped
`pg_advisory_xact_lock` keyed on the team, held for the writer's whole
transaction — same primitive as `TeamMetadataStore.advisory_lock`. Parent
existence, the rules-page restriction, the depth cap and the cycle check all
re-run inside that lock against a fresh read, not a snapshot taken before the
write. Without it, two writers touching different rows (an opposing move on
each side, or a child insert racing its parent's delete) could each pass
validation and commit, since neither a bare transaction nor a lock on the
moved row alone serializes across rows with no foreign key between them
(`parent_page_id` deliberately carries none — §5.3). Content-only writes
(`publish_revision`) do not take this lock: they cannot change the tree's
shape, and are already serialized by their own conditional `UPDATE` on
`current_revision_id`. No-op on SQLite, so the guarantee is proven only
against a real PostgreSQL — see the `integration_postgres`-marked tests in
`test_team_wiki_store_postgres_integration.py`.

**A page's slug is an opaque identifier** (2026-09-07), eight random hex
characters minted at creation. It never reaches an agent: the injected index
carries titles only, and the capability resolves a path to a slug itself, so
the HTTP API is unchanged. It is the page's URL and a rename never changes
it — nothing maps an old slug to a page — so deriving it from the title would
guarantee it goes stale on the first rename. Existing rows keep their slugs.

**The rules page is an ordinary page at a reserved slug**, `kind="rules"`. That
is what makes it unique per team: `(team_id, slug)` is already constrained, so
no partial index is needed, and the page inherits history, attribution and
restore for free. Its **content** is reachable only through `/wiki/rules`: the
ordinary page routes refuse a `rules` page for content edit, rename, move and
delete, so it cannot be rewritten by addressing it as a normal page.

`restore` and the review mark are deliberately NOT refused on it. Both are
`can_update_resources`, both are things an editor legitimately wants on the
rules page, and neither is reachable by an agent — the capability (slice 4)
ships no tool for either. Blocking them would cost an editor the ability to roll
back a bad rules edit while buying no isolation, since that same editor can
rewrite the page through `/wiki/rules` anyway.

`GET /wiki/rules` **never creates the row.** It is gated on the member-only read
permission, so materialising the page there would let any team member create the
page that steers every agent's system prompt, and be recorded as its author. A
team that has never written rules gets an empty representation with no
`revision_id`; the row appears on the first `PUT`, which is editor-only.

**One table holds every team's pages.** `team_id` is therefore the tenant
boundary, and it is always derived server-side from the authenticated request —
never read from a body parameter, never assembled by a client. A table per team
was rejected: it would mean DDL at team creation, outside Alembic and invisible
to the migration history.

**`needs_review`** is set when an agent-authored revision is published and
cleared when a human edits the page or an editor clears it explicitly. It is
what gives editors a review queue without building one, and it is the
counterpart of the wiki being open to every member's contributions through an
agent (RFC §5.4).

**2026-09-07 (WIKI-05) — clearing the review mark is recorded, and is not an
edit.** `POST .../review` now stamps `reviewed_at`/`reviewed_by` on the page's
currently published revision, and `WikiRevisionSummary` exposes both. Setting
`needs_review` back to true clears them: the same text is under review again,
so an earlier approval must not still stand against it.

Two bugs closed by that. The endpoint used to overwrite the page's
`updated_by`/`updated_at`, so validating an agent's page relabelled it as
edited by whoever read it — those columns are now left alone, since reviewing
is not editing. And the validation itself was recorded nowhere, which mattered
because the person who approves an agent's text need not be the one it was
written for. The frontend renders the stamp as its own entry in the page
history, at its own time, next to the edit it approves.

**The review mark is anchored to the revision the reviewer displayed**
(2026-09-08, WIKI-05). `SetNeedsReviewRequest` gained `base_revision_id`
(same field, same semantics as the content/rules writes above), and
`TeamWikiStore.set_needs_review`'s page-mark `UPDATE` carries the same
`current_revision_id == base_revision_id` compare-and-swap `publish_revision`
already uses — not a preceding `SELECT`, so a write racing between the
reviewer's read and this call cannot slip through a check that already
passed. Before this, the endpoint took no revision at all: a validation could
land on whatever text happened to be current at UPDATE time, certifying a
revision the reviewer never actually saw if one was published in between.
The refusal reuses the existing 409 shape (`current_revision_id`,
`current_content_md`) rather than inventing a second one, and `updated_at`/
`updated_by` stay untouched either way — the paragraph above's "reviewing is
not editing" holds for the refused path too.

**History is paginated by keyset, not offset, and bounded in SQL** (2026-09-08,
WIKI-05). `GET .../revisions` used to load every revision of a page — content
included — before slicing to `MAX_REVISION_PAGE_SIZE` (50) in Python; a page
edited a thousand times pulled a thousand Markdown bodies out of the database
to return 50. `TeamWikiStore.list_revisions` now takes `limit` and an optional
`before: RevisionCursor` and applies both as a real `WHERE`/`LIMIT`, still
ordered `(created_at DESC, revision_id DESC)`. The endpoint accepts an optional
`cursor` query parameter and `WikiRevisionList` gained `next_cursor`
(`str | None`); the service fetches `limit + 1` rows to learn whether more
remain without a second `COUNT` query, and builds `next_cursor` from the last
row actually **returned**, never the extra one.

The cursor is `base64(isoformat(created_at) + "|" + revision_id)` — opaque to
the client, validated on decode (well-formed base64, both parts present, the
timestamp timezone-aware, the id matching `_new_id()`'s 32-lowercase-hex
shape) and refused with `400`, never left to reach the store or fail as a
`500`. It is a keyset, not an offset: offset pagination on `ORDER BY created_at
DESC` breaks the moment a new revision is inserted while a reader is mid-walk,
since every row after it shifts by one position, producing exactly the
duplicate/gap this fix exists to prevent — a keyset anchored on an
already-seen `(created_at, revision_id)` is unaffected by inserts elsewhere,
because it names a value, not a position. The same tuple that breaks ties in
the `ORDER BY` is what the keyset condition compares on
(`created_at < cursor.created_at OR (created_at = cursor.created_at AND
revision_id < cursor.revision_id)`), so several revisions sharing one
timestamp — an edit then a restore inside the same second, which `_utcnow()`'s
own docstring already calls ordinary — do not destabilize a walk.

**Not a frozen snapshot, and that is closed rather than merely documented for
the one case that mattered.** A pending proposal's `created_at` is
proposal-creation time, not approval time, so in principle an approved
proposal could surface behind a cursor a reader had already established.
`publish_proposal`'s existing base-revision guard (above) closes this for
edit-proposals: a proposal can only be approved while its base is still the
page's current revision, i.e. nothing else was published since it was
proposed — which means the approved revision is always the newest thing on
the page, never older than anything a reader has already paged past. A
new-page proposal cannot exhibit this at all: the page does not exist, and so
has no pre-existing history to page past, until the proposal is approved.

**Restore is unaffected by pagination.** `restore` addresses a revision by id,
returned from any page a reader has fetched — never by its position within
one. `list_revisions` bounding the query changes what one response returns,
never what a caller can act on.

**A proposal a human never acts on resolves after 30 days, not never**
(2026-09-08, WIKI-05). Declining a HITL approval card is invisible to
control-plane: the runtime jumps back to `model` on cancel and
`wiki_publish_proposal`'s body never runs, so nothing reports the decision
back — a decline and simple abandonment are indistinguishable today, and both
left the proposal at `status="proposed"` forever, publishable by any later
retry that reused its id.

The platform HITL epic (issue #1080) confirms this is not settled anywhere
else either — "maximum age of an unanswered prompt" is explicitly listed as
an unresolved, platform-wide gap. `PolicyConfig.wiki_policies.proposal.
retention` (`conversation_policy_catalog.yaml`, default `P30D`, an ISO-8601
duration parsed the same way as every other retention value in that file) is
the platform-wide answer for wiki proposals specifically — not a team
override, since nothing asked for one.

**The lifecycle sweep reuses the existing Temporal `LifecycleManagerWorkflow`
tick — no second scheduled entrypoint.** The same 10-minute `Schedule`, the
same worker, the same `POST /lifecycle/run-once` manual trigger now also list
`status="proposed"` rows older than the retention cutoff
(`scheduler/wiki_proposal_actions.py`) and reject each with a single
conditional `UPDATE ... WHERE status = 'proposed'` — the identical
compare-and-swap idiom `store.py` already uses for every other proposal
transition. `LifecycleManagerResult.wiki_proposals` carries that sweep's own
`scanned`/`rejected`/`dry_run_actions` counts alongside the conversation
sweep's.

**Correction (2026-09-08).** The paragraph above originally claimed the
initial `WHERE status == "proposed"` lookup closed the retry hole with no
change to the publish path, "proven under real concurrency" by an
`asyncio.gather` test. Both halves were wrong: `publish_proposal` read the row
once at the top of its transaction and then wrote `status="published"` back
from that in-memory copy, unconditionally, as an ORM attribute flush keyed
only on `revision_id` — a reject that committed after the read but before
that write was silently overwritten. `asyncio.gather` never forced that
window open (nothing pins two independent DB round trips' relative order), so
the test could pass without the interleaving ever occurring. Fixed by making
that final write a second CAS — `WHERE ... AND status = 'proposed'` — in the
same transaction as every other write `publish_proposal` makes; a miss raises
`WikiProposalNoLongerPendingError`, mapped to the same 404 as the top-of-
function lookup, and rolls back the page create/update alongside it, so a
losing publish leaves no partial write. Proven with a genuinely forced
interleaving (an `AsyncSession.execute` pause keyed to the exact statement,
not `asyncio.gather` timing) in `test_team_wiki_store_postgres_integration.py`:
`test_publish_loses_to_a_reject_committed_between_its_read_and_write` (edit),
`test_publish_loses_to_a_reject_of_a_new_page_proposal_creates_no_page`
(new page), and `test_publish_loses_to_a_session_erasure_reject_committed_mid_transaction`
(session erasure). The same guard is what makes the sweep safe against a
concurrent approval in the other direction too: whichever of {reject,
publish} commits first is the only one that changes anything.

**Erasing a session rejects its still-pending proposals immediately**, rather
than waiting out the retention window: `team_wiki_revisions.session_id`
already existed but `ConversationErasureService.erase_session` never looked
at it. A proposal from a conversation that no longer exists is unambiguously
abandoned. This runs as its own isolated store step (`wiki_proposals` in the
erase receipt), matching every other store there — a failure there alone
makes the whole erase retryable, never destructive.

**Not built here, and why.** A synchronous decline→reject callback would mean
teaching `HitlSpec` an on-cancel hook that reaches back into a specific
capability's owning service — a new cross-stack contract surface belonging to
the HITL epic (#1080), not this fix. An editor review inbox for pending
proposals (RFC §12.2) stays deferred; retention does not need it, and building
one only to solve retention would be solving a smaller problem with a bigger
one.

## 50. Contract Notes — the admin tier splits into delegated roles (2026-09-09, issue #2592)

**Extends §43.** `organization:fred` gains three role relations, each
`[user] or platform_admin` in `schema.fga` — `team_manager`,
`feature_manager`, `prompt_editor` — plus two computed relations carved out
of the `can_manage_platform` catch-all: `can_manage_capabilities` and
`can_edit_platform_prompt`. `can_create_team` now reads `platform_admin or
team_manager` and `can_list_all_teams` `platform_admin or team_manager or
feature_manager` (see the capability paragraph below); `can_delete_team` and
`can_rescue_team_admin` stay `platform_admin`-only, so registry governance is
deliberately split from team creation. `can_manage_platform` is unchanged and
still gates import/export, tasks and platform reset.

**Re-gated endpoints — feature governance.** The whole `/admin/features`
surface moves off `can_manage_platform` onto `can_manage_capabilities`: the
seven `/control-plane/v1/admin/capabilities*` routes (aggregate list,
revoke-impact preview, per-team enable/disable, default-on, personal-scope,
model reasoning) and the `GET`/`PUT`/`DELETE`
`/control-plane/v1/admin/platform/model-bindings` trio, which is a panel of
that same page. Paths are unchanged. `capability#can_manage` — the per-object
gate every enablement mutation resolves through — is redefined from
`platform_admin from organization` to `can_manage_capabilities from
organization`; without that, a `feature_manager` would pass the org gate and
fail the object gate on the very next line. `can_list_all_teams` joins the
role for the same reason: the per-team enablement matrix is a team picker, and
it renders empty without the roster. That listing is names and ids only and
carries no authority over any team's data. Nothing else moves — import/export,
platform reset, tasks, platform stats and corpus audit stay on
`can_manage_platform`, which is what makes this delegation safe.

**New endpoint — `GET /teams/candidate-admins?query=<string>`** →
`list[UserSummary]`, gated on `can_create_team`. `POST /teams` requires at
least one `initial_team_admin_ids` entry, and the only org-wide directory
(`GET /users`) is gated on `can_administer_users`, which stays
`platform_admin`-only — so `/admin/teams` rendered for a `team_manager` with a
permanently empty admin picker and a submit button that could never enable.
The search is bounded exactly like `GET /teams/{team_id}/candidate-members`
(§ above): minimum 2 non-whitespace characters, at most 20 Keycloak matches,
never a full directory listing. Registered before `/teams/{team_id}` so the
literal segment is not captured as a team id.

**Re-gated endpoints — platform prompt.** All three routes of the
platform-prompt surface move off `can_manage_platform` onto
`can_edit_platform_prompt`: `GET` and `PUT
/control-plane/v1/admin/platform/prompt`, and the read-only `GET
/control-plane/v1/admin/platform/instructions`. The read moves with the write
deliberately — an editor who cannot see what they are overwriting is useless,
and the instructions pane is the reference they write against; neither was
readable below the admin tier before, so this widens rather than narrows. The
runtime path is untouched: `resolve_platform_prompt_text` is a server-side
platform assertion resolved per turn and has never been gated on the caller.
Team-scoped prompts (`/teams/{id}/prompts`) are unaffected — they are governed
by team relations, and `prompt_editor` grants nothing there.

`PlatformRoleRelation` grows the three values, so §43's three routes accept
them with no other change. The service layer iterates the enum instead of
naming roles, and the root guards remain scoped to `platform_admin` alone:
**any `platform_admin` grants and revokes the three new roles**, exactly as
for `platform_observer`. §43's direct-tuple rule now carries five relations'
worth of weight — every non-admin role unions in `platform_admin`, so an
expanded read would list every admin as a holder of all five and offer four
revokes that delete nothing.

**Breaking (frontend bootstrap):** `PermissionSummary` replaces
`is_platform_admin` / `is_platform_observer` with
`platform_roles: PlatformRoleRelation[]` — the roles the caller
*effectively* holds, union-resolved, so a `platform_admin` carries all five.
That is deliberately unlike `GET /users/platform-roles`, which reports
directly-granted tuples only because those are what a revoke can delete.
Five parallel `is_*` booleans over one closed enum is a list, and each future
role would otherwise have cost a field, a codegen run and an edit in every
consumer. The generated client, the frontend capability hook and the CLI
bootstrap summary move with it.

**Frontend surface renamed:** the admin page `feature_manager` owns moves from
`/admin/capabilities` to `/admin/features` (`FeaturesPage`, i18n key
`rework.sidebar.admin.menu.features`). "Capabilities" already means the ReBAC
computed relations and the agent-capability packages; the page governs
platform features — capabilities, agent templates and models — so it takes the
name of the role that governs it. The backend endpoints keep their
`/admin/capabilities` prefix: there the word is accurate.
