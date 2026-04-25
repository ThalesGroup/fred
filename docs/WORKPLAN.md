# Workplan

Short-cycle execution plan. Updated as items close.
Backlogs contain the full specs — this document answers **who does what, in what order, and what runs in parallel**.

Last updated: 2026-04-25

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

Three scenarios to validate from `fred-agent-chat`, in order:

1. **Managed execution end-to-end**
   - `--team-id personal`, one `agent_instance_id` enrolled in control-plane
   - Full cycle: prepare-execution → SSE stream → session_history written
   - Tick `[ ] one managed execution works end-to-end from fred-agent-chat`

2. **Managed HITL resume**
   - One turn paused on `awaiting_human`, resumed with `sendHitlResume`
   - Validate session_id + checkpoint_id consistency across pause/resume
   - Tick `[ ] one managed HITL resume flow works end-to-end from fred-agent-chat`

3. **Raw agent_id path still works through team-scoped managed path**
   - Same pod, same agent capability, accessed via `agent_instance_id` vs raw
   - Tick `[ ] one runtime capability reachable through raw agent_id also works correctly through team-scoped managed execution`

**Done when**: all three ticked in BACKLOG.md §3b.7, `make test` green.

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
- [ ] If A: wire call in `ManagedChatPage` on each `turn_persisted` SSE event (Félix, after F1 lands)
- [x] `make code-quality && make test` in `control-plane-backend`

---

## S2 — Prometheus Cardinality Fix (Simon) · Parallel, no gate

**Why**: `session_id` and `user_id` as Prometheus label dimensions create unbounded cardinality. Safe to fix now, independent of everything else.

**Ref**: `docs/backlog/BACKLOG.md` §7.3, §7.6.A

- [x] Remove `session_id` from Prometheus labels emitted from runtime KPI dims
- [x] Remove `user_id` from Prometheus labels emitted from runtime KPI dims
- [x] Keep both in structured KPI log output (OpenSearch / log backend)
- [x] Same cleanup for graph/KF phase timers via the shared Prometheus KPI sink
- [x] `make code-quality && make test` in `fred-runtime`

Can be done in parallel with S1, shipped separately.

---

## Phase 6A — Chat UI Architecture (Félix) · Starts after S1 + F1

**Ref**: `docs/backlog/CHAT-UI-BACKLOG.md` §1

Build the new component tree for `ManagedChatPage`. No markdown yet. Full spec in the backlog.

**Component build order** (sequential within Félix's track):

```
Step 1 — Atoms (no deps):
  MessageBubble · StreamingCursor · ToolBadge · SourceBadge

Step 2 — Molecules (need atoms):
  UserMessage · AssistantMessage
  ToolCallStep · ToolResultStep · ThinkingAccordion
  SourceCard · SourcesPanel
  ChatInputBar

Step 3 — Organisms (need molecules):
  ChatMessagesArea · AssistantTurn

Step 4 — Refactor ManagedChatPage to use all new components
Step 5 — Map SSE events to ConversationMessage state
Step 6 — Normalise history from runtime messages_url_template
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

## Phase 6B — Markdown Rendering (Félix) · After 6A

**Ref**: `docs/backlog/CHAT-UI-BACKLOG.md` §2

- [ ] Audit `package.json` for `react-markdown`
- [ ] Document library choice in CHAT-UI-BACKLOG.md §2.2 before writing code
- [ ] Implement `MarkdownRenderer` molecule
- [ ] Implement `CodeBlock` molecule (monospace + copy)
- [ ] Wire into `AssistantMessage` only

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

**Why**: `fred-agent-chat` gives us a first-class runtime validation console, but
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
- [ ] Run one live stack validation in no-security mode
- [ ] Run one live stack validation in Keycloak-enabled mode
- [ ] Run one operator happy path for enroll / unbind / prepare-execution

---

## Sequence Summary

```
NOW (parallel)
├── Simon:   S1 E2E validation ──────────────────────────────────► unblocks 6A
├── Simon:   S2 Prometheus cardinality fix ──────────────────────► ship anytime
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

## Open Decisions (need sync before implementation)

| Decision | Owner | Blocking |
|---|---|---|
| Option A/B/C for `updated_at` freshness | Florian + all | F1, then Félix 6A wiring |
| Whether `ExecutionPreparation` should expose agent runtime options | Simon + Florian | Félix 6C scope |
| Checkpoint TTL policy for standalone mode | Simon | BACKLOG.md §3b.9, non-urgent |
| `session_purge_queue` keep or repurpose | Florian | BACKLOG.md §6.4.E, non-urgent |
