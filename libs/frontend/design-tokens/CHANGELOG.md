# Design tokens changelog

## 0.1.0-alpha.2

Review: approved
Changes: Rework the neutral palette and surface scale (#2915, #2941). The `--core-cold-grey-*` ramp is a discreet blue-grey (CIE LCh chroma 1.5, hue 280°) with new steps 99.5, 97.5, 94.5, 45 and 25. In both themes the `--surface-container-*` levels get lighter from `-lowest` to `-highest`; `--surface-main` is set apart for text contrast (light 99.5, dark 6). New `--surface-floating` for menus, popovers, tooltips, dialogs and toasts, and new `--radius-ms` (12px). Secondary text is lighter. Breaking: `--outline-retreat`, the `--color-*` aliases and `--state-surface-main-*` are removed; replacements are listed in the README "Token migrations" section. The published token output keeps the same `:root` / `[data-theme]` selectors.

## 0.1.0-alpha.1

Review: approved
Changes: Initial published design-token archive; factual integrity and provenance are recorded in [RELEASE.md](../RELEASE.md#completed-first-release-evidence-historical-not-active-configuration).
