# Runtime Execution Contract — Phase 1 + Phase 2 Continuity

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

## 1. Goal

Establish `fred-sdk` as the single authoritative source of truth for the
**secure, team-scoped execution contract** between the frontend and agentic
runtime pods.

Every agent execution is:
- attributable to `user_id + team_id + agent_instance_id`
- authorized by a control-plane-issued `ExecutionGrant`
- scoped to a `session_id` for multi-turn continuity
- optionally resumable from a `checkpoint_id`
- observable through enriched trace/KPI/metrics metadata that preserves the
  same execution identity end-to-end

---

## 2. Frozen Contract — `fred-sdk/contracts/execution.py`

### 2.1 Identity models

| Model | Fields | Purpose |
|---|---|---|
| `ActorContext` | `user_id`, `principal` | User identity for audit/diagnostics |
| `TeamContext` | `team_id`, `team_type` | Team scope; always mandatory |
| `ExecutionTarget` | `agent_instance_id`, `underlying_agent_ref` | Managed instance reference |
| `TraceContext` | `request_id`, `trace_id`, `correlation_id`, `session_id`, `checkpoint_id` | Observability across services |

### 2.2 Authorization envelope — `ExecutionGrant`

Issued exclusively by **control-plane**. Runtime pods validate but never issue.

Key fields:
- `user_id`, `team_id`, `agent_instance_id` — the authorized execution scope
- `action` — `execute` or `resume`
- `audience` — intended runtime service URL (reject if mismatch)
- `issued_at`, `expires_at` — Unix timestamps; runtime must reject expired grants
- `scopes` — optional permission set
- `storage_scope` — logical persistence namespace (MUST NOT be a connection string)

Validation method: `grant.validate_for_execution(expected_action, expected_team_id, expected_agent_instance_id)` returns a list of violation strings (empty = valid).

**Architectural constraint:**
> `ExecutionGrant` MUST NOT contain infrastructure secrets, database
> credentials, or internal service connection strings. Any such field is a
> contract violation.

Phase 1 implements structural validation only (expiry, field consistency).
Cryptographic signature verification is deferred to a subsequent phase once
key distribution from control-plane is defined.

### 2.3 Execution request — `RuntimeExecuteRequest`

The frozen frontend-facing request body for `/agents/execute` and
`/agents/execute/stream`.

Execution paths:

1. **Managed** (preferred for frontend): set `agent_instance_id` + `execution_grant`
2. **Direct template** (dev/internal only): set `agent_id`; no grant required

Session/checkpoint semantics:
- `session_id` — primary continuity key; keep stable across turns and HITL resumes
- `checkpoint_id` — optional; enables precise resume from a graph snapshot
- `resume_payload` — HITL answer data; when set, `input` is ignored and the
  graph resumes from the checkpointed state

Compatibility helpers (transitional, will be removed):
- `effective_user_id()` — reads from grant first, then `runtime_context`
- `effective_team_id()` — same
- `to_legacy_context()` — bridges to internal plumbing; not part of the frozen contract

### 2.4 Grant validation helper — `validate_execution_grant`

```python
from fred_sdk.contracts.execution import validate_execution_grant, ExecutionGrantViolation

try:
    validate_execution_grant(request)
except ExecutionGrantViolation as exc:
    raise HTTPException(403, detail=str(exc))
```

For managed execution (`agent_instance_id` set), raises `ExecutionGrantViolation`
if the grant is absent, expired, or structurally inconsistent.
For direct template execution (`agent_id` set), is a no-op.

---

## 3. Runtime Routes — `fred-runtime/app/agent_app.py`

Both execute endpoints accept `RuntimeExecuteRequest` and call
`validate_execution_grant` before invoking the agent:

| Route | Handler | Contract |
|---|---|---|
| `POST {base_url}/agents/execute` | `execute()` | `RuntimeExecuteRequest` → `RuntimeEvent \| RuntimeErrorPayload` |
| `POST {base_url}/agents/execute/stream` | `execute_stream()` | `RuntimeExecuteRequest` → `StreamingResponse` (SSE) |
| `GET {base_url}/agents/sessions/{session_id}/messages` | `get_session_messages()` | `list[ChatMessage]` |
| `GET /v1/models` | `list_models()` | `OpenAIModelList` |

Internal bridge: `_to_internal_request(r: RuntimeExecuteRequest)` maps to the
legacy `_AgentExecuteRequest` for backward-compatible internal plumbing. This
bridge is transitional and will be removed once all internal helpers migrate to
the typed contract fields directly.

Managed execution invariant:
- even if a runtime pod also exposes a raw `agent_id` capability for
  dev/internal compatibility, the managed team-scoped path
  (`agent_instance_id` + `ExecutionGrant`) is the authoritative frontend path
- the same underlying capability must still behave correctly when called
  through the team-scoped managed path
- all runtime-facing side effects of that managed path must retain team-scoped
  identity in history, checkpoints, metrics, logs, and tracing

---

## 4. OpenAI Compatibility — `fred-sdk/contracts/openai_compat.py`

The `/v1/chat/completions` endpoint is a **secondary interface** for external
tools (Open WebUI, openai-python SDK). It is not the primary frontend protocol.

Key models:

| Model | Purpose |
|---|---|
| `OpenAIChatRequest` | Request body; `model` maps to `agent_id` |
| `OpenAIModelCard` / `OpenAIModelList` | Typed `/v1/models` response |
| `OpenAICompletionChunk` | One SSE chunk in the stream |
| `OpenAIDelta` | Content delta; `tool_calls` uses typed `OpenAIToolCall` |
| `OpenAIToolCall` / `OpenAIToolCallFunction` | Typed tool call (replaces `dict[str, Any]`) |
| `FredChunkMetadata` | `fred` field extension: sources, HITL, errors, ui_parts |

Fred-specific metadata travels in the top-level `fred` field of each chunk.
Standard OpenAI clients ignore unknown top-level fields.

**Current limitations of the OpenAI compat layer vs the native protocol:**
- System messages in the request are currently ignored (agent prompt is defined by pod registration)
- Team-scoped execution (`team_id`) is passed via `X-Fred-Team-Id` header only
- `ExecutionGrant` is not yet threaded through the `/v1` surface
- HITL semantics are expressed but cannot be fully resumed via standard OpenAI clients

---

## 5. Runtime Event Models — `fred-sdk/contracts/runtime.py`

Runtime events emitted during agent execution (both native SSE and OpenAI compat):

| `RuntimeEventKind` | Meaning |
|---|---|
| `assistant_delta` | Streaming text token from the model |
| `tool_call` | Agent issued a tool call |
| `tool_result` | Tool returned a result (with optional sources/ui_parts) |
| `awaiting_human` | HITL pause; carries `HumanInputRequest` |
| `node_error` | Graph node failed with on_error routing |
| `final` | Turn complete; carries content, sources, token_usage, ui_parts |
| `turn_persisted` | **Schema only — not emitted over SSE in Phase 1** (see gap below) |
| `status` | Internal status update (dropped by OpenAI compat layer) |

### SSE stream termination

The SSE stream emitted by `POST /agents/execute/stream` **terminates by
connection close** after the `final` event. There is no sentinel line (no
`data: [DONE]` or equivalent). `final` is always the last data line in a
successful turn.

SSE clients MUST:
- treat reception of `{"kind": "final"}` as the end-of-turn signal
- treat connection close before `final` as an error

### Unstructured error signal (contract gap — tracked below)

When an unhandled exception escapes `_iterate_runtime_event_payloads`, the
runtime yields a **bare error payload** before closing the stream:

```
data: {"error": "<exception message>"}
```

This payload has **no `kind` field** and is **not a member of the `RuntimeEvent`
union**. It is the only way a client receives notice of a server-side crash.

SSE clients MUST check for the top-level `"error"` key on every frame, not only
on frames that carry a `"kind"` discriminator.

This is a known contract gap tracked in Phase 3b. See Section 8 below.

### `TurnPersistedEvent` — schema defined, SSE delivery not yet wired (contract gap)

`TurnPersistedEvent` (`kind: "turn_persisted"`) exists in `RuntimeEventKind` and
`RuntimeEvent` and is listed above, but is **never emitted to the SSE client in
Phase 1**. History is written fire-and-forget via `asyncio.ensure_future` after
the SSE generator exhausts; no frame reaches the client.

Clients MUST NOT wait for `turn_persisted` as a stream-end signal. This gap is
tracked in Phase 3b. See Section 8 below.

### UI rendering parts (`UiPart`)

Carried in `tool_result` and `final` events:

| Type | Model | Fields |
|---|---|---|
| `link` | `LinkPart` | `href`, `title`, `kind` (download/open/cite) |
| `geo` | `GeoPart` | `geojson` (GeoJSON FeatureCollection) |

---

## 6. Checkpoint and History Semantics

`fred-runtime` is a **consumer** of persisted checkpoint state, not its
ownership authority. Control-plane owns the mapping from session to checkpoint
storage.

Runtime must validate before resuming:
- `session_id` is authorized by the `ExecutionGrant`
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
- Team-scoped managed agent authorization (`ExecutionGrant` validation)
- Runtime execution contracts (this module)
- History and checkpoint access validation
- Managed execution semantics (`agent_instance_id` resolution via control-plane)

Platform concerns belong to:
- Kubernetes `Service` and `Ingress` / Gateway API
- Namespace isolation and DNS stable names
- Argo CD / GitOps deployment descriptors

---

## 8. Known SSE Contract Gaps (discovered April 2026)

These gaps were surfaced while implementing an external SSE bench client against
the live protocol. They are tracked as Phase 3b correction tasks in `BACKLOG.md`.

### 8.1 Unstructured error signal

**Symptom**: SSE clients that only dispatch on `kind` silently ignore agent
crashes and hang until timeout.

**Root cause**: `_iterate_runtime_event_payloads` exception handler (line 1691
of `agent_app.py`) yields `{"error": str(exc)}` — no `kind` field. This payload
is not in `RuntimeEventKind` and not in the `RuntimeEvent` union.

**Required fix**: Promote the error signal to a first-class contract member.
Either:
- add `RuntimeErrorEvent(kind="execution_error", message=str)` to `fred-sdk`
  and update the exception handler to yield it, OR
- document `{"error": "..."}` as a guaranteed contract signal that all clients
  must handle

The fix must propagate to the OpenAPI spec and frontend codegen.

### 8.2 `TurnPersistedEvent` not delivered over SSE

**Symptom**: Any client that waits for `{"kind": "turn_persisted"}` as a
session-save confirmation will hang indefinitely.

**Root cause**: `_write_turn_history` is called via `asyncio.ensure_future` after
the SSE generator exhausts. The `TurnPersistedEvent` type exists in the SDK but
is never yielded to the client. The contract doc (Section 5) implies it is.

**Required fix**: Either:
- wire `TurnPersistedEvent` emission before the generator exhausts (requires
  awaiting the history write, which adds latency), OR
- deliver it via a push channel separate from the turn SSE stream (e.g. a
  session status endpoint), OR
- explicitly remove `turn_persisted` from the SSE contract and document it as
  a future push-channel event

Until resolved: clients MUST treat `final` as the only reliable end-of-turn
signal.

### 8.3 SSE stream termination not documented

**Symptom**: Client authors must read source code to know how the stream ends.

**Required fix**: Document in this file (done in Section 5 above) and confirm
in the OpenAPI description for `POST /agents/execute/stream` that:
- the stream terminates by connection close after `final`
- no sentinel line is emitted
- `turn_persisted` is not a reliable stream-end signal (see 8.2)

### 8.4 Direct-mode (`agent_id`) session scoping not documented

**Symptom**: Multi-turn bench clients using `agent_id` direct mode without
`runtime_context` end up with all sessions keyed to user `"unknown"`, making
per-user session isolation impossible.

**Root cause**: In direct mode the `execution_grant` is absent, so `user_id`
defaults to `"unknown"` unless `runtime_context.user_id` is explicitly provided.
This behavior is not documented.

**Required fix**: Add an explicit note in the `RuntimeExecuteRequest` docstring
and in Section 2.3 of this document that in direct (`agent_id`) mode, callers
MUST provide `runtime_context.user_id` (and optionally `team_id`) for correct
session scoping. Managed execution (`agent_instance_id` + `ExecutionGrant`)
is not affected — `user_id` is always authoritative there.

---

## 8. Developer CLI — `fred-agent-chat`

The CLI (`libs/fred-runtime/fred_runtime/client.py`) is a first-class contract
consumer. It exercises the frozen execution contract from terminal without the
frontend.

Entry point: `fred-agent-chat` (see `libs/fred-runtime/pyproject.toml`).

### Commands

| Command | What it does |
|---|---|
| `/help` | Print command reference |
| `/help <question>` | Ask a natural-language question via the pod (multilingual) |
| `/agents` | List available agent IDs |
| `/agent <id>` | Switch active agent |
| `/session <id>` | Change the current session ID |
| `/sessions` | List all sessions for the current user |
| `/history [session_id]` | Show conversation history |
| `/checkpoints [limit]` | List checkpoint threads |
| `/checkpoint <thread_id>` | Inspect all checkpoints for one thread |
| `/context` | Show execution context summary (agent, session, mode, pod URL) |
| `/stats` | Checkpoint storage statistics |
| `/mode [final\|stream]` | Show or change execution mode |
| `/scenario <file>` | Run a YAML scenario file |
| `/login` / `/login-password` | Authenticate via PKCE or username/password |
| `/team [team_id\|clear]` | Show, set, or clear the current team scope |
| `/whoami` / `/logout` | Auth status and logout |
| `/quit` | Exit |

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
- if a backend change cannot be validated through `fred-agent-chat` or targeted
  runtime tests, the backend path is not yet "dry" enough for frontend cutover

## 9. Backend Completeness Gate Before Phase 4

Before frontend SSE migration starts, the runtime/backend path must satisfy the
following invariants:

1. Team-scoped managed execution works correctly even when the same pod exposes
   the underlying capability through raw `agent_id`.
2. Managed execution is validated through control-plane resolution plus runtime
   grant enforcement, not inferred from pod-local tenancy.
3. Runtime history, checkpoint, and resume flows preserve the same execution
   identity set used at request time.
4. Logs, metrics, KPI rows, and tracing payloads are enriched consistently with
   the execution identity and correlation fields below.
5. Langfuse-exported traces keep the same identity metadata so downstream
   analysis does not lose team or managed-agent scope.
6. `fred-agent-chat` remains a first-class validation client for these flows.

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
- managed HITL resumes require `ExecutionGrant.action == "resume"`
- runtime span metadata, graph KPI dimensions, KF client KPI dimensions, MCP
  tool KPI dimensions, and Langfuse span metadata preserve the managed
  execution identity fields available at runtime
- `fred-agent-chat` can set team scope explicitly via `/team` or `--team-id`
  and exercise the same managed/team-scoped backend path without the frontend
- `fred-runtime` now restores a concrete KPI pipeline at pod startup:
  `KPIWriter`, Prometheus export when configured, and process/SQL pool KPI
  background emitters for scrape-based local validation and laptop benchmarks
- `fred-agent-chat` can now inspect that same runtime metrics surface directly
  via `/kpi [pattern]`, so backend KPI validation no longer depends on a local
  Grafana/Prometheus stack

Still pending before Phase 4:

- end-to-end validation from `fred-agent-chat` that one managed execution works
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

1. validate the managed execution path from `fred-agent-chat`
2. validate managed HITL resume end-to-end
3. finish the remaining observability/log-sink audit
4. only then begin Phase 4 frontend SSE migration

---

## 10. Phase 2 Status — OpenAPI And Frontend Codegen

Phase 2 is complete enough to serve as the contract source for the frontend.

### 10.1 What is now true

- `libs/fred-runtime/Makefile` exposes `make generate-openapi`
- `libs/fred-runtime/openapi.json` is generated locally from the pod app factory
- `frontend/src/slices/runtime/runtimeOpenApi.ts` is generated from `fred-runtime`
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

| Concern | Source of truth | Notes |
|---|---|---|
| Shared execution/auth contracts | `libs/fred-sdk/fred_sdk/contracts/` | Edit here first |
| Frontend-facing runtime routes | `libs/fred-runtime/fred_runtime/app/agent_app.py` | OpenAPI comes from these route signatures |
| OpenAI-compatible models | `libs/fred-sdk/fred_sdk/contracts/openai_compat.py` | Secondary interface only |
| Frontend generated runtime slice | `frontend/src/slices/runtime/runtimeOpenApi.ts` | Generated file; do not hand-edit |
| Migration sequencing | `BACKLOG.md` | Current phase and next step |

### 10.4 Regeneration Commands

```bash
cd libs/fred-runtime && make generate-openapi
cd frontend && make update-runtime-api
```

If the generated frontend slice does not change as expected, fix the source
contract first. Do not patch the generated TypeScript by hand.

---

## 11. What Is Explicitly Deferred

| Item | Phase |
|---|---|
| Cryptographic `ExecutionGrant` signature verification | Phase 2–3 |
| `checkpoint_id` authorization against `ExecutionGrant` at resume | Phase 2–3 |
| Backend completeness gate implementation for observability enrichment and managed-scope validation | Phase 3b |
| Frontend SSE transport migration (replace WebSocket) | Phase 4 |
| Control-plane product/session/admin API migration | Phase 3 |
| `agentic-backend` removal from frontend runtime path | Phase 6 |

---

## 12. Key Rules (for AI assistants and reviewers)

1. `team_id` is mandatory and explicit in every execution.
2. `agent_instance_id` is the default execution target; `agent_id` is dev-only.
3. Every execution must carry a verifiable `ExecutionGrant` when using managed execution.
4. Runtime validates — control-plane decides.
5. Checkpoint access must be authorized at session scope.
6. Fred code must not rebuild native Kubernetes routing/discovery behavior.
7. `ExecutionGrant` must never carry infrastructure secrets.
8. `OpenAI /v1` is secondary; the native SSE protocol is the primary frontend contract.
9. Do not recreate `agentic-backend` chat/session DTOs inside `fred-runtime`.
10. Do not add new abstraction layers, wrappers, or endpoints unless the current contract is provably insufficient.
11. Prefer strengthening typing on existing contracts over inventing new transport shapes.
12. Never hand-edit generated files such as `frontend/src/slices/runtime/runtimeOpenApi.ts`; regenerate from source contracts.
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
