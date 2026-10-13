# Design

## Context

See proposal.md. `theme-properties.json` is global. `FredUiContent` sets the browser title/favicon from those properties; custom catalog entries currently accept only id/label/base. The application provider reads a startup module snapshot, while admin mutations invalidate only the admin query. Existing cross-session refresh helpers implement 60-second polling and explicit focus refresh.

## Goals / Non-Goals

**Goals:** isolate tab metadata by theme; propagate saved visibility/default settings to user selection; make the admin state legible and responsive; make multi-theme ZIPs understandable through one folder per theme and a separate shared folder.

**Non-Goals:** per-theme translations, an editor, automatic ZIP replacement polling, backend changes or hiding every available theme.

## Decisions

- Extend each custom catalog entry with optional `tabTitle`, `faviconName`, `faviconNameDark`. Titles are nonblank strings of at most 200 characters; favicon values are SVG basenames (letters/digits/underscore/hyphen, at most 128 characters), served from the existing images surface. Omitted fields retain global defaults; when only the light icon is supplied, reuse it in dark mode. Validate it in the shared installer only: every served catalog passes through it, and these values only reach the tab title and an image path. A global branding map was rejected because it duplicates the catalog's identity.
- The existing `App.tsx` tab effect resolves these fields from the active theme and mode through a pure `uiThemeTab` helper. Switching back to a stock theme restores global tab branding. Keep CSS-scoped Paris artwork and global neutral translations unchanged.
- Subscribe the application provider to the existing generated public-config query with startup settings as the initial fallback. Tag it with the existing UI settings tag so successful saves refresh the same Redux store. Reuse cross-session refresh helpers for 60-second polling and focus refresh. Preserve the last successful settings during a network error. Resolve choices with the same catalog/filter everywhere, preserving hidden stored preferences for later restoration. No extra store or handwritten backend types.
- Preserve the existing safeguard that ignores the hidden list when no installed theme would remain. Count custom and built-in themes together; preserve unknown IDs on admin saves.
- Replace the disabled default action with a high-contrast status badge and tile border. Other offered themes retain an explicit set-default action. Label the light/dark previews and availability control using existing localized vocabulary; wrap the layout on narrow screens.
- Accept a structured ZIP with `theme-catalog.json` at its root, `themes/<id>/theme-custom.css` and `themes/<id>/images/**` for each catalog entry, and `shared/` for global properties, translations, legal markdown, and shared images. The installer assembles these into the existing served paths, keeping browser URLs and frontend consumers stable. It concatenates theme CSS in directory name order, preserving theme-scoped selectors; copies images into the existing images surface and rejects conflicting names rather than silently overwriting another theme. A theme folder must match a catalog id; reject unknown or duplicate theme folders. Flat ZIPs remain supported for existing deployments. The bundled example and archive builder use the structured layout; the builder reports layout errors before packaging.

## Risks / Trade-offs

- Old frontend images reject new catalog keys: upgrade the frontend before uploading the revised personal ZIP. Existing ZIPs remain compatible.
- Two themes may contain identically named images. Reject those archives with a clear filename error and document unique image names; do not let ZIP entry order choose which asset wins.
- Newly hidden active themes can change a connected user's appearance: apply the documented resolution without erasing their preference.
- Refetch failures must not reset the selection or expose hidden themes: retain the startup/last good configuration and test this transition.

## Migration Plan

Update the existing operator note and packaging example. Add tab metadata only to the personal Paris ZIP outside Git, upload it to local SeaweedFS and restart Vite. Roll back by removing the three optional fields and using the previous frontend. No database change.
