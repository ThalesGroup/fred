---
name: audit-control-plane
description: Review requested Weaver Control Plane responsibilities against agreed business invariants, PostgreSQL schema, transactions, authorization, actual consumers and arc42. Read-only and bounded to the requested increment; not an automatic whole-platform audit.
---

# Review Control Plane foundations and behavior

Follow `AGENTS.md`, `fred-reconstruction-method` and the read-only
[branch review procedure](../audit-branch/SKILL.md). Establish the actual checkout,
HEAD, comparison base and local changes. Honor the requested responsibility or
increment; review all manager responsibilities only if that breadth was requested.
Do not edit, commit, push or post externally as part of this review.

## Establish what should hold

Start with the business use, accepted decisions, rights and lifecycle. Read the
relevant arc42 chapters and generated schema references. Inspect SQL migrations,
constraints, indexes and transactions before tracing application usages, routes
and UI. Use `apps/control-plane/src/README.md` to locate owners, not as a frozen
inventory of completed features. Historical behavior is comparison evidence only
when needed; do not restore it over an approved Weaver decision.

Distinguish currently used behavior, schema preparation, agreed but unimplemented
features and historical Swift behavior. A target gap outside the increment is not
an implementation defect. A broken or insecure exposed path inside it is.
Record genuinely unresolved business questions instead of choosing new semantics.

For each relevant invariant, identify SQL enforcement, transaction coordination,
authorization and external projection synchronization. Verify real readers and
writers, including CLI/worker entry points and affected generated clients. A table,
`// Proves:` marker or generated reference alone does not establish a guarantee.

## Challenge the implementation

- Ownership, identity, uniqueness, cardinality, nullability, placement and foreign
  keys match the business meaning; one authoritative owner exists for each fact.
- Permanent and temporary rights remain independent; invitation provenance and
  expiry do not silently create global membership or inferior functional roles.
- Turn admission and resource-data checks respect their distinct lifetime rules.
- Quota reservation, publication, reprocessing, moves, deletion and purge have
  explicit transaction boundaries, lock ordering, idempotency and retry behavior.
- Actual queries have usable indexes, bounded batches/pagination and realistic
  selectivity. Check purge/FK paths as well as live-row reads and global counters.
- No process-local mechanism claims cross-replica correctness. No transaction
  stays open across remote calls, LLM work or human waits.
- Shared libraries and existing domain mechanisms are reused. Flag parallel
  implementations, unneeded abstractions, duplicate policy and abandoned old paths.
- UI changes reuse shared controls and generated clients without hiding a missing
  backend contract. The business model was not reverse-engineered from a screen.

Use the reconstruction skill's scale targets as design constraints, not measured
capacity. Identify actual fixture sizes and concurrency in any available evidence.
Do not infer capacity from one query plan or a successful local demo.

## Evidence and outcome

Trace concrete triggers and affected consumers. Separate confirmed defects,
code/arc42 discrepancies, open business decisions and verification gaps. Explain
impact and the smallest correction, including deletion or reuse opportunities.
Use existing proof only when its revision and coverage apply. Respect the user's
validation scope; do not start database/load/browser campaigns implicitly.

Independent review uses a separate reviewer only when requested or authorized for
this review. Provide raw requirements, scope, revisions and evidence, not expected
findings. Do not recursively delegate. State when review was not independent.

Report in the task or existing PR: scope, findings with locations and evidence,
verification actually performed, exclusions and limits. Do not create another
standing audit document or claim full readiness from a bounded review. Corrections
remain a separate authorized action.
