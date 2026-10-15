---
schema: 1
title: "Keep the model's answer after a failed tool round"
impact: none
configuration: none
configuration_reason: "Only the ReAct runtime's choice of final answer changes in fred-runtime; no configuration key, default or chart value is involved."
no_action_reason: "No API, event, data or configuration change: agents simply show the model's own answer instead of a generic error after a failed tool round, once the new runtime is deployed."
---
## Applicability

Existing Fred deployments upgrading to this release, including agent pods built on fred-runtime.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Ask an agent a question whose last tool call fails (for example by reaching the per-turn tool-call limit). The chat shows the model's answer, and the failed tool row is still marked as failed.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
