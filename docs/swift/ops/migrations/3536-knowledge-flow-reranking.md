---
schema: 1
title: "Configure Knowledge Flow reranking for document search"
impact: minor
configuration: production
configuration_reason: "Knowledge Flow gains an optional reranker_model in deployment configuration, and document access enables reranking by default."
---
## Applicability

Fred deployments using document access or Knowledge Flow vector search.

## Prerequisites

Keep the existing local CrossEncoder available in the Knowledge Flow image. For
optional remote inference, provide an HTTPS-compatible reranking endpoint and
its API key through a Knowledge Flow environment variable.

## Configuration

Omitting `reranker_model` uses the local CrossEncoder. To select a remote
model, set `reranker_model.provider: rerank`, `name`,
`settings.base_url`, and `settings.api_key_env` in Knowledge Flow's
configuration. Supply the named environment variable to Knowledge Flow API
pods. Do not put the API key in YAML. The optional chart value defaults to
`null` for both API and worker. Document access's advanced `rerank` setting
defaults to on for existing and new agents; turn it off per agent if needed.

## Upgrade

Deploy Knowledge Flow before the agent runtime and capability so `/vector/search`
accepts the new request flag. No data migration or re-ingestion is needed.
Remote inference is optional and may be configured after the normal upgrade.

## Validation

Search a document through a document access agent and check that reranking
metrics record a successful request. Turn off the agent's advanced `rerank`
switch and check that its search skips reranking. If remote inference is
configured, check the endpoint succeeds and that an unavailable endpoint
returns `503 reranker_unavailable`.

## Rollback

Remove `reranker_model` and restart Knowledge Flow API pods to return to the
local CrossEncoder. Turn off the agent switch to skip reranking. For a full
version rollback, restore the prior runtime and capability along with Knowledge
Flow. No data rollback is required.

## Limitations

Remote reranking configuration is global to Knowledge Flow on Swift. A remote
failure does not fall back to the local model; reranking requests return 503.
