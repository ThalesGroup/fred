---
schema: 1
title: "Capabilities classify their settings by scope and can prepare a copy of their configuration"
impact: none
configuration: production
configuration_reason: "The bundled MCP catalog marks chat_options.bound_library_ids with scope_private: true. In the final release it is delivered by fred-capability-mcp; custom servers use the chart external catalog described in the MCP migration note."
no_action_reason: "The copy-config endpoint is additive and is used by agent copying in this release; normal deployment keeps existing agent configurations valid. Custom catalogs should mark team-private library fields before cross-team copies."
---

## Applicability

Existing Fred deployments upgrading to this release, including deployments that
ship their own MCP catalog.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

`config_fields` entries of an MCP catalog accept an optional `scope_private`
boolean. When omitted, the field is treated as public. The bundled catalog sets
`scope_private: true` on `chat_options.bound_library_ids`.

In the external catalog prepared during the
[MCP migration](extract-mcp-agent-instructions.md), mark custom
`chat_options.bound_library_ids` fields with `scope_private: true` before copying
agents across teams. Without it, copies retain origin-team library identifiers.
The bundled catalog already carries this marker.

## Upgrade

Deploy matching agent pods, control plane and frontend. The agent copy flow
uses `POST /agents/capabilities/{id}/copy-config` in this release.

## Validation

The agent pods start normally and existing agents, including agents using the
PowerPoint filler and document access, open and answer as before.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Older pods ignore the `scope_private` key.

## Limitations

No additional migration limitations identified for this change.
