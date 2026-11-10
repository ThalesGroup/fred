---
schema: 1
title: "Build Docker images only when pull requests are ready for review"
impact: none
configuration: none
configuration_reason: "Only the GitHub Actions pull request trigger and job condition change; deployment configuration is unaffected."
no_action_reason: "Published images, application code and deployment behavior are unchanged."
---
## Applicability

This change affects GitHub Actions checks for pull requests. Existing deployments are unaffected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

Open or update a draft pull request and confirm the Docker image job is skipped. Mark it ready for review and confirm the affected images build.

## Rollback

Revert the workflow change to restore Docker image builds on draft pull requests. No data rollback is needed.

## Limitations

Manual runs of the Docker image check still build all images.
