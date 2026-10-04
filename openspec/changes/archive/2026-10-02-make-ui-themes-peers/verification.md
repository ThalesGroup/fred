# Verification: make-ui-themes-peers

Commits on `ui-theme-polish`: `10ae95e5e` (Pebble as a theme file, completeness test, design tokens
package), `851fba251` (theme before the first paint, docs, migration note).

## Themes are peers / complete token set

- `apps/frontend/src/styles/themes/themes.test.ts` (6 tests): every theme has root, light and dark
  blocks, all themes declare the same tokens per block, light and dark declare the same tokens,
  each mode block sets its `color-scheme`, and no base stylesheet (`src/styles/*.{css,scss}`,
  `src/styles.css`, `src/index.scss`) declares a theme token.
- Mutation check: removing `--tertiary-container` from Cloud's dark block fails the test with
  `cloud dark lacks --tertiary-container`.
- On first run the test found `--scrim` and `--surface-picture` inherited from Pebble by Cobalt and
  Cloud; both now declare them with Pebble's values.
- Rendering unchanged: a script resolved the effective value of every custom property for each theme
  and mode at `HEAD` before the refactor and after it (cascade with specificity, `var()` resolved):
  0 differences for pebble, cobalt and cloud, light and dark. The visual check in tasks 1.1/1.2 is
  replaced by this comparison; a visual pass in the running app is still recommended.

## Theme applied before the first paint

- `apps/frontend/src/app/uiThemes.test.ts` (12 tests): `public/theme-boot.js` run in `node:vm`
  against a fake browser agrees with `resolveUiTheme` / `computeDarkMode` on a case table (stored
  theme and mode, unknown theme `corporate`, nothing stored, `system` mode, garbage values, storage
  throwing, no `matchMedia`); the script reads the exact keys `useLocalStorageState` writes; the
  catalog matches the script's copy and the files in `src/styles/themes/`.
- `apps/frontend/src/app/themeBoot.e2e.test.tsx`: the real `ApplicationContextProvider` stores Cloud
  and dark, then the boot script run against that storage sets `cloud` / `dark`. Reverting the
  script to unprefixed keys fails this test (the bug an independent review found before commit).
- Headless Chromium against the dev server with the app bundle blocked (so only the boot script
  ran), storage written under the hook's keys: `<html>` already carried the right theme, mode, theme
  tokens and page background for cloud/dark on a light OS, cobalt/light on a dark OS,
  pebble/system on a dark OS, and an unknown `corporate` (resolved to pebble).
- Production `vite build`: `<script src="/theme-boot.js">` stays in `<head>` before the module
  bundle and the stylesheet link; `theme-boot.js` is copied to the build root.
- `apps/frontend/tests/application-proxy-smoke.sh` passes and asserts nginx serves
  `/theme-boot.js` with `Cache-Control: no-cache`.
- eslint parses `public/**/*.js` as ES5 (a `const` probe fails); the `lint` Make target covers it.

## Design tokens package unchanged

- Built output before and after the refactor compared per selector: same 4 selectors, 0 differing
  token names or values.
- `libs/frontend/tests/build-design-tokens.test.mjs`: new test that every Pebble token is published
  under `:root` / `[data-theme="light"]` / `[data-theme="dark"]` with the same value; the canonical
  source order test applies the same selector rewrite.
- `cd libs/frontend && npm test`: 377 tests, 376 pass, 1 skipped, 0 fail.
- Divergence from task 4.2: no frozen snapshot of the pre-change package was committed (it would
  fail on every intended token change); the one-off comparison above plus the durable test cover it.

## Suites

- `cd apps/frontend && npx tsc --noEmit`: clean. `npx prettier --check` on touched files: clean.
  `npx eslint` (src + public): clean.
- `npx vitest run` (whole frontend): 3179 passed, 7 skipped, 4 failed. The 4 failures are in
  `src/rework/core/hooks/useChatSse.test.tsx` (first-turn `ask_user` availability), untouched by
  this change and already failing on `swift`.
- `make migration-check`: valid (`docs/swift/ops/migrations/ui-themes-as-peers.md`, impact none).

## Reviews

Two independent review agents: the first (tasks 1-2) found no blocker and led to the CI path
filter, wider doc task and wider leak scan; the second (task 3) found the storage-key blocker, the
caching and ES5 issues, all fixed and re-reviewed as clear to commit.

## Not verified

- A visual pass in the running app by a person (Pebble, Cobalt, Cloud in both modes) and a reload
  recorded in the browser Performance panel.
