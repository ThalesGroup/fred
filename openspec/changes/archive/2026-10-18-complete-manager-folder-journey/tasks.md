## 1. Folder contract

- [x] 1.1 Confirm the proposed folder lifecycle, bounded navigation and interim document-control interaction with the developer; acceptance is the confirmed scope in this conversation. The original business UI remains invariant.
- [x] 1.2 Implement directory-selective bounded listing, full-directory search/sort and bounded ancestor resolution using the existing model; verify stable ordering, truthful totals, root/child isolation, missing/foreign parents and depth limits with focused API/SQL tests, then regenerate the client.
- [x] 1.3 Complete atomic folder/subfolder creation, rename and document-free subtree deletion under current authority; verify duplicate creation, stable descendant identities, document refusal, revocation and deletion races with focused integration tests and invariant markers.

## 2. Original Resources UI

- [x] 2.1 Bind the existing page, toolbar, table, breadcrumbs and dialogs to manager data and authority, preserving the separate knowledge-base consumer and excluding document writes; verify the two original controls, personal/team contexts, loading/errors, submission concurrency and stale completions with focused component tests and TypeScript.

## 3. Architecture evidence and delivery

- [x] 3.1 Measure navigation and writes on disposable fixtures with 10,000 folders, wide and deep directories, few/many caller memberships and concurrency 1/10/50; record SQL plans, returned rows, FGA RPC/tuple counts, latency and lock wait/hold time. Compare single-organization and separate-organization writers; do not infer a throughput guarantee from functional tests.
- [x] 3.2 Obtain independent scoped review, fix actionable findings with regression coverage and re-review corrections; record the reviewed revision, scope and exclusions here.
- [x] 3.3 Reconcile the relevant arc42 chapters into a compact architectural account of implemented behavior and measured limits; check architectural claims against code/tests, generate derived blocks, validate documentation and this change, and record the developer's manual recipe. Commit the completed lot locally without push; the global campaign remains separately scheduled by the developer.

## Investigation evidence

- Baseline: `13c660191`. Existing Resources components match local `origin/swift`; their buttons depend on Python permissions. Manager already owns folders, immutable placement and space authorization, with no folder-specific tuples.
- Independent scoped audit: unbounded folder responses, non-selective parent predicate and stale arc42 UI claims. Disposable PostgreSQL 15.12, 10,000 folders, concurrency 1: selecting one child examined 10,000 rows and 214 shared buffers; equality/IS NULL used the existing index and 3 buffers. This measures SQL access, not application throughput. The implemented measurements are recorded in arc42 chapter 09.
- Independent design review clarified all document entry points, folder-only page totals, real creation dates/unknown size and per-subtree deletion atomicity. The developer confirmed this scope on 2026-10-18, including recursive document-free deletion and the original document panel with sending unavailable.


## Verification and review

- Scope: local folder lot against `13c660191`; issue #3092. Generated client regenerated with `make -C apps/frontend update-control-plane-api`. No schema migration or FGA model change.
- API/SQL: the five existing resource-browsing cases passed; the new paged-directory/atomic-subtree case passed after correcting its fixture URL and returning the persisted timestamp precision. The forced-lock waiter case passes for PATCH, DELETE and child creation. Seven offline OpenAPI contract tests pass. Targeted clippy (`--lib --test integration --test openapi -- -D warnings`) and rustfmt pass.
- UI: 34 initial targeted tests pass (workspace drop, knowledge-base consumer, Resources page, depth modal); 21 final shared-workspace tests pass (manager, back navigation, knowledge-base, rename); Resources page including personal metadata passes. Four upload/import guard tests pass in a clean run from `apps/frontend`. TypeScript passes. These are overlapping focused selections, not a total-suite count.
- Scaling: `RUST_TEST_NOCAPTURE=1 make -C apps/control-plane test-integration CARGO_TEST_OPTS=folder_scaling` passes. It asserts RPC/tuple budgets, paginated roles, bounded returned rows, deletion and concurrent snapshot consistency. SQL plans and sampled lock spans are measured evidence, not production guarantees; authoritative figures and provenance are in arc42 09.
- Independent read-only review: backend, generated contract and SQL/FGA boundary; original UI/KB consumers and async interactions; then performance evidence and arc42. Four UI findings (empty last page, stale bulk busy state, duplicate DELETE, root-row drop target) were corrected with regressions and re-reviewed. Measurement projections, sampled-span terminology and overclaimed invariant markers were corrected and re-reviewed. Stale nonempty-folder/one-Check documentation was corrected and re-reviewed. No actionable finding remains in this scope.
- `make -C docs/architecture check` and strict OpenSpec validation pass. The dedicated dossier pass covers journeys, content ownership, role matrix, runtime/contract boundaries, costs and migration guidance. Full branch/PR review, deployed visual acceptance and global test/quality campaigns are excluded; broad checks remain deferred at the developer's request. No push.

## Deployed manual recipe

1. Rebuild/deploy manager and frontend from the same revision; retain existing SQL/FGA data and grants.
2. As Priya, open fredlab Resources. Compare the unchanged toolbar/table/dialogs; create a library, then two nested folders. Refresh and navigate using breadcrumbs.
3. Rename the parent and verify its children remain reachable. Search/sort and paginate a populated directory; delete the last entry of a last page and verify navigation recovers.
4. Confirm document-free subtree deletion and inspect partial results when selecting several roots. The document-bearing refusal is covered by the API fixture; do not ingest documents for this lot.
5. Open upload and drop a file onto a folder row: retain the original panel, show sending unavailable, and perform no content write. Check a read-only account and Priya's personal space. Observe ordinary errors from unchanged statistics/quota services if Python is stopped.

This manual recipe is not recorded as executed; the developer validates it on deployment.
