# Proposal

## Why

Some Azure APIM gateways expose an OpenAI-compatible model list but require both a Microsoft Entra client-credentials token and an APIM subscription key. Fred's current discovery sends only `OPENAI_API_KEY` as a Bearer token, so discovery fails even though static Azure APIM inference works.

## What Changes

- Allow a discovery source to select Azure APIM authentication and provide the non-secret connection settings already used by static `azure-apim` profiles.
- Authenticate model-list and model-detail requests with Entra OAuth and the pod-local APIM subscription key. Keep the current OpenAI-compatible behavior as the default.
- Generate `azure-apim` chat profiles with inference settings that make discovered models routable through the existing provider.
- Constrain administrator URL overrides for Azure APIM sources so credentials cannot be redirected to an unconfigured origin or gateway path.
- Document optional configuration and verify list, detail, refresh, routing, failure, and credential-boundary behavior. This is a focused slice of #3254; per-source Kubernetes Secret references remain outside this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `model-routing`: Add authenticated Azure APIM discovery while preserving OpenAI-compatible sources and safe administrator overrides.

## Impact

`fred-runtime` model catalog loading and discovery, its tests, and a new operator migration note. The existing `fred-core` Azure APIM inference provider and pod-local `AZURE_AD_CLIENT_SECRET` and `AZURE_APIM_SUBSCRIPTION_KEY` are reused. Existing deployments without an Azure APIM discovery source keep their behavior. No database or public HTTP API migration is planned.
