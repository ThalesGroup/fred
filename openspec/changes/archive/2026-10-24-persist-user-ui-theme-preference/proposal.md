## Why

The user's display choices currently live only in browser `localStorage`. The managed workstation clears browser data on restart, so these choices disappear and do not follow the signed-in user to another browser or device. The existing PostgreSQL theme row holds platform-wide administrator settings, not personal choices.

Tracking: GitHub issue #3282.

## What Changes

- Store each user's theme ID, display mode, language, navigation-sidebar state, and team and agent sort modes in a dedicated `users_preferences` table in PostgreSQL. Keep resized pane widths and trace expansion in browser localStorage.
- Add authenticated self-service read and partial-update endpoints for these preferences, and use the generated Control Plane client in the frontend.
- Resolve the signed-in user's saved ID against the installed and offered catalog. Keep a hidden or missing ID stored so it can become active again when offered.
- Read only the signed-in person's database record before application content paints. An absent row or failed read uses documented defaults. Existing browser values never seed or replace database-backed choices; those controls live in memory during the session.
- Document that shipped and ZIP theme IDs are stable, opaque names. A frontend restart does not generate a new ID; deployments must retain an ID for the same theme.
- Add one Alembic migration and an operator migration note. Existing users start with defaults and choose their durable settings again after rollout.

## Capabilities

### New Capabilities

- `user-ui-preferences`: authenticated read/write, persistence, account isolation and initial values for personal display preferences.

### Modified Capabilities

None. The existing theme-resolution and platform-fallback requirements remain valid; the new capability defines where the personal choice is stored and how it reaches that resolver.

## Impact

- `apps/control-plane-backend`: one `users_preferences` table migration, model/store, self-service routes, request/response validation, account-deletion cleanup and focused tests.
- `apps/frontend`: generated API client, database-only preference hydration, theme boot, profile controls, sorting and focused tests. Existing pane resizing and trace expansion stay local.
- Docs: product contract, theme guidance and an English migration note.
