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

On a pull request that selects Docker images for building, confirm each selected publishable final image receives a separate Trivy check and JSON report. A frontend build also runs a check of its npm lockfile, including development dependencies. Job logs list findings from CRITICAL through UNKNOWN, and the JSON reports include package inventories; critical findings produce warning annotations without failing the checks. `ws-bench` remains build-only. A documentation-only pull request can select no images and run no Trivy checks.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This is an advisory pull request scan. Release publication does not run Trivy and critical findings do not block a merge. Image scans cover only final images; the frontend lockfile check covers declared npm dependencies, including development dependencies, but does not prove which packages reached the shipped JavaScript bundle. Intermediate build-stage packages are not inventoried separately. Newly disclosed CVEs appear only when another pull request runs; there is no scheduled scan.
