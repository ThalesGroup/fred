---
schema: 1
title: "Require exact targets for Agent Pod migration downgrades"
impact: minor
configuration: none
configuration_reason: "The Agent Pod migration CLI and local Make target change arguments; database and deployment configuration do not change."
---
## Applicability

Weaver deployments that use `python -m fred_runtime downgrade` or the
`apps/fred-agents` `db-downgrade` Make target for an operator rollback.

## Prerequisites

Before a planned rollback, record the revision of each affected runtime or
installed capability tree in the older release. Stop writers, review the
crossed migration scripts and take a coordinated backup.

## Configuration

No configuration change is required. Select the intended database with the
existing `CONFIG_FILE`, `ALEMBIC_CONFIG_FILE` or `DATABASE_URL` mechanism.

## Upgrade

Deploy normally. `python -m fred_runtime migrate` still upgrades all installed
trees. Update operator scripts to supply a complete target revision ID, or
`base` when the older release had no revision in the selected tree:

```bash
python -m fred_runtime downgrade runtime <recorded-old-runtime-revision>
python -m fred_runtime downgrade capability:<id> <recorded-old-capability-revision-or-base>
make -C apps/fred-agents db-downgrade MIGRATION_TREE=runtime MIGRATION_REVISION=<recorded-old-runtime-revision>
```

The CLI rejects relative targets such as `-1`, abbreviated IDs and `head`.
`base` reverses every revision in the selected tree.

## Validation

On an isolated database, migrate the runtime and capability trees, then
downgrade one selected tree to its recorded old revision or `base`. Inspect its
version table and affected schema, confirm other trees retain their revisions,
and check that `migrate` can upgrade the trees again.

## Rollback

Reverting this CLI change restores the old single-step `-1` argument. Use the
newer image, which contains the newer migration scripts, for any required
schema downgrade before starting older services. Reverting the CLI does not
undo a downgrade already executed or recover removed data.

## Limitations

This command changes only the selected Alembic tree. It does not coordinate
PostgreSQL with object storage or other systems, and it cannot restore data
removed by migration scripts. Follow the release-specific rollback procedure.
