## 1. Chat header action

- [x] 1.1 Add a localized, labelled new-conversation button to the right side of the managed chat header and connect it to the existing session transition; verify an open session reaches the empty chat for the same agent without a new session POST.
- [ ] 1.2 Apply the shared spectrum border with a neutral rest state, interaction-only animation, and a reduced-motion fallback; verify light/dark themes, keyboard focus, and a narrow header in the UI.

## 2. Verification and documentation

- [x] 2.1 Add focused page tests for the action's visibility and activation, including its absence in the empty state; run the targeted Vitest file and confirm the existing session-switch hook tests still pass.
- [x] 2.2 Update `docs/swift/ux/COMPONENT-UX.md` and add the required English migration note; verify they describe the delivered UI and that no operator action is needed.
- [x] 2.3 Run the root code-quality gate once before commit, validate the OpenSpec change strictly, and record exact verification results in this checklist.

Verification (2026-09-30): targeted Vitest 65 passed; frontend `make test` 2,982 passed,
7 skipped; Sass compiled; `make migration-check` accepted 1 new note; root
`make code-quality` passed all modules with a global `uv` override for the
fresh worktree; `openspec validate --strict` passed. Browser-based visual review
remains unavailable in this environment.
