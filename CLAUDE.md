# CLAUDE.md

Repository-wide instructions for Claude Code.

---

## Task ID Convention — read this before touching any backlog or doc

Every tracked item in this project carries a **short identifier** that appears
in backlog files, STATUS.md, WORKPLAN.md, commit messages, and sprint.yaml.
Understanding the convention is required before writing, updating, or linking
any task.

### Canonical reference

**`docs/swift/data/id-legend.yaml`** — machine-readable registry of every known ID,
its owner, status, domain, and backlog cross-reference. AI assistants: read
this file when asked "what is X?", "who owns Y?", or "what is the status of Z?"
before scanning prose documents.

### Format for NEW items (post 2026-05-08)

```
<DOMAIN>-<N>[-<sub>]
```

| Prefix | Area |
|--------|------|
| `CP`   | control-plane features (product, session, admin APIs) |
| `RT`   | runtime features (execution, SSE, HITL, checkpoints) |
| `CU`   | chat-UI components and phases |
| `FE`   | frontend/rework migration |
| `MA`   | multi-agent and memory features |
| `EV`   | evaluation and benchmarking (Odélia track) |
| `OBS`  | observability, devops, CLI ergonomics |

Sub-phase suffixes:
- Lowercase letter (`-a`, `-b`, `-c`) for a major sub-feature within the track
- `.1`, `.2`, `.3` for individual task items within a sub-feature

Examples: `CP-1`, `RT-3-a`, `CU-4.1`, `MA-2-b.3`

### Legacy IDs (pre-convention — do NOT rename)

Items created before 2026-05-08 use shorter ad-hoc notation. The table below
lists the legacy prefixes and their meanings. **Never rename a legacy ID** —
renaming breaks cross-references in backlog files, commit messages, and git
history. Add a `legacy_id` field in sprint.yaml if you need to bridge notations.

| Legacy prefix | Meaning | Disambiguation |
|---|---|---|
| `S`  | Simon's track (runtime validation, observability) | S1, S2, S3 |
| `F`  | Florian's track (control-plane APIs) | F1, F2 — NOT "Frontend" |
| `M`  | Multi-agent memory feature | M1, M1-F.1..F.4 — "F" = internal phase letter |
| `C`  | Control-plane feature contract | C1, C1-A..D — NOT "Chat UI" |
| `P`  | Prompt safety / library feature | P1, P1-D1, P1-D2, P1-E |
| `O`  | Odélia's evaluation track | O1 |
| `D`  | Developer CLI track | D1 |
| `R`  | Runtime quality refactor | R1, R1-P1..P5 — "P" = quality phase |
| `6x` | Chat UI phases (Phase 6) | 6A, 6B, 6C, 6D |
| `5x` | Frontend migration phases (Phase 5) | 5A, 5B, 5C, 5D, 5E |

### Rules

1. Every new backlog item gets an ID before implementation starts.
2. The ID goes in: the backlog `[ ]` checkbox, STATUS.md "In Progress" table,
   sprint.yaml, and the commit message subject line.
3. Add the new ID to `docs/swift/data/id-legend.yaml` immediately — not after the
   work is done.
4. Status in `id-legend.yaml` and `sprint.yaml` must be kept in sync with
   the backlog checkboxes.

---

## Quick status (operational queries — read this first)

**For questions about team activity, sprint status, feature progress, or test coverage:**
read [`docs/swift/STATUS.md`](./docs/swift/STATUS.md) only. It is self-contained and answers:
- Who is working on what right now
- What was delivered this week
- What is blocked and why
- Which tests cover which feature

Only read the documents below if the specific detail is not in `docs/swift/STATUS.md`.
For deeper feature specs, follow the `Backlog ref` links inside `STATUS.md` directly.

**The mandatory read order below applies to development tasks only** (writing code,
touching APIs, implementing features). Skip it for operational/status queries.

---

## Mandatory Read Order

1. [`docs/swift/README.md`](./docs/swift/README.md) — document taxonomy and navigation map; read first to orient
2. [`docs/swift/platform/DEVELOPER_CONTRACT.md`](./docs/swift/platform/DEVELOPER_CONTRACT.md)
3. [`docs/swift/platform/PLATFORM_RUNTIME_MAP.md`](./docs/swift/platform/PLATFORM_RUNTIME_MAP.md)
4. [`docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](./docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md)
5. [`docs/swift/platform/REBAC.md`](./docs/swift/platform/REBAC.md) when access/team behavior is touched
6. [`docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`](./docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md) when touching execution contracts, `fred-sdk`, `fred-runtime`, runtime OpenAPI, frontend runtime typing, the CLI, or runtime observability/tracing/KPI/Langfuse metadata
7. [`docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md) when touching control-plane product/session/admin APIs or frontend migration away from `agentic-backend`
8. [`docs/swift/backlog/BACKLOG.md`](./docs/swift/backlog/BACKLOG.md) for migration phase status and next-step sequencing
9. [`docs/swift/WORKPLAN.md`](./docs/swift/WORKPLAN.md) for current sprint assignments and parallel work — always read before starting any task to avoid duplicating in-progress work
10. [`docs/swift/platform/FRONTEND_CODING_GUIDELINES.md`](./docs/swift/platform/FRONTEND_CODING_GUIDELINES.md) when touching **any** file under `frontend/src/rework/` — mandatory before writing or reviewing CSS/TSX
11. [`docs/swift/backlog/FRONTEND-BACKLOG.md`](./docs/swift/backlog/FRONTEND-BACKLOG.md) when touching frontend bootstrap, session, or team identity
12. [`docs/swift/backlog/CHAT-UI-BACKLOG.md`](./docs/swift/backlog/CHAT-UI-BACKLOG.md) when touching `ManagedChatPage`, chat UI components, or SSE event rendering
13. [`docs/swift/ux/COMPONENT-UX.md`](./docs/swift/ux/COMPONENT-UX.md) when implementing or refining any chat UI component — check open UX issues before writing CSS

---

## Task Lifecycle — Mandatory Protocol

Every non-trivial task follows this sequence without exception. Steps cannot be skipped or reordered.

### Step 1 — RFC first (for any design or API decision)

Before writing a single line of code for a feature, schema change, new endpoint, or component that involves a design choice:

1. Write a short RFC in `docs/swift/rfc/` (or amend an existing one if the area is already covered).
2. The RFC must state: **problem**, **proposed solution**, **alternatives considered**, **impact on existing contracts/docs**.
3. For purely mechanical fixes (bug in one function, typo, missing field already agreed on), an RFC is not required — state why it is mechanical.

### Step 2 — Backlog entry before implementation

1. Find the relevant backlog file (`BACKLOG.md`, `CHAT-UI-BACKLOG.md`, `FRONTEND-BACKLOG.md`, or `WORKPLAN.md`).
2. Add (or confirm existence of) a `[ ]` task item for the work about to be done.
3. If no backlog file covers the area, say so and ask the developer where to track it before proceeding.

### Step 3 — Explicit developer confirmation

After step 1 and step 2, **stop and present the plan** to the developer:

- What will be built or changed
- Which files will be touched
- Which tests will be added or updated
- Which docs will be updated as a result

**Do not begin implementation until the developer confirms.** One sentence of approval ("yes go ahead", "ok", "looks good") is enough. This rule is bypassed only when the developer explicitly says "implement immediately" or similar.

### Step 4 — Implementation

Write the code. Follow all coding constraints below.

### Step 5 — Verification (mandatory before reporting done)

Run in the touched project's root:
```
make code-quality   # ruff check + format (Python) or tsc + prettier (frontend)
make test           # offline unit tests only
```
If either fails, fix before proceeding. Do not report the task as done with red tests or lint errors.

### Step 6 — Doc update checklist (mandatory, same session)

At the end of every task, before the final reply to the developer, work through this checklist and update every applicable file:

| What changed | File to update |
|---|---|
| A backlog `[ ]` item is now done | Mark `[x]` in the relevant backlog file |
| A new behaviour, API field, or contract change | Update the spec table or behaviour description in the relevant design doc |
| A frozen contract was touched (`execution.py`, `agent_app.py`, OpenAPI) | Add a dated entry to `RUNTIME-EXECUTION-CONTRACT.md §8` or `CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| A UX component is implemented or its visual/interaction status changes | Update `docs/swift/ux/COMPONENT-UX.md` |
| A phase progress row exists for the area | Update the progress table at the bottom of the relevant backlog file |
| A WORKPLAN sprint item is finished | Mark it done in `docs/swift/WORKPLAN.md` |
| Code and a design doc diverge | Fix the design doc in the same change |

**Close-out statement (required in every final reply):** End every task response with a fenced block:

```
## Task close-out
- Code: <one line — what was changed>
- Tests: <pass / n tests added / why none needed>
- Docs updated: <list each file touched, or "none — mechanical fix">
- Backlog: <item marked done, or "none — not tracked yet">
- Skipped steps: <list any Step 1–3 steps skipped and why>
```

This block is non-negotiable. It exists so the developer can verify completeness in 10 seconds without reading the full response.

---

## Coding Constraints — Non-Negotiable

### General

- **Minimal scope.** Implement exactly what the task requires. No refactors, no "while I'm here" cleanups, no abstraction for hypothetical future use.
- **Shared code first.** Before writing a new utility, check whether it exists in `fred-core`, `fred-sdk`, or the shared frontend design system. Duplicate code is a defect.
- **Fewer lines over more lines.** If two approaches produce the same result, choose the shorter one. Verbose code is harder to audit.
- **No new architecture.** Do not invent a new endpoint family, service boundary, or migration direction. If the task requires one, write an RFC (Step 1) and stop.
- **No over-engineering.** No factory for a single implementation, no plugin system for a single case, no abstraction for three similar lines. Three similar lines is correct; premature abstraction is a bug.

### Python

- **Pydantic models for all public contracts.** Request bodies, response bodies, config schemas: always `BaseModel`. Never raw `dict` or `TypedDict` at a service boundary.
- **No Pydantic for internal dataclasses.** Pure-Python `@dataclass` or plain classes for internal structures that never cross an HTTP or serialisation boundary.
- **No mutable default arguments.** No `def f(x=[])`. Use `Field(default_factory=...)` in Pydantic, `field(default_factory=...)` in dataclasses.
- **Type-annotate every function signature.** Return type included. `Any` is allowed only when the upstream contract forces it; document why.
- **No silent `except Exception`.** Catch specific exceptions. When a broad catch is genuinely needed, log the exception and re-raise or return an explicit error value.
- **Tests offline by default.** All tests in `tests/` run without network, database, or external service. Tests that require external dependencies are marked `@pytest.mark.integration` and are excluded from `make test`.
- **One test file per module.** `tests/test_<module>.py` mirrors `package/<module>.py`. Do not pile unrelated tests into a single file.
- **Use existing `fred-core` utilities.** `ThreadSafeLRUCache`, `read_env_bool`, `get_config`, logging setup — do not reimplement.
- **Never hand-edit generated files.** `openapi.json`, `runtimeOpenApi.ts`, `controlPlaneOpenApi.ts` — regenerate from source. Document the regeneration command if you run it.

### Frontend (TypeScript / React)

- **Design system tokens only.** No hardcoded colours, sizes, or spacing. No `var(--token, fallback)` with colour or dimension fallbacks — add the missing token to the token file instead.
- **Every `background` has an explicit `color`.** Colour and background are always paired.
- **CSS modules only.** No inline styles, no `styled-components`, no MUI `sx` prop in rework components.
- **No MUI in `src/rework/`.** Use design system atoms (`Button`, `Icon`, `IconButton`, `Switch`, `TextInput`, `TextArea`, `ButtonGroup`, `Select`). If an atom is missing, add it — do not pull in MUI.
- **Strict icon typing.** Icon names must be in `MaterialIconType` (`Type.ts`). Add the name to the union rather than widening to `string`.
- **No hand-editing generated slices.** `runtimeOpenApi.ts`, `controlPlaneOpenApi.ts`, `knowledgeFlowOpenApi.ts` — regenerate from OpenAPI spec.
- **`tsc --noEmit` and Prettier must pass** before reporting a frontend task done.
- **No `any` at component boundaries.** Props interfaces are typed. Internal state can use `unknown` with a guard; never `as any` at a prop or hook boundary.

---

## Non-Negotiable Defaults (unchanged)

- Keep scope minimal. No over-engineering.
- Do not invent a new architecture, endpoint family, or migration direction.
- Do not take product or architecture initiatives when the docs already define the split.
- Use existing conventions and existing Make targets.
- Run `make code-quality` and `make test` in each touched project.
- Keep default tests offline. Any external dependency test must be marked `integration`.
- Prefer stronger typing on existing contracts over new wrappers or ad hoc payloads.
- Never hand-edit generated files such as `frontend/src/slices/runtime/runtimeOpenApi.ts`; regenerate them from source contracts.
- **Docs are part of the definition of done. Every task is incomplete until the relevant docs are updated.**

---

## Fred Runtime Topology

Canonical source: [`docs/swift/platform/PLATFORM_RUNTIME_MAP.md`](./docs/swift/platform/PLATFORM_RUNTIME_MAP.md)

This defines:

- `fred-runtime` (execution framework library), `apps/fred-agents` (production agent pod), Knowledge Flow API, Control Plane API responsibilities.
- `agentic-backend` has been **removed** from the active monorepo (archived in `ignored/fred/agentic-backend`). Do not reference it as a target or active service.
- Knowledge Flow / Agentic / Control Plane Temporal worker responsibilities.

---

## Current Architecture State (as of 2026-05-11)

The backend migration from `agentic-backend` is **complete**. What the monorepo has today:

| Component | Role |
|---|---|
| `libs/fred-sdk` | Shared execution contracts and SDK |
| `libs/fred-runtime` | Execution framework library (agent engine, SSE, HITL, checkpoints) |
| `apps/fred-agents` | Production agent pod — runnable agent definitions built on `fred-runtime` |
| `apps/control-plane-backend` | Product/session/admin APIs, ExecutionGrant issuance |
| `knowledge-flow-backend` | Ingestion, documents, retrieval |
| `ignored/fred/agentic-backend` | **Removed** — archived for reference only |

**What remains of the migration:** the frontend still imports ~30 types from `agenticOpenApi.ts`
(a file generated from the now-removed `agentic-backend` schema). This is Phase 5E — a
frontend-only cleanup tracked in [`docs/swift/backlog/FRONTEND-BACKLOG.md §7`](./docs/swift/backlog/FRONTEND-BACKLOG.md).

- New execution code → `libs/fred-runtime` / `libs/fred-sdk` / `apps/fred-agents`
- New product/session/admin code → `apps/control-plane-backend`
- Phase 1 execution contracts frozen: [`docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`](./docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md)
- Phase 3a product boundary: [`docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md)

---

## Continuation Rules

- treat `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` as the execution contract source of truth
- treat `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` as the product/session/admin source of truth
- treat `docs/swift/backlog/BACKLOG.md` as the sequencing and status source of truth
- prefer editing contract source files over adding compatibility layers
- if a needed type is missing, fix `fred-sdk` or the FastAPI schema first and regenerate instead of adding local mirror DTOs
- do not add abstractions "for later"; add only what the current phase needs
- if the documentation leaves a migration choice ambiguous, stop at the smallest safe change and update the docs/swift/backlog rather than improvising
- if several options exist, choose the smallest one aligned with the documented architecture
