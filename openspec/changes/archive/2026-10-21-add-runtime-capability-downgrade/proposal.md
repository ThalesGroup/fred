## Why

`fred-agents` can upgrade the packaged fred-runtime and installed capability Alembic trees in one command, but it has no matching one-step downgrade. Each other backend offers `make db-downgrade`, so operators currently have to locate and invoke the runtime and capability trees individually.

## What Changes

- Add `python -m fred_runtime downgrade <tree> -1` to move only an explicitly selected runtime or capability tree back one revision. An installed capability might not have advanced in the last deployment, so downgrading every tree would reverse unrelated migrations.
- Add `make db-downgrade MIGRATION_TREE=<tree>` in `apps/fred-agents`, matching the other backends' one-revision target while requiring a tree selection.
- Document the command, independent version tables, and destructive or no-op migration scripts. The command is an explicit database operation, not a complete deployment rollback.
- Keep `python -m fred_runtime migrate` and the deployment migration hook's upgrade behavior unchanged.

## Capabilities

### New Capabilities

- `runtime-capability-migrations`: Operational commands for applying one-step migrations to fred-runtime and installed capability trees.

### Modified Capabilities

None.

## Impact

The fred-runtime CLI and migration runner, `apps/fred-agents/Makefile`, focused migration tests, and database migration operator documentation. No new Alembic revision, schema, application API, or automatic rollback hook is introduced. This is the scoped CLI portion of issue #3224; coordinated deployment rollback remains in #3112.
