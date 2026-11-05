# Proposal

## Why

PRISM C2's model gateway lists models at `/ai-models/openai/v1/models`, but it requires a Microsoft Entra client-credentials token and an APIM subscription key. Fred's current discovery sends only `OPENAI_API_KEY` as a Bearer token, so enabling discovery in C2 values would fail even though static Azure APIM inference works.

## What Changes

- Allow a discovery source to select Azure APIM authentication and provide the non-secret connection settings already used by static `azure-apim` profiles.
- Authenticate model-list and model-detail requests with Entra OAuth and the pod-local APIM subscription key. Keep the current OpenAI-compatible behavior as the default.
- Generate `azure-apim` chat profiles with inference settings that make discovered models routable through the existing provider.
- Constrain administrator URL overrides for Azure APIM sources so credentials cannot be redirected to an unconfigured origin or gateway path.
- Document the C2 configuration and verify list, detail, refresh, routing, failure, and credential-boundary behavior. This is a focused slice of #3254; per-source Kubernetes Secret references remain outside this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `model-routing`: Add authenticated Azure APIM discovery while preserving OpenAI-compatible sources and safe administrator overrides.

## Impact

`fred-runtime` model catalog loading and discovery, its tests, and the model-discovery operator guide. The existing `fred-core` Azure APIM inference provider and pod-local `AZURE_AD_CLIENT_SECRET` and `AZURE_APIM_SUBSCRIPTION_KEY` are reused. No database or public HTTP API migration is planned. No release tag or C2 deployment is part of this change.
