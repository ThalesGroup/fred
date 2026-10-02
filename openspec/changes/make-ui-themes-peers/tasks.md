## 1. Pebble as a theme file

- [x] 1.1 Create `styles/themes/pebble.css` with Pebble's semantic colors (from `colors-semantic-light.css` / `colors-semantic-dark.css`), font family (from `typography.css`) and radius scale (from `radius.css`), and remove those values from the base files; verify the app renders Pebble unchanged in both modes (visual check on agents, resources, chat pages)
- [x] 1.2 Make `themes/cobalt.css` and `themes/cloud.css` declare every token Pebble declares (font family, full radius scale, any semantic token they inherited); verify both themes render unchanged in both modes
- [x] 1.3 Import order in `styles/index.css`: base first, then every theme file; verify `npx tsc --noEmit` and `npx prettier --check` pass

## 2. Completeness test

- [x] 2.1 Add a vitest test that compares the custom properties declared by each theme per block (root, light, dark) and asserts the base files declare none of them; verify it passes, then fails with the theme, mode and token named when one token is removed from a theme

## 3. Theme before the first paint

- [x] 3.1 Add `public/theme-boot.js` and load it from `<head>` in `index.html`: resolve the stored theme (catalog or default) and mode (stored or OS) and set `data-ui-theme` / `data-theme` on `<html>`, tolerating unavailable localStorage; give `html` the `--surface-main` background; verify a reload in Cloud dark shows no frame in another theme (Performance panel screenshots)
- [x] 3.2 Make `ApplicationContextProvider` resolve theme and mode with the same rules and a single exported catalog constant; add unit tests that the boot script's catalog matches it and that the theme files in `styles/themes/` match the catalog; verify the tests for `src/app` pass
- [x] 3.3 Verify an unknown stored theme (`"corporate"`) resolves to `pebble` before the first paint and in React

## 4. Design tokens package

- [x] 4.1 Point `libs/frontend/scripts/package-inputs.mjs` at `themes/pebble.css` and rewrite Pebble's selectors to the permitted package selectors during the build, and point the `frontend-packages` path filter in `.github/workflows/Check-pending-requests.yml` at `themes/pebble.css`; verify `npm run build:tokens` and the existing token contract tests pass
- [x] 4.2 Add a test that the rebuilt package declares the same token names and values as before the change; verify it passes

## 5. Docs and close-out

- [x] 5.1 Update the theme section of `docs/swift/platform/FRONTEND_CODING_GUIDELINES.md` (one file per theme, complete token set, base contents) and the stale `colors-semantic-*.css` references in `docs/swift/design/CHAT-COMPONENT-SPECS.md` and `docs/swift/ux/COMPONENT-UX.md` and add a migration note with `impact: none`; verify `make migration-check` passes
- [ ] 5.2 Run `npx tsc --noEmit`, prettier, eslint and the frontend vitest suites for `src/app`, `src/styles` and `libs/frontend`; record the evidence in `verification.md`
