## Context

See proposal.md for motivation and specs/user-ui-preferences/spec.md for the behavior. `ApplicationContextProvider` currently writes theme ID and mode through `useLocalStorageState`, and `public/theme-boot.js` reads the same global keys. `platform_ui_settings` holds the administrator's default and hidden IDs. `libs/fred-core/fred_core/users/user_models.py` already has a `users` row keyed by authenticated user UUID, and the Control Plane users API already has `/users/me/avatar` routes. The frontend catalog is owned by the shipped list plus the validated deployment `theme-catalog.json`.

## Goals / Non-Goals

**Goals:**

- Make the authenticated user row authoritative for the personal theme ID and mode.
- Preserve the existing catalog, platform fallback and pre-content theme rules.
- Keep identity separation on a browser shared by multiple accounts.

**Non-Goals:**

- Store the theme ZIP, CSS, label or assets in PostgreSQL.
- Change how administrators choose the platform default or hidden themes.
- Infer the owner of legacy browser keys, which were never associated with a user ID.

## Decisions

### Add columns to `users`

Add nullable `ui_theme_id` and `ui_theme_mode` columns in a single Control Plane Alembic migration. A null ID means no explicit personal theme; a null mode means `system`. Extend `UserRow` and its existing store rather than creating a second preferences table: both values have the same owner and lifecycle as the user, and no separate access policy or history is needed. The API returns `system` for a null mode. The write operation updates or creates the row for the authenticated UUID, following existing user-store behavior.

### Use self-service endpoints

Add `GET` and `PUT /control-plane/v1/users/me/ui-preferences`. `PUT` replaces both fields atomically with `{ui_theme_id, theme_mode}`; the response has the same shape. Require the authenticated identity and derive the UUID from it. Validate the 32-character lowercase ID syntax but do not check current catalog membership: frontend versions and ZIPs can differ, and temporarily absent IDs must survive. The mode is a three-value enum. Regenerate the frontend OpenAPI client from the backend source, then expose friendly hooks through the existing enhancements module.

### Reconcile the browser cache by identity

The static boot script uses public platform settings to color the empty document before authentication. Once login yields the user ID, the application reads a cache key scoped to that ID, applies it before rendering content, then fetches the database preference. A small gate holds application content until the first preference read succeeds, or falls back to that user's scoped cache/default if the read fails. The database response updates that cache and theme state. Profile changes update the UI and cache optimistically, then persist through the generated mutation; a failed save restores the last confirmed choice and shows an error. Existing global personal-choice keys are ignored and removed once the authenticated path initializes.

This sequence avoids attributing an unscoped legacy choice to whichever account happens to log in next. It also prevents a new browser from painting application content in the platform default before the user's database choice arrives. The user may briefly see only the boot background or loading shell during the fetch.

### Keep the ID stable at the catalog boundary

The saved value is the existing string ID, never a list index or generated UUID. Shipped IDs are constants. A deployment theme's ID comes from `theme-catalog.json` and does not change when the frontend process restarts. Duplicate IDs and collisions with shipped IDs remain rejected by archive validation. Document that changing an ID is equivalent to removing one theme and adding another; keep it stable across ZIP versions, and use a new ID when the theme's identity intentionally changes.

## Risks / Trade-offs

- [Legacy unscoped choices are not safely attributable to a user] -> Do not import them; explain the one-time reselection in the migration note.
- [Preference API unavailable] -> Use the account-scoped cache if present, otherwise platform default and system mode; retry on the next load. Saving failure restores the confirmed state.
- [One user changes preference in another browser while this page stays open] -> The fresh preference is read on the next load; live cross-browser synchronization is outside this slice.
- [ZIP removes a selected ID] -> Keep the ID in the user row and use existing frontend fallback resolution until that ID returns.

## Migration Plan

Apply the one additive nullable-column migration before deploying the Control Plane and frontend. Existing rows have no personal choice and resolve to the platform default/system mode. Rollback can return to the previous frontend/backend with the new columns left unused; dropping the columns would discard choices saved after rollout. Include the operational sequence and impact in the required PR migration note.
