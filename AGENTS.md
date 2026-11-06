# Fred team development instructions

This is the shared entry point for Codex, Claude, Gemini, Copilot and other
assistants. Tool-specific instruction files route here; they do not define a
second workflow. Read the nearest nested instructions before editing.
Explicit user instructions take precedence, then nearest `AGENTS.override.md` or
`AGENTS.md`, then this file. Resolve material conflicts before dependent edits.

## Sources and working order

Fred's maintained architectural explanation is [arc42](docs/architecture/README.md).
Start with its navigation map, then read the relevant chapters and technical
annexes; do not reload the whole dossier for every change. Code, migrations and
executable checks establish implementation facts. Accepted decisions describe
intended behavior, not unquestionable truths. Challenge a decision when concrete
evidence invalidates its assumptions or shows disproportionate cost. Explain the
evidence, consequence and smallest useful comparison before proposing a change;
do not silently replace the decision or rewrite the documentation to hide a defect.
Use component READMEs for commands and usage. Historical material in Git is
comparison evidence only when explicitly needed, never an active contract.

For a domain or persistence change, use
[fred-reconstruction-method](.agents/skills/fred-reconstruction-method/SKILL.md):
**business need -> invariants and lifecycle -> schema and transactions ->
application usages -> API -> UI**. Read its agreed decisions and design targets
before asking questions already answered. Do not derive the business model from
an endpoint, a screen or the existing implementation. Routine formatting, typing
or operational work does not require a schema-design exercise.

Distinguish four states in design and review: currently used behavior, schema
preparation only, agreed functionality still to implement, and historical Swift
behavior. A table, route, test or generated reference alone proves no integrated
user journey. Design capacity targets are not measured production capacity.

Read [fred-architecture](.agents/skills/fred-architecture/SKILL.md) at the start
of a Fred task; use its editorial rules when updating the dossier. Keep proposed
work in the current task or issue. No RFC workflow or separate architecture-doc
mode remains. Do not rebuild the retired document corpus.

## Architecture audits that support a decision

For a requested architecture assessment, state the decision to be informed and
inspect only the responsibilities and boundaries needed to answer it. Start the
report with a short conclusion: what to retain, what warrants reconsideration,
and what remains uncertain. A sound model is a valid outcome; do not manufacture
simplifications or turn every hypothetical use into an implementation requirement.
An explicitly deferred need stays outside acceptance criteria until reopened.

Separate structural concerns from local defects. Include concrete source evidence,
but put detailed findings after the decision summary, without repeating the whole
investigation. Surface a serious security or correctness issue even when it does
not change the architectural conclusion; discovering it does not authorize a fix
or a wider audit. This decision-first format takes precedence over exhaustive
skill output templates for architecture assessments; explicit review requests
still determine scope and required detail.

When documentation updates are authorized, reflect the agreed conclusion in the
existing arc42 explanation and annex references, not a new audit ledger. A
read-only audit stays read-only. Keep reasons and meaningful limits with
the canonical explanation; keep pending work in the task or issue. Link to that
explanation from instructions instead of copying domain rules into skills. Verify
the affected sources and distinguish implementation evidence from deployed
validation; document neither an untested journey as received nor a local defect
as proof that the whole architecture is wrong.

## Incremental collaboration

- State the concrete problem, in-scope components/files and expected result.
  Work in small, reviewable increments; do not turn a fix into a general audit.
- Inspect the branch, working tree and applicable instructions first. Reuse the
  suitable checkout; do not switch branches or create tracking artifacts merely
  to satisfy a ritual. Use an existing issue when the task supplies one.
- Other authors' uncommitted changes are theirs. Never revert, reformat, stage or
  commit them. If the task must modify such a file, ask before changing it.
- Inspect relevant decisions and sources before asking. Ask a concrete business
  question when uncertainty changes rights, isolation, retention, cardinality or
  lifecycle; explain the consequence with an example. Continue independent work.
  Resolve interchangeable SQL or implementation details yourself.
- Prefer few precise concepts, explicit relationships and one owner of each fact.
  Reuse existing mechanisms; remove superseded paths within the agreed scope.
  Do not add speculative generic resources, policy engines or compatibility layers.
- Explain limitations and a plausible evolution cost. When the foundations are
  sufficient, proceed with authorized implementation instead of extending design.
- User authorization persists. Do not add repeated permission gates for already
  requested work. A read-only request remains read-only.

## Acceptance rule: reduce, reuse and converge

Weaver is a consolidation of Fred, not another accumulation of standalone features.
**Do not add code as the default response to a request.** Start by asking where the
behavior belongs in what already exists, what can be extended, what it replaces
and what can disappear. Production-code reduction is a design and review objective,
not an optional cleanup after delivery.

Before implementation, identify the shared libraries, domain owners and design-system
components that can serve the use. Reuse them. Extend a shared primitive when that
is the right boundary; do not create a local helper, wrapper, service, endpoint,
store, state machine or UI control duplicating an existing mechanism. A new feature
name does not justify a new abstraction or independent implementation path.

For each increment, state the reused/extended mechanism, replaced or removed paths,
and expected effect on owned production code. If genuinely necessary behavior
cannot be expressed without additional code, explain the concrete gap and why reuse
or replacement is insufficient. An unavoidable net increase must be agreed in the
increment's scope; existing explicit authorization suffices, but novelty alone is
not an exception. Never compress code, remove useful tests/security constraints or
shift code into generated blobs to manufacture a lower line count.

Preserve simple, robust behavior while removing redundant concepts, parallel
implementations and obsolete consumers. Report production-code additions/removals
separately from tests, generated files and documentation. Raw line count supports
judgment; it does not justify less readable or less reliable software.

Contributions are welcome. A small maintaining team owns architectural decisions
and integration. UX designs express user needs; they do not independently define
persistence, authorization or service boundaries. Discuss a material design change
before building a parallel feature. Follow [CONTRIBUTING.md](CONTRIBUTING.md) so a
PR arrives with the integration, reuse and removal reasoning needed for acceptance.

## Architecture and authority

Control Plane and PostgreSQL own application identities, memberships, role grants,
placements and access-decision facts. Control Plane evaluates authorization;
SQL constraints protect structural invariants and coherent writes. Python
components call Control Plane and enforce their local resource constraints.
Knowledge Flow uses its workload identity and the authorized document scope.
S3 stores objects; search/vector indexes are projections, never another authority
for current placement or access. OpenFGA is removed. Do not reintroduce a remote
authorization engine, generic graph or duplicate permission matrix.

Preserve JWT validation, trusted delegation, the distinction between workload
and person, credential renewal/confidentiality and organization isolation.
Browser/model-supplied identifiers are requests to validate, not authority.
Keep canonical context server-bound; do not forward Fred credentials to unrelated
external tools. A workload token is not the person's permission.

Resolve trusted execution context once at turn admission. An admitted turn may
finish despite subsequent revocation, invitation expiry or user deletion; new
admissions observe the new state. Do not add per-tool/LLM authority refreshes or
new execution-grant schemes. Cancellation, terminal-state enforcement, execution
limits and resource-specific data checks remain separate. Resource checks must
not become a back door for refreshing the turn's admission authority.
Knowledge Flow validates delegated identity and obtains the authorized corpus
from Control Plane; an empty corpus never means unrestricted access. Check
attachments through their conversation boundary. Do not promise availability of
deleted data merely because a turn may finish.

Capability libraries own their configuration, validation, tools and UI packs.
Control Plane authenticates, checks admission/authorization and forwards to the
owning pod; it must not encode individual capability rules. Inspect current
registration and consumers rather than copying a historical SDK contract.

Preserve the existing business UI and its meaningful capabilities within the
accepted increment. Missing backend support is an implementation gap, not a
reason to hide a feature or invent a replacement UI. An approved business change
can change the contract; make its effect explicit rather than preserving a
retired implementation for compatibility.

## Persistence, concurrency and migrations

Apply the design targets and query/locking checklist in the reconstruction skill.
Reuse a table only when its meaning, ownership and lifecycle fit. Explain the
concrete need for a new table. Prefer ordinary PostgreSQL constraints and short
transactions; keep business policy responsibilities explicit in Control Plane.

Correctness across replicas cannot depend on process-local locks, queues, caches
or sticky routing. Use existing durable ownership, idempotency, leases and retry
mechanisms where needed. Bound work, memory, timeouts and batch sizes. Do not
hold SQL transactions across model calls, network requests or human waits.

Weaver is currently built only for fresh installations: every schema assumes an
empty initial SQL state. No upgrade from an older Weaver or from Swift is supported,
so do not write data recovery, writer drains, compatibility with older pods or upgrade
tests. Test fresh initialization only. An incompatible local database is recreated.

Weaver Control Plane uses immutable SQLx migrations from the current baseline in
`apps/control-plane/migrations/0001_schema.sql`. Once pushed, never edit a migration:
add a numbered transactional migration. Preserve constraints and reader grants.
SQLx serializes initialization and validates fingerprints. Never reset live data or
rewrite `_sqlx_migrations` checksums; recreating a shared database requires separate
authorization. API startup only verifies the schema; the initialization
command/deployment hook applies the migration chain.
Python components retain their own immutable Alembic histories. Inspect actual migration
ownership rather than assuming one framework across Fred. Never change a live
installation or reset data as an incidental validation step; inspect migration
history and arrange backup/authorization for a requested data operation.

A schema-only increment must preserve existing writes and rights, activate no
incomplete mechanism and create no divergent authority. Record obligations of
future consumers in the task/issue and relevant migration comments. If a new
constraint needs immediate application changes, explain that before editing.
For a necessary temporary transition, state its purpose, remaining adaptation
and exit condition. Do not remove a protection to enable an uncoordinated feature.

## Engineering baseline

Use [coding conventions](docs/CONVENTIONS.md) and the owning component's patterns.
Prefer small cohesive modules, typed boundaries and concise comments explaining
why. Do not hand-edit OpenAPI or generated TypeScript clients: regenerate from
the owning source when the public contract changes, including affected consumers.

For Rust, favor explicit ownership and borrowing, typed errors and normal `?`
propagation. Avoid production `unwrap`/`expect`; do not introduce `unsafe` without
an explicitly agreed need. Keep secrets and internal errors out of public replies.
Never hold synchronous locks across `.await` or block Tokio with synchronous I/O
or expensive work. Use bounded standard primitives and supervised tasks; respect
cancellation and the fact that cancelling a handle may not stop spawned work.
Reuse connection pools and parameterized SQL. Use compile-time checked SQL where
the repository's schema/metadata supports it; `FromRow` alone is not SQL validation.

For Python async paths, keep blocking I/O and expensive work off the event loop,
bound concurrency, reuse clients and route metrics through existing mechanisms.
For UI work, use shared components, design tokens, generated clients, accessibility
and both locales. Do not replace domain design with a frontend-first solution.

## Validation and reporting

Apply the repository formatter only to files changed by the increment. Before
handing back code, run `make code-quality` in each affected component or its
documented equivalent; required compilation is authorized. Fix introduced
failures and rerun affected checks after the final relevant edit. Do not weaken
checks or fix unrelated failures to obtain a pass. Report blockers honestly.
Documentation/instruction-only edits need scoped link, syntax and consistency
checks, not application compilation or runtime tests.

The developer owns functional validation. Unless requested, do not launch test,
benchmark, load, deployment or independent-review campaigns. A specialized skill
must not silently widen this scope. When tests or reviews are requested, use the
smallest meaningful scope and report what it proves and what remains unverified.
Synthetic SQL plans demonstrate a plan for that fixture, not production capacity.

Report the outcome, meaningful decisions and changes, actual commands/results,
necessary next adaptations and material limits. Do not create parallel status
files or a mandatory close-out template. Do not claim an independent review or
end-to-end validation that did not happen.

## Optional planning and external delivery

For Swift-to-Weaver integration work, read the
[merge method](docs/SWIFT_WEAVER_MERGES.md) and the
[porting status](WEAVER_SWIFT_PORTAGE_A_REPRENDRE.md). Keep newly arrived Swift
commits distinct from previously deferred behavior; record pinned references and
actual integration/validation evidence. These documents do not authorize agents,
merges, pushes or deployments by themselves.

OpenSpec is optional for an increment that needs explicit acceptance criteria or
coordination. Use it when requested or when the team agrees it is needed for the
specific increment. Ordinary discussion, fixes and implementation requests do not
automatically select it. No automatic initialization or recreation of old specs.
When selected, use the available OpenSpec CLI and corresponding skill for a small
change grounded in current decisions, schema and code. Archive only completed
work in the selected scope. Arc42 remains the current architectural explanation;
OpenSpec records that increment's change contract, not a competing architecture.

Commits, pushes, PR creation, publication, deployment and messages to others need
user authorization; an implementation request alone does not request them.
When preparing an authorized PR, use its actual target branch, stage explicit
paths, and describe the final problem, behavior and validation. Use the retained
[operator release-note workflow](deploy/release-notes/README.md); its CI checks
and the next release's historical coverage review still apply.

Use ordinary keyboard punctuation in authored repository text, preserving normal
language accents. Write GitHub titles, descriptions and commit messages in English.
