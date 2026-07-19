# Runtime Execution Contract — Phase 1 + Phase 2 Continuity

> ✅ **Security model — RUNTIME-07 rev. 2 (2026-06-28, RFC decision D5).** There is **no
> `ExecutionGrant`**: the control-plane issues no signed (or unsigned) authorization token.
> Managed execution is **authenticated** by the caller's **Keycloak JWT** and **authorized by
> the agent pod itself**, per request, via an **OpenFGA ReBAC check** on the team carried in
> `runtime_context.team_id`. The control-plane's `prepare-execution` resolves only *where* the
> agent runs (URLs) and the session's context — never a capability. §0–§3 describe this model;
> the dated entries in §8 record the abandoned signed-grant approach as history. See
> [`EXECUTION-GRANT-SECURITY-HARDENING-RFC.md`](../rfc/EXECUTION-GRANT-SECURITY-HARDENING-RFC.md)
> (§13/D5) and the narrative in [`ARCHITECTURAL-SECURITY-REPORT.md`](./ARCHITECTURAL-SECURITY-REPORT.md).

> ✅ **Service-agent execution — 2026-07-01 (EVAL-03 / RFC EVAL-AUTH, Solution A).**
> `_authorize_execution_or_raise` now recognizes a **service identity** (a caller holding
> the `service_agent` app role — the evaluation worker) for managed execution **scoped to
> the request `team_id`**, **without** consulting OpenFGA and **without** any stored tuple.
> Legitimacy is anchored upstream at campaign creation. It stays team-scoped and
> fail-closed: a missing `team_id` still returns 403; the decision is audited as
> `service_agent_authorized`. Regular users are unchanged (per-request OpenFGA `can_read`).
> Read-only by design — the worker never mutates a team.

> ✅ **Chat-context prompt injection — 2026-07-06 (PROMPT-08 / issue #1915).** The
> runtime now folds `runtime_context.context_prompt_text` into the final system
> prompt. A single shared composer,
> `fred_runtime.react.react_prompting.compose_system_prompt`, assembles the ReAct
> and Deep system prompts (template → tools → guardrails → global-base output
> contract → runtime-specific → **context-prompt** → attachments); the per-prompt
> suffix `build_context_prompt_suffix` renders through the safe token renderer.
> Wire contract is unchanged — the `context_prompt_text` field already existed;
> this records that the field is now applied instead of dropped after the binding.
> Convergence side effect: the Deep runtime previously never appended the
> attachment suffix and now does. See [`PROMPTS.md`](./PROMPTS.md) §5.

> ✅ **Personal-space regression fix — 2026-07-13 (AUTHZ-05 item 8b watch item,
> issue #1912).** `_authorize_execution_or_raise` now authorizes a **personal
> space** (`personal-<uid>`) as intrinsic ownership by exact identity comparison
> against `fred_core.common.personal_team_id(authenticated_user.uid)` — **never**
> via OpenFGA, which never held a tuple for it. This restores what the removed
> `groups_list_to_relations`/`_user_contextual_relations` contextual relation used
> to grant, without reintroducing any Keycloak-groups dependency. Any other
> `personal-*` id, or the bare `"personal"` alias, is explicitly denied (403),
> never routed to OpenFGA. Collaborative teams are unchanged: still OpenFGA
> `CAN_READ`, still fail-closed. See §2.2.

This document is the authoritative design reference for the Phase 1 runtime
execution contract. It describes what was frozen, where it lives, what the
architectural boundaries are, and what is explicitly deferred.

Phase 2 status is now reflected here as well, and this document also captures
the backend completeness gate that must be satisfied before frontend SSE
migration:

- `fred-runtime` generates `openapi.json`
- `frontend` generates `src/slices/runtime/runtimeOpenApi.ts`
- the important component schemas are OpenAPI-visible and must stay strongly typed
- Phase 3a control-plane read-only product APIs now exist and are code-generated
- Phase 3b backend completeness must be validated before Phase 4 frontend work
- this document plus `BACKLOG.md` are the continuation pack; do not invent a
  parallel migration note elsewhere

**Read this before touching:**

- `libs/fred-sdk/fred_sdk/contracts/execution.py`
- `libs/fred-sdk/fred_sdk/contracts/openai_compat.py`
- `libs/fred-runtime/fred_runtime/app/agent_app.py`
- `libs/fred-runtime/fred_runtime/client.py`
- `BACKLOG.md`

---

## 0. The Flow in 30 Seconds

This is what one agent turn looks like over HTTP SSE.

```
Browser / CLI                control-plane              fred-runtime pod
     │                            │                           │
     │── POST /prepare-execution ─►                           │
     │◄── ExecutionPreparation ───                            │
     │    (execute_stream_url,                                │
     │     team_id, agent_instance_id,                        │
     │     context_prompt_text)        ← URLs + context, no grant
     │                                                        │
     │── POST {execute_stream_url} ──────────────────────────►│
     │   Authorization: Bearer <user JWT>                     │
     │   Body: {                                              │
     │     input: "Transfer 500€ to Alice",                   │
     │     session_id: "uuid",           ← conversation key   │
     │     agent_instance_id: "inst-1",  ← which agent        │
     │     runtime_context: { team_id }  ← pod authorizes here│
     │   }                                                    │
     │                              pod: JWT identity +        │
     │                              OpenFGA CAN_READ(team)     │
     │◄── data: {"kind":"status","status":"starting"} ────────│
     │◄── data: {"kind":"assistant_delta","delta":"I will…"} ─│
     │◄── data: {"kind":"tool_call","tool_name":"check_bal…"} ─│
     │◄── data: {"kind":"tool_result","content":"1200€"} ─────│
     │◄── data: {"kind":"final","content":"Transfer done."} ──│
     │                                              [connection closed]
```

**Two execution paths:**

| Path                      | When                             | Required fields                                  |
| ------------------------- | -------------------------------- | ------------------------------------------------ |
| **Managed** (production)  | Frontend selects a team agent    | `agent_instance_id` + `runtime_context.team_id`  |
| **Direct** (dev/CLI only) | Developer targets a pod directly | `agent_id` (forbidden under the `c3` profile)    |

The managed path is the only one authorized for production frontend calls. The
agent pod authenticates the Keycloak JWT and authorizes the request itself with a
pod-side OpenFGA check on `runtime_context.team_id`. `control-plane` resolves which
runtime pod serves which agent instance (via `prepare-execution`) but issues no
capability and is never on the execution path.

> **2026-06-25 (VALID-02 / AGENT-VISIBILITY-RFC):** the **Direct** path now refuses
> agents with `AgentDefinition.public=False`: `_resolve_agent_instance` returns 404 for a
> non-public `agent_id` (treated as unknown). Internal agents may therefore be executed
> **only** through the Managed path, whose enrollment is admin-gated in control-plane.
> Sub-agents invoked in-process via `context.invoke_agent()` are unaffected.
> Related: `GET /agents/templates` gained an optional `include_non_public` (default false)
> query param so control-plane can enumerate internal templates for admins.

**Standalone / no-security mode (laptop, airgapped, developer workstation):**

When `KEYCLOAK_ENABLED=false` the pod runs without authentication. A mock user
(`uid="admin"`) is injected automatically. In this mode:

- `team_id` defaults to `"personal"` when the caller omits it — no explicit
  field is required in the request body.
- This default is applied by `_stream()` before building `PortableContext`,
  `RuntimeContext`, and the KPI/history records. Every subsystem sees the same
  resolved value.
- The CLI (`fred-agents-cli`) also defaults its active team to `"personal"` when
  no Keycloak configuration is present, and prints it in the startup banner:
  `[chat] team : personal`
- Checkpoints, history rows, and KPI labels all carry `team_id="personal"` —
  making it safe to compare metrics across restarts without null gaps.

**Session continuity:**

`session_id` is the single stable key for a conversation. Keep it identical
across all turns, including HITL resumes. The runtime uses it to restore the
agent's graph state (checkpoints) between turns.

**Error during execution:**

If the agent pipeline crashes, the runtime emits a typed error event before
closing the stream:

```
data: {"kind":"execution_error","message":"<reason>"}
[connection closed]
```

No `final` will follow. Treat `execution_error` as a terminal event.

---

## 0.1 The Managed Path Step by Step

The "managed path" is what happens before and during a production frontend call.
It involves three participants: the browser, `control-plane-backend`, and a
`fred-runtime` pod.

```
Browser                    control-plane              fred-runtime pod
  │                             │                           │
  │  1. Bootstrap               │                           │
  │── GET /frontend/bootstrap ─►│                           │
  │◄── { user, team, perms } ───│                           │
  │                             │                           │
  │  2. Pick an agent           │                           │
  │── GET /teams/{id}/agent-instances ─►                    │
  │◄── [ { agent_instance_id, name, … } ] ─────────────────│
  │                             │                           │
  │  3. Prepare execution       │                           │
  │── POST /teams/{id}/agent-instances/{inst}/prepare-execution ─►
  │                             │ validates team membership  │
  │                             │ resolves runtime binding   │
  │                             │ resolves session context   │
  │◄── ExecutionPreparation ────│                           │
  │    {                        │                           │
  │      execute_stream_url,    │  ← ingress-relative URL   │
  │      execute_url,           │                           │
  │      messages_url_template, │                           │
  │      agent_instance_id,     │                           │
  │      team_id,               │                           │
  │      context_prompt_text    │  ← no grant, no expiry    │
  │    }                        │                           │
  │                             │                           │
  │  4. Execute directly        │                           │
  │── POST {execute_stream_url} ──────────────────────────►│
  │   Authorization: Bearer <user JWT>                      │
  │   Body: { input, session_id,                            │
  │           agent_instance_id,                            │
  │           runtime_context: { team_id } }                │
  │                             │  pod authorizes per request:│
  │                             │  • validate Keycloak JWT    │
  │                             │    (strict iss/aud under c3)│
  │                             │  • session ownership        │
  │                             │  • OpenFGA CAN_READ(team)   │
  │                             │  • resolve instance (ReBAC) │
  │◄── SSE stream ─────────────────────────────────────────│
  │   (see section 0 for event sequence)                    │
```

**Why control-plane is in the middle for step 3 but not step 4:**

Control-plane is the only component that knows which runtime pod serves which
agent instance. But it must not proxy the SSE stream (latency, complexity).
`prepare-execution` resolves the binding once and returns a safe ingress-relative
URL plus the session's resolved context — **no capability token**. The browser
then calls the runtime pod directly with the user's own Keycloak JWT; the pod
authenticates that token and authorizes the request itself, so the browser never
learns any Kubernetes internal topology and the control-plane never mints a
credential the pod must trust.

**How the pod authorizes one request** (`_authorize_and_resolve` in `agent_app.py`):

1. **Identity from the token, never the body** — `user_id` is stamped from the
   validated JWT; any body-supplied `access_token` / `refresh_token` is neutralized.
2. **Session ownership** — an existing `session_id` must belong to the caller
   (conversations are private per owner; blocks intra-team session hijacking).
3. **OpenFGA authorization** — the caller must hold `CAN_READ` on
   `runtime_context.team_id` (the canonical team id, e.g. `personal-<uid>` for a
   personal space). Denial fails closed (403). Under the `c3` profile a direct
   `agent_id` is forbidden entirely.
4. **Team-scoped resolution** — the instance template + tuning is resolved from the
   control-plane through a ReBAC-gated, team-scoped callback, then the resolved
   owner team is cross-checked against the caller's claimed team.

**HITL resume** follows the exact same path with `execution_action: "resume"` and
`resume_payload` in the request body instead of a new user message.

---

## 1. Goal

Establish `fred-sdk` as the single authoritative source of truth for the
**secure, team-scoped execution contract** between the frontend and agentic
runtime pods.

Every agent execution is:

- attributable to `user_id + team_id + agent_instance_id`
- authorized by a **pod-side OpenFGA check** (identity proven by the Keycloak JWT)
- scoped to a `session_id` for multi-turn continuity
- optionally resumable from a `checkpoint_id`
- observable through enriched trace/KPI/metrics metadata that preserves the
  same execution identity end-to-end

---

## 2. Frozen Contract — `fred-sdk/contracts/execution.py`

### 2.1 Identity models

| Model             | Fields                                                                    | Purpose                             |
| ----------------- | ------------------------------------------------------------------------- | ----------------------------------- |
| `ActorContext`    | `user_id`, `principal`                                                    | User identity for audit/diagnostics |
| `TeamContext`     | `team_id`, `team_type`                                                    | Team scope; always mandatory        |
| `ExecutionTarget` | `agent_instance_id`, `underlying_agent_ref`                               | Managed instance reference          |
| `TraceContext`    | `request_id`, `trace_id`, `correlation_id`, `session_id`, `checkpoint_id` | Observability across services       |

### 2.2 Authorization — pod-side Keycloak JWT + OpenFGA

There is **no `ExecutionGrant` type** and no control-plane-issued capability. The
agent pod is the execution authority (RUNTIME-07 rev. 2):

- **Authentication** — every request carries the caller's Keycloak JWT in the
  `Authorization: Bearer` header. The pod is an OAuth2 resource server
  (`fred_core.security.oidc`). Under the `c3` profile it validates issuer and
  audience strictly (`verify_aud=True`), and each pod validates `aud == its own
  client_id` (per-agent audience — anti-confused-deputy, decision D5c).
- **Authorization** — for a **collaborative** `runtime_context.team_id` (anything
  not a personal space), the pod runs a per-request OpenFGA check that the caller
  holds `CAN_READ` on that team (the same relation the control-plane required
  before it would mint a grant). This is the model already homologated on
  `main`'s agentic-backend, re-instantiated per pod. A **personal space**
  (`personal-<uid>`) is never checked against OpenFGA — see below.
- **Identity integrity** — `user_id` is taken from the validated token, never the
  request body; body-supplied tokens are neutralized.

The team in `runtime_context.team_id` is caller-supplied but safe: OpenFGA only
authorizes teams the user actually has a relation to. A missing team on a managed
request fails closed (403). The `ExecutionGrantAction` enum (`execute` / `resume`)
survives as the `execution_action` field; the `ExecutionGrant` envelope does not.

**Personal spaces are intrinsic ownership, not an OpenFGA relation (AUTHZ-05 item
8b, 2026-07-13).** A personal space is a synthetic, system-recognized team
(`fred_core.common.personal_team_id(uid)`) with no `team_metadata` row and no
stored OpenFGA tuple of any kind — it is not a collaborative team and was never
meant to route through `CAN_READ`. `_authorize_execution_or_raise` therefore
special-cases it, before the OpenFGA branch, purely by identity comparison:

- `team_id == personal_team_id(authenticated_user.uid)` (the caller's own
  canonical personal space) → authorized as intrinsic ownership, audited
  `personal_space_owner_authorized`, **no OpenFGA call**.
- any other `personal-*` id (another user's personal space) → denied outright,
  audited `personal_space_denied`, HTTP 403. This is a hard identity check, not
  an OpenFGA lookup — a stray or residual OpenFGA tuple naming that id can never
  grant access here.
- the bare `"personal"` alias → also denied under this same rule once ReBAC is
  active, rather than resolved as if it meant the caller's own space; it stays a
  dev/CLI-only shorthand (see `fred_runtime/cli/entrypoint.py`).
- any non-personal `team_id` (a real collaborative team) → unchanged, always the
  OpenFGA `CAN_READ` check described above.
- `service_agent` callers are unaffected: their team-scoped, OpenFGA-free
  authorization (§ below, RFC EVAL-AUTH Solution A) is checked first and returns
  before the personal-space branch is reached.
- `platform_admin`/`platform_observer` confer no implicit access here, personal
  or collaborative — this carve-out is identity-only (JWT subject vs. the
  requested personal id), never role-based.

No Keycloak group, claim, or role feeds this decision anywhere — the removal of
`groups_list_to_relations`/`_user_contextual_relations` (item 8b) is unaffected;
this carve-out replaces the contextual (never-persisted) `team_member` relation
that helper used to grant for personal spaces, with an explicit, narrower check
local to the runtime.

**Architectural constraint (unchanged):**

> Nothing on the request may carry infrastructure secrets, database credentials,
> or internal service connection strings. The pod resolves configuration (instance
> template, tuning, context prompt) from the control-plane through a ReBAC-gated,
> team-scoped callback — never a secret or a capability.

### 2.3 Execution request — `RuntimeExecuteRequest`

The frozen frontend-facing request body for `/agents/execute` and
`/agents/execute/stream`.

Execution paths:

1. **Managed** (preferred for frontend): set `agent_instance_id`; carry the team in
   `runtime_context.team_id`. The pod authorizes the caller on that team.
2. **Direct template** (dev/internal only): set `agent_id`. **Forbidden under the
   `c3` profile**; identity-only in dev / non-c3.

Session/checkpoint semantics:

- `session_id` — primary continuity key; keep stable across turns and HITL resumes
- `checkpoint_id` — optional; enables precise resume from a graph snapshot
- `resume_payload` — HITL answer data; when set, `input` is ignored and the
  graph resumes from the checkpointed state

Compatibility helpers:

- `effective_user_id()` — `runtime_context.user_id` (the authenticated caller; the
  pod re-stamps this from the JWT, so the body value is never authoritative)
- `effective_team_id()` — `runtime_context.team_id` (the team the pod authorizes against)
- `effective_session_id()` — top-level `session_id`, else `runtime_context.session_id`
- `to_legacy_context()` — bridges to internal plumbing; not part of the frozen contract

Convergence rule for future work:

- New execution features should prefer first-class typed fields on the public
  contract and typed runtime plumbing behind it.
- Do not deepen transitional compatibility bridges (`runtime_context`,
  `to_legacy_context()`, private mirror request models) when the same change can
  instead retire or shrink them.
- In particular, do not add a second special-purpose execution API for
  agent-to-agent calls if the existing runtime execute transport can carry the
  needed typed fields.

### 2.4 Pre-execution authorization gate — `_authorize_and_resolve`

There is no `validate_execution_grant` helper. Every execute / execute-stream /
evaluate path (and HITL resume, which is a field on those endpoints) funnels
through `_authorize_and_resolve` in `agent_app.py`, which performs, in order:

1. identity stamping from the validated JWT (body tokens neutralized),
2. session/checkpoint consistency + session-ownership enforcement,
3. pod-side OpenFGA authorization on `runtime_context.team_id`
   (`_authorize_execution_or_raise`),
4. team-scoped instance resolution via a ReBAC-gated control-plane callback,
5. a final cross-check of the resolved owner team against the caller's claimed team.

Any failure raises `HTTPException(403)` — the pod fails closed.

Under the `c3` security profile the pod additionally refuses to **start** unless
Keycloak user auth, M2M, and OpenFGA ReBAC are all enabled
(`fred_core.security.oidc.apply_security_profile`), so the authorization path can
never silently degrade in a classified deployment.

---

## 3. Runtime Routes — `fred-runtime/app/agent_app.py`

Both execute endpoints accept `RuntimeExecuteRequest` and run
`_authorize_and_resolve` (§2.4) before invoking the agent:

| Route                                                  | Handler                  | Contract                                                        |
| ------------------------------------------------------ | ------------------------ | --------------------------------------------------------------- |
| `POST {base_url}/agents/execute`                       | `execute()`              | `RuntimeExecuteRequest` → `RuntimeEvent \| RuntimeErrorPayload` |
| `POST {base_url}/agents/execute/stream`                | `execute_stream()`       | `RuntimeExecuteRequest` → `StreamingResponse` (SSE)             |
| `GET {base_url}/agents/sessions/{session_id}/messages` | `get_session_messages()` | `list[ChatMessage]`                                             |

> The OpenAI-compatibility router (`/v1/chat/completions`, `/v1/models`) is **off by
> default** and mounted only when `app.openai_compat: true`. It executes by direct
> `agent_id`, which is not permitted under the `c3` profile — keep it disabled in
> classified deployments. See §4.

Internal bridge: `_to_internal_request(r: RuntimeExecuteRequest)` maps to the
legacy `_AgentExecuteRequest` for backward-compatible internal plumbing. This
bridge is transitional and will be removed once all internal helpers migrate to
the typed contract fields directly.

Managed execution invariant:

- even if a runtime pod also exposes a raw `agent_id` capability for
  dev/internal compatibility, the managed team-scoped path
  (`agent_instance_id` + pod-side OpenFGA on `runtime_context.team_id`) is the
  authoritative frontend path
- the same underlying capability must still behave correctly when called
  through the team-scoped managed path
- all runtime-facing side effects of that managed path must retain team-scoped
  identity in history, checkpoints, metrics, logs, and tracing

---

## 4. OpenAI Compatibility — `fred-sdk/contracts/openai_compat.py`

The `/v1/chat/completions` endpoint is a **secondary interface** for external
tools (Open WebUI, openai-python SDK). It is not the primary frontend protocol.

Key models:

| Model                                       | Purpose                                                 |
| ------------------------------------------- | ------------------------------------------------------- |
| `OpenAIChatRequest`                         | Request body; `model` maps to `agent_id`                |
| `OpenAIModelCard` / `OpenAIModelList`       | Typed `/v1/models` response                             |
| `OpenAICompletionChunk`                     | One SSE chunk in the stream                             |
| `OpenAIDelta`                               | Content delta; `tool_calls` uses typed `OpenAIToolCall` |
| `OpenAIToolCall` / `OpenAIToolCallFunction` | Typed tool call (replaces `dict[str, Any]`)             |
| `FredChunkMetadata`                         | `fred` field extension: sources, HITL, errors, ui_parts |

Fred-specific metadata travels in the top-level `fred` field of each chunk.
Standard OpenAI clients ignore unknown top-level fields.

**Current limitations of the OpenAI compat layer vs the native protocol:**

- System messages in the request are currently ignored (agent prompt is defined by pod registration)
- Team-scoped execution (`team_id`) is passed via the `X-Fred-Team-Id` header and
  authorized by the same pod-side OpenFGA check; the `/v1` surface is **off by default**
  and forbidden under the `c3` profile (direct `agent_id`)
- HITL semantics are expressed but cannot be fully resumed via standard OpenAI clients

---

## 5. Runtime Event Models — `fred-sdk/contracts/runtime.py`

Runtime events emitted during agent execution (both native SSE and OpenAI compat):

| `RuntimeEventKind` | Meaning                                                           |
| ------------------ | ----------------------------------------------------------------- |
| `assistant_delta`  | Streaming text token from the model                               |
| `tool_call`        | Agent issued a tool call                                          |
| `tool_result`      | Tool returned a result (with optional sources/ui_parts)           |
| `thought_start`    | Opens a structured reasoning block                                |
| `thought_delta`    | Streams one text fragment into an open reasoning block             |
| `thought_end`      | Closes a structured reasoning block                               |
| `awaiting_human`   | HITL pause; carries `HumanInputRequest`                           |
| `node_error`       | Graph node failed with on_error routing                           |
| `final`            | Turn complete; carries content, sources, token_usage, ui_parts    |
| `turn_persisted`   | **Schema only — not emitted over SSE in Phase 1** (see gap below) |
| `status`           | Internal status update (dropped by OpenAI compat layer)           |

### SSE stream termination

The SSE stream emitted by `POST /agents/execute/stream` **terminates by
connection close** after the `final` event. There is no sentinel line (no
`data: [DONE]` or equivalent). `final` is always the last data line in a
successful turn.

SSE clients MUST:

- treat reception of `{"kind": "final"}` as the end-of-turn signal
- treat connection close before `final` as an error

### Error signal — `RuntimeErrorEvent`

When an unhandled exception escapes the agent execution pipeline, the runtime
emits a typed `RuntimeErrorEvent` before closing the stream:

```
data: {"kind":"execution_error","message":"<reason>","sequence":0}
```

This event is a full member of the `RuntimeEvent` union. SSE clients that
dispatch on `kind` will receive it correctly. Treat it as a terminal event:
no `final` will follow.

### `TurnPersistedEvent` — schema defined, not emitted over SSE

`TurnPersistedEvent` (`kind: "turn_persisted"`) exists in `RuntimeEventKind`
and `RuntimeEvent` but is **never emitted over the SSE stream**. History is
written fire-and-forget after the stream closes; no frame reaches the client.

`final` is the only reliable end-of-turn signal. The type is kept for future
use (e.g. a dedicated push channel).

### UI rendering parts (`UiPart`)

Carried in `tool_result` and `final` events:

| Type   | Model      | Fields                                       |
| ------ | ---------- | -------------------------------------------- |
| `link` | `LinkPart` | `href`, `title`, `kind` (download/open/cite) |
| `geo`  | `GeoPart`  | `geojson` (GeoJSON FeatureCollection)        |

**Extension rule (2026-07-10, #1977):** `link` and `geo` are the frozen BASE
members. Capability `manifest.chat_parts` extend the union at registry boot via
`fred_sdk.contracts.ui_part_union.rebuild_ui_part_union` — never by hand-editing
the union literal in `context.py`. Duplicate `type` discriminators fail pod
startup (`DuplicateChatPartKindError`). Validators must resolve the union
lazily (`current_ui_part_union()`); the frontend skips unknown kinds when
rendering and never drops them from the data (see §8.13).

**Representation rule:** agent prose, code fences, math, and Mermaid stay in
plain markdown text and are rendered by the UI. `ui_parts` is reserved for
explicit, typed widgets that the frontend can render without parsing free text.
Keep this split aligned with standard chat ecosystems such as OpenWebUI and
OpenAI-style markdown-first message bodies.

Do not introduce structured `code` or `diagram` parts unless a concrete UI
need proves markdown is insufficient and the contract is extended by RFC.

**2026-06-18 — MCP filesystem-first file exchange (AGENT-FILESYSTEM):**
`ArtifactPublisherPort` and `ResourceReaderPort` in `RuntimeServices`, and the
associated SDK types (`ArtifactPublishRequest`, `PublishedArtifact`,
`ResourceFetchRequest`, `FetchedResource`, `ArtifactScope`, `ResourceScope`) are
removed or no longer exported in the fresh Swift target. Agents and graph nodes use
the authenticated Knowledge Flow MCP filesystem through SDK `ctx.fs` / `context.fs`
helpers or direct MCP tools. Generated files are written to filesystem paths and
returned to chat as safe Fred/Knowledge Flow `LinkPart` download references. The
`LinkPart` / `ui_parts` SSE contract is unchanged; runtime history must persist those
parts so live streaming and replay match. See `docs/swift/design/FILESYSTEM.md`.

---

## 6. Checkpoint and History Semantics

`fred-runtime` is a **consumer** of persisted checkpoint state, not its
ownership authority. Control-plane owns the mapping from session to checkpoint
storage.

Runtime must validate before resuming:

- `session_id` ownership is enforced by the pod (it must belong to the authenticated caller)
- `checkpoint_id` (when provided) belongs to the authorized `session_id`
- `checkpoint_id` is in a resumable state (not already consumed)
- For HITL resume: checkpoint is in a waiting state compatible with `resume_payload`

Separation of concerns:

- **checkpoint state** = runtime-facing graph persistence (LangGraph checkpointer)
- **history state** = UI-facing / audit-facing typed interaction history

Persistence infrastructure details (connection strings, table names, credentials)
MUST remain runtime-environment concerns and MUST NOT appear in frontend-facing
contracts.

Phase 1 deferred: runtime does not yet validate that `checkpoint_id` belongs to
the authorized `session_id` — this requires control-plane integration and is
tracked as a Phase 2–3 task.

---

## 7. Kubernetes-Native Platform Boundary

Fred code MUST NOT implement the following — they are Kubernetes platform
responsibilities:

- Pod discovery or dynamic runtime pod listing
- Service-to-pod resolution (use Kubernetes Service + DNS)
- Custom in-app load balancing or traffic distribution
- Topology-aware failover logic
- Runtime endpoint topology management beyond a single configured URL

Fred code IS responsible for:

- Endpoint protection (Keycloak RBAC, OpenFGA REBAC)
- Team-scoped managed agent authorization (pod-side OpenFGA `CAN_READ` on `runtime_context.team_id`)
- Runtime execution contracts (this module)
- History and checkpoint access validation
- Managed execution semantics (`agent_instance_id` resolution via control-plane)

Platform concerns belong to:

- Kubernetes `Service` and `Ingress` / Gateway API
- Namespace isolation and DNS stable names
- Argo CD / GitOps deployment descriptors

---

## 8. SSE Contract Gaps — Fixed (April–May 2026)

These gaps were surfaced while implementing an external SSE bench client.
All four have been resolved in commit `eedbc610` (branch `agentic-pod`).

### 8.1 ✅ Unstructured error signal — fixed

**Was**: exception handler yielded `{"error": str(exc)}` with no `kind` field,
invisible to clients dispatching on `kind`.

**Fix**: `RuntimeErrorEvent(kind="execution_error", message=str)` added to
`fred-sdk` contracts and `RuntimeEvent` union. Exception handler in
`agent_app.py` now yields it. OpenAPI and `runtimeOpenApi.ts` regenerated.

### 8.2 ✅ `TurnPersistedEvent` — decision documented

**Was**: type existed in the union but was never emitted; clients waiting for
`turn_persisted` would hang.

**Decision**: `TurnPersistedEvent` is explicitly **not emitted** over the SSE
stream. History is written fire-and-forget after the stream closes. The type
is kept for future use. `final` is the only reliable end-of-turn signal.
Documented in `TurnPersistedEvent` docstring and Section 5.

### 8.3 ✅ SSE stream termination — documented

**Fix**: Route docstring for `POST /agents/execute/stream` now states that the
stream ends by connection close after `final`, with no sentinel frame, and that
`RuntimeErrorEvent` is the terminal signal on pipeline crash.

### 8.4 ✅ Direct-mode `user_id` — documented

**Fix**: `RuntimeExecuteRequest.runtime_context` description updated: in
`agent_id` direct mode, `user_id` defaults to `"unknown"` unless
`runtime_context.user_id` is explicitly provided.

### 8.5 ✅ Chat options dropped in `_iterate_runtime_event_payloads` — fixed (May 2026)

**Was**: `agent_app.py` mapped the incoming `runtime_context` dict to the internal
`RuntimeContext` dataclass but only forwarded identity and observability fields.
User-selected chat options — `selected_document_libraries_ids`, `search_policy`,
`search_rag_scope`, `include_session_scope`, `include_corpus_scope`, `deep_search`,
`selected_document_uids`, `selected_chat_context_ids`, `refresh_token`,
`access_token_expires_at` — were silently discarded, causing `ContextAwareTool`,
all KF search helpers, and the v2 adapter to always fall back to their defaults
regardless of what the user selected in the UI.

**Fix**: All chat option fields are now copied from `ctx` into the `RuntimeContext`
construction in `_iterate_runtime_event_payloads` (`agent_app.py`). The full chain
is now correct: UI picker → `RuntimeExecuteRequest.runtime_context` →
`to_legacy_context()` → `ctx` dict → `RuntimeContext` → `ContextAwareTool` injection
→ KF `VectorSearchClient.search()` params.

**2026-06-26 (VALID-02): `context_prompt_text` was the one remaining field of this
class still dropped.** The same `RuntimeContext` construction in
`_iterate_runtime_event_payloads` forwarded the chat-option group but omitted
`context_prompt_text` — so a marketplace/library prompt the user selected for a
conversation (resolved control-plane-side at prepare-execution, forwarded by the
frontend) never reached any agent. **Fix**: `context_prompt_text=ctx.get("context_prompt_text")`
added to the construction; chain is now UI picker → session `context_prompt_ids` →
`prepare_execution` resolution → `RuntimeExecuteRequest.runtime_context` → `ctx` →
`RuntimeContext.context_prompt_text` → agent via `binding.runtime_context`. Caught
live by the admin self-test harness (the deterministic agent echoed
`context_prompt: (none)`). Regression: `test_execute_forwards_context_prompt_text_to_agent_binding`.

### 8.6 ✅ `THOUGHT_*` events replace `thought_kind` on `StatusRuntimeEvent` — May 2026

**Was**: All chain-of-thought signals arrived as generic `STATUS` events. The chat
UI could not distinguish planning from tool reasoning, observation, reflection, or
synthesis — preventing per-phase visual treatments (accordion colours, icons, labels).

**Fix**: `RuntimeEventKind` now has dedicated structured thought events:

- `thought_start` opens a reasoning block with `thought_id`, `phase`, optional
  `title`, and `source` (`authored` or `model_native`).
- `thought_delta` streams text into that block.
- `thought_end` closes it with optional `conclusion` and `duration_ms`.

`ThoughtKind` remains the phase discriminator used by `ThoughtStartEvent`:

```python
ThoughtKind = Literal[
    "planning",     # deciding what to do / which tools to call
    "tool_use",     # reasoning immediately before a tool invocation
    "observation",  # interpreting a tool result
    "reflection",   # self-correction or re-planning after an observation
    "synthesis",    # assembling the final answer from collected evidence
]
```

`StatusRuntimeEvent` stays a pure operational progress signal. It does not carry
`thought_kind`.

`GraphNodeContext` exposes `thinking()` and `emit_thought()` for authored graph
agent reasoning. ReAct agents use RUNTIME-05: the runtime auto-synthesizes
tool-call thoughts and promotes provider-native thinking chunks such as Claude
`thinking` blocks or Mistral `ThinkChunk` payloads to the same `THOUGHT_*`
stream.

`ThoughtKind` is exported from `fred_sdk.__init__` so agent authors can import it
directly. The `think` scenario in `fred.github.test_assistant` exercises all five
values in sequence to enable UI design validation.

**2026-06-18 — RUNTIME-05 Layer 2b lands the model-native ReAct promotion.**
The provider-native promotion clause above was design intent until this date; it
is now implemented in the ReAct runtime (no SSE contract change — `THOUGHT_*`
shapes are frozen). A new `fred_runtime/react/react_thinking.py` holds permissive
reasoning-block predicates; `react_stream_adapter.decode_stream_chunk()` splits
each streamed `AIMessageChunk` into model-native reasoning fragments and answer
text (handling the Mistral transition frame where the closing reasoning block and
the first answer text arrive in one content list); `react_runtime.stream()` opens a
single `source="model_native"` thought, streams `THOUGHT_DELTA`s, and closes it
before the first answer delta. `stringify_langchain_content()` now drops reasoning
blocks so raw chunk JSON never leaks into the assistant transcript or final answer.
Detection is permissive across dict-shaped (`type="thinking"` / `type="reasoning"`),
top-level `reasoning_content`, and provider SDK (`ThinkChunk`) shapes because the
configured Mistral path uses the OpenAI-compatible client (`provider: openai`,
`base_url: .../v1`) rather than the native `langchain_mistralai` client.

Layer 2c (replay sanitisation) also lands on this date. Reasoning-capable models
leave provider reasoning blocks inside the checkpointed assistant message; replaying
that transcript on the next tool-loop step made Mistral reject the request with
HTTP 422 (`content … should be a valid string`; observed wire payload
`messages[i].content = ['']`) and polluted model context.
`fred_runtime.support.thinking.strip_reasoning_from_history()` now runs at the shared
tool-loop model-call boundary (`support/tool_loop.py` `reasoner`): it collapses
**assistant** (`AIMessage`) list-content to clean reasoning-free text (preserving
`tool_calls` and metadata) before `model.ainvoke`, while leaving `HumanMessage`
(multimodal/base64 image content) and `ToolMessage` untouched. This is intentionally
a *collapse* rather than the "preserve full provider message internally" behaviour in
RFC §7.3 — Mistral's OpenAI-compatible endpoint rejects the raw reasoning form, so
the reasoning survives only as the streamed `THOUGHT_*` trace. The author override
(`thought_config`, Layer 2) remains open.

### 8.7 ✅ `knowledge.search` LLM-visible field pruning — RUNTIME-06 (May 2026)

**Was**: `_invoke_knowledge_search` in `adapters.py` serialised the full
`VectorSearchHit` model to the LangChain tool return string via
`hit.model_dump(mode="json")`. This exposed URL fields (`citation_url`,
`preview_url`, `preview_at_url`, `repo_url`) and operational fields
(`embedding_model`, `vector_index`, `tag_ids`, …) to the LLM, causing it
to reproduce broken paths in its replies.

**Fix**: The LLM-visible slice is now restricted to an explicit allowlist:

```python
_LLM_FIELDS = {"uid", "title", "content", "file_name", "page", "section", "score"}
```

All URL and operational fields are excluded from the string the model sees.
The full `VectorSearchHit` continues to be forwarded to the frontend via the
`sources` tuple in `ToolInvocationResult` — the SSE contract is unchanged.

The Rico system prompt (`basic_react_rag_expert_system_prompt.md`) was also
rewritten to add explicit `[N]` citation format rules, inline placement
requirements, and a "never reproduce URLs" guardrail. See
`docs/swift/rfc/RAG-AGENT-QUALITY-RFC.md` for the full rationale.

### 8.8 ✅ `artifacts.publish_text` — `key` arg removed — FILES-04 (June 2026)

**Was**: `ArtifactPublishTextToolArgs` (`fred-sdk` builtin catalog) exposed an
optional `key` "logical storage key" field with the promise *"leave empty to let
Fred generate one."* This was a leftover from the old artifact-store model. The
unified `/fs` workspace adapter (`FredWorkspaceFs.write`) addresses files purely
by team-rooted path and has no `key` parameter, so the `WORKSPACE_WRITE` invoker
silently ignored `key` — the schema advertised collision-avoidance behaviour that
never happened.

**Fix**: `key` removed from the tool schema. `file_name` is the storage address;
writing an existing name overwrites it (now stated in the field description).
Removal is non-breaking — pydantic v2 drops the unknown field, which matches the
prior effective behaviour.

### 8.9 ⚠️ Grant audience enforcement + team binding — RUNTIME-07 Phase 1 (June 2026) — SUPERSEDED by §8.11

**Was**: the runtime validated grants structurally only — `audience` was never
checked (a grant minted for one runtime was accepted by another) and `team_id`
was never tied to the agent instance actually being executed (a grant naming one
team could drive another team's instance). See `RUNTIME-07` findings F3, F4.

**Fix** (`fred-sdk` + `fred-runtime`, non-breaking, additive):
- `ExecutionGrant.validate_for_execution` / `validate_execution_grant` gain
  `expected_audience`; the runtime passes its own configured `platform.audience`
  (new optional field on `PodPlatformConfig` / `RuntimeConfig`). Unset → check
  skipped, so existing deployments are unaffected until they opt in.
- New `_validate_grant_team_binding` in `agent_app.py` runs after control-plane
  resolution and rejects (403) any grant whose `team_id` differs from the
  resolved instance's `owner_team_id`. Applied on all three execute endpoints.

Audience comparison is trailing-slash insensitive.

### 8.10 ⚠️ Self-contained signed grant — RUNTIME-07 Phase 2 (June 2026) — SUPERSEDED by §8.11

**Was**: the grant was unsigned (forgeable, F1) and the runtime made a per-turn
control-plane callback (`GET /agent-instances/{id}/runtime`, `require_admin`) to
resolve and authorize every execution — which broke managed chat for non-admin
members and let the two platform admins reach any team's instance (F2), while
keeping per-turn control-plane load.

**Fix** (the valet-key pattern, realized; `fred-sdk` + `fred-core` + `control-plane`
+ `fred-runtime`):
- `ExecutionGrant` gains a signature envelope (`key_id`, `jti`, `signature`) and
  **resolution claims** (`template_agent_id`, `owner_team_id`, `display_name`,
  inline `tuning`). `canonical_payload()` is the signed byte string (all fields
  except `signature`). The grant remains non-secret and topology-free.
- New shared `fred-core/security/keyless_signer.py`: `GrantSigner`
  (`LocalKeypairSigner` PRIMARY for local/on-prem, `IamSignBlobSigner` for GKE) +
  `GrantVerifier`. RS256 detached signatures; asymmetric so runtimes verify but
  never mint. `sign_grant`/`verify_grant_signature` glue in `fred-sdk`.
- Control-plane signs the grant at `prepare-execution` (after team ReBAC) and
  embeds the resolution claims; serves the public key at
  `GET /control-plane/v1/.well-known/grant-jwks`. Config:
  `security.grant_signing` (`fred-core`).
- Runtime verifies the signature (`_verify_grant_signature`) behind
  `security.grant_signing.enforcement`: `observe` (verify + audit, still serve)
  → `enforce` (reject unsigned/invalid). In `enforce`, the runtime resolves from
  the verified grant (`_resolve_from_grant`) and **no longer calls the
  control-plane per turn** — closing F2 by elimination and removing per-turn load.
  The `require_admin` resolution endpoint remains for operator/CLI inspection only.

Rollout is `observe → enforce`; both are equivalence-tested (the grant-derived
target matches the callback's). Cryptographic signing was previously deferred to a
later phase; it is now delivered here.

### 8.11 ✅ Signed grant removed — pod-side authorization (RUNTIME-07 rev. 2, June 2026)

**Supersedes §8.9 and §8.10.** The signed-grant / valet-key approach (Phases 1–2)
was reversed by RFC decision **D5**: making the control-plane a cryptographic root
of trust is an unnecessary homologation burden. The authoritative model is
**Keycloak resource servers + pod-side OpenFGA, with no control-plane-issued token**.

**Removed**: the `ExecutionGrant` envelope + `validate_execution_grant` (`fred-sdk`);
`fred-core/security/keyless_signer.py` + `security.grant_signing` config; the
control-plane grant signing + `GET /control-plane/v1/.well-known/grant-jwks` endpoint.

**Now**: every execute / resume / evaluate request funnels through
`_authorize_and_resolve` (§2.4) — JWT identity (body tokens neutralized), session
ownership, OpenFGA `CAN_READ(team)`, ReBAC-gated team-scoped instance resolution,
and an owner-team cross-check. The **`c3` security profile**
(`fred_core.security.oidc.apply_security_profile`) forces strict JWT issuer/audience
and **fail-closed startup** (Keycloak user + M2M + OpenFGA all required), enforced
today by control-plane, fred-agents, and knowledge-flow. The multi-pod packaging
(one Keycloak client/audience per agent) and the sessionless HTTPS/SSE transport
introduced on the branch are retained.

### 8.12 ✅ Global base prompt injected at runtime, not baked — RUNTIME-09 (June 2026)

**What changed.** Fred's shared global base prompt (currently the Mermaid output
contract, `fred_sdk.resources.prompts/mermaid_output_contract.md`) was previously
composed into each shipped agent's default `system_prompt_template` at authoring
time via `apply_global_base_prompts(...)` /
`load_agent_prompt_markdown(..., include_global_base_prompts=True)`. It is now
**injected at execution time** as a system-prompt suffix and is no longer part of
any editable template.

**Final system-prompt composition (ReAct).** In `ReActRuntime` the effective
prompt is now assembled as:

```
system_prompt
  + _build_runtime_tool_prompt_suffix(bound_tools)
  + _build_guardrail_suffix(definition)
  + _build_global_base_prompt_suffix()          # NEW — GLOBAL_BASE_PROMPT_MARKDOWN
  + _build_attachment_context_suffix(binding)
```

`DeepAgentRuntime` adds the same `_build_global_base_prompt_suffix()` before its
filesystem suffix. `build_global_base_prompt_suffix()` lives in
`fred_runtime.react.react_prompting` and returns `GLOBAL_BASE_PROMPT_MARKDOWN`
(the SDK-owned single source of truth) with a leading blank-line separator, or
`""` when the bundle is empty.

**Consequences.**

- The contract no longer appears in the operator-editable system prompt (agent
  editor) and cannot be deleted by an operator.
- An operator-overridden prompt (`prompts.system`) now **keeps** the contract,
  fixing a prior inconsistency where a custom prompt silently dropped it.
- Graph agents (mindmap, `GraphRuntime`) do not pass through this suffix path —
  unchanged; they never carried the bundle.
- `fred-sdk` retains `GLOBAL_BASE_PROMPT_RESOURCES` / `GLOBAL_BASE_PROMPT_MARKDOWN`
  as the content source; `apply_global_base_prompts` and the
  `include_global_base_prompts` flag are removed.
- **No data migration.** Agent instances created before this change keep the
  baked contract frozen in their persisted `tuning.values["prompts.system"]`;
  the editor still shows it for those until the operator clears the field. Only
  newly created instances get the clean default. (Decision: new agents only.)

### 8.13 ✅ `UiPart` union extended by capability registration — CAPAB-01 #1977 (July 2026)

**What changed.** `UiPart` (`fred_sdk/contracts/context.py`) stays declared as
the frozen `LinkPart | GeoPart` base, but is no longer a hand-edited hotspot:
capability `manifest.chat_parts` classes are folded into the union at registry
boot by `fred_sdk.contracts.ui_part_union.rebuild_ui_part_union` (alias swap in
importing modules + annotation rewrite + dependencies-first model rebuild).
Consequences for contract consumers:

- `boot_capability_registry()` now runs at `create_agent_app` **construction**
  (was: lifespan) so registered parts join the union before routes capture
  response-model schemas; the offline `generate_openapi.py` export therefore
  includes capability parts — regenerated OpenAPI/frontend types pick them up
  with zero hand edits to union files.
- Validators are built lazily against `current_ui_part_union()`; the
  `/agents/execute` response adapter and the OpenAI-compat `_extract_ui_parts`
  (which now validates against the union instead of a hand-listed `link`/`geo`
  switch) refresh automatically. Unknown part kinds are skipped, never a crash.
- Wire compatibility: events carrying only `link`/`geo` are byte-identical to
  before; capability parts appear only when the emitting pod has the
  capability installed (duplicate kinds fail boot, `DuplicateChatPartKindError`).
- Frontend mirror (#1977): `ThreadMessage` carries raw parts (no lossy
  pre-fold); a part-renderer registry keyed by part `type` dispatches known
  kinds and silently skips unknown ones at render time only.

---

### 8.14 ✅ Typed per-capability `turn_options` on the execute request — CAPAB-01 #1976 (July 2026)

**What changed.** `RuntimeExecuteRequest.turn_options: dict[str, dict]` is added
to the frozen execute/execute-stream body (`fred_sdk/contracts/execution.py`),
keyed by capability id. The envelope is generic; the key is the discriminator.

- **Turn start.** Before any SSE bytes flush, `_enforce_turn_options`
  (`agent_app.py`) resolves the instance's active capabilities and validates
  each slice against that capability's `TurnOptionsModel` via
  `validate_turn_options`. An unknown/unselected capability id or a slice that
  fails its model → typed **HTTP 422** (`TurnOptionsInvalidError`), same style as
  capability `validate-config` — never a mid-stream error event.
- **Assembly.** Each capability's middleware receives only its own typed slice
  through `CapabilityContext.turn_options` (`build_capability_contexts` narrows
  the generic map per capability); inside a capability everything is statically
  typed, only the assembly loop is generic (RFC §3.5).
- **New pod route.** `POST {base_url}/agents/capabilities/chat-controls`
  (`ChatControlsRequest` → `ChatControlsResponse`, same bearer as `/agents/*`)
  batch-evaluates `capability.chat_controls(config)` at session prep; the
  control-plane caches the results cache-aside and ships
  `ExecutionPreparation.chat_controls`. Retires `EffectiveChatOptions` (RFC
  §3.3/§3.7).
- Wire compatibility: an absent/empty `turn_options` is the default — existing
  bodies are byte-identical.

---

### 8.15 ✅ `RuntimeServices.document_search` port — CAPAB-01 #1906 (July 2026)

**What changed.** A new OPTIONAL, additive port on the frozen `RuntimeServices`
dataclass (`fred_sdk/contracts/runtime.py`), the same class of change as its
other optional ports (default `None`, backward-compatible — existing
construction sites and wire bodies are byte-identical):

```python
class DocumentSearchResult(FrozenModel):
    hits: tuple[VectorSearchHit, ...] = ()

class DocumentSearchPort(ABC):
    async def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        library_tag_ids: Sequence[str] | None = None,
        document_uids: Sequence[str] | None = None,
        search_policy: str | None = None,
    ) -> DocumentSearchResult: ...

@dataclass(frozen=True, slots=True)
class RuntimeServices:
    ...
    document_search: DocumentSearchPort | None = None
```

**Doctrine (RFC AGENT-CAPABILITY §3.8, §10).** Capabilities reach platform
services ONLY through typed optional ports on `RuntimeServices`; the per-turn
binding and the raw access token never enter `CapabilityContext`. The port takes
scope PARAMETERS only — never a caller-supplied context, identity, or token.
The runtime adapter (`DocumentSearchAdapter`, fred-runtime) captures the per-turn
binding PRIVATELY (wrapping the same `VectorSearchClient` path as
`FredKnowledgeSearchToolInvoker`) and exposes only `search(...)`; it is wired in
`_build_runtime_services` and flows to capabilities as
`ctx.services.document_search`.

- Rejected alternatives: (a) passing the binding into `CapabilityContext`
  (token-leak / security regression); (b) reusing `services.tool_invoker` with
  `tool_ref="knowledge.search"` (cannot express per-capability config scoping —
  it reads scope from `runtime_context`, not the payload).
- No OpenAPI/wire-schema change: the port is internal DI, not a serialized
  request/response model.

---

### 8.13 ✅ `RuntimeContext.user_groups` removed — AUTHZ-05 final sweep (July 2026)

**What changed.** `RuntimeContext.user_groups` (`fred_sdk.contracts.context`,
Group D) is removed. It was a confirmed dead Keycloak-groups vestige: its only
producer was `agent_app.py::_iterate_runtime_event_payloads` reading
`ctx.get("user_groups")`, a `RuntimeExecuteRequest.context` dict key that no
backend ever set and no `apps/frontend/src` code (only the generated OpenAPI
type) ever populated. Its only 2 consumers (`ReActRuntime`, `graph_runtime.py`)
fed it straight into `KPIActor.groups` (also removed the same session, see
`docs/swift/backlog/AUTHZ-MIGRATION-BACKLOG.md` §AUTHZ-05) via a
`MetricsProvider.timer(groups=...)` parameter — that parameter is removed too,
from `fred_core.portable.observability.MetricsProvider` and its 2
implementations, and from fred-runtime's `_MetricsTimerAdapter`.

**Wire impact.** `user_groups` was a field on the `RuntimeExecuteRequest`
schema exposed by both `libs/fred-runtime` and (via a separate, seemingly
unregenerated generated client) `apps/frontend/src/slices/agentic/`. Since no
caller ever set it, removal is behavior-preserving. Regenerated
`libs/fred-runtime/openapi.json` (`make generate-openapi`, gitignored
artifact) and `apps/frontend/src/slices/runtime/runtimeOpenApi.ts` (`make
update-runtime-api`, 1-line diff); frontend `tsc --noEmit` clean.
`apps/frontend/src/slices/agentic/agenticOpenApi.ts` still carries a stale
`user_groups` field — no Makefile target regenerates it (looks like a
dead/legacy generated client, out of scope for this sweep).

---

### 8.16 ✅ `DELETE /agents/checkpoints/{session_id}` returns a deleted count (July 2026)

**What changed.** The endpoint (`agent_app.py::delete_checkpoint_thread`) went
from `status_code=204, response_model=None` (bare, bodyless response) to
`status_code=200` returning `{"deleted": n}` — `n` is the number of rows
removed from the checkpoints table for that thread, mirroring the sibling
`DELETE /agents/sessions/{session_id}` (history) endpoint's `{"deleted": n}`
shape exactly. `FredSqlCheckpointer.adelete_thread` (`sql_checkpointer.py`) now
returns that count (`# type: ignore[override]` — LangGraph's
`BaseCheckpointSaver.adelete_thread` is typed `-> None`) instead of `None`,
computed from the `checkpoints` table's delete rowcount; the `writes`/`blobs`/
`thread_owner` rows are still purged but are not separately counted.

**Why.** `ConversationErasureService._erase_runtime_checkpoint` (control-plane,
CTRLP-12) had no way to report how many checkpoint rows an erasure actually
purged — every conversation erasure receipt showed `deleted_count=None` for
the `runtime_checkpoint` store regardless of whether it purged one checkpoint
or a hundred, while every other store in the same receipt reported a real
count. Discovered live while testing the SQL-agent/tabular observability path.

**Wire impact.** Regenerated `libs/fred-runtime/openapi.json` (`make
generate-openapi`, gitignored artifact — no frontend-facing generated client
consumes this pod-internal endpoint). `pod_client.py::PodClient.delete_checkpoint`
(fred-agents-cli) updated to return the count too, mirroring its sibling
`delete_session_messages`. `fred-runtime` version bumped `3.3.3` → `3.3.4`.

---

## 8. Developer CLI — `fred-agents-cli`

> **Platform convention:** every Fred backend exposes `make cli`.
> See [`platform/CLI-CONVENTION.md`](../platform/CLI-CONVENTION.md) for the full pattern.

The CLI is a first-class contract consumer. It exercises the frozen execution
contract from a terminal without the frontend. Run it with `make cli` from
`apps/fred-agents/`. Entry point: `fred-agents-cli` (`libs/fred-runtime/pyproject.toml`).

### Commands

| Command                      | What it does                                                   |
| ---------------------------- | -------------------------------------------------------------- |
| `/help`                      | Print command reference                                        |
| `/help <question>`           | Ask a natural-language question via the pod (multilingual)     |
| `/agents`                    | List available agent IDs                                       |
| `/agent <id>`                | Switch active agent                                            |
| `/session <id>`              | Change the current session ID                                  |
| `/sessions`                  | List all sessions for the current user                         |
| `/history [session_id]`      | Show conversation history                                      |
| `/checkpoints [limit]`       | List checkpoint threads                                        |
| `/checkpoint <thread_id>`    | Inspect all checkpoints for one thread                         |
| `/context`                   | Show execution context summary (agent, session, mode, pod URL) |
| `/stats`                     | Checkpoint storage statistics                                  |
| `/mode [final\|stream]`      | Show or change execution mode                                  |
| `/login` / `/login-password` | Authenticate via PKCE or username/password                     |
| `/team [team_id\|clear]`     | Show, set, or clear the current team scope                     |
| `/whoami` / `/logout`        | Auth status and logout                                         |
| `/quit`                      | Exit                                                           |

Any text that does not start with `/` is sent as a message to the current agent.
Unknown or malformed slash commands print a usage hint rather than forwarding
to the agent.

### `/help <question>` assistant

When the user types `/help <question>`, the CLI calls the pod's
`/agents/execute` endpoint with the question prefixed by a CLI reference context,
using an ephemeral session (`__help__<uuid>`). The agent responds in the user's
language. Falls back to the static command reference if the pod is unavailable.

---

### CLI role in the migration

The CLI is not just a developer convenience:

- it is the smallest end-to-end consumer for validating team-scoped managed
  execution before the frontend is rewired
- it must remain able to inspect execution context, history, checkpoints, and
  managed/runtime identity boundaries without browser dependencies
- if a backend change cannot be validated through `fred-agents-cli` or targeted
  runtime tests, the backend path is not yet "dry" enough for frontend cutover

## 9. Backend Completeness Gate Before Phase 4

Before frontend SSE migration starts, the runtime/backend path must satisfy the
following invariants:

1. Team-scoped managed execution works correctly even when the same pod exposes
   the underlying capability through raw `agent_id`.
2. Managed execution is authorized by the pod (Keycloak JWT + OpenFGA on the
   caller's team) and the instance is resolved through a ReBAC-gated control-plane
   callback — not inferred from pod-local tenancy.
3. Runtime history, checkpoint, and resume flows preserve the same execution
   identity set used at request time.
4. Logs, metrics, KPI rows, and tracing payloads are enriched consistently with
   the execution identity and correlation fields below.
5. Langfuse-exported traces keep the same identity metadata so downstream
   analysis does not lose team or managed-agent scope.
6. `fred-agents-cli` remains a first-class validation client for these flows.

Required observability identity set:

- `user_id`
- `team_id`
- `agent_instance_id`
- `template_agent_id` when known
- `session_id`
- `checkpoint_id` when relevant
- `trace_id`
- `correlation_id`
- runtime identity (`runtime_id` or equivalent service discriminator)

If any of these fields are missing in one backend path, the fix belongs in the
source contract/runtime instrumentation layer first, not in the frontend.

Implemented runtime-side today:

- `checkpoint_id` is propagated through the pod request bridge and enforced for
  resume-capable runtime requests
- managed HITL resumes set `execution_action == "resume"` (the `ExecutionGrantAction` enum)
- runtime span metadata, graph KPI dimensions, KF client KPI dimensions, MCP
  tool KPI dimensions, and Langfuse span metadata preserve the managed
  execution identity fields available at runtime
- `fred-agents-cli` can set team scope explicitly via `/team` or `--team-id`
  and exercise the same managed/team-scoped backend path without the frontend
- `fred-runtime` now restores a concrete KPI pipeline at pod startup:
  `KPIWriter`, Prometheus export when configured, and process/SQL pool KPI
  background emitters for scrape-based local validation and laptop benchmarks
- Prometheus export filters unbounded runtime identity labels (`session_id`,
  `user_id`, `exchange_id`) at the KPI sink; the original KPI event still carries
  those dimensions for structured delegates such as log/OpenSearch stores
- `fred-agents-cli` can now inspect that same runtime metrics surface directly
  via `/kpi [pattern]`, so backend KPI validation no longer depends on a local
  Grafana/Prometheus stack

Still pending before Phase 4:

- end-to-end validation from `fred-agents-cli` that one managed execution works
  through the real control-plane-approved path, not only pod-local shortcuts
- end-to-end validation that one managed HITL resume preserves the same
  session/checkpoint identity set across runtime history, checkpoints, KPI,
  metrics, and traces
- verification that a capability still reachable via raw `agent_id` behaves
  correctly when invoked through team-scoped managed execution
- broader audit of non-runtime backend log sinks so every emitted log path
  carries the same managed identity set consistently
- final end-to-end validation that control-plane-issued session authority is
  sufficient for managed resume authorization beyond runtime-local consistency

The current recommended continuation order is:

1. validate the managed execution path from `fred-agents-cli`
2. validate managed HITL resume end-to-end
3. finish the remaining observability/log-sink audit
4. only then begin Phase 4 frontend SSE migration

---

## 10. Phase 2 Status — OpenAPI And Frontend Codegen

Phase 2 is complete enough to serve as the contract source for the frontend.

### 10.1 What is now true

- `libs/fred-runtime/Makefile` exposes `make generate-openapi`
- `libs/fred-runtime/openapi.json` is generated locally from the pod app factory
- `apps/frontend/src/slices/runtime/runtimeOpenApi.ts` is generated from `fred-runtime`
- the following are OpenAPI-visible and should remain typed:
  - `RuntimeExecuteRequest`
  - execution identity and authorization models
  - `RuntimeEvent` variants
  - `UiPart`
  - `ChatMessage`
  - `OpenAIModelList`

### 10.2 What is still intentionally limited

- RTK Query codegen still emits `any` for SSE mutation responses:
  - `POST /agents/execute/stream`
  - `POST /v1/chat/completions`
- this is acceptable for now because Phase 4 will parse SSE frames manually
  with `fetch()` and can rely on the generated component types for the frame payloads
- if a frontend type is missing, fix the source contract or FastAPI schema and
  regenerate; do not add shadow TypeScript interfaces beside the generated slice

### 10.3 Source Of Truth Map

| Concern                          | Source of truth                                     | Notes                                     |
| -------------------------------- | --------------------------------------------------- | ----------------------------------------- |
| Shared execution/auth contracts  | `libs/fred-sdk/fred_sdk/contracts/`                 | Edit here first                           |
| Frontend-facing runtime routes   | `libs/fred-runtime/fred_runtime/app/agent_app.py`   | OpenAPI comes from these route signatures |
| OpenAI-compatible models         | `libs/fred-sdk/fred_sdk/contracts/openai_compat.py` | Secondary interface only                  |
| Frontend generated runtime slice | `apps/frontend/src/slices/runtime/runtimeOpenApi.ts`     | Generated file; do not hand-edit          |
| Migration sequencing             | `BACKLOG.md`                                        | Current phase and next step               |

### 10.4 Regeneration Commands

```bash
cd libs/fred-runtime && make generate-openapi
cd frontend && make update-runtime-api
```

If the generated frontend slice does not change as expected, fix the source
contract first. Do not patch the generated TypeScript by hand.

---

## 11. What Is Explicitly Deferred

| Item                                                                                               | Phase     |
| -------------------------------------------------------------------------------------------------- | --------- |
| `checkpoint_id` authorization against the caller's `session_id` at resume                          | deferred  |
| Backend completeness gate implementation for observability enrichment and managed-scope validation | Phase 3b  |
| Frontend SSE transport migration (replace WebSocket)                                               | Phase 4   |
| Control-plane product/session/admin API migration                                                  | Phase 3   |
| `agentic-backend` removal from frontend runtime path                                               | Phase 6   |

---

## 12. Key Rules (for AI assistants and reviewers)

1. `team_id` is mandatory and explicit in every managed execution (`runtime_context.team_id`).
2. `agent_instance_id` is the default execution target; `agent_id` is dev-only and forbidden under the `c3` profile.
3. Managed execution is authorized by the **pod itself**: a valid Keycloak JWT plus an OpenFGA `CAN_READ` check on `runtime_context.team_id`. There is **no `ExecutionGrant`**.
4. The **pod is the execution authority**; control-plane resolves *where* an agent runs (`prepare-execution`) but issues no capability and is never on the execution path.
5. Checkpoint/session access must be authorized at session scope (the session must belong to the caller).
6. Fred code must not rebuild native Kubernetes routing/discovery behavior.
7. No request field may carry infrastructure secrets; the pod resolves config from control-plane via a ReBAC-gated, team-scoped callback — never a secret.
8. `OpenAI /v1` is secondary; the native SSE protocol is the primary frontend contract.
9. Do not recreate `agentic-backend` chat/session DTOs inside `fred-runtime`.
10. Do not add new abstraction layers, wrappers, or endpoints unless the current contract is provably insufficient.
11. Prefer strengthening typing on existing contracts over inventing new transport shapes.
12. Never hand-edit generated files such as `apps/frontend/src/slices/runtime/runtimeOpenApi.ts`; regenerate from source contracts.
13. When code and migration docs diverge, update the docs in the same change.
14. If several implementation paths are possible, choose the smallest one that matches this document and `BACKLOG.md`.
15. If a schema is missing from frontend codegen, first fix `fred-sdk` or the
    FastAPI route signature/`response_model`; do not create parallel frontend DTOs.
16. If a migration decision is unclear, stop at the smallest safe change and
    document the ambiguity in `BACKLOG.md` rather than inventing a new direction.
17. Before frontend cutover, validate team-scoped managed execution through the
    CLI and backend tests, not only through browser assumptions.
18. Observability enrichment is part of the execution contract: logs, KPI,
    metrics, and Langfuse traces must preserve the same execution identity.

---

## 13. Evaluation Execution Surface — EVAL-01 (June 2026)

### Frozen surface

`POST /agents/evaluate` is the sole execution surface for agent evaluation.
No second evaluation endpoint will be introduced in `fred-runtime`.

`EvalTrace` (defined in `fred-sdk/contracts/eval.py`) is the frozen return contract.
Its fields — `output`, `error`, `steps`, `tools_called`, `retrieval_context`,
`latency_ms`, `token_usage` — are stable. Additions require a dated amendment here.

### Equivalence rule

`POST /agents/evaluate` must remain equivalent to the normal execution path for:
- authentication and pod-side authorization (`_authorize_and_resolve`, §2.4)
- runtime context and history behavior
- tool execution and identity propagation

The only difference is the synchronous structured return instead of an SSE stream.

### Scoring boundary

Scoring, metric calculation, and judge calls do **not** run inside `fred-runtime`.
They run in the separate evaluation worker (Control Plane side).
No DeepEval, LiteLLM, or OpenTelemetry dependency is permitted in `fred-runtime` or `fred-sdk` for this purpose.

### RFC reference

`docs/swift/rfc/AGENT-EVALUATION-RFC.md` — EVAL-01 v2
