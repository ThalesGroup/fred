## 1. Selected-tree downgrade command

- [x] 1.1 Add a downgrade runner using one selected packaged Alembic tree; verify focused tests cover runtime and capability selection, unknown trees and Alembic failure.
- [x] 1.2 Expose `python -m fred_runtime downgrade <tree> -1` and reject missing or unsupported targets before migration; verify CLI tests cover accepted and rejected invocations.
- [x] 1.3 Add `apps/fred-agents` `db-downgrade` with required `MIGRATION_TREE` and the optional config override used by the other backends; verify `make -n db-downgrade MIGRATION_TREE=runtime` shows the selected CLI command and existing `db-upgrade` still resolves.

## 2. Real migration and operator guidance

- [x] 2.1 Exercise a SQLite upgrade and separate one-step downgrades for runtime and a capability tree, checking the unselected tree retains its revision and schema; verify the focused test passes.
- [x] 2.2 Update database migration guidance and add the required PR migration note, including tree selection and destructive/no-op limits; verify `make migration-check` accepts the note.

## 3. Review and delivery

- [x] 3.1 Run the required focused tests and root quality gate, apply the branch audit with independent read-only review, and record results in the PR.
- [x] 3.2 Reconcile and sync the OpenSpec change, then commit, push and open the draft PR for issue #3224; verify its target is `swift` and it remains a draft.
