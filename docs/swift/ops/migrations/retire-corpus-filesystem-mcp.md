---
schema: 1
title: "Retire the corpus manager API and unused corpus and filesystem MCP servers"
impact: minor
after: [retire-mon-espace, split-attachments-and-team-documents]
configuration: production
configuration_reason: "Knowledge Flow no longer accepts mcp.filesystem_enabled; operators must remove the key from private overlays before the coordinated upgrade. No stored corpus data is migrated or deleted."
---
## Applicability

Fred deployments that expose the Knowledge Flow corpus or filesystem MCP server, call the `/corpus/*` maintenance API, or set `mcp.filesystem_enabled` in a custom values/configuration overlay.

## Prerequisites

Check custom agent definitions for `mcp-knowledge-flow-corpus` and `mcp-knowledge-flow-fs`. Replace document discovery with the `document_access` capability and its `list_document_tree` tool. Review any other use of the retired MCPs before upgrade.

Identify scripts or dashboards calling `/corpus/*`, including revectorization and vector-metadata repair. Complete any already-started revectorization or repair Temporal workflows before deploying workers without those workflow and activity registrations.

## Configuration

Remove `mcp.filesystem_enabled` from custom Knowledge Flow configuration and Helm values overlays. The remaining filesystem read limits still configure retained HTTP `/fs` reads, including the virtual corpus view.

## Upgrade

Complete the prerequisites and configuration cleanup in this note, the [file-area retirement](retire-mon-espace.md), and the [document-source SDK migration](split-attachments-and-team-documents.md) before one coordinated rollout. These procedures are not independent deployments. Deploy the updated agent pod catalog, Knowledge Flow API and Temporal workers, frontend and paired chart together. The retired MCP endpoints and SDK constants and all `/corpus/*` maintenance routes are unavailable after upgrade. The retained virtual-corpus reads and technical PPT binary upload/download/delete routes under `/fs`, `/documents/tree`, and ordinary ingestion routes remain available. See the [file-area migration](retire-mon-espace.md) for the other retired `/fs` operations.

Historical vector-metadata repair tasks remain in task storage. Their dedicated result counters remain in the stored task record, but the current task API omits them and Task Activity no longer displays the repair report. Export those task records before upgrade if the counters are needed operationally.

## Validation

Confirm the agent tool picker has no corpus or filesystem MCP entry; `/knowledge-flow/v1/mcp-corpus`, `/knowledge-flow/v1/mcp-fs`, and `/knowledge-flow/v1/corpus/*` are absent. Confirm `list_document_tree` still lists indexed documents and a PPT Filler template can still produce a downloadable presentation.

## Rollback

Roll back the agent pod catalog, Knowledge Flow API and workers, and frontend together. No stored files or corpus data are migrated or deleted by this change.

## Limitations

Saved agent selections naming a retired MCP must be updated before those agents can use their configured tools. The retired maintenance operations have no replacement endpoint in this change. Direct HTTP `/fs` retains virtual-corpus reads and technical agent-path reads plus the PPT binary transport after the general-purpose file-area retirement; it no longer serves the retired personal or team-shared paths.
