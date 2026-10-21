## 1. Generated contract and client

- [x] 1.1 Derive schemas and register existing routes with offline OpenAPI generation; verify route inventory, serialization edge cases, security and multipart/status contracts in Rust tests.
- [x] 1.2 Add equivalent Make generation targets, generated RTK slice and Redux registration; verify deterministic regeneration, transport tests and frontend typecheck.
- [x] 1.3 Independently review the contract/client diff and fix findings with regressions; run manager test, test-integration and code-quality plus architecture check, update arc42 and commit this complete step locally.

## 2. Provisioning UI and browser acceptance

- [x] 2.1 Integrate manager-authorized navigation, ZIP form, pending/completed/error states and proxy routing; verify guard, report, replay and error behavior with frontend tests.
- [x] 2.2 Automate the browser journey with the Make ZIP and disposable real dependencies; verify persisted hierarchy/roles, replay, access refusals and legacy ZIP feedback via one repeatable command.
- [x] 2.3 Obtain independent review and re-review regression corrections, perform the final arc42 documentation pass, run required manager/frontend/architecture checks, reconcile and archive OpenSpec, then commit locally without pushing.

Step 1 review: independent contract review against b29d2797e plus the working diff; three findings (401 replay, optional body typing, missing 404) corrected with regressions and re-reviewed. Verification: 34 unit, 4 OpenAPI, 47 integration, 8 frontend tests; TypeScript, ESLint, manager code-quality and architecture checks pass. Repeated Make generation is byte-identical. UI/proxy/browser acceptance is outside this review.

Step 2 review: independent read-only UI/contract review against ee0daf1b5 plus the working diff, followed by final documentation/proxy delta review; no actionable findings. Coverage includes navigation, manager authority, multipart/result state, existing shell/Migration consumers, browser fixture isolation, screenshots and proxy routing. Verification: 34 Rust unit tests, 4 OpenAPI tests, 47 integration tests and one real browser journey; 4,184 frontend tests pass (7 skipped), with typecheck, ESLint, formatting, production build, manager code-quality and architecture checks passing. The nginx container smoke test uses the current entrypoint with existing runtime image assets; current UI assets are built separately. The browser isolates control-plane shell reads and knowledge-flow task reads; admission policies, Temporal, dark-theme/screen-reader acceptance and historical branch changes are outside this lot review.
