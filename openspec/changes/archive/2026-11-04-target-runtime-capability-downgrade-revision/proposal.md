## Why

Release rollback needs an exact Alembic target for each database tree. The published `fred_runtime downgrade` command accepts only `-1`, so an operator must count revisions or construct a separate Alembic invocation even though the selected runtime and capability trees are already known to the CLI.

## What Changes

- **BREAKING:** Require an exact revision ID or `base` in `python -m fred_runtime downgrade <tree> <revision>`; reject relative targets such as `-1`.
- Reject targets outside the selected installed migration tree before running a migration.
- Require `MIGRATION_REVISION` in `apps/fred-agents` `db-downgrade`.
- Document explicit per-tree targets in the Docker Compose rollback runbook and verify them with focused tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `runtime-capability-migrations`: Selected runtime and capability trees require an explicit revision or base for downgrade.

## Impact

The fred-runtime operational CLI, the fred-agents Makefile, migration tests, and the operator runbook change. No Alembic revision, automatic upgrade behavior, deployment hook, or database schema is added. A targeted downgrade remains a manual, potentially destructive operation that requires stopped writers and a reviewed recovery plan.
