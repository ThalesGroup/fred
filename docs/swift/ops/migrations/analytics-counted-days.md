---
schema: 1
title: "Analytics can leave weekends and French public holidays out"
impact: none
configuration: none
configuration_reason: "No configuration key changes; the setting is a per-viewer choice in the analytics pages."
no_action_reason: "The new preset parameters default to counting every day, so existing API consumers see the same figures; no data migration."
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

Open Administration > Analytics, open the counted-days settings and include weekends: per-day averages change.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Only French public holidays are known.
