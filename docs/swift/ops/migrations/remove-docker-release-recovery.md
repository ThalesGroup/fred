---
schema: 1
title: "Keep the Docker provenance fix within the existing release workflow"
impact: none
configuration: none
configuration_reason: "Only CI orchestration changes; application and chart configuration are unchanged."
no_action_reason: "The manual recovery path is removed while OCI export and maximum provenance remain; deployments need no changes."
---

## Applicability

Docker release CI. This narrows the earlier exporter correction to its intended scope.

## Prerequisites

No additional deployment prerequisites.

## Configuration

No configuration changes are required.

## Upgrade

Deploy normally. Releases continue through the existing code/chart tag workflow.
The extra manual recovery dispatch and its parameters are removed.

## Validation

Release images retain maximum provenance and Trivy reads their OCI export.
The original paired-tag and migration-guide validation remains in place.
The release description lists the published Knowledge Flow PyMuPDF image.

## Rollback

Revert this CI change; no database or application rollback is required.

## Limitations

Already published images and Git tags are unchanged.
