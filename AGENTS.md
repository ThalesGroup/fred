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
this file. Its unconditional OpenSpec requirements are superseded by the
policy below. The former reference to a webdav checkout agreement is obsolete:
there is no checkout-wide suspension of OpenSpec or GitHub workflows.
Migrate remaining guidance as it is maintained; do not keep two authoritative
copies of the same rule. Legacy tool names do not require using Claude Code.

Conflict resolution order:

1. Explicit user instruction.
2. Closest nested `AGENTS.override.md` or `AGENTS.md`.
3. Root `AGENTS.md`.
4. Closest legacy `CLAUDE.md`, then root `CLAUDE.md`.
5. Root `AGENT.md`, if present (orientation only).

If a conflict cannot be resolved using this order, ask before changing files.

## Incremental collaboration - default working mode

Work in small, focused code increments that the developer can read and control.
Implement the requested adaptation, keeping the code simple, clear and robust,
then present the relevant diff and explain the concrete behavior. Do not expand
an implementation request into a general readiness or verification campaign.

The developer owns tests and quality validation. Unless explicitly requested,
do not launch tests, code-quality commands, audits, independent reviewer agents,
benchmarks, builds or deployments, and do not add a testing campaign to the lot.
Do not repeatedly ask permission to run them; hand back the code for review.
Read the code and affected callers as needed to implement the change correctly.
Flag a concrete unresolved issue briefly instead of widening the task.

Existing OpenSpec, RFC and arc42 documents inform implementation; they do not
automatically require new planning artifacts, approval gates or a documentation
campaign for each increment. Use those workflows when the developer asks for
them. A request to implement code alone does not request PR readiness, a commit,
a push or publication. State accurately which validation was not performed.

This working mode takes precedence over the automatic workflow, verification,
review and close-out requirements below and in legacy guidance or skills.

## Locating reconstruction code and documentation

For a question about the reconstructed user journey, start with the
[arc42 question map](docs/architecture/README.md#find-a-function), then the
[control-plane source map](apps/control-plane/src/README.md). They point to the
current UI consumers, Rust owners, SQL migrations and focused evidence. Historical
OpenSpec changes and Swift documents are comparison material, not proof of current
Rust behavior. Do not describe an API-only operation as an available UI journey.

## Functional reconstruction continuity

When continuing Dimi's incremental Rust reconstruction, first read
[`docs/WORKING-JOURNAL.md`](docs/WORKING-JOURNAL.md).
Update its indexed feature records after each meaningful step: observations,
focused changes, explicit user validation, pending architecture updates and next
step. Preserve the existing frontend, including nonfunctional screens, unless
Dimi requests a specific adaptation. Update architecture chapters on request;
do not confuse an implemented change with a validated user journey.

## OpenSpec - team choice, under evaluation

OpenSpec is the team's chosen default for substantial development, and remains
under evaluation. Use it where explicit requirements and acceptance criteria
help implementation and review; producing artifacts is not an end in itself.

Choose the workflow before implementation and briefly state the reason:

- **Use OpenSpec** for features, changed product behavior or public contracts,
  cross-component changes, migrations, and substantial or risky fixes and
  refactors. A small diff can still need OpenSpec when it affects authorization,
  data integrity, concurrency, or another sensitive contract.
- **Use a lightweight workflow** for localized, well-understood fixes restoring
  agreed behavior, mechanical typing/lint/format fixes, test-only improvements,
  and documentation corrections or maintenance. This applies when scope and
  acceptance can be stated clearly in the issue or PR, with no unresolved
  design or contract change. No separate permission to skip OpenSpec is needed.
- **Investigate first** for read-only reviews, diagnosis, and exploration. Do not
  create an OpenSpec change merely to investigate. If implementation follows,
  choose the appropriate workflow once the scope is known.

For lightweight work, state the problem, intended change, and verification in
concise prose; implement within the user's authorized scope, then report the
result and why OpenSpec was unnecessary. No RFC or separate planning approval
is required. This exception supersedes legacy planning gates in `CLAUDE.md`;
applicable engineering, testing, and review requirements still apply.
If the work grows beyond these conditions, reassess before expanding scope.

For OpenSpec work, find and extend an existing relevant change first. Before
implementation, prepare the proposal, design, tasks, and delta specs and obtain
developer confirmation of the scope and acceptance criteria. Follow the
repository procedures in `.agents/skills/openspec-*/SKILL.md`, using the
`openspec` CLI; these are plain Markdown procedures, not vendor-specific
features. Use `openspec status --json` and `openspec instructions` to guide
artifact creation. Scaffolding an empty directory does not complete planning.
After verification and required review, reconcile the artifacts with the final
implementation, sync the delta specs, and archive the completed change using
the archive procedure. Use an RFC only for genuinely unresolved design choices
or work too broad to scope into a buildable change.

## Keep the specification set manageable

- One change per coherent, reviewable outcome, not per alert, file, or tiny
  implementation task. Do not combine unrelated work just to reduce file count.
- Extend existing capability specs; do not create a new capability for every
  issue. Keep durable specs focused on current observable behavior and contracts,
  with acceptance scenarios that add useful coverage.
- Give each fact one authoritative home: GitHub issues/PRs track work; active
  changes describe intended deltas; `openspec/specs/` describes shipped capability
  requirements; compact docs cover cross-capability guidance. Link between them
  instead of repeating requirements or status.
- Keep the required artifacts concise. Do not add status documents, parallel
  summaries, or standalone verification files by default; record evidence in
  existing tasks or the PR unless a separate record has a concrete purpose.
- At close-out, reconcile superseded requirements and archive completed changes
  promptly. Archives preserve history, not current instructions: exclude them
  from default current-behavior searches and consult them only for history.
- Do not bulk-delete archives or rewrite historical decisions as cleanup.
  Agree any retention or deletion policy separately as a team.

During the evaluation, use team retrospectives to assess whether OpenSpec made
scope, acceptance, and review clearer, and whether artifact effort, stale active
changes, duplicated requirements, or capability fragmentation are growing.
Adjust this policy from that evidence; do not build another tracking system
solely to measure the workflow. Under evaluation means the policy can evolve,
not that substantial work may silently bypass it.

## Database table reuse

Before adding a table, check whether an existing table can naturally hold the
data. Prefer extending it when that keeps the model clear and avoids unnecessary
tables. Add a separate table when distinct meaning, lifecycle, access rules or
compatibility makes it clearer or safer; briefly explain that choice in the
existing change design or PR.

## Commit and verification rhythm

Commit completed, reviewable blocks as work progresses instead of accumulating
all changes in one final commit. Each commit should have one clear purpose and
exclude unrelated local changes.

Group tests and broad quality checks near the end of a PR or after a substantial
set of related files has changed. During implementation, run only the narrow
check needed to resolve a concrete risk. Honor a developer's request for manual
feature validation before running tests.

## control-plane reconstruction on chore/rust-rebac

For a reconstruction audit, use
[`audit-control-plane`](.agents/skills/audit-control-plane/SKILL.md). It scopes the
independent review to implemented manager responsibilities, affected consumers and
arc42 conformity. It does not claim full-Fred or full-PR readiness. The generic
branch review below remains applicable to a full PR readiness request.

Rebuild Fred's Python behavior in Rust one complete feature at a time, using
the organization/team/project model. Preserve the complete existing Fred business UI as
a reconstruction invariant: reuse the same pages, routes, navigation, controls
and styles, changing data/API bindings rather than replacing or removing UI to
match the currently implemented Rust surface. Organization information appears
only in the existing profile page unless the developer explicitly approves a
different presentation. A missing manager API is a backend reconstruction gap,
not authorization to hide its UI. The unchanged business UI is the reference for manual
revalidation. Platform governance is a separate, explicitly requested scope:
organization listing/creation and designation of the organization owner/admin,
with account and provisioning access. The platform area must not expose personal
spaces or business resources, even when its user also holds organization/team
roles. Access to that person's organization belongs to a separate entry point.
For each feature, inventory the existing
roles, permissions, edge cases and configuration, logging and security
conventions before implementing it. Preserve their meaning in the new model;
do not silently drop a supported role, accept an ineffective grant, weaken a
check, or defer a known weakness within the step. Source inconsistencies must
be resolved explicitly, with regression coverage, rather than copied blindly.
Feature boundaries do not excuse incomplete behavior within an accepted step.
Use the [user journeys](docs/architecture/02-user-journeys.md) to explain each
implemented entry point, and the [reconstruction checklist](docs/swift/design/FRED-RECONSTRUCTION-CHECKLIST.md)
to check prerequisites while scoping the next feature.

Keep direct roles in OpenFGA and let its model evaluate permissions; do not move
canonical grants into SQL or duplicate the permission matrix in Rust. For each
authorization change, identify the exact OpenFGA request types, filters, count,
pagination, tuple volume, dependency ordering and SQL lock duration. State which
cardinalities drive cost (users, memberships, spaces or documents), distinguish
client RPC counts from server-side evaluation work, and verify affected request
budgets with focused tests. Keep the implemented inventory in the arc42 quality
chapter; put proposed costs and trade-offs in the existing OpenSpec design.
Report measurements with their fixture sizes and concurrency. Do not infer
scalability from one Check call, passing correctness tests or a small demo.

Each step is one clean, tested and documented commit on this branch. Do not
push without the developer's explicit agreement. Obtain independent review,
fix every actionable finding with a regression test, and have the corrections
reviewed before closing the step. Tests proving an architecture invariant
carry `// Proves: I<n>`. Applied SQL migrations are immutable, including comments
and whitespace: SQLx checks their checksums. Add each schema evolution as the next
numbered SQL file in `apps/control-plane/migrations/`. Preserve existing data;
prefer additive changes and describe any required data transformation before applying
it. Never alter `_sqlx_migrations` checksums to bypass validation. Before changing an
existing installation, inspect its migration history and take a backup. A fresh
installation applies the complete migration chain. Historical reset instructions
in the immutable first migration are superseded by this policy.
Before the first production release, the OpenFGA model is still replaced rather
than upgraded; this separate policy does not require resetting SQL for additive changes.

After implementation and the review/correction passes, perform a dedicated
documentation pass over the arc42 dossier in `docs/architecture/`. Every
control-plane change updates the relevant dossier chapters in the same commit.
Describe only implemented behavior in the present tense: no progress, plans,
status, or lists of missing features. Planning belongs in OpenSpec. Regenerate
derived blocks instead of copying code into prose.

Before committing, run `make test`, `make test-integration` and
`make code-quality` in `apps/control-plane`, plus
`make -C docs/architecture check` from the repository root. Validate OpenSpec
artifacts when the step changes them.

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
At completion, push and open a draft PR unless the user limits the task to local
changes. Lightweight work does not require an OpenSpec change alongside its
issue or PR. Explicit user instructions take precedence over this workflow.

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
