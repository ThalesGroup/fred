## 1. Export and controls

- [x] 1.1 Extend the Mermaid SVG preparation area with standalone serialization; verify resolved theme styles, full bounds, labels and local references for preferred and compatibility output, without changing the live SVG.
- [x] 1.2 Add inline/fullscreen download icons and English/French labels using the existing Blob download helper; verify keyboard/form behavior, unavailable rendering, current theme selection and localized export-failure feedback in component tests.

## 2. Verification and delivery

- [x] 2.1 Download flowchart, HTML-label ER, pie and Gantt examples from localhost in light/dark modes and reopen the files outside Fred; verify complete diagrams, readable colors, local markers and retained fullscreen state.
- [x] 2.2 Run affected tests, production build, root code-quality and migration validation; fix failures and record results in the existing PR.
- [x] 2.3 Update component UX and the existing migration note, perform author/independent review of the added export contract, and record review coverage and dispositions in the PR.
- [ ] 2.4 Reconcile tasks/specs with verified behavior, sync the main spec, then commit/push to the existing draft PR; verify clean worktree and published head.

Archive the completed change afterward under the repository close-out policy.

Verification: 65 affected tests and 4,481 frontend tests passed (8 skipped); production build, all 17 modules of root code-quality and migration validation passed. Eight actual flowchart/HTML-label ER/pie/Gantt SVG downloads from light/dark UI reopened outside Fred with white backgrounds, readable selected-theme light colors, complete labels and local references. Fullscreen remains open after download. Author audit covered the actual swift-based branch and consumers; independent read-only download review found no actionable issue and reran 16 component/serialization tests. Review scope, previous findings and limitations are recorded in PR #3256. Main spec sync passed strict capability validation and normal validation of all 34 specs.
