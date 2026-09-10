# CLAUDE.md

Audience: AI assistants (Claude Code) only. This file is operational — it tells you
_how to work_ in this repository. Human developers start with `docs/swift/README.md`.

---

## Prime directive — extend, do not duplicate

Before writing any spec, RFC, type, or document: check whether it already exists.
This codebase has complete contracts and active backlogs. The most common failure
mode is producing new material that duplicates or contradicts what is already
specified. Find and extend; do not create.

Do not invent a new architecture, endpoint family, migration direction, or abstraction
unless an RFC is written and the developer confirms. When in doubt, choose the smallest
safe change aligned with the documented architecture.

---

## Current phase — consolidation (in effect until further notice)

Production is now stable on the Alembic front: every table's migration head is
controlled and up to date. That closes the stabilization push this repo has
been in — the team is now prioritizing **regaining control of the codebase**
over shipping breadth: smaller, single-purpose issues and PRs, more deletion
than addition, and trimming RFCs and docs that grew past what they need to
say. This is the standing default, not a sprint with an end date — keep
applying it until a developer says otherwise.

1. **Bias toward deletion.** When a task offers a real choice between adding
   new code/abstraction and simplifying or deleting existing code to reach
   the same outcome, take the deletion path, even if it costs a bit more
   effort than an additive patch. This sharpens the Prime Directive above —
   it is not a new, separate rule.
2. **Proactive RFC pruning.** Step 3 of the reuse audit below already says to
   check whether an RFC's content is settled before amending it. Do that
   check every time you read an RFC, not only when a task happens to close
   it out — if its open questions are closed, say so and offer to trim or
   archive it on the spot per "RFC vs. OpenSpec vs. doc" below, instead of leaving it to
   accrete until someone happens to touch it.
3. **Doc pruning candidates.** An intermediate or status doc is a deletion
   candidate when: the migration/step it describes is complete and
   superseded by a compact doc, its content duplicates something already
   current elsewhere, or it exists only to record a status GitHub now
   tracks. It is *not* a candidate when it is an intentionally frozen
   historical record (`BACKLOG.md`, `WORKPLAN.md`) — those stay frozen, not
   deleted, unless the developer says otherwise.
4. **Scope discipline.** Do not bundle a cleanup/deletion with an unrelated
   feature or fix in the same issue or PR. A reduction change stays its own
   commit and, where practical, its own PR — mixing the two makes the
   reduction hard to review and easy to revert by accident.
5. **Tracking.** Link consolidation work to whatever milestone is currently
   active for general development (check `gh issue list --milestone <name>`
   or ask the developer) — do not hardcode a milestone name here, it will go
   stale the moment that milestone closes.

---

## Before you write anything — reuse and convergence audit

Run this audit before any implementation, spec, or doc change.

**1. GitHub issue lookup first** — `docs/swift/backlog/BACKLOG.md` and
`docs/swift/WORKPLAN.md` are frozen (2026-07-16) and no longer track active
work. `docs/swift/PMO-BOARD.md` and `docs/swift/data/sprint.yaml` were removed
(2026-07-21) — they duplicated GitHub without ever being kept current. **GitHub
Issues + Milestones are the single source of
truth for sprints, issues, and milestones** (run `gh api "repos/:owner/:repo/milestones?state=open"`
to see which ones are current — do not hardcode milestone names in this file,
they close and get replaced). Before starting anything, check
`gh issue list` (by title keyword or milestone) for an existing issue covering
the task — do not create a duplicate. For status/planning questions, query
GitHub directly (`gh issue list`, `gh issue view`) rather than looking for a
tracking doc to read.

**2. Contract lookup** — before adding any field, endpoint, or type, check:

- Execution surface → `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`
- Product/session/admin surface → `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`

If the field exists but is not yet exposed, extend the contract. Do not create a
parallel type outside these files.

**3. RFC lookup** — before writing a new RFC, scan `docs/swift/rfc/`. If an RFC
covers the area, check whether the area is actually still open. **RFCs are
scoped to open design questions, and to agreed work still too broad or
uncertain to scope into one OpenSpec change, only** (2026-08-01 —
see "RFC vs. OpenSpec vs. doc" below); if the RFC's content is already settled and shipped,
amending it is the wrong move — fold that part into the relevant compact doc
instead. **RFCs are proposals, not verified truth** — each records intent at
the time it was written (or amended) and its own `**Status:**` line, but a
`Status: ...pending sign-off` amendment can sit for weeks looking authoritative
while being subtly wrong (an RFC read as "decided" is not the same as
"validated" — this has bitten this repo at least once). Cross-check an RFC's
design against the actual code and the frozen contract docs before treating it
as current; if they diverge, the code and contract docs win — flag the
divergence rather than implementing what the RFC says over what's actually
decided. During the consolidation phase above (and afterward — that rule is
permanent), do this check on every RFC you read, not only the one you're
closing out.

**4. OpenSpec lookup** — before scoping new buildable work, check
`openspec/changes/` (in-flight slices) and `openspec/specs/` (`openspec list`,
`openspec view`) for an existing change or capability spec covering the area.
Extend an in-flight change rather than starting a second one for the same
capability. An OpenSpec change is a scoped slice of already-agreed work — for
a design question that's still genuinely open, an RFC still comes first (see
"RFC vs. OpenSpec vs. doc" below).

**5. Convergence check (before close-out)** — does the code match the GitHub
issue's intent, and (if one exists) the RFC's or OpenSpec change's? Fix
divergence before closing. Close the GitHub issue or leave a status comment —
that is the only tracking surface that needs to stay current.

---

## Document workflow — what to write where

### RFC vs. OpenSpec vs. doc (2026-08-01, extended 2026-09-10)

Four homes, not three, each answering a different question:

- **RFC** (`docs/swift/rfc/`) — a design question still genuinely open, or
  work too broad to build in one pass. Stays prose; its `Status:` line
  shrinks as buildable pieces leave it.
- **OpenSpec change** (`openspec/changes/<name>/`) — one buildable, testable
  slice of already-agreed work: `proposal.md` (why / what / impact),
  `design.md` (rationale, deferred gaps), `tasks.md` (checklist), a delta
  `specs/<capability>/spec.md` (SHALL/MUST requirements + Given/When/Then
  scenarios) — the four artifacts the configured `spec-driven` schema
  (`openspec schemas`) actually generates. A `verification.md` (exact test
  evidence — what's proven, what isn't) is a useful per-change addition some
  contributors include, not a schema-mandated artifact — don't assume every
  change has one. Links a GitHub issue; never duplicates its tracking.
- **OpenSpec spec** (`openspec/specs/<capability>/spec.md`) — the compact,
  current truth for one capability. Written automatically when a change is
  archived (`openspec archive`) — the CLI folds the delta in and moves the
  change to `changes/archive/`.
- **Compact doc** (`docs/swift/design/`, `docs/swift/platform/`, component
  docs) — the compact, current truth for anything crossing more than one
  capability (a runtime contract, a product API, a platform convention).

RFCs are not a permanent home for finished decisions — they exist only for
**(a) a design question that is still genuinely open**, or **(b) agreed work
still too broad or too uncertain to scope into a single OpenSpec change**.
The moment a decision is settled and scoped — buildable as one slice, or
already implemented — its durable "what/why" belongs in an **OpenSpec
change** or a **compact doc** (crosses capabilities), never in another dated
RFC amendment.

Why: an RFC that keeps accreting amendment blocks reads as more authoritative
than it is. `Status: draft pending sign-off` looks the same on the page as
`Status: team-approved` to a quick read, so both a developer and an assistant
can mistake "written into the RFC" for "decided and validated" — including
amendments that turned out, on later inspection, not to have been especially
good ideas. OpenSpec changes and compact docs don't carry that ambiguity: a
change's `tasks.md` is binary about what's done vs. not, and if it's in a
compact doc, it shipped and it's current.

**Moving weight toward OpenSpec (2026-09-10).** New scoped work with testable
acceptance criteria — a bug fix, a bounded feature, a capability extension —
defaults to an OpenSpec change (`openspec-propose` / `opsx:propose`) instead
of a new RFC. Reserve a new RFC for what's genuinely undecided: real
alternatives still on the table, no buildable slice yet. Standing RFCs don't
get rewritten wholesale — they get thinner: each buildable piece leaves as an
OpenSpec change, and the RFC's `Status:` line only ever names what's left
(`docs/swift/FRED-FRONTEND-PACKAGING-RFC.md` is already being worked down this
way). Once nothing's left, fold and archive it per Step 6. Where an OpenSpec
capability spec has fully grown into what a compact-doc section used to say,
stop maintaining both — point the compact doc at the OpenSpec spec instead of
restating it.

In practice: when Step 6 below says a design doc needs updating, write there
first (or in the relevant OpenSpec change, if the work is a scoped slice).
Reach for `docs/swift/rfc/` only for the part that is still an open question,
or still too broad/uncertain to scope into one OpenSpec change — never to
re-document something already decided. An
existing RFC whose open questions have all closed should be trimmed back to
nothing (or archived) once its content has been folded into an OpenSpec spec
or compact doc, not left growing.

Decision tree for every piece of new content:

    Design or API decision still open, or agreed work too broad/uncertain
    to scope into one OpenSpec change?
      → write/amend an RFC in docs/swift/rfc/, scoped to the open part only.
        Stop until developer confirms.
    Agreed work, scoped to one buildable, testable slice?
      → openspec-propose a change in openspec/changes/, linking the GitHub
        issue. Stop until developer confirms.
    Design or API decision that is already settled or shipped, crossing more
    than one capability?
      → write/update the compact doc directly (design/contract doc, or the
        relevant component doc). No RFC or OpenSpec change needed — note why
        in the close-out.
    New feature, endpoint, or component?
      → check for an existing GitHub issue (see `gh api "repos/:owner/:repo/milestones?state=open"`).
        Stop until developer confirms.
    Code style, typing, or testing rule?
      → docs/CONVENTIONS.md
    Architecture overview or component map?
      → docs/ARCHITECTURE.html (entry point only — point to platform/ and design/)
    Operational guidance for the assistant?
      → this file (CLAUDE.md)

### Human-facing rendering (2026-09-10)

MD stays the only source of truth, always. Default to GitHub's native
rendering to read and confirm any single document — an RFC, an OpenSpec
`proposal.md`, a PR diff. Step 3 sign-off and PR review already happen there;
add no rendering pipeline for this. Generate an ad hoc HTML view (a Claude
Artifact, or a self-contained file written to a temp dir and opened locally
for any other agent) only for genuine cross-cutting synthesis a single file
can't give — a status rollup across several RFCs/changes, a mechanism
diagram. Never commit it, never re-open and edit it, never treat it as a
second source of truth: regenerate on demand from the current MD and
discard. (Deliberately out of scope: `fred-website`/Hugo — it's the public
project site, not an internal rendering pipeline.)

### Task lifecycle (mandatory — steps cannot be skipped or reordered)

**Step 1 — RFC first, only while the design is still open; OpenSpec for
agreed, scoped work.** For a design or API decision that is genuinely
undecided (real alternatives still being weighed), or agreed work still too
broad or too uncertain to scope into one buildable slice: write a short RFC
in `docs/swift/rfc/` (or amend existing), scoped to that open part. State:
problem, proposed solution, alternatives considered, impact on existing
contracts. If the work is already agreed and scoped to one buildable,
testable slice: skip the RFC and open an OpenSpec change instead
(`openspec-propose`) — proposal, design, tasks, delta spec (plus
`verification.md` if the change adds one; it's not schema-mandated). If the
design is already settled/shipped — or is a mechanical fix (typo, missing
agreed field) — skip both and write/update the compact doc directly; state
why in the close-out.

**Step 2 — Backlog link (RFC-backed work only).** If Step 1 produced an RFC and
a domain backlog file is still actively maintained for that area, link the RFC
there. Skip entirely for routine issue-driven work — the GitHub issue is the
entry.

**Step 3 — Developer confirmation.** Present: what will be built, which files
touched, which tests added, which docs updated. **Do not begin until confirmed.**
One sentence of approval is enough.

**Step 3.5 — GitHub issue (execution handoff).** Most work starts from an
existing GitHub issue (check `gh api "repos/:owner/:repo/milestones?state=open"` for the
current milestone) — that's the
normal case, use it. If none exists for the task, offer to create one before
implementing. If Step 1 produced an RFC, link it in the issue. Do not
implement authorless, untracked work.

**Step 4 — Implementation.** Write the code. Coding constraints: `docs/CONVENTIONS.md`.

**Keep code comments to 2-3 lines.** Say the "why" the code cannot show, then
stop. A comment that re-narrates the decision, lists the alternatives, or
restates what the next line does is noise the next reader has to skim past -
and it goes stale faster than the code. When the reasoning genuinely needs
more room, write it in the relevant compact doc and point at it from the code
("Full rationale: COMPONENT-UX.md"). This applies to file headers too: a few
lines on what the module is for, not an essay.

**No issue numbers in code.** Not in comments, not in `describe()` names, not
in stylesheets. `(#1234)` pins a line to a one-off decision that made sense the
week it was taken and means nothing a year later, and it invites the paragraph
of history that comes with it. Say what the code does and why it has to; the
issue, the PR and the commit message are where the trail lives. Existing
occurrences are not worth a cleanup pass of their own, but drop them from any
line you are already rewriting.

**Step 5 — Verification.** In the touched project root:

```
make code-quality   # ruff + format (Python) or tsc + prettier (frontend)
make test           # offline unit tests only
```

Fix before proceeding. Do not report done with red tests or lint errors.
Performance carries the same weight as these checks, not a lesser one — see
`docs/CONVENTIONS.md §Performance & concurrency`. If the change touches the
agent execution loop, an LLM or tool call site, KPI/log emission, a shared
client/cache, or anything else that runs per-turn or per-request under
concurrent load, also run the `fred-performance-reviewer` skill before
reporting done.

**Self-review is not enough for non-trivial logic changes.** Before reporting
done, run `/code-review` on your own diff — default effort at minimum, higher
for anything touching correctness-sensitive shared code. Tests you write from
the same reasoning pass that wrote the code confirm your own assumptions
instead of falsifying them; an agent checking its own work shares whatever
blind spot produced the bug in the first place. (2026-08-13: a same-day
ReAct size-budget fix — issue #2350, PR #2352 — passed its own tests,
`make code-quality`, and a `fred-performance-reviewer` pass, then shipped
with three P1 correctness bugs that an independent reviewer bot caught on
first read of the cold diff — each one a case not covered by the tests
written alongside the code they were breaking.) Do not skip this under time
pressure — that is exactly when a design's blind spots survive to
production instead of being caught same-session.

**Step 6 — Doc update checklist.**

| What changed                                                      | File to update                                                                           |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| New behaviour, API field, or contract change                      | Update spec table in the relevant design doc                                             |
| Frozen contract touched (`execution.py`, `agent_app.py`, OpenAPI) | Dated entry in `RUNTIME-EXECUTION-CONTRACT.md §8` or `CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| UX component implemented or visual status changed                 | `docs/swift/ux/COMPONENT-UX.md`                                                          |
| RFC-backed item finished, no open questions left                 | Fold the durable what/why into the relevant compact doc, trim the RFC to whatever (if anything) is still open, close the GitHub issue |
| OpenSpec change complete, no open tasks left                      | `openspec archive` it — folds the delta into `openspec/specs/<capability>/spec.md`; also update the relevant compact doc only if the change crosses more than one capability; close the GitHub issue |
| Code and design doc diverge                                       | Fix the design doc in the same change                                                    |
| Capability authoring surface changed (SDK types, hooks, lanes)    | Update `docs/swift/capabilities/AUTHORING.md` + the `add-fred-capability` Skill          |
| Hot-path code touched (LLM/tool call site, KPI/log emission, per-turn agent loop, shared client/cache) | Run the `fred-performance-reviewer` skill; if a new metric/label was added, confirm it's Grafana-visible per `OBSERVABILITY-AND-AUDIT.md` |

`docs/swift/backlog/BACKLOG.md` and `WORKPLAN.md` are frozen — never write to
them. Do not mark backlog checkboxes or add WORKPLAN rows. `PMO-BOARD.md` and
`sprint.yaml` no longer exist — never recreate them; track status on the
GitHub issue instead.

**Close-out statement (required in every final reply):**

```
## Task close-out
- Code: <one line — what was changed>
- Tests: <pass / n tests added / why none needed>
- Docs updated: <list each file touched, or "none — mechanical fix">
- Tracking: <GitHub issue # closed/updated, or "none — not tracked">
- Skipped steps: <list any Step 1–3 steps skipped and why>
```

---

## Task ID convention (informal — no registry)

`docs/swift/data/id-legend.yaml` was removed (2026-07-27): a 2600+ line
central registry that assistants spent significant time reading and that
created a second, easily stale source of truth alongside GitHub — its
`status: done`/`deferred` fields were repeatedly mistaken for a decided
architecture rather than the RFC snapshot they actually reflected. GitHub
Issues/Milestones are the only tracking surface now; see "Operational
queries" above.

The `DOMAIN-NN` shorthand (e.g. `MEMORY-01`, `CAPAB-02`, `MIGR-05`) can still
be useful as an informal label in a commit subject or GitHub issue title when
work is tied to an RFC or a genuine cross-cutting architecture decision —
purely mnemonic, not a registered ID. There is nothing to add it to and
nothing to keep in sync: the GitHub issue is the tracking unit, and an RFC's
own `**Status:**` line (if any) tracks the design.

---

## Operational queries — status and team

For team activity, current focus, and the actual list of active/open work,
query GitHub directly:
`gh api "repos/:owner/:repo/milestones?state=open"` for the current milestones, then
`gh issue list --milestone "<name>"`. Do not create or maintain a status/PMO
mirror in the repository.

`docs/swift/backlog/BACKLOG.md` and `docs/swift/WORKPLAN.md` are frozen
(2026-07-16) — historical record of the runtime migration only, not live
tracking. Do not treat them as current status. `docs/swift/PMO-BOARD.md` and
`docs/swift/data/sprint.yaml` were removed (2026-07-21): they mirrored GitHub
without ever being kept current. Sprints, issues, and milestones live on
GitHub only — query it directly, do not look for a doc mirror.

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

## Alembic migrations - keep history linear

One head per backend, always. When a feature branch's new migration has
fallen behind the base branch (`swift`) because migrations kept landing
there, **re-parent it**: point its `down_revision` (and the `Revises:`
docstring line) at the current base head, delete any merge revision the
branch may have accumulated, and verify with `alembic heads` (exactly one
head) plus a real `alembic upgrade head` before pushing. Do **not** create
an Alembic merge revision (`alembic merge`) to reconcile heads inside a PR -
a merge revision is a last resort, acceptable only when both divergent
migrations are already deployed somewhere and can no longer be re-parented.
(2026-08-24, PROMPT-06: the marketplace migration was re-parented onto the
swift head and its empty merge revision deleted - the PR then added a single
linear migration.)

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
| Active work, milestones (check `gh api "repos/:owner/:repo/milestones?state=open"`) | GitHub Issues/Milestones (`gh issue list`) |
| Domain feature backlogs (still live)     | `docs/swift/backlog/` (except `BACKLOG.md`, frozen)   |
| Execution contracts (frozen)             | `docs/swift/design/RUNTIME-EXECUTION-CONTRACT.md`     |
| Product/session/admin contracts (frozen) | `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` |
| Technical proposals — open questions, or work too broad for one OpenSpec change, only (settled/scoped decisions move to OpenSpec or design docs, 2026-08-01) | `docs/swift/rfc/` |
| Scoped, buildable slices of agreed work (in-flight) | `openspec/changes/<name>/` |
| Per-capability current spec (folded in on archive) | `openspec/specs/<capability>/spec.md` |
| Architecture entry point                 | `docs/ARCHITECTURE.html`                              |
| Platform topology detail                 | `docs/swift/platform/PLATFORM_RUNTIME_MAP.md`         |
| Coding style, typing, testing rules      | `docs/CONVENTIONS.md`                                 |
| Chat UI UX status                        | `docs/swift/ux/COMPONENT-UX.md`                       |
| Track manifests                          | `docs/swift/tracks/`                                  |
| Frozen — historical only, do not write to | `docs/swift/backlog/BACKLOG.md`, `WORKPLAN.md` |
| Sprints, issues, milestones (only source of truth) | GitHub Issues/Milestones (`gh issue list`) — `STATUS.md`, `docs/PMO.md`, `PMO-BOARD.md`, `sprint.yaml`, and `id-legend.yaml` were removed; never recreate them |
