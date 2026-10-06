---
schema: 1
title: "Retire the unused corpus and filesystem MCP servers"
impact: minor
configuration: production
configuration_reason: "Knowledge Flow no longer accepts mcp.filesystem_enabled; the chart defaults, sample configurations, and generated schemas remove it."
---
## Applicability

Fred deployments that expose the Knowledge Flow corpus or filesystem MCP server, or set `mcp.filesystem_enabled` in a custom values/configuration overlay.

## Prerequisites

Check custom agent definitions for `mcp-knowledge-flow-corpus` and `mcp-knowledge-flow-fs`. Replace document discovery with the `document_access` capability and its `list_document_tree` tool. Review any other use of the retired MCPs before upgrade.

## Configuration

Remove `mcp.filesystem_enabled` from custom Knowledge Flow configuration and Helm values overlays. The remaining filesystem read limits still configure the direct HTTP `/fs` API.

## Upgrade

Deploy the updated agent pod catalog and Knowledge Flow together. The two retired MCP endpoints and SDK constants are unavailable after upgrade; direct HTTP `/fs` and corpus-management routes remain available.

## Validation

Confirm the agent tool picker has no corpus or filesystem MCP entry, `/knowledge-flow/v1/mcp-corpus` and `/knowledge-flow/v1/mcp-fs` are absent, and a PPT Filler template can still produce a downloadable presentation.

## Rollback

Roll back the agent pod catalog and Knowledge Flow together. No stored files or corpus data are migrated or deleted by this change.

## Limitations

Saved agent selections naming a retired MCP must be updated before those agents can use their configured tools. This change does not remove the direct HTTP `/fs` API.
