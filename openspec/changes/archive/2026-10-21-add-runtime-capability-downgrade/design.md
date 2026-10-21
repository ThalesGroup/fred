## Context

See `proposal.md` for the operator gap. `fred_runtime.migrations.run_all_migrations()` upgrades the packaged runtime tree, then the paths returned by `CapabilityRegistry.migration_locations()`. That registry gives a deterministic capability ID order. The Alembic `env.py` in each package owns its metadata, database URL and version table. `scripts/makefiles/alembic.mk` gives single-tree backends `db-downgrade`, but `apps/fred-agents` cannot include it because the agent image hosts multiple trees.

## Goals / Non-Goals

**Goals:**
- Offer the same one-revision operator action as other backend Makefiles while requiring selection of a tree that actually advanced.
- Preserve each tree's own Alembic configuration and expose any failure clearly.

**Non-Goals:**
- Infer which trees advanced in a deployment or orchestrate a multi-tree transaction.
- Automatically downgrade during a deployment rollback, assess individual script reversibility, or restore data dropped by migrations. Issue #3112 covers the wider recovery contract.

## Decisions

1. Add a `downgrade <tree> -1` CLI subcommand and runner sibling to `migrate`. Use Alembic's `command.downgrade(config, "-1")` with the same packaged script locations and `env.py` configuration as upgrades. Require `runtime` or `capability:<id>` so a capability that did not advance is never downgraded merely because it is installed. A single-tree Alembic invocation remains available for a specific revision target.
2. Discover capability migration locations exactly as upgrade does, and reject unknown IDs before invoking Alembic. Only the selected tree is touched; a failure propagates as a nonzero result.
3. Add `db-downgrade` to `apps/fred-agents/Makefile` with the same `dev` prerequisite as `db-upgrade` and a required `MIGRATION_TREE` variable. Pass the same optional configuration override to both targets, following `scripts/makefiles/alembic.mk`.
4. Verify with focused CLI and runner tests, including a real SQLite database carrying both the runtime and writable-document capability trees. Check that each selected downgrade leaves the other tree's version table and schema intact.

## Risks / Trade-offs

- [A revision can destroy data] -> Document the writable-document base downgrade as a concrete destructive example. Require operators to inspect scripts and back up data before invoking the explicit command.
- [A runtime revision has a no-op `downgrade()`] -> Document that a changed version row is not proof that data or schema was restored.
- [The selected tree did not advance in the last deployment] -> Require operators to identify the changed tree before invoking the command; the CLI cannot infer deployment history from Alembic versions.

## Migration Plan

No database migration is introduced by this change. Normal upgrades continue to use `migrate`. The new command is an explicit maintenance operation only; operators identify the changed tree, stop writers, review its migration script and recovery plan, run it against the intended database, then verify its version table and schema before restarting services.
