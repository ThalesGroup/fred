## 1. Self-session claims

- [x] 1.1 Add bounded own-claims admin API using verified own credentials; verify unauthorized/service/delegated, bounds and real value tests.
- [x] 1.2 Regenerate OpenAPI and frontend client; verify generated types and drift.

## 2. Fred UI

- [x] 2.1 Add searchable JSON picker, observed catalog and Advanced entry; verify exact paths, array values, explicit copy and draft-only selection tests.
- [x] 2.2 Reuse shared PageError for admission feedback; verify actions, support and existing error compatibility tests.

## 3. Verification and delivery

- [x] 3.1 Validate real-account browser journeys and capture sanitized screenshots for the existing PR.
- [x] 3.2 Run root quality, targeted regression and independent branch review; resolve findings and update docs, PR and specifications.
- [x] 3.3 Commit reviewed implementation blocks and synchronize/archive the verified requirements. Final-head CI and mergeability are tracked in PR #2966 as the delivery gate.

Verification so far: 27 frontend regression tests, 36 strict signed-JWT tests, and 27 admission tests passed locally (8 unchanged PostgreSQL tests were skipped in this rerun; prior feature validation exercised the PostgreSQL fixtures). The real-account Playwright session received HTTP 200 from own-claims, selected/copy-tested a nested array in a draft, verified Enter expands a summary without confirming, and captured the observed catalog, refusal appearance and an invalid link response. No requests were mocked; no policy, membership, exception or filtering state was saved. Refusal screenshot is a visual check via direct navigation, not a new enforcement test. Personal claim values are masked in the published picker image.

Independent read-only review: base e79751028, working tree and affected unchanged consumers. Corrected summary Enter implicit confirmation and outside-router PageError navigation. No remaining supported findings; earlier full-PR review remains separate. Live production/load and independent browser execution excluded.

Performance follow-up reviewed the ordinary decoder/cache and the own-claims route: explicit verification and the whole projection run in worker threads; rejected keys consume the display traversal budget and oversized strings are rejected before serialization. A regression confirms the projection stays off the main thread. Normal principal-cache behavior and footprint are unchanged; no LLM/tool/KPI changes. Raw basedpyright: core 0 errors (2 existing unreachable warnings), control-plane 0 errors before the final worker-only change; final root code-quality passed across all modules; CI remains the final delivery check.

First full CI on 61d87a923: control-plane 1585 passed, 8 skipped, 11 deselected; only endpoint-ledger coverage failed because the new own-claims route was absent. Added its reviewed admin-plus-own-human permission row and verified the ledger test locally. Also restored role=alert on shared error messages and verified 16 affected frontend tests. Final CI will be checked after push; PostgreSQL fixture credential retrieval from Docker was rejected by automatic approval review, so no additional credentials or grants were used.

Final correction review on 61d87a923 plus the endpoint-ledger and error-announcement patch found no supported defects. The focused endpoint-ledger test passed. Final-head CI, push and PR readiness remain pending delivery checks, recorded in the existing PR rather than a second status document.
