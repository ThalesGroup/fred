---
schema: 1
title: "Package MCP catalogs and retire legacy local MCP tools"
impact: minor
configuration: production
configuration_reason: "Fred's internal MCP catalog moves into fred-capability-mcp, internal endpoints use service references and instructions use prompt_file. The Helm-managed MCP catalog, legacy document-search and GitHub entries, and inprocess transport are retired."
---

## Applicability

Fred agent pods, the control-plane and deployments using the Fred Helm chart.
Custom catalogs/templates using local MCP providers also need updating.

## Prerequisites

Back up `agent_instance` data before migration and quiesce control-plane agent
writes until the migration and pod deployment are complete. Use matching images
and chart values containing this change.

## Configuration

The installed `fred-capability-mcp` package contains one `mcp_catalog.yaml`
with Fred / Knowledge Flow servers only. The pod discovers it through
`fred.mcp_catalogs`. The Fred chart mounts `mcp_catalog_external.yaml` to add
deployment-owned MCP servers; its default `servers: []` leaves the packaged
servers unchanged. Move third-party entries from the old
`applications.fred-agents.mcp_catalog` value to
`applications.fred-agents.mcp_catalog_external`. The old Helm key is no longer
accepted. Duplicate IDs across installed and external servers fail startup.
The production image includes a default `models_catalog.yaml`; the Fred chart
mounts its configured catalog from `applications.fred-agents.models_catalog` at
the same path. Deployments without this chart can use the image default, mount
another file at `/app/config/models_catalog.yaml`, or set
`FRED_MODELS_CATALOG_FILE` to its path.
`FRED_MCP_CATALOG_FILE` still overrides an existing `./config/mcp_catalog.yaml`,
and either replaces the entire packaged list. `servers: []` disables all MCPs;
an explicitly selected missing file retains the previous no-MCP behavior.
`FRED_MCP_EXTERNAL_CATALOG_FILE` selects the additive file; an explicitly
selected missing file fails startup.

Internal HTTP entries use `service: knowledge_flow` and an API-relative `path`.
The existing `ai.knowledge_flow_url` supplies the scheme, host, port and API prefix.
`service: control_plane` uses `platform.control_plane_url`. A concrete `url`
remains supported, but cannot be combined with `service`.

The optional `prompt_file` reads UTF-8 from `pkg://package/path.md`, an absolute
path or a path relative to the catalog. It cannot accompany non-null inline
`agent_instructions`; unreadable files fail startup. The package includes
`prompts/tabular.md`; it is active with the packaged catalog. Custom
files must be mounted or packaged and are read at startup.

`transport: inprocess` is no longer accepted. Remove local-provider entries from
custom catalogs and implement local tools as native capabilities. Remove custom
references to `MCP_SERVER_KNOWLEDGE_FLOW_TEXT`; it is no longer exported by the SDK.
The default RAG and GitHub MCP entries have been removed, together with the unused
`prompts/document-search.md` resource. The GitHub entry had no implementation.

Canonical Python imports are `fred_sdk.contracts.capability.mcp` and
`fred_sdk.resources.mcp`; runtime imports remain compatibility re-exports.
Catalog entry points receive `fred_sdk.contracts.services.ServiceEndpointsPort`.
Live remote transport remains in `fred-runtime`.

## Upgrade

1. Back up agent data and pause agent writes. Move third-party entries from the
   old Helm `mcp_catalog` value to `mcp_catalog_external`; remove obsolete local
   MCP entries and prompt references from custom files before updating pods.
2. Check the control-plane database revision with `alembic current`. If it is
   before `ba2c3c7fd0c1`, apply the normal `alembic upgrade head`.
   Revision `ba2c3c7fd0c1` removes `mcp-knowledge-flow-mcp-text` and
   `mcp-web-github-readonly`, including both historical `mcp:`-prefixed forms,
   from `selected_capability_ids` and `capability_config`. Unrelated tuning,
   ordering, grants, enabled/suspension flags and audit fields are preserved.
   No replacement capability is added. If `alembic current` shows exactly
   `ba2c3c7fd0c1` as the sole applied head from before the GitHub cleanup,
   `upgrade head` alone will not replay it. With agent writes paused and a
   backup available, run `alembic downgrade 21e235382895` followed by
   `alembic upgrade ba2c3c7fd0c1`. The downgrade of this revision is a no-op
   for agent tuning. Do not use this replay procedure if the database is at a
   later or divergent revision: it would also downgrade other migrations.
3. Deploy the updated pods and chart, then resume traffic. ReAct RAG, Mindmap and
   Comparison keep their IDs but default to `document_access`. Stored selections
   that are null/absent still inherit defaults; explicit empty lists remain empty.
4. Where desired, explicitly select and authorize `document_access` for agents
   whose old explicit RAG selection was removed. An explicit selection containing
   only retired MCPs becomes `[]`. Review suspended instances through normal
   administration; the migration does not unsuspend them.

## Validation

Confirm the control-plane is at migration head and inspect migration diagnostics
for skipped non-object or malformed JSON rows. Repair those rows through normal
administration before relying on the cleanup. A concurrent tuning edit aborts the
migration; pause writes and retry. Running the revision again makes no further changes.

Render the Helm chart and load the packaged MCP catalog in the new image. Neither retired
server should appear; `document_access` should be available under the normal team
policy. Test document search on an authorized agent and a remaining remote MCP.

## Rollback

Roll back images and chart together and restore affected tuning from the backup
if needed. Alembic downgrade does not reconstruct removed selections/configuration.
Restore literal URLs and inline instructions before using symbolic/file-reference
catalogs with an older runtime. Do not overwrite newer agent edits during restoration.

## Limitations

The migration cannot repair malformed tuning, grant replacement capabilities or
remove historical OpenFGA tuples. Native document search and its shared Knowledge
Flow client remain supported. MCP `sse`/`websocket` identifiers retain their existing
configuration support; this change does not implement those connection paths.
