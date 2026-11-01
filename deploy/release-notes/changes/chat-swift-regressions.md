---
schema: 1
title: "Restore conversation behaviours missing from Weaver"
impact: none
configuration: none
configuration_reason: "Only frontend components and translations change."
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

Open a conversation: the model can be changed before typing.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
