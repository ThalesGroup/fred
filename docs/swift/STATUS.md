# Fred Platform — Current Status

**Purpose**: One-page queryable snapshot of team activity. Updated each session.
Answers "what's next?", "who owns X?", "what was done this week?", "what's blocked?"

**AI assistants**: for structured queries ("status of S1", "what is C1-deferred?")
read [`docs/data/id-legend.yaml`](data/id-legend.yaml) first — it is faster than scanning prose.
For sprint-level structured data, read [`docs/data/sprint.yaml`](data/sprint.yaml).

Ask Claude Code directly: *"What is Simon working on?"* · *"What tests cover MCP config?"*
· *"What is the next backend task for Dimitri?"* · *"What's blocking Félix?"*

Last updated: 2026-05-10

---

## Team

| Person | Role |
|---|---|
| **Dimitri** | Lead architect — backend contracts, runtime design, cross-cutting |
| **Félix** | Frontend — rework design system, chat UI migration |
| **Simon** | Backend — fred-runtime, fred-sdk, observability, E2E validation |
| **Florian** | Backend — control-plane-backend, APIs, DB, session lifecycle |
| **Odélia** | Agent evaluation — deepeval track (independent) |
| **Claire** | Team organisation, planning |
| **Arnaud** | Team organisation, planning |

---

## In Progress Now (week of 2026-05-07)

| Feature | Owner | Status | Backlog ref |
|---|---|---|---|
| S1 — E2E live stack validation (managed + HITL scenarios) | Simon | In progress | [BACKLOG §3b.7](backlog/BACKLOG.md) |
| 6C — Agent options panel + session title inline edit | Félix | In progress (unblocked) | [CHAT-UI-BACKLOG §3](backlog/CHAT-UI-BACKLOG.md) |
| M1-F.1..F.4 — Multi-agent memory hardening (4 branches) | Dimitri | Next up | [MULTI-AGENT-MEMORY-BACKLOG](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) |
| P1-D1 — Backend prompt CRUD | Codex | **Done 2026-05-08** | [BACKLOG §3d.9](backlog/BACKLOG.md) |
| P1-D1b — Backend extension (versioning, analytics, context) | Dimitri | **Done 2026-05-10** | [BACKLOG §3d.9](backlog/BACKLOG.md) · [RFC](rfc/PROMPT-LIBRARY-RFC.md) |
| P1-D2 — PromptsPage + AgentFormModal (import, drift badge, 422) | TBD | **Next — unblocked** | [BACKLOG §3d.9](backlog/BACKLOG.md) |
| P1-D3 — Chat context picker (replaces free textarea) | Félix | **Next — unblocked** | [BACKLOG §3d.9](backlog/BACKLOG.md) |
| C1-deferred — Model profiles endpoint + form picker | Dimitri | Queued | [BACKLOG §3d](backlog/BACKLOG.md) |
| P1-E — Global prompt marketplace | Dimitri | Deferred (after P1-D2 + P1-D3) | [BACKLOG §3d.10](backlog/BACKLOG.md) |
| P1-F — Token cost KPI integration | Simon + Dimitri | Deferred (after O1 + fred-core) | [BACKLOG §3d.9](backlog/BACKLOG.md) |
| O1 — Agent evaluation harness (deepeval) | Odélia | RFC exists, impl not started | [AGENT-EVALUATION-RFC](rfc/AGENT-EVALUATION-RFC.md) |

---

## Closed This Week (2026-05-01 → 2026-05-10)

| Feature | Owner | Closed | Backlog ref | Tests |
|---|---|---|---|---|
| P1-D1b — Backend extension: versioning, analytics, context integration | Dimitri | 2026-05-10 | [BACKLOG §3d.9](backlog/BACKLOG.md) | `test_main.py` (6 new tests, 120 passing) |
| R1b-A — fred-runtime raw type-check cleanup + baseline emptied | Codex | 2026-05-09 | [FRED-RUNTIME-QUALITY](backlog/FRED-RUNTIME-QUALITY.md) | `make code-quality`, `make test`, raw `basedpyright` |
| C1 — Pod catalog exposure + MCP tri-state selection | Dimitri | 2026-05-06 | [BACKLOG §3d](backlog/BACKLOG.md) | `test_mcp_config.py`, `test_agent_app.py`, `test_main.py` |
| P1 — Prompt safety: rendering fix + persistence validation | Dimitri | 2026-05-07 | [BACKLOG §3d.9](backlog/BACKLOG.md) | `test_prompt_utils.py`, `test_main.py` |
| F2 — PATCH session endpoint (`updated_at`, `title`) | Florian | 2026-05-06 | [BACKLOG §6.4.D](backlog/BACKLOG.md) | `test_main.py` |
| fred-agents cleanup (remove simple_assistant, fix IDs) | Dimitri | 2026-05-07 | [WORKPLAN](WORKPLAN.md) | `test_smoke.py` |
| Version bumps: fred-core 2.0.3, fred-sdk 2.0.4, fred-runtime 2.0.5 | Dimitri | 2026-05-07 | — | — |
| OPERATING_MODES.md — standalone vs full-stack guide | Dimitri | 2026-05-07 | — | — |

---

## Recently Closed (last 30 days — reference)

| Feature | Owner | Closed | Ref |
|---|---|---|---|
| 6B — Markdown rendering (react-markdown, CodeBlock, SourceBadge) | Dimitri | 2026-05-04 | [CHAT-UI-BACKLOG §2](backlog/CHAT-UI-BACKLOG.md) |
| M1 — Multi-agent conversational memory (core, phases A–E) | Dimitri | 2026-05-05 | [MULTI-AGENT-MEMORY-BACKLOG](backlog/MULTI-AGENT-MEMORY-BACKLOG.md) |
| Agent FieldSpec declarations (all 3 production agents) | Dimitri | 2026-05-04 | [BACKLOG §3d](backlog/BACKLOG.md) |
| AgentFormModal refactor (template browser, tuning fields) | Dimitri | 2026-04-28 | [AGENT-INSTANCE-FORM-RFC](rfc/AGENT-INSTANCE-FORM-RFC.md) |
| S2 — Prometheus cardinality fix + observability hardening | Simon | 2026-04-26 | [BACKLOG §7.3](backlog/BACKLOG.md) |
| S3 — Runtime CLI ergonomics + session purge | Simon/Dimitri | 2026-04-26 | [BACKLOG §6.4.B](backlog/BACKLOG.md) |
| D1 — Control-plane developer CLI (`make cli`) | Dimitri | 2026-04-25 | [BACKLOG](backlog/BACKLOG.md) |
| 6A — Chat UI architecture (new component tree) | Félix | — | [CHAT-UI-BACKLOG §1](backlog/CHAT-UI-BACKLOG.md) |
| F1 — Session `updated_at` strategy + PATCH impl | Florian | — | [BACKLOG §6.4.D](backlog/BACKLOG.md) |
| R1 — fred-runtime quality refactor (P1–P5 only) | Simon | 2026-04-27 | [WORKPLAN R1](WORKPLAN.md) |

---

## Milestones

| Milestone | Tracks | Target | Status | Completion |
|---|---|---|---|---|
| Phase 3 complete — E2E validated + M1 hardened | S1 + M1-F.1..F.4 | TBD | In progress | ~60% |
| Prompt library shipped — P1-D1 + P1-D2 | P1-D1 ✅ + P1-D2 | TBD | In progress | 50% |
| Chat UI Phase 6 complete — 6C shipped | 6C | TBD | In progress | ~80% |
| Frontend agentic-backend removal — Phase 5E | 5E | TBD | Not started | 0% |
| Agent evaluation v1 — O1 harness live | O1 | TBD | Not started | 0% |
| Model profiles — C1-deferred shipped | C1-deferred | TBD | Queued | 0% |

> Target dates to be defined. Track them in `docs/data/sprint.yaml` when known.

---

## Velocity (last 2 weeks — 2026-04-25 → 2026-05-09)

| Metric | Value |
|---|---|
| Items closed | 11 major items (S2, S3, D1, F1, F2, R1, 6A, 6B, M1-core, C1, P1) |
| Sub-items closed | 6 (C1-A, C1-B, C1-C, C1-D, P1-D1, R1b-A) |
| Items opened net | +3 (M1-F.1..F.4 hardening branches, P1-D2, R1b reopened) |
| Items deferred | 2 (C1-deferred, P1-E) |
| Subjective velocity | **On track, with caution** — `fred-runtime` raw type debt is closed, but coverage and file-splitting hardening should still be paid down before more runtime-surface growth |

---

## Blocked / Pending Decisions

| Item | Blocked on | Owner |
|---|---|---|
| S1 live stack scenarios | Live pod available + `FRED_AGENT_INSTANCE_ID` set | Simon |
| M1 F.1–F.4 hardening branches | Swift branch commit | Dimitri |
| 6C full completion | S1 gate (runtime SSE validation confirmed) | Félix |

---

## Feature → Tests quick reference

| Feature area | Test file(s) | Package |
|---|---|---|
| Managed agent CRUD, tuning validation, execution prep | `test_main.py` | `control-plane-backend` |
| Control-plane developer CLI commands | `test_cli.py` | `control-plane-backend` |
| Session lifecycle, purge policies | `test_lifecycle_actions.py` | `control-plane-backend` |
| ReBAC policy engine | `test_policy_engine.py` | `control-plane-backend` |
| Agent runtime (tuning application, MCP selection, KPI) | `test_agent_app.py` | `fred-runtime` |
| MCP catalog loading + tri-state selection (C1) | `test_mcp_config.py` | `fred-runtime` |
| Multi-agent memory — runtime wiring (M1 phases C+D) | `test_conversational_memory.py` | `fred-runtime` |
| Prompt safety token registry + validation (P1) | `test_prompt_utils.py` | `fred-sdk` |
| Multi-agent memory — SDK primitives (M1 phases A+B) | `test_conversational_memory.py` | `fred-sdk` |
| SSE execution contracts, `ExecutionGrant`, events | `test_execution_contracts.py` | `fred-sdk` |
| Prometheus KPI cardinality + labels (S2) | `test_prometheus_kpi_store.py` | `fred-core` |
| Structured KPI log output (S2) | `test_log_kpi_store.py` | `fred-core` |
| CLI KPI ring buffer display (S2/S3) | `test_kpi_display.py` | `fred-runtime` |
| History store, HITL persistence, session purge (S3) | `test_history.py` | `fred-runtime` |
| Pod client, CLI session commands | `test_client.py` | `fred-runtime` |

---

## How to use this file (for Claire and Arnaud)

Open this repository in **VS Code** and install the **Claude Code** extension (see
[claude.ai/code](https://claude.ai/code)). Then ask questions directly in the chat panel:

- *"What is Simon working on this week?"*
- *"What was closed since Monday?"*
- *"Who owns the chat UI?"*
- *"What tests cover the MCP configuration feature?"*
- *"What is blocking Félix?"*
- *"Where is the prompt safety feature tracked?"*

Claude Code reads this file plus the linked backlogs and code to answer. No Jira login needed.

For deeper dives:
- Feature specs → [`backlog/BACKLOG.md`](backlog/BACKLOG.md)
- Sprint details → [`WORKPLAN.md`](WORKPLAN.md)
- Architecture decisions → [`design/`](design/)
- Technical proposals → [`rfc/`](rfc/)
