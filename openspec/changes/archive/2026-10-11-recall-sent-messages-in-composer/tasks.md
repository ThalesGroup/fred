## 0. Preconditions

- [x] 0.1 GitHub issue #3038 created and linked in proposal.md; branch `feat/composer-message-recall` from swift.

## 1. Recall

- [x] 1.1 `useComposerRecall` hook in `ManagedChatPage`: recall lines from the thread's user rows (command turns rebuilt as `/command appended`, empty rows skipped, consecutive duplicates collapsed), derived browsing index, ArrowUp / ArrowDown / past-newest empties, ignored with a modifier, during IME composition, with the menu open or a disabled composer. Verify: `useComposerRecall.test.tsx` covers every scenario of the delta spec.
- [x] 1.1b `useComposerCommands`: `dismiss(line)` marks a recalled line's query as dismissed; the dismissal clears as soon as the query changes to another value. Verify: `useComposerCommands` tests (recalled `/summary` keeps the menu shut, Backspace reopens it, Esc then delete-and-retype reopens it).
- [x] 1.2 `RichInputField`: optional `onRecallKeyDown` handler called after `commandTrigger`; the caret goes to the end through the existing `focusEndRequestId`. Verify: `useComposerRecall.test.tsx` mounts the real field with the menu (open menu keeps the arrows; caret at the end).
- [x] 1.3 Wire the hook in `ManagedChatPage` with `threadMessages`, `input`, `setInput` and the menu state. Verify: `ManagedChatPage` test recalling a sent message and a command turn as typed.

## 2. Docs and close-out

- [x] 2.1 `docs/swift/ux/COMPONENT-UX.md` (composer keyboard, next to "Prompt commands in the composer") and fr/en Help Center `features/chat.md` (one short paragraph). Verify: both locales updated.
- [x] 2.2 Migration note, impact `none`. Verify: migration note check valid.
- [x] 2.3 Quality gates with npx (not the make targets): `tsc --noEmit`, `prettier --check src`, `vitest run`. Verify: all green, counts recorded here. Done 2026-10-10: tsc and prettier clean; vitest 303 files, 3523 passed, 7 skipped (after the menu-flash fix); migration note check valid.
- [x] 2.4 Owner check in the app. Verify: owner confirmation. Done: owner ran the 19-step manual checklist on 2026-10-10, all passed.
- [x] 2.5 Archive after merge. Verify: `openspec validate recall-sent-messages-in-composer --strict`.
