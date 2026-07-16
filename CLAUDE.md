# CLAUDE.md

Audience: AI assistants (Claude Code) only. This file is operational — it tells you
_how to work_ in this repository. Human developers start with `docs/swift/README.md`.

---

## Prime directive — extend, do not duplicate

Before writing any spec, RFC, type, or document: check whether it already exists.
This codebase has complete contracts, registered IDs, and active backlogs. The most
common failure mode is producing new material that duplicates or contradicts what is
already specified. Find and extend; do not create.

Do not invent a new architecture, endpoint family, migration direction, or abstraction
unless an RFC is written and the developer confirms. When in doubt, choose the smallest
safe change aligned with the documented architecture.

---

## Before you write anything — reuse and convergence audit

Run this audit before any implementation, spec, or doc change.

**1. GitHub issue lookup first** — `docs/swift/backlog/BACKLOG.md`,
`docs/swift/WORKPLAN.md`, and `docs/swift/PMO-BOARD.md` are frozen (2026-07-16)
and no longer track active work. **GitHub Issues + Milestones
(`swift-golive`, `swift ga`) are the source of truth.** Before starting
anything, check `gh issue list` (by title keyword or milestone) for an
existing issue covering the task — do not create a duplicate.

**2. ID lookup (narrow scope)** — open `docs/swift/data/id-legend.yaml` only
when the task is tied to an RFC or a genuine cross-cutting architecture
decision. Most issues do not need an ID — the GitHub issue itself (title,
label, milestone) is the tracking unit; do not register one just to have one.
If an entry exists: read its `status` — if `done` or `deferred`, ask before
reopening.

**3. Contract lookup** — before adding any field, endpoint, or type, check:

- Execution surface → `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`
- Product/session/admin surface → `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`

If the field exists but is not yet exposed, extend the contract. Do not create a
parallel type outside these files.

**4. RFC lookup** — before writing a new RFC, scan `docs/swift/rfc/`. If an RFC
covers the area, amend it rather than creating a new one.

**5. Convergence check (before close-out)** — does the code match the GitHub
issue's intent, and (if one exists) the RFC/`id-legend.yaml` entry? Fix
divergence before closing. Close the GitHub issue or leave a status comment —
that is the only tracking surface that needs to stay current.

---

## Document workflow — what to write where

Decision tree for every piece of new content:

    Design or API decision?
      → write/amend RFC in docs/swift/rfc/. Stop until developer confirms.
    New feature, endpoint, or component?
      → check for an existing GitHub issue (swift-golive / swift ga milestone).
        Add an id-legend.yaml entry only if an RFC backs it. Stop until developer confirms.
    Code style, typing, or testing rule?
      → docs/CONVENTIONS.md
    Architecture overview or component map?
      → docs/ARCHITECTURE.html (entry point only — point to platform/ and design/)
    Operational guidance for the assistant?
      → this file (CLAUDE.md)

### Task lifecycle (mandatory — steps cannot be skipped or reordered)

**Step 1 — RFC first.** For any design or API decision: write a short RFC in
`docs/swift/rfc/` (or amend existing). State: problem, proposed solution,
alternatives considered, impact on existing contracts. Mechanical fixes (typo,
missing agreed field) are exempt — state why.

**Step 2 — Backlog entry (RFC-backed work only).** If Step 1 produced an RFC,
add/confirm its `id-legend.yaml` entry and, if a domain backlog file is still
actively maintained for that area, link it there. Skip entirely for routine
issue-driven work — the GitHub issue is the entry.

**Step 3 — Developer confirmation.** Present: what will be built, which files
touched, which tests added, which docs updated. **Do not begin until confirmed.**
One sentence of approval is enough.

**Step 3.5 — GitHub issue (execution handoff).** Most work starts from an
existing GitHub issue (`swift-golive` / `swift ga` milestone) — that's the
normal case, use it. If none exists for the task, offer to create one before
implementing. If Step 1 produced an RFC or Step 2 an `id-legend.yaml` entry,
link them in the issue. Do not implement authorless, untracked work.

**Step 4 — Implementation.** Write the code. Coding constraints: `docs/CONVENTIONS.md`.

**Step 5 — Verification.** In the touched project root:

```
make code-quality   # ruff + format (Python) or tsc + prettier (frontend)
make test           # offline unit tests only
```

Fix before proceeding. Do not report done with red tests or lint errors.

**Step 6 — Doc update checklist.**

| What changed                                                      | File to update                                                                           |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| New behaviour, API field, or contract change                      | Update spec table in the relevant design doc                                             |
| Frozen contract touched (`execution.py`, `agent_app.py`, OpenAPI) | Dated entry in `RUNTIME-EXECUTION-CONTRACT.md §8` or `CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| UX component implemented or visual status changed                 | `docs/swift/ux/COMPONENT-UX.md`                                                          |
| RFC-backed item finished                                          | Mark `id-legend.yaml` status `done`, close the GitHub issue                              |
| Code and design doc diverge                                       | Fix the design doc in the same change                                                    |

`docs/swift/backlog/BACKLOG.md`, `WORKPLAN.md`, and `PMO-BOARD.md` are frozen —
never write to them. Do not mark backlog checkboxes or add PMO/WORKPLAN rows.

**Close-out statement (required in every final reply):**

```
## Task close-out
- Code: <one line — what was changed>
- Tests: <pass / n tests added / why none needed>
- Docs updated: <list each file touched, or "none — mechanical fix">
- Tracking: <GitHub issue # closed/updated, or id-legend.yaml entry updated, or "none — not tracked">
- Skipped steps: <list any Step 1–3 steps skipped and why>
```

---

## Task IDs and the registry

Format: `DOMAIN-NN` — a 4-7 letter domain code and a two-digit sequential number.

| Code      | Area                                                      |
| --------- | --------------------------------------------------------- |
| `AUTHZ`   | Authorization model — RBAC→ReBAC migration, OpenFGA schema, authz teardown |
| `CHAT`    | Chat UI — options panel, attachments, sessions, rendering |
| `CTRLP`   | Control plane — APIs, sessions, instances, lifecycle, MCP |
| `EVAL`    | Agent evaluation, scoring, harness                        |
| `FRONT`   | Frontend migration and refactor (excluding chat UI)       |
| `MEMORY`  | Multi-agent conversational memory                         |
| `OBSERV`  | Observability, metrics, Prometheus, KPIs                  |
| `OPS`     | CLI, deployment, environment ops                          |
| `PROMPT`  | Prompt safety, library, context picker, marketplace       |
| `QUALITY` | Quality refactors — typing, file size, test coverage      |
| `RUNTIME` | Execution contracts, SDK, ChatContext, runtime CLI        |
| `VALID`   | End-to-end validation, live-stack scenarios               |

Examples: `MEMORY-01`, `PROMPT-04`, `CHAT-03`. No sub-phase suffixes.
If an item needs a parent relationship, use the `parent:` field in `id-legend.yaml`.

**Scope narrowed (2026-07-16):** an ID is only needed when the work is tied to
an RFC or a genuine cross-cutting architecture decision. Routine issues do not
need one — the GitHub issue (title, label, milestone) is the tracking unit.
Forcing an ID onto every issue is exactly the busywork that made the old
tracking docs unmaintainable; do not recreate it.

Rules (when an ID is warranted):

1. Add the ID to `id-legend.yaml` before implementation starts, with an `issue:`
   ref to the GitHub issue and, if applicable, an `rfc:` ref.
2. The ID appears in the commit subject and the GitHub issue.
3. Keep `id-legend.yaml` status in sync with the GitHub issue's open/closed state.

---

## Operational queries — status and team

For team activity, current focus, and where the real work lives: read
`docs/swift/STATUS.md` first — it is intentionally thin and points to GitHub.
For the actual list of active/open work, query GitHub directly:
`gh issue list --milestone "swift-golive"` (due 2026-07-31) or
`--milestone "swift ga"` (due 2026-09-30). Do not expect `STATUS.md` to mirror
issue content — it won't, by design.

`docs/swift/backlog/BACKLOG.md`, `docs/swift/WORKPLAN.md`, and
`docs/swift/PMO-BOARD.md` are frozen (2026-07-16) — historical record of the
runtime migration only, not live tracking. Do not treat them as current status.

The mandatory read order below applies to **development tasks only**. Skip for status queries.

1. `docs/swift/README.md` — document taxonomy and navigation
2. `docs/swift/platform/DEVELOPER_CONTRACT.md`
3. `docs/swift/platform/PLATFORM_RUNTIME_MAP.md`
4. `docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md`
5. `docs/swift/platform/REBAC.md` — when touching access or team behavior
6. `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` — fred-sdk, fred-runtime, runtime OpenAPI, CLI, tracing/KPI
7. `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` — product/session/admin APIs
8. `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` — mandatory for `apps/frontend/src/rework/`
9. `docs/swift/backlog/FRONTEND-BACKLOG.md` — frontend bootstrap, session, team identity
10. `docs/swift/backlog/CHAT-UI-BACKLOG.md` — ManagedChatPage, chat UI, SSE rendering
11. `docs/swift/ux/COMPONENT-UX.md` — check open UX issues before writing CSS

---

## Git conventions

- One commit per logical change.
- Conventional prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Subject includes the task ID: `feat(RT-2): add checkpoint field to ExecutionGrant`.
- Do not amend published commits. Prefer a new commit over force-push.
- Never skip hooks (`--no-verify`). If a hook fails, fix the root cause.
- Never hand-edit generated files (`openapi.json`, `runtimeOpenApi.ts`,
  `controlPlaneOpenApi.ts`). Regenerate from source and document the command used.

---

## Backend ↔ frontend contract — generated API client (mandatory)

The frontend RTK Query client and all backend-derived TypeScript types are
**generated** from each backend's OpenAPI spec. They are the single source of
truth for request/response shapes. Two hard rules:

1. **Touched a backend controller or Pydantic model? Regenerate the client in the
   same change.** Adding/editing a FastAPI route, request body, or response model
   changes the OpenAPI spec — the generated client is now stale until you run:

   ```
   cd apps/frontend && make update-control-plane-api   # control-plane
   # or: make update-all-apis                          # all backends at once
   ```

   (each target regenerates the backend `openapi.json` via `make generate-openapi`,
   then the hooks via `@rtk-query/codegen-openapi`.) Commit the regenerated
   `controlPlaneOpenApi.ts` alongside the backend change.

2. **Never hand-write a UI type or `fetch()` that duplicates a generated one.**
   Consume the generated hooks (`useXxxQuery` / `useXxxMutation`, re-exported with
   friendly aliases from `controlPlaneApiEnhancements.ts`) and the generated types
   (`PlatformStats`, `ResetLaunchResponse`, …) from `controlPlaneOpenApi.ts`. A
   hand-declared `interface` mirroring a backend model can silently drift from the
   contract — exactly the failure this rule prevents.

   Narrow, justified exception: a raw `fetch` is acceptable only for mechanics the
   generated client cannot express (multipart upload, binary download). Even then,
   import the generated **type** for the response — never re-declare it. See
   `features/migration/launchPlatformImport.ts` (upload) and `exportPlatform.ts`
   (binary) for the sanctioned pattern.

---

## When you are stuck

Stop and ask when:

- A section of the task does not fit any target file cleanly.
- A reference in an existing doc points to a file or concept that no longer exists.
- Two valid approaches exist and the docs do not resolve the tie.
- Scope would expand beyond what was confirmed in Step 3.
- A line budget cannot be met without losing essential content.

Do not silently expand scope. Do not silently delete content.

---

## What lives where — quick map

| Content type                             | Canonical location                                    |
| ---------------------------------------- | ----------------------------------------------------- |
| AI operational rules (Claude Code)       | `CLAUDE.md` (this file)                               |
| OpenAI/Codex agent instructions          | `AGENT.md`, `AGENTS.md`                               |
| Gemini agent instructions                | `GEMINI.md`                                           |
| Team activity, current focus (thin — points to GitHub) | `docs/swift/STATUS.md`                  |
| Active work, milestones (`swift-golive`, `swift ga`)   | GitHub Issues/Milestones (`gh issue list`) |
| RFC-backed feature IDs (narrow scope)     | `docs/swift/data/id-legend.yaml`                      |
| Domain feature backlogs (still live)     | `docs/swift/backlog/` (except `BACKLOG.md`, frozen)   |
| Execution contracts (frozen)             | `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`     |
| Product/session/admin contracts (frozen) | `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| Technical proposals                      | `docs/swift/rfc/`                                     |
| Architecture entry point                 | `docs/ARCHITECTURE.html`                              |
| Platform topology detail                 | `docs/swift/platform/PLATFORM_RUNTIME_MAP.md`         |
| Coding style, typing, testing rules      | `docs/CONVENTIONS.md`                                 |
| Chat UI UX status                        | `docs/swift/ux/COMPONENT-UX.md`                       |
| Track manifests                          | `docs/swift/tracks/`                                  |
| Frozen — historical only, do not write to | `docs/swift/backlog/BACKLOG.md`, `WORKPLAN.md`, `PMO-BOARD.md`, `docs/PMO.md` |
