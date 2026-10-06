## Why

After a user has accepted `v1`, changing `app.gcu_version` to `v2` causes acceptance to fail with HTTP 500 because the shared user model and PostgreSQL enum only support `v1`. This contradicts the documented configurable-version contract and prevents deployments from requiring updated terms. Tracking: [GitHub issue #2972](https://github.com/ThalesGroup/fred/issues/2972).

## What Changes

- Keep the existing single accepted GCU version and timestamp in `users`, replacing enum storage with an opaque string. Each acceptance replaces the stored version and timestamp; no history table or JSON column is added.
- Add one control-plane migration converting legacy database `V1` entries to `v1` preserving timestamps, nulls and other user data.
- Keep exact version matching for protected human requests and existing service/asserted-user exemptions.
- Ensure reacceptance records the new version without repeating default-team enrollment.
- Regenerate the control-plane frontend client so `cguValidated` accepts any string.
- **BREAKING**: `UserRow.gcuVersionAccepted` becomes a string instead of an enum instance. Retain the exported `GcuVersionsType.V1` as a legacy store-input compatibility shim; document the model and deployment transition.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `user-terms-acceptance`: Revise the existing draft capability to retain only the latest GCU acceptance, as requested. The charter retains its existing per-version contract and authorization.

## Impact

- `fred-core`: shared user model, store input types and OIDC admission checks; all backends consuming the shared model must upgrade together.
- Control-plane: GCU acceptance service, user-details response and an Alembic correction joining the locally applied revision and the target identity migration.
- Frontend: generated control-plane schema and existing GCU guard consumers.
- Tests: actual `v1` to `v2` reacceptance, admission, persistence and migration/rollback coverage.
- Operations: migrate with old readers stopped; reject rollback if accepted versions cannot be represented by the legacy enum.
- Documentation: update the existing terms guide and product contract rather than introducing a parallel guide.
