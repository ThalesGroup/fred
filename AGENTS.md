# Team / AI Assistant Instructions

`AGENTS.md` is the primary team workflow and governance entrypoint for coding
agents. The team is moving away from Claude/Anthropic tooling; the workflow
must remain usable through ordinary repository files and command-line tools.

At the start of every Fred task, read
[fred-architecture](.agents/skills/fred-architecture/SKILL.md). This shared skill
is mandatory for Codex, Claude and other coding assistants. Its editorial policy
applies to every feature change and architecture edit.

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

Formatting and local code-quality checks are part of every code increment:

- During editing, apply the repository's formatter to the files changed by the
  lot; do not approximate its rules manually or reformat unrelated files.
- Before handing back code, run `make code-quality` in each affected component,
  or its documented equivalent. Fix issues introduced by the lot and rerun the
  affected checks after the last relevant edit. Local compilation required by
  these checks, including Clippy, is authorized without another request.
- Report the commands and results. If a check cannot run or fails on a pre-existing
  issue, state the blocker and do not claim quality validation. Do not widen the
  lot to fix unrelated failures or weaken checks to obtain a pass.

Documentation-only changes do not require application code-quality commands.
The developer owns functional validation. Unless explicitly requested, do not
launch tests, audits, independent reviewer agents, benchmarks, release builds or
deployments, and do not add a testing campaign to the lot. Other compilation
commands also remain outside the default scope. Do not repeatedly ask permission
to run them. Read the code and affected callers as needed to implement the change
correctly; flag a concrete unresolved issue briefly instead of widening the task.

Existing OpenSpec, RFC and arc42 documents inform implementation; they do not
automatically require new planning artifacts, approval gates or a documentation
campaign for each increment. Use those workflows when the developer asks for
them. A request to implement code alone does not request PR readiness, a commit,
a push or publication. State accurately which validation was not performed.

This working mode takes precedence over the automatic workflow, verification,
review and close-out requirements below and in legacy guidance or skills.

## Weaver (Fred 5.x): current state versus target

Branch `weaver` carries Fred 5.x. It changes Fred's architecture, not what Fred
does: one Control Plane concentrates permissions, documents and user/organization
administration, which Swift (Fred 4.x, branch `swift`) spread across Python
services. Rust is an implementation detail of that Control Plane. Python keeps
the components that rely on Python libraries: the agent pod (LangChain/LangGraph)
and Knowledge Flow (Docling, PDF libraries, LangChain embeddings), which both
processes documents and serves knowledge to capabilities through its API.
In one sentence: Knowledge Flow holds and serves knowledge, pods reason,
Control Plane governs.

| Component | Target role | On `weaver` today |
| --- | --- | --- |
| Control Plane (`apps/control-plane`, Rust) | Identity and admission, OpenFGA permissions, organizations, teams, spaces, users, document drive, ingestion through Temporal, agent instances | Replaces the deleted Python `apps/control-plane-backend`; covers part of the product. Unported screens still call `slices/legacyControlPlane` and fail. |
| Agent pod (`apps/fred-agents`, `libs/fred-runtime`, `fred-sdk`, capability libraries) | Runs agents; reaches knowledge only through capabilities, which call Knowledge Flow API | Custom assistant wired. `document_access` search temporarily runs locally in the pod (to be returned to Knowledge Flow API); other capabilities call Knowledge Flow over HTTP and are not yet adapted (see capability lots below). |
| Knowledge Flow worker (`main_worker.py`) | Temporal worker for document processing | Native ingestion path being finished. |
| Knowledge Flow API (`main.py`) | Serves knowledge to capabilities (search, markdown, tree, content, files, tabular) under the space-based model | Endpoints still use the Swift catalog and per-document ReBAC; adaptation to Weaver documents and space permissions is the capability lots' work. |
| Frontend | Same business UI, rebound to the Control Plane | Partially rebound. |

Keep the two columns apart in every audit, review, plan and report:

- Label each claim **current** (observed in `weaver` code, with evidence),
  **target** (this section, the security section below, an OpenSpec change) or
  **Swift** (4.x behavior, comparison material only). Code present in the tree
  is not a wired Weaver journey; only Dimi's validation recorded in
  `docs/WORKING-JOURNAL.md` makes a journey validated.
- A gap between current and target is migration distance, not a defect, unless
  the lot under review claims to close it. Report it as such, briefly.
- Do not invest in what the target removes (the legacy control-plane client,
  Knowledge Flow API routes no capability uses) beyond what the requested lot
  needs, and add no new consumer of them. Do not implement target pieces outside the agreed lot.
- On this branch, `docs/swift/` and the Swift-specific parts of `CLAUDE.md`
  (Python control plane, Alembic) describe 4.x. `docs/architecture/` describes
  only the current validated state, per the fred-architecture skill.

Codex and Claude both work on this branch, in separate lots:

- State the lot's scope (components, files) before editing and stay inside it.
- Uncommitted changes you did not make belong to Dimi or the other assistant:
  never revert, reformat, stage or commit them. If your lot must touch such a
  file, stop and ask. Stage explicit paths, never `git add -A` or `git add .`.
- Re-check shared sequences just before creating an entry: next SQL migration
  number, OpenFGA model, generated clients. In the journal, edit only your
  lot's record.

## Weaver: capability lots

Dimi's direction (2026-10-27): every capability installed on the native agent
pod becomes enableable, selectable and working from the existing UI, one
targeted lot at a time. Dimi leads; each lot runs in a fresh assistant from a
lot brief. The plan and lot list are in the journal record `CAP`.

- **No OpenSpec** for these lots unless Dimi asks: the brief and its journal
  record are the agreement. For lots Dimi launches, this supersedes the
  capability exclusions of OpenSpec `simplify-weaver-runtime-authorization`
  (decision 5a, task 2.2). Its security decisions (M4 turn boundary, pod-owned
  offers 5b-5d, document visibility 5) and the security section below still apply.
- **No invention.** A lot rewires an existing Swift feature: same capability
  package, manifest, tools, UI packs and panels. Adapt only what Weaver's ReBAC
  boundary requires: canonical space context instead of `team_id`, Rust Control
  Plane owners instead of the Python control plane, Knowledge Flow API endpoints
  reading Weaver documents under space permissions instead of the Swift catalog
  and per-document tuples. Do not move Knowledge Flow functions into the pod.
  A new contract, endpoint or store needs Dimi's decision, recorded in the
  brief, before code.
- **Responsibilities.** A capability is a public library linked into one agent
  pod; its offer is (pod, capability). A model is a network service reachable by
  any pod. Control Plane is a gateway and configuration manager: it checks
  inventory membership, the organization's authorization and the person's
  rights, forwards configuration to the owning pod's `validate-config` and
  stores the returned envelope. It never names a capability, reads a capability
  configuration field or encodes a capability rule. Those live in the library
  (`validate_config`, tools, ports). The native pod links the same libraries as
  Swift; its inventory is the single truth, with no allowlist elsewhere. The
  organization's authorization (deny by default) is the only usage gate.
- **Branch-new code.** No installation or saved data to preserve: no migration
  path, compatibility shim or legacy branch for earlier `weaver` states.
- **Brief, required before editing:** goal; Swift reference (behavior, files);
  Weaver adaptation and the guarantee it preserves; in-scope files; out of
  scope; decisions already taken; manual cases Dimi will play; arc42 chapters
  expected to change. If the brief is ambiguous or the work exceeds it, stop and ask.
- **Cycle:** implement in incremental mode (formatter and `make code-quality`,
  no test campaign, no commit) -> Dimi validates in the UI -> journal record with
  that validation -> arc42 update of the validated journey (functional view,
  then technical view, code references in annexes) -> Dimi commits. Until Dimi
  validates, a lot updates the journal only, never arc42.
- Not applicable to these lots: CLAUDE.md lifecycle steps 1-6, GitHub issue and
  close-out statement; the per-step tests, independent review and commit of
  the control-plane section below. Run them only when Dimi asks.

## Weaver: preserve Swift's security model while simplifying ReBAC

This is Dimi's explicit Weaver direction. Weaver reinvents the ReBAC data model
and consolidates its implementation; it does not authorize a departure from
Swift's security model, trust principles or guarantees. Preserve the guarantees,
not the scattered checks, legacy tables, endpoint layout or per-document tuples.
Read this section before planning or changing Python libraries, agent execution,
capabilities, identity, authorization or backend-to-backend communication.

Weaver development is a breaking replacement, not a backward-compatible Swift
variant. Do not add compatibility flags, legacy aliases, fallback endpoints or
parallel old/new authorization paths. Migration is a separate workstream. Replace
and remove obsolete behavior in each scoped lot, after checking its consumers;
preserve security guarantees and useful shared mechanisms, not legacy code.
Optimize for the fewest concepts and least owned production code consistent with
clear, robust behavior. Do not weaken controls or compress code to claim savings.

- Dimi clarified departure semantics: no reversible suspension or automatic
  restoration of former access/context on return; treat return as newcomer
  admission. Dimi's 2026-10-26 M4 arbitration supersedes the earlier next-operation
  rechecks and five-minute revocation bound for agent turns: one complete trusted
  Control Plane resolution per turn, then local enforcement of that fixed context
  for every LLM call, retry and descendant. No additional HTTP/SQL/OpenFGA reads to
  refresh turn authority during the turn; revocation/decommissioning is observed at
  the next turn. A started turn may finish. Explicit cancellation, terminal-run
  enforcement, execution limits and resource-specific data checks remain separate.
  See OpenSpec simplify-weaver-runtime-authorization, design 5e. This is an accepted
  implementation target, not evidence of a wired runtime. Runtime/access cleanup
  is not implicit authorization to erase shared content, persisted histories or
  audit evidence.
- Preserve JWT validation, the distinction between the authenticated workload
  and the person it acts for, trusted delegation, user/service credential
  renewal, credential confidentiality and run-lifetime enforcement. A service
  token is not the person's identity or permission. Renewing credentials must
  never restore revoked rights or extend a completed run's authority.
- Identity comes from validated credentials or an explicitly trusted delegation
  path. Browser/model-supplied user, organization, space, instance and conversation
  fields are requests to verify, not authority. Bind canonical context on the
  server; model/tool arguments cannot replace or broaden it.
- Preserve admission, organization/space isolation, conversation ownership/access,
  revocation and lifecycle controls at their agreed boundaries. The M4 turn
  context authorizes only that turn and cannot broaden resource/data scope.
  Initial execution admission is not unlimited authority for later turns or data
  access. A missing Weaver equivalent is a contract gap to resolve explicitly,
  never permission to disable the Swift guarantee or reproduce a legacy bypass.
- The agent's exchange with Control Plane to resolve its execution context already
  exists in Swift. Clarify and simplify that contract; do not infer a decision to
  replace all Python authorization with REST calls or to introduce a new signed
  execution grant. The accepted M4 freshness boundary is one complete resolution
  at turn admission; do not reintroduce per-invocation authority reads.
- Knowledge Flow API stays (Dimi, 2026-10-27, reversing the morning's removal
  decision). Capabilities reach knowledge through its endpoints; only Knowledge
  Flow holds storage credentials. Each endpoint must establish, for the person
  the call acts for, read access to the requested space before exposing data,
  then apply the shared visibility primitive (`fred_core.documents.access`).
  Decision K1 (Dimi, 2026-10-27): Knowledge Flow validates the person's
  (delegated) identity as in Swift, then makes one OpenFGA `can_read` check on
  the requested space against the published Weaver model. It neither asks
  Control Plane nor trusts a pod-asserted space. The pod sends the space from
  its turn binding, never from model arguments. This per-request check is a
  resource-specific data check, not a turn-authority refresh.
  Storage credentials authenticate infrastructure access, not Bob's entitlement.
- Document permissions derive from their containing Weaver space (organization,
  team, project or personal space); do not recreate per-document authorization
  tuples. PostgreSQL placement/publication/lifecycle facts and OpenFGA permissions
  jointly constrain access. An index hit alone is not authorization. Consolidate
  checks into a few shared, efficient primitives; do not duplicate the permission
  matrix in each capability or assume a fixed RPC budget without evidence.
- Keep external tools outside Fred's identity trust distinct from services that
  explicitly accept delegation. Do not forward Fred credentials automatically to
  unrelated endpoints. Port remote MCP behavior in its own agreed scope; preserve
  existing credential renewal and delegation guarantees rather than redesigning
  them incidentally during the local-capability migration.

For each affected security guarantee, identify the Swift enforcement point, its
Weaver replacement and the evidence needed to establish preservation. Explain any
changed trust boundary before implementation; obtain an explicit decision rather
than infer approval from "simplification". This traceability is scoped to the
change and does not authorize a broad audit or tests outside the agreed workflow.
Do not claim security equivalence from version numbers, successful startup or
catalog discovery, or promise that SSI/CVSSI reassessment is unnecessary.

## Rust engineering baseline

Apply these rules to Rust implementation and review, including the Control Plane
and its embedded agent. This is Fred's shared baseline for Codex and Claude;
no external prompt collection is required. Keep the incremental workflow above.

### Safety, ownership and errors

- Prefer immutability, explicit ownership and simple, zero-cost abstractions.
  Do not add traits, generics or indirection without a concrete need.
- Do not introduce `unsafe` code unless explicitly requested by the developer
  with an architectural justification; document the safety invariants if used.
- Avoid `unwrap()` and `expect()` in production paths. Propagate errors with `?`
  and use existing typed errors (`thiserror`, `AppError` or the component's
  equivalent). Keep internal error detail out of public responses and secrets
  out of logs. Distinguish startup failures from recoverable request errors.
- Prefer borrowing (`&str`, slices) when appropriate and avoid unnecessary
  allocations and clones. Owned values are appropriate when data must outlive
  a call or move into a task; cloning an `Arc` is not a deep data copy.

### Async, concurrency and SQLx

- Never hold a `std::sync::MutexGuard` across `.await`. Keep synchronous lock
  sections short; use `tokio::sync::Mutex` only when async locking is needed.
  Avoid holding any lock across network I/O when the operation can be separated.
- Do not block Tokio executor threads with synchronous I/O or CPU-heavy work.
  Use async APIs or bounded `spawn_blocking` work where appropriate; account for
  the fact that started blocking work cannot simply be aborted.
- Prefer standard Tokio primitives and bounded channels for agent/event loops.
  Use `mpsc`, `oneshot` or `broadcast` according to delivery semantics; handle
  backpressure, closed receivers and broadcast lag explicitly. Keep async traits
  minimal and make `Send` requirements match how tasks are actually executed.
- Bound concurrent executions and outbound-call durations. Tie work to its
  owning request/run, propagate cancellation, and stop stream producers when
  the SSE client disconnects. Avoid detached tasks without an explicit owner
  and shutdown policy. Do not assume dropping a future undoes remote effects.
- Reuse configured SQLx pools. Never retain a transaction or checked-out SQL
  connection throughout an LLM call or SSE stream; scope database work narrowly.
- Prefer compile-time checked `query!`/`query_as!` where the project's schema or
  prepared offline metadata supports them. Otherwise use parameterized queries
  with explicit typed results (`query_as` and `sqlx::FromRow`). `FromRow` alone
  does not validate SQL at compile time. Never interpolate untrusted SQL values.

### Structure and verification

- Separate domain logic, wire models and Axum handlers with small modules;
  follow existing component boundaries without inventing layers for trivial code.
  Reuse Fred's contracts and authorization mechanisms at HTTP boundaries.
- Match APIs and features to the dependency versions in Cargo manifests and
  lockfiles. Avoid adding dependencies for behavior already supplied locally.
- Deliver complete file edits with necessary imports and error handling. When
  code snippets are requested, make them self-contained or clearly identify
  their integration context; do not present pseudocode as compilable Rust.
- Review likely compiler and Clippy issues before handing back code, including
  ownership, `Send` bounds, lock lifetimes and unused results. Static reasoning
  is not a successful build. Follow the incremental mode for running checks and
  report exactly which compilation, lint and tests were or were not performed.

## Dimi's reconstruction method

Use [fred-reconstruction-method](.agents/skills/fred-reconstruction-method/SKILL.md)
for an explicitly requested reconstruction convergence or corpus review. It defines
bounded completeness, independent review, the committed reference and the canonical
arc42/source maps. The mandatory fred-architecture skill governs the dossier:
current human-readable architecture and technical annexes, with no feature plan
or proposed decisions. Scoped, authorized consolidation retires superseded prose
only after preserving useful contracts and resolving consumers. It does not
authorize unrequested tests, commits, publication, resets or unrelated deletion.

## Architecture maintenance

Apply [fred-architecture](.agents/skills/fred-architecture/SKILL.md) when adding or
changing a feature: update its existing architectural explanation and relevant
technical annexes as part of the work. No separate documentation request is needed.
Follow the agreed editorial scope; clarify genuinely new section scope instead of
filling headings with implementation inventories. This policy supersedes older
instructions that defer architecture updates or put plans inside arc42.

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
Dimi requests a specific adaptation. Keep affected architecture chapters current
as part of feature work under fred-architecture;
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

## control-plane reconstruction on weaver

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
Use the [user journeys](docs/architecture/02.1-user-journeys.md) to explain each
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
installation applies the complete migration chain.
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
