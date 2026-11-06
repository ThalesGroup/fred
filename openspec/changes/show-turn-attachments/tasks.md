## 1. Contract and runtime

- [x] 1.1 Add optional `RuntimeContext.attachments` (`attachment_id`, `name`, `mime?`) in fred-sdk, with a test.
- [x] 1.2 Store it as `metadata.extras.attachments` on the user row in `_write_turn_history`, with a test.
- [x] 1.3 Regenerate the runtime client: `cd apps/frontend && make update-runtime-api`.

## 2. Frontend

- [x] 2.1 Send this turn's ready attachments in `sendTurn`, keep them on the optimistic user row, re-send them on restart, and block a send without text.
- [x] 2.2 Map `extras.attachments` in `toThreadMessages`; render read-only tonal chips inside the bubble in `UserMessage`, with tests (live, reload, absent field, restart, no text).

## 3. Verification and close-out

- [x] 3.1 `make code-quality` and `make test` in touched projects; `openspec validate show-turn-attachments --strict`.
- [x] 3.2 Dated §8 entry and a line next to skill selections in `RUNTIME-EXECUTION-CONTRACT.md`.
- [x] 3.3 Migration note in `docs/swift/ops/migrations/` (no operator action, patch).
- [x] 3.4 Help Center: no update expected (chips are self-explanatory); confirm `features/chat.md` fr+en stays accurate.

## Verification

- fred-sdk, fred-runtime: `make code-quality` and `make test` green; new tests in `tests/test_context.py` and `tests/test_history.py`.
- frontend: `make code-quality` and `make test` green; new tests in `UserTurn.test.tsx`, `toThreadMessages.test.ts`, `runtimeContextBuilder.test.ts`, `useManagedChat.test.tsx`.
- Help Center `features/chat.md` (fr+en) unchanged: still accurate.
