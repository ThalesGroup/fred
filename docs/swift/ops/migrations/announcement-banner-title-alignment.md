---
schema: 1
title: "Centre the announcement banner title when its description wraps"
impact: none
configuration: none
configuration_reason: "Only a CSS alignment rule changes; no configuration key, default or chart value is involved."
no_action_reason: "Presentation-only frontend change; stored announcements, APIs and per-browser dismissal state are untouched."
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

Open an announcement whose short description wraps onto two lines and check
that its title is centred vertically, like the severity icon and the actions.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
