## 1. Audit classification

- [x] 1.1 In `audit_stores`, classify vector-only UIDs with `is_session_scoped_document` in one worker thread and skip those classified as session attachments; keep `orphan_vectors` on `False`, unsupported, or failed classification, logging failures.

## 2. Regression coverage

- [x] 2.1 Test a session attachment beside a genuine corpus orphan: only the orphan is reported, and metadata-backed UIDs are not classified.
- [x] 2.2 Test an adapter whose chunk lookup raises `NotImplementedError`: the UID stays reported.
- [x] 2.3 Test a chunk lookup that raises an error: the UID stays reported and a warning is logged.

## 3. Close-out

- [x] 3.1 Add the migration note under `docs/swift/ops/migrations/` and run `make migration-check`.
- [x] 3.2 Run the focused audit tests, `make test` in `apps/knowledge-flow-backend`, and ruff on touched files; record evidence in `verification.md`.
- [x] 3.3 Run `openspec validate exclude-session-vectors-from-corpus-audit --strict`.
