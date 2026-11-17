# Tasks

## 1. Tracking and configuration contract

- [x] 1.1 Scope approved; issue #3537 references parent Epic #2833 and this change. Reuse fix-tabular-trace-details at the developer's explicit request.
- [x] 1.2 Distinguish omitted max_rows, explicit null and positive integers; remove the fixed row ceiling and default to 500. Add request/config tests proving omission/null survive actual HTTP and MCP calls and integers above 2000 are accepted.
- [x] 1.3 Introduce validated max_output_chars=50000, update Helm values and regenerate schemas; add configuration tests and verify chart rendering carries both deployment overrides. Add the English migration note for retired max_rows configuration and changed null semantics, declaring minor operational impact for the next paired release (ordinary feature PRs do not bump release versions).

## 2. Bounded query results

- [x] 2.1 Replace whole-result DataFrame materialization with incremental worker consumption under the existing abort lifecycle. Verify unlimited large results stop on character overflow with bounded retained memory and cancellation/timeouts remain effective.
- [x] 2.2 Budget normalized serialized JSON rows, retain the longest complete prefix, and count finite results without retaining discarded rows. Add focused service and HTTP serialization tests for exact boundaries, Unicode/escaping, null/date/decimal values, empty and aggregate results, first oversized row, unlimited requests and finite limits above 2000.
- [x] 2.3 Produce all agreed success messages in RawSQLResponse.message after rows. Verify known-total, reached-limit, combined-limit and unknown-total cases through actual HTTP/MCP output, preserving error=null and distinguishing truncation-to-zero from no matches.

## 3. Consumers and guidance

- [x] 3.1 Update controller/argument descriptions and packaged tabular guidance to document omitted=500, explicit null=unlimited and the character budget; verify advertised MCP schema, argument-presence behavior and focused inventory tests.
- [x] 3.2 Preserve tool-owned messages after result data in supported trace consumers, including zero returned rows from truncation. Add focused live/history rendering checks and regenerate affected OpenAPI/frontend clients using repository targets; verify generated changes and typechecking.

## 4. Integration and review

- [x] 4.1 Run focused concurrent query checks with large or unlimited requests, confirming execution budgets, bounded retained result memory, request isolation and no process-local cross-request correctness state; record evidence here or in the PR.
- [x] 4.2 Run relevant tabular/MCP/frontend tests and root make code-quality. Apply audit-branch against the actual target and fred-performance-reviewer, obtain independent read-only review, and record base/head, coverage, findings, dispositions and exclusions in the PR or task response.
- [x] 4.3 Reconcile artifacts and verification with the implementation, validate the change and commit reviewable blocks; verify scope and migration guidance match the final behavior. Publication follows archive below.

## Workflow follow-up

- After approval, verification and required review, sync delta specs and archive using the repository archive procedure.
- Verify the current capability spec and archived artifacts, push the commits, update existing draft PR #3528 and tracking issue #3537.


## Verification evidence

- Backend: 260 offline tests passed, 2 integration tests deselected across tabular services, serialization, execution/SQL safety, config and MCP inventory/security. Final startup/config correction: 5 tests passed (4 overlap). Frontend: 251 tests passed across four drawer/trace/tabular suites, repeated after localized empty-result handling.
- Actual mounted MCP coverage verifies omitted/null/positive limits, text and structured result equality, notices and four overlapping calls. Six guarded concurrent synthetic queries over million-row inputs retain isolated bounded previews. An observing DuckDB function verifies unlimited requests do not evaluate the entire million-row result before budgeting. These are focused regressions, not production capacity evidence.
- Backend configuration validation, chart values validation and rendered Helm overrides (700 rows / 12000 characters) passed. Generated backend/chart schemas and frontend API descriptions were regenerated from source. Static API generation used the normal configuration with temporary writable storage paths and in-memory vectors; no generated endpoint removals remain. Migration check and OpenSpec validation passed.
- Review: actual PR target swift; merge base 743a0666bfd993a6d442bd50e6f6ae89e18741ce. Independent full-branch/working-tree correctness and performance review at 2f33d2f2645d1a42fddb697ccb45124b356dca67 found eager unlimited materialization and conflicting zero-row instructions. Both were fixed and re-reviewed. Subsequent reviews covered the invocation-local MCP null workaround, localization and startup summary; no remaining findings. Implementation commits: 8a27f6124 and af88a131d.
- Exclusions: full monorepo test suite, production-scale load campaign and fresh browser/mobile/accessibility/OS clipboard verification. Existing engine guards still govern expensive SQL and very large scalar values. Sandbox HTTP tests stalled on thread/event-loop wakeups; their processes were stopped, and the offline scope completed outside the sandbox. No new distributed correctness state, clients, model calls or KPI labels were introduced.

- Final root `make code-quality` passed across all 17 modules (exit 0); Knowledge Flow basedpyright: 0 errors, 0 warnings, 0 notes. Frontend ends with `All frontend code quality checks completed`. Backend/chart schema drift comparisons and `git diff --check` passed.
