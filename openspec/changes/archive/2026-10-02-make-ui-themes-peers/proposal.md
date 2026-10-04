## Why

The frontend now ships three UI themes (Pebble, Cobalt, Cloud), but Pebble is not a theme like the
others: its colors, font and radius scale live in the base stylesheets, and Cobalt and Cloud only
override them. Pebble therefore cannot be hidden or removed, any token another theme forgets
silently falls back to Pebble, and the theme attribute is only set during the first React render, so
the page can paint in the wrong theme before that. A platform-wide theme setting (follow-up change
`add-platform-ui-theme-settings`) needs every theme to be a peer and the theme to be known before
anything is painted.

## What Changes

- Pebble moves out of the base stylesheets into its own theme definition, alongside Cobalt and
  Cloud. Every theme defines the complete set of theme tokens (semantic colors for light and dark,
  font family, radius scale); the base keeps only theme-independent tokens.
- A test fails when a theme is missing a token another theme defines, or defines one the others do
  not.
- The theme and the light/dark mode are applied to the document before the first paint, from the
  user's stored choice, so the application never paints in another theme first. An unknown stored
  theme resolves to the default theme.
- The `@fred-oss/design-tokens` package keeps its published contract and values (Pebble, exposed
  under `[data-theme]`), so SDK consumers and hosted applications see no change.

## Capabilities

### New Capabilities

- `frontend-ui-themes`: the set of UI themes the frontend ships, what a theme must define, and how
  the active theme and mode are resolved and applied before the first paint.

### Modified Capabilities

None.

## Impact

- `apps/frontend/src/styles/`: `colors-semantic-light.css`, `colors-semantic-dark.css`,
  `radius.css`, `typography.css` lose their theme values; new `themes/pebble.css`;
  `themes/cobalt.css` and `themes/cloud.css` become complete definitions.
- `apps/frontend/index.html` and a new static boot script under `apps/frontend/public/`;
  `ApplicationContextProvider` theme resolution.
- `libs/frontend/scripts` (design tokens build) reads Pebble from its theme file; published output
  unchanged.
- Docs: `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` (theme section).
- Migration note: frontend only, `impact: none`.
- Tracking: #2933 (milestone swift-v4); builds on #2915.
