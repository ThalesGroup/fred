## Context

See proposal.md. Builds on `make-ui-themes-peers`: every theme is a self-contained file, a static
boot script (`public/theme-boot.js`) applies the stored theme and mode to `<html>` before the
stylesheets, and `ApplicationContextProvider` resolves with the same rules.

Startup order today: `index.tsx` awaits `loadConfig()` (static `config.json`, then the public
`GET /control-plane/v1/frontend/config`), then the Keycloak login, then `createRoot().render()`. No
application content is painted before that render.

The control plane has no generic settings store. The closest pattern is the platform prompt: a
singleton table (`platform_prompt`, `id='default'` enforced by a CHECK), a `platform_prompt/`
module (store, service, api) and `GET` / `PUT /admin/platform/prompt` guarded through ReBAC.
Announcements use the `CAN_MANAGE_PLATFORM` organization permission (`platform_admin`).

## Goals / Non-Goals

**Goals:**

- Two platform settings, edited in the admin UI, applied before any application content is painted.
- Same resolution rules in the boot script, in React and in the profile picker.

**Non-Goals:**

- Live push of a changed setting to connected users (applies at next load).
- Server-side storage of each user's choice (stays in localStorage).
- Per-team themes, theme authoring from the UI, passing the theme to hosted applications.

## Decisions

**Storage: a singleton table, modeled on `platform_prompt`.** Table `platform_ui_settings` with
`id` (`'default'`, CHECK constraint), `default_theme` (nullable string), `hidden_themes` (JSON list
of strings, default empty), `updated_by`, `updated_at`. Store `get` returns `None` when no row
exists; `set` upserts. Alternative considered: a generic key/value settings table; rejected for now,
one consumer does not justify a generic store, and the platform prompt sets the precedent.

**Permission: `CAN_MANAGE_PLATFORM`.** Same as announcements: a platform-wide presentation setting.
No new ReBAC role. Frontend nav and route use the existing `admin` requirement.

**Exposure: public `GET /frontend/config`, field `ui_themes`.** `FrontendConfig.ui_themes:
FrontendUiThemes | None` with `default_theme: str | None` and `hidden_themes: list[str]`; `None`
when the row does not exist. The values are not sensitive. It must be public because
`/frontend/config` is the only surface loaded before the first render (the authenticated
`/frontend/bootstrap` is loaded after it and is GCU-gated). Alternative considered: the bootstrap
payload; rejected, it arrives after the first paint.

**Admin API.** `GET` and `PUT /control-plane/v1/admin/platform/ui-settings` with body
`{ default_theme, hidden_themes }`. The service validates the id format, the list size, distinct ids
and "default not hidden" (422 on failure). It does not know the frontend catalog.

**Frontend resolution in one place.** A pure function `resolveUiTheme({ catalog, stored,
platform })` returns the theme id per the spec (offered = shipped and not hidden; hidden ignored if
it would leave nothing). The boot script cannot import it (static file); it carries a copy of the
same rules, and a unit test runs both against the same table of cases.

**No flash.** The boot script applies the theme from the stored choice and the last known platform
settings, cached in localStorage (`ApplicationContextProvider.platformUiThemes`) each time
`/frontend/config` is loaded. `index.tsx` re-resolves with the fresh settings after `loadConfig()`
and before `createRoot().render()`. A cache miss or a stale cache can therefore only change the
blank page background before the first render, never painted application content.

**Admin page.** Route `/admin/interface`, nav entry "Interface utilisateur" / "User interface"
(`requires: "admin"`). One card: a dropdown for the default theme ("None, use the catalog order"
plus every shipped theme), and one checkbox per shipped theme labelled "Offered to users". Saving
is disabled with an inline message when the default is unchecked or no theme is checked. Ids stored
but not shipped are kept on save and listed as "Unknown to this version".

**Profile picker.** Lists offered themes; hidden when exactly one is offered.

## Risks / Trade-offs

- [Stale cache shows the previous default's background for a moment on a first load after an
  admin change] → only the blank pre-render background, accepted by the spec.
- [Boot script and `resolveUiTheme` drift] → shared case table test.
- [An administrator hides the theme a user relies on for accessibility] → the user's choice is kept
  and returns if the theme is offered again; Help Center page explains the setting.
- [Public endpoint grows] → two short fields, no user data.

## Migration Plan

Alembic migration creating `platform_ui_settings` (re-parented on the current `swift` head before
merge, one head). No configuration key. With no row, behavior is exactly that of
`make-ui-themes-peers`. Rollback: image rollback; the table is unused by the previous version. Migration
note `platform-ui-theme-settings.md`: `impact: minor`, required by the repo policy for any new
Alembic revision; the chart's migration hook runs it on a normal upgrade, before the new control
plane serves the public config that reads the table.
