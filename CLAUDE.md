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

**1. ID lookup** — open `docs/swift/data/id-legend.yaml`. Find the feature or track.
If an entry exists: read its `backlog_ref` (source of truth for scope and status);
check its `status` — if `done` or `deferred`, ask before reopening. Use its ID in
every commit message, backlog checkbox, and STATUS.md row you touch. If no entry
exists → create one before implementation starts (see §Task IDs).

**2. Backlog lookup** — open the relevant backlog (`BACKLOG.md`,
`CHAT-UI-BACKLOG.md`, `FRONTEND-BACKLOG.md`, `MULTI-AGENT-MEMORY-BACKLOG.md`).
If a `[ ]` item already covers the task, link to it — do not create a duplicate.

**3. Contract lookup** — before adding any field, endpoint, or type, check:

- Execution surface → `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`
- Product/session/admin surface → `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`

If the field exists but is not yet exposed, extend the contract. Do not create a
parallel type outside these files.

**4. RFC lookup** — before writing a new RFC, scan `docs/swift/rfc/`. If an RFC
covers the area, amend it rather than creating a new one.

**5. Convergence check (before close-out)** — do the code, backlog checkbox,
STATUS.md, and id-legend.yaml all agree on status? Fix divergence before closing.

---

## Document workflow — what to write where

Decision tree for every piece of new content:

    Design or API decision?
      → write/amend RFC in docs/swift/rfc/. Stop until developer confirms.
    New feature, endpoint, or component?
      → add backlog entry + id-legend.yaml entry. Stop until developer confirms.
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

**Step 2 — Backlog entry.** Find the relevant backlog file. Add or confirm a `[ ]`
item. If no backlog covers the area, ask the developer before proceeding.

**Step 3 — Developer confirmation.** Present: what will be built, which files
touched, which tests added, which docs updated. **Do not begin until confirmed.**
One sentence of approval is enough.

**Step 3.5 — GitHub issue (execution handoff).** After confirmation and before
implementation, a GitHub issue must exist that links the task ID, RFC, and
backlog entry. This is the team's execution handoff — it is how the developer
picks up the work and how the code assistant knows the task is authorised.
If no issue exists, offer to create one. Do not implement without it unless the
developer explicitly waives this step. The issue does not replace the RFC or
backlog entry — it references them.

**Step 3.6 — PMO sync (mandatory when PMO-visible tracking changes).**
`docs/swift/PMO-BOARD.md` is the PMO-facing mirror of active and upcoming
tracked work. Update the matching PMO board row in the same change whenever a
tracked item's owner, status, backlog ref, RFC ref, blocker, or execution ref
changes in any source document. Typical trigger files include
`docs/swift/backlog/`, `docs/swift/rfc/`, `docs/swift/STATUS.md`,
`docs/swift/data/id-legend.yaml`, `docs/swift/data/sprint.yaml`, and
`docs/swift/tracks/`. Keep PMO fields aligned with the source documents.
Execution ref priority: GitHub issue → PR → working branch → `TBD`. When an
execution ref is known, mirror it directly under the relevant backlog item as
`Execution: ...`.

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
| Backlog `[ ]` item done                                           | Mark `[x]` in backlog file                                                               |
| New behaviour, API field, or contract change                      | Update spec table in the relevant design doc                                             |
| Frozen contract touched (`execution.py`, `agent_app.py`, OpenAPI) | Dated entry in `RUNTIME-EXECUTION-CONTRACT.md §8` or `CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| UX component implemented or visual status changed                 | `docs/swift/ux/COMPONENT-UX.md`                                                          |
| Phase progress row exists                                         | Update progress table at bottom of backlog file                                          |
| WORKPLAN sprint item finished                                     | Mark done in `docs/swift/WORKPLAN.md`                                                    |
| PMO-visible tracking field changed (owner, status, blocker, refs, execution) | Update `docs/swift/PMO-BOARD.md` in the same change                         |
| GitHub issue / PR / branch known for a backlog item               | Record it under the backlog item as `Execution: ...` and in `docs/swift/PMO-BOARD.md`   |
| Code and design doc diverge                                       | Fix the design doc in the same change                                                    |

**Close-out statement (required in every final reply):**

```
## Task close-out
- Code: <one line — what was changed>
- Tests: <pass / n tests added / why none needed>
- Docs updated: <list each file touched, or "none — mechanical fix">
- Backlog: <item marked done, or "none — not tracked yet">
- Skipped steps: <list any Step 1–3 steps skipped and why>
```

---

## Task IDs and the registry

Format: `DOMAIN-NN` — a 4-7 letter domain code and a two-digit sequential number.

| Code      | Area                                                      |
| --------- | --------------------------------------------------------- |
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

Rules:

1. Every new item gets an ID before implementation starts.
2. The ID appears in: backlog checkbox, STATUS.md, sprint.yaml, commit subject.
3. Add the ID to `id-legend.yaml` immediately — not after the work is done.
4. `id-legend.yaml` and `sprint.yaml` status must stay in sync with backlog checkboxes.

---

## Operational queries — status and team

For team activity, sprint status, feature progress, or test coverage: read
`docs/swift/STATUS.md`. It answers who owns what, what was delivered, what is
blocked, and which tests cover which feature. Follow its `Backlog ref` links for
deeper specs. For structured ID queries, read `docs/swift/data/id-legend.yaml`
and `docs/swift/data/sprint.yaml` directly — faster than scanning prose.

The mandatory read order below applies to **development tasks only**. Skip for status queries.

1. `docs/swift/README.md` — document taxonomy and navigation
2. `docs/swift/platform/DEVELOPER_CONTRACT.md`
3. `docs/swift/platform/PLATFORM_RUNTIME_MAP.md`
4. `docs/swift/platform/CONFIGURATION_AND_POLICY_CONVENTIONS.md`
5. `docs/swift/platform/REBAC.md` — when touching access or team behavior
6. `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` — fred-sdk, fred-runtime, runtime OpenAPI, CLI, tracing/KPI
7. `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` — product/session/admin APIs
8. `docs/swift/backlog/BACKLOG.md` — migration phase status and sequencing
9. `docs/swift/WORKPLAN.md` — sprint assignments; read before starting any task
10. `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` — mandatory for `apps/frontend/src/rework/`
11. `docs/swift/backlog/FRONTEND-BACKLOG.md` — frontend bootstrap, session, team identity
12. `docs/swift/backlog/CHAT-UI-BACKLOG.md` — ManagedChatPage, chat UI, SSE rendering
13. `docs/swift/ux/COMPONENT-UX.md` — check open UX issues before writing CSS

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
| Team activity, sprint status, blockers   | `docs/swift/STATUS.md`                                |
| Feature IDs and registry                 | `docs/swift/data/id-legend.yaml`                      |
| Sprint-level structured data             | `docs/swift/data/sprint.yaml`                         |
| Feature backlogs                         | `docs/swift/backlog/`                                 |
| Execution contracts (frozen)             | `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`     |
| Product/session/admin contracts (frozen) | `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| Technical proposals                      | `docs/swift/rfc/`                                     |
| Architecture entry point                 | `docs/ARCHITECTURE.html`                              |
| Platform topology detail                 | `docs/swift/platform/PLATFORM_RUNTIME_MAP.md`         |
| Coding style, typing, testing rules      | `docs/CONVENTIONS.md`                                 |
| Chat UI UX status                        | `docs/swift/ux/COMPONENT-UX.md`                       |
| Sprint assignments                       | `docs/swift/WORKPLAN.md`                              |
| Track manifests                          | `docs/swift/tracks/`                                  |
| PMO delivery board                       | `docs/swift/PMO-BOARD.md`                             |
| Coordination guide (Claire, Arnaud)      | `docs/PMO.md`                                         |
