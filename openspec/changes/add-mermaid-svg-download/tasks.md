## 1. Export and controls

- [ ] 1.1 Extend the Mermaid SVG preparation area with standalone serialization; verify resolved theme styles, full bounds, labels and local references for preferred and compatibility output, without changing the live SVG.
- [ ] 1.2 Add inline/fullscreen download icons and English/French labels using the existing Blob download helper; verify keyboard/form behavior, unavailable rendering, current theme selection and localized export-failure feedback in component tests.

## 2. Verification and delivery

- [ ] 2.1 Download flowchart, HTML-label ER, pie and Gantt examples from localhost in light/dark modes and reopen the files outside Fred; verify complete diagrams, readable colors, local markers and retained fullscreen state.
- [ ] 2.2 Run affected tests, production build, root code-quality and migration validation; fix failures and record results in the existing PR.
- [ ] 2.3 Update component UX and the existing migration note, perform author/independent review of the added export contract, and record review coverage and dispositions in the PR.
- [ ] 2.4 Reconcile tasks/specs with verified behavior, sync and archive this change, then commit/push to the existing draft PR; verify clean worktree and published head.
