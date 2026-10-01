## 1. Chat header action

- [x] 1.1 Add a localized new-conversation icon button with a tooltip to the right side of the managed chat header and connect it to the existing session transition; verify an open session reaches the empty chat for the same agent without a new session POST.
- [ ] 1.2 Apply the shared spectrum border with a neutral rest state, interaction-only animation, and a reduced-motion fallback; verify light/dark themes, keyboard focus, and a narrow header in the UI.

## 1b. Agent identity in the empty chat

- [x] 1.3 Show the agent's icon, name, and role above the greeting of every empty conversation, stacked and centred (round icon, `title-medium` name, `body-medium` role); hide the conversation header until a session is bound; extend the page tests to assert name, role and no header for a new conversation, and a kept header for a bound empty session.
- [ ] 1.4 Verify the identity block in the UI: light/dark themes, a long name or role, and a narrow viewport.

## 2. Verification and documentation

- [x] 2.1 Add focused page tests for the action's visibility and activation, including its absence in the empty state; run the targeted Vitest file and confirm the existing session-switch hook tests still pass.
- [x] 2.2 Update `docs/swift/ux/COMPONENT-UX.md` and add the required English migration note; verify they describe the delivered UI and that no operator action is needed.
- [x] 2.3 Run the root code-quality gate once before commit, validate the OpenSpec change strictly, and record exact verification results in this checklist.

Verification (2026-09-30): targeted Vitest 65 passed; frontend `make test` 2,982 passed,
7 skipped; Sass compiled; `make migration-check` accepted 1 new note; root
`make code-quality` passed all modules with a global `uv` override for the
fresh worktree; `openspec validate --strict` passed. Browser-based visual review
remains unavailable in this environment.

Verification (2026-10-01, after the icon-button and agent-identity changes, rebased on
`swift`): root `make code-quality` passed all modules (global `uv` override); frontend
`make test` 3,148 passed, 7 skipped; full Vitest rerun on the final tree 3,148 passed,
7 skipped; `tsc`, eslint and Prettier clean; `make migration-check` accepted 1 new note;
`openspec validate --strict` passed. Tasks 1.2 and 1.4 await the visual check in review.
