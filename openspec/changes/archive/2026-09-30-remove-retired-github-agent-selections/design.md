## Context

See proposal.md. `UnknownCapabilityError` is raised when a stored selection
names a capability absent from the pod. `mcp-web-github-readonly` was removed
from both catalogs, but revision `ba2c3c7fd0c1` originally handled only RAG.
Some installations may already have applied that revision.

## Goals / Non-Goals

**Goals:** Clean the retired GitHub selection from managed agents using one
retired-MCP migration file and document how to reapply it on an upgraded database.

**Non-Goals:** Reintroduce GitHub, change templates/runtime, grant replacement
capabilities, rewrite OpenFGA tuples or unsuspend agents automatically.

## Decisions

- Extend `ba2c3c7fd0c1` to remove the two GitHub ID spellings alongside the two
  retired RAG ID spellings. This keeps a single retired-MCP migration file.
  Alembic will not replay it automatically where that revision was applied
  already; the operator note gives a controlled downgrade/upgrade procedure.
- Keep the self-contained JSON transformation. Remove retired IDs from
  `selected_capability_ids` and `capability_config`. Keep missing/null/[]
  distinct and serialize only changed rows. A compare-and-swap UPDATE fails
  if a concurrent write changed tuning.
- Skip malformed/non-object JSON with a row-identifier diagnostic, without
  exposing payload content. Leave all non-tuning columns untouched. Downgrade
  is a no-op; removed selections cannot be reconstructed from the database.

## Risks / Trade-offs

- An explicit GitHub-only selection becomes `[]` → operators can select an
  installed capability through the normal UI if the agent still needs tools.
- Writes during migration can conflict → quiesce agent edits, back up data and
  retry after a compare-and-swap failure. Normal Alembic transactions roll back
  the failed revision.
- Already-applied revisions do not rerun with `upgrade head` → only when
  `alembic current` shows exactly `ba2c3c7fd0c1` as the sole applied head,
  with agent writes paused and a backup available, downgrade its no-op data
  revision to `21e235382895`, then upgrade to `ba2c3c7fd0c1`. A database
  at a later or divergent revision needs a separate remediation plan.
- Previously suspended agents remain suspended → use existing administration
  and availability reconciliation; the migration must not change permission
  or suspension decisions.

## Migration Plan

Back up `agent_instance`, pause agent writes, run the normal control-plane
`alembic upgrade head` on a fresh database, or after checking the sole current
revision is exactly `ba2c3c7fd0c1`, downgrade to `21e235382895` before
upgrading back to `ba2c3c7fd0c1`. Restart/refresh affected services before
testing an existing agent. Rollback of removed tuning requires restoring
affected rows from backup; Alembic downgrade cannot infer prior selections.
