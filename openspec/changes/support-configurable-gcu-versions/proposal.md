## Why

After a user has accepted `v1`, changing `app.gcu_version` to `v2` causes acceptance to fail with HTTP 500 because the shared user model and PostgreSQL enum only support `v1`. This contradicts the documented configurable-version contract and prevents deployments from requiring updated terms. Tracking: [GitHub issue #2972](https://github.com/ThalesGroup/fred/issues/2972).

## What Changes

- Persist GCU acceptances per user and opaque version string, matching the charter: a previously accepted version remains valid when it becomes active again.
- Add one control-plane migration converting legacy database `V1` entries to `v1` and seeding a per-version acceptance table, preserving timestamps, nulls and other user data.
- Keep exact version matching for protected human requests and existing service/asserted-user exemptions.
- Ensure reacceptance records the new version without repeating default-team enrollment.
- Regenerate the control-plane frontend client so `cguValidated` accepts any string.
- **BREAKING**: `UserRow.gcuVersionAccepted` becomes a string instead of an enum instance. Retain the exported `GcuVersionsType.V1` as a legacy store-input compatibility shim; document the model and deployment transition.

## Capabilities

### New Capabilities

- `user-terms-acceptance`: Configurable GCU versions, persisted acceptance and admission until the active version is accepted. No existing capability spec covers this contract.

### Modified Capabilities

None. Charter behavior already satisfies the confirmed rule; retain its existing per-version contract and verify the same transition for both mechanisms.

## Impact

- `fred-core`: shared user model, store input types and OIDC admission checks; all backends consuming the shared model must upgrade together.
- Control-plane: GCU acceptance service, user-details response and one Alembic migration.
- Frontend: generated control-plane schema and existing GCU guard consumers.
- Tests: actual `v1` to `v2` reacceptance, admission, persistence and migration/rollback coverage.
- Operations: migrate with old readers stopped; reject rollback if accepted versions cannot be represented by the legacy enum.
- Documentation: update the existing terms guide and product contract rather than introducing a parallel guide.
