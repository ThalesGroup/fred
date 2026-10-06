## 1. Single-version acceptance

- [x] 1.1 Remove GCU history model/store methods and keep one string version/timestamp in `users`; verify latest-version replacement, repeated timestamp updates, null reads, storage preservation and concurrent upserts on SQLite and PostgreSQL.
- [x] 1.2 Read the stored string in OIDC and user details; verify HTTP `v1 -> v2 -> v1` requires reacceptance after each mismatch and preserves first-only default-team enrollment and existing exemptions.
- [x] 1.3 Remove the history table and reader ownership/startup dependencies; verify application code contains no history model/query/startup dependency or JSON column and the final schema contains no history table. Preserve the separate charter regression test.

## 2. Migration and frontend

- [x] 2.1 Preserve the already-applied enum-conversion revision and link one corrective revision removing the intermediate history table without altering current user data; verify isolated SQLite/PostgreSQL round trips, arbitrary string writes, one Alembic head, actual upgrade/check and final linkage against the target and locally applied `a7e9c2d41063`, documenting the two-revision exception.
- [x] 2.2 Retain the regenerated `string | null` frontend client and update the guard regression test for stored latest-version semantics; verify the targeted frontend test and TypeScript checks.

## 3. Documentation and close-out

- [x] 3.1 Reconcile terms, product contract, operator note and these artifacts with the approved single-version policy; verify strict change validation and migration declaration.
- [x] 3.2 Apply the full branch audit and independent read-only review, resolve findings, and run root code-quality plus targeted affected tests; record SHAs, results and exclusions.
- [x] 3.3 Reconcile final artifacts and sync the main spec; verify strict change and main-spec validation. Complete the repository archive/commit/push and existing draft PR/issue update after implementation verification is complete.

Verification evidence (2026-10-06, revised single-version scope):

- Targeted control-plane acceptance/migration/default-team/charter and merged identity/ownership checks: 56 passed, 3 PostgreSQL cases deselected.
- Core admission/store and merged identity store: 26 passed, 2 PostgreSQL cases deselected. Direct identity ORM test adapted to string values; GCU persistence regression verifies identity fields and storage counters remain intact.
- Frontend guard: 2 passed; client regenerated after target integration with `make update-control-plane-api`.
- Isolated PostgreSQL migration cases: 3 passed; store replacement/concurrency: 2 passed. Actual Alembic upgrades from both `a7e9c2d41063` (arbitrary current acceptance) and `b4e8d2a9c613` (legacy enum), downgrade/re-upgrade, data checks and `alembic check` passed with one `e6b8d2a41074` head. Historical base-downgrade enum residue was cleaned only between isolated test cases.
- `make migration-check MIGRATION_BASE=origin/swift`: one valid declaration. Strict change and main-spec validation passed. Local database inspected read-only: already on `a7e9c2d41063`; no developer database migration applied by this work.
- Root `make code-quality` passed all 16 modules before and after target integration; basedpyright returned 0 errors, 0 warnings and 0 notes, and frontend TypeScript/Prettier/ESLint passed. No deployment, live browser validation or load campaign; HTTP test uses controlled identity/team dependencies with real handlers and SQL persistence.
- Full core offline suite after target integration: 1094 passed, 42 integration cases deselected.
- Independent full-branch audit and async/performance inspection: base `5bd9c7113b439294d29e15d88563b2e0fbdd3bd1`, reviewed implementation/merge HEAD `c879ecb585465448d92d6700f7648cde93c676bb`. The two-head finding is resolved by the correction joining both immutable parents; the subsequent operator-ordering sentence is corrected. Coverage includes new identity snapshot consumers and all PR files; personal configuration excluded. No functional findings remain in the reviewed scope.
- Repository-wide strict specs: 13 passed, 1 pre-existing failure in `frontend-surface-scale` (placeholder Purpose), unchanged from the target.
