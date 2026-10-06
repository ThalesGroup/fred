## Why

Users pick their UI theme in their profile, but a platform has no way to set the theme new users get,
nor to withdraw a theme it does not want offered (for example to impose a branded theme). Requires
`make-ui-themes-peers`: every theme, Pebble included, can then be the default or be hidden, and the
theme is resolved before the application paints.

## What Changes

- A platform administrator can set, from a new admin page "Interface utilisateur" ("User
  interface"), the platform default theme and the themes hidden from users.
- The control plane stores these two settings and serves them in the public `GET /frontend/config`,
  which the frontend already loads before its first render, so the resolved theme is known before
  any application content is painted.
- Theme resolution becomes: the user's stored choice when it is offered, otherwise the platform
  default when it is offered, otherwise the first offered theme of the catalog. The mode (light /
  dark / system) is unchanged.
- The profile theme picker lists offered themes only, and is not shown when a single theme is
  offered.

## Capabilities

### New Capabilities

- `platform-ui-theme-settings`: platform default theme and hidden themes, how administrators edit
  them, how they are exposed, and how they constrain each user's theme.

### Modified Capabilities

None. `frontend-ui-themes` is introduced by `make-ui-themes-peers`, not yet archived; its
resolution rule is extended here through the new capability.

## Impact

- Control plane: new singleton table `platform_ui_settings` (Alembic migration, `table_ownership.py`),
  module `platform_ui_settings/` (store, service, api), `FrontendConfig` gains `ui_themes`,
  `GET` / `PUT /control-plane/v1/admin/platform/ui-settings` guarded by `CAN_MANAGE_PLATFORM`.
- Frontend: regenerated `controlPlaneOpenApi.ts`; admin page, nav entry and route; theme resolution
  in the boot script and `ApplicationContextProvider`; profile picker.
- Docs: `CONTROL-PLANE-PRODUCT-CONTRACT.md` (dated entry for `FrontendConfig.ui_themes` and the admin
  endpoints), `FRONTEND_CODING_GUIDELINES.md` theme section, Help Center (fr/en) page for the admin
  setting, migration note.
- Tracking: #2933 (milestone swift-v4).
