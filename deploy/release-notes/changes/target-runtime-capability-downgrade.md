---
schema: 1
title: "Require exact targets for Python agent migration downgrades"
impact: minor
configuration: none
configuration_reason: "Only the Python migration CLI and Make target arguments change; no database connection configuration changes."
---

## Applicability

Operators using python -m fred_runtime downgrade or apps/fred-agents make db-downgrade.

## Prerequisites

Record every installed tree's current and rollback revision, stop writers, and take a coordinated backup. Review the destructive effects of each crossed migration.

## Configuration

No new configuration keys. This command applies only to runtime and capability Alembic trees, not Weaver Control Plane SQLx migrations.

## Upgrade

Use python -m fred_runtime downgrade runtime <complete-revision-id> or python -m fred_runtime downgrade capability:<id> <complete-revision-id>. The Make equivalent requires both MIGRATION_TREE and MIGRATION_REVISION. The literal base is supported; relative steps, aliases, abbreviations and revisions belonging to another tree are rejected.

## Validation

The targeted migration tests exercise exact revision selection, independent trees, invalid targets and CLI/Make argument handling on disposable fixtures. No live database downgrade was run.

## Rollback

Use the reviewed exact revision for the selected tree, then deploy the matching code. Restore the backup if a crossed downgrade removes required data.

## Limitations

Target validation is not a data-recovery plan. Downgrading multiple trees requires separately selecting and reviewing each tree.
