# Tasks

## 1. SQL-backed discovery
- [x] 1.1 Add nullable activity and index with a linear Alembic migration; verify head and migration upgrade on an isolated database.
- [x] 1.2 Reuse explicit owner-scoped activity PATCH with server timestamps; test no activity on rename and no regression.
- [x] 1.3 Implement bounded ranked instance query and permission-scoped product endpoint; test filtering, backfill, ties, personal-only and partial failure. Document contract and migration.

## 2. Home integration
- [x] 2.1 Regenerate control-plane API using make update-control-plane-api; replace home fan-out with the generated hook; test loading/error/retry and five cards. Update UX docs.

## 3. Integration and review
- [x] 3.1 Run focused tests, required quality checks, independent author/performance review; record evidence and fix findings.
- [x] 3.2 Add an optional bounded route limit, pass it through the SQL and failure fallback, and regenerate the client.
- [x] 3.3 Verify default, custom and invalid limits; review the integration with swift and update the contract and PR evidence.

## Workflow follow-up
- Sync and archive after verification and required review; push a draft PR linked to #3510.

Verification: 54 targeted backend conversation/store/service/migration tests and 4 frontend tests pass. Raw backend basedpyright: 0 errors, 0 warnings, 0 notes. Frontend TypeScript passes. Migration upgrade/downgrade tested on isolated SQLite; one Alembic head. Fifty concurrent home queries through two SQL pools preserve ordering and five-result bounds. API regenerated with make update-control-plane-api under Node 24. make migration-check passes with one isolated declaration.

Root code-quality covered all modules: unchanged libraries/capabilities and fred-agents passed in the full run; after fixing three import-order blocks and annotating public Alembic revision ids using the existing allowlist convention, control-plane, knowledge-flow and frontend passed in a resumed root run. The initial web-research bootstrap failure was resolved using existing uv pip tooling without dependency-file changes.

Independent read-only author/performance review: base bef0098f4fa37f21121f023725394c212b012604, code head fe39545728b34d199b0ffb4629f18dd9abcda784. Full code/tests/docs/spec coverage, no actionable implementation findings. Initial unrelated inherited ancestry was removed. Subsequent code changes only sort imports and annotate public migration revision ids. git diff --check passes. Exclusions: no browser/dev-server validation, full monorepo test suites or production PostgreSQL p95/load claim. Concurrent SQLite reads establish correctness, not production throughput.

Swift integration follow-up: the optional route limit defaults to 5 and accepts 1-20; route tests cover default, custom and rejected values. The generated client exposes the optional argument. The activity migration follows revision 52344270c256 and Alembic reports one head. After resolving the store, product-contract and managed-conversations conflicts, 28 focused backend tests and 2 frontend home tests pass; TypeScript and root make code-quality pass. The independent read-only review of the complete diff against origin/swift (2b377b522) found that current readiness-gating preparations could leave unusable launchers in the result. An indexed SQL existence filter before LIMIT and a regression test resolve that finding, including fallback backfill. The product contract, archived change, current spec and PR description record the final behavior. The 50-query two-pool test checks concurrency correctness, not PostgreSQL latency.
