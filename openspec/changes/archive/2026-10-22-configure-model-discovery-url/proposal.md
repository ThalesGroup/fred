## Why

The Models tab shows the catalog loaded at pod startup. Administrators cannot change the discovery URL, see which upstream models appeared or disappeared, or distinguish an endpoint failure from a confirmed removal. A removed selection can break a managed turn.

## What Changes

- Keep static YAML profiles and OpenAI-compatible `GET /models` discovery in one catalog. Let an administrator override a source URL, with the YAML URL as its default.
- Refresh discovery when Features > Models opens. Show new and confirmed removed models before the rows, retain unavailable rows, and keep new models disabled until explicitly enabled. A failed refresh preserves the last successful inventory.
- Provide a platform fallback chat model independent of the existing forced platform binding. Use it only when a saved selection is confirmed removed, without changing that selection.
- Apply successful URL and inventory changes without restarting pods. Preserve display-name overrides and stable model identities.
- Separate manually declared and discovered models in the admin list using pod-advertised provenance. If discovered rows exist without a registered source status, explain that URL management is unavailable instead of claiming no discovery is configured.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `model-routing`: Live discovery inventory, change reporting, and a platform fallback for confirmed removed chat profiles.

## Impact

Pod catalog refresh and routing, control-plane inventory and fallback settings, one extension to this PR's Alembic migration, the Models admin UI, generated API types, tests, and the routing operator guide. The provenance projection is additive and needs no further migration.
