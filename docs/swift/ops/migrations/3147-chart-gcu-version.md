---
schema: 1
title: "The fred chart documents app.gcu_version (terms of use)"
impact: none
configuration: production
configuration_reason: "deploy/charts/fred/values.yaml now lists applications.control-plane-backend.configuration.app.gcu_version with its existing default, null; behaviour is unchanged, and operators who want users to accept terms of use set a version such as v1."
no_action_reason: "The default stays null, so the rendered configuration behaves as before; deployments that already set gcu_version keep their value."
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

`helm show values` lists `gcu_version` under the control-plane backend's `configuration.app`, with its explanation.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
