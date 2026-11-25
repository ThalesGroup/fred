---
schema: 1
title: "Prevent repeated dialog scroll measurements from crashing chat"
impact: none
configuration: none
configuration_reason: "Only frontend dialog rendering changes; no configuration keys or defaults change."
no_action_reason: "Existing data and APIs are unchanged; the fix takes effect with a normal deployment."
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

Open a chat with many queued messages and confirm that the page remains usable.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
