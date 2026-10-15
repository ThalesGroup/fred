## 1. Manager onboarding

- [x] 1.1 Add versioned personal consent and startup/onboarding contracts; verify config validation, consent persistence, stale-version rejection and zero membership side effects with unit/integration tests.
- [x] 1.2 Gate business HTTP and authenticated CLI import on consent; preserve root-only bootstrap guarantees and verify direct bypass, service/delegation rejection and completed-root behavior.
- [x] 1.3 Regenerate OpenAPI/client and verify route/security/serialization contracts.

## 2. First UI journey

- [x] 2.1 Connect startup, consent and bootstrap screens to manager; verify failures, pending states and reload behavior with frontend tests.
- [x] 2.2 Expose provisioning and own memberships through a minimal manager entry using existing UI primitives; verify no Python calls or implicit membership.
- [x] 2.3 Extend the disposable browser test from empty state through terms/bootstrap/import/logout/member login; verify real persisted data and consent isolation.

## 3. Review and documentation

- [x] 3.1 Independently review implementation and correct findings with regression tests, then review corrections.
- [x] 3.2 Record the complete business-journey inventory and update implemented arc42 chapters/configuration, frontend and manager instructions; verify architecture checks.
- [x] 3.3 Run manager tests/integration/quality, frontend tests/build, root quality and OpenSpec validation; reconcile, sync/archive and commit locally without push.

## Review and verification evidence

Reviewed against baseline HEAD `5eb7b93cf50e60e5c87412bee50426805908c6d9` including the
working-tree implementation. Independent read-only reviewers covered Rust
admission/bootstrap/CLI and frontend contracts, version changes, errors, account
switching and browser acceptance. These are step reviews, not a new audit of all
prior experimental branch work or legacy Python features.

Findings and dispositions:
- Corrected the service-token fixture to include canonical client markers and assert
  classification; added service_agent refusal. The focused consent integration passes.
- Removed the stale bootstrap-local command and documented the actual UI entry;
  no shell command accepts terms for users. Corrections were independently re-reviewed.
- Keyed displayed CGU by active version so focus refresh reloads the legal document
  and resets reading state. The real caller regression passes; independent reviewer
  reran nine targeted UI/legal tests and accepted the correction.
- Added visible startup failure/reload and exercised it by aborting the first real
  browser configuration request. No response is fabricated. Missing legal text
  also fails closed with explicit retry and regression coverage.

Validation includes 35 Rust unit and four OpenAPI tests; 48 disposable integration
tests; real browser onboarding/import/logout/member journey; generated client,
frontend build and tests; Rust quality, architecture regeneration/check and strict
OpenSpec validation. Frontend shared-consumer mock updates are covered by their
15 passing tests. The browser fixture uses 15 imported identities, one organization,
three teams and a project, one import at a time; it is not a load or throughput test.
No k3d deployment or existing development data is modified. No push is performed.

Final checks: full frontend Vitest suite 4,347 passed / 7 skipped; frontend npm
auxiliary tests and production build passed. Root make code-quality and manager
make code-quality passed. Architecture check renders every diagram. Strict delta
and synchronized main-spec validation and migration-note validation passed.
