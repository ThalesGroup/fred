---
schema: 1
title: "Require exact targets for agent migration downgrades"
impact: minor
configuration: none
configuration_reason: "The agent migration CLI and local Make target change arguments, but database and deployment configuration keys do not change."
---
## Applicability

Fred deployments that use the agent image's `fred_runtime downgrade` command
or the `apps/fred-agents` `db-downgrade` Make target for operator rollback.

## Prerequisites

Before a planned rollback, record the old revision of each runtime or installed
capability migration tree. Stop writers, review the crossed migrations and take
a coordinated backup as described in the Docker Compose rollback runbook.

## Configuration

No configuration changes are required. Select the intended database with the
existing `CONFIG_FILE` or `DATABASE_URL` before running a downgrade.

## Upgrade

Deploy Fred normally. The automatic `python -m fred_runtime migrate` command
still upgrades the runtime and installed capability trees to their heads.
Update any operator script that calls `fred_runtime downgrade <tree> -1` or
`make db-downgrade MIGRATION_TREE=<tree>` to supply the recorded old revision
or `base` as an explicit target. `base` applies only when the old release had
no revision in that selected tree.

## Validation

On an isolated database, upgrade the runtime and installed capability trees,
then run `python -m fred_runtime downgrade runtime <recorded-old-revision>`
and, if needed, `python -m fred_runtime downgrade capability:<id> base`.
Verify each selected version table and affected schema. Confirm other trees
retain their revisions and the normal `migrate` command still upgrades them.

## Rollback

Reverting this CLI change restores the old single-step `-1` argument. The
older image lacks migration scripts introduced by a newer release, so use the
newer image for any required schema downgrade before starting older services.
Review data loss before running a downgrade; reverting CLI code does not undo
a migration already executed.

## Limitations

This command only changes one selected migration tree. It does not restore
data removed by a downgrade or coordinate PostgreSQL with object storage and
external systems. Follow the release-specific rollback procedure.
