## 1. Complete role foundation

- [x] 1.1 Add all platform/space roles and typed capabilities, preserving stored tuple names; verify an exhaustive positive/negative matrix against real OpenFGA and DSL/JSON parity.
- [x] 1.2 Extend space role parsing, listing and grant/revoke for analyst; verify parent/child and personal-space invariants, cumulative grants, no implicit member fallback, last-admin protection and concurrent revocations with `// Proves: I<n>` annotations.
- [x] 1.3 Add service-account configuration, the Keycloak directory lookup client and factory identities/secret wiring; validate config and factory rendering, and verify unknown identities, directory outages and secret-safe diagnostics with an HTTP fixture.
- [x] 1.4 Add direct platform-role list/grant/revoke and effective `/me` reporting, sharing the platform lock with bootstrap; verify target existence before grants, stale-grant removal, root-only admin changes, root protection, absent direct grant errors and authorization-after-lock races.
- [x] 1.5 Add authenticated self capability checks, delegated team creation and metadata-only registry listing; verify team-manager/feature-manager boundaries, no caller role side effects, and denial of project/content/governance escalation.
- [x] 1.6 Run author review and independent review of the complete role delta; fix every actionable finding with a regression test, then obtain review of the corrections and record dispositions in the task response.
- [x] 1.7 After review, update applicable arc42 chapters and component usage docs with implemented behavior only; regenerate blocks, then run all three manager Make checks and the architecture check. Commit this complete role step on chore/rust-rebac without pushing.

## 2. Authenticated provisioning import

- [x] 2.1 Implement the validated bundle parser and CLI/token-file contract; verify all role aliases, per-entry team fallback, duplicate/unknown fields, malformed inputs, and secret-safe diagnostics with offline tests.
- [x] 2.2 Extend the shared Keycloak client with identity creation; verify exact/paginated lookup, preserved existing identity, missing password preflight, create conflicts, expired service tokens, timeouts and sanitized failures using an HTTP fixture.
- [x] 2.3 Validate the import configuration against the factory's existing identity declaration and app manifest rendering; verify user/service credentials remain distinct in configuration tests.
- [x] 2.4 Implement read-only initialization and complete authorization/preflight before mutations; verify invalid/missing/expired bearers, disabled auth, wrong identity mapping, non-admin callers and non-root admin-grant attempts produce zero writes.
- [x] 2.5 Implement additive organization/team reconciliation and direct role grants with shared locks and bounded FGA batches; verify name reuse/collisions, parent-before-child grants, admin-only team content denial, preserved undeclared grants and stable replay IDs.
- [x] 2.6 Exercise partial failure and cancellation at each cross-system boundary plus concurrent import/revocation and username/name creation; use real SQL/FGA and controlled HTTP barriers, with invariant annotations and replay assertions.
- [x] 2.7 Add a disposable Keycloak integration scenario using fred-manager's own service account; verify real identity creation/lookup and every role in a representative imported bundle, without modifying shared realm state.
- [x] 2.8 Run author and independent reviews over the entire import delta and affected role consumers; correct every actionable finding with a regression test and have the correction delta reviewed.
- [x] 2.9 After review, update README/CLI help and applicable arc42 chapters in present tense; document actual factory setup, authentication, role mapping, error/replay behavior and initialization prerequisites, regenerate derived blocks and review the final documentation.
- [x] 2.10 Run `make test`, `make test-integration`, `make code-quality` in apps/fred-manager and `make -C docs/architecture check`; record actual evidence, then commit the complete import step without pushing.

## 3. Close out the coherent change

- [x] 3.1 Reconcile requirements and tasks against the implemented behavior and review evidence; sync and archive through the repository OpenSpec procedure, validating the resulting spec and keeping the dossier free of plans/status.

## Review and verification evidence

Role foundation: independent read-only review of baseline `624f6e5` through the
step-1 working tree covers role parity, governance routes, locking, directory
configuration and client, deployment, tests and final arc42 documentation. Identity
mapping, audit stream/timing, URL normalization and concurrent audit-test precision
findings are corrected with regressions and re-reviewed. Final docs corrections
clarify capabilities versus operations and repair Markdown table continuity.
Verification: 29 unit tests, 20 real Postgres/OpenFGA integration tests, manager
code-quality and architecture check pass. Factory identity check and app lint/render
pass. Review is scoped to this manager step; unrelated branch changes and Python/UI
implementation are excluded. No push.

Import step: independent read-only reviews against `17e4931b2` cover the parser,
CLI initialization, identity client, reconciliation, concurrency/failure tests,
Make usage and final README/arc42 pass. Corrected findings: repeated role keys,
empty-email fallback, preflight lock duration, FGA-state and cancellation proof
precision, early-error counts, and the exposed SQLx logging-probe interaction.
Regressions reproduce each runtime defect; corrections and final documentation
are re-reviewed with no remaining actionable findings. The audit threshold test
uses the same global-filter composition as production.

Final verification: `make test` passes 32 unit tests; `make test-integration`
passes 34 tests against disposable Postgres/OpenFGA and real Keycloak, including
all roles, concurrent imports/revocations, cancellation, every FGA write boundary,
SQL commit failure and additive replay. `make code-quality` and
`make -C docs/architecture check` pass. The subsequent test-only audit-filter
alignment passes its targeted test and code-quality. CLI `--help` is verified.
Factory identity declaration and rendered service credentials are unchanged from
step 1's successful factory checks. Source migrations are unchanged. OpenSpec
requirements are preserved and synced before archival. No push.

Review scope is the two manager implementation steps and their affected callers,
configuration, deployment and docs, not an audit of unrelated branch changes or
Fred's entire architecture. Runtime evidence uses isolated test infrastructure;
no shared realm is modified.
