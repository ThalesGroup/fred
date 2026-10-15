## 1. Scope confirmation

- [ ] 1.1 Obtain developer confirmation of this search containment slice and its acceptance scenarios; retain scenario 4b retry repair and other tool/UI investigations as remaining #3091 work.

## 2. Search isolation

- [ ] 2.1 Separate the contextual library envelope from selected libraries in VectorSearchService and validate explicit UIDs with current metadata and authorization. Verify multi-team rejection, mixed union, document-only narrowing, empty/denied selections, personal and unscoped callers in focused offline tests.
- [ ] 2.2 Gate all corpus strategy candidates before enrichment or content diagnostics using batched metadata, current branch membership and request-local deduplicated read checks. Verify stale tags with revoked and surviving grants, missing metadata, denied reads, authority failures, valid remaining-library access, hybrid fallback and supported service-agent behavior. Assert bounded concurrency and one read check per distinct UID despite repeated chunks; report fixture sizes and call counts.

## 3. Conversation sources

- [ ] 3.1 Remove corpus UID filtering from the session branch while retaining user/session/scope filters and source ceilings. Verify attachment-plus-corpus retrieval, disabled sources and other-user/session exclusion offline.
- [ ] 3.2 Extend the existing live combined-selection test to execute a real deterministic runtime turn as well as the direct Knowledge Flow request. Keep the existing late-library and late-attachment controls and verify temporary resource cleanup.

## 4. Acceptance and close-out

- [ ] 4.1 Run relevant offline suites and root code-quality, deploy the changed Knowledge Flow image to the existing k3d environment, and rerun the focused validation-report campaign. Require all 26 existing cases plus added runtime coverage to pass with no setup/teardown errors; record image revisions and restore only temporary test grants.
- [ ] 4.2 Apply the full branch audit and independent read-only correctness/performance reviews; fix actionable findings and verify corrections. Record base/head, reviewed scope, evidence and exclusions in the PR.
- [ ] 4.3 Update the existing migration note and PR around the implemented fix, reconcile and validate these artifacts, then sync/archive the completed change. Verify the residual issue scope stays explicit, commit coherent blocks and keep the draft PR current.
