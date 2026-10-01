---
schema: 1
title: "Retire legacy knowledge-flow resources"
impact: major
configuration: production
configuration_reason: "Remove retired knowledge-flow resource store and MCP keys from local configuration and Helm overrides before deploying the matching code."
---

## Applicability

Knowledge-flow deployments exposing the old prompt/template/chat-context resource
API. The unused `/mcp/reports/write` API and `mcp-reports` mount are also removed.
The unused global metadata endpoint `/documents/metadata/search` and the old
filesystem corpus area `/corpus/...` are removed too. The current document UI
refreshes the selected folder; corpus access uses the current document tools.
Existing external clients of these retired paths must be updated before rollout.
Current control-plane team prompts, document downloads and workspace files under
`/teams/...` remain supported.

## Prerequisites

Stop new ingestion and legacy resource writes, drain existing work, then stop all
old knowledge-flow API and worker processes. Back up the database and OpenFGA
store using the deployment's normal procedure. No mixed-version rollout is supported.

Run this read-only inventory against the knowledge-flow database before upgrading:

```sql
SELECT resource_id, resource_name, resource_type FROM resource ORDER BY resource_id;
SELECT tag_id, owner_id, name, type FROM tag
WHERE type IS NULL OR type <> 'document' ORDER BY tag_id;
SELECT count(*) FROM kf_ingestion_submission;
```

Both legacy-resource queries must return no rows and the submission count must be
zero. Otherwise stop: export the legacy records and obtain an explicit disposition
decision. Do not delete records simply to make the migration pass. A backup does
not authorize deletion. Coordinate the removal of any old external REST/MCP clients.

## Configuration

Remove `storage.resource_store`, `mcp.resources_enabled`,
`mcp.templates_enabled` and `mcp.reports_enabled` from knowledge-flow configuration and matching Helm
overrides. The generated configuration and chart schemas no longer expose them.
Do not remove text-search or control-plane prompt configuration.

## Upgrade

With the old writers stopped, apply the knowledge-flow migrations using the
deployment's configured database connection:

```sh
cd apps/knowledge-flow-backend
uv run alembic upgrade head
uv run alembic heads
```

Revision `b2845a001003` refuses remaining legacy resource/non-document folder data
and drops only the empty `resource` table. It follows `b2845a001002`, whose separate
guide covers submission queue removal. This SQL migration does not mutate OpenFGA
tuples; their removal belongs to the coordinated corpus authorization cutover.

Deploy matching code and configuration. The old resource REST operations,
`mcp-resources`, the empty `mcp-template` mount and the report creation API/MCP
mount are removed, with no adapter or
automatic conversion into control-plane prompts.

## Validation

- Alembic reports one head; the `resource` table is absent.
- The generated knowledge-flow OpenAPI has no `Resources` operations.
- Existing document folders still list; current control-plane prompts still list/edit.
- `/mcp/reports/write`, `mcp-reports` and `/documents/metadata/search` are absent.
- Filesystem operations refuse `/corpus/...`; `/teams/...` remains functional.
- No compatibility adapter replaces retired paths.
- Existing report documents are retained. Reports missing a stored corpus folder
  remain explicit review cases for the single-folder migration; do not purge them.

## Rollback

Before restoring old code, stop new processes and downgrade the resource-removal
revision with the deployment's normal Alembic procedure. Downgrade recreates an
empty resource table and its indexes. It does not restore exported/deleted data or
OpenFGA tuples. After any separately approved data/tuple removal, restoring prior
behavior requires the verified backup and matching code/configuration.

## Limitations

This retirement does not yet change corpus authorization, folder membership or
attachment storage. Obsolete OpenFGA tuples must be inventoried and handled in
the coordinated authorization migration; this revision does not remove them.
