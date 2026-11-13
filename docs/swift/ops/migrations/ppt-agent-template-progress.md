---
schema: 1
title: "Show progress while an agent's PowerPoint template is prepared"
impact: none
configuration: none
configuration_reason: "Only frontend progress indicators and text change; no configuration keys or defaults change."
no_action_reason: "Existing upload and analysis APIs are unchanged; the indicators appear after a normal deployment."
---

## Applicability

Existing Fred deployments using PowerPoint template overrides on agents.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Upload a PowerPoint template override and save the agent. The form shows upload
progress and says the window can be closed. The agent card shows preparation
progress until
the template analysis succeeds or fails.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The existing polling schedule determines when the card reflects the final
preparation state.
