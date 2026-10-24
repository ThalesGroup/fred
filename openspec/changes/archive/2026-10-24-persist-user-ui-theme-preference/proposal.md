## Why

The user's display choices currently live only in browser `localStorage`. The managed workstation clears browser data on restart, so these choices disappear and do not follow the signed-in user to another browser or device. The existing PostgreSQL theme row holds platform-wide administrator settings, not personal choices.

Tracking: GitHub issue #3282.

## What Changes

- Store each user's theme ID, display mode, language, navigation-sidebar state, team and agent sort modes, and trace-expansion choice in a dedicated `users_preferences` table in PostgreSQL. Keep resized pane widths in browser localStorage.
- Add authenticated self-service read and partial-update endpoints for these preferences, and use the generated Control Plane client in the frontend.
- Resolve the signed-in user's saved ID against the installed and offered catalog. Keep a hidden or missing ID stored so it can become active again when offered.
- Import validated legacy browser choices when the signed-in person has no database row, then mark the browser import complete after a successful save. Use a user-scoped browser cache for the first application paint. The database becomes authoritative after the profile request completes; an account switch must not reuse another user's cached choice.
- Document that shipped and ZIP theme IDs are stable, opaque names. A frontend restart does not generate a new ID; deployments must retain an ID for the same theme.
- Add one Alembic migration and an operator migration note. Legacy keys have no owner, so the first authenticated import on a shared browser can only be best effort; already-cleared browser data cannot be recovered.

## Capabilities

### New Capabilities

- `user-ui-preferences`: authenticated read/write, persistence, first-login import, account isolation and initial values for personal display preferences.

### Modified Capabilities

None. The existing theme-resolution and platform-fallback requirements remain valid; the new capability defines where the personal choice is stored and how it reaches that resolver.

## Impact

- `apps/control-plane-backend`: one `users_preferences` table migration, model/store, self-service routes, request/response validation, account-deletion cleanup and focused tests.
- `apps/frontend`: generated API client, preference hydration and browser import, theme boot, profile controls, sorting and trace-state writers, and focused tests. Existing pane resizing stays local.
- Docs: product contract, theme guidance and an English migration note.
