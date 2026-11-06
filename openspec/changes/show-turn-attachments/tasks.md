## 1. Contract and runtime

- [ ] 1.1 Add optional `RuntimeContext.attachments` (`attachment_id`, `name`, `mime?`) in fred-sdk, with a test.
- [ ] 1.2 Store it as `metadata.extras.attachments` on the user row in `_write_turn_history`, with a test.
- [ ] 1.3 Regenerate the runtime client: `cd apps/frontend && make update-runtime-api`.

## 2. Frontend

- [ ] 2.1 Send this turn's ready attachments in `sendTurn` and keep them on the optimistic user row.
- [ ] 2.2 Map `extras.attachments` in `toThreadMessages`; render read-only chips in `UserTurn`, with tests (live, reload, absent field).

## 3. Verification and close-out

- [ ] 3.1 `make code-quality` and `make test` in touched projects; `openspec validate show-turn-attachments --strict`.
- [ ] 3.2 Dated §8 entry and a line next to skill selections in `RUNTIME-EXECUTION-CONTRACT.md`.
- [ ] 3.3 Migration note in `docs/swift/ops/migrations/` (no operator action, patch).
- [ ] 3.4 Help Center: no update expected (chips are self-explanatory); confirm `features/chat.md` fr+en stays accurate.
