## 1. Candidate authorization

- [x] 1.1 Bound and deduplicate the existing document READ helper; verify empty input, duplicate UIDs, denied checks, disabled ReBAC and authority failures, with at most ten active checks and no global document ListObjects call.
- [x] 1.2 Convert the five known-candidate metadata methods named in design.md; verify the same 20-document folder with 0 and 1,001 irrelevant readable documents, multi-folder batching, missing UIDs, stable page ordering and unchanged store totals.

## 2. Complete deletion inventory

- [x] 2.1 Obtain document-folder subtrees from canonical stored owner/type/path scope and preflight existing folder/document permissions; test same-path foreign owners, sibling prefixes, denied descendants and truncated authorization enumerations without mutation on preflight failure.
- [x] 2.2 Process canonical memberships sequentially across folders and in existing bounded item batches, then verify no links remain before each folder removal; test multi-folder survival, parent/child membership, explicit failures, healthy last-link artifact cleanup and exactly-once quota release.
- [x] 2.3 Verify public folder-update removal uses the corrected complete inventory; retain synchronized-folder guards and explicit failure behavior, without attempting the separate partial-revocation repair in #3121.

## 3. Validation and delivery

- [x] 3.1 Record candidate-dependent logical permission checks, actual OpenFGA request counts and peak concurrency in focused tests; rerun #3115 search/isolation/KPI regressions and confirm no extra check cost from irrelevant documents.
- [x] 3.2 Extend existing validation coverage for folder listing/removal; provide an explicit opt-in large-corpus campaign using disposable fixtures and store/quota postconditions. Do not seed or run a live campaign before the developer's agreed validation session.
- [x] 3.3 Update existing integration-test/deployment guidance and add the required migration note; verify no schema/configuration change and clearly distinguish remaining #2845 scope from completed work.
- [x] 3.4 Run affected offline suites and root make code-quality, obtain independent full-branch and performance reviews, fix and re-review actionable findings, and record actual evidence in this task file/PR.
- [x] 3.5 Reconcile and validate the specification artifacts, sync/archive the completed change, and publish the reviewed draft PR with #2845 remaining open for explicitly deferred scope.

## Verification evidence

- Base: swift `90ba6ba9f`; product and harness reviewed as working-tree changes now committed in `e7e613366` and `e33eedfa1`. Author review traced the five read consumers, folder detail/update/delete, canonical SQL subtree scope, search reuse, public validation APIs and docs.
- Independent backend/performance review: bounded folder preflight finding fixed with ten concurrent checks; correction re-reviewed. Independent validation/doc review: migration headings fixed and re-reviewed. A subsequent quota test-evidence finding was corrected by exercising the real resolver; re-review accepted it. No outstanding actionable findings in the reviewed scope.
- Knowledge Flow offline suite: 1,517 passed, 45 integration tests deselected. Final focused checks: 38 passed; after exercising the real ownership resolver, all 23 inventory tests passed. Existing search/isolation/KPI regressions included in the full suite.
- Validation harness: 54 offline tests passed with the local deployment-factory checkout supplied. Root `make code-quality` passed after correcting one formatting failure. Migration declaration validation passed. OpenSpec strict change validation and all 28 main specs passed.
- Measured offline SDK-boundary budget: 37 unique candidates produce 37 Checks with peak ten; duplicates/irrelevant documents add none. Deleting 20 documents in two same-owner folders (40 memberships) produces 105 Checks, 40 writes and 60 ownership ListUsers calls. The real quota resolver yields 40 applications totaling -400 bytes, consistent with existing per-membership accounting; counter writes and artifact stores are mocked. Admission account-status checks are covered separately by route tests.
- Exclusions: no live PostgreSQL/OpenFGA, k3d, embeddings or concurrency/load campaign run. The new live scenario verifies persisted store counts and quota when the developer runs it on the deployed image. General discovery, historical repair, external-store recovery and concurrent ingestion/deletion remain outside this change.

Draft PR: https://github.com/ThalesGroup/fred/pull/3124 (targets swift; #2845 remains open).
