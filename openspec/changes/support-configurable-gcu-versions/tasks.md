## 1. Storage and acceptance

- [x] 1.1 Change the shared user model to nullable string storage, add authoritative per-version acceptance records and normalize legacy enum inputs in the user store; verify focused SQLite persistence tests cover insert, `v1` to `v2` update, timestamps, null reads, repeated/concurrent acceptance, retained earlier versions and legacy `GcuVersionsType.V1` input.
- [x] 1.2 Add one control-plane Alembic revision converting `V1` to `v1`, seeding the history table and guarding incompatible downgrade; verify SQLite and isolated PostgreSQL upgrade/downgrade tests preserve nulls, timestamps, IDs and storage counters, and leave data/schema unchanged when downgrade is refused. Confirm `alembic heads` has one head against the actual PR base.
- [x] 1.3 Update the acceptance service and user-details DTO to use configured strings; extend `test_default_team_for_new_users.py` with actual `v1` to `v2` and arbitrary-version acceptance, no reenrollment and failed-first-enrollment coverage. Verify the route and returned user-details schema accept a version beyond `v1`.

## 2. Admission and consumers

- [x] 2.1 Replace enum-value extraction in OIDC admission with exact string matching; update `test_oidc_gcu_admission.py` to use string-backed rows and verify old-version rejection, new-version access, restored access for a previously accepted active version, case sensitivity and all existing bypass/service/asserted-user cases.
- [x] 2.2 Regenerate the control-plane frontend client using repository tooling; verify `cguValidated` is `string | null`, affected TypeScript checks pass and a focused GCU guard test confirms updated terms remain reachable before acceptance and the shell is accessible afterward.
- [x] 2.3 Check all shared-model consumers in control-plane, knowledge-flow and agent backends; verify a repository search finds no remaining internal `.value` reads or enum construction for configured GCU versions, and affected user-store consumers pass their focused checks. Include the new table in reader startup guards, verify runtime fails at boot only when GCU admission is enabled, and keep ownership with control-plane.

## 3. Documentation and verification

- [x] 3.1 Update the existing terms guide, relevant product-contract sections and the PR migration note with shared-reader deployment ordering, exact version matching, legacy data conversion and guarded rollback; verify the note using `make migration-check` against the PR base.
- [x] 3.2 Run an end-to-end local version transition on isolated test data: accepted `v1`, configure `v2`, verify protected HTTP 403, successful POST acceptance, returned/persisted `v2`, restored admission and switching back to accepted `v1` without a new prompt or repeated default-team enrollment. Verify the equivalent charter transition using existing per-version tests. Record evidence in the PR or this task list.
- [x] 3.3 Apply the branch audit and obtain an independent read-only review of the full change against its actual base; resolve findings and record reviewed SHAs, coverage and exclusions. Run root `make code-quality` once the series is ready for commit, plus the affected targeted tests.
- [x] 3.4 Reconcile these artifacts with the final implementation and its verification evidence; verify strict change validation succeeds. Follow the repository close-out procedure to sync/archive and publish the linked draft PR once these implementation tasks are complete.


Verification evidence (2026-10-06):

- Control-plane `make test PYTEST_OPTS=-q`: 1490 passed, 11 integration cases deselected.
- Fred-core `make test PYTEST_OPTS=-q`: 1045 passed, 40 integration cases deselected; subsequent focused admission/store check: 15 passed, 2 PostgreSQL cases deselected.
- Frontend `npx vitest run`: 3287 passed, 7 skipped. Client regenerated with `make update-control-plane-api`.
- PostgreSQL isolated migration tests: 3 passed; real Alembic heads/upgrade/check/downgrade/re-upgrade passed, one head and no schema drift. Store PostgreSQL history/concurrency tests: 2 passed.
- Runtime context/startup: 23 passed; knowledge-flow ownership/startup: 4 passed. Offline HTTP transition covers actual GCU handlers and SQL persistence with controlled identity/team dependencies; no deployment or live browser validation was performed.
- `make migration-check MIGRATION_BASE=origin/swift`: one valid declaration.
- Independent full working-tree audit and performance review against base/HEAD `52d55420bc60495b7a098ae253b335cd014d00ca`: startup dependency finding corrected and subsequent delta reviewed without findings. Shared-model consumers, schema ownership, OIDC, API/frontend and migration covered; no deployment/load campaign. Root `make code-quality`: all 16 modules passed; basedpyright reported 0 errors, 0 warnings and 0 notes, and frontend TypeScript, Prettier and ESLint passed.
