---
schema: 1
title: "Expose the shared theme calendar clock"
impact: none
configuration: none
configuration_reason: "The frontend publishes two additive theme values using a fixed event time zone."
no_action_reason: "The existing theme and ZIP formats are compatible with the additional clock values."
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

Inspect the document element for the Paris date and the numeric CSS property --fred-seconds-since-midnight.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
