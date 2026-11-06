## 1. Contract and runtime

- [x] 1.1 Add optional `RuntimeContext.attachments` (`attachment_id`, `name`, `mime?`) in fred-sdk, with a test.
- [x] 1.2 Store it as `metadata.extras.attachments` on the user row in `_write_turn_history`, with a test.
- [x] 1.3 Regenerate the runtime client: `cd apps/frontend && make update-runtime-api`.

## 2. Frontend

- [x] 2.1 Send this turn's ready attachments in `sendTurn`, keep them on the optimistic row and on restart; no send without text.
- [x] 2.2 Map `extras.attachments` in `toThreadMessages`; render tonal chips in `UserMessage`, with tests.

## 3. Close-out

- [x] 3.1 Root `make code-quality`, `make test` in frontend (5119), fred-sdk (668), fred-runtime (2537); `openspec validate --strict`.
- [x] 3.2 `RUNTIME-EXECUTION-CONTRACT.md` §2.3 line and dated §8 entry; migration note (impact none).
- [x] 3.3 Help Center `features/chat.md` (fr+en) checked: still accurate.
