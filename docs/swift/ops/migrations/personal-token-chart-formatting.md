---
schema: 1
title: "Format personal token charts with compact values"
impact: none
configuration: none
configuration_reason: "Only frontend chart formatting changes; no configuration keys or defaults change."
no_action_reason: "Existing token data and APIs are unchanged; the display update takes effect with normal deployment."
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

Open My usage with large token counts. Check that the personal chart scales and hover values use compact k/M values and that the date-range control remains in the page header.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
