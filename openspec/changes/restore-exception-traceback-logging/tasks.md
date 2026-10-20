# Tasks

## 1. Scope and regression coverage

- [x] 1.1 Obtain scope confirmation for targeted exception-text redaction, request-boundary ownership with the same available identity as completion and exact-exception Uvicorn duplicate suppression; identify the implementation tracking issue [#3190](https://github.com/ThalesGroup/fred/issues/3190), related to #2906, and use a dedicated topic branch, verified by the confirmed scope, issue link and branch status.
- [x] 1.2 Add focused regressions through the real shared logging setup for retained exception type/message/frames/visible chains, JSON line framing and readable output with delegation off and each direction enabled; add failing request-flow coverage asserting the same available user/session/agent/team and request/correlation references on exception and completion across middleware tasks, and verify the tests fail before changing code.

## 2. Restore exception stdout

- [x] 2.1 Reuse one known-pattern URL sanitizer from both logging sites without a circular import, read `event.get("exc_info")` in `EventProcessor`, remove its delegation check and sanitize rendered exception text; verify the output regressions pass and a known credential appearing only in an exception cause is redacted while ordinary text and frames survive.
- [x] 2.2 Remove the blanket message/diagnostic-clearing branch from `UvicornSensitiveQueryFilter`, retaining only URL sanitization and leaving dependency cleanup unchanged. Add a separate minimal `AlreadyReportedExceptionFilter` using the shared `was_reported` helper, wire it to `uvicorn.error` before sanitization and replace it on repeated setup; verify record immutability, marked/unmarked exceptions, distinct exceptions with identical messages, repeated setup and dependency confinement.
- [x] 2.3 Emit uncaught exception diagnostics in `RequestLoggingMiddleware` from the same owned snapshot used by completion, mark the reported exception and re-raise it; remove the generic handler's detail-free error log while preserving its response and KPI bookkeeping. Verify the real server path yields one correlated exception ERROR and one correlated HTTP 500 completion ERROR, with no Uvicorn duplicate, including admitted identity bound in middleware child tasks.
- [x] 2.4 Verify concurrent differently scoped failures followed by another request remain independently searchable by every available identity field, without identity leakage or suppressed distinct errors. Verify handled controller-logged errors still yield the two expected events, explicit 500s do not invent traces, and response headers/CORS, KPI behavior, application OSError, cancellation, disconnect and stream outcomes retain their existing behavior.

## 3. Documentation and readiness

- [x] 3.1 Update the existing observability guide and add the required English operator migration note; verify they explain targeted redaction, restored exception messages, correlated request-boundary ownership, narrow server duplicate suppression, fixed-message/logger query changes and rollback without changing the generic-store or unrelated delegation scope.
- [x] 3.2 Run the relevant shared logging, sensitive logging, context and request-flow tests plus required root quality checks once the implementation is complete; record exact commands/results and distinguish simulated/offline behavior from any real Uvicorn and GKE validation in this task list or the PR.
- [ ] 3.3 Apply the full author branch audit and obtain independent read-only correctness and performance review for the affected logging/request paths; record base/head, coverage, findings/dispositions and exclusions in the PR or task response and verify no required fixes remain.
- [ ] 3.4 Reconcile these artifacts with the verified implementation, sync the delta and archive through the repository procedure, then push completed reviewable commits and open the required draft PR linked to the tracking issue; verify the PR diff excludes unrelated local changes and includes the final migration note and validation evidence.

## Verification evidence

- Scope confirmed in the implementation chat, including a dedicated pure duplicate filter and request-owned correlated exception logging. Branch: `codex/restore-exception-traceback-logging`; target base: `1cfde953717d661d6c9a059aa2ff492da374b27d` (`origin/swift`).
- Before implementation: the selected formatter/sanitizer/request regressions failed in all 10 cases on the original code. After implementation those 10 passed.
- Offline core logging/sensitive logging tests: 98 passed using the existing Knowledge Flow environment with `--disable-socket --allow-unix-socket`. A sandbox-only thread test stalled; rerunning the same suite with thread support outside the sandbox passed.
- Actual Knowledge Flow factory plus Uvicorn over Unix socket: 6 passed, including three failure cases (delegation off/accept/act) proving one correlated exception and one completion with no server duplicate. No live GKE or production replay performed.
- Final affected core logging/context/audit/KPI subset: 120 passed; separate generic-handler module: 21 passed; real KF/Uvicorn Unix-socket suite: 6 passed (147 targeted cases total). Changed Python files pass Ruff lint/import ordering/format checks.
- Root `make migration-check`: passed with one new declaration. Root `make code-quality`: its 28 migration-tool tests passed, then existing virtualenv bootstrap failed because ambient `python3` is 3.10 while the installed environments use Python 3.12/3.13. The failed bootstrap configuration was restored to the existing Python 3.13 runtime; no tooling or dependency files changed. Full monorepo quality is not claimed.
