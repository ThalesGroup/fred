---
schema: 1
title: "Authenticate model discovery through Azure APIM"
impact: none
configuration: none
configuration_reason: "Bundled Fred configuration is unchanged; operators can enable an optional Azure APIM discovery source after upgrading the agent image."
no_action_reason: "Azure APIM discovery is opt-in. Deployments without this source retain their existing model catalogs, routing and credentials, with no data migration or operator action."
---
## Applicability

This applies to agent pods that discover chat models through Azure APIM. Existing static profiles and ordinary OpenAI discovery need no change.

## Prerequisites

An operator enabling the optional source must provide `AZURE_AD_CLIENT_SECRET` and `AZURE_APIM_SUBSCRIPTION_KEY` to the agent pod. The APIM product must allow its model-list endpoint for the configured Entra client and subscription.

## Configuration

No bundled configuration changes are required. To enable the feature, set the discovery source's `provider` to `azure-apim` and supply the six non-secret `azure_apim_settings` fields already used by static Azure APIM profiles. The discovery URL must stay within the configured APIM origin and resource path. Keep `include_model_ids` limited to verified chat models when the gateway omits chat capability metadata.

## Upgrade

Deploy an agent image containing this change before enabling the optional discovery source. Restart agent pods after changing their mounted model catalog; static profiles remain available during the rollout. Deployments without this source need no extra upgrade step or database migration.

## Validation

Refresh the configured source and confirm its model list succeeds with OAuth and the APIM subscription header. Confirm a discovered model can be selected for a managed turn, and that an existing model with a Responses API route retains that route. The source URL may be edited only within the configured HTTPS origin and APIM product path.

## Rollback

Remove or comment out the optional discovery source and restart agent pods. Keep the existing static Azure APIM profiles and their credentials.

## Limitations

Discovery does not grant access to new models automatically. If the gateway omits chat capability metadata, use `include_model_ids` to prevent embedding models from appearing as chat choices.
