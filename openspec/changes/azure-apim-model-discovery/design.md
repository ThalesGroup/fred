# Design

## Context

See `proposal.md`. `ModelCatalog.resolve_discovery`, its async counterpart, and model-detail lookup currently send `OPENAI_API_KEY` to `{base_url}/models`. Generated profiles always use the `openai` provider. Static `azure-apim` profiles already use Entra client credentials and `TrustNest-Apim-Subscription-Key` for inference. C2's confirmed list URL is `https://api.thalesdigital.io/ai-models/openai/v1/models`; its inference provider uses the `/ai-models/openai` resource path. The list and inference paths are related but not identical.

## Goals / Non-Goals

**Goals:**

- Reuse the pod-local Azure APIM secrets and existing inference provider without putting credentials in YAML, control-plane state, or API payloads.
- Make generated profiles constructible for chat routing, and make invalid source settings fail before advertisement.
- Preserve existing OpenAI-compatible sources and keep discovery bounded per request and per response.

**Non-Goals:**

- Per-source Kubernetes SecretKeyRef wiring or secret rotation policy from the remainder of #3254.
- Automatically classifying every model in a gateway's inventory. C2 can use `include_model_ids` for known chat models when the upstream omits capabilities.
- A release tag or C2 deployment.

## Decisions

### Source contract and inference settings

Add an explicit `provider` choice to `ModelDiscoverySource`, defaulting to `openai`. An `azure-apim` source requires a typed, non-secret inference-settings object with the six fields already required by `fred_core.model.factory.get_model()`. Validate its origin and resource path against the source's configured `/v1` base URL. Generated chat profiles use `provider: azure-apim`, the returned wire ID, and those settings. They override inherited `temperature` with `null` so a catalog-wide value is not forced on reasoning models; a source may set other supported non-secret model knobs. The alternative of reusing an arbitrary `dict` would allow credential-shaped keys and produce unroutable profiles after a successful list response.

### Discovery authentication

Centralize request-header construction for list and detail calls. For Azure APIM, obtain a token with the configured tenant, client ID, scope, and `AZURE_AD_CLIENT_SECRET`, then send it with `AZURE_APIM_SUBSCRIPTION_KEY` only to the configured gateway. Use synchronous and asynchronous Azure Identity credentials for the corresponding catalog paths. Keep the existing `OPENAI_API_KEY` branch unchanged. Missing secrets fail before any gateway request. Token failures surface a redacted error class, never token or secret text. Each call has the existing 1 MiB response bound and no redirects. Discovery is an occasional refresh, not a per-turn model call; no process-local state is needed for correctness across pods.

### Administrator URL override

For an Azure APIM source, reject a URL change before acquiring credentials or sending an HTTP request. The Models admin view marks its URL read-only and still permits refresh at the configured URL. Existing editable URL behavior remains for standard sources. A previously persisted override for a source converted to Azure APIM is rejected until cleared, keeping the last verified inventory rather than redirecting credentials. Allowing arbitrary admin URLs would create a credential-exfiltration path; restricting only the hostname would still permit untrusted routes on the same gateway.

## Risks / Trade-offs

- [The upstream list includes non-chat models without capability metadata] -> Use `include_model_ids` in C2 values until the gateway supplies trustworthy chat capability flags.
- [OAuth token acquisition can fail while static profiles still work] -> Preserve the last verified discovery inventory and keep static profiles available, following the existing refresh behavior.
- [A saved URL override becomes invalid when a source is switched to Azure APIM] -> Reject it explicitly and require an administrator to clear it; do not send credentials to the saved URL.
- [Using one source-wide model-settings object cannot tune every heterogeneous model] -> Keep the first PR focused on known chat IDs and retain manual profiles for model-specific settings.

## Migration Plan

Ship the Fred change first, then configure the C2 source with the exact tested `/ai-models/openai/v1` base URL, the existing non-secret APIM settings, and an explicit chat-model allowlist. Publish a new Fred image and chart only in a later, separately approved release. Rollback removes the optional source and keeps static profiles; no database migration is required.
