---
schema: 1
title: "Queue and send messages during active agent turns"
impact: none
configuration: none
configuration_reason: "The chat UI and agent runtime add turn steering without changing deployment settings or permissions."
no_action_reason: "Queued messages remain in the browser until sent, and forced messages use the active runtime process; no stored data needs conversion."
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

During an agent turn, queue a message and choose Send. Verify it reaches the agent at the next model boundary, including after a tool confirmation.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Forced messages awaiting a model boundary are held in the active runtime process, so a runtime restart can require the person to resend them.
