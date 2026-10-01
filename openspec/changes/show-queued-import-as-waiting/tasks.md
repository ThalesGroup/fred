## 1. Phase model and stepper

- [x] 1.1 Add the `waiting` phase state to `importPhases.ts`: a `pending` task outside a conflict shows it on the phase in flight; `importPhaseLabel` / `importPhaseHintFor` name it; the link feeding it takes its colour. Cover it in the phase-model tests.
- [x] 1.2 Render `waiting` in `ImportStepper` with the outlined `pending` icon in grey and no spinner; add `pending` to `materialIcons` and raise the packed UI archive's expected glyph count. Cover it in the stepper test.
- [x] 1.3 Add the English and French strings (status line, hint, phase-state accessible name).

## 2. Documentation and verification

- [x] 2.1 Mention the waiting state on the Help Center Resources page, fr and en.
- [x] 2.2 Add the English migration note; run root `make code-quality`, frontend `make test`, `libs/frontend` `npm test`, `make migration-check` and `openspec validate --strict`, and record the results here.
- [ ] 2.3 Verify in the UI: a batch import shows waiting tiles in grey with the `pending` icon and no spinner, then the usual running state once a worker picks each file up.

Verification (2026-10-01): root `make code-quality` passed all modules (global `uv`
override); frontend `make test` 3,148 passed, 7 skipped; `libs/frontend` `npm test`
375 passed, 0 failed (glyph count 134); `make migration-check` accepted 1 new note;
`openspec validate --strict` passed. An independent review found no blocking issue;
its one test nit is fixed. Task 2.3 (visual check) awaits PR review.
