## Why

GitHub issue: #3543

The whitelist exists to admit people the platform rule does not admit, yet today an administrator can only add someone who already has an identity in the configured directory: an exception is keyed by the user id and references `users.id`. A person who has never signed in (for example a federated account Keycloak only creates on first login) cannot be whitelisted ahead of time.

## What Changes

- Administrators can whitelist an email address that matches no known identity. It is stored as a pending entry (email, granted by, granted at).
- On that person's first refused request, if the verified token's email matches a pending entry, the entry becomes a regular manual exception for that account and is deleted. Admitted people pay no extra lookup.
- Whitelist > Users shows pending emails above the table, each with "Remove". The "Add users" dialog offers to add the typed text as an email when it is a valid address.
- New endpoints: `GET`, `POST` and `DELETE /admin/platform/access/pending-emails`. Generated OpenAPI and frontend client regenerated.
- One Alembic migration (control-plane) adds `platform_access_pending_emails`.
- **Cleanup filter.** Whitelist > Users gets a chip bar: All, "Admitted by the rule" (the exception is redundant) and "Whitelist only" (removing it makes the person lose access). `GET /admin/platform/access/users` gains `overlap=rule|whitelist_only`, with `exceptions_only=true`; `total` follows the filter.
- **Bulk removal.** Each row starts with a checkbox; the header checkbox selects every row matching the current search and filter, across all pages, and rows can then be unchecked. One bulk bar action "Remove" calls the new `POST /admin/platform/access/users/revoke` (`user_ids`, or `all_matching` with `query`, `overlap` and `excluded_ids`), atomic, with the existing safeguard against an administrator removing their own last access.
- **Reversal of a recorded decision:** `whitelist-lists-individual-exceptions` removed row selection from this table because there was no bulk-remove endpoint. The owner restores it for removal.

## Capabilities

### Modified Capabilities

- `platform-access-control`: adds "Administrators pre-authorize people by email" and "Administrators clean up redundant exceptions".

## Impact

- `libs/fred-core/fred_core/security/platform_access/{models,store,access_control}.py` and tests.
- `apps/control-plane-backend/control_plane_backend/platform_access/{api,service,schemas}.py`, tests, one migration, `openapi.json`.
- `apps/frontend/src/slices/controlPlane/controlPlaneOpenApi.ts` (regenerated), `PlatformAccessPage/` (page, add dialog, tests), fr/en strings.
- `docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`, one migration note (impact: none, the migration runs with the usual upgrade).
