---
name: fred-reconstruction-method
description: Apply Dimi's incremental Fred reconstruction method when establishing or reviewing a committed baseline, closing an agreed feature slice, or consolidating code and arc42 into the future reference corpus. Not an automatic full audit for every small edit.
---

# Fred: a small scope, fully understood

Dimi's objective is a committed implementation he understands and accepts, with a
precise arc42 corpus that makes the next feature straightforward to locate and
review. A small scope limits functionality, never correctness or security. Time
pressure does not turn a known defect into an acceptable completion condition.

Read the current checkout's AGENTS.md and arc42 entry point. Resolve every path
below against that checkout, not against this skill's installed location. Do not
assume a fixed directory, branch, current SHA, deployed version or feature list.

## Establish what is being requested

Distinguish review, correction, documentation consolidation and creation of a skill.
Writing this method does not itself launch an implementation/audit campaign.
An ordinary small fix remains small. For an explicitly requested convergence pass,
continue through the agreed scope rather than stopping after a useful first report.

Record the current commit and working-tree state. A committed baseline is a review
reference, not certification. If Dimi asks for a whole-checkout snapshot, include the
authorized current state instead of blocking on historical commit purity; exclude
secrets and disposable artifacts. Never rewrite history, discard changes, push,
deploy or erase state merely to make the review easier. Do not carry permission to
reset an environment from an earlier discussion into a new destructive action.

Name the accepted journey and its dependencies. Distinguish:

- exposed and required behavior within this slice;
- implementation present outside the slice, not validated by this review;
- future features, explicitly proposed or requested, with no runtime implementation
  implied by their listing.

For example, a journey ending at folder creation includes authentication, consent,
bootstrap, identities, organization attachment, roles, workspace selection and folder
persistence. It does not justify inventing ingestion cleanup, agents or satellites.
A callable unsafe path inside the accepted scope remains a defect even if its button
is absent. Dependencies necessary to exercise the slice cannot be silently excluded.

## Non-negotiable design constraints

- Preserve existing Fred behavior, security levels, supported identity-provider
  modes and frontend controls unless Dimi explicitly approves a difference.
  Reuse the existing UX; do not hide unreconstructed screens to make progress look
  complete. Do not invent a connected UI for an API-only operation.
- Keep authentication, personal consent, organization attachment, governance and
  content permissions distinct. An ownership/admin label never proves content access.
- Configurable resource names, service addresses, credentials and deployment choices
  have one authoritative configuration. All consumers, including provisioning,
  derive them from that source. Do not duplicate resource literals or infer business
  storage names from a component name. True protocol constants and agreed domain
  invariants belong in named code definitions; do not turn them into gratuitous knobs.
- Prefer an explicit boundary and the existing mechanism to another abstraction,
  compatibility branch, fallback or recovery system. Describe a concrete failure
  scenario before adding machinery for it; obtain design agreement for added complexity.
  Do not remove required transactional/security guarantees merely to shorten code.
- State persisted-resource and migration effects explicitly. A rename is not a data
  migration. SQL, OpenFGA and object storage have distinct owners. Applied SQLx
  migrations are immutable; a new database starts from the full migration chain.

## Build the future corpus in arc42

Keep the main reading path about people: actor, prerequisites, action, visible
result, denied actions and retained data. Technical detail goes in linked references.
No empty chapter scaffolding, aspirational capabilities or generic architecture prose
as a substitute for a verified explanation.

Reuse the existing dossier, not a second architecture tree. Give these three views
separate, explicitly labelled homes within arc42:

1. **Current implementation**: precise journeys, permissions, contracts, deployment
   boundary and SQL catalogue. Include every application table, keys, constraints,
   indexes, ownership and the meaning of relationships absent from SQL. Generate
   schema/API references from their source when possible; distinguish SQL guarantees
   from application guarantees and generator limitations.
2. **Feature plan**: one indexed list of accepted/current features and explicitly
   proposed next slices. For each: stable ID, user outcome, scope/exclusions,
   prerequisites, acceptance scenario, current implementation reference and state
   (proposed, agreed, implemented, verified). Link evidence rather than duplicate
   the journal or issue tracker. Dimi chooses ordering; never invent a backlog to
   fill a template. A future row is not authorization to implement it.
3. **Key design decisions**: stable ID, question, current/accepted/proposed status,
   decision, reason, constraints/trade-offs, affected features and code. Preserve
   meaningful unresolved alternatives; do not manufacture an ADR for every detail.
   An unresolved choice must not appear as an implemented guarantee.

These plan/decision views are deliberate exceptions to current-state-only prose;
their status is explicit. Reuse existing arc42 sections where suitable; introduce a
single dedicated feature-plan or decision page only if no existing home serves it.
The working journal remains outside the dossier and records execution/review status.

Maintain two complementary maps, linked from AGENTS.md:

- arc42: question/feature -> useful contract, journey, SQL or decision section;
- code: feature -> actual UI consumer, handler, domain owner, authorization,
  persistence/configuration and focused tests, with a link back to arc42.

Use file paths and stable symbols rather than copied implementation prose or line
numbers that immediately drift. Test presence is not proof of a passing test.

## Independent review and correction loop

For an authorized audit, use the repository's `audit-control-plane` procedure if
present. Give independent reviewers fresh context: checkout, commit, agreed scope,
user constraints and source pointers, not desired findings. Split by coherent
boundaries only when useful. Reviewers read without editing; the author reconciles
findings and owns corrections. Ordinary implementation does not automatically spawn
review agents.

Trace the actual consumer through API, authority, persistence and observable result.
Check code against the accepted contract and docs in both directions. Existing code,
prose and old tests are evidence, not automatic authority over the user's intent.
Report each finding with trigger, evidence, impact, smallest correction, regression
scenario and classification: defect, documentation discrepancy, decision or missing
verification. Reject unsupported future-feature demands, not confirmed defects.

When corrections are authorized, make small coherent changes, update the canonical
references and have substantive corrections independently re-read. Use targeted
checks that exercise the violated guarantee. Respect the user's test/build ownership;
if a necessary check has not run, keep verification open rather than claim closure.
Do not repeat a broad audit after every tiny wording correction. The tracked findings
and coverage must converge; do not restart a new disconnected review each turn.

## Retire misleading RFC/OpenSpec material

The desired endpoint is one active, sufficient corpus, not several contradictory
specifications that every future assistant must reconcile.

During an authorized corpus-consolidation pass, inventory only documents relevant
to the accepted scope. For each old RFC/spec/change, determine whether it contains:

- a current contract/decision: preserve its substance in the canonical arc42 section;
- an unresolved useful choice: retain it once in the design-decision view;
- a future feature Dimi wants: reference it once in the feature plan;
- obsolete or duplicated content: retire it after its unique information is accounted for.

Update inbound links, generators, skills and CI consumers before deleting a referenced
file. Applied SQL migrations, security regression tests and executable schema inputs
are not obsolete design prose. Do not weaken CI to make document deletion pass.
Use a compact old-path -> canonical-section disposition in the existing work record
while reconciling; it is not a new permanent documentation layer.

When removal is authorized for the scoped corpus, remove superseded working-tree
RFC/OpenSpec files; Git retains their history. Do not bulk-delete unrelated product
specifications or archives. If a required consumer still depends on an old file,
resolve that dependency or record the precise remaining blocker. An archive still
present must be clearly historical and excluded from the normal reading path, not
another active authority. Creating this skill alone does not authorize that cleanup.

For this reconstruction, accepted feature/design entries can carry the agreed scope
and criteria instead of adding another RFC/OpenSpec package. Do not duplicate them
solely to satisfy legacy process wording; preserve executable contracts that remain
required. Other repository workflows continue to apply outside this reconstruction.

## Completion means evidence, not reassurance

Close an agreed slice only when its journey and dependencies are implemented,
security and supported modes are preserved, findings are dispositioned, required
verification is evidenced, arc42 and both maps match the code, and obsolete active
references have been reconciled within the authorized cleanup scope. A deferred
in-scope defect or unrun required check keeps the slice open.

Keep commits coherent and usable as review references when committing is authorized.
Do not confuse a snapshot commit with this completion criterion. Report the commit,
exact scope, checks actually run, remaining decisions and next user validation.
Dimi's manual acceptance is explicit; never infer it from silence or a successful build.
Never certify "perfect" or "bug-free". State what the evidence establishes.

For a reusable independent-review request, read
[references/review-prompt.md](references/review-prompt.md).
