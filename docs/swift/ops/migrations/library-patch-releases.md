---
schema: 1
title: "Prepare new library release versions"
impact: none
configuration: none
configuration_reason: "Only library release metadata, changelogs and local dependency lockfiles change; deployment configuration is unaffected."
no_action_reason: "Version preparation does not publish packages or change runtime behavior; existing deployments use the normal upgrade procedure."
---
## Applicability

All Python libraries under `libs/`, including capabilities, and the three public
frontend npm packages. Application and Helm chart versions are unchanged.

## Prerequisites

No additional deployment prerequisites. Package publication is a separate step
after merge into Swift.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally. Library maintainers publish the new coordinates after merge,
using the existing Python targets and protected npm release workflow.

## Validation

Check that library manifests and regenerated lockfiles agree, and that the frontend
release contract and package archive checks pass for the new coordinates.

## Rollback

Use the previous application image or dependency lockfile. No data migration is
introduced and existing published package versions are not replaced.

## Limitations

This change does not publish or verify registry artifacts. External npm consumers
must still follow the existing design-token migration guidance when adopting the
new archives; this metadata change adds no further API or token changes.
