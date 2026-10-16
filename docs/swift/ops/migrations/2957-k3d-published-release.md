---
schema: 1
title: "Fred's k3d values move to fred-deployment-factory, which deploys published releases"
impact: none
configuration: local
configuration_reason: "deploy/k3d/values.yaml and the k3d hooks move to fred-deployment-factory (k3d-apps/fred/); only the local k3d instance is affected, production charts, chart values and schemas are unchanged."
no_action_reason: "No deployed workload, data or API changes; only the local k3d command changes, to make k3d-app APP=fred [DIR=<fred checkout>]."
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

From fred-deployment-factory, run `make k3d-app APP=fred` and check that every Fred pod
runs `ghcr.io/thalesgroup/fred-agent/*:v<pinned version>`.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
