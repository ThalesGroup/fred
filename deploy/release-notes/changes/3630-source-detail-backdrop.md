---
schema: 1
title: "Extend the source detail backdrop over the chat composer"
impact: none
configuration: none
configuration_reason: "Only frontend modal placement changes; no configuration keys or defaults change."
no_action_reason: "Existing data and APIs are unchanged; the fix takes effect with normal deployment."
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

In the light theme, open a chat source detail dialog and check that its blurred backdrop covers the composer at the bottom of the page.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
