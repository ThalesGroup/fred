---
schema: 1
title: "Restore the default model catalog in the agent image"
impact: none
configuration: none
configuration_reason: "The production image again includes the existing default models_catalog.yaml; no configuration key or Helm value changes. The Fred chart continues to mount its configured catalog at the same path."
no_action_reason: "The default returns with the normal agent image update. Existing model profiles, data and APIs do not change."
---

## Applicability

Fred agent pods deployed with the production image.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required. Deployments outside the Fred chart can
use the bundled model catalog or continue to mount their own.

## Upgrade

Deploy the updated agent image normally; no additional action is required.

## Validation

Verify that `/app/config/models_catalog.yaml` exists in the agent image. A pod
with its normal configuration and no separate model-catalog mount can load the
bundled default; a Helm-managed pod continues to use the mounted chart catalog.

## Rollback

Use the normal image rollback procedure; this change introduces no data migration.

## Limitations

The agent pod still requires its normal configuration and environment settings.
