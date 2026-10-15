## 1. Candidate authorization

- [ ] 1.1 Bound and deduplicate the existing document READ helper; verify empty input, duplicate UIDs, denied checks, disabled ReBAC and authority failures, with at most ten active checks and no global document ListObjects call.
- [ ] 1.2 Convert the five known-candidate metadata methods named in design.md; verify the same 20-document folder with 0 and 1,001 irrelevant readable documents, multi-folder batching, missing UIDs, stable page ordering and unchanged store totals.

## 2. Complete deletion inventory

- [ ] 2.1 Obtain document-folder subtrees from canonical stored owner/type/path scope and preflight existing folder/document permissions; test same-path foreign owners, sibling prefixes, denied descendants and truncated authorization enumerations without mutation on preflight failure.
- [ ] 2.2 Process canonical memberships sequentially across folders and in existing bounded item batches, then verify no links remain before each folder removal; test multi-folder survival, parent/child membership, explicit failures, healthy last-link artifact cleanup and exactly-once quota release.
- [ ] 2.3 Verify public folder-update removal uses the corrected complete inventory; retain synchronized-folder guards and explicit failure behavior, without attempting the separate partial-revocation repair in #3121.

## 3. Validation and delivery

- [ ] 3.1 Record candidate-dependent logical permission checks, actual OpenFGA request counts and peak concurrency in focused tests; rerun #3115 search/isolation/KPI regressions and confirm no extra check cost from irrelevant documents.
- [ ] 3.2 Extend existing validation coverage for folder listing/removal; provide an explicit opt-in large-corpus campaign using disposable fixtures and store/quota postconditions. Do not seed or run a live campaign before the developer's agreed validation session.
- [ ] 3.3 Update existing integration-test/deployment guidance and add the required migration note; verify no schema/configuration change and clearly distinguish remaining #2845 scope from completed work.
- [ ] 3.4 Run affected offline suites and root make code-quality, obtain independent full-branch and performance reviews, fix and re-review actionable findings, and record actual evidence in this task file/PR.
- [ ] 3.5 Reconcile and validate the specification artifacts, sync/archive the completed change, and publish the reviewed draft PR with #2845 remaining open for explicitly deferred scope.
