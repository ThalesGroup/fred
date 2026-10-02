## 1. Clean persisted selections

- [x] 1.1 Extend `ba2c3c7fd0c1` to remove both GitHub ID spellings alongside RAG; verify `alembic heads` has one head and there is no second migration file.
- [x] 1.2 Test selection/config removal, missing/null/empty states, unchanged rows, malformed JSON, concurrent edits and idempotence with focused tests.
- [x] 1.3 Verify fresh upgrade and controlled reapplication from an already-applied revision on a disposable database.

## 2. Document and close

- [x] 2.1 Update the existing operator migration note and current contract/spec guidance; verify migration-note and OpenSpec validation.
- [x] 2.2 Run root code quality and independent review, resolve findings, sync the MCP spec and archive this change. Verify no commit, staging or live database migration occurred.
