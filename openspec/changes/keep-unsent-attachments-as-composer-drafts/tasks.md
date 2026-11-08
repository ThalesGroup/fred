## 1. Composer drafts

- [ ] 1.1 Tag each local chip with the conversation it was ingested for; show and send only the current conversation's chips.
- [ ] 1.2 Derive sent attachment ids from the loaded user messages, plus rows created before the latest user message.
- [ ] 1.3 Restore unsent rows of the conversation as ready composer chips.
- [ ] 1.4 Feed the drawer, its count and `attachments_markdown` from sent attachments plus the turn's own files.

## 2. Verification

- [ ] 2.1 Unit tests: switch conversation with a draft (a), leave and come back (b), legacy conversation without attachment metadata.
- [ ] 2.2 `make code-quality` and `make test` in `apps/frontend`.
- [ ] 2.3 Manual UI check of (a) and (b) with the developer.
