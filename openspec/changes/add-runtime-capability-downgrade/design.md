## Context

See `proposal.md` for the operator gap. `fred_runtime.migrations.run_all_migrations()` upgrades the packaged runtime tree, then the paths returned by `CapabilityRegistry.migration_locations()`. That registry gives a deterministic capability ID order. The Alembic `env.py` in each package owns its metadata, database URL and version table. `scripts/makefiles/alembic.mk` gives single-tree backends `db-downgrade`, but `apps/fred-agents` cannot include it because the agent image hosts multiple trees.

## Goals / Non-Goals

**Goals:**
- Offer the same one-revision operator action as other backend Makefiles while covering the trees that `fred-agents` upgrades.
- Preserve each tree's own Alembic configuration and expose the order and any failure clearly.

**Non-Goals:**
- Choose a common revision ID across independent trees or orchestrate a multi-tree transaction.
- Automatically downgrade during a deployment rollback, assess individual script reversibility, or restore data dropped by migrations. Issue #3112 covers the wider recovery contract.

## Decisions

1. Add a `downgrade -1` CLI subcommand and runner sibling to `migrate`. Use Alembic's `command.downgrade(config, "-1")` with the same packaged script locations and `env.py` configuration as upgrades. Limit the combined command to `-1`: a revision ID or `base` has different meaning for every tree. A single-tree Alembic invocation remains available for a specific target.
2. Discover capability migration locations exactly as upgrade does, reverse their order, and run runtime last. This reverses upgrade's ordering without depending on a source checkout. A failure propagates and stops the sequence; no cross-tree rollback is attempted.
3. Add `db-downgrade` to `apps/fred-agents/Makefile` with the same `dev` prerequisite as `db-upgrade`. Pass the same optional configuration override to both targets, following `scripts/makefiles/alembic.mk`.
4. Verify with focused CLI and runner tests, including a real SQLite database carrying both the runtime and writable-document capability trees. Check revision tables and schema before and after downgrade, and assert the order and stop-on-error path with an isolated registry double.

## Risks / Trade-offs

- [A revision can destroy data] -> Document the writable-document base downgrade as a concrete destructive example. Require operators to inspect scripts and back up data before invoking the explicit command.
- [A runtime revision has a no-op `downgrade()`] -> Document that a changed version row is not proof that data or schema was restored.
- [One tree can fail after earlier trees completed] -> Stop immediately, log the tree being processed, and instruct operators to inspect each version table before recovery.

## Migration Plan

No database migration is introduced by this change. Normal upgrades continue to use `migrate`. The new command is an explicit maintenance operation only; operators stop writers, review the relevant migration scripts and recovery plan, run it against the intended database, then verify every affected version table and schema before restarting services.
