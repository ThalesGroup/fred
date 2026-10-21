---
schema: 1
title: "Stable local k3d image tags"
impact: none
configuration: none
configuration_reason: "Only local deploy/k3d/build image tag calculation changes; production images, values and schemas are unchanged."
no_action_reason: "The normal local deployment command generates and imports the new tags automatically."
---
## Applicability

Local k3d deployments built from a Fred checkout.

## Prerequisites

Use the existing Docker and k3d development environment. No additional tools or
service upgrades are required for this tag calculation change.

## Configuration

No configuration changes are required. Existing deployment commands, chart
values and credentials remain unchanged.

## Upgrade

Run the usual application deployment command. The first run adopts new tags and
may import all images once. Subsequent builds with unchanged filesystem layers,
runtime configuration and platform retain their tags despite provenance changes.

## Validation

After an unchanged rebuild, confirm the same image references are emitted and
already-present images are skipped by the deployment factory's importer.

## Rollback

Revert the build script and redeploy. No data migration or configuration change.

## Limitations

Docker build commands still run and use Docker's layer cache. This change does
not skip provisioning hooks or Helm sync, and makes no build-duration guarantee.
