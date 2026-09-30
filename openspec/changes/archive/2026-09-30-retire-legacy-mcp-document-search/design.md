## Context

See proposal.md. The legacy inprocess registry has exactly one implementation:
`kf_vector_search`. GitHub is declared but unimplemented. Native `document_access`
uses the shared `VectorSearchClient` through `DocumentSearchAdapter` and therefore
must retain both, along with table-hit repair and `knowledge.search` support.
Managed agents persist JSON text in `agent_instance.tuning_json`.

## Goals / Non-Goals

**Goals:** Remove the duplicate toolkit and its configuration; keep shipped agent
templates bootable and migrate stored references without unrelated data changes.

**Non-Goals:** Change native RAG behavior, rewrite OpenFGA grants, automatically activate replacement
capabilities on stored explicit selections, or run migrations on a live deployment.

## Decisions

- Delete the single-provider registry, bootstrap injection, optional factory,
  SDK transport/provider fields and local MCP lifecycle. Reject `inprocess`
  catalogs; native capability tool invokers remain supported. The developer
  explicitly extended this change to retire the entire local MCP transport.
- Remove the unimplemented GitHub entry as explicitly approved. The data migration
  remains limited to RAG removal, as requested; any old GitHub selection can be
  removed manually without replacement.
- Replace all three shipped defaults with `document_access` while keeping template
  IDs stable. The developer explicitly chose this separately from stored migration.
- Add a self-contained Alembic data revision after current head `b88202b8451e`.
  Reuse the existing migration deployment path instead of adding a second CLI.
  Remove the plain ID and historic `mcp:`-prefixed form from
  `selected_capability_ids` and `capability_config` only.
- Keep missing/null/empty activation semantics and unrelated JSON values. Only
  serialize changed rows. Invalid JSON/non-object rows remain unchanged with a
  diagnostic; do not print their payloads. Guard updates against concurrent edits.
- Downgrade cannot infer removed selections/configuration and therefore does not
  restore them. Document database backup as the recovery path.

## Risks / Trade-offs

- Explicit legacy-only selections become empty → document manual activation of
  `document_access`; do not broaden capability access during migration.
- Inherited template defaults now resolve to `document_access` → existing
  capability permission checks still apply; no grant is auto-created by the migration.
- Old custom catalogs can still declare the removed provider → operators must
  remove that entry; the runtime no longer supplies an implementation.
- Stale imports and prompt references → scan current code and test installed
  catalog boot, native search and template defaults.

## Migration Plan

Back up agent data, quiesce control-plane writes, apply the usual control-plane
`alembic upgrade head`, and deploy updated pods/chart before resuming traffic.
Keep any suspension flags and audit fields unchanged. Rollback requires the old
image/chart plus restoration of affected tuning data from backup if needed.
