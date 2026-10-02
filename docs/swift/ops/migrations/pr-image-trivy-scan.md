---
schema: 1
title: "Scan pull request Docker images with Trivy"
impact: none
configuration: none
configuration_reason: "Only the GitHub Actions pull request image workflow changes; deployment configuration is unchanged."
no_action_reason: "The scan runs in CI on pull requests and does not change released images, application data, or runtime behavior."
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

On any pull request, confirm all five Docker images build and the four publishable final images receive separate Trivy checks and JSON reports. The frontend builder stage and all tracked Python and npm lockfiles also receive checks. Job logs list findings across all severities, and the JSON reports include package inventories; critical findings produce warning annotations without failing the checks. `ws-bench` remains build-only.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This is an advisory pull request scan. Release publication does not run Trivy and critical findings do not block a merge. Lockfile findings include development and fixture dependencies that may not appear in production images. Newly disclosed CVEs appear only when another pull request runs; there is no scheduled scan.
