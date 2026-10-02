---
name: audit-branch
description: Review a branch before PR readiness for actionable defects, public-contract mismatches, consumer regressions and stale integration paths. Includes frontend and backend; passing tests do not replace review.
---

# Branch review

Read-only review of the change and its affected consumers. Do not edit files,
commit, push or post comments as part of the reviewer role. Return findings to
the author, who handles them within the user's authorized scope. Apply the
repository's AGENTS.md and relevant nested instructions.

## Establish the actual scope

- Read `git status --short`. Record the reviewed HEAD, base and any local changes.
- For an existing PR, read its actual base with `gh pr view --json baseRefName,headRefOid`.
  Otherwise use the user-specified base or inspect branch/upstream metadata to
  establish the intended target. Do not assume `develop`, `swift`, or the
  feature branch's tracking upstream is the PR base. Ask if genuinely ambiguous.
- Resolve the base locally and use the merge base for the committed diff:
  `git diff <base>...HEAD`. Fetch the identified remote ref when needed; do not
  check out, reset or modify the author's worktree.
- Include staged, unstaged and relevant untracked changes if reviewing the
  working tree. A last-commit review is not a full branch review. If the requested
  review is focused, explicitly name what it excludes.
- Group all changed files by responsibility, including packages, tests, docs,
  help content, configuration and deployment. Frontend code is not exempt
  because TypeScript passes. Follow affected callers and imports outside the diff.

## Inspect behavior and contracts

Read the applicable existing specs/contracts, then compare them with the actual
implementation and representative consumers. Load runtime/product contracts
only for changes touching those boundaries; use package contracts for SDK work.

Before following implementation details, state the observable invariants from
user requirements, existing valid usages and the contract. Do not infer the
expected behavior solely from the new types or tests: both may encode the same
mistake. For each changed public boundary, trace inputs through state owners and
consumers to observable results, including unchanged dependencies.

Review one coherent responsibility to completion before handing off its first
fix. Collect all supported findings in that pass; do not repeatedly switch from
one review comment to its patch and call that a review of the responsibility.
For externally reported defects, first identify the failed assumption and check
its other uses in the bounded surface. Review every operand of an arithmetic
contract, every participant sharing an event, or every consumer relying on the
same identity; choose variants from that mechanism, not from the example's nouns.

Try to disprove each invariant with a valid-looking consumer outside the current
happy path. Use stateful children for identity claims, a second participant for
exclusive ownership, and changed inputs for lifecycle claims. Explain why the
chosen scenario exercises the assumption; a long list of tests is not evidence
that it does. An optional property must work when omitted or be rejected by the
contract. Demonstrate failing behavior rather than reporting broad types alone.

Use the relevant questions below, not a mandatory matrix for unrelated work:

| Area | Questions to challenge |
| --- | --- |
| Public types | Do optional/conditional props agree with runtime requirements? Are invalid combinations rejected? Does generated or packaged output expose the same contract? |
| Input/state | Do supported controlled/uncontrolled modes, empty values, external updates and reset behavior remain consistent? |
| Identity | Do selection, sorting, pagination and persistence use the same stable identity? |
| Dimensions | Are accepted units and boundary values interpreted correctly, including container-relative layouts? |
| Interaction | Do nested native/ARIA controls, editable content, portals and keyboard events preserve their own actions? |
| Presentation | Are foreground/background tokens paired, themes inherited, and long text/narrow layouts usable? |
| Async work | Are delayed responses, errors, cancellation and terminal states consistent across consumers? |
| Retirement/migration | Do routes, callers, generated clients, configuration, help/search links and both locales still lead to supported behavior? |

For backend and repository integrity, also inspect relevant paths for dead or
commented-out code, duplicate declarations/validators, missing imports hidden
by type suppressions, and temporary artifacts. For migration changes, verify
linear Alembic ancestry and the repository's required migration checks. For
merges within the reviewed range, use the relevant merge-review procedure.
Do not expand a targeted review into unrelated cleanup or speculative hardening.

## Composition and extraction review

When exporting reusable UI or changing event/focus handling, read
[the composition review procedure](references/ui-composition.md). Follow events
through realistic parent/child combinations, including unchanged dependencies;
separate component tests do not establish composition correctness.

For moves/extractions, compare representative valid calls against the merge
base before accepting a correction. Classify findings as introduced regression,
pre-existing defect newly exposed, or deliberate contract change. Rejecting a
previously valid input is a compatibility change, not evidence that the original
bug is fixed. Document it as such and check it against the authorized scope.

## Evidence and verification

- Existing tests show what is covered, not that all accepted inputs work. Seek
  counterexamples before adding tests that restate the implementation.
- Reproduce findings with a focused test, typecheck or browser case when useful.
  Separate a confirmed failure from a plausible concern and an unverified area.
- For public UI changes, use the existing `libs/frontend` isolated packed
  consumer and browser fixtures. Use type-negative cases for rejected inputs
  and runtime cases for valid behavior. Source imports alone do not validate
  package consumers. Do not create a parallel test harness by default.
- Reuse relevant current verification evidence. Rerun affected checks after
  corrections; do not repeatedly run unrelated suites without a concrete reason.
  When a broad quality check is required, run it from the repository root.
- Consult relevant specialist review skills when available. If unavailable,
  apply the corresponding checks here and declare any remaining limitation;
  do not claim the specialist review occurred.

## Independent review handoff

For the non-trivial changes covered by AGENTS.md's review rule, use a separate
reviewer with fresh context when available. Give it the task requirements,
base/head, full diff or an explicitly bounded responsibility, relevant contracts
and raw verification artifacts. Do not supply a list of expected bugs or ask it
merely to confirm the author's solution. Divide large reviews by responsibility
and account for every excluded area. A review of one corrective patch does not
establish coverage of the whole PR.

The reviewer is read-only and returns all supported actionable findings with
file/line, concrete trigger, impact and minimal correction direction. The author
must assess each finding, fix or justify it, and verify affected behavior.
If independent review cannot run, report that limitation rather than substituting
self-review and calling it independent. Do not invent findings to fill a quota.

## Report and completion

Put concise evidence in the existing PR or task response, not a new tracking
file by default:

- **Scope:** base/head, local changes, reviewed responsibilities and exclusions.
  For substantial reviews, include a compact responsibility-to-evidence mapping
  in the existing response/PR: invariant, challenged scenario, result, untested
  boundary. Do not create a parallel tracking document.
- **Findings:** severity, location, reproduction/trigger and user impact;
  distinguish confirmed defects from questions. Include disposition on follow-up.
- **Verification:** commands/results actually obtained, with relevant limitations.
- **Residual gaps:** unreviewed consumers, unavailable environments or pending
  independent review. Say "no findings in the reviewed scope", not "bug-free".

Only call the work ready when actionable findings have a recorded disposition
and required checks pass. A changed HEAD needs review of the subsequent delta;
repeat broader review only when its impact warrants it. For GitHub follow-up,
read full review bodies as well as inline threads and general comments, and obey
the user's instructions about replying and resolving discussions.

To assess whether this procedure improves detection, use the bounded replay
protocol in [references/evaluate-review.md](references/evaluate-review.md).
