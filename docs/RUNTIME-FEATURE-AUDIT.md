# Runtime Feature Audit

**Scope:** `fred-runtime`, `fred-sdk`, `fred-agent-chat` CLI, and their direct dependencies in `fred-core`.

**Purpose:** A developer-facing, implementation-level inventory. For each feature and sub-feature:
- implementation status and quality
- exact source files (and line ranges where non-obvious)
- known gaps, risks, and "time bombs"
- related tests
- how to validate locally

**How to use this file:**
- Before touching a feature: read its entry to understand the landscape and known risks.
- After fixing a gap or finding a new one: update the entry immediately.
- When starting a new chat session: hand this file to the assistant so it does not rediscover known issues.

**Status legend:**
| Symbol | Meaning |
|---|---|
| ✅ | Implemented and validated |
| ⚠️ | Implemented but with known gaps or untested paths |
| ❌ | Not implemented |
| 🔥 | Known defect — do not rely on this in production |

---

## 1. Standalone / No-Security Mode

> Single-user deployment without Keycloak. `KEYCLOAK_ENABLED=false`. Mock admin user.

### 1.1 Mock user injection
**Status:** ✅
**Files:** `agent_app.py:_make_user_dependency()` (~line 1049–1075)
**How:** When `security_enabled=False`, `get_current_user` returns `None`; all route handlers that accept `authenticated_user` receive `None` and skip identity checks.
**Tests:** Covered implicitly by all no-security route tests.

### 1.2 Default team_id = "personal"
**Status:** ✅ (fixed 2026-04-22, commit `dce5e33f`)
**Files:**
- `agent_app.py:_stream()` (~line 1493–1510) — resolves `team_id` before all downstream calls
- `client.py:main()` (~line 3887) — `effective_team_id = "personal"` when no login config
**Gap history:** Was previously only resolved inside `_iterate_runtime_event_payloads`, so KPI and history received `team_id=None`.
**Tests:** `test_no_security_resolves_personal_team_before_iterate`, `test_no_security_resolves_personal_team_in_portable_context`

### 1.3 CLI startup banner shows active team
**Status:** ✅ (added 2026-04-22)
**Files:** `client.py:main()` (~line 3882–3888)
**Output:** `[chat] team      : personal`

### 1.4 Standalone KPI / history labels
**Status:** ✅ (fixed 2026-04-22, commit `4b69d4e6`)
**Detail:** `agent.turn_completed` dims no longer include `session_id` / `exchange_id` (cardinality). `team_id="personal"` reaches Prometheus correctly.

---

## 2. SSE Execution Stream — Direct Path (agent_id)

> Developer/CLI path. No execution grant. Agent identified by `agent_id` directly.

### 2.1 Route and request model
**Status:** ✅
**Files:**
- `agent_app.py:execute_stream()` (~line 2194–2260) — `POST /agents/execute/stream`
- `agent_app.py:_AgentExecuteRequest` (internal) / `RuntimeExecuteRequest` (public)
- `fred_sdk/contracts/runtime.py` — `RuntimeExecuteRequest`

### 2.2 SSE event types
**Status:** ✅
**Files:** `fred_sdk/contracts/runtime.py` — `RuntimeEvent` union, `RuntimeEventKind` enum
**Events defined:** `status`, `assistant_delta`, `tool_call`, `tool_result`, `sources`, `hitl_interrupt`, `turn_persisted`, `final`, `execution_error`, `node_error`
**⚠️ Gap:** `turn_persisted` is in the type union but NOT emitted live over SSE. Documented in the SDK docstring and in `RUNTIME-EXECUTION-CONTRACT.md`. Intentional for now (async history write).

### 2.3 Terminal signal
**Status:** ✅
**Contract:** `final` is the only reliable end-of-turn signal. `execution_error` is the only error signal. Connection close follows immediately after either. Documented in `RUNTIME-EXECUTION-CONTRACT.md` §0.

### 2.4 Error signal
**Status:** ✅ (typed event added 3b.6, commit `eedbc610`)
**Files:** `agent_app.py:_iterate_runtime_event_payloads()` except block (~line 1705–1709)
**Contract:** `{"kind": "execution_error", "message": "<reason>"}` — typed `RuntimeErrorEvent`.
**⚠️ Gap:** If the streaming generator is closed by client disconnect BEFORE the `execution_error` event is sent, the client sees nothing. There is no retry or reconnect mechanism.

### 2.5 Multi-turn / session continuity
**Status:** ✅
**Files:** `agent_app.py:_iterate_runtime_event_payloads()` — `session_id` drives LangGraph `thread_id`
**Contract:** Same `session_id` across turns restores agent graph state from checkpointer.
**⚠️ Gap:** If `session_id` is omitted, falls back to `request_id` — creating a new graph state every turn (stateless). No warning is emitted to the caller.

---

## 3. SSE Execution Stream — Managed Path (agent_instance_id + ExecutionGrant)

> Production path. Control plane issues grant. Runtime validates it.

### 3.1 ExecutionGrant validation
**Status:** ✅ (3b.6)
**Files:** `agent_app.py:_validate_execution_grant()` and `_resolve_agent_instance()`
**Contract:** Grant must not be expired; grant user_id must match bearer token user_id when security is enabled.

### 3.2 Agent instance resolution
**Status:** ✅
**Files:** `agent_app.py:_resolve_agent_instance()` — fetches agent definition from control plane via HTTP.

### 3.3 End-to-end validation
**Status:** ❌ Not yet validated
**Blocked by:** Requires running control-plane-backend + PostgreSQL.
**Backlog:** 3b.7

---

## 4. Checkpoint Management

> LangGraph SQL checkpointer. One checkpoint row per graph step.

### 4.1 Checkpointer setup
**Status:** ✅
**Files:**
- `agent_app.py:create_agent_app()` lifespan (~line 2300–2410)
- `runtime_support/sql_checkpointer.py` — `FredSqlCheckpointer`
- `app/config.py:PodStorageConfig` — SQLite default at `~/.fred/pod/pod.sqlite3`

### 4.2 Admin API
**Status:** ✅
**Files:** `agent_app.py:_build_agent_router()` — checkpoint admin routes
**Endpoints:**
- `GET /agents/checkpoints` — list all threads with sizes
- `GET /agents/checkpoints/_stats` — aggregate storage stats
- `GET /agents/checkpoints/{session_id}` — per-session checkpoint detail
- `DELETE /agents/checkpoints/{session_id}` — purge one session's checkpoints
**CLI:** `/checkpoints [limit]`, `/checkpoint <session_id>`, `/stats`

### 4.3 Checkpoint retention / TTL
**Status:** ❌ No automatic pruning
**Detail:** Checkpoints accumulate indefinitely. Manual DELETE exists.
**🔥 Risk:** SQLite at `~/.fred/pod/pod.sqlite3` grows forever in standalone mode.
**Backlog:** 3b.9 — define TTL policy and add background sweeper.

### 4.4 History vs checkpoint relationship
**Status:** ⚠️ Partially documented
**Key distinction:** Checkpoints = LangGraph graph state (binary blobs, per step). History = human-readable turn messages (stored separately in history store).
**🔥 Risk:** `DELETE /agents/checkpoints/{session_id}` does NOT delete history rows. This asymmetry is not visible to the caller.

---

## 5. Turn History

> Human-readable conversation log. Written fire-and-forget after SSE stream closes.

### 5.1 History write
**Status:** ✅
**Files:**
- `agent_app.py:_write_turn_history()` (~line 1230)
- `agent_app.py:_stream()` — `asyncio.ensure_future(_write_turn_history(...))` after stream close
**⚠️ Gap:** Fire-and-forget — if the pod dies immediately after the stream closes, the history write is lost. No retry, no WAL.

### 5.2 History API
**Status:** ✅
**Files:** `agent_app.py:_build_agent_router()` — `GET /agents/sessions/{session_id}/messages`
**CLI:** `/history [session_id]`

### 5.3 History team_id tagging
**Status:** ✅ (fixed 2026-04-22, same commit as 1.2)
**Detail:** `_stream()` passes `resolved_team_id` to `_write_turn_history()`.

---

## 6. KPI / Observability

> Prometheus metrics, structured log KPIs, optional Langfuse tracing.

### 6.1 Phase latency (react_stream)
**Status:** ✅
**Files:** `fred_sdk/react/react_runtime.py:stream()` (~line 267–279)
**Metric:** `app_phase_latency_ms{phase="react_stream", agent_step="react", team_id=..., session_id=..., template_agent_id=...}` (Histogram)
**⚠️ Gap:** `session_id` is a Prometheus label here too — same cardinality concern as `agent.turn_completed` had. At scale this will explode. For now acceptable in standalone (one session at a time).

### 6.2 Turn completion KPI
**Status:** ✅ (fixed 2026-04-22, commit `4b69d4e6`)
**Files:** `agent_app.py:_emit_turn_completed()` (~line 1410)
**Metric:** `agent_turn_completed{team_id, template_agent_id, runtime_id, model_name, finish_reason}` (Histogram, ms)
**Quantities (counters):**
- `agent_turn_completed_quantity_tool_count_total`
- `agent_turn_completed_quantity_input_tokens_total`
- `agent_turn_completed_quantity_output_tokens_total`
**finish_reason values:** `"stop"`, `"tool_calls"`, `"error"`, `""` (unknown)

### 6.3 Error counter
**Status:** ✅ (added 2026-04-22, commit `4b69d4e6`)
**Files:** `agent_app.py:_emit_turn_completed()` — emitted when `is_error=True`
**Metric:** `agent_turn_error_total{team_id, template_agent_id, runtime_id, model_name, finish_reason}` (Counter)

### 6.4 Checkpoint / SQL pool KPIs
**Status:** ✅
**Files:**
- `runtime_support/sql_checkpointer.py` — `phase_timer` wraps checkpoint read/write
- `agent_app.py:_start_runtime_kpi_tasks()` — background `emit_sql_pool_kpis`

### 6.5 Process KPIs
**Status:** ✅ — standard Prometheus process collector (CPU, memory, FDs)

### 6.6 Langfuse tracing
**Status:** ⚠️ Wired but not validated
**Files:** `agent_app.py:create_agent_app()` — `LangfuseObservabilityConfig`
**Backlog:** Phase 7 — `log_llm()` wiring

### 6.7 CLI `/kpi` command
**Status:** ✅
**Files:** `client.py:render_kpi_report()`, `summarize_prometheus_histograms()`, `parse_prometheus_text_exposition()`
**⚠️ Gap:** `app_phase_latency_ms` uses `session_id` as a Prometheus label, making the "context" block in `/kpi` output session-scoped. Multiple concurrent sessions would produce multiple histogram series, each shown separately. Acceptable for now.

### 6.8 Missing production KPIs
**Status:** ❌ Not yet implemented
- `agent.turn_error_rate` alerting rule (Prometheus recording rule, not code)
- `agent.tool_latency_ms` per-tool (KF tool calls are timed via `kf_base_client.py` but not broken down per tool name)
- `agent.llm_latency_ms` standalone metric (currently inside `react_stream` phase)
- Remove `session_id` from `app_phase_latency_ms` dims (cardinality, lower priority)

---

## 7. HITL (Human-in-the-Loop)

> Graph interrupt/resume. Agent pauses for human input mid-turn.

### 7.1 Interrupt signaling
**Status:** ✅
**Files:** `fred_sdk/contracts/runtime.py:HitlInterruptEvent`
**Event:** `{"kind": "hitl_interrupt", "question": "...", "checkpoint_id": "..."}`

### 7.2 Resume request
**Status:** ✅
**Files:**
- `agent_app.py:RuntimeExecuteRequest` — `checkpoint_id`, `resume_payload` fields
- `agent_app.py:_validate_session_checkpoint_access()` — consistency check

### 7.3 End-to-end HITL validation
**Status:** ❌ Not yet validated
**Blocked by:** Requires running stack. Backlog: 3b.7.

---

## 8. Multi-Agent (AgentInvoker)

> Agent-to-agent calls. One agent invokes another within the same pod.

### 8.1 Port and result types
**Status:** ✅ (types defined)
**Files:** `fred_sdk/contracts/agent_invoker.py` — `AgentInvokerPort`, `AgentInvocationResult`

### 8.2 Concrete implementation
**Status:** ✅
**Files:** `agent_app.py:_LocalAgentInvoker` — calls `_iterate_runtime_event_payloads` directly

### 8.3 team_id propagation in invoker
**Status:** ⚠️ Partial
**Detail:** `_LocalAgentInvoker.invoke()` passes `team_id=request.context.team_id` to `_iterate_runtime_event_payloads`. No standalone "personal" default here (invoker path is not exposed to the CLI/HTTP layer directly). Acceptable for now.

### 8.4 Error handling in invoker
**Status:** ⚠️ Partial
**Detail:** `node_error` kind is handled and returns `AgentInvocationResult(is_error=True)`. `execution_error` (the new typed event) is not explicitly handled — falls through to the `content_parts` collector, returning an empty result.
**🔥 Risk:** Silent failure on LLM error in agent-to-agent calls.

---

## 9. CLI (fred-agent-chat)

### 9.1 Interactive REPL
**Status:** ✅
**Files:** `client.py:run_interactive_chat()`
**Commands:** `/agents`, `/agent <id>`, `/team <id>`, `/session [id]`, `/sessions`, `/history [id]`, `/checkpoints [limit]`, `/checkpoint <id>`, `/stats`, `/kpi [pattern]`, `/whoami`, `/mode`, `/login`, `/logout`, `/context`, `/execution-context`, `/scenario`, `/help`, `/quit`

### 9.2 One-shot mode
**Status:** ✅
**Files:** `client.py:run_single_turn()`

### 9.3 Scenario file runner
**Status:** ✅
**Files:** `client.py:run_scenario_file()`

### 9.4 Keycloak PKCE login
**Status:** ✅
**Files:** `client.py:KeycloakUserSessionManager`

### 9.5 Metrics URL auto-discovery
**Status:** ✅
**Files:** `client.py:default_agent_metrics_url()` — reads `app.metrics_port` from `configuration.yaml`

### 9.6 Standalone defaults (team, auth banner)
**Status:** ✅ (added 2026-04-22)
**Detail:** No Keycloak config → `effective_team_id="personal"`, banner shows `[chat] auth: none (standalone mode)` and `[chat] team: personal`.

---

## 10. ReAct Runtime

> LangGraph-based ReAct agent execution. The primary runtime for `ReActAgent` pods.

### 10.1 Graph compilation and execution
**Status:** ✅
**Files:** `fred_sdk/react/react_runtime.py` — `ReActRuntime`

### 10.2 Streaming and event translation
**Status:** ✅
**Files:** `fred_sdk/react/react_stream_adapter.py`, `react_langchain_adapter.py`

### 10.3 Tool execution
**Status:** ✅
**Files:** `fred_sdk/react/react_runtime.py` — tool dispatch via LangChain tool interface

### 10.4 Tool error surfacing
**Status:** ⚠️ Partial
**Detail:** If a tool returns `is_error=True`, the runtime suppresses the subsequent LLM response and surfaces the tool error as the final message. This is correct behavior but not tested end-to-end in the standalone scenario suite.

### 10.5 Model routing / phase routing
**Status:** ✅
**Files:** `fred_sdk/react/react_runtime.py` — `ChatModelRouter` / phase config

---

## 11. Graph Runtime

> LangGraph `GraphAgent` execution. More flexible than ReAct, custom graph topology.

### 11.1 Execution
**Status:** ✅
**Files:** `fred_sdk/graph/` — `GraphRuntime`, `GraphAgentDefinition`

### 11.2 Streaming events
**Status:** ⚠️ Less tested than ReAct path
**Detail:** Uses same `_iterate_runtime_event_payloads` and SSE stack, but event translation is graph-specific.

---

## 12. Error Handling

### 12.1 Agent pipeline crash → execution_error
**Status:** ✅ (typed since 3b.6)
**Files:** `agent_app.py:_iterate_runtime_event_payloads()` except block

### 12.2 Grant validation failure → HTTP 403 / 409
**Status:** ✅
**Files:** `agent_app.py:_validate_execution_grant()`

### 12.3 Checkpointer unavailable → HTTP 503
**Status:** ✅
**Files:** `agent_app.py:_get_checkpointer()` — raises `HTTP_503`

### 12.4 Client disconnect mid-stream
**Status:** 🔥 Known gap
**Detail:** If the client disconnects after receiving `execution_error` but before the generator's post-yield code runs, `_emit_turn_completed` and history write may be skipped (depends on Starlette generator lifecycle). Wrapping in `try/finally` would make this robust.
**Backlog:** Should be addressed before production (add `try/finally` in `_stream()`).

### 12.5 LLM error visibility to invoker (agent-to-agent)
**Status:** 🔥 Known gap — see §8.4 above.

---

## 13. Security / Auth

### 13.1 Keycloak JWT validation
**Status:** ✅
**Files:** `agent_app.py:get_current_user()`, `_make_user_dependency()`

### 13.2 ExecutionGrant user_id correlation
**Status:** ✅
**Files:** `agent_app.py:_enforce_grant_user_correlation()`

### 13.3 Auth deps applied to checkpoint admin routes
**Status:** ✅ — `dependencies=_auth_deps` on all checkpoint endpoints

### 13.4 No-security bypass
**Status:** ✅ — `security_enabled=False` skips all auth deps cleanly

---

## Known Defects Summary

| ID | Area | Description | File | Severity |
|---|---|---|---|---|
| KD-1 | Error handling | Client disconnect may skip `_emit_turn_completed` and history write (generator lifecycle) | `agent_app.py:_stream()` | Medium |
| KD-2 | Multi-agent | `execution_error` not handled in `_LocalAgentInvoker` — silent failure | `agent_app.py:_LocalAgentInvoker` | Medium |
| KD-3 | KPI | `session_id` still a Prometheus label in `app_phase_latency_ms` (react_runtime.py) — cardinality risk at scale | `react_runtime.py:stream()` | Low (standalone OK) |
| KD-4 | Checkpoints | No TTL / automatic pruning — SQLite grows forever | `agent_app.py`, `config.py` | Low (standalone OK) |
| KD-5 | History | Fire-and-forget write — lost on pod crash immediately post-stream | `agent_app.py:_stream()` | Low (acceptable until WAL) |
| KD-6 | Session | No warning when `session_id` is omitted — silently stateless | `agent_app.py:_iterate_runtime_event_payloads()` | Low |

---

## Validation Checklist (Standalone Mode)

Run these manually with `make chat` in a fred-samples pod before any production stack work.

- [ ] `fred-agent-chat` starts: banner shows `auth: none (standalone mode)` and `team: personal`
- [ ] Send a message: agent responds with streaming deltas and a `final` event
- [ ] `/kpi`: `app_phase_latency_ms{phase=react_stream}` appears with `team_id=personal`
- [ ] `/kpi`: `agent_turn_completed` histogram appears with `finish_reason=stop`
- [ ] Send a message when LLM is down: `(execution_error)` received by CLI
- [ ] `/kpi` after error: `agent_turn_error_total` counter appears; `agent_turn_completed{finish_reason=error}` appears
- [ ] `/checkpoints`: session row appears with growing checkpoint count across turns
- [ ] `/stats`: checkpoint and blob byte counts are non-zero and stable
- [ ] `/history`: turn messages present for the current session
- [ ] `/checkpoint <session_id>`: per-step checkpoint chain visible
- [ ] `DELETE /agents/checkpoints/<session_id>` (via curl): session row disappears from `/checkpoints`; history row survives
- [ ] Restart pod; re-use same `session_id` from CLI: agent resumes graph state (multi-turn continuity)
- [ ] HITL: agent asks for confirmation; resume with `resume_payload`; continues correctly
