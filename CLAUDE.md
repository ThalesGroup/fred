# CLAUDE.md

Audience: AI assistants (Claude Code) only. This file is operational — it tells you
*how to work* in this repository. Human developers start with `docs/swift/README.md`.

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
      → docs/ARCHITECTURE.md (entry point only — point to platform/ and design/)
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

**Step 4 — Implementation.** Write the code. Coding constraints: `docs/CONVENTIONS.md`.

**Step 5 — Verification.** In the touched project root:

```
make code-quality   # ruff + format (Python) or tsc + prettier (frontend)
make test           # offline unit tests only
```

Fix before proceeding. Do not report done with red tests or lint errors.

**Step 6 — Doc update checklist.**

| What changed | File to update |
|---|---|
| Backlog `[ ]` item done | Mark `[x]` in backlog file |
| New behaviour, API field, or contract change | Update spec table in the relevant design doc |
| Frozen contract touched (`execution.py`, `agent_app.py`, OpenAPI) | Dated entry in `RUNTIME-EXECUTION-CONTRACT.md §8` or `CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| UX component implemented or visual status changed | `docs/swift/ux/COMPONENT-UX.md` |
| Phase progress row exists | Update progress table at bottom of backlog file |
| WORKPLAN sprint item finished | Mark done in `docs/swift/WORKPLAN.md` |
| Code and design doc diverge | Fix the design doc in the same change |

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

| Code | Area |
|---|---|
| `CHAT` | Chat UI — options panel, attachments, sessions, rendering |
| `CTRLP` | Control plane — APIs, sessions, instances, lifecycle, MCP |
| `EVAL` | Agent evaluation, scoring, harness |
| `FRONT` | Frontend migration and refactor (excluding chat UI) |
| `MEMORY` | Multi-agent conversational memory |
| `OBSERV` | Observability, metrics, Prometheus, KPIs |
| `OPS` | CLI, deployment, environment ops |
| `PROMPT` | Prompt safety, library, context picker, marketplace |
| `QUALITY` | Quality refactors — typing, file size, test coverage |
| `RUNTIME` | Execution contracts, SDK, ChatContext, runtime CLI |
| `VALID` | End-to-end validation, live-stack scenarios |

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
10. `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` — mandatory for `frontend/src/rework/`
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

| Content type | Canonical location |
|---|---|
| AI operational rules | `CLAUDE.md` (this file) |
| Team activity, sprint status, blockers | `docs/swift/STATUS.md` |
| Feature IDs and registry | `docs/swift/data/id-legend.yaml` |
| Sprint-level structured data | `docs/swift/data/sprint.yaml` |
| Feature backlogs | `docs/swift/backlog/` |
| Execution contracts (frozen) | `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md` |
| Product/session/admin contracts (frozen) | `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| Technical proposals | `docs/swift/rfc/` |
| Architecture entry point | `docs/ARCHITECTURE.md` |
| Platform topology detail | `docs/swift/platform/PLATFORM_RUNTIME_MAP.md` |
| Coding style, typing, testing rules | `docs/CONVENTIONS.md` |
| Chat UI UX status | `docs/swift/ux/COMPONENT-UX.md` |
| Sprint assignments | `docs/swift/WORKPLAN.md` |
| Track manifests | `docs/swift/tracks/` |
| Coordination guide (Claire, Arnaud) | `docs/PMO.md` |
