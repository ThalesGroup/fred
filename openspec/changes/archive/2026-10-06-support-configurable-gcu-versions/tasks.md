## 1. Single-version acceptance

- [x] 1.1 Remove GCU history model/store methods and keep one string version/timestamp in `users`; verify latest-version replacement, repeated timestamp updates, null reads, storage preservation and concurrent upserts on SQLite and PostgreSQL.
- [x] 1.2 Read the stored string in OIDC and user details; verify HTTP `v1 -> v2 -> v1` requires reacceptance after each mismatch and preserves first-only default-team enrollment and existing exemptions.
- [x] 1.3 Remove the history table and reader ownership/startup dependencies; verify application code contains no history model/query/startup dependency or JSON column and the final schema contains no history table. Preserve the separate charter regression test.

## 2. Migration and frontend

- [x] 2.1 Keep one enum-to-text revision after the actual target head, with no history or corrective/merge migration; verify SQLite/PostgreSQL data-preserving round trips, arbitrary strings, guarded downgrade, one head and a real upgrade/check. Handle the superseded local trial separately from the PR migration contract.
- [x] 2.2 Retain the regenerated `string | null` frontend client and update the guard regression test for stored latest-version semantics; verify the targeted frontend test and TypeScript checks.

## 3. Documentation and close-out

- [x] 3.1 Reconcile terms, product contract, operator note and these artifacts with the approved single-version policy; verify strict change validation and migration declaration.
- [x] 3.2 Apply the full branch audit and independent read-only review, resolve findings, and run root code-quality plus targeted affected tests; record SHAs, results and exclusions.
- [x] 3.3 Reconcile final artifacts and sync the main spec; verify strict change and main-spec validation. Complete the repository archive/commit/push and existing draft PR/issue update after implementation verification is complete.

Verification evidence (2026-10-06, revised single-version scope):

- Targeted control-plane acceptance/migration/default-team/charter and merged identity/ownership checks: 56 passed, 3 PostgreSQL cases deselected.
- Core admission/store and merged identity store: 26 passed, 2 PostgreSQL cases deselected. Direct identity ORM test adapted to string values; GCU persistence regression verifies identity fields and storage counters remain intact.
- Frontend guard: 2 passed; client regenerated after target integration with `make update-control-plane-api`.
- Earlier application verification is retained below; migration consolidation is reverified for the final single-revision implementation. No deployment, live browser validation or load campaign; HTTP test uses controlled identity/team dependencies with real handlers and SQL persistence.
- Full core offline suite after target integration: 1094 passed, 42 integration cases deselected.
- Repository-wide strict specs: 13 passed, 1 pre-existing failure in `frontend-surface-scale` (placeholder Purpose), unchanged from the target.
- Final single migration: SQLite/HTTP 4 passed, PostgreSQL 3 passed. Both preserve the parent's identity expression index; the round-trip test also executes the parent downgrade. Real PostgreSQL upgrade/check/downgrade/re-upgrade passed with one head `a7e9c2d41063` after `b4e8d2a9c613`.
- The superseded developer-local trial was repaired separately after an isolated reproduction, with a private backup. All six existing user records were preserved; local `alembic check` detects no drift. No trial-cleanup revision is included in the PR.
- Independent read-only consolidation review: target `287b5207f0f8477aeb5468f5d69b917b9302718a`, HEAD `604652e6b018dddb4c49d428fe2a4db73fbd1fc1` plus the final working-tree delta. Prior full application review at `c879ecb585465448d92d6700f7648cde93c676bb` remains applicable because application code is unchanged. The SQLite expression-index loss was fixed and independently rechecked; no remaining findings. Personal configuration is excluded.
- Final root `make code-quality`: all 16 modules passed after the index correction. Strict main acceptance-spec validation passed.
