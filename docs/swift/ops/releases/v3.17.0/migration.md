# Migration guide - v3.17.0

Upgrade from: `code/v3.16.0`
Operational impact: **minor** (minimum version: `3.17.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Whitelist people by email before their first sign-in, and clean up redundant exceptions

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/docs/swift/ops/migrations/3543-whitelist-pending-emails-and-cleanup.md)

### Applicability

Fred deployments with platform access filtering available (authenticated, ReBAC enforced).

### Prerequisites

No additional prerequisites beyond the normal deployment procedure.

### Configuration

No configuration changes are required.

### Upgrade

1. Run the control-plane database migration (`make db-upgrade` in `apps/control-plane-backend`, or the chart's migration hook). It creates `platform_access_pending_emails`.
2. Then roll out the backends. Knowledge Flow and the agent backends check for this table at startup, like the other platform access tables, and refuse to start without it.

Existing exceptions, rules and teams are unchanged.

### Validation

In Platform access > Users, add an email that no user has yet: it appears under the "Pending" filter. Sign in with that verified email while filtering is on: access is granted and the person moves to the whitelist table.

### Rollback

Use the normal rollback procedure. The downgrade drops `platform_access_pending_emails`; emails still waiting are lost, while exceptions already created from them remain.

### Limitations

An email entry only matches a token whose email claim equals it and whose `email_verified` claim is `true`.

## Update frontend NGINX for CVE-2026-123007

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/docs/swift/ops/migrations/3657-frontend-nginx-cve-2026-123007.md)

The patched NGINX version takes effect with the normal frontend image rollout; no data or API migration is required.

See the source note for applicability, validation and rollback.

## Keep Home search responsive while the team list is unavailable

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/docs/swift/ops/migrations/home-search-team-list-loading.md)

Normal frontend deployment delivers the fix. Existing team data and API responses remain compatible.

See the source note for applicability, validation and rollback.

## Prepare Fred v3.17.0 and audit dependency updates

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/docs/swift/ops/migrations/prepare-v3.17.0-release.md)

The covered frontend and Python dependency updates require no data migration or configuration change. This preparation takes effect through the normal release rollout; other in-range notes describe its required database migration and optional theme activation.

See the source note for applicability, validation and rollback.

## Make frontend error details selectable

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/docs/swift/ops/migrations/selectable-frontend-errors.md)

The updated frontend enables selection on the route error screen without changing APIs or stored data.

See the source note for applicability, validation and rollback.

## Expose the local theme clock and optional daylight schedule

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/docs/swift/ops/migrations/shared-theme-clock.md)

### Applicability

The clock is available after a normal frontend upgrade. The activation steps apply
only to deployments that choose to enable a schedule in a theme ZIP.

### Prerequisites

Upgrade all frontend replicas before activating an archive that uses
`localDaylight`. Earlier installers reject that catalog field.

### Configuration

To activate scheduled appearance, add local `sunrise` and `sunset` times to the
theme catalog as described in the [theme authoring guide](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/apps/frontend/src/rework/features/helpCenter/content/en/guides/custom-theme.md).

### Upgrade

Keep the existing archive while upgrading. To activate a schedule afterwards,
publish the new ZIP under a new object key, update the theme URL and restart the
frontend replicas.

### Validation

Inspect `<html>` for the device's current local date and time. With a scheduled
theme selected in System mode, press Shift+F8 and advance through sunset.
Check that Fred changes to Dark, then use **Use live time** to restore the live
clock. Explicit Light or Dark retains its selected palette.

### Rollback

Restore the previous archive URL and restart the frontend replicas before
downgrading to an installer that predates schedule support. Existing archives
without the schedule can stay in place during the rollback.

### Limitations

The schedule uses fixed daily times in the visitor's device time zone.

## Fix wiki version history crash on never-saved agent rules

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/docs/swift/ops/migrations/wiki-history-unsaved-rules.md)

Frontend-only fix; existing data and APIs are unchanged, so normal deployment is enough.

See the source note for applicability, validation and rollback.

## Clarify that Word templates come from configured libraries

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.17.0/docs/swift/ops/migrations/word-template-library-source-clarification.md)

No runtime behavior, data, or deployment configuration changes.

See the source note for applicability, validation and rollback.
