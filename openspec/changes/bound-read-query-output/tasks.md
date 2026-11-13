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
- [ ] 4.2 Run relevant tabular/MCP/frontend tests and root make code-quality. Apply audit-branch against the actual target and fred-performance-reviewer, obtain independent read-only review, and record base/head, coverage, findings, dispositions and exclusions in the PR or task response.
- [ ] 4.3 Reconcile the artifacts with the implementation, validate the change, commit reviewable blocks and push a draft PR referencing the tracking issue; verify scope and migration guidance match the final behavior.

## Workflow follow-up

- After approval, verification and required review, sync delta specs and archive using the repository archive procedure.
- Verify the current capability spec and archived artifacts, and update the tracking issue.
