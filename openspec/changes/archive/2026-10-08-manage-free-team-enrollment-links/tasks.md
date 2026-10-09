## 1. Invitation lifecycle

- [x] 1.1 Implement independent link model with aggregate counters, ownership and the single pending migration; verify migration head, schema correspondence and data-preserving local draft reconciliation.
- [x] 1.2 Add bounded administration, recoverable own-admin URLs, independent revocation, optional note/expiry and Free suspension; verify focused backend tests for bounds, guards and lifecycle.
- [x] 1.3 Add own-credential opening recording and retain live preview/legal/enrollment checks; verify duplicate frontend effects and concurrent opening increments, expiry/revocation, same-token membership withdrawal and PostgreSQL races.

## 2. Administration and delivery

- [x] 2.1 Regenerate OpenAPI/RTK Query and implement the localized shared-control link manager and enrollment recording; verify focused UI regressions and real-account no-mock browser scenarios.
- [x] 2.2 Reconcile existing product/UX/operator docs, obtain independent authorization review, resolve findings and run root quality; record base/head, evidence and limitations.
- [x] 2.3 Synchronize verified OpenSpec behavior, prepare archive, commit separately from filter UI, and update the existing PR with safe screenshots; verify strict specs, independent review, implementation CI and conflict-free mergeability. Track final post-closeout readiness in the PR.

Verification: implementation head `4983ffc1d` integrates Swift `05a773919`; root quality passed after the merge. Full and focused independent read-only reviews were completed and supported findings resolved. Exact test counts, real-account browser scenarios, review coverage and exclusions are recorded in PR #2966.

Implementation CI: all 140 checks passed on `4983ffc1d`. Separate asynchronous-test annotation corrections passed Ruff and both affected tests, including PostgreSQL. Final pushed-head checks and review-thread disposition remain in PR #2966.
