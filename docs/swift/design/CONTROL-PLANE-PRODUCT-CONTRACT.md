# Control Plane Product Contract — Phase 3a

> ✅ **`prepare-execution` issues no `ExecutionGrant` (RUNTIME-07 rev. 2, 2026-06-28 — RFC
> decision D5).** The control-plane is the **catalogue + display-filtering + resolution**
> authority: `prepare-execution` returns the runtime URLs and the session's resolved context,
> never an authorization token. Authorization happens at the agent pod (Keycloak JWT +
> pod-side OpenFGA on `runtime_context.team_id`). Any `ExecutionGrant` / grant-issuance /
> `.well-known/grant-jwks` mention left below is a historical record, marked as such. See
> [`EXECUTION-GRANT-SECURITY-HARDENING-RFC.md`](../rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md)
> (§13/D5) and [`RUNTIME-EXECUTION-CONTRACT.md`](./RUNTIME-EXECUTION-CONTRACT.md) §2.2.

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

`FrontendBootstrap` must not carry deployment branding labels. Static branding
and frontend display strings (`siteDisplayName`, `siteTitle`, `siteSubtitle`,
agent nicknames, logos, favicons, banners, support links) are owned by the
frontend static configuration surface, `config.json` `properties`, so a
deployment has one branding source of truth. The former control-plane
`ui_settings` bootstrap block was removed; do not reintroduce a parallel
branding channel in control-plane.

Permissions are exposed via:

- `PermissionSummary`
  - `items`
  - flattened booleans such as `can_manage_team_agents`
  - no raw RBAC/REBAC graph internals

Permission booleans must reflect the product actor model defined in
`docs/swift/platform/REBAC.md §Product authorization model`. In particular:
the owner/manager split is orthogonal — a flag that is true for owner must not
imply it is also true for manager, and vice versa.

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
- `effective_chat_options: EffectiveChatOptions` — **added 2026-05-24 (CHAT-07)** — computed read-only field; same resolution as `ExecutionPreparation.effective_chat_options` but available at mount without a `prepareExecution` round-trip. Never stored; recomputed on every read from active MCP server config.
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
- Graph agents read prompt and setting values through `context.tuning_values`
- tool-owned chat options are resolved from `mcp_config_values` into a typed
  `effective_chat_options` surface exposed by `ExecutionPreparation`

This contract is intentionally narrow:

- prompt fields describe instructions
- settings fields describe agent behavior
- chat-option fields that remain agent-authored describe UI affordances
- tool-owned UI affordances live in `mcp_config_values` and resolve into
  `effective_chat_options`
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

**`session_purge_queue` warning:** The `session_purge_queue` table in `control-plane-backend` is a legacy concept inherited from `agentic-backend`. It is not connected to the `session_history` table written by `fred-runtime`. It must not be used as the retention mechanism for runtime sessions. When a proper retention policy is implemented, it must call the runtime purge endpoints above, not the legacy queue.

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
       Auth:     task creator or platform owner

POST   /api/v1/tasks/{task_id}/cancel
       Response: 202  (idempotent — no-op if task is already terminal)
                 404  if task_id not found
       409  if the task kind does not support cancellation
       Auth:     task creator or platform owner
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
