---
schema: 1
title: "Add one-step downgrade for agent pod migration trees"
impact: none
configuration: none
configuration_reason: "The command reads the existing CONFIG_FILE or DATABASE_URL; no configuration setting or chart value changes."
no_action_reason: "Normal deployment still runs the existing upgrade command. The new downgrade command is an optional operator maintenance action."
---
## Applicability

Fred deployments with an agent pod that installs fred-runtime and capability Alembic trees.

## Prerequisites

No additional prerequisites for normal upgrades. Before an intentional downgrade, stop writers, inspect every affected script and prepare a database backup and recovery plan.

## Configuration

No configuration changes are required. Select the intended database with the existing CONFIG_FILE or DATABASE_URL; `make db-downgrade` also accepts ALEMBIC_CONFIG_FILE.

## Upgrade

Deploy Fred normally. The migration hook continues to run `python -m fred_runtime migrate` and moves the runtime and installed capability trees to their heads.

## Validation

On a throwaway database, run `make db-upgrade` and then `make db-downgrade` from `apps/fred-agents`. Verify every participating version table moved back one revision and inspect the affected schema. The production upgrade path needs no extra action.

## Rollback

Reverting this code removes the new CLI and Make target; it does not reverse a downgrade that an operator already ran. If the command was used, inspect all tree revisions and schemas, then apply a reviewed recovery plan before restarting workloads.

## Limitations

This is not a coordinated deployment rollback. A capability downgrade can drop data, a migration may have an empty `downgrade()`, and a failure can leave only some trees downgraded. In particular, the writable-document base downgrade drops its document table, while fred-runtime's retired demo table revision has a no-op downgrade.
