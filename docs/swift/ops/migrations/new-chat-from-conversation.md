---
schema: 1
title: "Start a new conversation from the managed chat header"
impact: none
configuration: none
configuration_reason: "Only the frontend chat header changes; no configuration keys or defaults change."
no_action_reason: "Existing sessions and APIs are unchanged; the action appears with normal frontend deployment."
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

Open an existing managed-agent conversation and check that the header action opens an empty chat for the same agent.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
