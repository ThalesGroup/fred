## 1. Complete role foundation

- [ ] 1.1 Add all platform/space roles and typed capabilities, preserving stored tuple names; verify an exhaustive positive/negative matrix against real OpenFGA and DSL/JSON parity.
- [ ] 1.2 Extend space role parsing, listing and grant/revoke for analyst; verify parent/child and personal-space invariants, cumulative grants, no implicit member fallback, last-admin protection and concurrent revocations with `// Proves: I<n>` annotations.
- [ ] 1.3 Add service-account configuration, the Keycloak directory lookup client and factory identities/secret wiring; validate config and factory rendering, and verify unknown identities, directory outages and secret-safe diagnostics with an HTTP fixture.
- [ ] 1.4 Add direct platform-role list/grant/revoke and effective `/me` reporting, sharing the platform lock with bootstrap; verify target existence before grants, stale-grant removal, root-only admin changes, root protection, absent direct grant errors and authorization-after-lock races.
- [ ] 1.5 Add authenticated self capability checks, delegated team creation and metadata-only registry listing; verify team-manager/feature-manager boundaries, no caller role side effects, and denial of project/content/governance escalation.
- [ ] 1.6 Run author review and independent review of the complete role delta; fix every actionable finding with a regression test, then obtain review of the corrections and record dispositions in the task response.
- [ ] 1.7 After review, update applicable arc42 chapters and component usage docs with implemented behavior only; regenerate blocks, then run all three manager Make checks and the architecture check. Commit this complete role step on chore/rust-rebac without pushing.

## 2. Authenticated provisioning import

- [ ] 2.1 Implement the validated bundle parser and CLI/token-file contract; verify all role aliases, per-entry team fallback, duplicate/unknown fields, malformed inputs, and secret-safe diagnostics with offline tests.
- [ ] 2.2 Extend the shared Keycloak client with identity creation; verify exact/paginated lookup, preserved existing identity, missing password preflight, create conflicts, expired service tokens, timeouts and sanitized failures using an HTTP fixture.
- [ ] 2.3 Validate the import configuration against the factory's existing identity declaration and app manifest rendering; verify user/service credentials remain distinct in configuration tests.
- [ ] 2.4 Implement read-only initialization and complete authorization/preflight before mutations; verify invalid/missing/expired bearers, disabled auth, wrong identity mapping, non-admin callers and non-root admin-grant attempts produce zero writes.
- [ ] 2.5 Implement additive organization/team reconciliation and direct role grants with shared locks and bounded FGA batches; verify name reuse/collisions, parent-before-child grants, admin-only team content denial, preserved undeclared grants and stable replay IDs.
- [ ] 2.6 Exercise partial failure and cancellation at each cross-system boundary plus concurrent import/revocation and username/name creation; use real SQL/FGA and controlled HTTP barriers, with invariant annotations and replay assertions.
- [ ] 2.7 Add a disposable Keycloak integration scenario using fred-manager's own service account; verify real identity creation/lookup and every role in a representative imported bundle, without modifying shared realm state.
- [ ] 2.8 Run author and independent reviews over the entire import delta and affected role consumers; correct every actionable finding with a regression test and have the correction delta reviewed.
- [ ] 2.9 After review, update README/CLI help and applicable arc42 chapters in present tense; document actual factory setup, authentication, role mapping, error/replay behavior and initialization prerequisites, regenerate derived blocks and review the final documentation.
- [ ] 2.10 Run `make test`, `make test-integration`, `make code-quality` in apps/fred-manager and `make -C docs/architecture check`; record actual evidence, then commit the complete import step without pushing.

## 3. Close out the coherent change

- [ ] 3.1 Reconcile requirements and tasks against the implemented behavior and review evidence; sync and archive through the repository OpenSpec procedure, validating the resulting spec and keeping the dossier free of plans/status.
