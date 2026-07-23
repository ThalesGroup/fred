# Control Plane Product Contract — Phase 3a

> ✅ **`prepare-execution` issues no `ExecutionGrant` (RUNTIME-07 rev. 2, 2026-06-28 — RFC
> decision D5).** The control-plane is the **catalogue + display-filtering + resolution**
> authority: `prepare-execution` returns the runtime URLs and the session's resolved context,
> never an authorization token. Authorization happens at the agent pod (Keycloak JWT +
> pod-side OpenFGA on `runtime_context.team_id`). Any `ExecutionGrant` / grant-issuance /
> `.well-known/grant-jwks` mention left below is a historical record, marked as such. See
> [`EXECUTION-GRANT-SECURITY-HARDENING-RFC.md`](../rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md)
> (§13/D5) and [`RUNTIME-EXECUTION-CONTRACT.md`](./RUNTIME-EXECUTION-CONTRACT.md) §2.2.

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
`docs/swift/rfc/FRONTEND-AUTH-CONFIG-ENDPOINT-RFC.md §7` and
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
mocked identity would make the JWT proof meaningless. See
`docs/swift/rfc/FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` Part 8 (§40-42) for
the full design rationale (same shape as Kubernetes' cluster-admin bootstrap,
ArgoCD's `argocd-initial-admin-secret`, Rancher's bootstrap password, and
Keycloak's own `KC_BOOTSTRAP_ADMIN_*` variables) — replaces the config-seeded
`platform_admin_subjects`/`platform_observer_subjects` path entirely (removed
from `security.rebac` config, AUTHZ-07 Step 6). No path grants a platform
role from deployment config anymore; the only other path is the declarative
platform import (`PLATFORM-IMPORT-RFC.md` §10).
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
- `mcp_servers: list[ManagedMcpServerRef]` — MCP tool references advertised by the template; `display_name` enriched from the pod's MCP catalog; `config_fields` for per-instance tool configuration declared by the tool catalog

The control plane is a **pure proxy** for these values — it does not interpret them. The runtime pod is the author; the control plane aggregates and forwards.

**`ManagedAgentInstanceSummary`** — a team-scoped enrolled instance (DB-backed):

- `agent_instance_id` — primary identifier
- `team_id`, `template_id`
- `display_name`, `description`, `status`
- ~~`effective_chat_options: EffectiveChatOptions`~~ — **REMOVED 2026-07-11 (CAPAB-01 #1976).** `EffectiveChatOptions` is retired; chat controls are a session-prep projection shipped on `ExecutionPreparation.chat_controls`, not a listing-surface field. The composer fetches them via an eager prepare-execution at chat open. See RFC AGENT-CAPABILITY-RFC §3.3/§3.7.
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

**`session_purge_queue` — deferred-delete scheduler (CTRLP-12 A5/A6):** Originally a legacy concept inherited from `agentic-backend`, not connected to the `session_history` table written by `fred-runtime`. CTRLP-12 A5 repurposes it as the *scheduler* for governed deferred deletes: the delete button hides the conversation (`session_metadata.deleted_at`) and enqueues a `USER_DELETED` entry due at `now + window`. The queue is only a timer — the retention *mechanism* is `ConversationErasureService.erase_session` (which fans out over the runtime purge endpoints above plus KPI anonymise, attachments, and metadata). The queue consumer must invoke `erase_session` at expiry (A6, pending). **Until A6 lands the consumer performs a metadata-only delete, so a configured delete-grace window does NOT yet fully erase at expiry** (see `CTRLP-12-QUALITY-REVIEW.md` blocker 2). Do not treat the queue as the retention mechanism until the consumer is wired to `erase_session`.

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

- `PromptSummary`
- `PromptDetail`
- `CreatePromptRequest`
- `UpdatePromptRequest`

Rules:

- prompt ownership is team-scoped
- the reserved system team `personal` is the personal prompt library; do not
  introduce a parallel user-scoped prompt API
- prompt `text` uses the same template-validation contract as agent
  `prompts.*` tuning values
- importing or saving a prompt from the agent form is a control-plane workflow,
  but the managed agent instance stores only copied `prompts.*` text, never a
  live prompt reference

The global prompt marketplace is a follow-up control-plane surface:

- publishing must create a separate published snapshot, not mutate team prompt
  ownership in place
- agent instances and team prompt records must not point at mutable global
  marketplace rows

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
    otherwise hidden from the create-agent catalog (see `AGENT-VISIBILITY-RFC.md`)

> **2026-06-25 (VALID-02 / AGENT-VISIBILITY-RFC):** internal (`public=False`) agents are
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
> selection. See `AGENT-CAPABILITY-RFC.md` §8.1's dated fix note for the full
> mechanism, including the required one-off backfill for instances persisted
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
- global prompt marketplace publication / moderation surface
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

Two new tables in `fred_swift` (Alembic-managed, both mandatory):

- `task_run` — current-state summary (one row per task, updated in place)
- `task_event_log` — append-only event journal (one row per `TaskEvent`, source of truth for SSE replay)

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

**2026-07-12 — Decision (RFC `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` Part 7,
§33-39):** a team member may now hold `team_admin`, `team_editor`, and
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
backend/frontend design: `PLATFORM-IMPORT-RFC.md` §11,
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

## 17. Contract Notes — CAPAB-01 (July 2026)

### Admin capability-enablement routes

**2026-07-11 — Routes fixed (CAPAB-01 / RFC `AGENT-CAPABILITY-RFC.md` §8.5;
backend #1980, admin dashboard #1981).** The Tier 3 admin surface over the
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
| `GET /admin/capabilities` | — | `CapabilityEnablementList` | Aggregated pod catalog with, per capability: `id`, `name` (i18n key), `version`, `icon`, `team_scope` (`default_on` \| `admin_gated`), `default_on`, `enabled_team_ids`, `team_settings_fields` (the enable-with-settings form specs). |
| `PUT /admin/capabilities/{capability_id}/teams/{team_id}` | `EnableTeamCapabilityRequest` (`settings`) | `TeamCapabilityEnablementResult` | Enable-with-settings: validates `settings` against `team_settings_fields`, writes the settings row then the `enabled` tuple. |
| `DELETE /admin/capabilities/{capability_id}/teams/{team_id}` | — | `TeamCapabilityEnablementResult` (`suspended_instances`) | Revoke: deletes the `enabled` tuple (writes a `disabled` opt-out for a default-on cap), reconciles dependent instances → suspension. |
| `PUT /admin/capabilities/{capability_id}/default-on` | `SetCapabilityDefaultOnRequest` (`default_on`) | `CapabilityDefaultOnResult` (`suspended_instances`) | Toggle the platform-wide `default_on` marker; turning it off revokes inherited access team-by-team and may suspend instances. |

`suspended_instances` on the two revoking mutations is the **delta** the action
caused (#1975 reconciliation), surfaced by the #1981 dashboard as post-action
feedback. Frontend consumes the generated hooks via the friendly aliases
`useAdminCapabilitiesQuery` / `useEnableTeamCapabilityMutation` /
`useDisableTeamCapabilityMutation` / `useSetCapabilityDefaultOnMutation` in
`controlPlaneApiEnhancements.ts`; the dashboard lives at `/admin/capabilities`.

**2026-07-16 — personal-space class scope (CAPAB-01 / #1961, RFC
`AGENT-CAPABILITY-RFC.md` §8.4 amendment).** The personal-space capability class
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

**2026-07-17 — agent templates join this surface (CAPAB-01, `AGENT-CAPABILITY-RFC.md`
§8.6 / `AGENT-VISIBILITY-RFC.md` §7.5).** `CapabilityEnablementItem` and
`CapabilityCatalogEntry` gained `kind: "tool" | "agent"` (defaults `"tool"`,
so existing rows are unchanged). `GET /admin/capabilities` now also lists a
`kind="agent"` row per registered agent template (control-plane-side
projection — never a runtime pod change), enabled/disabled through the exact
same `PUT`/`DELETE .../teams/{team_id}` and gated the exact same way. The
frontend (`CapabilitiesPage.tsx`) filters the one dataset by `kind` (a
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
#2004, CTRLP-14; design in `AGENT-CAPABILITY-RFC.md` §8.6).**
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

## 18. Contract Notes — team-scoped candidate-member search (2026-07-20)

**New endpoint:** `GET /teams/{team_id}/candidate-members?query=<string>` →
`list[UserSummary]`. Gated on `can_administer_members` for `team_id` (owner-only,
no platform escalation — `FRED-AUTHORIZATION-TARGET-MODEL-RFC.md` §24.7/§24.9).
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
team space returns the team's prompts + platform defaults only; the personal
space returns the caller's prompts (scope `personal`) + defaults. Response
shape unchanged. Already-attached personal prompts keep resolving at
prepare-execution (see `design/PROMPTS.md` §5/§6).

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

An asset-bearing capability (first: `ppt_filler`, AGENT-CAPABILITY-RFC §3.4)
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
