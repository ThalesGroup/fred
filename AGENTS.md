# Team / AI Assistant Instructions

`AGENTS.md` is the primary team workflow and governance entrypoint for coding
agents. The team is moving away from Claude/Anthropic tooling; the workflow
must remain usable through ordinary repository files and command-line tools.

Before changing code or documentation, read:

1. This root `AGENTS.md`.
2. Root `CLAUDE.md`, which temporarily retains detailed engineering guidance.
3. Any nested `AGENTS.override.md`, `AGENTS.md`, or legacy `CLAUDE.md` in the
   target directory.

The guidance in `CLAUDE.md` remains applicable where it does not conflict with
this file. Migrate remaining guidance as it is maintained and keep one
authoritative copy of each rule.

Conflict resolution order:

1. Explicit user instruction.
2. Closest nested `AGENTS.override.md` or `AGENTS.md`.
3. Root `AGENTS.md`.
4. Closest legacy `CLAUDE.md`, then root `CLAUDE.md`.
5. Root `AGENT.md`, if present (orientation only).

If a conflict cannot be resolved using this order, ask before changing files.

## Scope and acceptance

Use the GitHub issue to record the intended outcome and acceptance criteria.
For localized fixes and maintenance, state the intended change and verification
briefly and proceed within the agreed scope. Use an RFC for unresolved design
questions or work that still needs to be split into buildable pieces. Update the
relevant design, platform or component docs when shipped behavior changes.

## Database table reuse

Before adding a table, check whether an existing table can naturally hold the
data. Prefer extending it when that keeps the model clear and avoids unnecessary
tables. Add a separate table when distinct meaning, lifecycle, access rules or
compatibility makes it clearer or safer; briefly explain that choice in the
existing change design or PR.

## Scale and multi-pod operation

For every change, assess behavior at the platform's target scale: hundreds of
concurrent users, thousands of registered users, hundreds of teams, and tens of
thousands of documents. Design affected runtime paths for these volumes. Check
bounded work and memory use, query and index costs, pagination, contention, and
reuse of configured client and database connection pools. Validate material
scaling risks with focused load or concurrency tests; a single-user test is not
sufficient evidence for a shared hot path.

Assume every backend can run with multiple pod replicas, including during
rollouts and retries. State needed across requests or instances must use shared
storage or an existing distributed coordination mechanism, with clear ownership,
idempotency, expiration, and failure recovery. Do not rely on process-local
queues, locks, caches, or sticky routing for correctness. For changes involving
long-running work, streaming, HITL, callbacks, or background jobs, verify that
successive requests can land on different pods.

## Commit and verification rhythm

Commit completed, reviewable blocks as work progresses instead of accumulating
all changes in one final commit. Each commit should have one clear purpose and
exclude unrelated local changes.

Group tests and broad quality checks near the end of a PR or after a substantial
set of related files has changed. During implementation, run only the narrow
check needed to resolve a concrete risk. Honor a developer's request for manual
feature validation before running tests.

## Author review before readiness

Before declaring implementation ready or requesting final PR review, apply
[the branch review procedure](.agents/skills/audit-branch/SKILL.md) to the full
change against its actual target branch, including affected consumers and docs.
Passing lint, compilation and tests does not replace this review. Scale depth
to risk; localized documentation/mechanical changes need only relevant checks.

For non-trivial logic or public-contract changes, obtain an independent,
read-only review using a separate agent or reviewer with fresh context when
available. This rule authorizes that bounded delegation for repository work;
provide requirements and the diff, not expected findings. Record the reviewed
base/head, coverage, findings and dispositions, verification, and exclusions in
the existing PR or task response. If independent review is unavailable, state
that limitation. Do not present a focused patch review as a full PR review.

## Branch and draft PR workflow

For implementation work, identify or create the tracking GitHub issue and use
a dedicated topic branch. Reuse the current branch when the user identifies it
as the branch for this work. Keep unrelated local changes out of commits.
Before creating an issue, search open GitHub Epics for a relevant parent. Link
the issue to a matching Epic. Reference that Epic in the PR when useful. If none
matches, tell the developer and present the choices: contact the product owner
(PO) or proceed knowingly without an Epic.
When creating a branch, choose a descriptive name that does not contain `codex`.
At completion, push and open a draft PR unless the user limits the task to local
changes. Explicit user instructions take precedence over this workflow.

PR titles must use `<type>(#<issue-number>): <short title>`, where `type` is
`fix`, `feat`, `chore`, `docs`, `impr`, `ci`, `perf` or other. Use the primary tracking issue number
and write the title in English.

## Writing and keyboard characters

Use ordinary keyboard punctuation and symbols in authored text, translations,
comments, documentation, commit messages and GitHub content:

- Use straight apostrophes and double quotes.
- Write an ellipsis as three periods (`...`) and use the ordinary hyphen (`-`).
- Use normal spaces and ASCII equivalents for decorative symbols.
- Avoid typographic quotes, single-character ellipses, long dashes, nonbreaking
  spaces and decorative Unicode punctuation.
- Keep normal accented letters for the language being written.

Write GitHub content and commit messages in English.
