---
name: audit-control-plane
description: Independently audit the implemented Rust control-plane reconstruction against arc42, existing Fred behavior and affected UI/security contracts. Use for a PoC or weaver audit, not a whole-Fred review or a demand to implement future migration slices.
---

# Audit the control-plane reconstruction

Use the read-only [branch review procedure](../audit-branch/SKILL.md) with the
bounded scope below. The objective is a robust, simple Rust replacement for
control-plane and selected knowledge-flow APIs, delivered feature by feature,
with the existing Fred UI, security guarantees and overall architecture preserved
except for explicitly approved reconstruction decisions.

For Dimi's reconstruction, the companion
[reconstruction method](../fred-reconstruction-method/SKILL.md) defines the agreed
scope and canonical corpus. Historical RFC/OpenSpec content is evidence to reconcile,
not a competing active authority. The read-only audit reports consolidation needs;
it does not execute document deletion or corrections.

## Scope and independence

Read root `AGENTS.md`, applicable legacy guidance and nested instructions first.
Locate the user's Rust checkout through Git; do not assume the current checkout is
`weaver`, switch branches or audit the Python checkout by accident.
Record branch, HEAD, actual comparison base/merge-base and local changes.

By default, audit **all currently implemented manager responsibilities**, including
code unchanged by the last commit. Use the branch diff for orientation and regression
history, not as the boundary of a last-lot-only review. A user-requested narrower
scope overrides this default and must be named in the report.

- Primary scope: `apps/control-plane/` Rust code, SQL migrations, OpenFGA model,
  configuration, CLI/API/worker entry points, tests and deployment tooling; the
  applicable current explanations in `docs/architecture/`.
- Follow generated frontend clients, reachable UI consumers and shared deployment
  or library boundaries only where they exercise a manager contract. Preserving
  the UI includes navigation, errors, pending/empty states, identity changes and
  visible permissions. New endpoint wiring need not preserve old backend internals.
- Read the corresponding control-plane/knowledge-flow Python paths as behavior
  evidence for a feature under review. Do not audit unrelated Python changes merged
  from swift, all shared libraries, all frontend pages or the whole Fred platform.
- A future feature outside the accepted/implemented slice is not an audit defect.
  An incomplete, insecure or broken path already exposed within that slice is.
  Check callable routes, CLI commands and worker handlers, not just visible UI.

When orchestrating the audit for the implementation author, delegate it to a separate
assistant with fresh context when available. Give it this skill, the checkout,
requested scope, base/head and raw evidence, not the author's conclusions or expected
findings. The reviewer can inspect earlier review dispositions after its own first
pass. When already acting as that independent reviewer, execute directly; do not
recursively delegate merely to claim independence. Split a large scope by coherent
responsibility only when useful, then reconcile coverage and cross-boundary findings.
If a separate reviewer is unavailable, state that limitation.

Review without editing source/docs/specs, committing, pushing or posting externally.
Focused reproduction may use disposable services and temporary artifacts; never
mutate the user's running installation. Do not implement fixes as part of the audit.

## Establish the contract before judging it

Read the [arc42 entry point](../../../docs/architecture/README.md),
[user journeys](../../../docs/architecture/02.1-user-journeys.md),
[security](../../../docs/architecture/03-security.md),
[action/role matrix](../../../docs/architecture/A7-action-role-matrix.md),
[quality invariants](../../../docs/architecture/09-quality.md), and the relevant
domain chapters and A1/A2/A3 manager references. Use the
[reconstruction checklist](../../../docs/swift/design/FRED-RECONSTRUCTION-CHECKLIST.md)
to identify prerequisites of implemented features, not to demand the entire product.

Build a compact coverage map from observed entry points: journey/responsibility,
Rust path, affected consumer or Python reference, arc42 contract, verification and
unreviewed boundary. Derive the feature inventory from the current checkout; do not
freeze it to an old list of completed lots. Empty arc42 headings make no claim.

Review editorial fitness as well as factual accuracy. A system overview must explain
the system's purpose, actors, boundary and principal responsibilities; a correct
local deployment inventory does not satisfy it. Apply the companion method's
section-approval rule: unagreed sections stay empty. Flag a missing explanation
without generating replacement prose or treating filler as completion. Separate
user journeys, data models, operations and design decisions instead of mixing them.

Check agreement in both directions: documented guarantees must hold in code, and
implemented behavior/limitations must be explained in the relevant arc42 chapter.
Inspect generated references and the tests behind invariant markers; a generated
table or a `// Proves:` comment alone is not evidence that the guarantee holds.

For each reconstructed feature, compare role scopes, admission, ownership, normal
behavior and failure semantics with its Python counterpart and actual UI consumer.
Keep canonical grants and permission evaluation in OpenFGA, as required by AGENTS.
Distinguish an explicitly approved model change from an accidental regression.
A difference listed in documentation is not automatically an approved decision.
Do not silently restore Python behavior over an approved Rust decision, copy a
known Python weakness, weaken isolation for compatibility, or propose a UI redesign.
When approval evidence is absent or current sources conflict, report the concrete
contract question and its consequence instead of inventing the intended semantics.

Arc42 is the cross-capability account to verify; relevant current OpenSpec capability
specs are acceptance contracts. Active changes describe intended deltas, not shipped
behavior. Consult RFCs/archives only for targeted decision history. Neither source
code, tests nor prose wins a disagreement simply by existing: identify whether the
implementation, documentation or decision evidence needs correction.

## Review implementation quality and robustness

Trace each accepted journey through its real consumers, authority checks, effects
and observable result. Challenge invariants with realistic alternate actors,
failures, restarts and concurrency, using the generic review procedure's evidence
standard. In particular examine:

- Rust boundaries and simplicity: cohesive ownership of validation and effects,
  idiomatic error/option handling, typed configuration and public contracts,
  reachable panic paths, duplicated policy, unnecessary state/abstractions and
  compatibility branches. Recommend simplification for a demonstrated maintenance
  or correctness benefit, not personal style or speculative future extensibility.
- Security composition: authentication and admission, current authorization,
  organization isolation, inherited/direct roles and content versus administration,
  revoked/retired targets, credentials and structured audit/logging conventions.
- Persistence and async work: transaction/lock ordering and duration, partial remote
  effects, idempotency, ambiguous acknowledgments, cancellation, timeouts, retries,
  durable progress, startup/upgrade compatibility and safe shutdown. Review the
  actual dependency API/SDK semantics when an invariant relies on them.
- Cost: exact OpenFGA request types, filters, count, pagination, tuple volume and
  dependency order; SQL lock boundaries; cardinalities driving growth. Separate
  client RPC counts from server evaluation work. Report measured fixture sizes and
  concurrency; neither one Check nor a passing demo establishes scalability.
- Contracts and operations: Rust/OpenAPI/generated-client agreement, real UI wiring,
  configuration defaults and validation, migration compatibility, worker registration,
  deployment/reset/rollback consumers and truthful readiness/progress behavior.

Use specialist review skills where materially relevant and available, without
expanding this scope. Reuse existing verification evidence only when its revision
and coverage apply. Run focused checks to resolve uncertainty; report exactly what
ran and what remains unverified. For a complete manager verification campaign use
its documented Make targets, the arc42 check and relevant worker/browser suites.
A required monorepo quality command is verification infrastructure, not permission
to broaden the code audit to every Fred component.

## Deliver an actionable, bounded report

Use the user's language. Report the coverage map and prioritized findings with
file/line, concrete trigger, violated contract or invariant, impact, minimal
correction direction and a regression scenario. Separate confirmed code defects,
code/arc42 discrepancies, unresolved decision questions and verification gaps.
Record approved differences without presenting them as bugs. State exclusions and
verification limits; say "no findings in the reviewed scope", never "perfect" or
"bug-free". Do not infer full branch/PR readiness from this scoped audit.

Arc42 convergence is also an audit outcome: identify obsolete or duplicated guidance
encountered in scope and its verified replacement section, preserving any unique
unresolved decision or historical value. Recommend bounded consolidation candidates;
do not scan or delete thousands of RFCs/OpenSpec records, replace capability specs
with prose, or create another permanent audit/status document by default.

Return findings to the author for disposition. Corrections require regression
verification and independent re-review under AGENTS; those are a subsequent task.
