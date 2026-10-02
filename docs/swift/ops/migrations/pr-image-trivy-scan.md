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

On a pull request changing a production Dockerfile, an image dependency manifest or lockfile, or an image build recipe, confirm each publishable Docker image job publishes a Trivy summary and attaches its JSON report. On other pull requests, confirm all five image builds still run while Trivy steps are skipped. `ws-bench` remains build-only. A critical finding produces a warning annotation without failing that job.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This is an advisory pull request scan. Release publication does not run Trivy and critical findings do not block a merge. The frontend's final image contains built static assets, so scanning that image does not inventory npm packages used only in the builder stage.
