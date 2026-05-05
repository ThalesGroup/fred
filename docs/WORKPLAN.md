# Workplan

Short-cycle execution plan. Updated as items close.
Backlogs contain the full specs — this document answers **who does what, in what order, and what runs in parallel**.

Last updated: 2026-04-28

---

## Team

| Who | Area |
|---|---|
| **Dimitri** | Backend — architecture, contracts, runtime design |
| **Félix** | Frontend (rework design system, chat UI, migration) |
| **Simon** | Backend — fred-runtime, fred-sdk, observability |
| **Florian** | Backend — control-plane-backend, APIs, DB |
| **Olélia** | Agent evaluation (deepeval) — parallel track |

---

## Current Priority: Gate Before Phase 6A

Two backend items must close before Félix starts the Chat UI (Phase 6A).
They can run in parallel between Simon and Florian.

```
Simon ──────[ S1: E2E validation ]──────────────────────────────────────┐
                                                                         ├──► Félix: Phase 6A
Florian ────[ F1: updated_at strategy + impl ]──────────────────────────┘
```

---

## S1 — Backend E2E Validation (Simon) · Phase 3b gate

**Why**: the SSE execution chain has never been formally validated without the frontend.
All UI work that follows rests on this foundation.

**Ref**: `docs/backlog/BACKLOG.md` §3b.7

**Scenario automation complete (2026-04-26)** — scenarios now run via `pytest -m integration` or
`make test-integration-only` in `apps/fred-agents`. No manual CLI replay needed.

| Scenario file | Description | Env var required |
|---|---|---|
| `s1_raw_echo.yaml` | Raw `agent_id` path, echo turn | none |
| `s1_managed_echo.yaml` | Managed path via `agent_instance_id` | `FRED_AGENT_INSTANCE_ID` |
| `s1_hitl_resume.yaml` | HITL two-phase pause + resume | none |

Three scenarios to validate, in order:

1. **[x] Scenario automation wired** — `run_scenario_file()` supports `agent_instance_id`, HITL steps, env-var substitution, `history_has_messages` + `kpi_turn_recorded` checks
2. **[ ] Live stack validation** — run `make test-integration-only` with pod up + `FRED_AGENT_INSTANCE_ID` set
   - Tick `[ ] one managed execution works end-to-end from fred-agents-cli`
   - Tick `[ ] one managed HITL resume flow works end-to-end from fred-agents-cli`
   - Tick `[ ] one runtime capability reachable through raw agent_id also works correctly through team-scoped managed execution`

**Done when**: all three ticked in BACKLOG.md §3b.7 after live stack run.

---

## F1 — Session `updated_at` Strategy (Florian) · Phase 6 gate

**Why**: the sidebar sorts sessions by `updated_at`. Today this field is set at session creation and never updated. Every conversation appears in creation order, not activity order.

**Ref**: `docs/backlog/BACKLOG.md` §6.4.D

**Decision to make first** (needs alignment, ~30min sync):

| Option | Mechanism | Trade-off |
|---|---|---|
| A | Frontend sends `PATCH /sessions/{id}` after each `turn_persisted` event | Simple, but couples frontend to control-plane on the hot path |
| B | Runtime notifies control-plane via async queue after each `final` | Clean separation, slightly more infra |
| C | Sidebar sorts by frontend-local timestamp, `updated_at` stays stale | Degrades on reload but unblocks immediately |

**Recommended starting point**: Option A — simplest, no new infra, correct for the current scale.

**Tasks**:
- [x] Decide and document option in BACKLOG.md §6.4.D
- [x] If A: implement `PATCH /control-plane/v1/teams/{team_id}/sessions/{session_id}` (body: `{ updated_at }`)
- [x] If A: wire call in `ManagedChatPage` on each `turn_persisted` SSE event (Félix, after F1 lands)
- [x] `make code-quality && make test` in `control-plane-backend`

---

## S2 — Prometheus Cardinality Fix + Observability Hardening (Simon/Dimitri) · Closed 2026-04-26

**Why**: `session_id` and `user_id` as Prometheus label dimensions create unbounded cardinality. Also closes the turn-level KPI gap and opens a dedicated security audit channel.

**Ref**: `docs/backlog/BACKLOG.md` §7.3, §7.6, §7.7

- [x] Remove `session_id` from Prometheus labels emitted from runtime KPI dims
- [x] Remove `user_id` from Prometheus labels emitted from runtime KPI dims
- [x] Keep both in structured KPI log output (OpenSearch / log backend)
- [x] Same cleanup for graph/KF phase timers via the shared Prometheus KPI sink
- [x] `exchange_id` propagated to Langfuse trace metadata via `context.baggage`
- [x] `_emit_turn_completed()` wired to **non-streaming `execute()` path** (was streaming-only)
- [x] `KpiLogStore.index_event()` fixed: now logs structured JSON for `agent.turn_completed`,
  `agent.turn_error_total`, `agent.tool_failed_total` (was silent no-op)
- [x] Pod ring buffers (`_KPI_TURNS_BUFFER`, `_AUDIT_EVENTS_BUFFER`) + endpoints
  `GET /agents/kpi-turns` and `GET /agents/audit-events`
- [x] `/kpi [limit]` CLI command — per-turn ring buffer view with current-session highlight
- [x] Dedicated `fred.security.audit` logger + audit ring buffer; events emitted at all
  auth boundaries (`grant_validated`, `grant_validation_failed`, `grant_user_mismatch`)
- [x] `/audit [limit]` CLI command — security audit event table with colour coding
- [x] `_emit_audit_event()` helper: mutualize all audit event emission (ring buffer + logger);
  fixes `grant_validation_failed` not reaching the ring buffer
- [x] `Quantities` model: add `tool_count`, `input_tokens`, `output_tokens` with `None` defaults;
  change pipeline fields from `= 0` to `= None` — turn KPI quantities were silently discarded
- [x] `datetime.utcnow()` → `datetime.now(timezone.utc)` at all 4 sites
- [x] `asyncio.ensure_future` → `asyncio.create_task`
- [x] Unit tests: `_emit_audit_event`, ring buffer endpoints, `_emit_turn_completed` via execute,
  `KpiLogStore.index_event()` (structured JSON, error events, unknown name filter)
- [x] `make code-quality && make test` in `fred-core` (31 tests) and `fred-runtime` (62 tests)

---

## AgentFormModal Refactor (Dimitri) · Done 2026-04-28

Per `docs/rfc/AGENT-INSTANCE-FORM-RFC.md`.

- [x] Backend: `ManagedMcpServerRef` extended with `display_name` + `config_fields`
- [x] Backend: `AgentTemplateSummary` now includes `mcp_servers`
- [x] Backend: runtime's `available_mcp_servers` enriched into `ManagedMcpServerRef.display_name`
- [x] Frontend: OpenAPI client regenerated
- [x] Frontend: `TemplateBrowser` + `TemplateCard` + `TuningFieldRenderer` + `AgentFormBody` extracted
- [x] Frontend: all field types implemented (secret, url, number, integer, boolean, enum, prompt, multiline)
- [x] Frontend: field grouping via `ui.group`; inline validation; edit mode context bar + metadata footer
- [x] Frontend: MCP tools read-only section in form body

---

## Agent FieldSpec Declarations (Dimitri) · Done 2026-04-28

Wires the control-plane form with actual tunable fields for all three production agents.

- [x] `fred-sdk`: added `MCP_SERVER_KNOWLEDGE_FLOW_TEXT` + `MCP_SERVER_KNOWLEDGE_FLOW_PROMETHEUS_OPS` constants
- [x] `GeneralAssistantDefinition`: full KF MCP toolkit in `default_mcp_servers` (7 servers); `prompts.system`, `chat_options.attach_files`, `chat_options.libraries_selection` fields
- [x] `SentinelReActDefinition`: `prompts.system` field (optional override of built-in monitoring prompt)
- [x] `RagExpertReActDefinition`: `prompts.system` + `chat_options.attach_files` + `chat_options.libraries_selection` fields
- [x] `make code-quality && make test` in `fred-agents` and `fred-sdk`

**Done (2026-05-04)**: `prompts.system` value now applied in `_apply_runtime_tuning`. Fix required two changes: (1) `AgentTuning` in fred-sdk gained `values: dict[str, Any]` so Pydantic no longer silently drops the field during control-plane response deserialization; (2) `_apply_runtime_tuning` reads `tuning.values.get("prompts.system")` and, when non-blank and the definition is a `ReActAgentDefinition`, overlays `system_prompt_template` in the `model_copy` update. Two offline unit tests added to `test_agent_app.py`. All 127 fred-runtime + 75 fred-sdk tests pass.

---

## Phase 6A — Chat UI Architecture (Félix) · Starts after S1 + F1

**Ref**: `docs/backlog/CHAT-UI-BACKLOG.md` §1

Build the new component tree for `ManagedChatPage`. No markdown yet. Full spec in the backlog.

**Component build order** (sequential within Félix's track):

```
[x] Step 1 — Atoms (no deps):
      MessageBubble · StreamingCursor · ToolBadge · TogglePanelButton
      (SourceBadge deferred to Phase 6B)

[x] Step 2 — Molecules (need atoms):
      UserMessage · AssistantMessage · ChatInputBar
      TraceEntryRow · TraceDetailDrawer · ThoughtTrace
      SourceCard · SourcesPanel

[x] Step 3 — Organisms (need molecules):
      ChatMessagesArea · AssistantTurn

[x] Step 4 — Refactor ManagedChatPage (new components + three-column layout)

[x] Step 5 — Map SSE events to ConversationMessage state
[x] Step 6 — Normalise history from runtime messages_url_template
```

**Validation criteria** (must pass before 6B starts):
- User messages right-aligned, agent messages left-aligned
- StreamingCursor visible during delta, gone on final
- ThinkingAccordion opens on first tool_call, closes on final
- SourcesPanel appears when final event carries sources
- ChatInputBar disabled while streaming
- HITL flow unaffected
- History renders identically to streamed messages
- `make code-quality` green on frontend

---

## Phase 6B — Markdown Rendering (Dimitri) · Done 2026-05-04

**Ref**: `docs/backlog/CHAT-UI-BACKLOG.md` §2

- [x] Audit `package.json` for `react-markdown` — present at `^9.1.0`
- [x] Document library choice in CHAT-UI-BACKLOG.md §2.2
- [x] Implement `MarkdownRenderer` molecule (react-markdown + remark-gfm + rehype-sanitize + inline `rehypeCitations` plugin)
- [x] Implement `SourceBadge` atom (Phase 6B prerequisite, deferred from 6A)
- [x] Implement `CodeBlock` molecule (monospace + copy)
- [x] Wire into `AssistantMessage`; thread `onSourceClick` through `AssistantTurn` → `SourcesPanel` activeIndex highlight
- [x] Prettier + `tsc --noEmit` pass (zero new errors)

## Code Quality Audit (Dimitri) · Done 2026-05-04

Full audit of all rework frontend code for design-system compliance.

- [x] Remove MUI `KeyboardArrowRightIcon` from `Breadcrumb` — replaced with `Icon` atom (`chevron_right`)
- [x] Remove `CssBaseline` from `MainLayout` — global reset already handled by `reset.scss`
- [x] Move `Menu` from `organisms/Menu/` → `molecules/Menu/` — it only composes `MenuItem` atoms; update 3 import sites (`Select`, `Autocomplete`, `IconButtonMenu`)
- [x] Remove hex fallbacks from `HitlPrompt.module.css` (4 `var(token, #hex)` lines → `var(token)`)
- [x] Add Apache 2.0 license headers to all 51 rework `.tsx` files that were missing them
- [x] Keep `KfVectorSearchForm` — still consumed by old-tree `AgentToolsSelection` via `TOOL_PARAMS_REGISTRY`; add license header and note in backlog

---

## F2 — PATCH Session Endpoint (Florian) · Before Phase 6C

**Ref**: `docs/backlog/BACKLOG.md` §6.4.D, `docs/backlog/CHAT-UI-BACKLOG.md` §3

Needed for inline session title editing in Phase 6C.

- [ ] `PATCH /control-plane/v1/teams/{team_id}/sessions/{session_id}` — body: `{ title?, status? }`
- [ ] Authorization: same team membership check as POST
- [ ] `make code-quality && make test` in `control-plane-backend`
- [ ] Regenerate `controlPlaneOpenApi.ts`

Can be implemented in parallel with Phase 6A/6B (no frontend dependency yet).

---

## R1 — fred-runtime Quality Refactor (Simon/Dimitri) · Parallel, independent

**Ref**: `docs/backlog/FRED-RUNTIME-QUALITY.md`

**Why**: Code-quality audit (2026-04-27) identified five structural problems:
monolithic `client.py` (3 880 lines), no dependency container, blocking I/O
in async paths, untyped `Any` boundaries, no shared test fixtures.

**Target**: `control-plane-backend` structural quality — full async, no `Any`
at boundaries, `PodApplicationContext` container, ≥ 70% offline unit coverage.

| Phase | Goal | Effort | Status |
|---|---|---|---|
| P1 | Fix async/sync correctness (`kf_workspace_client.py`, `user_token_refresher.py`) | 1 h | `[x]` ✅ 2026-04-27 |
| P2 | Shared test fixtures (`tests/conftest.py`) | 1 h | `[x]` ✅ 2026-04-27 |
| P3 | Split `client.py` → `fred_runtime/cli/` package | 3 h | `[x]` ✅ 2026-04-27 |
| P4 | Introduce `PodApplicationContext` container | 4 h | `[x]` ✅ 2026-04-27 |
| P5 | Eliminate `Any` at all typed boundaries | 2 h | `[x]` ✅ 2026-04-27 |

**Done when**: all gates in `FRED-RUNTIME-QUALITY.md §Definition of Done` are ticked.

**Status (2026-04-27):** P1–P5 all complete. Two DoD gates deferred to **R1b**:
- `Any` zero at function boundaries: `runtime_context.py` + `cli/pod_client.py` need typed DTOs and circular-import analysis
- No file > 600 lines: `agent_app.py` (2 578 lines) needs router extraction into `fred_runtime/app/routers/`

See `FRED-RUNTIME-QUALITY.md §R1b` for exact file-by-file breakdown and fix approach.

---

## O1 — Agent Evaluation Track (Olélia) · Parallel, independent

**Ref**: `docs/rfc/AGENT-EVALUATION-RFC.md`

This track is independent of the migration and UI work.
Coordinate with Simon/Florian when backend evaluation hooks are needed.

Current state: RFC exists, no implementation started.

**Suggested first steps**:
- [ ] Confirm scope: which agents, which datasets, which deepeval metrics
- [ ] Identify whether evaluation needs a dedicated runtime endpoint or CLI-only
- [ ] Draft evaluation harness structure in `apps/` or a standalone eval runner
- [ ] Align with Simon on any runtime observability hooks needed (exchange_id, token usage)

---

## D1 — Control-Plane Developer CLI · Important next backend ergonomics track

**Ref**: `docs/backlog/CONTROL-PLANE-CLI-BACKLOG.md`

**Why**: `fred-agents-cli` gives us a first-class runtime validation console, but
we still lack an equivalent terminal workflow for the control-plane product and
admin surface. As `control-plane-backend` becomes the sole authority for
managed-agent lifecycle, runtime binding, and execution preparation, this gap is
becoming operationally expensive.

**Intent**:
- give `control-plane-backend` its own `make cli` developer/operator console
- keep runtime-specific chat behavior in `fred-runtime`
- move only truly shared CLI primitives into `fred-core`
- explicitly defer the `knowledge-flow` CLI until after `knowledge-flow-backend`
  is moved under `apps/`

**Current status (2026-04-25)**:
- [x] Freeze placement rules: shared CLI primitives in `fred-core`, runtime
      chat in `fred-runtime`, control-plane commands in
      `control-plane-backend`
- [x] Add one dedicated control-plane console script + `make cli`
- [x] Deliver MVP commands for templates, instances, enrollment, runtime
      binding, sessions, execution preparation, and lifecycle/policy inspection
- [x] Keep `knowledge-flow` CLI out of scope for this track
- [x] `make code-quality` and `make test` pass in `control-plane-backend`
- [x] `make code-quality` and `make test` pass in `libs/fred-core`
- [x] `make code-quality` and `make test` pass in `libs/fred-runtime`
- [x] Run one live stack validation in no-security mode
- [x] Run one live stack validation in Keycloak-enabled mode
- [x] Run one operator happy path for enroll / unbind / prepare-execution

---

## S3 — Runtime CLI Ergonomics + Session Purge (Simon/Dimitri) · Closed 2026-04-26

**Ref**: `docs/backlog/BACKLOG.md` §6.4.B, §6.4.G

Completed in one session — no outstanding items.

- [x] `fred.test.assistant` graph agent (no LLM): exercises `echo`, `hitl choice`, `hitl text`,
  `trace`+sources, `error`, `long` scenarios; registered in `apps/fred-agents` registry
- [x] History schema: `Channel.hitl_request` / `Channel.hitl_response`, `HitlRequestPart`,
  `HitlResponsePart`, `make_hitl_request` / `make_hitl_response` factories; sources extracted
  from `final` payload and stored in `ChatMetadata.sources` (see BACKLOG.md §6.4.F)
- [x] Session purge stack: `delete_session()` on `BaseHistoryStore`, `PostgresHistoryStore`,
  `HistoryStorePort`; `DELETE /agents/sessions/{session_id}` pod endpoint; client methods
  `delete_session_messages()` + `delete_checkpoint()` (see BACKLOG.md §6.4.B)
- [x] CLI commands: `/session-info`, `/session-new`, `/session <N>` index switching,
  `/sessions` with preview, `/whoami` full identity panel, `/history --raw`,
  `/delete-session`, `/delete-checkpoint`, `/purge-session` (see BACKLOG.md §6.4.G)
- [x] `make code-quality` and `make test` green in `fred-core` and `fred-runtime`

---

## Sequence Summary

```
NOW (parallel)
├── Simon:   S1 E2E validation ──────────────────────────────────► unblocks 6A
├── Simon:   S2 Observability hardening ── CLOSED 2026-04-26 ───► shipped
├── Florian: F1 updated_at strategy + PATCH impl ────────────────► unblocks 6A
├── Florian: F2 PATCH session endpoint ──────────────────────────► unblocks 6C
├── Olélia:  O1 Evaluation RFC → harness ────────────────────────► independent
└── Parallel: D1 Control-plane CLI live validation + closeout ───► backend ergonomics track

AFTER S1 + F1 CLOSED
└── Félix:   6A Chat UI architecture ──────────────────────────────────────┐
                                                                            │
AFTER 6A                                                                    │
└── Félix:   6B Markdown rendering ─────────────────────────────────────── │
                                                                            │
AFTER 6B + F2                                                               │
└── Félix:   6C Agent options + session title ──────────────────────────── ┘
```

---

## M1 — Multi-Agent Conversational Memory (Dimitri) · Core implemented, hardening pending (2026-05-05)

**Ref**: `docs/rfc/MULTI-AGENT-MEMORY-RFC.md` · `docs/backlog/MULTI-AGENT-MEMORY-BACKLOG.md`

**Why**: `TeamAgent` in `route` mode fails on the second user question. The coordinator has no knowledge of prior turns, the sub-agent receives no conversation context, and the graph state discards history at every turn boundary. The root cause is a missing general primitive in the SDK — not a `TeamAgent`-specific bug.

**Design constraint**: The fix must be a general SDK contract (`ConversationTurn`, `ConversationalState`, explicit turn carry-forward, `build_completed_state`, typed `prior_turns`/`invocation_turns`). `TeamAgent` is a consumer of these primitives, not a special case. See RFC §3 Design Principles.

**Implementation rule**: do not use this feature to deepen transitional runtime plumbing. If a touched path already has a public typed contract plus a private bridge (for example `RuntimeExecuteRequest` → `_AgentExecuteRequest` → `to_legacy_context()`), prefer spending effort where the same change reduces that duplication.

**Current state (2026-05-05)**: The core continuity contract is implemented and validated, but the review identified four follow-up hardening slices that should be split into separate branches from `swift` before this track is considered fully closed: agent-scoped checkpoint isolation, remote execute-contract convergence, local projection convergence, and TeamAgent history-cap enforcement.

- [x] Preliminary runtime seam convergence: `LocalRegistryAgentInvoker` now projects through `RuntimeExecuteRequest`, `_iterate_runtime_event_payloads(...)` uses one extracted preparation path, and `make code-quality` / `make test` passed in `libs/fred-runtime` (2026-05-05)
- [x] Phase A — SDK primitives: `ConversationTurn`, `ConversationalState`, `build_turn_state`, `build_completed_state`, `AgentInvocationRequest`, `ExecutionConfig` (2026-05-05)
- [x] Phase B — `TeamAgent` consumes the primitives: state, history append, coordinator prompts, `invoke_agent` (2026-05-05)
- [x] Phase C — Runtime: ReAct context injection, local/remote invoker forwarding, `GraphRuntime` checkpoint wiring (2026-05-05)
- [x] Phase D — Integration validation: 28 new offline tests; manual 3-turn validation with `fred.samples.team_of_3.router` confirmed (2026-05-05)
- [x] Phase E — Documentation: `AGENTS.md` multi-turn section, `V2_AGENT_CREATION.md` pointer, RFC status → Implemented (2026-05-05)
- [ ] Phase F.1 — `fix/memory-agent-checkpoint-isolation`: isolate persisted state per agent within a shared session
- [ ] Phase F.2 — `fix/remote-agent-runtime-execute-contract`: make remote invocation use the public `RuntimeExecuteRequest` shape
- [ ] Phase F.3 — `refactor/local-agent-execute-projection`: remove duplicate local `_AgentExecuteRequest` construction and keep one projection path
- [ ] Phase F.4 — `fix/team-memory-history-cap`: enforce `conversation_history_max_turns` on TeamAgent append

---

## Open Decisions (need sync before implementation)

| Decision | Owner | Blocking |
|---|---|---|
| Option A/B/C for `updated_at` freshness | Florian + all | F1, then Félix 6A wiring |
| Whether `ExecutionPreparation` should expose agent runtime options | Simon + Florian | Félix 6C scope |
| Checkpoint TTL policy for standalone mode | Simon | BACKLOG.md §3b.9, non-urgent |
| `session_purge_queue` keep or repurpose | Florian | BACKLOG.md §6.4.E, non-urgent |
