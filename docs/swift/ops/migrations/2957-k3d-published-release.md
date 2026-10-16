---
schema: 1
title: "Deploy a published Fred release on the local k3d instance"
impact: none
configuration: local
configuration_reason: "deploy/k3d/values.yaml declares evaluator 1.2.0 for the local k3d instance only; production charts, chart values and schemas are unchanged."
no_action_reason: "No deployed workload, data or API changes; RELEASE is an opt-in for local k3d deployments only."
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

From fred-deployment-factory, run `make k3d-app DIR=<fred checkout> RELEASE=<version>`
and check that every Fred pod runs `ghcr.io/thalesgroup/fred-agent/*:v<version>`.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
