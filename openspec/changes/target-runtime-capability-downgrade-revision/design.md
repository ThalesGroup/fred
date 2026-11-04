## Context

The packaged `fred_runtime migrate` command upgrades the runtime tree and every discovered capability tree. Its downgrade sibling selects one tree but hard-codes `-1`; the release runbook instead needs the exact revision recorded before upgrade. The v3.8.0 to v3.10.0 rehearsal succeeded with one step per affected agent tree, and a direct Alembic call from the v3.10.0 image also reached the exact v3.8.0 runtime revision. See `proposal.md` for the operator gap.

## Goals / Non-Goals

**Goals:** Require a release-target argument in the selected-tree CLI without changing upgrade behavior or tree discovery. Make the agent Make target require the same explicit revision.

**Non-Goals:** Infer the previous release from the database, automatically downgrade during Compose or Helm rollback, coordinate multiple databases, or make destructive migration scripts reversible.

## Decisions

1. Keep `downgrade <tree> <revision>` and pass the validated target to Alembic for that tree only. Accept `base` or a complete revision ID found in the selected script directory. Resolve the ID before opening the database so an ID from another tree, a typo, or an abbreviated ID cannot silently select the wrong target. Alembic remains responsible for checking the path from the current database revision and executing it. Relative `-1` calls are rejected because they do not state the release target.
2. Keep the installed capability registry as the source of migration locations. A capability absent from the new agent image has no valid selected tree; the operator must use an image that still contains its migration scripts. Do not add a global downgrade command because trees advance independently.
3. Require `MIGRATION_REVISION` in the agent Make target. The image CLI remains the production Compose entry point; Make is a local operator convenience.
4. Test exact runtime targets across more than one revision and capability `base` using isolated databases. Also test rejection of `-1` and invalid IDs before Alembic execution, and retention of other version tables. The rehearsal commands and their data-loss observations belong in the existing rollback runbook, not a parallel status document.

## Risks / Trade-offs

- [A downgrade drops newer data or tables] - Require stopped API and worker writers, a backup, release-specific script review, and explicit target verification in the runbook. The CLI does not claim a revision change restores data.
- [Different agent images contain different migration trees] - Use the newer image that applied the migration until all downgrades are complete; resolve targets against that installed tree.
- [Multiple replicas or retries race on one version table] - Operators run one migration container per tree while all application replicas and workers are stopped. The CLI adds no request-time or process-local coordination state.

## Migration Plan

No database migration is introduced. Existing deployment upgrade jobs continue to call `python -m fred_runtime migrate`. For an operator-approved rollback, stop writers, retain the newer agent image, inspect the crossed revisions and backup, run `downgrade` once per affected tree to its recorded old revision or `base`, verify every version table and affected data, then start old images. Existing operator scripts using `-1` must supply exact targets before updating the runtime package.
