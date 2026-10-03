## 1. Excel attachment ingestion

- [x] 1.1 Reuse corpus `ExcelProcessor` and `ExcelTableRegistrationProcessor` for new Excel attachments, publish `output.md`, skip vector preview indexing, and return tabular availability; verify a multi-sheet fast-ingest test can describe all sheets and query rows beyond the old preview cap.
- [x] 1.2 Reject corrupt or tableless workbooks without a successful attachment and compensate uploaded artifacts after any failed stage; verify focused failure and cleanup tests.

## 2. Scope and lifecycle

- [x] 2.1 Resolve all tables of an explicitly named owned Excel attachment in tabular schema, search, and SQL paths without exposing them to other users or blind listing; verify owner, non-owner, and ReBAC-disabled tests.
- [x] 2.2 Classify and delete both CSV and multi-table Excel attachment artifacts through owner and platform lifecycle paths; verify all Parquet objects, `output.md`, and metadata are removed.

## 3. Agent behavior

- [x] 3.1 Guide the agent to use Excel and CSV tabular schemas and queries, including the `output.md` roadmap, while allowing old text-backed Excel attachments to use the text path; verify focused runtime prompt tests.
- [x] 3.2 Keep selected document reading tools useful for text attachments and make calls on tabular-only attachments explicitly bounded or unavailable; verify focused content and capability tests do not present partial spreadsheet previews as full reads.

## 4. Documentation and verification

- [x] 4.1 Update the session attachment design, Help Center, UX note, and existing PR migration note for new Excel behavior and legacy compatibility; verify the migration declaration and strict OpenSpec validation.
- [x] 4.2 Run focused backend and frontend tests, review the diff, and run root code quality once before push; record actual results in this change and PR #2838.

## Verification evidence

- Backend ingestion and delete authorization: 32 focused tests passed. Tabular service: 65 tests passed, including a two-sheet attachment, `output.md`, a row after the old 20-row preview, search, owner isolation, and ReBAC-disabled listing. Content reader fallback: 7 tests passed.
- Runtime prompt: 53 tests passed. Frontend pack selection: 12 tests passed.
- `openspec validate tabular-excel-chat-attachments --strict` and `openspec validate merge-attachments-into-team-resources --strict` passed. `make migration-check MIGRATION_BASE=origin/swift` passed. Root `make code-quality` passed through every module, including frontend TypeScript, Prettier, and ESLint.
- Diff reviewed for table registration, cleanup, owner checks, legacy text attachments, and Simple pack selection.
