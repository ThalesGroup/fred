# Runtime Execution Contract — Phase 1 + Phase 2 Continuity

> ✅ **Security model — RUNTIME-07 rev. 2 (2026-06-28, RFC decision D5).** There is **no
> `ExecutionGrant`**: the control-plane issues no signed (or unsigned) authorization token.
> Managed execution is **authenticated** by the caller's **Keycloak JWT** and **authorized by
> the agent pod itself**, per request, via an **OpenFGA ReBAC check** on the team carried in
> `runtime_context.team_id` for regular collaborative-team users (with the documented
> intrinsic-personal and service-agent cases). The control-plane's `prepare-execution` resolves only *where* the
> agent runs (URLs) and the session's context — never a capability. §0–§3 describe this model;
> the dated entries in §8 (§8.9-§8.11) record the abandoned signed-grant approach as history.
> See the narrative in [`ARCHITECTURAL-SECURITY-REPORT.md`](./ARCHITECTURAL-SECURITY-REPORT.md).

RFC links in this document preserve decision history only. This design document
is the current authority for implemented runtime behavior.

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

> ✅ **Per-tool-call reverify / service-agent regression fix — 2026-07-22
> (EVAL-03 follow-up).** `ToolObservabilityMiddleware._reverify_team_authorization`
> (added the same day to close a least-privilege gap — a stale/revoked team
> membership was trusted for a whole ReAct turn after the one OpenFGA check at
> turn start) called the low-level `check_permission_or_raise` primitive
> unconditionally, without the `is_service_agent` bypass `_authorize_execution_or_raise`
> already grants at turn start (EVAL-AUTH Solution A, above). This broke every
> tool call made by the evaluation worker's service identity — turn start
> passed, the first tool call then failed closed with `AuthorizationError`.
> Fix: `_authorize_and_resolve` now stamps the trusted `is_service_agent`
> verdict (computed once from the JWT, never from caller-supplied `context`)
> into `PortableContext.baggage`; the per-tool-call reverify reads it and skips
> the ReBAC check for service-agent callers, mirroring the turn-start decision
> instead of re-deriving a stricter one. Regular users are unaffected — the
> least-privilege re-check still runs for every non-service-agent call.

> ✅ **Public-team content/execution gap closed — 2026-07-29 (issue #2146, PR #2147).**
> TEAM-09/TEAM-10 widened `TeamPermission.CAN_READ` to include any authenticated
> user via the `public` marketplace-discovery relation on `PUBLIC`-visibility
> teams (the default for every team at the time; new teams default to
> `PRIVATE` since 2026-08-26, #2433 — existing rows keep their stored value).
> Every pod-side authorization check that
> gates real content or execution — not just team-profile discovery — must
> therefore use `TeamPermission.CAN_USE_TEAM_AGENTS` (`team_member`-only)
> instead. This was true at turn start (`_authorize_execution_or_raise`,
> §2.2/§2.4) but not at three sibling checks, all now fixed: the per-tool-call
> reverify (`ToolObservabilityMiddleware._reverify_team_authorization`), the
> OpenAI-compatible `/v1/chat/completions` surface
> (`openai_compat_router.py`), and the control-plane's own prompt-library
> reads (`product/api.py`, `control-plane-backend`). Every other reference to
> `CAN_READ` below and in §8's dated history predates this fix and should be
> read as `CAN_USE_TEAM_AGENTS` for anything that returns real content or
> executes an agent; `CAN_READ` alone remains correct only for team-profile
> discovery (e.g. `get_team_agent_instance_runtime`, config-only). See §8.28.

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
     │                              team authorization         │
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
agent pod authenticates the Keycloak JWT and authorizes the request itself:
OpenFGA `CAN_USE_TEAM_AGENTS` for regular collaborative-team users, exact
intrinsic ownership for a personal space, or the scoped service-agent rule.
`control-plane` resolves which
runtime pod serves which agent instance (via `prepare-execution`) but issues no
capability and never proxies the SSE stream. The runtime currently performs an
internal control-plane binding lookup again before activation, so control-plane
availability and latency remain a pre-LLM dependency; §0.2 records that current
implementation honestly.

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
  │                             │  • authorize team scope     │
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
3. **Team authorization** — a regular collaborative-team caller must hold
   OpenFGA `CAN_USE_TEAM_AGENTS`; a personal-space caller must present the exact canonical
   `personal-<uid>` derived from the JWT; the scoped service-agent rule is the
   only other bypass. Denial fails closed (403). Under the `c3` profile a direct
   `agent_id` is forbidden entirely.
4. **Team-scoped resolution** — the instance template + tuning is resolved from the
   control-plane through a ReBAC-gated, team-scoped callback, then the resolved
   owner team is cross-checked against the caller's claimed team.

**HITL resume** follows the exact same path with `execution_action: "resume"` and
`resume_payload` in the request body instead of a new user message.

---

## 0.2 One-turn hot path, performance, and scalability contract

This section is the current operational design authority for one managed turn.
It replaces inference from dated RFC narratives. The source-backed review and
per-finding acceptance criteria live in
[`2026-07-26-agent-turn-core`](../reviews/performance/2026-07-26-agent-turn-core/README.md).

### Current execution sequence

| Order | Boundary | Work on the critical path before the next boundary |
|---:|---|---|
| 1 | `POST /agents/execute/stream` | Validate request and Keycloak identity; normalize trusted runtime context |
| 2 | Session/checkpoint access | Verify resumed checkpoint ownership when applicable; for an existing session, verify existence and owner in PostgreSQL |
| 3 | Pod execution authorization | For a regular collaborative-team user, require OpenFGA `CAN_USE_TEAM_AGENTS`; personal ownership and the scoped service-agent rule keep their documented behavior |
| 4 | Managed runtime binding | Call the control-plane internal binding endpoint, authorize the team there, read the instance/team capability settings and the current reasoning-enabled model set, then cross-check the resolved owner team |
| 5 | Model authorization | Resolve usable model capabilities with a team-scoped OpenFGA lookup before model routing |
| 6 | Runtime activation | Build request context/services/capabilities, activate MCP tools, construct the selected ReAct/Deep/Graph runtime and executor |
| 7 | Model/tool loop | Stream remote LLM output; execute tools and any HITL pause/resume; checkpoint through the shared async SQL engine |
| 8 | SSE delivery | Serialize typed events and deliver them directly from the runtime pod to the caller |
| 9 | Completion/history | Emit turn telemetry, then persist the projected history asynchronously and fail-open relative to the already delivered response |

The control-plane does **not** proxy step 8, but its internal lookup in step 4
means it is still a synchronous dependency of runtime activation. A production
turn is not ready for its first LLM token until steps 1–6 complete.

### Runtime performance invariants

Every implementation and review must preserve these invariants:

1. **LLM latency first, tool latency second.** Pre-LLM work has an explicit
   budget; every runtime emits the canonical `llm.call_latency_ms` and
   `agent.tool_latency_ms` signals through the resilient KPI sink.
2. **No synchronous I/O in async execution.** Network, SQL, filesystem, token
   refresh, and sink operations reached from an `async def` must be natively
   async or isolated behind a deliberately bounded executor.
3. **Bound every remote wait and shared resource.** LLM, OpenFGA,
   control-plane, MCP, Keycloak, Knowledge Flow, SQL-pool acquisition, pending
   history work, and pod admission need explicit time/capacity limits.
4. **Share transports, not request identity.** Reuse process-wide HTTP/model
   transports where safe. Tokens, checkpoint state, request baggage,
   interceptors, and authorization decisions remain request/principal scoped.
5. **Concurrency must be intentional.** Independent I/O may use bounded
   concurrency (`asyncio.gather` or a task group). Security checks and ordering
   dependencies must not be parallelized merely to hide an over-fetching
   contract.
6. **Conversation work is bounded.** Model-input history, persisted checkpoint
   growth, tool calls per turn, parallel tool calls, event buffering, and
   background persistence have explicit budgets and overload behavior.
7. **Replica scope is explicit.** A pod-local cache or in-memory queue is never
   described as shared or durable. Its key, TTL, invalidation, token treatment,
   and behavior across deployment replicas are part of the design.
8. **Authorization stays fail-closed.** Performance work must not weaken
   turn-start, model-capability, or per-tool authorization or extend revocation
   staleness without an approved security decision.

### Current compliance status (2026-07-26)

| Area | Current status | Evidence / required follow-up |
|---|---|---|
| Direct SSE path | **Meets design** — the control-plane does not proxy the stream | §0.1 |
| LLM transport | **Meets base design** — async streaming, shared connection pool, explicit connect/read/write/pool timeout | `fred_core.model.http_clients`; production model catalog |
| Knowledge Flow transport | **Meets base design** — shared async client and explicit tuning | `fred_runtime.common.kf_http_client` |
| Binding call budget | **Gap (P1)** — full team projection causes about 21 control-plane ReBAC operations per managed turn and the pod creates a fresh HTTP client | [TURN-01](../reviews/performance/2026-07-26-agent-turn-core/TURN-01-control-plane-runtime-binding-fanout.md) |
| Model authorization | **Needs load evidence (P1)** — one additional OpenFGA lookup before every team-scoped LLM turn | [PERF-02](../reviews/performance/2026-07-26-observ-02-v3/PERF-02-model-authz-openfga-hot-path.md) |
| MCP activation | **Needs load evidence (P1)** — sequential cold discovery, token-scoped pod cache, no singleflight | [TURN-02](../reviews/performance/2026-07-26-agent-turn-core/TURN-02-mcp-cold-path-and-cache-scope.md) |
| ReAct/Deep model/tool boundary | **Mostly meets design** — canonical KPI/audit middleware and per-tool ReBAC; the authorization cost needs an explicit stage metric and load budget | [core review](../reviews/performance/2026-07-26-agent-turn-core/README.md) |
| Graph model/tool boundary | **Gap (P1)** — bypasses canonical LLM/tool KPI, tool audit, and per-call ReBAC | [TURN-03](../reviews/performance/2026-07-26-agent-turn-core/TURN-03-graph-runtime-observability-and-authz.md) |
| Turn resource budgets | **Partially fixed** — ReAct now has a size-based model-input budget alongside the message-count window (§8.52, 2026-08-13) and a shipped tool-call cap (`apps/fred-agents/tool_pacing.py`, 2026-08-01); **Gap (P1) remains** for Deep, Graph, persisted-checkpoint compaction, and the unused parallel-call policy | [TURN-04](../reviews/performance/2026-07-26-agent-turn-core/TURN-04-turn-resource-bounds.md), [#2343](https://github.com/ThalesGroup/fred/issues/2343) |
| SSE/history lifecycle | **Needs load evidence (P2)** — full payload buffering and unbounded fire-and-forget persistence tasks | [TURN-05](../reviews/performance/2026-07-26-agent-turn-core/TURN-05-sse-buffering-and-history-backpressure.md) |
| Pod/SQL admission | **Needs load evidence (P1)** — Uvicorn limit unset; shared async SQL pool defaults to 15 maximum connections | [TURN-06](../reviews/performance/2026-07-26-agent-turn-core/TURN-06-admission-and-sql-capacity.md) |
| Token refresh | **Fixed offline 2026-08-07** — the refresh is async, coalesced and bounded; the synchronous helper was removed (§8.48). The pod-level forced-expiry proof is still owed and cannot run until delegated refresh is reachable again | [TURN-07](../reviews/performance/2026-07-26-agent-turn-core/TURN-07-sync-token-refresh-in-async-path.md) |
| Runtime construction | **Needs load evidence (P2)** — runtime/executor/ReAct compilation repeats per turn | [TURN-08](../reviews/performance/2026-07-26-agent-turn-core/TURN-08-per-turn-runtime-rebuild.md) |

The call-budget estimate and P1/P2 labels above are review findings, not measured
production SLO results. The design is considered performance-validated only
after the relevant 200-concurrent-turn, four-replica scenarios and overload
behavior are recorded in the dossiers.

---

## 1. Goal

Establish `fred-sdk` as the single authoritative source of truth for the
**secure, team-scoped execution contract** between the frontend and agentic
runtime pods.

Every agent execution is:

- attributable to `user_id + team_id + agent_instance_id`
- authorized by the **pod-side team rule** (identity proven by the Keycloak
  JWT; OpenFGA for regular collaborative teams, with the documented intrinsic
  personal/service-agent cases)
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
- **Authorization** — for a collaborative team, the pod runs a per-request
  OpenFGA check that the caller holds `CAN_USE_TEAM_AGENTS` (`team_member`-only —
  unlike `CAN_READ`, which also admits the `public` marketplace-discovery
  relation; see the 2026-07-29 callout above) on
  `runtime_context.team_id`. A canonical personal space
  (`personal-<authenticated uid>`) uses intrinsic ownership by exact identity
  comparison, and the evaluation worker's `service_agent` identity uses the
  separately documented team-scoped bypass. Every other case fails closed.
- **Identity integrity** — `user_id` is taken from the validated token, never the
  request body; body-supplied tokens are neutralized.

The team in `runtime_context.team_id` is caller-supplied but safe: a
collaborative team must pass OpenFGA, and a personal-team identifier must equal
the canonical identifier derived from the authenticated user. A missing team on
a managed request fails closed (403). The `ExecutionGrantAction` enum (`execute`
/ `resume`) survives as the `execution_action` field; the `ExecutionGrant`
envelope does not.

**Personal-space authorization at this runtime boundary is intrinsic.** A
personal space has no `team_metadata` row and remains synthetic on the
control-plane product surface (`build_personal_team`). The runtime authorizes
only `fred_core.common.personal_team_id(authenticated_user.uid)` by exact
comparison, without an OpenFGA request. Another user's `personal-*` identifier
and the bare `"personal"` alias deny. Other platform operations may still model
personal teams in ReBAC as documented in
[`REBAC.md` § Personal teams](../platform/REBAC.md#personal-teams--self-provisioned-never-admin-writable-authz-08);
that does not change this turn-start fast path. `service_agent` callers are
unaffected: their team-scoped, OpenFGA-free authorization is checked first.

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
3. pod-side team authorization (`_authorize_execution_or_raise`): OpenFGA for
   a regular collaborative team, exact intrinsic ownership for a personal
   space, or the scoped service-agent rule,
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
- For ReAct V2 HITL resume specifically (#2216, see §8.39): `interrupt_id`
  (a field distinct from `checkpoint_id` — see §8.39 for why) must exactly
  match LangGraph's own `Interrupt.id` for one of the interrupts currently
  pending on that thread, not merely prove that *some* interrupt is
  pending. That occurrence is then atomically claimed, immediately before
  graph invocation, so a concurrent duplicate response can never resume it
  a second time

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
- Team-scoped managed agent authorization (pod-side OpenFGA `CAN_USE_TEAM_AGENTS` on `runtime_context.team_id`)
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
(multimodal/base64 image content) and `ToolMessage` untouched. **Superseded by §8.37 (2026-07-31):** this was originally an unconditional
collapse on every replayed message. It now only strips reasoning across a
*closed* turn boundary — reasoning inside an still-open tool loop is kept,
re-homed as ordinary assistant text, so the model does not "forget" why it
called a tool between loop steps. See §8.37 for the current contract. The
author override (`thought_config`, Layer 2) remains open.

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
requirements, and a "never reproduce URLs" guardrail.

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

**Still open (deployment infra, no code gap):** NetworkPolicies (ingress→pod,
pod→OpenFGA, pod→Keycloak, deny inter-agent) and end-to-end TLS to the pod are not
yet in the chart; no GitHub issue tracks this specifically.

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

**Amendment (2026-07-21).** `search()` gained an additive keyword
`attachments_only: bool = False`: the adapter then searches the session scope
only (`include_session_scope=True, include_corpus_scope=False`) — the
conversation's attached files, never the corpus. First consumer:
`document_access.search_attachments_only` (the capability also drops its
scope-picker chat control when the flag is on). `general_only` RAG scope keeps
precedence (no search at all).

---

### 8.16 ✅ `agent_assets` / `document_content` / `document_folders` ports — #1903 PPT filler (July 2026)

**What changed.** Three more OPTIONAL, additive ports on `RuntimeServices`
(`fred_sdk/contracts/runtime.py`), same class of change and same §8.15 doctrine
(scope/key parameters only; binding + token captured privately by the
fred-runtime adapters):

- `agent_assets: AgentAssetPort | None` — per-agent-instance config-asset
  storage (`store`/`fetch`/`delete` by slot-relative key). Backed by the KF
  virtual-filesystem sub-area `teams/{t}/agents/{agent_instance_id}/config/...`
  (`AgentConfigAssetsAdapter`). Injected BOTH turn-time
  (`_build_runtime_services`) and save-time
  (`_build_capability_save_services`, which now also receives the
  `agent_instance_id` from the validate-config form and stamps it on the
  privately-held `RuntimeContext`).
- `document_content: DocumentContentPort | None` — a corpus document's
  ORIGINAL bytes by uid (KF `GET /raw_content/{uid}`, `DocumentContentAdapter`
  over the new minimal `KfDocumentClient`).
- `document_folders: DocumentFolderPort | None` — author folder string →
  DOCUMENT tag id (save/analyze-time validation) and folder-tag document
  listing (KF `GET /tags` + `POST /documents/metadata/browse`,
  `DocumentFolderAdapter` over the new `KfTagClient`).

No OpenAPI/wire-schema change on the execution surface. The pod's
`validate-config` endpoint behavior is unchanged except that its save services
now carry the three ports, letting an asset-bearing capability store binaries
and resolve folders during `validate_config` (RFC AGENT-CAPABILITY §3.4/§3.8).

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

### 8.17 ✅ `DeepAgentRuntime` gets the same observability middleware as ReAct (July 2026)

**What changed.** `DeepAgentRuntime.build_executor` (`deep/deep_runtime.py`)
now always leads the middleware list it hands to `deepagents.create_deep_agent`
with `TracingKpiMiddleware` and `ToolObservabilityMiddleware` — the same two
instances, same construction, that `build_react_platform_middleware_frame`
wires for every ReAct agent. The pre-existing filesystem-tool guard
(`ToolCallLimitMiddleware` per disabled filesystem tool, unchanged) now
follows them instead of being the only middleware present.

**Why.** `DeepAgentRuntime` overrides `build_executor` entirely and never
calls `build_react_platform_middleware_frame`/`_create_compiled_react_agent`
— it builds its own `deepagents`-native graph. That meant a Deep turn emitted
no `[LLM][CALL]`/`[LLM][RESPONSE]` logs, no `llm.call_latency_ms` /
`agent.tool_latency_ms` KPI, and no `agent.tool.invocation.*` audit events:
the same guarantees `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` §9
documents for every other execution path, silently absent for Deep since the
runtime was first added. Found and fixed while scoping DeepAgent's move from
dormant to visible ahead of the go-live validation, landed in the same change
that registered `fred.github.deep_assistant` (`apps/fred-agents`) — the first
concrete `DeepAgentDefinition` in any app — so no Deep turn has ever run
unaudited in a shipped environment.

**Consequences.**

- No change to Deep's typed input/output/events, its filesystem-tool policy,
  or its explicit non-support for tool approval /
  `max_tool_calls_per_turn` (still `NotImplementedError` — out of scope here).
- `create_deep_agent`'s own `middleware=` parameter is the extension point;
  `TracingKpiMiddleware`/`ToolObservabilityMiddleware` needed no changes
  themselves — both were already generic `AgentMiddleware` implementations,
  not ReAct-specific.
- Regression coverage:
  `libs/fred-runtime/tests/test_deep_agent_middleware.py`.

### 8.18 ✅ `FieldSpec.ui.widget` stock form-widget hint — #2023 (2026-07-20)

**What changed.** `UIHints` (`fred_sdk/contracts/models.py`) gained an optional
`widget: str | None` field. It names a frontend stock **form** widget to render
that field in the agent-creation/edit form instead of the type-derived default
input — distinct from the chat-turn `ChatControlSpec.widget` registry. First
consumer: `document_access.library_tag_ids` sets
`ui=UIHints(widget="document_libraries")`, rendered by the frontend
`TuningFieldRenderer` as the `DocumentLibraryScopePicker` tree instead of a raw
tag-id `TagInput`. Control-plane's `ManagedAgentUiHints` mirror gained the same
field.

**Why.** Users had to hand-type library tag ids when configuring the
document-access capability on an agent; the tree picker already existed for the
chat composer. Additive and backward compatible: `None`/unknown widget ids fall
back to the default input, and older pods simply omit the field.

`controlPlaneOpenApi.ts` and `runtimeOpenApi.ts` regenerated
(`make update-control-plane-api` / `make update-runtime-api`).

**Amendment (2026-07-21).** `UIHints` also gained `visible_when: str | None` —
the key of a sibling field in the same form; the field is only rendered while
that sibling's effective value (current input or declared default) is truthy.
Display-only: the hidden field keeps its stored value, and backends must not
rely on it being hidden. First consumer: the legacy search tool's
`chat_options.bound_library_ids` is gated on `chat_options.libraries_binding`
in the pod `mcp_catalog.yaml`.

### 8.19 ✅ Personal-team authorization moved to fred-core, real ReBAC tuple — AUTHZ-08 (2026-07-20)

**What changed.** `agent_app.py::_authorize_execution_or_raise` no longer
special-cases personal spaces (the identity-only guard from AUTHZ-05 item 8b is
deleted). Personal teams are now real ReBAC team objects: `fred-core`'s
`RebacEngine.check_user_permission_or_raise`/`has_user_permission` self-heal
the owner's own `team_editor` tuple on a personal team on first touch, and
`RebacEngine.add_relation` refuses any other tuple naming a personal team. See
§2.2 above and [`REBAC.md` § Personal teams](../platform/REBAC.md#personal-teams--self-provisioned-never-admin-writable-authz-08)
for the full design.

**Why.** Live-stack testing (2026-07-20) found the AUTHZ-05 item 8b guard was
never generalized past `agent_app.py` — every other consumer of a personal
`team_id` (knowledge-flow-backend's filesystem/corpus/tag routes,
`openai_compat_router.py`, `tasks/authz.py`, control-plane's evaluations API)
still assumed OpenFGA held the answer, and it didn't: some crashed with an
unhandled 500, most wrongly 403'd the space's own owner. A real, narrowly
write-guarded tuple fixes every one of those call sites from one change in
`fred-core`, with no per-caller special-casing, and unlike an identity-only
guard it also makes `ListObjects`/enumeration (`lookup_user_resources`) work
correctly for personal spaces.

No OpenAPI/type changes — this is authorization-internals only.

### 8.20 ✅ Personal-team enumeration self-heal — AUTHZ-08 follow-up (2026-07-21)

**What changed.** §8.19's claim that a real tuple "makes `ListObjects`/
enumeration (`lookup_user_resources`) work correctly for personal spaces" was
not yet true when written: self-heal was wired into the permission-*check*
methods only. `fred-core`'s `RebacEngine.lookup_user_resources` now self-heals
the caller's own personal-team tuple too, before enumerating — see
[`REBAC.md` § Personal teams](../platform/REBAC.md#personal-teams--self-provisioned-never-admin-writable-authz-08).

**Why.** A first-touch user whose first authenticated call was an
enumeration (e.g. `GET /fs/list?path=/teams`, listing "teams I can read")
rather than a permission check on a known team id got an empty result — their
own personal team was silently missing until some other call happened to
provision it first. No OpenAPI/type changes.

### 8.21 ✅ `ToolResultRuntimeEvent.latency_ms` — chat trace detail restored (2026-07-22)

**What changed.** `ToolResultRuntimeEvent` (`fred_sdk/contracts/runtime.py`)
gains an additive `latency_ms: int | None = None` field. `react_runtime.py`
already computed the wall-clock duration of every tool call to close the
paired `tool_use` `ThoughtEndEvent` (`_elapsed_ms_since(thought_started_at)`)
— it now attaches that same value to the `ToolResultRuntimeEvent` itself
instead of only the bookkeeping thought. `agent_app.py`'s history-persistence
path threads it into `make_tool_result(..., latency_ms=...)` (the
`ToolResultPart.latency_ms` field already existed in `fred-core`'s
`history_schema.py` but was never populated by any caller). OpenAPI/generated
client regenerated (`make update-runtime-api`).

On the frontend, `useChatSse.ts` now copies `event.latency_ms` onto the
`ToolResultPart` it builds for the `tool_result` SSE case (previously
dropped, mirroring how `sources` was already handled for the `final` event
but not `tool_result`). `traceUtils.groupTraceEntries()` also stops emitting
a solo trace row for the synthetic `tool_use`-phase thought that brackets
every tool call: that row's title ("Calling `<tool>`") and its `conclusion`
were always the hardcoded literal `"Done"`/`"Error"` from `react_runtime.py`
— purely redundant bookkeeping, not agent-authored reasoning — and produced
one repeated, information-free "Done" row per tool call in the chain-of-thought
list. The paired `tool_call`/`tool_result` combo row already shows the
humanized tool label and the status dot, and now also shows the real latency.
Genuine authored thoughts (`planning`/`observation`/`reflection`/`synthesis`)
are unaffected — their `conclusion` is real agent-written text, not this
synthetic placeholder.

Separately, `TraceDetailDrawer`'s tool-result view (previously a blanket
`{action, status, latency}` redaction for every tool, per #1774/CHAT-13 —
see §8.6's sibling UX work) now recognizes two common, specifically-curated
content shapes from `ToolResultPart.content` and renders them richly instead
of redacting them: a tabular/SQL tool result (`{sql_query, rows, error}`,
e.g. `knowledge-flow-backend`'s `RawSQLResponse`) shows the executed SQL and a
row preview; a RAG/vector-search tool result (`{query, hits}`) shows the
search query and the retrieved hits via the existing `SourcesPanel` molecule.
Any other tool shape still falls back to the original redacted view — the
redaction default from #1774 is preserved for unrecognized tools, only two
specifically useful shapes are now exempted from it.

**Why.** User-reported regression (chain-of-thought review, 2026-07-22): the
#1774/CHAT-13 fix for noisy raw tool identifiers (see §8.6 area) overcorrected
by discarding all tool-result detail, including the two kinds of information
users actually look for mid-answer — the SQL query behind a numeric answer,
and the sources behind a RAG citation — and left `latency_ms` permanently
empty because no event in the pipeline ever populated it, while the
chain-of-thought list repeated a synthetic, content-free "Done" once per tool
call. No new contract surface was needed: `content` already carried the SQL
query and RAG hits (per-tool `sources` on `ToolResultRuntimeEvent` exist too,
but are still only consumed in aggregate on the final message — wiring
per-call `sources` through `ToolResultPart` is a possible fast-follow, not
done here since `content` already covers the citation case).

---

### 8.21 ✅ `RuntimeServices.document_tree` + `document_summarize` ports — #1906 follow-up (2026-07-21)

**What changed.** Two new OPTIONAL, additive ports on the frozen
`RuntimeServices` dataclass (`fred_sdk/contracts/runtime.py`), completing the
#1906 document-access pilot — the same class of change as §8.15 (default
`None`, backward-compatible, no wire-schema impact):

```python
class DocumentTreePort(ABC):
    async def tree(
        self,
        *,
        working_directory: str | None = None,
        library_tag_ids: Sequence[str] | None = None,
        max_chars: int = 6000,
    ) -> DocumentTreeResult: ...

class DocumentSummarizePort(ABC):
    async def summarize(
        self,
        document_uid: str,
        *,
        instruction: str | None = None,
        max_chars: int = 2000,
    ) -> DocumentSummaryResult: ...

@dataclass(frozen=True, slots=True)
class RuntimeServices:
    ...
    document_tree: DocumentTreePort | None = None
    document_summarize: DocumentSummarizePort | None = None
```

**Backing endpoints (Knowledge Flow).** `POST /documents/tree` (scoped
folder/document listing rendered as indented text, ReBAC-scoped through
`TagService.list_all_tags_for_user` with `owner_filter`/`team_id`, leaves
ReBAC-filtered via `MetadataService`) and synchronous
`POST /documents/{document_uid}/summarize` (steerable `instruction`,
`max_chars` budget, map-reduce for large documents; session attachments
reconstructed from their vectors when the corpus lookup is denied/missing).

**Doctrine.** Same as §8.15: scope parameters only; the adapters
(`DocumentTreeAdapter`, `DocumentSummarizeAdapter`, fred-runtime) capture the
per-turn binding privately through `KfDocumentClient`, stamp the
`owner_filter`/`team_id` seam (tree — the #1899 team-leak guard), and are
wired in `_build_runtime_services`. Transport failures are mapped onto the
SDK-typed `DocumentPortCallError` (timeout flag + HTTP status) so the
capability renders `is_error` tool results without importing the HTTP stack.
`KfBaseClient._request_with_token_refresh` gained an additive per-request
`read_timeout` override (`RuntimeTimeouts.summarize_read`, default 300s) for
the long-running summarize path. First consumer: `document_access`'s
`list_document_tree` + `summarize_document` tools (RFC §10.1).

---

### 8.22 ✅ `AgentCapability.tools()` — Graph agents can use capabilities (2026-07-22)

**What changed.** `AgentCapability` (`fred-sdk/contracts/capability/base.py`) gains
`tools(ctx) -> Sequence[BaseTool]`, the primary, execution-model-agnostic runtime
surface (RFC §3.2); `middleware()` loses its `@abstractmethod` and defaults to
wrapping `tools()` for `create_agent()`. `CapabilityAgentBlock` (`assembly.py`) gains a
`tools` field built directly from `capability.tools(ctx)`, deduped by name with a named
`CapabilityAssemblyError` on a cross-capability name collision. `agent_app.py`'s two
ReAct-only gates (`_effective_capability_ids`, `_build_capability_block`) are removed —
the block is now built identically for `ReActAgentDefinition` and `GraphAgentDefinition`.
`GraphRuntime` (`graph_runtime.py`) accepts `capability_block` and merges
`_adapted_capability_tools(...)` into `runtime_tools`, so a Graph node's
`context.invoke_runtime_tool(...)` reaches a selected capability's tool.

**The adapter.** A capability tool built `@tool(..., response_format="content_and_artifact")`
(the `document_access` convention) silently drops its `ToolInvocationResult` artifact
when invoked through `BaseTool.ainvoke()` with a plain args dict — the shape
`invoke_runtime_tool` uses, versus the `ToolCall` dict `create_agent()`'s real ReAct
loop uses. `_adapt_capability_tool_for_graph` (`graph_runtime.py`) calls the tool's
underlying `.coroutine` directly (bypassing `.ainvoke()`'s response-shape handling
entirely) and re-wraps the result as a bare `ToolInvocationResult` — the one return
shape proven to survive a plain-dict `.ainvoke()` intact. `document_access`'s tool
definition is unchanged; the adaptation lives entirely at this merge seam. A capability
tool name colliding with an MCP-resolved runtime tool name raises
`CapabilityAssemblyError` here too (both name spaces are in scope together for the
first time at this seam).

**Migrated onto `tools()`:** `document_access`, `demo.py`. **Deliberately `middleware()`-only:**
`ppt_filler`, `writable_document` — genuine ReAct-specific hooks. This first landing left
a real gap here (nothing stopped either from being *selected* on a Graph agent, where
they'd silently contribute no tools) — closed the next day, §8.23.

**Proof.** `apps/fred-agents/fred_agents/test_assistant` gained a `document` scenario
(search → HITL confirm/discard → branch) exercised end to end on a real `GraphRuntime` +
`CapabilityAgentBlock`, including the graceful-failure path when the capability isn't
selected. `libs/fred-runtime/tests/test_graph_capability_bridge.py` proves the adapter
is load-bearing with a control test that reproduces the artifact-loss bug when it is
skipped. Validated against three real external agents that predate this change and use
neither `tools()` nor `middleware()`-based capabilities (`dt-agents/aegis`,
`dt-agents/dva_risk_validator_team`, `fred-samples/cvem_watch`) — zero regression.

**Why.** Capabilities were designed ReAct-only (`middleware()` was the only hook); any
`GraphAgentDefinition` selecting a real capability failed loudly. Teams building Graph
agents (deterministic multi-step workflows, not just ReAct loops) had no way to reuse a
shared capability like `document_access` — every Graph agent that needed the same
document search had to hand-roll it via `declared_tool_refs`/`invoke_tool` instead. See
`docs/swift/capabilities/AUTHORING.md` for the authoring-facing summary.

---

### 8.23 ✅ Four correctness gaps in the Graph/capability bridge, closed (2026-07-23)

**What changed.** Independent review (Codex) of §8.22's landing found four real gaps,
verified against the code before fixing:

1. **Silent capability loss on Graph, now loud.** Nothing stopped a Graph agent from
   *selecting* `ppt_filler`/`writable_document` — they'd build without error and
   silently contribute zero tools. `CapabilityManifest` gains
   `execution_models: tuple[Literal["react", "graph"], ...] = ("react", "graph")`
   (`fred-sdk/contracts/capability/manifest.py`); `ppt_filler` and `writable_document`
   now declare `("react",)` explicitly. `_build_capability_block` (`agent_app.py`)
   rejects a `GraphAgentDefinition`'s selection of a declared-ReAct-only capability with
   a named `CapabilityError`, before any turn runs.
2. **`document_access` silently corrupted two of its three tools on Graph.**
   `list_document_tree` and `summarize_document` built their `ToolInvocationResult`
   artifact with no payload (`tool_ref` only) — the real tree/summary text lived
   entirely in `content`, which `_adapt_capability_tool_for_graph` (§8.22) discards by
   design. A Graph node calling either got back a near-empty result. Fixed by mirroring
   `search_documents_using_vectorization`'s pattern: the payload is now duplicated into
   `blocks` (`ToolContentBlock(kind=TEXT, text=...)`). ReAct is unaffected — `content`
   was and remains what the model reads.
3. **`tools(ctx)` called twice per capability per assembly.** The default `middleware()`
   calls `self.tools(ctx)` internally; `build_capability_agent_block` (`assembly.py`)
   also called `capability.tools(ctx)` separately for `block.tools`/HITL binding — two
   independent calls, a latent identity ambiguity for any future stateful `tools()`
   implementation (today's are pure closures, so harmless in practice, but not
   guaranteed by the contract). Fixed: `AgentCapability`'s tool-carrier middleware class
   is now public (`ToolCarrierMiddleware`, exported from
   `fred_sdk.contracts.capability`); `build_capability_agent_block` calls
   `capability.tools(ctx)` exactly once and, when `middleware()` is the unoverridden
   default, builds `ToolCarrierMiddleware` directly from that same result instead of
   calling `middleware(ctx)` a second time.
4. **`demo.py`'s tool was sync**, the one capability tool on the `.func`-only path
   `_adapt_capability_tool_for_graph`'s own comment assumed nothing used — it would have
   silently lost its `ui_parts` artifact under a Graph agent, via the same
   plain-dict-`.ainvoke()` collapse §8.22's adapter exists to work around. Made `async`;
   zero behavior change, no test changes needed.

**Why.** All four are instances of the same failure mode RFC §3.9 names first: a broken
or incompatible capability must suspend/fail loudly, never silently degrade. §8.22's
landing enforced this for the *tools it built*; these four gaps were in what fed that
mechanism (an undeclared incompatible capability, an artifact with nothing in it, an
ambiguous tool identity, an unguarded sync path) — each one a way the "never silently
degrade" rule could be violated without tripping any of the loud checks §8.22 added.

---

### 8.24 ✅ Eight more correctness gaps in the Graph/capability bridge, closed (2026-07-23)

**What changed.** A second independent review (Codex) of §8.23's fixes found that
one of them was itself incomplete, plus seven more real gaps. All verified against
the code before fixing, all fixed the same day:

1. **`tools()` + overridden `middleware()` were either/or, not composed.**
   §8.23's single-call fix (`build_capability_agent_block`) added a
   `ToolCarrierMiddleware` only when `middleware()` was the unoverridden
   default — a capability implementing BOTH `tools()` for plain tools AND
   overriding `middleware()` for a genuine ReAct-only hook (the documented
   pattern) silently lost its plain tools under `create_agent()` (they still
   reached `block.tools`/Graph, but never ReAct's own binding). Fixed: a
   `ToolCarrierMiddleware` is now added whenever `tools()` returns anything,
   AND an overridden `middleware()` is always also called — only the default
   `middleware()` is skipped (it would just rebuild the same thing from a
   second `tools(ctx)` call).
2. **The catalog still offered ReAct-only capabilities to Graph templates.**
   `execution_models` was enforced at assembly (§8.23) but not reflected in
   `GET /agents/templates`' `available_capabilities` — a user could select
   `ppt_filler` on a Graph template in the UI and discover the incompatibility
   only at first launch. `list_agent_templates` (`agent_app.py`) now filters
   per template: a Graph template's `available_capabilities` excludes any
   entry without `"graph"` in `execution_models`.
3. **Capability HITL is still bypassed on Graph (stopgap, not full support).**
   `CapabilityAgentBlock.hitl` is built but `GraphRuntime.invoke_runtime_tool`
   never consults it. No production capability declares an active `HitlSpec`
   today, so this was not yet a live regression — but the RFC presents
   `HitlSpec` as a single, fail-closed, universal gate, which was not true for
   Graph. `_build_capability_block` now refuses (named `CapabilityError`) a
   Graph agent's selection of any capability with non-empty `hitl_specs()`.
   Full Graph HITL support (reconciling Graph's own node-level pause/resume
   with the per-tool gate) is real design work, deliberately deferred — this
   stopgap keeps the "never silently degrade" guarantee intact meanwhile.
4. **`document_access`'s FAILURE path was still degraded on Graph.** §8.23
   fixed the success-path artifacts (tree/summary text duplicated into
   `blocks`); `_document_tool_failure`'s artifact still carried only
   `is_error=True` with no message — a Graph node learned THAT a call failed
   but not WHY, and lost the "you likely passed a name instead of a uid"
   recovery hint entirely. Fixed the same way: the diagnostic message is now
   also in `blocks`.
5. **`invoke_runtime_tool` hardcoded `is_error=False`** on its emitted
   `ToolResultRuntimeEvent` regardless of what the tool actually reported — a
   capability tool that correctly returns `is_error=True` (RFC §3.9: report,
   never raise) had its own runtime trace contradict it. The graph node's own
   `dict` return value was unaffected (it always carried the real
   `is_error`), but the trace/observability layer was lying. Fixed: the event
   now reads `is_error` off the normalized result.
6. **The Graph adapter silently broke on a sync capability tool.** `_adapt_capability_tool_for_graph`
   passed a `.coroutine`-less (sync-only) tool through unchanged, including
   one declared `content_and_artifact` — which would silently lose its
   artifact under Graph exactly like the async case the adapter exists to
   fix, with no `.coroutine` available to adapt it correctly. Fixed: now
   refuses loudly (`CapabilityAssemblyError`) instead of passing it through
   broken. No capability tool in this codebase is sync today (§8.23 made the
   last one, `demo.py`, async) — this closes the general SDK contract gap,
   not just that one instance.
7. **The adapter's 2-tuple unwrap fired for ANY 2-tuple return**, not only a
   declared `content_and_artifact` one — a plain tool whose ordinary return
   value happened to be some unrelated 2-tuple would have its second element
   silently reinterpreted as an artifact. Fixed: gated on the tool's own
   `response_format`.
8. **`McpCapability`'s `agent_instructions` "non-negotiable grounding
   contract" is ReAct-only, but the code said "each runtime consumes the half
   that concerns it"** — true for tools (a separate, already
   execution-model-agnostic path, `FredMcpToolProvider`), false-by-omission
   for the prompt fragment, which only `middleware()` carries and Graph never
   reads. Not fixed (no Graph-side prompt-injection mechanism exists to wire
   it into) — the `_build_capability_block` docstring now says so explicitly
   instead of implying parity that doesn't exist.

**Also regenerated:** `GET /agents/templates`'/`available_capabilities`'
`execution_models` field is additive on `CapabilityCatalogEntry` — the
committed `runtimeOpenApi.ts` and `controlPlaneOpenApi.ts` clients were stale
relative to the backend model (mandatory per this repo's contract-generation
rule) and have been regenerated (`make update-runtime-api`,
`make update-control-plane-api`; both are one-line additive diffs).

**Why.** Same rule as §8.23: a broken or incompatible capability must fail
loudly, never silently degrade (RFC §3.9). Each of these eight was a way that
guarantee could still be violated after §8.23's fixes — an either/or that
dropped a valid authoring pattern, a picker that still offered what the
runtime would refuse, an enforcement gap in a mechanism the RFC calls
universal, a diagnostic that vanished exactly when it mattered most, an event
that misreported its own tool's answer, an adapter narrower than the contract
it claims to implement, and a doc claim broader than the code beneath it.

---

### 8.25 ✅ `execution_models` can no longer be silently forgotten; two more Graph diagnostics fixed (2026-07-23)

**What changed.** A third independent review found that §8.23/§8.24's loud
refusal only covered a capability that EXPLICITLY declared itself ReAct-only
— an author who simply forgot to set `execution_models` on a
`middleware()`-only capability kept the class default (`("react", "graph")`),
which still silently passed the Graph assembly check and still contributed
zero tools. Fixed with a new boot invariant, not a runtime one:
`CapabilityRegistry._validate_execution_models` (new
`InvalidExecutionModelError`) fails pod startup for any capability that
overrides `middleware()` without implementing `tools()` and never explicitly
set `execution_models` — detected via pydantic's `model_fields_set`, which
distinguishes "the author wrote `execution_models=(...)`" from "the field
kept its default," something a plain equality check cannot (writing the
default value explicitly is indistinguishable from never mentioning it).
`McpCapability` is exempt (its tools reach every execution model through
`FredMcpToolProvider`, entirely outside `tools()`/`middleware()`). Two
existing test fixtures (`corp_drive`, `greeter` in
`test_capability_selection_1974.py`) needed the same explicit declaration
`ppt_filler`/`writable_document` already carry — this invariant would have
caught them too. `CapabilityManifest` also now rejects any `execution_models`
that omits `"react"` — there is no Graph-only capability shape (every
Graph-visible tool is also ReAct-visible, since `tools()` feeds both), so a
declaration missing `"react"` cannot correspond to anything the runtime can
build.

Two more diagnostics gaps closed the same review found:
- `document_access`'s 403/404 recovery hint (the "you likely passed a file
  name" guidance) was appended to `message` AFTER `_document_tool_failure`
  had already built the artifact from the shorter pre-hint message — so the
  hint reached ReAct's `content` but not the artifact `blocks` a Graph agent
  keeps. Fixed: the artifact is rebuilt with the final message.
- `invoke_runtime_tool` read `is_error` off the NORMALIZED dict (§8.24's
  fix), which could misclassify a coincidental `is_error`-named key on an
  unrelated (e.g. MCP) tool's business payload as this platform's error
  contract, and never populated `sources`/`ui_parts` on the event at all.
  Fixed: `is_error`/`sources`/`ui_parts` are now read off the raw result
  BEFORE normalization, and only when it is a genuine `ToolInvocationResult`
  instance — never off an arbitrary dict. The span status also now reflects
  `is_error` instead of always reporting "ok" on any non-exception return.

**Why.** Same rule each of §8.22–§8.25 exists to enforce (RFC §3.9): a
capability must fail loudly when it cannot do what's asked of it, never
silently degrade. §8.23/§8.24 closed the cases where a capability KNEW it
was incompatible; this round closes the case where the platform itself
couldn't tell an author had never made that declaration at all, plus two
more spots where a real diagnostic still silently evaporated on the one path
(Graph) that only ever sees the artifact half of a tool's answer.

---

### 8.26 ✅ `execution_models` boot check closed on the VALUE, not the declaration; graph KPI status fixed (2026-07-23)

**What changed.** §8.25's boot invariant only caught a `middleware()`-only
capability that never MENTIONED `execution_models` — one that explicitly
wrote `execution_models=("react", "graph")` still passed every check
(boot, manifest validator, Graph assembly) while still having zero
`tools()` output, reproducing the exact silent no-op the whole chain of
fixes exists to prevent. `CapabilityRegistry._validate_execution_models`
(`InvalidExecutionModelError`, renamed from `UndeclaredExecutionModelError`)
now checks the VALUE: any `middleware()`-only capability whose
`execution_models` contains `"graph"` fails pod boot, whether that value
came from the class default or an explicit declaration.
`model_fields_set` is now used only to make the error message precise
("never declared" vs. "declared, but to the wrong value"), not to decide
whether to raise.

Also fixed: `invoke_runtime_tool`'s KPI timer (`_graph_phase_timer`) never
captured its `kpi_dims`, so a capability tool reporting failure via
`ToolInvocationResult(is_error=True)` (never raising) recorded
`status=ok` in the metric — the timer's own default when no exception
propagates. Mirrors the canonical `invoke_tool` pattern now:
`kpi_dims["status"] = "error"` when the typed result reports failure.

**Why.** Same rule as §8.22–§8.25: a capability's incompatibility with
Graph must be impossible to miss, at every layer — including when an
author writes the wrong value on purpose, not just when they forget to
write anything. And a failing tool call must look like a failure
everywhere it's recorded — the trace event (§8.24), the span (§8.25), and
now the KPI metric a dashboard or alert would actually query.

---

### 8.27 ✅ Tool-failure recovery notice added to the ReAct/Deep system prompt (2026-07-23)

**What changed.** The §8.12 suffix chain gains one more hard-invariant
suffix. `fred_runtime.react.react_prompting.build_tool_failure_recovery_suffix()`
is now composed in `compose_system_prompt` right after
`build_global_base_prompt_suffix()` and before `runtime_suffixes`:

```
system_prompt
  + tool_suffix
  + build_guardrail_suffix(definition)
  + build_global_base_prompt_suffix()
  + build_tool_failure_recovery_suffix()        # NEW
  + *runtime_suffixes
  + build_context_prompt_suffix(binding, agent_id=agent_id)
  + build_attachment_context_suffix(binding)
```

The suffix tells the model that when a tool call fails or returns an
error/troubleshooting message, it must never surface that raw text as the
final answer — it should retry with corrected arguments, or answer from
context already gathered if that suffices, and only report a failure to the
user after reasonably exhausting recovery options.

**Why.** Found via eval run `eval-run-3ba7e559` (`fred.github.assistant`,
case `case-39a41df8`, issue #2073): `summarize_document`
(`document_access/capability.py:781-867`) catches its own exception and
returns a recovery message as an ordinary tool result instead of raising.
The agent surfaced that raw message as its final answer instead of retrying
or falling back to four already-successful search results that covered most
of the expected facts (`AnswerRelevancyMetric=0`, `ContextualRecallMetric=0.25`,
despite `FaithfulnessMetric=1.0` / `ContextualPrecisionMetric=1.0` confirming
retrieval itself was fine). Nothing in the shared ReAct prompt previously
told the model how to behave after a tool failure. This is prompt-only:
whether `summarize_document`/`list_document_tree` should raise instead of
returning error text as a normal result is a separate, larger structural
fix (tracked in a follow-up issue linked from #2073), not addressed here.

---

### 8.28 ✅ Pod-side execution/content checks moved off public-discovery `CAN_READ` (issue #2146, PR #2147, 2026-07-29)

**Supersedes the `CAN_READ`/`can_read` wording in §8.9–§8.11 and the earlier
top-of-document callouts** — accurate for their own dates, superseded now.

**What changed.** TEAM-09/TEAM-10 (`FRED-TEAM-CONFIG-RFC.md` §5.1.1/§5.1.2)
deliberately widened `TeamPermission.CAN_READ` to include any authenticated
user via the `public` marketplace-discovery relation, granted unconditionally
on every `PUBLIC`-visibility team (the default for every team at the time;
new teams default to `PRIVATE` since 2026-08-26, #2433). The OpenFGA
model (`schema.fga`) already anticipated this and kept `can_use_team_agents`
strictly `team_member`-only, but three pod-side/runtime call sites written
before that split still checked the wide `CAN_READ`, so a non-member visiting
a public team could execute its agents or read tool-call context, not just
see that the team exists:

1. `_authorize_execution_or_raise` (agent_app.py, §2.2/§2.4) — turn-start
   managed-execution authorization.
2. `ToolObservabilityMiddleware._reverify_team_authorization`
   (`tool_observability.py`, §8.9-era per-tool-call reverify) — re-checked
   the same wide permission on every tool call after turn start.
3. The OpenAI-compatible `/v1/chat/completions` surface
   (`openai_compat_router.py`) — a separate gate duplicating (1) rather than
   funneling through it, so it carried the same gap independently.

All three now require `TeamPermission.CAN_USE_TEAM_AGENTS`. The equivalent
control-plane-side leak (prompt-library content reachable via the same
over-wide default) was fixed in the same PR in
`control_plane_backend/product/api.py` (`get_team_prompts`,
`get_context_prompts_early`, `get_team_prompt`), mirroring the precedent
`post_prepare_execution` in the same file had already set.

**Not changed by this fix**: `get_team_agent_instance_runtime` stays on
`CAN_READ` deliberately — it returns instance config only, never prompt
content, so public-discovery visibility is the correct (and intended) gate
for it. `product/teams/service.py`'s `_list_teams` (`GET /teams`) also stays
on `CAN_READ` — whether every public team should appear in a non-member's
team list is an open product question, not folded into this fix.

**Verification.** `make validation-report` against a live local stack: 190
passed/35 failed/0 error before, 205 passed/20 failed/0 error after — the
remaining 20 are exclusively the `GET /teams` open question above.

### 8.29 ✅ Reasoning is declared, projected, and enforceable — REASON-01 phase 1 (issue #2166, 2026-07-29)

Levels 1 and 2 of REASON-01 (declare aptitude, platform activation). Before this, reasoning was
one untyped YAML line (`ModelConfiguration.settings.reasoning_effort`, an opaque
`Dict[str, Any]`): nothing in Fred knew a profile reasoned, and changing it
needed a redeploy.

**Runtime contract changes:**

1. **`ModelProfile.supports_thinking: bool = False`**
   (`model_routing/contracts.py`) — declared APTITUDE, per profile. Additive
   with a safe default, so every existing catalog keeps loading. Declaring a
   reasoning setting *without* it now **fails at pod boot** with a named error
   (RFC §4.3): the state is always an authoring mistake, and tolerating it
   silently is what made the current situation invisible.
2. **`_ModelCatalogEntry.thinking_profile_ids`** (`agent_app.py`,
   `GET /agents/models-catalog`) — the `supports_thinking` subset of
   `profile_ids`, derived inside the existing `(provider, name)` grouping
   (RFC §5.3). Aptitude stays per profile, where it is true; the admin toggle
   is keyed per model, where the capability id space is. Never authored twice.
   Reaches control-plane on `CapabilityCatalogEntry.model_thinking_profile_ids`,
   the same join `model_profile_ids` already carries.
3. **`RuntimeContext.reasoning_enabled_model_ids: list[str] | None`**
   (fred-sdk, Group C) — the platform admin's activation, snapshotted at session
   prep and forwarded per turn, the same three-hop channel and lifecycle as
   `chat_default_profile_id` (§8.32 above). **Not** a
   per-turn lookup.
4. **`RoutedChatModelFactory.build_for_chat` strips reasoning settings**
   (`model_routing/provider.py`) when the resolved model is absent from that
   list — at CLIENT CONSTRUCTION, not by declining to add them (RFC §5.6.2).
   The distinction is the whole point: `reasoning_effort` is already in
   `settings` by then, so a toggle that only skipped *adding* it would be
   decorative — the `allow_parallel_calls` failure recorded in
   an incident lever's name on it.
   `tests/test_model_reasoning_enablement.py` proves it against the real
   `ChatOpenAI` request payload, both directions.

**Semantics worth reading twice:** `reasoning_enabled_model_ids` is
**off by default** and is the OPPOSITE of `usable_model_ids` in this respect —
there `None` means "unrestricted", here `None` and `[]` both mean "no model
reasons" (RFC §5.6). A model reasons only by being named.

**Not additive on upgrade.** A deployment running reasoning through YAML alone
stops reasoning until an administrator switches it on (RFC §5.6.1) — on this
branch that is `chat.mistral.small`, the current `chat` default. Release-noted,
not silent. The safe direction, and deliberately so: §8.37 measured 10/10
turns with duplicate tool calls on that exact profile, and a live
per-model off switch is the only lever that stops a reasoning-induced
incident without a redeploy.

**Untouched**: per-team model authorization. Reasoning has no subject, so it is
not a permission and writes no ReBAC tuple (RFC §5.1/§5.4). Levels 3 (per-agent
config) and 4 (composer control) are phase 2 and not implemented here.

---

### 8.30 ✅ Per-agent and per-question reasoning — REASON-01 phase 2 (issue #2166, 2026-07-30)

Levels 3-4 of REASON-01 (per-agent and per-question reasoning), plus its three
tool-loop-safety preconditions. Builds on §8.29 (levels 1-2); read that first.

**Reasoning is not a capability** (RFC §15, Amendment A). It was built as one, as
§7 specified, and withdrawn before release: an agent does not *use* reasoning the
way it uses a tool, so the Tools tab was the wrong place to enable it. What ships:

| Level | Where it lives |
| ----- | -------------- |
| 3 — the agent offers it | `AgentTuning.reasoning_enabled` (fred-sdk) — a plain agent property, edited in the **General** section of the agent form |
| 4 — the user chooses per question | `RuntimeContext.reasoning` — a platform chat option travelling per turn like `search_policy`/`search_rag_scope` |

**`RuntimeContext.reasoning` is tri-state, and the distinction is load-bearing:**

- `None` — the agent never offered the choice; levels 1-2 decide alone. The
  default, and the pre-REASON-01 behaviour for every agent that does not opt in.
- `False` — the agent offers it and the user declined: this turn must not reason
  even on a model whose reasoning is enabled platform-wide.
- `True` — permission, never a guarantee: level 2 stays a ceiling (§5.3).

Collapsing `None` into `False` would silently suppress reasoning everywhere.

**One enforcement point for every level.** `RoutedChatModelFactory.build_for_chat`
strips the reasoning settings when `not platform_allows or turn_declined`, on
`ModelConfiguration.settings` **before the client is built** — the same place and
the same primitive (`without_reasoning_settings`) §8.29 already used for level 2.
There is no second mechanism, no built client to patch, and nothing that can
drift out of step with level 2.

**Level 3 reaches that point as part of the ceiling, computed pod-side**
(2026-07-30 fix, RFC §14.5). `_iterate_runtime_event_payloads` (`agent_app.py`)
assembles `RuntimeContext.reasoning_enabled_model_ids` as `level 2 AND level 3`:

```python
reasoning_enabled_model_ids=(
    ctx.get("reasoning_enabled_model_ids")
    if tuning is not None and tuning.reasoning_enabled
    else []
),
```

The list rides the request; `tuning` is resolved server-side from the managed
instance, so a client cannot open a gate the agent's author left shut. Absent
tuning (agent-to-agent invocation) means no author enabled it — empty ceiling.
Do not "simplify" this back to a straight `ctx.get(...)`: the first cut gated
only the composer control on level 3, and agents with reasoning off reasoned
anyway, invisibly, because the UI that would have shown it is precisely the
toggle that was correctly hidden.

This is why the RFC's §7.3 `.bind`-vs-`model_copy` question (and the probe that
settled it, §12 q2) no longer applies: both were needed only because a capability
middleware runs *after* the client exists. It is also why levels 3-4 are **not**
ReAct-only as §7.1 accepted — with no `middleware()`-only capability, the boot
rule that forced that exclusion does not apply, and a Graph agent's model call
goes through the same factory.

**§9 preconditions, all three closed:**

1. `max_tool_calls_per_turn = 12` on all five ReAct agents
   (`apps/fred-agents/fred_agents/tool_pacing.py`). `ToolCallLimitMiddleware` was
   wired but inert since nothing set the value (§8.37).
   Applies to every turn, not only reasoning ones — RFC §14.4 explains why, and
   why a capability-contributed cap would break `frame.py`'s documented
   `after_model` ordering against the HITL gate.
2. `TOOL_REPETITION_RULE` added to `build_runtime_tool_prompt_suffix`
   (`react_tool_binding.py`). Amendment C §C.7 measured that the protection was
   real but **accidental** — carried by the #2073 tool-failure suffix, with
   nothing tying it to reasoning drift. Now explicit, greppable, and tied by two
   tests in `test_react_prompting.py`.
3. `ToolSelectionPolicy` docstrings corrected (`fred_sdk/contracts/models.py`):
   the cap IS enforced (untrue since `frame.py` wired it), and
   `allow_parallel_calls` is now documented as declarative-only.

---

### 8.31 ✅ Reasoning blocks are persisted to session history (2026-07-31)

§8.6/§8.31 specify how reasoning is *surfaced* and never what
becomes of it afterwards — its own §C.9 names the gap. The consequence was
user-visible: reasoning streamed into the trace, then vanished on page reload,
because `_write_turn_history` (`agent_app.py`) mapped `tool_call`, `tool_result`,
`awaiting_human`, `node_error` and `final`, and let all three `thought_*` kinds
fall through. `Channel.thought` existed in the stored schema since fred-core and
was written by nothing.

**`thought_*` → one `Role.assistant / Channel.thought` row per reasoning block.**
The envelope matches what the live stream builds client-side
(`useChatSse.ts`) — same role, same channel, same `metadata.extras` keys
(`thought_id`, `phase`, `title`, `source`, `conclusion`, `duration_ms`) — because
the chat UI renders streamed and reloaded rows through one path
(`traceUtils.thoughtExtras()`). Frontend, schema, DB column and read endpoint all
already accepted this shape; only the writer was missing.

Four rules, each of which is a bug if reversed:

1. **The rank is reserved at `THOUGHT_START`, not at `THOUGHT_END`.** A
   model-native block opens on the first reasoning token and closes only at the
   first answer delta (§7.3), so it brackets every tool call of the turn. Ranking
   it at close would file the reasoning *after* the tools it preceded, and a
   reloaded trace would not match what the user watched.
2. **`tool_use` blocks are not persisted.** The runtime opens one per tool call
   (Amendment A, Layer 1) and the UI has hidden them since Amendment B — the
   call/result combo row already carries what ran, how it went, how long it took.
   Storing them would file up to `max_tool_calls_per_turn` (12) content-free rows
   a turn.
3. **`streaming_delta` is never stored.** It is the live "still running" flag; a
   persisted block is complete and would otherwise pulse forever on reload.
4. **Blocks left open by a truncated turn are still written** (the live UI closes
   them itself on `final`), but a block with neither text nor conclusion is
   dropped — an empty reasoning card reads as a rendering bug.

`extras` is reached through `ChatMetadata.model_validate({...})`: it is not a
declared field, `extra="allow"` exists for exactly this, and a keyword argument
does not type-check.

This is display persistence only. It does **not** change what is replayed to the
model — see §C.9 and the note below.

---

### 8.32 ✅ `RuntimeContext` gains team routing policy fields (TEAM-05, #2118, 2026-07-27)

**2026-08-16 — chat-only drift enforcement (#2365).** A team-selected profile
whose declared capability is not `chat` now raises
`TeamRoutingProfileDriftError`; it no longer falls through silently to the pod
chat default. Control-plane prevents new incompatible writes through the
pod-authored chat-profile projection, while this runtime check covers stored
legacy state and deployment drift.

**What changed.** `RuntimeContext` (`libs/fred-sdk/fred_sdk/contracts/context.py`)
carries two fields threaded from control-plane at session-prep time, the
same three-hop channel `context_prompt_text` already uses:

- `chat_default_profile_id: str | None` — the team's default chat model
  profile, or `None` to fall through to the runtime's own default.
- `agent_profile_overrides: dict[str, str] | None` — `agent_id -> profile_id`,
  a flat per-agent override map (no rule list, no operation/purpose
  matching — a duplicate key simply cannot be represented in a `dict`, so
  there is nothing to disambiguate).

Both are a **session-prep snapshot, not a per-turn lookup** — resolved once
by `routing_policy/service.py::resolve_execution_routing_snapshot` when
`ExecutionPreparation` is built, not re-read from control-plane on every
turn. `fred-runtime`'s `resolve_team_override`
(`libs/fred-runtime/fred_runtime/model_routing/resolver.py`) is consulted by
`RoutedChatModelFactory.select` only when the pod's static YAML
`agent_profile_overrides` (`models_catalog.yaml`) has no entry for this
agent — that static map stays the pod operator's escape hatch and always
wins. It is a two-step fallback chain, not a
specificity-scored matcher: `agent_profile_overrides.get(agent_id)` first,
else `chat_default_profile_id`, else `None`. A resolved profile id unknown to
the pod, or declaring a non-chat capability, fails closed
(`TeamRoutingProfileDriftError`) rather than silently selecting the pod
default. A resolved concrete model that is no longer team-enabled fails with
`ModelNotUsableError`; this is runtime enforcement of the existing access
decision, not profile substitution.

Since #2365 (`RUNTIME-EXECUTION-CONTRACT.md` §8.55), a third, trusted field —
`BoundRuntimeContext.platform_chat_model_binding` — sits above both of these
in precedence and is resolved fresh every turn rather than snapshotted; see
§8.55 for why it needs a different trust model than the two fields above.

Product/data/API contract (data model, resolution, authorization, frontend
surface): `CONTROL-PLANE-PRODUCT-CONTRACT.md` §37.

---

### 8.33 ✅ A pod whose durable SQL storage cannot be reached must never finish starting (2026-07-31)

**What changed.** `PodApplicationContext.initialize_sql()`
(`libs/fred-runtime/fred_runtime/app/context.py`) used to catch every
exception from engine/checkpointer/history-store construction, log
`"running stateless"`, and return — leaving `checkpointer`/`history_store`
at `None` with no signal to the FastAPI lifespan. Because SQLAlchemy's async
engine is lazy (construction never opens a connection), an unreachable or
misconfigured Postgres passed silently: the pod finished startup, passed its
`tcpSocket` readiness probe, and served conversation turns with no
persistence — invisibly, and only for whichever replica lost the race.

`initialize_sql()` now (1) lets construction failures (missing
`FRED_POSTGRES_PASSWORD`, missing `host`/`database`/`username`) propagate
instead of swallowing them, and (2) runs one bounded (5s) `SELECT 1` against
the engine right after construction — the only point that actually proves
connectivity — before wiring the checkpointer/history store. Either failure
now aborts the FastAPI lifespan, so the pod process exits without ever
reaching `Running`; Kubernetes never marks it `Ready` regardless of probe
type, and the two other invariants already enforced in `agent_app.py`'s
lifespan (checkpointer and history store must both come from the same
`initialize_sql()` call, and neither may be set without the other) still
hold on top of this.

There is no supported "stateless" pod mode today — every real
`AgentPodConfig.storage.postgres` (dev SQLite via `sqlite_path`, production
Postgres) intends durable storage; SQLite-for-dev is a backend choice, not
an opt-out. This change does not introduce one.

**Not done, deliberately deferred:** dedicated `/healthz` + dependency-aware
`/ready` HTTP endpoints (the pattern `knowledge-flow-backend` and
`control-plane-backend` already use) and switching fred-agents' Helm probes
from `tcpSocket` to `httpGet`. The fail-fast boot behavior above already
satisfies the production invariant without either; closing the small
residual race window (a `tcpSocket` probe could see the port briefly open
during the ≤5s connectivity check before the process exits) is left as
follow-up if it proves necessary in practice.

---

### 8.34 ✅ ReAct/Deep prompt composition no longer depends on the process-global runtime context (2026-07-31)

**What changed.** `ReActRuntime.build_executor` and `DeepAgentRuntime.build_executor`
(`libs/fred-runtime/fred_runtime/react/react_runtime.py`,
`libs/fred-runtime/fred_runtime/deep/deep_runtime.py`) fetched the KPI writer
via `get_runtime_context().get_kpi_writer()` — a bare process-global lookup —
inline during executor construction, instead of through the existing
`RuntimeServices` dependency-injection container both runtimes already
receive. Any standalone unit test of `build_executor()` (not routed through
`agent_app.py`'s lifespan-initialized global context) raised
`RuntimeError: RuntimeContext has not been initialized.` `RuntimeServices`
(`libs/fred-sdk/fred_sdk/contracts/runtime.py`) gains a `kpi_writer:
BaseKPIWriter | None` field, populated in `agent_app.py`'s
`_build_runtime_services` from the same `runtime_config.kpi_writer` already
in scope there; both `build_executor` methods now read
`self.services.kpi_writer` instead of the global. `kpi=None` is the
pre-existing, already-`None`-safe default for every downstream KPI
consumer (`TracingKpiMiddleware`, `ToolObservabilityMiddleware`,
`build_tool_loop_compiled_react_agent`), so no behavior changed for any
lifespan-initialized production request — only the composition path's
testability changed. Confirmed by 3 previously-failing prompt-injection unit
tests going green, deterministically, independent of test-file collection
order (a `test_deep_agent_middleware.py` test was separately found to leak
`set_runtime_context(...)` into the shared process-global for the rest of
the pytest session with no teardown; that call is now unnecessary and was
removed rather than patched with a reset).

---

### 8.35 ✅ Reasoning-enabled model list is resolved fresh per turn, not trusted from the request (2026-08-01)

**What changed.** Of the three fields riding the client-forwarded request
context that mirror a control-plane session-open snapshot (routing default
profile, routing override rules, reasoning-enabled model ids), only the third
is a genuine admin control — the other two are a frugality/comfort choice
already bounded by the per-turn model-authorization check, so they are left
as-is. Reasoning is different: it is the admin's platform-wide kill switch,
and a client that keeps forwarding a session-open copy could keep reasoning
active past the moment an admin switched it off.

`ManagedAgentRuntimeBinding` (control-plane, `product/schemas.py`) and
`_ResolvedAgentInstance`/`_ResolvedExecutionTarget` (fred-runtime,
`app/agent_app.py`) gain a `reasoning_enabled_model_ids` field, populated by
`get_runtime_binding_for_team` from the same store `prepare_execution` reads.
This call already happens once per turn to resolve the instance's tuning and
team-capability settings, so this adds one cheap store read to an existing
round trip rather than a new one. `_iterate_runtime_event_payloads` now takes
`reasoning_enabled_model_ids` as a parameter sourced from this resolved
target instead of reading it off the caller-supplied context.

**Left alone, on purpose:** `chat_default_profile_id`/`agent_profile_overrides`
keep riding the client-forwarded context unchanged. The per-turn model
`can_use` check already stops a request from reaching a model the team isn't
authorized for, whatever routing profile it names — narrowing that further
was assessed and rejected as disproportionate for what is a cost/comfort
lever, not an access boundary. `platform_chat_model_binding` (§8.55, added
#2365) is the fourth field in this family and does **not** get the same
pass: unlike a team's own routing choice, it is the platform operator's
authority over what a deployment can even reach, so it gets the strictest
treatment of any of the four — never client-forwarded at all, not just
resolved fresh.

---

### 8.36 ✅ Native `anthropic` model provider — RUNTIME-07 (2026-07-21)

**What changed.** `fred-core`'s chat model factory gained a seventh
`ModelProvider`, `anthropic` (`langchain_anthropic.ChatAnthropic`), alongside
`azure-apim`, `azure-openai`, `ollama`, `openai`, `vertex-ai`, and
`vertex-ai-model-garden`. It targets both direct Anthropic API access and an
Anthropic-native gateway (e.g. a LiteLLM router exposing the Anthropic
Messages API at a custom base URL) — previously the only path to such a
gateway was shimming it through the `openai` provider against the wrong API
surface (OpenAI Chat Completions instead of Anthropic Messages).

**As-built auth (diverges from the original proposal):** a single
`anthropic_api_key` accepts **either** `ANTHROPIC_API_KEY` or
`ANTHROPIC_AUTH_TOKEN` (`os.getenv("ANTHROPIC_API_KEY") or
os.getenv("ANTHROPIC_AUTH_TOKEN")`), sent as the standard `x-api-key` header
in both cases. The originally proposed split — `ANTHROPIC_AUTH_TOKEN` forcing
a distinct `Authorization: Bearer` header for gateway mode — was not built;
one code path covers both direct-API and gateway deployments. `base_url`
resolves from an explicit `settings.base_url`, else `ANTHROPIC_BASE_URL`, else
the SDK default.

**Unchanged:** `vertex-ai-model-garden` with `model_family: anthropic`
(Google ADC auth) stays as a separate, still-supported path — this provider
does not replace it. No frozen contract field changed; this is a new enum
value and a new factory branch only.

---

### 8.37 ✅ Reasoning threads within an open tool loop; tool-loop safety guardrails (RUNTIME-04/05, 2026-07-31)

**Supersedes §8.6's "collapse-only" description of `strip_reasoning_from_history`.**
That helper originally stripped provider reasoning blocks from every replayed
assistant message, unconditionally — safe against Mistral's HTTP 422 on
replayed raw reasoning, but it also meant the model "forgot" its own
reasoning between tool-loop steps and re-derived the same plan, re-issuing
byte-identical tool calls (measured: 10/10 turns with a duplicate call on
`mistral-small` + `reasoning_effort: high`, confirmed independently across
re-measurements).

**Fix — thread within the open turn, strip only across turn boundaries.**
`CheckpointHygieneMiddleware` now calls
`thread_reasoning_within_open_turn`: reasoning content is kept, re-homed as
ordinary assistant text (prefixed `RECALLED_REASONING_PREFIX`), for any
message still inside the current open tool loop; it is dropped only once
the turn closes (`final` reached) — closed-turn reasoning is never replayed
into a later turn's context. There is no protocol-level channel that marks
re-homed reasoning as privileged — it is ordinary `content`, the same field
a user-facing reply is written into, so any consumer reading a checkpointed
transcript must not assume a stronger separation than a text prefix
convention provides. Measured empty risk (0/8 trials) of the model
narrating or repeating this recalled text back to the user, but the
channel itself carries no guarantee against it.

**Tool-loop safety guardrails, permanent (not reasoning-specific — apply to
every ReAct turn):**

- `max_tool_calls_per_turn = 12` on all five ReAct agents
  (`fred_agents/tool_pacing.py`) — a real cap, not a documented-but-inert
  default; hitting it degrades the answer (`exit_behavior="continue"`)
  rather than erroring the turn.
- `TOOL_REPETITION_RULE`, explicit and tested, in
  `build_runtime_tool_prompt_suffix` (`react_tool_binding.py`) — previously
  a symptom of the tool-failure-recovery suffix (unrelated issue #2073) was
  the only thing suppressing repeat calls in production, with nothing
  tying that protection to reasoning drift or guaranteeing it would survive
  a rewording.

**Not closed by this work:** reasoning continuity across a **Graph** agent's
node boundaries (Graph authors use `context.thinking()` directly, a
different execution model); token cost of re-homed reasoning (it now
consumes context tokens the previous strip-everything behavior did not).

---

### 8.38 ✅ `HumanInputRequest.pending_calls` — batched HITL confirmation + trace correlation (2026-08-03)

**Problem, part 1 (trace correlation).** A HITL-gated tool call's
`ToolCallRuntimeEvent` streams the instant the ReAct model node commits its
`AIMessage.tool_calls` — a separate, earlier LangGraph step than
`FredHitlMiddleware.aafter_model`'s own `interrupt()`. The chat UI's
`statusForEntry()` had no way to tell that call apart from one already
executing: both are a `tool_call` with no `tool_result` yet, so the trace row
read "running…" (and the trace header "Thinking…") before the user had even
seen, let alone answered, the "Confirm tool execution" prompt (found
live-testing `document_access`'s `summarize_document` gate, #2177).

**Problem, part 2 (one prompt per call).** The original gate raised one
`interrupt()` per gated tool call, sequentially — so "summarize every
document in this folder" meant one confirmation click per document. This was
pure friction, not extra safety: cancelling any ONE call already skipped the
WHOLE batch (`FredHitlMiddleware`'s established cancel semantics — no tool of
the batch executes), so the outcome was already all-or-nothing regardless of
how many times the human was asked.

**What changed.** `FredHitlMiddleware.aafter_model` now runs in two passes:
collect every tool call the gate decides needs approval (`GatedToolCall`,
`fred_runtime/react/middleware/hitl.py`), then raise exactly ONE combined
`interrupt()` covering all of them — proceed executes the whole batch,
cancel skips it entirely, identical semantics to before, asked once instead
of N times.

`HumanInputRequest` gains a new field, `pending_calls:
tuple[PendingToolCall, ...]` (`fred_sdk/contracts/runtime.py`) — one entry
per gated call (`tool_call_id`, `tool_name`, `args_preview`), replacing the
single-call `metadata.tool_name`/`tool_args_preview` keys entirely (no other
caller read them — grepped clean before removing). This IS a wire-shape
change (a new typed field, not an addition to the open `metadata` bag), so
both `libs/fred-runtime`'s OpenAPI spec and the frontend's generated
`runtimeOpenApi.ts` were regenerated (`make update-runtime-api`) — see the
new `PendingToolCall` type there.

The approval `question`/`title` text is generic ("Confirm 3 tool
executions"/lists the N tool names) rather than merging per-call
`HitlSpec.question` overrides (#1973) — no in-tree capability sets one today,
and there is no sound way to combine N arbitrary override sentences; a
capability's override still applies verbatim whenever its call is the only
one gated.

`useChatSse.ts`'s `awaiting_human` handler forwards `request.pending_calls`
into the frontend's `AwaitingHumanEvent.payload` (the legacy `HitlPayload`
type already has an open `[key: string]: any` index signature, so no change
needed there). The trace-status derivation
(`traceUtils.statusForEntry`/`traceSummary`) takes `pendingToolCallIds:
string[]` instead of a single id, so every call in a batch reads "awaiting
confirmation" simultaneously, not just the first. See `COMPONENT-UX.md`'s
`TraceEntryRow` entry for the UI side.

---

### 8.39 ✅ HITL resume bound to a unique interrupt occurrence — #2216 P1 (2026-08-04)

**Current behavior.** A ReAct V2 HITL resume is authorized and executed
through four independent layers, each closing the same class of bug — a
stale or duplicate resume response silently landing on the wrong, or an
already-resumed, HITL prompt:

1. **Wire contract.** `RuntimeExecuteRequest.checkpoint_id` (legacy Graph V2
   — a real checkpointer-storage id) and `.interrupt_id` (ReAct V2 —
   LangGraph's own `Interrupt.id`) are mutually exclusive, enforced by a
   pydantic validator (`fred_sdk.contracts.execution._validate_execution_target`)
   — never both set, and `interrupt_id` is meaningless without
   `resume_payload`. This is what lets layer 2's checkpoint lookup double
   as "the thread's latest checkpoint" for every ReAct V2 request, never a
   client-chosen historical one.
2. **Read-only admission gate** (`agent_app._validate_session_checkpoint_access`,
   runs before session ownership, OpenFGA, and target resolution): extracts
   every currently pending `"__interrupt__"` id on the thread's latest
   checkpoint (`_pending_react_v2_interrupt_ids` — collects ALL matching
   ids, not just the first) and requires the client's `interrupt_id` to
   match one of them exactly — missing, empty, malformed, unknown,
   cross-thread, or stale all fail closed with `409 Conflict`. Never
   mutates anything.
3. **Targeted LangGraph resume, mandatory** (`react_message_codec.graph_input_from_react_input`):
   `Command(resume={interrupt_id: payload})`, never the scalar
   `Command(resume=payload)` form. LangGraph resolves the map key against
   the pending task's own `Interrupt.id` and simply re-raises the SAME
   interrupt when no task matches, so even if the pending interrupt
   changed between layer 2 and layer 3 (two separate operations) a
   decision can never land on the wrong occurrence. A resume without
   `interrupt_id` raises — no scalar fallback exists.
4. **Durable, atomic, fenced claim** (`FredSqlCheckpointer`'s
   `checkpoint_hitl_claim` table, key `(thread_id, checkpoint_ns,
   interrupt_id)`, with `checkpoint_ns` always `""` for ReAct V2 — see
   §8.61), acquired as LATE as possible — inside
   `agent_app._iterate_runtime_event_payloads`, immediately before
   `executor.stream(...)`, never in the read-only gate. State machine
   `claimed -> started -> consumed`, every operation fenced by an opaque
   `claim_token` so a caller that lost ownership can never affect the
   current owner's row:
   - `aclaim_hitl_resume` — `INSERT ... ON CONFLICT DO UPDATE ... WHERE
     <stale>`, mints a fresh token, moves to `claimed`. Only a `claimed`
     row past `_HITL_CLAIM_TTL_SECONDS` (default 60s) is eligible to be
     superseded.
   - `astart_hitl_resume` — atomically confirms the caller still owns the
     row and moves to `started`, immediately before graph invocation.
     `started` has **no time-based expiry** — a long-running turn is never
     superseded merely because wall-clock time passed.
   - `aconsume_hitl_resume` — best-effort, audit-only terminal marker after
     a successful turn; `started` alone already permanently blocks a
     duplicate regardless of whether this ever runs.
   - `arelease_hitl_resume` — frees a still-`claimed` row on a
     pre-invocation failure only; never releases a `started` row.
   - Claim timestamps use the DATABASE's own clock (`_db_now`), not the
     calling process's, so replica clock skew cannot incorrectly steal or
     fail to steal a lease.
   Deliberately a separate table from `langgraph_checkpoint_write`: that
   table is LangGraph-owned semantic storage read back as `pending_writes`,
   and an artificial row there would corrupt `pending_write_count` /
   checkpoint-administration semantics
   (`test_hitl_claim_rows_never_appear_in_pending_writes`). `adelete_thread`
   also purges `checkpoint_hitl_claim` rows for the deleted thread.

**Native LangGraph ownership vs FRED's admission boundary.** LangGraph owns
`Interrupt.id`, interrupt persistence, pending graph state, and targeted
resume routing (layer 3). FRED owns exactly three things: HTTP-layer
authorization (layer 2), cross-stack transport of `interrupt_id` (CLI,
frontend, OpenAPI contract), and the minimum durable multi-replica
admission guard LangGraph itself has no opinion on (layer 4) — FRED never
mints a parallel occurrence identity of its own. `Interrupt.id` is
`xxh3_128_hexdigest(task_checkpoint_ns)` and is **NOT universally
occurrence-unique**: two `interrupt()` calls within the SAME LangGraph task
share it, matched by call order instead
(`test_langgraph_interrupt_id_semantics.py` pins this against the installed
LangGraph version). #2216 relies on a narrower, FRED-specific fact instead:
`FredHitlMiddleware.aafter_model` has exactly one `interrupt()` call site,
invoked at most once per task, so two DISTINCT FRED HITL occurrences
always land in different tasks and always get different ids — proven
against FRED's real tool loop
(`test_hitl_resume_two_sequential_prompts_get_different_interrupt_ids`)
and, end to end against a real compiled agent + `FredSqlCheckpointer` +
the actual emitted `Interrupt.id` + `graph_input_from_react_input`, by
`test_hitl_resume_langgraph_integration.py`.

**Guaranteed properties** (see `FredSqlCheckpointer.aclaim_hitl_resume`'s
docstring for the authoritative version):

- a stale response for an earlier interrupt (A) can never resume a later
  one (B) — enforced independently by layer 2's exact-id match and layer
  3's targeted resume-map matching
- no two healthy requests can both hold a live claim (`claimed` or
  `started`) for the same occurrence at once — proven same-process (N-way
  race via `asyncio.gather`), cross-replica (two independently created
  `AsyncEngine`s sharing one file-backed SQLite database —
  `test_concurrent_claims_across_separate_checkpointer_instances_have_one_winner`),
  and end-to-end through real concurrent HTTP requests with a tool-call
  counter (`test_concurrent_duplicate_resumes_execute_the_tool_at_most_once`)
- an abandoned `claimed` row (setup failed, or the owning process died
  before confirming start) is recoverable after the short TTL
- a `started` row is held for the life of that invocation attempt with no
  time-based reclaim; a stale owner (superseded after TTL expiry) can never
  delete, restart, or consume a newer owner's row

**Cancellation / crash limitations.** Exactly-once EXTERNAL tool side
effects are explicitly NOT guaranteed once a claim reaches `started`, for
ANY of: pod/process crash, task cancellation, an SSE/browser disconnect,
the frontend's `AbortController` firing, or cancellation landing after
graph invocation started but before the claim is marked `consumed`
(`test_cancellation_after_start_leaves_the_claim_stuck_not_released`
proves the row is left untouched — not released, not stolen — and a
duplicate is rejected, under a real cancellation exercised through the
same code path a client disconnect uses). There is **no automatic
recovery** for a `started` row in this patch, for any of those causes: the
occurrence stays permanently claimed. The only recovery today is
deleting/purging the thread (`adelete_thread`) or direct database
intervention — there is no in-app "unstick this dialog" surface. Reload /
rehydration and automatic recovery are tracked follow-up work, not solved
here. Tool-level idempotency remains the caller's own responsibility, same
as any distributed system without a two-phase-commit external resource
manager.

**PostgreSQL test limitation.** The Postgres path uses the identical
`pg_insert(...).on_conflict_do_update(...)` construct already proven in
production by `aput_writes`/`AsyncBaseSqlStore.upsert`, but this claim's
specific `WHERE` + `RETURNING` combination is exercised only against
SQLite by the offline suite
(`test_sql_checkpointer_hitl_claim.py`), plus one offline
dialect-compilation assertion
(`test_hitl_claim_insert_compiles_the_expected_postgresql_statement`) that
proves the statement is well-formed Postgres SQL — this is NOT a
substitute for a real PostgreSQL concurrency integration test, which this
repo does not have. True multi-process/multi-replica testing (spawning
separate OS processes) was not attempted either:
`fred_runtime.runtime_context.get_runtime_context()` is a single
process-wide global, so two live `create_agent_app` instances cannot
safely coexist within one test process — the cross-replica test targets
the checkpointer layer directly instead, the layer that constraint
actually allows testing honestly.

**Metrics.** `aclaim_hitl_resume`/`astart_hitl_resume` emit the same
`persist_pool_wait_ms`/`persist_sql_ms` timers `aput`/`aput_writes` use
(`store="checkpoint"`, `op="hitl_claim"`/`"hitl_claim_start"`) —
`pool_wait_ms` measured before the connection is acquired, `sql_ms`
covering the whole transaction including the `_db_now` round trip.
`aconsume_hitl_resume`/`arelease_hitl_resume` are best-effort side
operations and are deliberately NOT instrumented, matching the existing
convention for `adelete_thread`/`aget_tuple`. `store`/`op` are NOT in
`PROMETHEUS_ALLOWED_LABELS` (`prometheus_kpi_store.py`) — they are not
independently visible as Grafana label dimensions; only the aggregate
`persist_pool_wait_ms`/`persist_sql_ms` series are.

**Scope.** ReAct V2 only. The legacy Graph runtime's `graph_v2` checkpoint
path (`graph_runtime.py::_store_pending_checkpoint`) already validates
against a real checkpointer-storage `checkpoint_id` and is unchanged; it
has no equivalent atomic claim.

**Cross-stack transport.** `fred-agents-cli` (`pod_client.py`,
`history_display.py`, `repl.py`) forwards `interrupt_id` end to end —
`execute()`/`stream_events()`/`iter_stream_events()` accept it,
`run_single_turn()` forwards both `checkpoint_id` and `interrupt_id`, and
the interactive REPL extracts both from the pending
`AwaitingHumanRuntimeEvent.request`. The frontend (`useChatSse.ts`) carries
it through an explicit `RuntimeHitlPayload`/`RuntimeAwaitingHumanEvent`
type pair based on the generated `HumanInputRequest` contract, replacing
the legacy agentic-backend `HitlPayload`'s open index signature for this
purpose.

**Immediate follow-up (tracked, not in this patch).** `FredHitlMiddleware`
stays a hand-rolled `AgentMiddleware` with FRED's own `interrupt()` call
site and the claim table described above. The immediate next step is
migrating it onto LangChain's native `HumanInTheLoopMiddleware`, letting
FRED delegate more of the interrupt/resume lifecycle to the upstream
library instead of layering a bespoke claim table underneath it. That
migration is out of scope here — this patch is deliberately the smallest
safe fix for the identity/duplication bug, not a rewrite of the HITL
middleware.

---

### 8.40 ✅ `ToolCallRuntimeEvent.token_usage` — per-step token usage in the chat trace (TRACE-01, issue #2217, 2026-08-04)

**New optional field.** `ToolCallRuntimeEvent` (`fred_sdk.contracts.runtime`)
gains `token_usage: dict[str, int] | None = None` — the usage of the model
call that decided to make that tool call, not a per-tool split. Additive,
backward-compatible: only ever *constructed* with kwargs by the two
producers (`react_runtime.py`, `graph_runtime.py`); no consumer in the
monorepo re-parses it via `.model_validate()`, so `FrozenModel`'s
`extra="forbid"` never gets a chance to reject it.

**Both execution engines, symmetric fix:**

- ReAct (`react_runtime.py:486-518`): captured directly off the
  tool-deciding `AIMessage` via `_runtime_metadata_from_message`, once per
  message (not per parallel tool call).
- Graph (`graph_runtime.py:627-636`, `701-710`): the node's own
  `_last_token_usage` (whatever `record_model_metadata` last recorded on
  that node) is attached at `invoke_tool`/`invoke_runtime_tool` time — a
  graph node can call several models before invoking a tool, so this is the
  most recent one, not necessarily that exact call's own usage.

**Live stream and persisted history both carry it — deliberately, not just
the SSE payload.** Every turn is written to the history store at the end of
the exchange (`_write_turn_history` → `make_tool_call`,
`fred_core.history.history_schema`); that persisted `ChatMessage.metadata`
is what a page refresh or session reopen reads (`useSessionHistory.ts`), a
different path from the live SSE stream. Wiring only the live event would
have made the figure vanish on refresh for a conversation created the same
day — corrected during implementation, see
`docs/swift/rfc/TRACE-TOKEN-USAGE-RFC.md` §2.1.

**Out of scope (unchanged by this entry):** conversations whose history was
already persisted *before* this shipped — no retroactive backfill; the
separate `ThoughtRecord` eval-harness format; and a pre-existing,
independently-tracked bug where `FinalRuntimeEvent.token_usage` (and
anything summing it, e.g. the chat top-bar total) reflects only the
**last** model call of a multi-tool-round-trip exchange, not the true sum
(per-provider `usage_metadata` is per-call, not cumulative) — see the RFC's
§1 for detail. **Fixed same day, see §8.41.**

---

### 8.41 ✅ `FinalRuntimeEvent.token_usage` now sums every model call in the turn, not just the last (2026-08-04)

**Closes the gap §8.40 explicitly deferred.** Confirmed live: with §8.40
shipped, summing a turn's per-step token figures in the chat trace gave a
larger number than the chat top-bar total — the top bar sums each
exchange's `FinalRuntimeEvent.token_usage`, and that value was a
last-write-wins rolling variable (`last_token_usage` in `react_runtime.py`;
`_last_token_usage` on both `_GraphNodeExecutionContext` and
`_DeterministicGraphExecutor` in `graph_runtime.py`), overwritten by every
model call rather than summed. A ReAct/Graph turn commonly makes several
model calls (tool-deciding calls, then the final answer — or several calls
inside one Graph node) and each provider's `usage_metadata` is per-call, not
cumulative, so only the last call's tokens ever reached the final event.

**Fix — sum instead of overwrite, at exactly one point per model call.**
New shared helper `sum_token_usage(a, b)`
(`fred_runtime/runtime_support/model_metadata.py`, re-exported through
`react_stream_adapter.py` → `react_langchain_adapter.py` for ReAct).
Accumulation happens once per model call, not once per observation of it:

- **ReAct** (`react_runtime.py`): the `"messages"` streaming mode no longer
  writes into the accumulator — it observes the same AIMessage the
  `"updates"` mode later delivers as a complete message, and summing both
  would double-count every call. `total_token_usage` is now folded in
  exactly at the two `"updates"`-mode capture points: the tool-deciding
  `AIMessage` branch and the final-answer `AIMessage` branch.
- **Graph** (`graph_runtime.py`), two layers, same shape of fix:
  - Node level (`_GraphNodeExecutionContext`): a new `_total_token_usage`
    field sums every model call the node makes; the pre-existing
    `_last_token_usage` (last call only) is kept **unchanged** and still
    feeds `ToolCallRuntimeEvent.token_usage` (TRACE-01 per-step display) —
    summing there would have turned each step's figure into a running
    total instead of "the cost of the call that decided this step".
    `last_model_metadata` (the property the executor reads) now returns
    the node's *summed* usage, not its last call.
  - Turn level (`_DeterministicGraphExecutor`): `_last_token_usage` renamed
    `_total_token_usage`, `_record_model_metadata` now sums each node's
    (already-summed) contribution instead of overwriting.

**Verified non-breaking** the same way as §8.40: nothing re-parses these
events strictly. Regression tests added: `test_react_token_usage_totals.py`
(turn sums every call; a step still shows only its own triggering call, not
a running total) and `test_graph_runtime_token_usage_totals.py` (same two
properties at the node level).

**Still out of scope:** backfilling this corrected total into history
persisted before this fix.

---

### 8.42 ✅ Tool error claims the final response only when the whole round failed (issue #2244, 2026-08-05)

**Refines §8.27's runtime half.** Since the v2 loop shipped, any
`is_error=True` tool result made the ReAct stream surface that error text
verbatim as the `FinalRuntimeEvent` content and discard the LLM's own
synthesis ("the LLM is NOT trusted to relay it", `react_runtime.py`).
Observed live (mistral-small, 2026-08-05): a "summarize all my docs" turn
made six parallel `summarize_document` calls — five succeeded, one 403'd
(the model had passed a folder's tag id from `list_document_tree` as a
`document_uid`) — and the user got only the raw 403 text while five good
summaries were thrown away. This also actively contradicted §8.27's
tool-failure-recovery prompt suffix, which instructs the model to answer
from what succeeded: the model complied, and the runtime then discarded
that answer.

**New policy** (`react_runtime.py`, `round_had_tool_success`): an error
claims the final response only while no tool call of the same round (the
batch requested by one tool-calling `AIMessage`) has succeeded. Any
success — a parallel sibling arriving before or after the error, or a
later round's recovery retry — revokes the claim and restores the LLM's
synthesis as the final response; the failed call itself still reports
`is_error=True` in the trace. A wholly-failed round keeps the pre-existing
guarantee: the error text is the final response and assistant deltas stay
suppressed. A success in an *earlier* round does not shield a later
wholly-failed round — each round is judged on its own results.

**Companion fixes in the same change (issue #2244):** Knowledge Flow's
tree rendering now prefixes folder tag ids (`name [folder:tag-id]/`,
`tree_builder.py`) so they are no longer visually identical to document
uids; `list_document_tree`'s docstring warns folder ids are never
`document_uid`s; `summarize_document`'s 403/404 recovery hint covers the
folder-id cause; the frontend's `stripDocumentUids` redaction also strips
the `folder:` form. Regression tests:
`test_react_tool_error_final_2244.py` (all four round shapes),
`test_tree_builder.py`, `test_capability_document_summarize.py`,
`traceUtils.test.ts`.

### 8.48 ✅ Keycloak user-token refresh is async and coalesced (TURN-07, issue #2125, 2026-08-07)

> **Scope of the ✅:** every acceptance criterion is met offline except the
> delayed-Keycloak, two-SSE-stream pod test. That one is not merely unrun — it
> is currently *unrunnable*, because `_authorize_and_resolve` nulls
> body-supplied refresh tokens and no producer supplies one, so nothing can
> drive a real refresh end to end. It stays owed until
> `DELEGATED-DOWNSTREAM-AUTH-RFC.md` lands or the criterion is formally
> revised. See the TURN-07 dossier for the full accounting.

**Enforces §0.2 invariant #2 on the last path that violated it.**
`refresh_user_access_token_from_keycloak` was a synchronous `httpx.post(...,
timeout=10.0)`, and every 401-recovery path reached it through sync methods
called from `async def` bodies. A single refresh therefore parked the pod's
event-loop thread for up to ten seconds, stalling every *other* concurrent SSE
turn, timer, and tool call on that pod — not just the request that triggered
it. Token expirations arrive in cohorts, so a refresh wave produced a pod-wide
latency cliff rather than a contained slowdown.

Four call chains reached the blocking helper (the fourth was not in the
original TURN-07 evidence): `KfBaseClient._request_with_token_refresh` and
`_execute_authenticated_request` (via `_current_access_token`);
`ExpiredTokenRetryInterceptor.__call__` for MCP; the media adapter in
`agent_app.py`; and the workspace filesystem adapter, whose sync `_token()`
was called from `async def _download`/`ls`/`delete`/`link_for`
(`integrations/v2_runtime/adapters.py`).

**Now**: the helper is `async def`, backed by a per-event-loop
`httpx.AsyncClient` with bounded connection limits, and coalesces concurrent
refreshes through a singleflight registry keyed on a SHA-256 digest of
`(realm_url, client_id, refresh_token)` — so one identity's concurrent 401s
share one Keycloak round trip while distinct principals never share a result.
The in-flight task is `asyncio.shield`ed, so a caller disconnecting mid-turn
cannot abort the refresh its peers are awaiting. Timeouts and transport errors
now normalize to `RuntimeError` alongside the pre-existing HTTP-status failure,
keeping the path fail-closed.

`REFRESH_TIMEOUT_SECONDS` is the **total** budget, enforced inside the shared
exchange task itself; httpx additionally applies per-phase budgets
(connect/read/write/pool) that sum to it. The full rationale — why the total
cannot live at the await site — is a few paragraphs below.

**Replica scope (§0.2 invariant #7): the singleflight registry is pod-local.**
`fred-agents` runs several replicas with no principal-sticky routing, so
coalescing holds within one pod only — two replicas refreshing the same
identity still issue two Keycloak round trips. Making it global would require
a shared store; the residual failure it would prevent (one of two *cross-pod*
concurrent refreshes losing the rotation race) degrades to an ordinary 401
retry, which is why the pod-local scope is accepted rather than escalated.

Within a pod, coalescing is also a **correctness** fix: Keycloak rotates
refresh tokens, so two concurrent 401s replaying the same token previously made
the second fail `invalid_grant`.

**Scope note — the blocking call is unreachable, but the path is not.**
`_refresh_runtime_context_access_token` raises at its `if not refresh_token`
guard *before any HTTP*, because `runtime_context.refresh_token` is `None` on
every authenticated request. (`_authorize_and_resolve` neutralises the
body-supplied value under `if authenticated_user is not None`; with
`KEYCLOAK_ENABLED=false` nothing neutralises it, but there is equally no
Keycloak to refresh against, so the path stays unreachable either way.) Two
independent causes, in this order: the frontend producer was deleted
on 2026-05-21 (`9680cd5b`, "remove old legacy code", which removed the last
`GetRefreshToken` call sites along with the WS hook), and `_authorize_and_resolve`
(control F-B) began nulling any body-supplied `refresh_token` on 2026-06-28
(`f27fe2f8`, #1862) — five weeks *after* the producer was already gone. **F-B
sealed an already-dead path; it did not break a working one.**

Two consequences, and the second is the one that matters:

1. TURN-07's event-loop stall cannot occur today: execution never reaches the
   synchronous `httpx.post`. This change enforces the invariant *ahead of* a
   producer being wired, so whoever restores delegated refresh does not
   simultaneously reintroduce a pod-wide stall.
2. **The guard itself is reached in production and is user-visible.**
   Expired-token recovery fails outright instead of degrading. Reported three
   times — [#1948](https://github.com/ThalesGroup/fred/issues/1948) (KEA prod,
   closed not-planned), [#1951](https://github.com/ThalesGroup/fred/issues/1951)
   (swift), and [#2073](https://github.com/ThalesGroup/fred/issues/2073) Item 3,
   reproduced live 2026-07-23 with this exact guard in the stack trace — all
   closed with no fix, and no open issue now tracks it.

Restoring delegated refresh is **not** simply re-adding the producer: F-B
neutralizes body-supplied refresh tokens deliberately, and giving a pod a user's
long-lived refresh token is a security decision, not a bug fix. The design for
closing the root cause is `docs/swift/rfc/DELEGATED-DOWNSTREAM-AUTH-RFC.md`
(token exchange at admission) — written, not implemented, awaiting its own
issue. §8.49 and §8.50 record the two no-RFC mitigations landed alongside this
change.

**Contract-visible signature changes** (all internal to `fred-runtime`; the
`fred-sdk` authoring surface is untouched and no capability package consumes
these): `KnowledgeFlowAgentContext.refresh_user_access_token`,
`TokenRefreshCallback`, `KfBaseClient._try_refresh_token` /
`_current_access_token`, the three v2 agent shims, `_workspace_access_token`,
and `_refresh_runtime_context_access_token` are now awaitable. The synchronous
helper was removed rather than deprecated, so no sync network I/O remains
reachable from an async path.

Refresh duration and outcome are emitted through the existing KPI writer as a
**dedicated metric**, `auth.token_refresh_latency_ms`, with a single
`status=ok|error|timeout` dim, measuring the Keycloak exchange itself. Because
the total deadline lives *inside* the exchange (below), every outcome —
including a timeout — is emitted exactly once by the exchange that produced it,
and every coalesced caller sees that same outcome. A `phase` dim on the shared
`app.phase_latency_ms` was rejected: `phase` is deliberately absent from
`PROMETHEUS_ALLOWED_LABELS`, so it is stripped at the Prometheus boundary and
the timings would have been indistinguishable in Grafana from every other phase
emitter. `status` is already an allowed label, so the series is attributable by
name and outcome without adding a label (a new label is a deliberate
cardinality decision — `OBSERVABILITY-AND-AUDIT.md` §3). No token, user,
session, or team identity reaches the dims. Emitting the `timeout` outcome
requires leaving the timer block normally and raising afterwards — raising
*through* `KPIWriter._TimerImpl.__exit__` forces `status="error"` and would
collapse "Keycloak is slow" into the same series as "Keycloak said no".

Two consequences of moving from a throwaway `httpx.post` to a **shared** client
had to be handled explicitly, since both are capabilities the old per-call
client did not have:

- **No cookie persistence.** httpx calls `cookies.extract_cookies(response)` on
  every response, so one principal's Keycloak cookies would have been replayed
  on the next principal's refresh. The client is built with a jar that refuses
  to store. (It is installed on `_cookies` because httpx's public setter
  re-wraps any value in a plain `Cookies`; the regression test fails loudly if
  that internal ever changes, which is preferable to silently resuming storage.)
- **Shutdown drains before closing.** `aclose_token_refresh_client` awaits
  in-flight refreshes — each already bounded by `REFRESH_TIMEOUT_SECONDS` —
  before closing the transport, so an orderly shutdown cannot turn a running
  turn's refresh into "Cannot send a request, as the client has been closed".
  The state stays registered for the whole drain and is popped only at the end,
  so a refresh arriving mid-drain reuses this client instead of building a
  second one behind the closer's back — and the drain re-reads `inflight` each
  pass rather than working from a snapshot, so that late arrival is waited for
  too. (A `closing` flag was tried first and was inert: nothing read it, and the
  snapshot still let a mid-drain exchange have the transport closed under it.)
  The wait is `asyncio.wait`, not `wait_for(gather(...))`:
  the latter cancels the gather on timeout, which propagates into every child
  task, and each shielded waiter would then see `CancelledError` — a
  `BaseException` that every caller's `except Exception` 401-recovery handler
  misses, so a rolling restart would kill in-flight turns rather than degrade
  them.

**`REFRESH_TIMEOUT_SECONDS` is enforced inside the shared exchange task, not at
the await site.** Per-phase budgets (`connect`/`read`/`write`/`pool`, summing to
the total) bound the ordinary case, but they are not a total: a peer that sends
a byte inside every read window resets the read timer indefinitely and no phase
ever trips. With the only total bound on the waiter, each caller gave up on
schedule while the exchange ran on — holding its `inflight` slot and a pooled
connection with nobody left waiting to notice, so `max_connections=32` such
identities could pin the pool. The deadline therefore wraps the POST *within*
the task, and callers simply `await asyncio.shield(task)`: bounded by
construction. The shield still lets the task outlive a *cancelled* caller —
deliberately, for the coalesced peers still waiting — but never beyond its own
deadline, which is the bound that was previously missing.

**A cancelled caller never cancels the exchange**, even when it is the only one
waiting — the await site is a plain `asyncio.shield`, with no waiter
bookkeeping. Any last-waiter-cancels scheme races the waiters' own resumption
(reference-counting was tried and reverted for exactly that) and delivers
`CancelledError` — a `BaseException` every caller's `except Exception`
401-recovery handler misses — killing turns instead of degrading them. The
accepted cost is a rotation nobody consumes (the exchange completes, Keycloak
invalidates the presented token, the replacement is dropped): the
protocol-inherent lost-rotation race already recorded as
`DELEGATED-DOWNSTREAM-AUTH-RFC.md` open question 8, which degrades to one
`invalid_grant` retry. Each waiter also receives its **own** copy of the
payload, since one task resolves to one object and a shared mutable dict would
let the first mutator corrupt what its peers already read.

**Coalescing covers overlapping calls only.** A turn whose 401 lands *after* an
earlier refresh completed finds no in-flight entry and presents a token Keycloak
has already consumed, so it still gets `invalid_grant`. Closing that needs a
cached result keyed on the pre-rotation token — live credentials held in pod
memory, an AUTH-TX decision rather than a refresher one.

**A 2xx is not a promise of a token.** The success path validates the response
shape — JSON object, non-empty string `access_token`, and an `expires_in` that
is absent (RFC 6749 §5.1 makes it optional; the documented 300 s default
applies) or genuinely numeric — and otherwise fails closed with a constant
message. This is the success-path half of the same OWASP A09 / CWE-532 rule the
error path already followed: `int(payload["expires_in"])` put the rejected
value verbatim into a `ValueError` that Knowledge Flow and MCP then log.

**The token-refresh hook contract is enforced on the result, not the callable's
shape.** Hooks are `Callable[[], Awaitable[str]]`, and every legal shape —
coroutine function, `async __call__`, coroutine-returning closure — must work;
no static check can classify these, so none is attempted.
`resolve_refresh_result` (`common/structures.py`) awaits whatever the hook
returned. A legacy *synchronous* hook violates this section's contract: it runs
its network I/O on the event loop once and is named at ERROR, but its token is
still used — discarding a refresh that succeeded would turn one slow call into
permanently broken 401 recovery.

Regression tests: `test_user_token_refresher.py` (55 cases, including
singleflight coalescing, cross-principal isolation, cancellation safety, the
`timeout` status surviving to the metric, an assertion that every emitted dim
survives `PROMETHEUS_ALLOWED_LABELS`, proof that a timed-out exchange leaves no
task and no registry entry behind, malformed-2xx bodies never reaching a log
sink, a structural guard that every hop in all four 401-recovery chains stays
awaitable, the closed-client branch pinned against httpx's own wording by
closing a real client, and an event-loop liveness assertion that fails against
the pre-change implementation), plus `test_kf_base_client_refresh_shapes.py`
(all three async hook shapes resolve; a sync wrapper degrades loudly instead of
being rejected).

**One acceptance criterion is only partially met.** #2125 asks for a
delayed-Keycloak test proving *unrelated SSE streams keep progressing* during a
refresh. The liveness assertion proves the mechanism — a ticker task advances
during the refresh window, 0 ticks against the pre-change code and 18 after —
but it exercises the refresher directly, not a pod serving concurrent SSE
turns. The pod-level forced-expiry scenario (`WORKING-PROTOCOL.md` §6) needs a
live stack and is not reachable from `make test`; it remains owed.

### 8.49 ✅ `search_documents_using_vectorization` degrades instead of killing the turn (2026-08-07)

**Companion to §8.48, and the only part of the expired-token exposure fixable
without an RFC.** Three tools in `document_access` handled an identical
downstream failure three different ways. `list_document_tree` and
`summarize_document` caught it and returned an `is_error=True` artifact via the
module's shared `_document_tool_failure` helper — whose own docstring states the
rule: *"a failing tool MUST return such a result instead of raising — a raised
exception is re-raised by the default `ToolNode` handler, which leaves the tool
call pending in the trace and yields an empty error detail to the UI."*
`search_documents_using_vectorization`, the most-used RAG tool, had no
`try`/`except` at all, so the exception escaped and **killed the whole turn**,
surfacing a raw `Client error '401 Unauthorized' for url '.../vector/search'`
with an empty error detail.

That is the failure observed live in #2073 Item 3: the same expired-token 401
that MCP tools survived (degraded) took the turn down through this tool.

**Now**: the `port.search(...)` call is wrapped like its siblings, returning
`_document_tool_failure(...)` so the model sees an actionable error and can
recover or explain, and the trace carries a populated `is_error` row. This does
not fix the token expiry itself — §8.48 explains why that needs an RFC — it
bounds the blast radius from "turn dies" to "one tool call failed", for this and
every other Knowledge Flow failure mode.

Two defects found while reviewing that change had to be fixed with it, or the
degradation would have been silent:

1. **The search adapter never mapped its errors.** `_wrap_document_port_error`
   was applied on the tree and summarize adapters but not on
   `DocumentSearchAdapter.search`, so a raw `httpx` error reached the
   capability. The capability reads `status_code`/`timed_out` off the exception
   and never imports the HTTP stack, so the incident's 401 rendered as "the
   Knowledge Flow service call failed" with no status named. `search` now wraps
   like its siblings.
2. **A handled failure was audited as a success.**
   `ToolObservabilityMiddleware` decided failure purely from
   `ToolMessage.status == "error"`, which LangChain sets only when a tool
   *raised*. A tool that returns an `is_error=True` artifact — the contract
   `_document_tool_failure` implements, and what `react_runtime` already reads
   to mark the trace step failed — produced an ordinary `ToolMessage`, so the
   call was recorded `outcome="succeeded"` and never counted in
   `agent.tool_failed_total`. Converting this tool from raising to returning
   would therefore have *removed* it from failure accounting. The middleware
   now also honours the artifact flag, which aligns the audit trail with the
   trace for all three document tools.

   **This does not fix the MCP case.** `ContextAwareTool._arun` returns its
   error as *text* with a `None` artifact (`return msg, None`), so there is no
   `is_error` flag for the middleware to read and an MCP tool failure is still
   audited `outcome="succeeded"` — the misreporting recorded in #2073 as
   adjacent to #2011 remains open. Closing it needs a distinct signal from
   `ContextAwareTool`, which is outside this change.

Regression tests: `test_search_tool_failure_returns_is_error_result` and
`test_search_adapter_wraps_httpx_error_with_status_code`
(`test_capability_document_access_1906.py`);
`test_awrap_tool_call_is_error_artifact_marks_failed` and
`test_awrap_tool_call_success_artifact_stays_succeeded`
(`test_tool_observability_middleware.py`). Each fails against its pre-change
implementation.

### 8.50 ✅ Chat turn-start token preflight: more headroom, no doomed sends (2026-08-07)

**Frontend companion to §8.48/§8.49 — the last no-RFC-needed piece of the
expired-token exposure.** Two defects in the send path compounded the mid-turn
expiry window:

1. Turns preflighted with `ensureFreshToken(30)` — the same 30 s threshold as
   ordinary fetches — so a turn could *begin* with 30 seconds of bearer life
   while the pod forwards that bearer for the whole turn with no mid-turn
   renewal (§8.48).
2. `ensureFreshToken` resolves `false` on refresh failure/timeout instead of
   rejecting, so the `try/catch` around it in `useChatSse.ts` was dead code and
   the boolean was discarded: a silently failed refresh removed even the 30 s
   floor, starting turns with arbitrarily little token life.

**Now** (`useChatSse.ts`, `KeycloakService.ts`): both send paths (send and HITL
resume) preflight through one helper. It requests `TURN_TOKEN_MIN_VALIDITY_S =
120` of headroom; on a failed refresh it consults the new
`GetTokenSecondsLeft()` and **blocks the send with a user-facing message** when
less than `TURN_TOKEN_HARD_FLOOR_S = 30` remains — a clear error at the
composer beats an opaque tool failure 30 s into the stream — and otherwise
proceeds with a console warning. Ordinary fetches keep the 30 s default.

**A refusal must leave the interaction retryable.** `handleHitlAnswer` clears
`pendingHitl` before awaiting the resume, so a refused HITL resume would have
hidden a prompt whose checkpoint is still paused server-side, with no way to
answer it. `sendHitlResume` therefore resolves `false` for **every** outcome
where the resume never reached the runtime — token refusal, prepare-execution
failure, an abort/supersession before the stream started, *or* the runtime
rejecting the request outright (a fetch failure, or a non-2xx such as 503 from
an unready pod). The dividing line is the runtime's own acceptance:
`streamToMessages` signals `onAccepted` once past its status check, and only
after that does a failure count as reached — a mid-stream reset must NOT
resurrect the prompt, because the checkpoint has already been consumed.

Not-reached is a fact about the backend, not about who owns the UI, so
`handleHitlAnswer` guards the restore itself, three ways: same session
(`activeSessionIdRef`), thread-derived staleness (the restore is skipped when
the thread's last message carries a *different* `exchange_id` than the prompt —
a turn that genuinely starts appends its optimistic user message under a new
`exchange_id`, so the thread itself says whether the user has moved past the
exchange, while a send that fails before committing appends nothing, which is
exactly when the prompt should return), and empty slot only (a functional
update, so a newer `awaiting_human` is never overwritten by a late-settling
continuation). No counter or rollback state is kept for this: nothing
accumulates, so nothing needs unwinding when a superseding send fails. A
`.catch()` mirrors the same restore, since `pendingHitl` is cleared before the
await and this continuation is the only path that can put it back. For the same reason the optimistic "cancelled"
tool_results now go in **after** prepare-execution succeeds, not before:
applied earlier, a failed preparation left the gated calls displayed as
cancelled by an attempt that never ran, and because those messages are ranked
by `Date.now()` they could never collide with a backend rank in `upsertOne` —
so the real results arriving on the retry sat *alongside* the fake ones, and
`groupTraceEntries` (last result per `call_id` in rank order) kept the fake one
permanently. `upsertOne` now also matches an optimistic cancellation by
`call_id` within its exchange, so a real result supersedes it in every case.

**Cleared-session fail-closed (2026-08-09).** keycloak-js ends the session
itself when a refresh comes back HTTP 400 (`clearToken()`), and that state was
fail-open three ways: `isTokenExpired` starts *throwing* (a bare string) and
the preflight's fast path sat outside its catch — `dynamicBaseQuery` awaits
`ensureFreshToken` with no catch at all, so ordinary requests aborted before
their 401→logout recovery; `GetTokenSecondsLeft()` returned `null` ("no floor
to enforce") for a session that was dead, letting the preflight proceed
"unbounded"; and `GetToken()` fell back to the persisted `localStorage` copy,
so an unexpired-but-orphaned bearer kept authenticating requests the backend
accepts via offline JWT validation. Now: `ensureFreshToken` keeps its boolean
contract in that state (resolves `false`, attempts no doomed exchange) and
reports the headroom it actually obtained — it re-checks the refreshed token
rather than answering `true` because `updateToken` settled, which on a realm
whose lifespan is below the requested validity made the guarantee unkeepable and
silently disabled the hard floor (only consulted when this resolves `false`).
**`minValidity <= 0` means FORCE**, mapped to keycloak-js's `updateToken(-1)`
sentinel — its only unconditional-refresh path — and skipping the headroom
check entirely. That is what `dynamicBaseQuery` asks for after a 401, where the
browser's own view of the token is precisely what must not be trusted (clock
skew against admission's `leeway=0`, an SSO logout elsewhere, realm key
rotation). Merely coercing `0` up to the library's 5 s floor was tried first and
only moved the hole: a 401 arriving while the browser believed 20 s remained
still short-circuited, replayed the same bearer, took a second 401 and logged
the user out. Non-forced thresholds are floored at 5 s so the value tested here
matches the one `updateToken` will apply, and the single-flight reuse gate
compares those *proven* thresholds rather than the raw arguments — `0` is the
strongest request but the weakest raw number. Meanwhile
`GetTokenSecondsLeft` reports `0` — dead, not unconstrained — once the session
has actually **died** (tracked from `onAuthLogout`; keycloak-js reports
`authenticated = false` both for a cleared session and before `init()` has ever
run, so an absent token alone cannot tell them apart, and treating bootstrap as
dead would hard-refuse turns at startup). It returns `null` — unconstrained —
when keycloak-js's `timeSkew` is `null`, which is that library declaring expiry
undeterminable rather than declaring zero skew; defaulting it to 0 turned a fast
client clock into a large negative and refused every turn for a bearer the
server still accepts. And
`createKeycloakInstance` registers `onAuthLogout` to drop the persisted copy
the moment Keycloak ends the session. The removal is hygiene against the app's
own fallback, not a boundary — anything running in the page could keep a copy
of the token regardless; only the 300 s TTL (and, eventually, the RFC's
server-side exchange) actually bounds a leaked bearer.

This narrows the window; it does not close it (a turn can still outlive a
120–300 s token). The close is `DELEGATED-DOWNSTREAM-AUTH-RFC.md` (token
exchange at admission), deliberately not implemented here.

Regression tests: `useChatSse.test.tsx` (refusal below the hard floor, degraded
proceed above it, HITL refusal reporting not-reached with no optimistic
cancellation left behind, and the same for a failed preparation),
`useManagedChat.test.tsx` (prompt restored on not-reached, stays cleared
otherwise), `chatSseUtils.test.ts` (supersession by `call_id`, scoped to the
same exchange). Each fails against its pre-change implementation.

---

### 8.51 ✅ Tool-KPI label discipline, complete pod shutdown, wire-time token rescue (§8.48–§8.50 follow-up, 2026-08-10)

**Three corrections landed with the §8.48–§8.50 change. The first two share
one shape: a mechanism that looked correct in the source and did nothing at
runtime.**

1. **`agent.tool_latency_ms` carries `status` and no other outcome dim.**
   `ToolObservabilityMiddleware` wrote `error_code`/`exception_type` onto the
   timer's dims on both failure branches. Neither ever reached Grafana:
   `PrometheusKPIStore._resolve_labeling` freezes a metric's label-name tuple
   on the metric's **first** sample, and the first tool call in any pod is
   overwhelmingly a success carrying neither dim — so every later value was
   discarded before export, with nothing in the code, the metric, or the
   dashboard to say so. They are removed from the timer rather than back-filled
   on the success path: the failure taxonomy already lives on
   `agent.tool_failed_total` (a counter, labelled identically on the raised and
   the handled-failure branch, per §8.49), and `agent.tool_latency_ms` is a
   histogram whose bucket series would be multiplied by error-code cardinality
   for a question — "latency by error code" — nobody asks. `status` alone
   answers the one that is asked, and `_TimerImpl.__exit__` sets it on every
   sample.

   **Rule this generalises:** adding a dim to one emission site of a KPI means
   adding it to *every* site of that metric, success paths included, with a
   constant filler where it does not apply. A dim only some branches emit is
   not partially visible — it is absent.

2. **Pod shutdown runs to completion.** `agent_app.py`'s lifespan released
   gc-diagnostics, the pod container and the Keycloak refresh pool as bare
   statements after `yield`. An exception propagating out of the app skipped
   all three, and a raising `container.shutdown()` (a hung KPI task, a failed
   SQL dispose) stranded the 32-connection refresh pool behind it — silently,
   since nothing logged either failure. Shutdown is now a `finally` with each
   step independently guarded and its failure logged with the step named;
   `CancelledError` deliberately still propagates, because a cancelled shutdown
   is not a failed step.

3. **The wire-time token gate refreshes once before refusing.**
   `verifyTokenStillUsable` (`useChatSse.ts`) re-checks the hard floor after
   the unbounded pre-stream awaits, and used to refuse outright below it. That
   made the degraded band of §8.50 unreachable on the realms it was built for:
   where access tokens live under `TURN_TOKEN_MIN_VALIDITY_S` (120 s) the
   turn-start preflight can *never* reach its target, so it proceeds degraded
   by design — and a refuse-only gate then hard-failed every turn whose
   preparation was slow. The gate now takes one `ensureFreshToken` before
   giving up, asking for `TURN_TOKEN_HARD_FLOOR_S` rather than the turn-start
   target (at the wire the only remaining question is whether the bearer
   survives admission and the first tool call; asking for 120 s would report
   "not fresh" for a refresh that had in fact cleared the floor). **The verdict
   is always the measured lifetime afterwards, never the refresh's own
   boolean** — `ensureFreshToken` answers "is THIS caller's headroom
   satisfied?", and its rejection is not a verdict either. Both call sites
   re-check `ac.signal.aborted` after the new await, since it is one more
   window in which the attempt can be superseded.

   Deliberately NOT changed alongside it, both reviewed and kept: `state.closed`
   stays a one-way door per event loop (a pod boots once and dies once;
   reopening reintroduces the "rebuild a pool nothing closes" leak the flag
   exists to stop), and an aborted HITL resume still counts as delivered (a
   prompt stranded that way is recovered by `reconstructPendingHitl` from
   server history on reload, whereas restoring it eagerly risks an unanswerable
   card that 409s on every attempt).

Regression tests: `test_awrap_tool_call_is_error_artifact_marks_failed`
(asserts the timer's *absence* of `error_code`/`exception_type`,
`test_tool_observability_middleware.py`),
`test_lifespan_shutdown_releases_every_resource_even_when_a_step_raises`
(`test_agent_app.py`), plus
`test_client_closed_under_an_inflight_exchange_is_reported_as_shutdown` and
`test_unexpected_runtime_error_is_not_reported_as_an_orderly_shutdown`
(`test_user_token_refresher.py`), which pin §8.48's closed-client branch
against httpx's own wording by closing a real client rather than hand-building
the exception; and, for the gate, `useChatSse.test.tsx`'s pair — a token under
the floor that the rescue refresh clears (turn proceeds, second refresh asks
for 30 s not 120 s) and one it cannot (refusal, but only after the attempt).
Each was verified to fail against its pre-change implementation.

---

### 8.52 ✅ Deployment-scoped chat-input length limit — issue #2253 (2026-08-12)

One submitted chat message is bounded by the runtime-pod startup policy
`app.max_chat_input_chars` (default `5000`, positive integer). The unit is a
Unicode code point: Python uses `len(text)`, while managed chat iterates the
string by code point without materializing a second array. This is deliberately
a character policy, not a model-token, conversation-history, request-byte, or
context-window budget.

The runtime is authoritative and validates before exchange lookup, target
resolution, history persistence, stream construction, or agent execution on
`POST /agents/execute`, `/agents/execute/stream`, and `/agents/evaluate`.
Ordinary turns count `RuntimeExecuteRequest.input`. HITL resumes count a bare
string, or the combined string values of canonical `choice_id`, `answer`, and
`text` fields; arbitrary JSON keys are not traversed. The OpenAI-compatible
route applies the same code-point limit to the last user message Fred forwards.

Fred-native rejection is HTTP 422 with `detail.code =
"chat_input_too_long"`, `message`, `limit_chars`, and `actual_chars`.
OpenAI compatibility returns HTTP 400 with the corresponding
`invalid_request_error`, `param = "messages"`, and the same stable code/counts.
Neither response, logs, metrics, nor traces may include the rejected content.
A static Pydantic `max_length` is not used because the value is deployment
policy, HITL is field-aware, and FastAPI's default validation response can echo
the offending input.

The effective pod-scoped value is mirrored on every `/agents/templates` item,
following the existing pod-metadata publication pattern. Managed chat receives
that optional projection through execution preparation, displays a counter,
blocks an oversized draft without truncation or native `maxLength`, and relies
on backend enforcement when an older runtime does not yet publish the field.
During a rolling deployment, replicas configured with different limits may
temporarily advertise and enforce different values: execution preparation can
project one replica's value while the browser's execution request reaches
another. The displayed limit is therefore advisory; the receiving runtime
remains authoritative, returns its own `limit_chars` on rejection, and managed
chat adopts that returned limit for subsequent validation.
This semantic handler check occurs after HTTP body parsing; whole-request byte
limits and HTTP 413 remain outside issue #2253.

---

### 8.53 ✅ ReAct model-input size budget, in addition to the message-count trim — TURN-04 partial (#2350, 2026-08-13)

**ReAct-only slice of TURN-04's "turn resource bounds" finding** (full finding
still open for Deep and Graph, and for persisted-checkpoint compaction — see
[#2343](https://github.com/ThalesGroup/fred/issues/2343)). Field incident
(2026-08-12, `mistral-small-2603`): a session stayed at ~25 turns, far under
`_V2_MAX_HISTORY_MESSAGES = 500`, while a 115k-character tool result followed
a few turns later by a 22k-character generated document pushed one call's
input to 178,670 tokens — still accepted — and the very next turn then failed
outright (`finish_reason="error"`, 0 output tokens). The message-count trim
never engages on payload size; whether the failure itself was specifically a
provider context-length rejection could not be confirmed from the persisted
turn history — Fred's own error-path token reporting attaches the last
successful sub-call's usage to the turn, not the failing request's real size,
which is exactly the separate `execution_error` persistence gap #2343 flags
for its own fix.

`CheckpointHygieneMiddleware.awrap_model_call`
(`fred_runtime/react/middleware/checkpoint_hygiene.py`) now applies a second,
size-based trim after the existing message-count trim:
`trim_to_char_budget` (`fred_runtime/support/tool_loop.py`) keeps as many
trailing messages as fit under `_V2_MAX_HISTORY_CHARS` (200,000 characters,
`fred_runtime/react/react_tool_loop.py`), then advances to the same safe
HumanMessage/orphan-ToolMessage boundary as the message-count trim so it
never hands a provider a payload that starts mid tool-call/result pair.

Character count, not tokens: no exact tokenizer covers every provider this
deployment can point at (Mistral, Azure, OpenAI, ...), so this is a
deliberately provider-agnostic proxy, the same reasoning `max_chat_input_chars`
(#2253) uses for a single message. The 200,000-character default is
calibrated off the same field incident, not a generic "~4 chars/token" rule
of thumb: replaying that incident's persisted turn history against its own
reported token usage gives roughly 1.35 characters per token for this
deployment's French/HTML-heavy content (240,395 visible characters of prior
turns fed the call that reported 178,670 input tokens) — a naive 4x
assumption would correspond to ~800k characters and would never have trimmed
before this exact failure. 200,000 characters (~148k tokens at the measured
ratio) sits comfortably below the 178,670 tokens that already nearly failed
while still covering the incident's own single-document/single-tool-result
payloads (each well under 150k characters) without trimming them on their
own. This is one deployment's measured ratio, not a portable constant — see
`react_tool_loop.py`'s comment for the full derivation and re-check it if the
configured models or typical content mix change materially. When even the
trimmed window still exceeds the budget — the CURRENT turn's own content is
the culprit, and no amount of dropping older history helps — the middleware
raises `ChatTurnTooLargeError` (numbers only, never the oversized content)
instead of forwarding a payload the provider will reject anyway. It
propagates through the existing generic `except Exception` →
`RuntimeErrorEvent` path (`agent_app.py`) unchanged, so no new frontend
handling was needed.

**Observability.** A production robustness audit of this exact failure mode
(same day) found the rejection was only a DEBUG log — invisible without
digging through OpenSearch, and not how the 200,000-character default (a
first-pass estimate) would get validated or re-tuned from real traffic. Two
additions, both numbers/identifiers only, never content: the log is now
WARNING; and `CheckpointHygieneMiddleware` gained `binding`/`kpi` (following
`TracingKpiMiddleware`/`ToolObservabilityMiddleware`'s own required-not-
optional convention for those two params) to emit `agent.turn_rejected_total`
— a counter, same shape as the sibling `agent.tool_failed_total`
(`status`/`error_code`/`exception_type` dims, `KPIActor(type="system")`),
reaching Grafana through the existing `PROMETHEUS_ALLOWED_LABELS` allow-list
with no new label needed. The identity/correlation dims (`session_id`,
`user_id`, `team_id`, `agent_instance_id`, `template_agent_id`,
`correlation_id`, `trace_id`) are built by a new shared
`identity_kpi_dims(binding)` helper (`react/middleware/shared.py`), factored
out of `ToolObservabilityMiddleware._base_dims`'s identical logic rather than
hand-rolling a second copy — that method itself was left untouched to avoid
touching already-shipped, tested code same-day.

Deliberately out of scope here: Deep and Graph runtimes, persisted-checkpoint
compaction (`CheckpointHygieneMiddleware` trims only the outgoing model
request by design, never graph state), and #2330 (making
`_V2_MAX_HISTORY_MESSAGES` itself configurable) — all tracked separately
under #2343.

Regression tests: `test_char_budget_*` (`test_tool_loop_trim.py`, pure
function), `test_history_is_trimmed_by_char_budget`,
`test_current_turn_alone_over_char_budget_fails_cleanly`, and
`test_current_turn_too_large_emits_a_kpi_counter`
(`test_react_loop_regressions_1972.py`, full loop through
`agent.astream`).

**Three PR-review fixes to the counting itself (same day), each verified by
reverting and confirming its regression test fails without the fix:**

1. `_message_char_len` only read `AIMessage.content`, which LangChain leaves
   empty on a pure tool-calling turn — the real payload sits in
   `tool_calls[*]["args"]` instead (exactly `write_document`'s shape in the
   motivating field incident). Now sums tool-call arguments
   (JSON-serialized) too.
2. The budget ran BEFORE `thread_reasoning_within_open_turn`, so a large
   open-turn reasoning trace — invisible to `_message_char_len` as
   structured `thinking`-block content — could pass unmeasured and only
   balloon past the limit once rehomed into ordinary text. Reordered so the
   budget measures what the handler actually receives.
3. `trim_to_char_budget` can legitimately collapse to `[]` when the only
   message it could keep under budget is a lone trailing ToolMessage with
   no preceding AIMessage in the window (one oversized tool result, e.g. a
   big RAG hit) — an unsafe orphan boundary. Measuring that now-empty
   result silently passed the check and sent the model NO messages at
   all — worse than a raw crash. The collapse itself is now detected and
   measured against the pre-trim total instead.

Additional regression tests: `test_char_budget_counts_tool_call_arguments_not_just_content`
(`test_tool_loop_trim.py`), `test_history_is_trimmed_by_char_budget_from_tool_call_arguments`,
`test_oversized_reasoning_trace_is_budgeted_after_rehoming`, and
`test_oversized_trailing_tool_result_fails_cleanly_not_silently_empty`
(`test_react_loop_regressions_1972.py`).

---

### 8.43 ✅ `DocumentMarkdownPort` — paginated full-content read for capabilities (DOCREAD-01, 2026-08-07)

**New optional port on `RuntimeServices` (`fred-sdk`
`contracts/runtime.py`).** `document_summarize` returns a lossy overview and
the model cannot tell it only saw a summary — so "what does the first paragraph
say?" or "list ALL the requirements" answers come out half-complete. The three
existing document ports could not close this: `document_summarize` is
deliberately lossy, `document_content` returns the original uploaded **bytes**
(a PDF/DOCX blob the model can't read as text), and `document_search` returns
only the top-k relevant chunks. Knowledge Flow already stores the full parsed
markdown (`output.md`, un-truncated under the default ingestion config) and
serves it at `GET /knowledge-flow/v1/markdown/{uid}` — it just wasn't reachable
through a capability-safe port.

`DocumentMarkdownPort.fetch_markdown(document_uid, *, offset, max_chars) ->
DocumentMarkdownResult{text, offset, next_offset, total_chars}` exposes it under
the same doctrine as the other document ports (scope parameters only; the
per-turn binding and access token stay private to the adapter; KF per-document
ReBAC is the gate). **Pagination is the contract's point:** each call returns one
bounded window and `next_offset` (None at end of document), so an exhaustive
read can never silently stop half-way — the failure mode §8.42/§8.27 work around
downstream, addressed here at the source. Wiring: `DocumentMarkdownAdapter`
(`adapters.py`) fetches the whole markdown once via
`KfDocumentClient.fetch_markdown` (KF client stays wire-format only), memoises it
per uid on the per-turn instance, and slices adapter-side (`paginate_markdown`,
a pure helper) — KF has no page parameter today. Injected in `agent_app.py`'s
`RuntimeServices` assembly (turn-time path only; the save-time services subset
does not carry it). Additive and optional, so no existing runtime breaks.

**Consumers (DOCREAD-01):** two admin-gated capabilities, `document_verbatim`
(tool `read_document`, positional verbatim slice) and `document_extract` (tool
`extract_from_document`, exhaustive enumeration), both on this one port and
differing only in tool intent and how the continuation footer is worded. The
frontend Simple view groups them under one `document_reading` tool pack while the
Advanced view keeps each toggle independent (front-only presentation, no backend
change). Phase 1 relies on the agent paging to completion (guided by
`next_offset`); a server-side map-reduce extraction endpoint is the deliberately
deferred Phase 2 if that proves unreliable on very large documents. Tests:
`test_capability_document_reading.py` (pagination contract, both tools' footers,
config cap, error shaping), `test_capability_endpoints_1974.py` (pod advertises
the pair).

---

### 8.44 ✅ `DocumentExtractionPort` — server-side exhaustive extraction (DOCREAD-01 Phase 2, 2026-08-07)

**Moves `document_extract` off client-side paging.** The Phase 1 tool
(§8.43) had the agent page the whole document into its own context and
accumulate — a burst of token-heavy model calls that tripped the provider's
rate limit (observed live: Mistral `mistral-small-latest` returned HTTP 429
`code=1300` mid-turn on a multi-page extraction). Root cause is structural, not
a bug: exhaustive extraction over a big document is inherently many LLM calls,
and doing them agent-side re-sends the growing context each round.

**New optional port `DocumentExtractionPort.extract(document_uid, *,
instruction) -> DocumentExtractionResult`** (`fred-sdk`) runs the whole
map-reduce **server-side in Knowledge Flow**, in ONE agent tool call. KF's new
`POST /knowledge-flow/v1/documents/{uid}/extract` (`ExtractService` +
`DocumentExtractor`) maps over EVERY chunk (no salience pruning — deliberately
NOT `SmartDocSummarizer`, which keeps only top-N shards and compresses at
reduce, dropping items) and reduces by concatenate + case-insensitive de-dupe,
never summarizing. The map phase runs with **bounded concurrency
(`_MAP_CONCURRENCY=3`) and 429-aware retry/backoff** (respects `Retry-After`,
exponential + jitter) so a throttling provider slows the extraction rather than
failing the turn (DOCREAD-01 #2). Document text is resolved through
`SummarizeService.get_document_text`, so the corpus/session-attachment access
rules stay single-sourced. `document_verbatim`'s positional read stays on the
paginated `document_markdown` port; only exhaustive extraction moved.

Wiring mirrors the summarize path: `KfDocumentClient.extract` (extended read
timeout), `DocumentExtractionAdapter`, injected in `agent_app.py`'s turn-time
`RuntimeServices`. The `document_extract` capability tool is now one call
returning the consolidated list; its `page_max_chars` config field was removed
(server owns paging). Additive/optional — no existing runtime path changes.
Tuning knobs (concurrency, retry, input cap) are module constants pending live
calibration against real provider limits, and the map remains inherently
LLM-call-heavy on very large documents (slow-but-complete by design). Tests:
`test_document_extractor.py` (exhaustive de-dupe, NONE handling, 429 retry),
`test_capability_document_reading.py` (one-call path, empty/truncation/error
shaping).

### 8.45 ✅ Prompt-cache token visibility in `token_usage` and cost estimation — CACHE-01 (2026-08-10)

**Surfaces prompt-cache detail Fred was already receiving but silently
dropping.** LangChain's standardized `UsageMetadata.input_token_details` has
carried `cache_creation`/`cache_read` since `langchain-core` 0.3.9, and
`runtime_metadata_from_message` (`model_metadata.py`) already read the
attribute carrying it — `normalize_token_usage` just never extracted the
nested breakdown. See
[`PROMPT-CACHE-TOKEN-VISIBILITY-RFC.md`](../rfc/PROMPT-CACHE-TOKEN-VISIBILITY-RFC.md)
for the full design; open questions (distinct GreenOps rate for cached
tokens, sovereign-model cache support, per-step trace display) remain
unresolved there, not settled here.

**Contract additions, both additive:**

- `token_usage` (`ToolCallRuntimeEvent`/`FinalRuntimeEvent`, §5) gains two
  keys: `cache_read_tokens`, `cache_creation_tokens` — always present
  (default `0`), same dict shape, no schema break. Flows through
  `normalize_token_usage`/`sum_token_usage` (`fred-runtime`) and
  `ChatTokenUsage` (`fred-core`, persisted history) end to end; confirmed
  surviving a page reload via the same `make_assistant_final`/
  `_write_turn_history` path §8.38 fixed for the base fields.
- `Quantities` (`fred-core` KPI event schema) gains `cache_read_tokens`.
  `agent.turn_completed` now emits it as a quantity — one new Prometheus
  counter series (`agent_turn_completed_quantity_cache_read_tokens_total`),
  no new label, no cardinality change (same label set as `input_tokens`).
- `ModelImpactFactors`/`estimate_green_cost` (`fred-core/kpi/model_impact_factors.py`)
  gains `cost_per_1k_cached_input_tokens`; `cache_read_tokens` is billed at
  that reduced rate instead of the full input rate, clamped to
  `input_tokens` defensively. `cache_creation_tokens` is deliberately **not**
  given a distinct rate — still billed as ordinary input (RFC scope
  decision, not an oversight). One dashboard preset
  (`token_usage_by_model.py`) is wired to the new quantity; the other five
  token-usage presets are unchanged (still bill every input token at the
  full rate — not a regression, just not yet upgraded).

**Not done by this work:** real per-model `cost_per_1k_cached_input_tokens`
rates — `model_impact_factors.yaml` still ships every rate at `0.0`
("not populated yet"), so the mechanism is correct but every displayed cost
figure is unchanged until an operator fills in real provider pricing. No
distinct kWh/CO2e rate for cached tokens. No cache-hit ratio or
cached-vs-fresh visual on `AnalyticsPage` — `TokenUsageImpact` just becomes
more accurate once rates are populated, no new UI element shipped.

---

### 8.45 ✅ Alembic owns `session_history` DDL; an unmigrated pod fails at startup (issue #2290, 2026-08-07)

**Extends §8.33.** `PostgresHistoryStore` used to call `_ensure_tables()` —
`metadata.create_all` under a Postgres advisory lock — from every read and
write path (`save`, `get`, `list_sessions`, `delete_session`,
`session_belongs_to_user`, `session_exists`, `next_rank`,
`latest_exchange_id`), in parallel with the Alembic tree that already owns the
same schema (`libs/fred-runtime/alembic/versions/a1e2f3c4d5b6_*`,
`b2f3a4e5c6d7_*`, `c3d4b5a6f7e8_*`). Hit in production: an install that skipped
its migration job worked — the store silently made the table — but
`alembic_version_runtime` was never stamped, so the first `alembic upgrade head`
needed for anything else replayed from the first revision and died on "table
already exists". The operator was left with a working database and a migration
tree that could never be applied, recoverable only by hand-stamping.

**What changed.** `_ensure_tables()` and all eight call sites are gone; the
store creates nothing, on any path. `PodApplicationContext.initialize_sql()`
now calls `fred_core.sql.require_tables` once, right after the §8.33
connectivity ping and before the checkpointer/history store are published: a
missing `session_history` raises `SchemaNotMigratedError` naming the table and
the exact fix (`python -m fred_runtime migrate`), so the lifespan aborts and
the replica never becomes Ready. This is startup-only work — nothing was added
to the per-turn path; the eight per-call `await self._ensure_tables()` guards
were in fact removed from it. A database whose tables exist but whose version
table is unstamped (the pre-#2290 state) still boots, with a warning naming the
recovery path.

**Tests run the real migrations, not hand-rolled DDL.** Every pod-booting test
applies fred-runtime's Alembic tree to its SQLite file through
`fred_runtime.migrations.upgrade_sqlite_database` (`DATABASE_URL` override, run
off-loop because Alembic's online runner calls `asyncio.run`) — used by
`libs/fred-runtime/tests/conftest.py`'s `migrate_test_config` and by
`apps/fred-agents/tests/test_smoke.py`. Cost is ~30ms per database once imports
are warm, and the payoff is that the suite proves the migration tree produces a
schema the pod can boot against, leaving `alembic_version_runtime` stamped at
head exactly like a real install. Re-introducing `metadata.create_all` in test
setup would recreate, in test code, the second schema definition this entry
removed from production.

The one exception is `fred_core.history.create_history_schema`, for fred-core's
own unit tests: fred-core sits below the package that owns the Alembic tree and
cannot import upwards to run it. Anything that *can* import fred-runtime must
use `upgrade_sqlite_database`.

Note for test authors: a suite that boots a pod against a **persistent** SQLite
file (`apps/fred-agents/config/configuration.yaml` points at
`~/.fred/fred-agents/runtime.sqlite3`) must migrate it itself. Such a file left
over from before this change already contains `session_history`, so the guard
stays quiet locally and fires only on a clean runner — which is exactly how this
was missed locally and caught by CI.

Operator recovery path (which revision to stamp, by columns present):
[`ops/DATABASE_MIGRATIONS.md`](../ops/DATABASE_MIGRATIONS.md).

**Deliberately out of scope:** `SqlCheckpointer._ensure_tables()`
(`fred_runtime/runtime_support/sql_checkpointer.py`, ~12 call sites plus three
direct calls from `agent_app.py`) has the identical pattern and is tracked
separately — its tables are in no Alembic tree yet, so removing lazy creation
there needs migrations written first.

---

### 8.46 ✅ `FinishReason` — normalized, Fred-owned enum replaces the raw provider string (issue #1840, 2026-08-11)

**Closes FRONT-05 (`FRONTEND-BACKLOG.md §7`).** The frontend's last remaining
import from the retired `agentic-backend` client was `FinishReason` — a named
6-value enum that client happened to expose, with nothing equivalent on the
runtime side (`ChatMetadata.finish_reason` was a plain `Optional[str]`,
whatever the LLM provider reported verbatim).

**Why a raw passthrough was the wrong shape.** Providers report this under
different keys and vocabularies — OpenAI: `response_metadata["finish_reason"]
= "stop"/"length"/"tool_calls"`; Anthropic:
`response_metadata["stop_reason"] = "end_turn"/"max_tokens"/"tool_use"`
(**a different key entirely** — Fred only ever read `"finish_reason"`, so
every Claude-backed turn silently had `finish_reason = None` before this fix);
Gemini/Vertex: `"STOP"`/`"MAX_TOKENS"`, or `"UNKNOWN_<n>"` when the installed
SDK doesn't recognize an enum value the API returned. That last case means the
raw value space is open-ended by construction — no closed type can enumerate
it, on the frontend or the backend.

**What changed.**

- `fred_core.history.history_schema` (`libs/fred-core`) gains `FinishReason(str,
  Enum)` — `stop | length | content_filter | tool_calls | error | other` — and
  `coerce_finish_reason(raw)`, a case-insensitive alias table mapping every
  known provider value onto it. Anything not in the table (a new provider, a
  new SDK enum value, a typo) maps to `other` rather than raising — this is a
  deliberate, designed fallback, not an accidental gap.
- `ChatMetadata.finish_reason` is now `Optional[FinishReason]`, with a
  `field_validator(mode="before")` calling `coerce_finish_reason` — applied on
  **both** construction and `.model_validate()` (read), so a history row
  persisted before this change, still holding a raw provider string, loads
  without error instead of failing validation.
- `fred_sdk.contracts.runtime.FinalRuntimeEvent.finish_reason` (the live SSE
  contract) is now `FinishReason | None`, with the same tolerant
  `field_validator` — this is a separate Pydantic model from `ChatMetadata`
  (one is the live event, one is persisted history), so both needed the fix;
  fixing only one would have made the live view and a reloaded conversation
  disagree on the same turn's value.
- `fred_runtime.runtime_support.model_metadata.runtime_metadata_from_message`
  now reads `response_metadata["finish_reason"]` **or**
  `["stop_reason"]` (fixing the Anthropic gap above) and normalizes via
  `coerce_finish_reason` at the source, once — both the SSE event and the
  persisted history descend from this same call, so they can never diverge.

**Frontend.** `runtimeOpenApi.ts` now generates a named `FinishReason` union;
`useChatSse.ts` reads it directly, no cast. `agenticOpenApi.ts`,
`agenticApi.ts`, and their config are deleted — this was their last consumer,
closing out `FRONTEND-BACKLOG.md §7` entirely.

**Deliberately out of scope:** no retroactive backfill of `error`/`other`
misclassification in history rows written before this shipped (the
`mode="before"` coercion is what keeps them loadable, it does not rewrite
them); no per-provider GreenOps/cost impact (unrelated to `TokenUsageImpact` /
issue #2312).

---

### 8.47 ✅ `CorpusTreeService` truncation fix; paginated `list_documents_by_label` in its own capability (issue #2326, 2026-08-12)

**Problem.** `CorpusTreeService`'s size-budgeted folder-tree renderer had a
silent-truncation bug: `tree_builder.py::_render_budgeted_root`'s final
fallback rebuilt its candidate lines from bare folder headers only, discarding
whatever content depth-based pruning had already collapsed into them. A wide,
shallow match (e.g. 150 folders, one document each) let those 150 bare headers
fit comfortably under the char budget, so the response shipped
`truncated=True` with **zero** documents and **zero** omission message —
indistinguishable from a complete, empty corpus (regression test:
`test_wide_shallow_tree_never_reports_truncated_with_zero_omission_signal`).
Separately, `CorpusTreeService._resolve_leaves` resolved tree leaves via
`MetadataService.get_documents_metadata` → `store.get_all_metadata()` — an
unbounded `SELECT *` over the whole `metadata` table filtered in Python, run
on **every** `list_document_tree` call (`document_access` is `DEFAULT_ON`).

There was no agent-facing way to resolve a business label to *every* document
carrying it, exhaustively — only browsing (`list_document_tree`, a
size-budgeted folder tree) and single-document lookup.

**Fix.**
1. `_render_budgeted_root` now measures each candidate as the FULL block
   (folder header + whatever was already collapsed into it by depth-pruning),
   never a bare header — `truncated=True` can no longer ship without an
   explicit, accurate omission signal.
2. `CorpusTreeService._resolve_leaves` now calls new
   `MetadataService.get_documents_by_uids` (indexed `get_metadata_by_uids`,
   ReBAC-filtered after fetch) instead of the full-table scan.
   `get_metadata_by_uids` and its label-hydration query
   (`_hydrate_labels`, `postgres_document_store.py`) both chunk their
   `document_uid IN (...)` statements at `_BULK_UPDATE_CHUNK_SIZE` — the
   same constant `bulk_mark_vector_done` already chunks its updates with —
   so a tree spanning the full `_MAX_FOLDERS` (10,000 folders) stays well
   clear of a driver bind-parameter ceiling instead of sending one unbounded
   query.
3. **New port method** `DocumentTreePort.list_by_label(*, label, offset=0,
   limit=50) -> DocumentLabelPageResult` (`fred-sdk/contracts/runtime.py`) —
   flat, exhaustive, paginated label resolution, on the SAME port/adapter/
   client as `tree()` (`KfDocumentClient`/`DocumentTreeAdapter` each gain one
   more method) rather than a new port class: two distinct, unambiguous agent
   tools at the LLM-facing layer, one port at the plumbing layer. Backed by
   new `MetadataService.get_document_uids_with_any_label` (one ReBAC
   resolution + one indexed `label IN (...)` store query, OR-semantics across
   labels, UID-only, unpaginated — used by the non-paginated
   `get_documents_with_label`) and a separate paginated sibling,
   `get_document_uids_with_any_label_page`/`get_documents_with_label_page`
   (real `ORDER BY ... OFFSET ... LIMIT ...` plus a matching `COUNT(*)` pushed
   into the store query, not a fetch-everything-then-slice-in-Python — so
   enumerating many pages of a large match set does not repeat a full,
   unbounded label scan on each call; the ReBAC `lookup_user_resources` call
   itself still runs once per page, same cost every other paginated,
   authorized listing in this service already pays per call). KNOWN GAP,
   documented on the port method itself: does NOT accept `library_tag_ids` —
   Knowledge Flow's label resolution narrows only by document-level READ
   permission, never by folder/library scope, so an agent configured with
   `bind_libraries=True` still sees every readable document carrying a label,
   corpus-wide, through this method. Not silently implemented as a no-op
   parameter — flagged as follow-up work.
4. **New capability `document_label_search`**
   (`fred-runtime/capabilities/document_label_search/`), registered via its
   own `fred.capabilities` entry point, manifest `team_scope` left at the
   class default (`ADMIN_GATED` — same reasoning as `document_summarize`,
   §10.1: no config-shaped trigger a user can reason about, a team admin must
   opt an agent in explicitly). Owns exactly one tool,
   `list_documents_by_label`: one page per call (documents as `name [uid]`,
   `total`, `has_more`); the tool's docstring tells the model to call again
   with `offset=next_offset` and never report a count without checking
   `has_more`. Deliberately NOT added to `document_access` (`DEFAULT_ON`):
   bundling it there would mean every existing `document_access` agent —
   already in production — picks up a second, semantically-adjacent tool the
   moment it ships. Both tools answer "documents with label X"; the
   discriminating axis (where they sit vs. give me all of them) is a harder
   tool-selection call for the model than the pre-existing
   `search_documents_using_vectorization` vs. `list_document_tree` split
   (content question vs. structure question — a much clearer boundary in
   natural language), with a fail-quiet failure mode (a plausible-looking,
   silently-incomplete answer once a large match set hits the tree's size
   budget) instead of a fail-loud one. `list_document_tree` itself does no
   label filtering at all, by design — a folder tree is the wrong response
   shape for "give me every document labeled X".

**Backing HTTP route.** `GET /documents/by-label` (query-param transport) is
paginated: `offset`/`limit` query params, response `LabelDocumentsPage
{label, documents: [{document_uid, document_name}], total, offset, limit,
next_offset, has_more}` — a leaner response model than `BrowseDocumentsResponse`
(full `DocumentMetadata`), which the path-segment `GET /documents/by-label/{label}`
route keeps unpaginated for existing consumers. Both resolve through the same
`MetadataService.get_document_uids_with_any_label`; `document_label_search`'s
tool reaches the same route through `DocumentTreePort.list_by_label` — no new
route, no plumbing duplication.

**Bounded context.** `CorpusTreeService` is a read-only projection over the
already-ingested corpus — it stores no bytes, accepts no writes, and is
intentionally distinct from the future `WorkspaceService` (mutable,
persistent user/agent files, currently implemented under `/fs`). See
`FILESYSTEM.md` "Business labels vs. scope tags".

Tests: `test_corpus_tree_builder.py` (renderer invariant),
`test_corpus_tree_service.py`, `test_metadata_service_labels.py` +
`test_postgres_document_store_labels.py` (resolver), `test_metadata_labels_controller.py`
(pagination), `test_capability_document_access_1906.py` (tree tool unchanged,
2 params, no label awareness), `test_capability_document_label_search.py`
(new — registration, `ADMIN_GATED` default, tool behavior, real-adapter param
forwarding), `test_capability_endpoints_1974.py` (catalog advertisement list
gains `document_label_search`, sorted by id). Tracking:
[#2326](https://github.com/ThalesGroup/fred/issues/2326).

---

### 8.48 ✅ Reasoning stays ON/OFF per question — effort picker built and withdrawn same-day (2026-08-12)

A per-question `RuntimeContext.reasoning_effort` override (composer effort
picker, low/medium/high) was implemented and **withdrawn the same day**:
providers disagree on accepted values (measured: Mistral small rejects
low/medium with a 400 `Must be one of (none, high)` that fails the whole
turn), and the per-model declaration/snapshot machinery required to offer
only valid values wasn't worth the surface. Decision: the effort a reasoning
turn runs with is the ops-authored `settings.reasoning_effort` of the routed
profile, full stop — the user's per-question choice remains the §8.30
tri-state boolean, now presented as a right-edge composer chip
(model identity + Activé/Désactivé, `docs/swift/ux/COMPONENT-UX.md`). No
wire, contract, or enforcement change survives; this entry exists so the
next "let users pick the effort" idea starts from the measured constraint.

---

### 8.54 ✅ Ops name the model — `model_display_name` in `models_catalog.yaml` (2026-08-13, reduced 2026-08-18)

The composer chip derived its model label by splitting the capability id on
hyphens. That heuristic cannot tell a version separator from a variant one —
`claude-sonnet-4-6` rendered "Claude Sonnet 4 6" — and only whoever pinned the
model knows which it is.

**What survives.**

- `ModelProfile.model_display_name` (optional, per profile) in
  `models_catalog.yaml`. Display only: routing, enablement and the capability id
  still key on `(provider, name)`.
- `GET /agents/models-catalog` carries it as `ModelCatalogEntry.display_name`,
  taken from the first profile in the `(provider, name)` group that declares one
  — same first-seen rule as `description`. `CapabilityCatalogEntry` carries it
  as `model_display_name`; the multi-pod union keeps a name authored on one pod
  when another serves the model unnamed.
- The frontend prefers that string verbatim, then prettifies the real model
  `name`, then falls back to splitting the capability id.

**What was removed (#2387, 2026-08-18).** The original delivery path went
through two snapshot columns on `model_reasoning` — `display_name` and
`default_effort`, copied from the catalog entry when an admin toggled a model's
reasoning — and reached the composer on the `reasoning_toggle` control's
`params.display_name` / `params.effort`.

Both columns, both params, and the `ModelCatalogEntry.reasoning_effort` /
`CapabilityCatalogEntry.model_reasoning_effort` projections that fed them are
gone. The columns are dropped at the head of the chain, by `d5c9a1b73e60`.

**Correction (2026-08-20).** The two migrations that added them
(`c9e1f74b2a63`, `a7d2e9c41f38`) were first deleted outright, on the stated
premise that neither had shipped in a tagged release. That premise was wrong:
`code/v2.1.35` shipped with `a7d2e9c41f38` as its control-plane head, so every
instance on that release carries the id in `alembic_version_control_plane`.
Deleting the file makes the id unresolvable and alembic refuses to start — it
cannot place itself in the graph, so it cannot move forward either. Both
migrations are restored and stay in the chain permanently; only the columns go,
at the head, where every deployment reaches them by walking forward.

The premise was checked with `git tag --contains` on the commit that introduced
the migration, which returned nothing. On a repository that squash-merges, that
proves nothing — the tag holds an equivalent commit with a different identity,
so the original is never an ancestor. **Whether a migration has shipped is a
question about the tag's tree, not its ancestry**: use `git ls-tree -r <tag> --
<versions-dir>` and match on the revision id.

Two independent reasons:

1. The label rode on the wrong object. `params.display_name` named the model
   whose REASONING was enabled platform-wide, not the model a turn routes to, so
   the composer contradicted every platform binding and team override (§8.56).
   The label now comes from `EffectiveChatModel.display_name`, read live from
   the pod catalog entry for the model that actually answers.
2. The effort had no business being displayed. The composer's reasoning menu is
   a plain on/off; the level a turn runs with is the pod's ops-authored
   `settings.reasoning_effort`, applied live at model construction. Quoting it
   back at the user implied a per-question choice that never existed — the same
   confusion that got the effort *picker* withdrawn the same day it was built
   (§8.48).

`settings.reasoning_effort` in `models_catalog.yaml` is untouched and still
governs behaviour — only its display projection is gone. The staleness caveat
this section used to carry ("editing the catalog reaches the composer at the
next admin re-toggle") no longer applies: there is no snapshot left to go stale.

---

### 8.55 ✅ Trusted platform-wide `chat` model binding, resolved fresh per turn — issue #2365 (2026-08-15)

**What changed.** `BoundRuntimeContext.platform_chat_model_binding`
(`libs/fred-sdk/fred_sdk/contracts/context.py`) lets a platform operator
assert one authoritative `(provider, name, settings)` binding for the `chat`
capability that overrides whatever every pod would otherwise resolve
locally. Unlike `chat_default_profile_id`/`agent_profile_overrides` (§8.32),
it is never carried on the client-forwarded `RuntimeContext` at all — there
is no field for it there, by construction, so a forged or stale request body
cannot influence chat model selection. The runtime resolves it itself, fresh
on every managed turn (including HITL resume), on the same per-turn,
server-to-server `GET /teams/{team_id}/agent-instances/{id}/runtime` lookup
that already resolves `reasoning_enabled_model_ids` (§8.35) — one additional
indexed single-row read inside the same `asyncio.gather`, not a new round
trip.

**Precedence (unconditional, `RoutedChatModelFactory.select`,
`libs/fred-runtime/fred_runtime/model_routing/provider.py`).** For the
`chat` capability, when the binding is set it is returned immediately,
before the resolver — and therefore before the pod's static
`models_catalog.yaml` agent override and the team-policy fields in §8.32 — is even
consulted:

    platform_chat_model_binding  >  pod static agent_profile_overrides  >  team agent_profile_overrides / chat_default_profile_id  >  pod chat default

A team-level override only ever names a profile from *some* pod's local
menu — the exact limitation an operator-asserted binding exists to route
around — so a stale team choice can never silently defeat it.

**ReBAC exemption.** The resulting `ModelSelectionSource.PLATFORM_BINDING`
selection is exempt from the `usable_model_ids` `can_use` gate
`build_for_chat` otherwise enforces: the platform operator is the authority
on what is actually reachable/licensed in a deployment, so a team-level
restriction cannot veto it — the same trust relationship that lets an
org-admin already grant `can_use` for every team unconditionally, not a new
authorization surface being bypassed.

**Managed-only scope.** V1 populates this field only for managed
agent-instance execution — direct (non-managed) `agent_id` execution never
receives it and stays on pod-local routing. A managed turn that in turn
invokes a nested agent (`context.invoke_agent`) inherits the same trusted
binding through private runtime wiring (`LocalRegistryAgentInvoker`), never
through `RuntimeContext`, `PortableContext`, or any other client-reachable
channel.

**Settings boundary.** `ModelBindingSettings` is a strict, typed allowlist
(`extra="forbid"`) — no credential-designated field, no generic
auth/header/cookie/client passthrough container, and no `timeout`/
`http_client_limits` (removed deliberately: `fred_core.model.http_clients.
get_shared_stack()` is a first-call-wins process singleton, so a later
per-binding tuning request would be silently ignored, contradicting the
"takes effect on the very next turn" promise this feature makes elsewhere).
`provider` is restricted to `fred_core.model.models.ModelProvider`, and a
provider with additional required settings (`azure-openai`, `azure-apim`,
`vertex-ai`, `vertex-ai-model-garden`) is validated against those exact
requirements before persistence. Full settings contract, persistence
boundary, and admin API: `CONTROL-PLANE-PRODUCT-CONTRACT.md` §40.

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
3. Managed execution is authorized by the **pod itself**: a valid Keycloak JWT
   plus the team rule in §2.2 (OpenFGA for regular collaborative teams, with the
   documented intrinsic personal/service-agent cases). There is **no
   `ExecutionGrant`**.
4. The **pod is the execution authority**; control-plane resolves *where* an
   agent runs and issues no capability. It never proxies SSE, but the runtime's
   per-turn internal binding lookup currently keeps it on the pre-LLM critical
   path (§0.2).
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

---

## 14. Agent-to-Agent Invocation — `invoke_agent`

### Frozen surface

One agent invokes another as a **bounded function call**, not a handoff: the
caller passes a message (and optionally a typed output schema and a per-call
retrieval scope), keeps control of its own turn, and gets a typed result back.
There is no separate "handoff" primitive that transfers conversation control
to a callee — composition is always caller-keeps-control.

```
GraphNodeContext.invoke_agent(
    agent_id: str,
    message: str,
    *,
    prior_turns: tuple[ConversationTurn, ...] = (),
    output_schema: type[BaseModel] | None = None,
    scope: InvocationScope | None = None,
) -> AgentInvocationResult
```

`output_schema` and `scope` are optional and additive — every caller that
never sets them keeps working unchanged.

### Requesting several facts in one call — compose the schema, don't ask for a new primitive

`output_schema` is deliberately one schema per call. There is no separate
mechanism for requesting several independently-named structured facts from
one `invoke_agent` exchange, and none is planned — this matches every
comparable contract (MCP tool results, OpenAI/Anthropic structured outputs,
LangGraph sub-graph calls): richness comes from the shape of the schema, not
from the call protocol.

When a caller needs several related facts from one callee turn, the
canonical pattern is to compose one Pydantic model with multiple fields and
pass that as `output_schema` — not to invent a multi-schema call, and not to
make several sequential calls for facts that belong together. The
CMDB-trust-signals call below (Eva → Tessa) is the reference example: Eva
defines one combined `CmdbTrustSignalsOutput` schema covering every signal it
needs from that exchange, and gets them all back from a single `invoke_agent`
call.

Reach for several separate `invoke_agent` calls (run concurrently with
`asyncio.gather` if latency matters) only when the facts genuinely come from
independent callee turns — e.g. two different sub-agents, or two calls that
need a different `scope`/`prior_turns`. Do not reach for it just to avoid
defining a combined schema.

### Invariants — what is shared, what is not

Every `AgentInvokerPort` implementation (today only `LocalRegistryAgentInvoker`)
must uphold these, regardless of transport:

- **Identity is delegated, never re-authenticated or elevated.** The callee
  runs under the caller's own access token and `team_id`; ReBAC/document
  permissions are enforced against that identity, not a fresh one.
- **Scope narrows, never widens.** `InvocationScope` (`document_uids`,
  `library_ids`, `search_policy`) can only restrict what the callee's
  retrieval sees for that one call — it cannot grant access the caller's
  identity doesn't already have.
- **No shared mutable state.** The callee executes with its own fresh
  graph/ReAct state — no shared object, no shared long-term memory. (Its
  *checkpoint* isolation from the caller is a known gap — see below.)
- **No shared tools.** The callee uses only its own declared tools/MCP
  servers; the caller's tool access is never extended to it.
- **History is opt-in and minimal.** `prior_turns` forwards a curated
  `tuple[ConversationTurn, ...]` (`user_message`/`agent_response`/`agent_name`
  only) — never the callee's internal message trace — and is empty by
  default.
- **Typed output is optional and bounded.** When `output_schema` is given, the
  runtime forces and validates a schema-conformant result with a bounded
  retry (2 attempts); on persistent mismatch the call still returns
  (`structured=None`) rather than hanging.

### Boundary — same pod only

`invoke_agent` today only resolves agents registered in the calling pod's own
in-process registry. This is a **deliberate, hard boundary**, not a
placeholder: cross-pod/remote agent invocation is a **separate mechanism**,
requiring its own security review, never an invisible extension of this one.
See "Note of intention" below.

### Known gaps (tracked, not yet closed)

- **Composition depth / cycle limit.** Narrowed, not closed (§8.63): the
  invoker now counts depth on every re-entry and the `subagent` capability
  stops offering its tool at `max_depth`, but a Graph node or `TeamAgent`
  calling `invoke_agent` directly still has no bound of its own. Tracked as
  MEMORY-06 in
  [`../rfc/MULTI-AGENT-MEMORY-HARDENING-RFC.md`](../rfc/MULTI-AGENT-MEMORY-HARDENING-RFC.md).
- **Agent-scoped checkpoint isolation.** Checkpoint state is keyed by
  `session_id` alone, not by agent — a caller and a callee sharing one
  session can load or overwrite each other's checkpoint. Sidestepped for
  same-agent children, which run checkpointer-free (§8.63); still open for
  every cross-agent caller. Tracked as MEMORY-02 in the same RFC (proposed
  fix: `checkpoint_ns` derived from the executing agent, `thread_id` kept as
  `session_id`).

### Real-world adopter — fred-rags "move to cloud"

`fred-rags`'s `apps/rags-agents` pod (external repo) is a production consumer
of the typed/scoped contract: its cloud-migration-assessment agents (`Eva`,
`Chronos`) invoke sub-agents (`Tessa`, `Rico`) with `output_schema` +
`InvocationScope(document_uids=...)` to extract structured facts scoped to
specific documents, rather than free-text parsing and un-scoped retrieval. Its
producer/callee agents run inside the same user session (the MEMORY-02
scenario above) and its CMDB-trust-signals composition (Eva → Tessa) is
exactly the kind of multi-hop call the missing depth/cycle guard (MEMORY-06)
needs to cover.

### Note of intention — remote/Temporal transport (future, separate)

`AgentInvokerPort` and `AgentInvocationRequest`/`AgentInvocationResult` are
already designed to be transport-independent — in-process, HTTP, and Temporal
child workflow are all named in the contracts' own docstrings — and a full
HTTP/SSE implementation (`RemoteSseAgentInvoker`) already exists in
`fred-sdk`, unused by any pod today. Extending `invoke_agent` to cross-pod or
durable/Temporal execution is intentionally **out of scope for the
invariants above** and will get its own design pass when a concrete need
appears (pod discovery/topology, per `platform/PLATFORM_RUNTIME_MAP.md`, is
still a manually-maintained static catalog, not yet auto-discovered) — never an
implicit relaxation of the same-pod boundary.

See [`MULTI-AGENT-MEMORY-HARDENING-RFC.md`](../rfc/MULTI-AGENT-MEMORY-HARDENING-RFC.md)
for the two open gaps (MEMORY-02, MEMORY-06).

### 8.56 ✅ Pod advertises its own two precedence levels; one shared precedence implementation — issue #2387 (2026-08-17)

**Problem.** The composer labelled itself with the single model whose
*reasoning* a platform admin had enabled (§8.54's `model_display_name`, carried
on the `reasoning_toggle` control) — a value unrelated to routing. With a
platform binding (§8.55) or any override in force it therefore named a model
that was not answering, which reads to anyone testing model routing as "routing
is broken".

Telling the composer the truth means resolving §8.55's precedence chain
control-plane-side, and two of its four profile-valued levels live only in the
pod's `models_catalog.yaml`.

**`GET /agents/models-catalog` — two additive top-level fields.**

| Field | Meaning |
| ----- | ------- |
| `default_chat_profile_id: str \| None` | This pod's `default_profile_by_capability.chat` — the LOWEST precedence level. `None` when the catalog declares no chat default. |
| `agent_chat_profile_overrides: dict[str, str]` | This pod's ops-authored `agent_profile_overrides`, RESTRICTED to entries targeting a chat profile — the HIGHEST level below the platform binding. |

Both are pod-level, not per-model, so they sit beside `models` rather than on
each entry: `aggregate_capability_catalog` unions entries by id across pods, and
a pod-level value riding on an entry would be overwritten or unioned
nonsensically (the failure mode §8.7's `_union_profile_ids` guard already
describes).

The override map is filtered pod-side, mirroring the runtime's long-standing
rule that a static override naming a profile of a different capability is
skipped, not fatal. An entry naming a profile absent from the catalog is dropped
for the same reason: neither can ever route a chat turn.

**No new field for the concrete pair.** `CapabilityCatalogEntry.name` already
carries the model name for a `kind="model"` entry, and `id` identifies the
`(provider, name)` pair uniquely, so the composer needs nothing more. Worth
recording for whoever ever needs the provider on its own:
`model_capability_id` NORMALIZES characters outside the id charset to `-`, so
`id` is **not reversible** into the real pair and a split will not recover
it — it would need its own carried field.

**One precedence implementation, shared.** `resolve_team_override`
(`fred_runtime/model_routing/resolver.py`) is **deleted**, not renamed. The
single implementation is now
`fred_sdk.contracts.context.resolve_effective_chat_profile`, called by both
`RoutedChatModelFactory.select` and control-plane. It returns a
`ChatProfileResolution` (`profile_id` + `ChatProfileOrigin`), and the runtime
maps origin → `ModelSelectionSource` through an explicit table so the
`[V2][MODEL_ROUTING]` log line operators grep is unchanged: both team levels
still report `team_policy`, with `profile=` distinguishing them.

The precedence itself is unchanged from §8.55 — the pod static override remains
the operator's local escape hatch above every team level. `ModelRoutingResolver`
gains `agent_overrides_for(capability)` / `default_profile_id_for(capability)`,
precomputed at construction (the policy is immutable for the pod's lifetime;
`select` runs per turn).

**Not in `ExecutionPreparation`, deliberately.** Resolving this needs the pod
catalog, and prepare-execution runs on **every send** while being contractually
free of pod-catalog fetches. The read lives on control-plane's
`GET /teams/{team_id}/routing-policy/effective-chat-model` instead — per
chat-page open, same cost profile as `available-models` beside it. See
`CONTROL-PLANE-PRODUCT-CONTRACT.md` for that endpoint.

**Rolling upgrade.** A pod not yet advertising the two fields reads as
"declares no chat default and no static override", so the composer shows no
model rather than guessing one — the same fail-quiet direction
`model_chat_profile_ids` takes.

**`params.model_id` / `params.display_name` are removed from the
`reasoning_toggle` control.** They carried the single reasoning-enabled model's
identity, which the composer displayed as its model label — the root of this
issue. The control now ships only what it is authoritative about (`default`,
`effort`).

### 8.57 ✅ Per-tool and per-message token badges report marginal cost, not billed totals — issue #2403 (2026-08-21)

**A tool row claimed a tool had consumed 17 559 tokens when it had consumed
none.** `ToolCallRuntimeEvent.token_usage` carried the usage of the model call
that *decided* the tool call, and the trace UI rendered it on the tool's row
(`toolCallTokenUsage` in `traceUtils.ts`). A tool call costs nothing by itself;
what the row was actually displaying was the whole prompt of the deciding call.
The final-answer badge had the mirror problem: it showed the turn total summed
across every model call, which the conversation header already sums again —
so the per-message figure repeated the header while being an order of magnitude
larger than what the turn had added.

Field trace of one 2-tool turn, before the fix:

| model call | input | output | rendered as |
| --- | --- | --- | --- |
| 1 (decides tool 1) | 17 550 | 9 | tool row 1: "17 559 tokens" |
| 2 (decides tool 2) | 19 709 (17 520 cached) | 83 | tool row 2: "19 792 tokens" |
| 3 (final answer) | 19 942 | 64 | — |
| turn total | 57 201 | 156 | answer badge: "57 357 tokens" |

**The measurement.** Within a turn the context only grows, so the input size of
the LAST model call is the context the turn leaves behind — no estimation, no
tokenizer. `FinalRuntimeEvent` gains one field:

| Field | Meaning |
| --- | --- |
| `context_tokens: int \| None` | `input_tokens` of the turn's LAST model call — the context size at turn end |

`ToolCallRuntimeEvent.token_usage` is **removed**, and tool rows now carry no
token figure at all: a tool call costs nothing by itself, so the row shows
latency only. (An intermediate version of this work added a
`tool_context_cost` map attributing each round's context growth per `call_id`;
it served its diagnostic purpose — proving the tools cost ~2 300 tokens, not
~17 500 — and was then removed along with its display as UI weight. The
measurement is recoverable from this issue's history if a per-tool figure is
ever wanted again.) `token_usage` on `FinalRuntimeEvent` is unchanged and still
carries the billed total.

**The conversation header sums what the messages display, not the invoice.**
Summing billed usage there put `72 595` above two messages badged `16 871` and
`3 136` — the same parts-versus-whole mismatch as the tool rows, one level up.
`conversationTokenTotals` (`toThreadMessages.ts`) now adds the per-message
figures, so the thread reconciles with its header; because each turn
contributes `contextTokens(T) − contextTokens(T−1)`, that sum telescopes to
`contextTokens(last) + every output` — the tokens the conversation actually
holds. The billed total is still computed and surfaced, in the header tooltip.

The per-message figure is derived, not transported:
`new_input(T) = context_tokens(T) − context_tokens(T−1)`.
`ChatMetadata` gains `context_tokens` (assistant-final rows) so a reloaded
conversation recomputes identically.

**The anchor is the previous `context_tokens` alone, deliberately not
`+ output_tokens(T−1)`.** Adding the previous turn's output assumes all of it
returns in the next prompt, and it does not: reasoning tokens are counted in
`output_tokens` but dropped from replay (`CheckpointHygieneMiddleware` —
"reasoning from closed turns is dropped"). That over-subtracted by however much
the model had reasoned. Observed live: a turn whose two tool rows read `+2254`
and `+332` displayed `2534` new input tokens — the parts exceeded the whole,
and the implied question length was −52. Anchoring on `context_tokens` alone is
fully observed and monotonic. The consequence is that the previous answer
counts as output when produced and as input when re-sent; both are real costs
at different rates, so this is not double counting.

**Graph agents do not set it.** The measurement assumes one context growing
across consecutive calls, which a graph's independent nodes do not share. Their
badges fall back to the billed total rather than showing a number that does not
mean what it says.

**What the UI ends up showing.** Header: `Total: <sum of the message badges>`.
Message: `↑<new input> · ↓<output>`, each arrow titled "N tokens sent" /
"N tokens received" on hover. Tool row: label, latency, nothing else. No
tooltip explains the accounting model — how the figure is derived is an
implementation detail, and an earlier version that spelled it out in three
tooltips was rejected as noise.

**Consequence worth knowing:** a conversation's FIRST message still shows its
full prompt as new, because on turn 1 the system prompt and tool schemas
genuinely are. That makes the fixed base cost a single legible line item
instead of noise repeated on every turn — relevant while the baseline itself
stays large (see below).

**Out of scope, measured but deliberately not changed.** The ~16 700-token
baseline on a bare "Hello" is not history — it is the tool definitions, sent
twice per model call:

1. Every `FastApiMCP` server in `knowledge-flow-backend/main.py` sets
   `describe_all_responses=True, describe_full_response_schema=True`, which
   embeds each route's full JSON response schema in its tool description.
   Measured: Tabular's 5 tools go 25 505 → 10 323 chars with the flags off,
   Vector Search's 4 go 22 892 → 9 368; the handwritten docstrings survive
   intact, only the generated schema dump is dropped.
2. `build_runtime_tool_prompt_suffix` (`react_tool_binding.py`) then re-emits
   every tool's description into the system prompt, on top of the `tools` API
   parameter that already carries it.

Both are real reductions and neither was taken here — this change is display
and accounting only, kept separate per the consolidation rule against bundling
a reduction with an unrelated fix.

### 8.58 ✅ `agent.turn_completed` carries `session_id` — issue #2426 (2026-08-25)

**Problem.** Conversation depth (how many messages a conversation actually
gets) is not derivable from any existing KPI row. `agent.turn_completed` is the
one event emitted once per turn, but its dims stopped at the agent/model
identity — with no conversation key, turns could not be grouped per session.

**`agent.turn_completed` dims — one additive field.**

| Field | Meaning |
| ----- | ------- |
| `session_id: str \| None` | The conversation the turn belongs to. `None` for a turn with no session (the same cases the ring-buffer record already tolerates). |

`agent.turn_error_total`, which reuses the same dims dict, carries it too.

**OpenSearch only — not a Prometheus label.** The cardinality protection is
`PROMETHEUS_ALLOWED_LABELS` (`fred_core/kpi/prometheus_kpi_store.py`), an
allowlist: `session_id` is absent from it, so it is stripped before Prometheus
label resolution while the OpenSearch KPI store keeps the full dims. This is the
established pattern, not a new one — `identity_kpi_dims`
(`fred_runtime/react/middleware/shared.py`) emits `session_id`/`user_id`/
`team_id` the same way. `_emit_turn_completed`'s old comment claimed the
exclusion itself was the protection; it was rewritten to point at the allowlist.
`exchange_id` and `user_id` are deliberately still not carried here — no query
needs them, and per-turn tracing already has them in history rows and SSE logs.

**No index-mapping change.** `dims.session_id` is already an explicit `keyword`
in `KPI_INDEX_MAPPING` (added for the CTRLP-12 A3 erasure `update_by_query`), so
the new dim is `term`-aggregatable on existing indexes with no migration.

**Consumer.** Control-plane's `conversation_depth` KPI preset (`GET
/kpi/presets/conversation_depth`) — a `terms` agg on `dims.session_id` behind an
`exists` filter, so pre-#2426 turn rows are excluded rather than collapsing into
one bucket.

---

### 8.59 ✅ `ui_parts` persisted on `ChatMetadata` - issue #2462 (2026-08-28)

**The bug.** A conversation reloaded from history came back with its answer text
and its source cards, and with **every capability card missing** - a filled deck,
a written document, a link, a map. Generating a deck and pressing F5 a second
later was enough to lose it.

**Why.** `ChatMessage.parts` is a CLOSED discriminated union
(`fred_core/history/history_schema.py`) - text, code, image_url, tool_call,
tool_result, hitl_request, hitl_response. No `UiPart` in it, and `ChatMetadata`
carried `sources` but nothing for chat parts. The runtime emitted them correctly
(`FinalRuntimeEvent.ui_parts`, aggregated across every tool of the turn), the
live SSE stream rendered them, and then nothing wrote them down.

**The fix - one additive metadata field**, mirroring `sources` exactly.

| Field | Meaning |
| ----- | ------- |
| `ChatMetadata.ui_parts: list[dict]` | The turn's chat parts, on the assistant/final row. Empty list when the turn produced none. |

`agent_app.py::_write_turn_history` fills it from the `final` payload's
`ui_parts`, keeping only object entries.

**Raw objects, on purpose.** `UiPart` is an OPEN union assembled at pod boot from
the installed capabilities (`fred_sdk.contracts.ui_part_union`), and fred-core
sits BELOW fred-sdk - there is no closed type to validate against there. That is
also why `MessagePart` stays closed and these parts do not live in `parts`:
that union is closed precisely to validate storage, and opening it would mean
accepting unvalidated dicts in the column.

**Frontend.** `uiPartsOf` (`rework/utils/traceUtils.ts`) reads both carriers -
inline `parts` for a streamed message, `metadata.ui_parts` for a stored one -
deduplicated by identity, so a message carrying a part on both sides renders one
card. Nothing else changed: the part-renderer registry still decides at render
time what it can draw and skips unknown kinds.

**Migration.** None. The field defaults to an empty list, so rows written before
this change read back as "no cards" - exactly what they render today. Their parts
are not recoverable; they were never stored.

---

### 8.60 ✅ `document_similarity` capability + `DocumentSimilarityPort` - issue #2461 (2026-08-28)

**Was**: Knowledge Flow shipped targeted similarity / comparison search in
`POST /vector/similarity-search` (issue #1772, `DESIGN.md` §4), but a Fred agent
could only reach it over the Text MCP server. There was no first-order path, so
#1772's last acceptance criterion - a comparison agent calling it directly
instead of fetching everything and filtering client-side - stayed open.

**Now**: a real capability, `document_similarity`, registered through the
`fred.capabilities` entry point alongside its `document_access` /
`document_summarize` / `document_verbatim` / `document_extract` siblings and
`ADMIN_GATED` like them. One tool, `find_similar_passages(anchor,
document_uids, top_k)`, reaching Knowledge Flow through a new typed port,
`RuntimeServices.document_similarity` (`DocumentSimilarityPort.find_similar`),
behind `DocumentSimilarityAdapter`. `VectorSearchClient.similarity_search`
carries the wire call.

**Why a capability and not a built-in tool ref.** The first cut of this issue
ported the `mvp/rags-support` shape verbatim: a `knowledge.similarity_search`
entry in the `fred-sdk` built-in catalog, next to `knowledge.search`. That was
withdrawn before merge. `capabilities/document_access/capability.py` already
documents the built-in surface as back-compat whose retirement is a follow-up,
so adding to it would have meant shipping a new tool onto a surface with a
scheduled end, and a second, differently-scoped comparison path the moment
anyone wired both. The capability path also buys what the built-in cannot
express: per-instance config, admin gating, and team scoping.

**Why its own port rather than a method on `DocumentSearchPort`.** Two reasons,
one structural and one about safety. Structural: every document feature here
already has its own optional port (`document_tree`, `document_summarize`,
`document_markdown`, `document_extraction`), and adding an abstract method to a
published SDK ABC breaks every out-of-tree implementor. Safety: the two ports
enforce different things. Under `search(...)` the document uids come from the
capability's stored config, so narrowing them against the session binding is a
formality. Under `find_similar(...)` they come from the MODEL, on the call - so
that seam is the only thing between an LLM-named uid and a document the user
never put in this conversation. It returns `DocumentSearchResult` rather than a
near-identical twin: both modes produce ranked `VectorSearchHit`s.

**Three deliberate behaviours**, each pinned by a test:

- **An empty target never widens, and never reads as "no matches".** Targeting
  is the point of the mode. A missing, empty, or non-list `document_uids` is
  answered as an `is_error` artifact and never reaches the port. If narrowing
  against the session binding empties the set, the adapter raises the new
  `DocumentScopeRefusedError` rather than calling Knowledge Flow with an empty
  target list (which downstream reads as "no targeting") - and rather than
  returning no hits, which the model cannot tell apart from a genuine no-match
  and would report as "nothing in that document resembles this passage" about a
  document it never searched. The capability renders that refusal as its own
  `is_error` result naming the out-of-scope uids, not through
  `document_tool_failure` - nothing failed downstream, so the transport wording
  would be a lie.
- **A weak match stays citable**: `select_citable_sources(hits,
  min_score_ratio=0.0)`. That helper excludes two things
  (RAG-DATASET-DISCOVERY-RFC.md §7) and only one applies here. Dataset-pointer
  chunks are still never citable - metadata, not content. The score-ratio half
  is switched off: it cuts corpus-wide noise relative to the best match, and the
  caller named these documents, so a weak match is a real finding about them,
  often the interesting one. Passing `min_score_ratio=0.0` rather than
  `tuple(hits)` is what keeps the first exclusion - an easy distinction to lose.
- **`general_only` is honoured**, as in `_invoke_knowledge_search`: corpus
  retrieval turned off for the turn is off for every corpus tool, and naming
  target uids does not opt back in.

**Bounded transient retry**, in `VectorSearchClient.similarity_search` only:
`KfBaseClient._request_with_token_refresh` retries a 401 and nothing else, and
no caller above retries either, so one dropped connection failed a whole
comparison run - which fans out one call per anchor passage. Two jittered
retries, scoped to this method rather than the shared base client so
`search`/`rerank` keep their behaviour. What is retried is drawn tightly around
one question - could the work already be in flight, and would re-issuing help?

- retried: connection errors, connect timeouts, **pool timeouts** (no
  connection was ever acquired, so nothing was sent), and 502/503/504;
- not retried: read and write timeouts - Knowledge Flow may still be reranking
  the first request, so re-issuing multiplies load on an already-slow backend
  rather than recovering, which the fan-out then multiplies again;
- not retried: a plain 500, and no 4xx. Knowledge Flow's controller wraps every
  unexpected exception in a 500, so retrying one buys three full
  pool-and-rerank round trips before failing anyway.

**Its own read timeout**, `RuntimeTimeouts.similarity_read` (default 90s,
mirroring the `summarize_read` precedent and applied per-request the same way).
Knowledge Flow retrieves a candidate pool of up to 100 chunks and cross-encodes
all of them inside one request, making this the heaviest read on the vector
path; the shared 30s default is what a plain `search` is sized for. It is also
the one failure the retry above deliberately will not recover from, which makes
a generous ceiling the only defence.

**The tool points the model at the corpus, not at attachments.** Knowledge Flow
runs this mode with `include_session_scope=False` ("comparison is over the
corpus targets, not chat attachments"), so a file attached to the conversation
is not searchable here and its uid would return zero hits. The tool docstring
says so explicitly, because the sibling document tools DO accept attachment
uids and a model that carried that habit over would read the empty result as
"nothing matches".

**Frontend.** It rides the **team-resources** pack (`toolPacks.ts`), corpus-only,
not the document-reading one. Two reasons, and the first is what settles it: the
tool takes document uids it cannot produce, and `document_access` - the pack's
uid source, through `list_document_tree` and the `uid` on every search hit -
lives here. A document-reading pack that carried it alone would hand an agent
three uid-taking tools and no way to obtain one. Second, it belongs here anyway:
Knowledge Flow runs this mode over the corpus with `include_session_scope=False`,
so it is a search mode, not a reading tool, and it contributes nothing to an
attachments-only agent - hence `add(CAP_DOCUMENT_SIMILARITY, nextCorpus)` in
`withResourceState`, which is what actually selects the pack's capabilities
(`enablesCapabilityIds` documents an intent pack, it does not drive it).

Fixed alongside, and independent of this capability: `derivePackChecked`
required EVERY id in a pack to be selected while `applyPackToggle` only ever
adds ids the admin enabled, so a plain pack containing anything unavailable to
the team could not be switched on at all - flip it, the missing member is never
added, the derived state reads false again - while switching it off still
stripped the rest. It now takes `availableIds` and derives from the members the
team can actually select.

### 8.61 ✅ ReAct V2 checkpoints are always unnamespaced - issue #2479 (2026-08-31)

**Was**: every ReAct V2 HITL resume dead-ended in
`409 "No pending checkpoint was found for this session."`. The paused
checkpoint existed, with its `__interrupt__` write; the admission gate
(§8.39 layer 2) was reading in the wrong place.

**Why**: LangGraph resets `checkpoint_ns` to `""` for every non-nested run
(`pregel/_loop.py::PregelLoop.__init__`). A per-agent namespace configured
on a compiled root graph therefore never reaches storage. The executor
passed one anyway, while the gate and the `checkpoint_hitl_claim` key both
read at `agent_instance_id` - so the write and the read never met. The
hand-rolled Graph runtime is unaffected: it calls `aput` itself, so its
namespace is real.

**Now**:

- ReAct V2 stores and reads unnamespaced. The executor no longer configures
  a `checkpoint_ns` (it was inert), and the HITL claim keys on `""`.
- `_resume_checkpoint_namespaces` picks the candidate namespace from the
  request's own resume identifier - `checkpoint_id` is Graph V2's,
  `interrupt_id` is ReAct V2's. A `checkpoint_id` resume probes the agent
  namespace only, since the Graph executor reads nowhere else and a gate
  that waved it through would fail mid-stream, past the point a 409 can be
  sent. An `interrupt_id` resume probes `""` first, keeping the agent
  namespace for a Graph pause that never stamped a `checkpoint_id`. The gate
  runs before target resolution, so it cannot know the runtime kind directly.
- `test_langgraph_resets_root_checkpoint_namespace` pins the LangGraph
  behaviour: a version bump that changed it fails a test instead of
  silently moving live checkpoints out of the gate's reach.

**Still open**: isolating agent checkpoints within a shared session, the
goal of #2415. `checkpoint_ns` cannot deliver it for a root graph - the only
LangGraph-native lever is `thread_id`, which touches
`checkpoint_thread_owner`, per-user erasure, and session deletion. Tracked
in issue #2481; ReAct agents currently share the session's checkpoint thread.

---

### 8.62 ✅ `AgentDefinition` declares its reasoning defaults; `default_tuning` carries them — issue #2473 (2026-08-28)

**Additive SDK surface.** `AgentDefinition` gains two declarable fields,
`reasoning_enabled` and `reasoning_default_on` (both default `False`), and
`AgentTuning` gains `reasoning_default_on` beside the `reasoning_enabled` it
already had. `_definition_to_agent_tuning` (`app/agent_app.py`) now projects
both onto the `default_tuning` a pod advertises on `/pod/v1/agents/templates`;
it previously projected only `role`/`description`/`tags`/`fields`, which pinned
both fields `False` on the wire regardless of what a definition declared.

**Why the pod side matters.** REASON-01 level 3 is an agent property, and
Amendment B's `reasoning_default_on` seeds where the composer's toggle starts.
Both were reachable only per instance, through the agent-creation form — so a
template could not express "this agent's job needs reasoning". The wire already
carried `default_tuning` as a full `AgentTuning`, so no new transport was
needed; the projection was the whole gap.

**No runtime behaviour change.** These fields are declaration only. Nothing in
the execution path reads them: reasoning is still turned off at the single
`RoutedChatModelFactory.build_for_chat` point (§8.48), against
`RuntimeContext.reasoning` (level 4) and `reasoning_enabled_model_ids` (level
2). A template declaring `reasoning_enabled=True` on a deployment where no model
has its reasoning enabled produces no composer control and no reasoning turn.

**Rolling upgrade.** Both models default the fields to `False`, so a pod
predating #2473 advertises a `default_tuning` without the keys and a newer
control-plane reads both as `False` — never inventing an offer no template
declared. Consumer side and the seed-not-gate semantics:
`CONTROL-PLANE-PRODUCT-CONTRACT.md` §33 addendum (2026-08-28).

**Adopter.** `fred_agents.platform_ops` declares both `True` — a diagnostic
agent whose turns are inherently multi-step.


### 8.63 ✅ Sub-agent invocation: same-agent children, bounded depth, `execution_error` mapped — issue #2525 (2026-09-03)

The ReAct side of `invoke_agent` (§14). A `subagent` capability
(`libs/fred-capability-subagent`) gives an agent one tool, `run_subagent`,
that runs a fresh-context copy of the calling agent. Design and deferred
tiers: `../rfc/SUBAGENT-CAPABILITY-RFC.md`.

**Same-agent children inherit the parent turn; cross-agent children do not.**
Before this, a child invoked through `LocalRegistryAgentInvoker` reached
`_iterate_runtime_event_payloads` with no `tuning`, no `capability_registry`,
no `team_settings`, no `agent_instance_id`, no `exchange_id` and no
`reasoning_enabled_model_ids` — so it had **no capabilities and no tools at
all**. That is unchanged for a child naming a *different* agent, which must
still be resolved on its own terms. A child naming the **same** `agent_id` now
inherits all of those, plus the parent's `turn_options` and the selections on
its `RuntimeContext` (`selected_document_uids`, `search_policy`, `language`,
…), so a user who narrowed their agent to one folder gets children searching
that folder rather than the whole corpus.

**A same-agent child runs the parent's own definition, not the registry
template.** `_ParentTurn` carries it. The registry holds templates, and only
`_apply_runtime_tuning` turns an instance's `selected_capability_ids` into the
`default_mcp_servers` that `_build_agent_settings` hands `FredMcpToolProvider`
— so forwarding `tuning` alone left the child with the native capability block
but **no MCP tools at all**, plus the template's system prompt.

A caller-supplied `InvocationScope` still applies **on top** of those inherited
selections, exactly as it does for a cross-agent call — it replaces the
document/library/policy keys rather than intersecting with them, so a Graph
caller invoking a same-agent child can widen them (the tracked #1859 shape).
`run_subagent` never sets `scope`, so the capability's own children cannot;
closing it for every caller is #1859's job, not this entry's.

All of it travels on a **private attribute of the invoker**
(`_ParentTurn`), the `platform_chat_model_binding` doctrine (§8.55): never on
`RuntimeContext`, `PortableContext` or `AgentInvocationRequest`, so a caller
can neither read nor forge it. The request's `PortableContext` becomes a
*declaration* the invoker verifies — a same-agent child whose claimed
`user_id`/`session_id`/`team_id` differ from the calling turn's is refused —
rather than the channel the child's context is built from. The child does
**not** inherit `context_prompt_text`, `attachments_markdown`, the resume
fields, or the access token (which reaches it as an explicit parameter).

**Composition depth is now bounded on this path.** `CapabilityContext` gains
`invocation_depth: int = 0` (additive; threaded from
`_iterate_runtime_event_payloads` through `_build_capability_block` into every
capability context). The counter lives on the invoker, which re-enters the
turn path at *d+1* on **every** invocation, cross-agent included — depth is a
property of the call stack, not of an agent's identity, so an A → B → A cycle
is bounded too. Enforcement is capability-side, in `tools()`: at `max_depth`
(clamped config, default 3, ceiling 5) the tool is simply not returned, so a
leaf child is never shown a delegation it would only be refused. There is
deliberately **no second limit** in the invoker — one bound, one place. This
narrows, but does not close, the MEMORY-06 gap listed in §14: Graph and
`TeamAgent` callers still have no bound of their own.

**A same-agent child runs without a checkpointer.** `RuntimeServices` is built
fresh per request, so this is a per-run substitution
(`_build_runtime_services(use_checkpointer=False)`), not a change to the pod's
checkpointer. Without it the child would map the parent's `session_id` to
LangGraph's `thread_id`, load the parent's checkpoint — seeing the whole
conversation — and overwrite it mid-turn. Cross-agent children keep today's
behaviour byte for byte; the MEMORY-02 gap in §14 stays open for them. Two
consequences, both accepted: a child cannot be resumed, and therefore cannot
be paused for human approval (HITL stripping is a follow-up — until it lands,
enable `subagent` only on agents with no approval-gated tools).

**`CapabilityIdentity` gains `agent_id`** (additive, default `None`): the
template/definition id beside the `agent_instance_id` it already carried. A
capability that needs it and finds it `None` must fail loudly, never guess.

**`execution_error` is mapped.** `LocalRegistryAgentInvoker` handled `final`,
`assistant_delta` and `node_error` but not `execution_error` — the terminal
event a raising child ends its stream with. Every caller of `invoke_agent`
(the `fred-rags` pod included) therefore received `is_error=True` with an
**empty** message, which a model reads as "the callee answered nothing". The
invoker now returns the event's real `message`.

**Not in this change** (tracked separately): HITL stripping, per-child token
accounting (`agent.subagent_turn_completed`), child `sources`/`ui_parts` on
`AgentInvocationResult`, and the `system_prompt` override on
`AgentInvocationRequest` — so §14's frozen request/result shapes are
unchanged here.

**And, explicitly, no bound on fan-out.** Depth bounds height; nothing bounds
how many children one assistant message launches, and they run concurrently in
one pod against a shared connection pool. `max_tool_calls_per_turn` is not that
bound — it is per graph run, and a child is its own graph run, so it resets at
every level; nor does the per-child content cap compose. Deliberate for the
POC, to be settled with POC data — see issue #2531 and
[`../rfc/SUBAGENT-CAPABILITY-RFC.md`](../rfc/SUBAGENT-CAPABILITY-RFC.md) §5.5.
Until then it is a local/POC surface: an admin must enable it per team
(`ADMIN_GATED`), and no agent selects it by default.
