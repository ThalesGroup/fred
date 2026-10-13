# Proposal

## Why

Theme branding is global, so a custom theme cannot update the browser tab without branding the other themes. The user picker reads startup settings while admin changes only invalidate the admin query, and the default tile uses a disabled low-contrast button.

## What Changes

- Add optional theme-local browser tab title and light/dark SVG favicon names to the ZIP catalog, preserving existing archives and global defaults.
- Clearly identify the default theme using a visible badge and tile border; separate availability controls and light/dark previews, including narrow screens.
- Keep user theme resolution and offered choices synchronized with the public admin settings after a successful save and on return to the application.
- Update a personal deployment ZIP and verify it on localhost:5173; keep its assets outside the PR.
- Organize new theme archives with `theme-catalog.json` at the root, one `themes/<id>/` directory per custom theme, and `shared/` for content that applies to every theme. Keep existing flat archives installable.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-ui-themes`: theme-local browser tab metadata and validation.
- `platform-ui-theme-settings`: readable default state and refreshed user choices after admin changes.

## Impact

Frontend catalog validation, shared ZIP installer and archive builder, browser tab effect, application theme provider, existing generated public-config query and invalidation, admin page/CSS, tests and existing theme documentation. No backend contract or migration, editor or new storage loading mechanism. Reuse branch feat/ui-theme-customization, issue #3027 and draft PR #3028.
