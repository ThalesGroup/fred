---
schema: 1
title: "Keep the slash-command menu open while a command is typed"
impact: none
configuration: none
configuration_reason: "Frontend rendering fix only; no configuration keys or defaults change."
no_action_reason: "The chat composer's command menu no longer remounts on each keystroke; nothing to configure or migrate."
after: [3211-compose-chart-registrations]
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

Type `/` then a few letters in the chat composer: the command menu stays open and filters without flickering.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
