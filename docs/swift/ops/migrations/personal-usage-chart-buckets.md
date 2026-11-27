---
schema: 1
title: "Show complete personal token scale and selectable calendar grouping"
impact: none
configuration: none
configuration_reason: "The existing KPI bucket and time-zone parameters are reused; no configuration changes."
no_action_reason: "Existing token events and API clients remain valid; normal deployment enables the chart update."
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

Open My usage with large token values, confirm every Y-axis label is visible, then switch between 1D, 1W and 1M within the same date range.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
