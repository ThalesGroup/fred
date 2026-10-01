## 1. Remove the built-in integration

- [x] 1.1 Remove the team navigation entry and built-in evaluator views; verify remaining section access and legacy URL fallback with navigation and TeamSettingsPage tests.
- [x] 1.2 Remove evaluator Activity polling, task rehydration/SSE routing, dedicated client/store registration and generation target; verify Activity regressions and absence of imports/references to the deleted slice.
- [x] 1.3 Remove unused evaluator translations/support files and retain shared exports; verify type-check/build and shared UI package tests.

## 2. Verify and close out

- [x] 2.1 Update COMPONENT-UX.md and update the existing PR migration note for the operator impact explaining external application registration; validate with migration-check.
- [x] 2.2 Run root code-quality, relevant frontend/hosting/package tests and an independent review; record results and distinguish existing failures from regressions.
- [x] 2.3 Reconcile the hosting and package specifications and record review evidence; verify OpenSpec validation.

Close-out uses the existing PR #2890 with a dedicated removal commit and #2904; archive the verified change, push and update the PR after validation.

## Verification evidence

- User approved the removal scope and reuse of #2890 on 2026-10-01.
- Focused navigation, Activity, task and hosting suite: 270 passed before adding the rehydration regression test; full run includes the new test.
- Frontend full suite: 3,165 passed, 7 skipped, 4 existing `useChatSse` failures (`Invalid runtime execution URL`). Same four failures verified on untouched baseline during the preceding dropdown fix. No new failures. Application proxy tests also pass.
- `npm run build` in apps/frontend passes. Shared frontend package producer: 379 tests pass.
- `make migration-check` passes. Existing interaction note gained its required Prerequisites section.
- Independent review of routing, task lifecycle, SDK preservation and final docs found no remaining actionable issue; stale TaskTray copy and integration references were corrected.
- Root `UV_NO_SYNC=true make code-quality` passes across all modules.
- Hosting and shared-package requirements synced; `openspec validate --specs`: 9 specifications pass.
