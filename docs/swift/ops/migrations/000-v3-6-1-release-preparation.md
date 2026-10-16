---
schema: 1
title: "Coordinated v3.6.1 upgrade and rollback"
impact: none
configuration: none
configuration_reason: "Release preparation adds no setting; the included changes touch only chart documentation and metadata and the local k3d tooling."
no_action_reason: "Rendered Kubernetes manifests, application behaviour and data are unchanged from v3.6.0; deploying the paired v3.6.1 code and chart is enough."
---

## Applicability

Upgrade from Fred v3.6.0 to v3.6.1 with paired code and chart releases. This
release adds no migration. Python package publication remains a separate
maintainer operation.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. `configuration_prod.yaml` is for local
Docker Compose, not the production reference.

## Upgrade

Deploy the v3.6.1 chart and images normally; no additional operator or user
action is required.

## Validation

`helm show readme oci://ghcr.io/thalesgroup/fred-helm/fred --version 3.6.1`
prints the chart's installation guide, and every Fred pod runs the `v3.6.1`
images.

## Rollback

Use the normal rollback procedure; this release introduces no data migration.

## Limitations

The paired Fred tags do not publish Python packages.
