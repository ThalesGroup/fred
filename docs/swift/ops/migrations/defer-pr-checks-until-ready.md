---
schema: 1
title: "Run PR quality and tests when ready for review"
impact: none
configuration: none
configuration_reason: "Only the GitHub Actions trigger changes; deployed Fred configuration is unaffected."
no_action_reason: "The PR validation schedule changes without altering Fred runtime behavior or deployment steps."
---
## Applicability

This change affects GitHub pull request validation only; existing Fred deployments are unaffected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open a draft PR and confirm that `Check pending request` skips its jobs. Mark it ready for review and confirm that the checks run.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
