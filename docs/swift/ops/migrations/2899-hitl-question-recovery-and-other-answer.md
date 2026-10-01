---
schema: 1
title: "Improve HITL question recovery and Other answers"
impact: none
configuration: none
configuration_reason: "Agent-question handling, managed-chat presentation, and frontend TypeScript path resolution change; no deployment configuration keys or defaults change."
no_action_reason: "Existing data and APIs are unchanged; the updated behavior takes effect through normal deployment."
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

Ask an interactive agent a question with multiple choices. Confirm that an Other text field appears below the choices, accepts an answer, and that a question following an invalid tool call does not show the previous failure as a final response.

## Rollback

Use the normal rollback procedure; this change introduces no data migration. Pending questions created before or after the deployment keep the answer forms stored in their checkpoints.

## Limitations

An agent can still submit more than four choices. Such a call is rejected, and the agent must retry with at most four choices.
