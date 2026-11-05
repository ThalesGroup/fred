---
schema: 1
title: "Authenticate model discovery through Azure APIM"
impact: none
configuration: none
configuration_reason: "Bundled Fred configuration is unchanged; operators can enable an optional Azure APIM discovery source after upgrading the agent image."
no_action_reason: "Existing catalogs, data and APIs remain unchanged. C2 discovery stays commented, so this change needs no migration or operator action during a normal Fred deployment."
---
## Applicability

This applies to agent pods that discover chat models through Azure APIM. Existing static profiles and ordinary OpenAI discovery need no change.

## Prerequisites

The agent pod must receive the existing `AZURE_AD_CLIENT_SECRET` and `AZURE_APIM_SUBSCRIPTION_KEY` environment variables. The APIM product must allow its `/v1/models` endpoint for the configured Entra client and subscription.

## Configuration

No bundled configuration changes are required. To enable the feature later, set the discovery source's `provider` to `azure-apim` and supply the six non-secret `azure_apim_settings` fields already used by static Azure APIM profiles. PRISM C2's tested discovery base URL is `https://api.thalesdigital.io/ai-models/openai/v1`, with inference resource path `/ai-models/openai`. Keep `include_model_ids` limited to verified chat models when the gateway omits chat capability metadata. PRISM C2 stages this source as a commented block until a new Fred release is tagged.

## Upgrade

Deploy an agent image containing this change before enabling the C2 discovery block. Restart agent pods after changing their mounted model catalog; static profiles remain available during the rollout. No database migration is added by this change.

## Validation

Refresh the configured source and confirm its model list succeeds with OAuth and the APIM subscription header. Confirm a discovered model can be selected for a managed turn, and that an existing model with a Responses API route retains that route. The source URL may be edited only within the configured HTTPS origin and APIM product path.

## Rollback

Remove or comment out the optional discovery source and restart agent pods. Keep the existing static Azure APIM profiles and their credentials.

## Limitations

Discovery does not grant access to new models automatically. If the gateway omits chat capability metadata, use `include_model_ids` to prevent embedding models from appearing as chat choices; the staged C2 list contains only its three existing chat models.
