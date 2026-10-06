## 1. Single-version acceptance

- [x] 1.1 Remove GCU history model/store methods and keep one string version/timestamp in `users`; verify latest-version replacement, repeated timestamp updates, null reads, storage preservation and concurrent upserts on SQLite and PostgreSQL.
- [x] 1.2 Read the stored string in OIDC and user details; verify HTTP `v1 -> v2 -> v1` requires reacceptance after each mismatch and preserves first-only default-team enrollment and existing exemptions.
- [x] 1.3 Remove the history table and reader ownership/startup dependencies; verify application code contains no history model/query/startup dependency or JSON column and the final schema contains no history table. Preserve the separate charter regression test.

## 2. Migration and frontend

- [ ] 2.1 Preserve the already-applied enum-conversion revision and link one corrective revision removing the intermediate history table without altering current user data; verify isolated SQLite/PostgreSQL round trips, arbitrary string writes, one Alembic head, actual upgrade/check and final linkage against the target and locally applied `a7e9c2d41063`, documenting the two-revision exception.
- [ ] 2.2 Retain the regenerated `string | null` frontend client and update the guard regression test for stored latest-version semantics; verify the targeted frontend test and TypeScript checks.

## 3. Documentation and close-out

- [ ] 3.1 Reconcile terms, product contract, operator note and these artifacts with the approved single-version policy; verify strict change validation and migration declaration.
- [ ] 3.2 Apply the full branch audit and independent read-only review, resolve findings, and run root code-quality plus targeted affected tests; record SHAs, results and exclusions.
- [ ] 3.3 Sync the main spec, archive the completed change, commit/push the updated branch and rewrite the existing draft PR/issue to describe the final scope; verify clean working tree apart from the user's local configuration.
