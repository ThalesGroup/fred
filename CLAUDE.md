# CLAUDE.md

Repository-wide instructions for Claude Code.

---

## Mandatory Read Order

1. [`docs/README.md`](./docs/README.md) — document taxonomy and navigation map; read first to orient
2. [`docs/platform/DEVELOPER_CONTRACT.md`](./docs/platform/DEVELOPER_CONTRACT.md)
3. [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md)
4. [`docs/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md`](./docs/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md)
5. [`docs/platform/REBAC.md`](./docs/platform/REBAC.md) when access/team behavior is touched
6. [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](./docs/design/RUNTIME-EXECUTION-CONTRACT.md) when touching execution contracts, `fred-sdk`, `fred-runtime`, runtime OpenAPI, frontend runtime typing, the CLI, or runtime observability/tracing/KPI/Langfuse metadata
7. [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md) when touching control-plane product/session/admin APIs or frontend migration away from `agentic-backend`
8. [`docs/backlog/BACKLOG.md`](./docs/backlog/BACKLOG.md) for migration phase status and next-step sequencing
9. [`docs/WORKPLAN.md`](./docs/WORKPLAN.md) for current sprint assignments and parallel work — always read before starting any task to avoid duplicating in-progress work
10. [`docs/platform/FRONTEND_CODING_GUIDELINES.md`](./docs/platform/FRONTEND_CODING_GUIDELINES.md) when touching **any** file under `frontend/src/rework/` — mandatory before writing or reviewing CSS/TSX
11. [`docs/backlog/FRONTEND-BACKLOG.md`](./docs/backlog/FRONTEND-BACKLOG.md) when touching frontend bootstrap, session, or team identity
12. [`docs/backlog/CHAT-UI-BACKLOG.md`](./docs/backlog/CHAT-UI-BACKLOG.md) when touching `ManagedChatPage`, chat UI components, or SSE event rendering
13. [`docs/ux/COMPONENT-UX.md`](./docs/ux/COMPONENT-UX.md) when implementing or refining any chat UI component — check open UX issues before writing CSS

---

## Task Lifecycle — Mandatory Protocol

Every non-trivial task follows this sequence without exception. Steps cannot be skipped or reordered.

### Step 1 — RFC first (for any design or API decision)

Before writing a single line of code for a feature, schema change, new endpoint, or component that involves a design choice:

1. Write a short RFC in `docs/rfc/` (or amend an existing one if the area is already covered).
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
| A UX component is implemented or its visual/interaction status changes | Update `docs/ux/COMPONENT-UX.md` |
| A phase progress row exists for the area | Update the progress table at the bottom of the relevant backlog file |
| A WORKPLAN sprint item is finished | Mark it done in `docs/WORKPLAN.md` |
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

Canonical source: [`docs/platform/PLATFORM_RUNTIME_MAP.md`](./docs/platform/PLATFORM_RUNTIME_MAP.md)

This defines:

- `fred-runtime` (execution surface, target), Knowledge Flow API, Control Plane API responsibilities.
- `agentic-backend` is being migrated out — do not add execution logic there.
- Knowledge Flow / Agentic / Control Plane Temporal worker responsibilities.

---

## Active Migration

Fred is mid-migration from `agentic-backend` to `fred-runtime` + `control-plane-backend`.

- New execution code → `fred-runtime` / `fred-sdk`
- New product/session/admin code → `control-plane-backend`
- Migration plan: [`docs/backlog/BACKLOG.md`](./docs/backlog/BACKLOG.md) (Phases 0–6)
- Phase 1 execution contracts frozen: [`docs/design/RUNTIME-EXECUTION-CONTRACT.md`](./docs/design/RUNTIME-EXECUTION-CONTRACT.md)
- Phase 3a product boundary: [`docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`](./docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md)

---

## Continuation Rules

When continuing the migration:

- treat `docs/design/RUNTIME-EXECUTION-CONTRACT.md` as the execution contract source of truth
- treat `docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` as the product/session/admin source of truth for Phase 3a
- treat `docs/backlog/BACKLOG.md` as the sequencing and status source of truth
- prefer editing contract source files over adding compatibility layers
- if a needed type is missing, fix `fred-sdk` or the FastAPI schema first and regenerate instead of adding local mirror DTOs
- do not recreate `agentic-backend` behavior inside `fred-runtime`
- do not add abstractions "for later"; add only what the current phase needs
- if the documentation leaves a migration choice ambiguous, stop at the smallest safe change and update the docs/backlog rather than improvising
- if several options exist, choose the smallest one aligned with the documented architecture
