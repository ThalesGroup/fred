## 1. Selected-tree CLI

- [x] 1.1 Require and validate complete revision IDs and `base` for one selected tree; verify focused CLI and runner tests reject `-1` and invalid targets without invoking Alembic.
- [x] 1.2 Exercise runtime exact-target and capability-base downgrades against an isolated database; verify the selected tree's version and schema change while other trees retain their revisions.

## 2. Operator entry points

- [x] 2.1 Require `MIGRATION_REVISION` in `apps/fred-agents` `db-downgrade`; verify the check target rejects a missing revision and `make -n` passes an explicit one.
- [x] 2.2 Update the existing Docker Compose rollback runbook with the exact-target agent commands and the v3.8.0 to v3.10.0 rehearsal findings; verify the commands match the released image paths and script behavior.

## 3. Close-out

- [x] 3.1 Run focused tests and the required root quality check once, audit the branch against `swift`, then reconcile this change's artifacts with the verified implementation.
- [x] 3.2 Push the isolated branch and open a draft PR linked to issue #3112; verify its diff and CI status are visible to reviewers.
