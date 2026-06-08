# Workplan

Short-cycle execution plan. Updated as items close.
Backlogs contain the full specs — this document answers **who does what, in what order, and what runs in parallel**.

Last updated: 2026-06-03

---

## Team

| Who         | Area                                                |
| ----------- | --------------------------------------------------- |
| **Dimitri** | Backend — architecture, contracts, runtime design   |
| **Dimitri**   | Frontend (rework design system, chat UI, migration) |
| **Sébastien** | DevOps — CI, Docker, Helm, deployment             |
| **Simon**   | Backend — fred-runtime, fred-sdk, observability     |
| **Florian** | Backend — control-plane-backend, APIs, DB           |
| **Odélia**  | Agent evaluation (deepeval) — parallel track        |

---

## Current Priority: DEVOPS-FREDLAB / GKE Autopilot Kickoff

This week the deployment target is an internal Swift environment on `GCP / GKE Autopilot`.
The work is already tracked under `OPS-01` and `DEVOPS-FREDLAB`;
`OPS-02` and `OPS-03` closed on 2026-06-03, so do not open a parallel DevOps
backlog item for the same scope.

```
Sébastien ──[ OPS-02: CI pipeline ✓ ]────────────┐
Simon ───────[ OPS-03: Docker packaging ✓ ]──────┼──► OPS-01: Helm chart ───► DEVOPS-FREDLAB
                                                 │                            (GKE Autopilot live)
Simon ───────[ VALID-01: live runtime validation ]┘
```

**Today's focus**

- [x] `OPS-03` — Dockerfiles, image names, and startup contracts aligned with `apps/fred-agents`
      for the first `GKE Autopilot` deployment
- [x] `OPS-02` — CI now builds, validates, and publishes the modern artifact set used by the
      chart
- [ ] `OPS-01` — Simon reprend les changements chart/values pour la cible Autopilot
      maintenant que `OPS-02` + `OPS-03` sont clos
- [ ] `DEVOPS-FREDLAB` — keep the same execution track for the internal use-case deployment;
      no duplicate ticket required

---

## Earlier Priority: Gate Before Phase CHAT-01

Two backend items must close before Dimitri starts the Chat UI (Phase CHAT-01).
They can run in parallel between Simon and Florian.

```
Simon ──────[ VALID-01: E2E validation ]──────────────────────────────────────┐
                                                                         ├──► Dimitri: Phase CHAT-01
Florian ────[ CTRLP-01: updated_at strategy + impl ]──────────────────────────┘
```

---

## VALID-01 — Backend E2E Validation (Simon) · Phase 3b gate

**Why**: the SSE execution chain has never been formally validated without the frontend.
All UI work that follows rests on this foundation.

**Ref**: `docs/backlog/BACKLOG.md` §3b.7

**Scenario automation complete (2026-04-26)** — scenarios now run via `pytest -m integration` or
`make test-integration-only` in `apps/fred-agents`. No manual CLI replay needed.

| Scenario file          | Description                          | Env var required         |
| ---------------------- | ------------------------------------ | ------------------------ |
| `s1_raw_echo.yaml`     | Raw `agent_id` path, echo turn       | none                     |
| `s1_managed_echo.yaml` | Managed path via `agent_instance_id` | `FRED_AGENT_INSTANCE_ID` |
| `s1_hitl_resume.yaml`  | HITL two-phase pause + resume        | none                     |

Three scenarios to validate, in order:

1. **[x] Scenario automation wired** — `run_scenario_file()` supports `agent_instance_id`, HITL steps, env-var substitution, `history_has_messages` + `kpi_turn_recorded` checks
2. **[ ] Live stack validation** — run `make test-integration-only` with pod up + `FRED_AGENT_INSTANCE_ID` set
   - Tick `[ ] one managed execution works end-to-end from fred-agents-cli`
   - Tick `[ ] one managed HITL resume flow works end-to-end from fred-agents-cli`
   - Tick `[ ] one runtime capability reachable through raw agent_id also works correctly through team-scoped managed execution`

**Done when**: all three ticked in BACKLOG.md §3b.7 after live stack run.

---

## CTRLP-01 — Session `updated_at` Strategy (Florian) · Phase 6 gate

**Why**: the sidebar sorts sessions by `updated_at`. Today this field is set at session creation and never updated. Every conversation appears in creation order, not activity order.

**Ref**: `docs/backlog/BACKLOG.md` §6.4.D

**Decision to make first** (needs alignment, ~30min sync):

| Option | Mechanism                                                               | Trade-off                                                     |
| ------ | ----------------------------------------------------------------------- | ------------------------------------------------------------- |
| A      | Frontend sends `PATCH /sessions/{id}` after each `turn_persisted` event | Simple, but couples frontend to control-plane on the hot path |
| B      | Runtime notifies control-plane via async queue after each `final`       | Clean separation, slightly more infra                         |
| C      | Sidebar sorts by frontend-local timestamp, `updated_at` stays stale     | Degrades on reload but unblocks immediately                   |

**Recommended starting point**: Option A — simplest, no new infra, correct for the current scale.

**Tasks**:

- [x] Decide and document option in BACKLOG.md §6.4.D
- [x] If A: implement `PATCH /control-plane/v1/teams/{team_id}/sessions/{session_id}` (body: `{ updated_at }`)
- [x] If A: wire call in `ManagedChatPage` on each `turn_persisted` SSE event (Dimitri, after CTRLP-01 lands)
- [x] `make code-quality && make test` in `control-plane-backend`

---

## OBSERV-01 — Prometheus Cardinality Fix + Observability Hardening (Simon/Dimitri) · Closed 2026-04-26

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

**Done (2026-05-06)**: documentation and RFCs now freeze the managed-agent tuning taxonomy explicitly:

- `prompts.*` = author instructions
- `settings.*` = typed runtime/business behavior
- `chat_options.*` = frontend chat affordances
- MCP/model selection stays out of generic tuning fields and belongs in dedicated typed contract fields

Updated docs:

- `docs/platform/V2_AGENT_CREATION.md`
- `docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`
- `docs/rfc/AGENT-INSTANCE-FORM-RFC.md`
- `docs/backlog/BACKLOG.md` §3d design principles

**Done (2026-05-06)**: `control-plane-backend` now validates known managed-agent tuning values against the frozen field contract before persistence:

- shared validator in `product/service.py`
- reused by both enroll and update flows
- known values now enforce declared type / enum / min/max / pattern constraints
- unknown keys remain ignored for compatibility
- offline coverage added for create and patch failure cases

---

## Phase CHAT-01 — Chat UI Architecture (Dimitri) · Starts after VALID-01 + CTRLP-01

**Ref**: `docs/backlog/CHAT-UI-BACKLOG.md` §1

Build the new component tree for `ManagedChatPage`. No markdown yet. Full spec in the backlog.

**Component build order** (sequential within Dimitri's track):

```
[x] Step 1 — Atoms (no deps):
      MessageBubble · StreamingCursor · ToolBadge · TogglePanelButton
      (SourceBadge deferred to Phase CHAT-02)

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

**Validation criteria** (must pass before CHAT-02 starts):

- User messages right-aligned, agent messages left-aligned
- StreamingCursor visible during delta, gone on final
- ThinkingAccordion opens on first tool_call, closes on final
- SourcesPanel appears when final event carries sources
- ChatInputBar disabled while streaming
- HITL flow unaffected
- History renders identically to streamed messages
- `make code-quality` green on frontend

---

## Phase CHAT-02 — Markdown Rendering (Dimitri) · Done 2026-05-04

**Ref**: `docs/backlog/CHAT-UI-BACKLOG.md` §2

- [x] Audit `package.json` for `react-markdown` — present at `^9.1.0`
- [x] Document library choice in CHAT-UI-BACKLOG.md §2.2
- [x] Implement `MarkdownRenderer` molecule (react-markdown + remark-gfm + rehype-sanitize + inline `rehypeCitations` plugin)
- [x] Implement `SourceBadge` atom (Phase CHAT-02 prerequisite, deferred from CHAT-01)
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

## CTRLP-02 — PATCH Session Endpoint · Done 2026-05-06

**Ref**: `docs/backlog/BACKLOG.md` §6.4.D, `docs/backlog/CHAT-UI-BACKLOG.md` §3

- [x] `PATCH /control-plane/v1/teams/{team_id}/sessions/{session_id}` — body: `{ title?, updated_at? }` (`status` deferred — no column exists yet)
- [x] Authorization: same team membership check as POST
- [x] `make code-quality && make test` in `control-plane-backend` (91 tests pass)
- [x] Regenerate `controlPlaneOpenApi.ts`

---

## QUALITY-01 / R1b — fred-runtime Quality Refactor (Simon/Dimitri) · Parallel, independent

**Ref**: `docs/backlog/FRED-RUNTIME-QUALITY.md`

**Why**: Code-quality audit (2026-04-27) identified five structural problems:
monolithic `client.py` (3 880 lines), no dependency container, blocking I/O
in async paths, untyped `Any` boundaries, no shared test fixtures.

**Target**: `control-plane-backend` structural quality — full async, no `Any`
at boundaries, `PodApplicationContext` container, ≥ 70% offline unit coverage.

| Phase     | Goal                                                                             | Effort | Status              |
| --------- | -------------------------------------------------------------------------------- | ------ | ------------------- |
| PROMPT-01 | Fix async/sync correctness (`kf_workspace_client.py`, `user_token_refresher.py`) | 1 h    | `[x]` ✅ 2026-04-27 |
| P2        | Shared test fixtures (`tests/conftest.py`)                                       | 1 h    | `[x]` ✅ 2026-04-27 |
| P3        | Split `client.py` → `fred_runtime/cli/` package                                  | 3 h    | `[x]` ✅ 2026-04-27 |
| P4        | Introduce `PodApplicationContext` container                                      | 4 h    | `[x]` ✅ 2026-04-27 |
| P5        | Eliminate `Any` at all typed boundaries                                          | 2 h    | `[x]` ✅ 2026-04-27 |

**Done when**: all gates in `FRED-RUNTIME-QUALITY.md §Definition of Done` are ticked.

**Status (2026-04-27):** PROMPT-01–P5 all complete. Two DoD gates deferred to **R1b**:

- `Any` zero at function boundaries: `runtime_context.py` + `cli/pod_client.py` need typed DTOs and circular-import analysis
- No file > 600 lines: `agent_app.py` (2 578 lines) needs router extraction into `fred_runtime/app/routers/`

See `FRED-RUNTIME-QUALITY.md §R1b` for exact file-by-file breakdown and fix approach.

**Status (2026-05-09 follow-up audit):** R1b is now active and partially
closed. Raw `basedpyright` is now clean in `fred-runtime`; the baseline file is
emptied; total offline coverage is still 65%; logging-style cleanup started;
and the largest runtime files remain monolithic.

| R1b slice | Goal                                                                                | Status                   |
| --------- | ----------------------------------------------------------------------------------- | ------------------------ |
| R1b-A     | Raw `basedpyright` clean in `fred-runtime`; baseline emptied or removed             | `[x]` ✅ 2026-05-09      |
| R1b-B     | Remaining `Any` / `dict[str, Any]` boundaries converged or explicitly marked opaque | `[ ]`                    |
| R1b-C     | Offline runtime coverage back to `>= 70%`; focused tests added for high-risk files  | `[ ]`                    |
| R1b-D     | Logging uniformity pass: no new `logger.*(f"...")`, touched files normalised        | `[~]` 2026-05-09 started |
| R1b-E     | Split `agent_app.py` first, then `integrations/v2_runtime/adapters.py` by concern   | `[ ]`                    |

**Execution rule:** while R1b is open, do not add new runtime-facing feature
logic to `agent_app.py`, `integrations/v2_runtime/adapters.py`, or
`runtime_context.py` without first paying down the seam you are extending.

**Next round order (for Codex or Claude):**

1. `R1b-E1` — split `agent_app.py` into execute/session/admin router modules.
2. `R1b-CTRLP-03` — add focused coverage for `graph_runtime.py`.
3. `R1b-B1` — tighten `runtime_context.py` and `cli/pod_client.py` boundaries.
4. `R1b-E2 / D2` — split `integrations/v2_runtime/adapters.py` by concern and continue log normalization.

---

## EVAL-01 — Agent Evaluation Track (Odélia) · Parallel, independent

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

## CTRLP-05 — Control-Plane Developer CLI · Important next backend ergonomics track

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

## RUNTIME-01 — Runtime CLI Ergonomics + Session Purge (Simon/Dimitri) · Closed 2026-04-26

**Ref**: `docs/backlog/BACKLOG.md` §6.4.B, §6.4.G

Completed in one session — no outstanding items.

- [x] `fred.github.test_assistant` graph agent (no LLM): exercises `echo`, `hitl choice`, `hitl text`,
      `trace`+sources, `error`, `long` scenarios; registered in `apps/fred-agents` registry
- [x] `fred.github.test_assistant` expanded into the managed-agent tuning and routing probe:
      `prompts.system`, `prompts.planning`, `prompts.routing`, `settings.verbose`,
      `settings.delay_ms`, `chat_options.attach_files`,
      `chat_options.libraries_selection`; optional `model routing` /
      `model planning` scenarios prove graph operation-aware routing without making
      the default UI-validation path depend on an LLM (2026-05-06)
- [x] `tuning_values` moved from `GraphAgentDefinition` to base `AgentDefinition` — all agent
      families (ReAct, Graph, Deep, Proxy) now carry typed tuning values (2026-05-06)
- [x] `TuningScalar` + `TuningValue` typed aliases replace all `Dict[str, Any]` in the
      tuning surface; `FieldSpec.default` and `AgentTuning.values` are now strongly typed (2026-05-06)
- [x] `inline_tuning: dict[str, TuningValue] | None` added to `RuntimeExecuteRequest` and
      internal `_AgentExecuteRequest`; direct-template path in `_resolve_agent_instance` applies
      inline overrides via `_apply_runtime_tuning` — enables CLI to inject session-local tuning
      without a managed agent instance (2026-05-06)
- [x] ReAct silent-drop gap closed: non-`prompts.system` tuning values now reach
      `render_prompt_template` via `extra_tokens` (keys dot-to-underscore transformed) (2026-05-06)
- [x] CLI `/inspect` — fetches `GET /agents/templates`, renders grouped FieldSpec table
      (kind, description, tags, field key/type/default/range, MCP servers) with color (2026-05-06)
- [x] CLI `/run <scenario>` — sends scenario keyword as message; tab-completes the 8
      `fred.github.test_assistant` scenario keywords (`echo`, `error`, `hitl choice`, `hitl text`,
      `long`, `model planning`, `model routing`, `trace`) (2026-05-06)
- [x] CLI `/tune key=value` + `/tuning` — session-local tuning overrides stored in
      `current_inline_tuning`; prompt badge `~N` in yellow when overrides are active;
      values forwarded as `inline_tuning` on every execute/stream request (2026-05-06)
- [x] `GET /agents/templates` added to `AgentPodClient.list_templates()` (2026-05-06)
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

## Sequence Summary (as of 2026-05-07)

```
CLOSED / SHIPPED
├── OBSERV-01  Observability hardening ─────────────────────────────────── 2026-04-26 ✅
├── RUNTIME-01  Runtime CLI ergonomics + session purge ──────────────────── 2026-04-26 ✅
├── CTRLP-05  Control-plane developer CLI ─────────────────────────────── 2026-04-25 ✅
├── CTRLP-01  Session updated_at + PATCH impl ─────────────────────────── ✅
├── CTRLP-02  PATCH session endpoint ──────────────────────────────────── 2026-05-06 ✅
├── CHAT-01  Chat UI architecture (Dimitri) ────────────────────────────── ✅
├── CHAT-02  Markdown rendering (Dimitri) ────────────────────────────── 2026-05-04 ✅
├── MEMORY-01  Multi-agent conversational memory (core) ────────────────── 2026-05-05 ✅
├── CTRLP-03  Pod catalog exposure + agent instance config ────────────── 2026-05-06 ✅ (model profiles deferred)
├── PROMPT-01  Prompt safety rendering fix + persistence validation ─────── 2026-05-07 ✅ (Slice D deferred)
└── FRONT-07  Rework UI architecture compliance (native controls → DS) ─── 2026-06-02 ✅

NOW (parallel)
├── Simon:    VALID-01  E2E live stack validation ─────────────────────────────► closes Phase 3b gate
├── Dimitri:    CHAT-03  Agent options panel + session title ──────────────────► unblocked (CHAT-01+CHAT-02+CTRLP-02 done)
├── Odélia:   EVAL-01  Evaluation RFC → harness ──────────────────────────────► independent
└── Dimitri:  swift branch commit + MEMORY-01 F.1–F.4 hardening (4 branches)

NEXT UP — Dimitri (next few days)
├── Commit  swift branch — CTRLP-03 + PROMPT-01 + version bumps + fred-agents + docs
├── MEMORY-02  fix/memory-agent-checkpoint-isolation
├── MEMORY-03  fix/remote-agent-runtime-execute-contract
├── MEMORY-04  refactor/local-agent-execute-projection
├── MEMORY-05  fix/team-memory-history-cap
├── CTRLP-03-def  GET /agents/model-profiles + ManagedModelProfileRef + form picker (deferred from CTRLP-03)
├── PROMPT-02   Team/personal prompt library: CRUD + OpenAPI regen + dedicated `Prompts` page
├── PROMPT-04   AgentFormModal prompt import/save + inline 422 display
└── PROMPT-06    Global prompt marketplace publication (after PROMPT-02 + PROMPT-04)

NEXT UP — Dimitri (unblocked now)
└── CHAT-03  Agent options panel refinements + session title inline edit
```

---

## MEMORY-01 — Multi-Agent Conversational Memory (Dimitri) · Core implemented, hardening pending (2026-05-05)

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

## CTRLP-03 — Pod Catalog Exposure + Agent Instance Configuration Contract (Dimitri) · Blocks form UI

**Ref**: `docs/backlog/BACKLOG.md` §3d

**Why**: Team admins must be able to select which MCP tools to activate and
which model profile to use when creating or editing an agent. Currently the
pod catalogs (`mcp_catalog.yaml`, `models_catalog.yaml`) are private to the
runtime — the control-plane and frontend have zero visibility. Without this
contract, the form can only show static read-only lists and cannot write
tool or model selections back to the instance.

Additionally: when the pod is redeployed with a changed catalog, any enrolled
instance that referenced a now-missing server or profile must surface a clear
error to the admin ("delete and recreate") rather than failing silently at
execution time.

**Sequence**: backend contract first (fred-runtime endpoints → control-plane
schemas and service → OpenAPI regen), frontend form last.

**Tasks**:

_fred-runtime (CTRLP-03):_

- [x] `GET /agents/mcp-catalog` → `McpCatalogResponse` (all catalog servers, no URLs/credentials)
- [ ] `GET /agents/model-profiles` → `ModelProfilesResponse` (all profiles, `is_default` from `default_by_capability`) — deferred
- [x] Extend `_apply_runtime_tuning`: filter MCP servers to `selected_mcp_server_ids` (`model_profile_id` deferred)
- [x] `make code-quality && make test` in `fred-runtime`

_control-plane-backend (CTRLP-03):_

- [ ] `ManagedModelProfileRef` in `config/models.py` — deferred
- [ ] `AgentTemplateSummary.available_model_profiles` populated from pod fan-out — deferred
- [x] `CreateAgentInstanceRequest` / `UpdateAgentInstanceRequest`: add `mcp_server_ids`; reject unknown IDs with 422 (`model_profile_id` deferred)
- [x] `ManagedAgentTuning`: add `selected_mcp_server_ids` (`model_profile_id` deferred)
- [x] `ManagedAgentTuning`: add dedicated `mcp_config_values` per MCP server; validate unknown server IDs / config keys with 422
- [x] `ManagedAgentInstanceSummary`: add `runtime_status`, `catalog_warnings`
- [x] `ManagedAgentInstanceSummary` / `ExecutionPreparation`: expose `mcp_config_values` and resolved `effective_chat_options`
- [x] Enrollment service: validate IDs against live catalog, store selection
- [x] Enrollment/update service: preserve tri-state MCP selection (`null` = inherit default, `[]` = activate none, list = exact subset)
- [x] Drift detection in `list_managed_agent_instances`: compare stored IDs vs live catalog; `runtime_status = "unavailable"` when pod unreachable
- [x] Regenerate `controlPlaneOpenApi.ts`
- [x] `make code-quality && make test` in `control-plane-backend`

_catalog/runtime hardening (CTRLP-03):_

- [x] Reject duplicate MCP server IDs when loading `mcp_catalog.yaml`
- [x] Remove duplicate `mcp-knowledge-flow-prometheus-ops` entry from `apps/fred-agents/config/mcp_catalog.yaml`
- [x] `make code-quality && make test` in `fred-agents`

_frontend (CTRLP-03 — after CTRLP-03 merged):_

- [x] `AgentFormBody`: MCP checkbox multi-select from `mcp_servers` on the template
- [ ] `AgentFormBody`: model profile picker from `available_model_profiles` — deferred
- [x] Wire `mcp_server_ids` into `AgentFormPayload` and create/update mutations (`model_profile_id` deferred)
- [x] `AgentCard`: "pod unreachable" badge for `runtime_status = "unavailable"`
- [x] `AgentCard`: MCP drift warning banner when `catalog_warnings` non-empty
- [x] `McpServerCard` reads/writes per-server `configValues` (not flat `tuningFieldValues`); `AgentFormBody` passes server-scoped slices; `AgentFormModal` stores `mcpConfigValues` separately and preserves tri-state (`[]` ≠ `null`); `TeamAgentsPage` forwards `mcp_config_values` to create/update API calls (2026-05-06)
- [x] `useChatSse` exposes `effectiveChatOptions` from each prepare-execution; `AgentOptionsPanel` gates sections on it; `ManagedChatPage` syncs search defaults from agent config (2026-05-06)
- [x] `tsc --noEmit` + `npm run build` pass

---

## PROMPT-01 — Prompt Safety: Rendering Fix + Persistence Validation (Dimitri) · Done 2026-05-07

**Ref**: `docs/rfc/PROMPT-SAFETY-RFC.md` · `docs/backlog/BACKLOG.md` §3d.9

**Why**: Production incident 2026-05-06 — system prompts with code braces
(`ExcelScript.Workbook { ... }`) or unknown `{token}` patterns crashed the agent
silently at turn-start with `AttributeError` / `ValueError`. No validation existed
at save time.

- [x] `fred_sdk.contracts.prompt_utils` — `PROMPT_SAFE_TOKENS` registry + `PromptTemplateError` + `validate_prompt_template`
- [x] `react_prompting.py` — regex renderer replaces `format_map` + `_LiteralFriendlyDict`; crash-proof for all brace patterns
- [x] `control_plane_backend/product/service.py` — `_validate_tuning_field_values` calls validator for `"prompt"` fields; unknown tokens → 422
- [x] 26 new offline tests across `fred-sdk` and `control-plane-backend`
- [x] `make code-quality && make test` green in all three packages

**Remaining (next prompt slices, separate branch)**:

- [ ] PROMPT-02 — team/personal prompt library in `control-plane-backend`:
      `Prompt` entity CRUD + DB migration + OpenAPI regen + dedicated `Prompts` page
- [ ] PROMPT-04 — `AgentFormModal` keeps manual prompt editing and adds
      `[Import from library]` + `[Save as prompt]` + inline 422 display
- [ ] PROMPT-06 — global prompt marketplace publication-by-copy after the team/personal
      prompt library is stable

---

## Open Decisions (need sync before implementation)

| Decision                                                           | Owner           | Blocking                                                                            |
| ------------------------------------------------------------------ | --------------- | ----------------------------------------------------------------------------------- |
| Option A/B/C for `updated_at` freshness                            | Florian + all   | CTRLP-01, then Dimitri CHAT-01 wiring                                                 |
| Whether `ExecutionPreparation` should expose agent runtime options | Simon + Florian | Resolved 2026-05-06: yes — typed `effective_chat_options` on `ExecutionPreparation` |
| Checkpoint TTL policy for standalone mode                          | Simon           | BACKLOG.md §3b.9, non-urgent                                                        |
| `session_purge_queue` keep or repurpose                            | Florian         | BACKLOG.md §6.4.E, non-urgent                                                       |
