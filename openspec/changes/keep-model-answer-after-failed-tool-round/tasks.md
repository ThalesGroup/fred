Tracks GitHub issue #2588. Status lives on the issue; this checklist covers this slice only.

## 1. Runtime

- [x] 1.1 Stop suppressing assistant deltas after a wholly-failed round.
- [x] 1.2 Use the model's non-empty answer after the last claimed error as the final
      content; fall back to the claimed error text only when there is none.

## 2. Tests

- [x] 2.1 Cap refusal (`status="error"`, no artifact) followed by a model answer.
- [x] 2.2 Typed `is_error=True` result followed by a model answer.
- [x] 2.3 Wholly-failed round with no model answer keeps the error fallback.
- [x] 2.4 Answer deltas stream after a failed round.
- [x] 2.5 Update the §8.42/§8.74 tests whose final assertions assumed the override,
      keeping their tool-row and leak assertions.

## 3. Docs and verification

- [x] 3.1 Dated entry in `RUNTIME-EXECUTION-CONTRACT.md` §8; migration note.
- [x] 3.2 `make test`, ruff (incl. `--select I`), format check, basedpyright in
      `libs/fred-runtime`; root `make migration-check`; performance checklist.
- [x] 3.3 `openspec validate keep-model-answer-after-failed-tool-round --strict`.

## Verification Evidence

- `libs/fred-runtime` `make test`: 2132 passed, 11 skipped, 22 deselected.
- Focused module `test_react_tool_error_final_2244.py`: 23 passed; 3 of the new tests fail
  against the previous runtime.
- `make code-quality` (ruff, `--select I`, format, bandit, detect-secrets, basedpyright
  with baseline): 0 errors; 5 pre-existing warnings in untouched files.
- Root `make migration-check`: valid.
- Performance: per-chunk path loses one flag check; the final block adds one `strip()` per
  turn and an INFO log only on the error fallback. No I/O, awaits, shared state or metric.
