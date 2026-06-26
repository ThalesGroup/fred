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

## 0. The Flow in 30 Seconds

This is what one agent turn looks like over HTTP SSE.

```
Browser / CLI                control-plane              fred-runtime pod
     │                            │                           │
     │── POST /prepare-execution ─►                           │
     │◄── ExecutionPreparation ───                            │
     │    (execute_stream_url,                                │
     │     execution_grant,                                   │
     │     team_id, agent_instance_id)                        │
     │                                                        │
     │── POST {execute_stream_url} ──────────────────────────►│
     │   Authorization: Bearer <user token>                   │
     │   Body: {                                              │
     │     input: "Transfer 500€ to Alice",                   │
     │     session_id: "uuid",           ← conversation key   │
     │     agent_instance_id: "inst-1",  ← which agent        │
     │     execution_grant: { ... }      ← control-plane auth │
     │   }                                                    │
     │                                                        │
     │◄── data: {"kind":"status","status":"starting"} ────────│
     │◄── data: {"kind":"assistant_delta","delta":"I will…"} ─│
     │◄── data: {"kind":"tool_call","tool_name":"check_bal…"} ─│
     │◄── data: {"kind":"tool_result","content":"1200€"} ─────│
     │◄── data: {"kind":"final","content":"Transfer done."} ──│
     │                                              [connection closed]
```

**Two execution paths:**

| Path                      | When                             | Required fields                         |
| ------------------------- | -------------------------------- | --------------------------------------- |
| **Managed** (production)  | Frontend selects a team agent    | `agent_instance_id` + `execution_grant` |
| **Direct** (dev/CLI only) | Developer targets a pod directly | `agent_id` (no grant)                   |

The managed path is the only one authorized for production frontend calls.
`control-plane` is the sole authority that issues `ExecutionGrant` and resolves
which runtime pod serves which agent instance.

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
  │                             │ issues ExecutionGrant      │
  │◄── ExecutionPreparation ────│                           │
  │    {                        │                           │
  │      execute_stream_url,    │  ← ingress-relative URL   │
  │      execution_grant,       │  ← short-lived (5 min)    │
  │      agent_instance_id,     │                           │
  │      team_id,               │                           │
  │      expires_at             │                           │
  │    }                        │                           │
  │                             │                           │
  │  4. Execute directly        │                           │
  │── POST {execute_stream_url} ──────────────────────────►│
  │   Authorization: Bearer <token>                         │
  │   Body: { input, session_id,                            │
  │           agent_instance_id, execution_grant }          │
  │                             │  runtime validates:        │
  │                             │  • bearer token            │
  │                             │  • grant expiry            │
  │                             │  • team_id match           │
  │                             │  • agent_instance_id match │
  │◄── SSE stream ─────────────────────────────────────────│
  │   (see section 0 for event sequence)                    │
```

**Why control-plane is in the middle for step 3 but not step 4:**

Control-plane is the only component that knows which runtime pod serves which
agent instance. But it must not proxy the SSE stream (latency, complexity).
The `prepare-execution` step solves this: control-plane resolves the binding
once, issues a short-lived grant, and returns a safe ingress-relative URL.
The browser then calls the runtime pod directly — authorized, but without ever
knowing any Kubernetes internal topology.

**What the `execution_grant` contains:**

```
{
  user_id:           "alice",
  team_id:           "fredlab",
  agent_instance_id: "inst-abc123",
  action:            "execute",          ← or "resume" for HITL
  audience:          "/runtime/agents-v2",
  issued_at:         1745000000,
  expires_at:        1745000300          ← 5 minutes
}
```

Runtime rejects requests where any field mismatches or the grant is expired.
The browser token is validated independently by Keycloak middleware.

**HITL resume** follows the exact same path with `action: "resume"` and
`resume_payload` in the request body instead of a new user message.

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

| Model             | Fields                                                                    | Purpose                             |
| ----------------- | ------------------------------------------------------------------------- | ----------------------------------- |
| `ActorContext`    | `user_id`, `principal`                                                    | User identity for audit/diagnostics |
| `TeamContext`     | `team_id`, `team_type`                                                    | Team scope; always mandatory        |
| `ExecutionTarget` | `agent_instance_id`, `underlying_agent_ref`                               | Managed instance reference          |
| `TraceContext`    | `request_id`, `trace_id`, `correlation_id`, `session_id`, `checkpoint_id` | Observability across services       |

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

Convergence rule for future work:

- New execution features should prefer first-class typed fields on the public
  contract and typed runtime plumbing behind it.
- Do not deepen transitional compatibility bridges (`runtime_context`,
  `to_legacy_context()`, private mirror request models) when the same change can
  instead retire or shrink them.
- In particular, do not add a second special-purpose execution API for
  agent-to-agent calls if the existing runtime execute transport can carry the
  needed typed fields.

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

| Route                                                  | Handler                  | Contract                                                        |
| ------------------------------------------------------ | ------------------------ | --------------------------------------------------------------- |
| `POST {base_url}/agents/execute`                       | `execute()`              | `RuntimeExecuteRequest` → `RuntimeEvent \| RuntimeErrorPayload` |
| `POST {base_url}/agents/execute/stream`                | `execute_stream()`       | `RuntimeExecuteRequest` → `StreamingResponse` (SSE)             |
| `GET {base_url}/agents/sessions/{session_id}/messages` | `get_session_messages()` | `list[ChatMessage]`                                             |
| `GET /v1/models`                                       | `list_models()`          | `OpenAIModelList`                                               |

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
- Team-scoped execution (`team_id`) is passed via `X-Fred-Team-Id` header only
- `ExecutionGrant` is not yet threaded through the `/v1` surface
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
parts so live streaming and replay match. See `docs/swift/rfc/AGENT-FILESYSTEM-RFC.md`.

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
2. Managed execution is validated through control-plane resolution plus runtime
   grant enforcement, not inferred from pod-local tenancy.
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
- managed HITL resumes require `ExecutionGrant.action == "resume"`
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
| Cryptographic `ExecutionGrant` signature verification                                              | Phase 2–3 |
| `checkpoint_id` authorization against `ExecutionGrant` at resume                                   | Phase 2–3 |
| Backend completeness gate implementation for observability enrichment and managed-scope validation | Phase 3b  |
| Frontend SSE transport migration (replace WebSocket)                                               | Phase 4   |
| Control-plane product/session/admin API migration                                                  | Phase 3   |
| `agentic-backend` removal from frontend runtime path                                               | Phase 6   |

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
- authentication and `ExecutionGrant` validation
- runtime context and history behavior
- tool execution and identity propagation

The only difference is the synchronous structured return instead of an SSE stream.

### Scoring boundary

Scoring, metric calculation, and judge calls do **not** run inside `fred-runtime`.
They run in the separate evaluation worker (Control Plane side).
No DeepEval, LiteLLM, or OpenTelemetry dependency is permitted in `fred-runtime` or `fred-sdk` for this purpose.

### RFC reference

`docs/swift/rfc/AGENT-EVALUATION-RFC.md` — EVAL-01 v2
