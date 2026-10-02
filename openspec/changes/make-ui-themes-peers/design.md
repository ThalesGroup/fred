## Context

See proposal.md for motivation. Current state:

- `styles/colors-semantic-light.css` / `colors-semantic-dark.css` define Pebble's semantic colors
  under `[data-theme="light|dark"]`, mapped onto the neutral and accent ramps of
  `styles/color-ramps.css`. `radius.css` and `typography.css` define Pebble's radius scale and font
  family on `:root`.
- `styles/themes/cobalt.css` and `styles/themes/cloud.css` override those tokens under
  `[data-ui-theme="<id>"][data-theme="<mode>"]` (colors) and `:root[data-ui-theme="<id>"]` (font,
  radii), with literal hex values generated from LCh seeds.
- `ApplicationContextProvider` reads the theme and mode from localStorage
  (`ApplicationContextProvider.uiTheme`, `ApplicationContextProvider.themeMode`, JSON-encoded) and
  `App.tsx` sets `data-theme` / `data-ui-theme` during the first React render, after
  `loadConfig()` and the Keycloak login have completed.
- `@fred-oss/design-tokens` is built by `libs/frontend/scripts/build-design-tokens.mjs` from a fixed
  list of style files (`package-inputs.mjs`); `token-css-contract.mjs` only allows `:root`,
  `[data-theme="light"]` and `[data-theme="dark"]` selectors.

## Goals / Non-Goals

**Goals:**

- One file per theme, all with the same shape; the base holds only theme-independent tokens.
- Theme and mode on `<html>` before the first paint, for every visit where a choice is stored.
- No change to the published token package.

**Non-Goals:**

- Platform default and hidden themes (change `add-platform-ui-theme-settings`).
- Passing the UI theme to hosted applications (they keep receiving `light` / `dark` only).
- Changing any theme's visible values.

## Decisions

**Theme file shape.** Each `styles/themes/<id>.css` holds three blocks:
`:root[data-ui-theme="<id>"]` (font family, radius scale), and
`[data-ui-theme="<id>"][data-theme="light|dark"]` (semantic colors). Pebble keeps referencing the
`--core-*` ramps; `color-ramps.css` stays in the base as a raw palette any theme may use (Cobalt and
Cloud keep literal values). Alternative considered: keep Pebble in the base and treat it as "the
default"; rejected, it is exactly the asymmetry this change removes.

**What stays in the base.** Spacing, motion, gradients, the `--core-*` ramps, the state-layer
tokens (`colors-state-semantic.css`, derived from the semantic tokens with `color-mix`, so they
follow any theme) and the light/dark shadows. Shadows stay per mode, not per theme; a theme may
override them later.

**Completeness test.** A vitest test reads every file in `styles/themes/`, collects the custom
properties declared per block (root, light, dark) and asserts all themes declare identical sets,
reporting theme, mode and token on mismatch. It also asserts the base files declare none of those
tokens. Alternative considered: a hand-maintained token list; rejected, the themes themselves are
the list and the test only has to compare them.

**Applying the theme before the first paint.** A small static script,
`public/theme-boot.js`, is loaded synchronously from `<head>` in `index.html`, before the
stylesheets. It reads the two localStorage keys (same JSON encoding as `useLocalStorageState`),
resolves the theme against the catalog and the mode against `prefers-color-scheme`, and sets
`data-ui-theme` and `data-theme` on `<html>`. React keeps owning the attributes after mount and
resolves them with the same rules. `html` gets `background: var(--surface-main)` so the area outside
`body` never shows an unthemed color.

- A static file rather than an inline script so a deployment CSP with `script-src 'self'` still
  allows it. The repo ships no CSP today, but customer overlays may add one.
- The catalog list in the boot script and in `ApplicationContextStruct` must stay identical; a unit
  test compares them (the boot script exports nothing, so the test reads its source).

**Design tokens package.** `package-inputs.mjs` points at `themes/pebble.css` instead of the two
semantic files, and the build rewrites Pebble's selectors to the package's permitted ones
(`[data-ui-theme="pebble"][data-theme="light"]` → `[data-theme="light"]`,
`:root[data-ui-theme="pebble"]` → `:root`). Other themes are not packaged. A test compares the
rebuilt token set (names and values) with the one produced before the change.

## Risks / Trade-offs

- [The boot script and React disagree] → both use the same catalog constant (checked by test) and the
  same resolution rules; React re-applies on mount, so a disagreement would show as one change, not
  a broken page.
- [localStorage unavailable (private mode, blocked storage)] → the boot script catches the error and
  falls back to the default theme and the OS mode.
- [A blocking script in `<head>` delays the first paint] → it is a few hundred bytes, no network
  call, no dependency. Served with `Cache-Control: no-cache` so it is never stale: each load pays
  one revalidation round trip (304), accepted for a script that decides the first frame.
- [Package consumers relied on `colors-semantic-*.css` file paths] → only the built output is
  published, not the source paths; the output is unchanged.

## Migration Plan

Frontend-only; ships with the frontend image. Users keep their stored choice. Rollback is the normal
image rollback. Migration note with `impact: none`.
