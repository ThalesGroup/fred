## 1. Resource read contract

- [x] 1.1 Validate folder filters after space authorization, expose existing reads without Temporal, and regenerate OpenAPI/client; verify API regressions for roots, folders, cursors, revoked/governance-only access and cross-space filters, including measured FGA requests.

## 2. Existing UI journey

- [x] 2.1 Wire scoped Resources navigation and read-only explorer through generated DTOs/hooks; verify route, state, breadcrumb, cursor pagination, failure/retry and stale-response regressions.
- [x] 2.2 Extend the disposable real browser journey for Priya's personal space and fredlab with seeded folders/documents, pagination and empty/denied/error states; assert zero Python-service requests.

## 3. Review and close-out

- [x] 3.1 Run independent branch review, fix actionable findings with regression coverage and obtain correction review; record base/head, scope and dispositions here.
- [x] 3.2 Perform the dedicated arc42 documentation pass after review, regenerate derived blocks and pass the architecture check.
- [x] 3.3 Pass manager test, test-integration and code-quality, root code-quality, frontend focused tests and OpenSpec validation; sync/archive the change and create one local commit without pushing.

## Review evidence

Lot base/head: `068d434967c74c00c6023019f18a48965d2d867f` plus this working-tree delta.
Actual branch target: `origin/swift` at `d8aa32f752bd8376a643482cb00c8bd02e00d058`;
merge base `e44837560a2b45df2e23802cd8c067097d5cf00d`. Both independent reviewers
inventoried the 222-file committed branch and reviewed the affected foundation and
lot; this is not a new full-PR approval of unrelated historical changes.

- Backend coverage: API, scoped SQL filters, admission, organization resolution,
  FGA model/reads, generated contract and disposable fixtures. Finding: independent
  placement Reads serialized each resource request. Fixed with bounded concurrency,
  preserving per-project dependencies and RPC counts. A 40-team regression passes;
  independent correction review found no remaining issue.
- Frontend coverage: route/sidebar reachability, generated DTOs, explorer/pagination,
  cache and effect races, shared consumers and admission/logout dependencies.
  Finding: pending requests could satisfy a later entry without new authorization.
  Fixed with cancellation, per-entry request-ID/readiness checks and a retained
  StrictMode revocation regression. ES2021 typing errors corrected. Independent
  correction review found no remaining issue; all four resource state tests pass.
- Exclusions: unrelated branch mutation/import/deployment review, full authentication
  audit and representative production load testing. Browser/visual acceptance and
  the dedicated documentation pass are recorded below.

## Verification

- Manager offline tests: 36 unit and 5 OpenAPI tests passed.
- Manager full integration: 72 passed against disposable Postgres/OpenFGA/Keycloak;
  includes the shared context resolver's concurrency, ambiguity and mutation fences.
- Real browser journey passed (100.63 s); the command also passed all 72 integration
  cases. No Python-service request or browser application error. Desktop personal/team
  and 390 px team screenshots inspected; controls and layout remain usable.
- Frontend: 58 focused tests passed across routing, scoped navigation, resource
  lifecycle/races, shared explorer/table and generated client. Typecheck passed.
- OpenAPI/client regenerated with no generated TypeScript diff (shapes unchanged).
- Dedicated arc42 pass completed after correction reviews; generated blocks updated,
  architecture check and all Mermaid renders passed. OpenSpec strict validation passed.
- Manager code-quality (Clippy, Rustfmt, model consistency) and root code-quality
  passed. The initial cold root run received SIGTERM at frontend; a complete warm
  rerun exited 0. Migration declarations and git diff whitespace checks passed.
- Delta requirements synchronized and verified against the current spec; close-out
  archives this change in the same local commit. No push is part of this lot.
