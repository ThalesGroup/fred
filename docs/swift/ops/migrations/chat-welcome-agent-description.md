---
schema: 1
title: "Show the agent description on the chat welcome card"
impact: none
configuration: none
configuration_reason: "Only the chat welcome card (frontend component and styles) changes; no configuration keys or defaults change."
no_action_reason: "The card reads the agent description already returned by the existing agent listing; no data, API or permission changes, so normal deployment is enough."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Start a new conversation with an agent that has a description: the card above the composer shows three columns: agent icon, name and role, then the visible description. A short description makes the card narrower. Long descriptions scroll within the card. On a narrow window the description moves below the identity. An agent without a description keeps its identity visible.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
