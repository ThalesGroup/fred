---
schema: 1
title: "Keep page content on screen during background refreshes"
impact: none
configuration: none
configuration_reason: "Only frontend behaviour changes."
no_action_reason: "The change ships with the normal deployment and stores no new data."
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

Leave the prompt marketplace open for one minute: the list stays on screen during its refresh.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
