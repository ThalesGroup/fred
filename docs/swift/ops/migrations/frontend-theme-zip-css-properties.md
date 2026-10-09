---
schema: 1
title: "Read theme CSS, branding properties and labels from the frontend ZIP"
impact: operations
configuration: none
configuration_reason: "The existing FRONTEND_THEME_URL and SeaweedFS object are reused."
---

## Applicability

Frontend deployments using a theme ZIP through `FRONTEND_THEME_URL`.

## Prerequisites

The ZIP remains reachable by the frontend container. No database migration is required.

## Configuration

The existing SeaweedFS object may now include `theme-custom.css`, `theme-properties.json` and `theme-translations/en.json` or `fr.json`. Only branding labels and asset names are accepted in the properties JSON; see `apps/frontend/README.md`. No new environment variable is required.

The ZIP may also include `theme-catalog.json` to declare several additional selectable themes. Each entry has a unique `id`, display `label`, and `base` (`pebble`, `cobalt`, or `cloud`). For light and dark overrides, use `[data-ui-theme="<id>"][data-ui-base-theme="<base>"][data-theme="light"]` and its dark counterpart. The base attribute gives ZIP CSS priority over shipped CSS while letting admin previews match. The new choices appear after frontend pods restart and browsers reload; existing platform defaults and hidden-theme settings can select them.

## Upgrade

Deploy the new frontend image. To activate overrides, upload a ZIP with the optional files to the object configured by `FRONTEND_THEME_URL`, then restart the frontend pods. Existing ZIPs containing only images and Markdown continue to work.

## Validation

Open the frontend in a fresh browser session and verify the browser tab name, selected image names, translated UI labels and light/dark theme CSS. Check that the theme CSS, properties and translation URLs serve the ZIP content. The frontend container logs `Theme installed from ...` when the ZIP is accepted.

## Rollback

Restore the previous ZIP and restart frontend pods, or remove the optional files from the ZIP. No data rollback is needed.

## Limitations

Replacing the SeaweedFS object does not update already running pods; they must restart. Connected browsers then reload to receive the new values.
