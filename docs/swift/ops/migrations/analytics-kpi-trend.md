---
schema: 1
title: "Analytics tiles open their trend over the period"
impact: none
configuration: none
configuration_reason: "Only the analytics page and two extra series in an existing preset change; no configuration key is involved."
no_action_reason: "The activity preset only gains two keys in its values map; existing data and consumers are unaffected."
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

Open Administration > Analytics > Overview and click the trend icon of Conversations: the curve ends at the tile value.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
