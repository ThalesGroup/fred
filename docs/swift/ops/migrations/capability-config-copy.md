---
schema: 1
title: "Capabilities classify their settings by scope and can prepare a copy of their configuration"
impact: none
configuration: production
configuration_reason: "The bundled MCP catalog in deploy/charts/fred/values.yaml marks chat_options.bound_library_ids with the new optional scope_private: true; no other key or default changes."
no_action_reason: "The new pod endpoint is additive and nothing calls it yet; existing agents, stored configurations and MCP catalogs keep working unchanged."
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

Deployments that maintain their own MCP catalog can add the same line to their
`chat_options.bound_library_ids` fields now. It only matters once copying agents
between teams is released; that release's note will say so again.

## Upgrade

Deploy Fred normally; no additional operator action is required. The agent pods
expose `POST /agents/capabilities/{id}/copy-config`, which no component calls in
this release.

## Validation

The agent pods start normally and existing agents, including agents using the
PowerPoint filler and document access, open and answer as before.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Older pods ignore the `scope_private` key.

## Limitations

No additional migration limitations identified for this change.
