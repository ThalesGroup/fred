## 1. Generated contract and client

- [x] 1.1 Derive schemas and register existing routes with offline OpenAPI generation; verify route inventory, serialization edge cases, security and multipart/status contracts in Rust tests.
- [x] 1.2 Add equivalent Make generation targets, generated RTK slice and Redux registration; verify deterministic regeneration, transport tests and frontend typecheck.
- [x] 1.3 Independently review the contract/client diff and fix findings with regressions; run manager test, test-integration and code-quality plus architecture check, update arc42 and commit this complete step locally.

## 2. Provisioning UI and browser acceptance

- [ ] 2.1 Integrate manager-authorized navigation, ZIP form, pending/completed/error states and proxy routing; verify guard, report, replay and error behavior with frontend tests.
- [ ] 2.2 Automate the browser journey with the Make ZIP and disposable real dependencies; verify persisted hierarchy/roles, replay, access refusals and legacy ZIP feedback via one repeatable command.
- [ ] 2.3 Obtain independent review and re-review regression corrections, perform the final arc42 documentation pass, run required manager/frontend/architecture checks, reconcile and archive OpenSpec, then commit locally without pushing.

Step 1 review: independent contract review against b29d2797e plus the working diff; three findings (401 replay, optional body typing, missing 404) corrected with regressions and re-reviewed. Verification: 34 unit, 4 OpenAPI, 47 integration, 8 frontend tests; TypeScript, ESLint, manager code-quality and architecture checks pass. Repeated Make generation is byte-identical. UI/proxy/browser acceptance is outside this review.
