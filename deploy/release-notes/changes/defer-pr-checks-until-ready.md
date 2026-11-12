---
schema: 1
title: "Run PR quality and tests when ready for review"
impact: none
configuration: none
configuration_reason: "Only the GitHub Actions trigger and draft gate change; deployed Fred configuration is unaffected."
no_action_reason: "The PR validation schedule changes without altering Fred runtime behavior or deployment steps."
---

## Applicability

This change affects the `Check pending request` GitHub Actions workflow only;
Fred deployments are unaffected.

## Prerequisites

No additional prerequisites beyond the existing GitHub Actions setup.

## Configuration

No deployment configuration changes are required.

## Upgrade

Apply the updated workflow in the repository; no deployment or data migration
is needed for this change.

## Validation

Open a draft PR and confirm that `Check pending request` skips its jobs. Mark it
ready for review and confirm that the applicable checks run. Convert it back to
a draft and confirm that the replacement workflow run skips its jobs.

## Rollback

Revert the workflow change to restore checks on draft PR updates. No Fred
deployment or data rollback is required.

## Limitations

Other workflows retain their own triggers. Execution on GitHub must be checked
separately from local YAML validation.
