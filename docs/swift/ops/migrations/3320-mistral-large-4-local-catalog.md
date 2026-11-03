---
schema: 1
title: "Add Mistral Large 4 to the local text model catalog"
impact: none
configuration: local
configuration_reason: "Only apps/fred-agents/config/models_catalog.yaml gains a local chat profile using existing schema fields. Production Helm catalogs and defaults are independent and unchanged."
no_action_reason: "Existing deployments keep their configured catalogs and defaults; this adds a selectable profile to the developer catalog without changing runtime code, permissions or data."
---
## Applicability

Local developer agent pods loading the repository's
`apps/fred-agents/config/models_catalog.yaml`.

## Prerequisites

Using the optional profile requires the existing `OPENAI_API_KEY` to contain a
Mistral API key with access to `mistral-large-4`.

## Configuration

The local catalog adds `chat.mistral.large4`, displayed as Mistral Large 4,
through the existing OpenAI-compatible Mistral endpoint. It declares thinking
support with `reasoning_effort: high`; existing platform and team controls
continue to determine access and reasoning activation. The default remains
`chat.mistral.small`. No schema or production chart values change.

## Upgrade

Deploy Fred normally. Local hot reload picks up the catalog edit; restart a
local agent process running without reload to load the updated catalog.

## Validation

Confirm that the loaded agent model catalog advertises Mistral Large 4 with
profile `chat.mistral.large4` and wire model `mistral-large-4`. Use the existing
model access controls to make it selectable for the intended team.

## Rollback

Restore the previous local catalog and reload the agent pod. This introduces
no database migration or new permission mechanism.

## Limitations

Provider inference was not called as part of the offline catalog validation.
Deployments using a separate catalog keep their own model inventory.
