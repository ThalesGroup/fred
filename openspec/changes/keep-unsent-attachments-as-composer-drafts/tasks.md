## 1. Composer drafts

- [x] 1.1 Tag each local chip with the conversation it was ingested for; show and send only the current conversation's chips.
- [x] 1.2 Derive sent attachment ids from the loaded user messages, plus rows created before the latest legacy composer message.
- [x] 1.3 Restore unsent rows of the conversation as ready composer chips.
- [x] 1.4 Feed `attachments_markdown` from sent attachments plus the turn's own files.
- [x] 1.5 Record empty attachment lists on new user turns and preserve later composer drafts across an interrupted turn's restart.
- [x] 1.6 Show successfully ingested composer drafts in the conversation drawer and its badge without adding them to earlier turns' agent context.

## 2. Verification

- [x] 2.1 Unit tests: switch conversation with a draft (a), leave and come back (b), legacy conversation without attachment metadata.
- [x] 2.2 `make code-quality` and `make test` in `apps/frontend`.
- [x] 2.3 Manual UI check of (a) and (b) with the developer (2026-11-08: both fixed).
- [x] 2.4 Unit-verify the badge and drawer after ingestion and reload, while drafts remain excluded from earlier turns.

## Evidence

- Full frontend suite before the final restart correction: 418 test files, 5138 tests passed, 8 skipped. After the correction: 219 focused tests passed, plus typecheck, lint and format.
- Runtime attachment history tests: 2 focused cases passed; Ruff check passed. Root `make code-quality` reached Knowledge Flow dependency downloads and could not finish in this environment.
- Follow-up #3633: 170 focused frontend tests passed. `make code-quality` passed. `make test` twice hit 5-second timeouts in the unrelated SQL trace rendering suite; its 26 tests passed in isolation, and the full Vitest suite passed with a 30-second timeout (5,394 passed, 8 skipped). Application proxy and theme checks passed.
