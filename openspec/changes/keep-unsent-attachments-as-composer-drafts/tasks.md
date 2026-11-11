## 1. Composer drafts

- [x] 1.1 Tag each local chip with the conversation it was ingested for; show and send only the current conversation's chips.
- [x] 1.2 Derive sent attachment ids from the loaded user messages, plus rows created before the latest legacy composer message.
- [x] 1.3 Restore unsent rows of the conversation as ready composer chips.
- [x] 1.4 Feed the drawer, its count and `attachments_markdown` from sent attachments plus the turn's own files.
- [x] 1.5 Record empty attachment lists on new user turns and preserve later composer drafts across an interrupted turn's restart.

## 2. Verification

- [x] 2.1 Unit tests: switch conversation with a draft (a), leave and come back (b), legacy conversation without attachment metadata.
- [x] 2.2 `make code-quality` and `make test` in `apps/frontend`.
- [x] 2.3 Manual UI check of (a) and (b) with the developer (2026-11-08: both fixed).

## Evidence

- Full frontend suite before the final restart correction: 418 test files, 5138 tests passed, 8 skipped. After the correction: 219 focused tests passed, plus typecheck, lint and format.
- Runtime attachment history tests: 2 focused cases passed; Ruff check passed. Root `make code-quality` reached Knowledge Flow dependency downloads and could not finish in this environment.
