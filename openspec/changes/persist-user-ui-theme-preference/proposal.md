## Why

The profile's theme and light/dark/system choices currently live only in browser `localStorage`. They survive a reload in the same browser, but do not follow the signed-in user to another browser or device. The existing PostgreSQL theme row holds platform-wide administrator settings, not personal choices.

Tracking: GitHub issue #3282.

## What Changes

- Store each user's selected theme ID and display mode on the existing `users` row in PostgreSQL.
- Add authenticated self-service read and write endpoints for these preferences, and use the generated Control Plane client in the frontend.
- Resolve the signed-in user's saved ID against the installed and offered catalog. Keep a hidden or missing ID stored so it can become active again when offered.
- Use a user-scoped browser cache for the first application paint. The database becomes authoritative after the profile request completes; an account switch must not reuse another user's cached choice.
- Document that shipped and ZIP theme IDs are stable, opaque names. A frontend restart does not generate a new ID; deployments must retain an ID for the same theme.
- Add one Alembic migration and an operator migration note. Existing unscoped browser preferences cannot be assigned safely to an account, so users without a saved database preference initially receive the platform default and can select their theme again.

## Capabilities

### New Capabilities

- `user-ui-preferences`: authenticated read/write, persistence, account isolation and initial values for personal UI preferences.

### Modified Capabilities

None. The existing theme-resolution and platform-fallback requirements remain valid; the new capability defines where the personal choice is stored and how it reaches that resolver.

## Impact

- `libs/fred-core`: add two nullable preference fields and user-store operations on the existing `users` model.
- `apps/control-plane-backend`: one users-table migration, self-service routes, request/response validation and focused tests.
- `apps/frontend`: generated API client, application theme state, boot cache, profile picker and focused tests.
- Docs: product contract, theme guidance and an English migration note.
