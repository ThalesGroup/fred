## Context

See [proposal.md](proposal.md) for the problem and scope. Configuration already exposes `gcu_version` as a string. The model instead uses `GcuVersionsType.V1`, SQLAlchemy stores its name `V1`, the acceptance service constructs this enum, and OIDC admission reads `.value`. The API's `cguValidated` field generates a frontend `"v1"` union. Existing admission tests use arbitrary versions behind a fake enum wrapper, while the default-team test named for a newer version still accepts `v1`.

The shared `users` table is owned by control-plane migrations and consumed through `fred-core` by multiple backends. Historical migrations remain unchanged.

The user confirmed that acceptance of a version remains valid when that version becomes active again. The charter already implements this rule with per-version records. Local read-only diagnosis found charter `v2` applied and already accepted, explaining why no further prompt appeared. Apply the same acceptance semantics to GCU without changing charter scope or authorization.

## Goals / Non-Goals

**Goals:** Make the stored version match configuration and HTTP values, preserve existing acceptance data, and test the actual version transition through persistence and admission.

**Non-Goals:** New terms content configuration, changes to charter authorization, default-team enrollment policy or service admission exemptions.

## Decisions

### Store opaque version strings

Use nullable SQL text for the legacy `gcuVersionAccepted` projection and add `user_gcu_acceptances`, keyed by user UUID and version, with its acceptance timestamp and a cascading user foreign key. This table is the authoritative per-version record. Admission checks existence of the configured version. User details return the configured version if it has been accepted, otherwise the latest accepted version or null. Do not trim, case-fold or interpret versions as ordered numbers. Adding `V2` to the enum would only postpone the next deployment failure; the existing documented contract permits deployment-owned version identifiers.

Keep the exported `GcuVersionsType.V1` for legacy callers of the user-store update method. The concrete store accepts strings or the legacy enum and normalizes enum input to its value before writing. Internal callers use strings. Model reads always return strings, so external `.value` consumers must adapt. This small compatibility boundary avoids a package-export removal without retaining an enum restriction in persistence or HTTP schemas.

### Convert legacy values in one migration

Add one revision after the control-plane head on the PR's actual target branch. Convert only the legacy representation `V1` to `v1`, preserving nulls, timestamps, IDs and storage counters. PostgreSQL casts the enum column to text with the explicit mapping, then drops the unused enum type. Seed history from each existing non-null acceptance, keeping its timestamp (including a historical null timestamp). Register the new shared table as control-plane-owned. Cover the supported SQLite migration path with batch column alteration as appropriate.

Downgrade first checks that all accepted versions in both history and the legacy projection are exactly `v1`; if not, it fails before changing schema or data. Otherwise recreate the legacy enum representation `V1` and nullable column. Silently resetting newer acceptances would lose consent records and is excluded.

### Preserve acceptance and admission boundaries

The existing POST acceptance route checks prior acceptance before enrolling default teams. Keep that condition; replace enum construction with the configured version. Write history and the latest-version projection atomically. Conflict-safe inserts preserve the first acceptance timestamp for a version and handle concurrent acceptance/storage row creation without erasing history. Update persistence and admission tests to use real string values, including old-version denial, a successful new-version write, and admission when a previously accepted version becomes active again. Existing disabled-security, unset-version and service/asserted-user behavior remains as currently implemented.

Regenerate the control-plane OpenAPI frontend client using the repository tooling. Register the history table in knowledge-flow required tables and conditionally guard runtime GCU schema when admission is enabled; startup must point to the control-plane migration and standalone pods must still boot without it. Verify `GcuGuard` compares the current public frontend-config version to the accepted string and that no remaining internal consumer requires an enum instance.

## Risks / Trade-offs

- Old processes cannot read the converted values with their enum ORM mapping - stop consumers and deploy updated readers together.
- SQLite-only tests would miss PostgreSQL native-enum behavior - run a focused PostgreSQL migration round trip against an isolated test database, never the developer's active database.
- New accepted versions cannot be represented by the old schema - guard downgrade and document that rollback requires a backup or an explicit data decision.
- Older external users of the ORM may expect `.value` - document the string model change while retaining legacy store-input compatibility.

## Migration Plan

1. Back up the shared user data and stop backends reading the shared table.
2. Apply the single control-plane migration using the updated release.
3. Start updated control-plane, knowledge-flow and agent backends, then deploy the regenerated frontend.
4. Confirm legacy `v1` acceptance and timestamps remain intact. Configure a newer version and confirm protected human access is denied until acceptance succeeds and persists it.
5. Roll back only if the downgrade guard accepts the data, or restore a coordinated pre-upgrade backup. Do not remove newer acceptance records automatically.

The operational procedure is documented in `docs/swift/ops/migrations/2972-configurable-gcu-versions.md`.
