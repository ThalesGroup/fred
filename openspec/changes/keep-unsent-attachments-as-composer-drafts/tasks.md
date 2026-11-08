## 1. Composer drafts

- [x] 1.1 Tag each local chip with the conversation it was ingested for; show and send only the current conversation's chips.
- [x] 1.2 Derive sent attachment ids from the loaded user messages, plus rows created before the latest user message.
- [x] 1.3 Restore unsent rows of the conversation as ready composer chips.
- [x] 1.4 Feed the drawer, its count and `attachments_markdown` from sent attachments plus the turn's own files.

## 2. Verification

- [x] 2.1 Unit tests: switch conversation with a draft (a), leave and come back (b), legacy conversation without attachment metadata.
- [x] 2.2 `make code-quality` and `make test` in `apps/frontend`.
- [x] 2.3 Manual UI check of (a) and (b) with the developer (2026-11-08: both fixed).

## Evidence

- `vitest run` (apps/frontend): 417 files, 5144 tests passed, 8 skipped (after the independent review fixes). New: `splitSessionAttachments` (no messages, listed id, legacy rule), hook keeps a file in its own conversation, `useManagedChat` shows drafts in the composer and sent rows in the drawer, sends restored drafts, treats every row as sent without history, refuses a drop while a message is queued; the legacy cutoff ignores HITL answers, steered and optimistic rows; a send leaves other conversations chips alone.
- `tsc --noEmit`, `prettier --write`, `eslint` on touched files: clean. Run directly, not through `make`, because a dev Vite server was running.
