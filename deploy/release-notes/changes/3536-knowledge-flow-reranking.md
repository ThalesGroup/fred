---
schema: 1
title: "Configure Knowledge Flow reranking for document search"
impact: minor
configuration: production
configuration_reason: "Knowledge Flow gains an optional reranker_model in deployment configuration; document access can enable reranking per agent."
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
`settings.base_url` in Knowledge Flow's
configuration. Supply `KNOWLEDGE_FLOW_RERANKER_API_KEY` (or the `OPENAI_API_KEY` fallback) to Knowledge Flow API
pods. Do not put the API key in YAML. The optional chart value defaults to
`null` for the API; the worker does not rerank searches. Document access's advanced `rerank` setting
defaults to off for new agents and stored configurations that omit it. Turn it
on per agent when the relevance gain justifies the extra search latency.
Previously saved values remain unchanged.

## Upgrade

Deploy Knowledge Flow before the agent runtime and capability so `/documents/search`
accepts the new request flag. No schema change or re-ingestion is introduced; Weaver supports fresh installations only.
Remote inference is optional and may be configured after the normal upgrade.

## Validation

Search a document through a default document access agent and check that its
search skips reranking. Turn on the agent's advanced `rerank` switch and check
that reranking metrics record a successful request. If remote inference is
configured, check the endpoint succeeds and that an unavailable endpoint
returns `503 reranker_unavailable`.

## Rollback

Remove `reranker_model` and restart Knowledge Flow API pods to return to the
local CrossEncoder. Turn off the agent switch to skip reranking. For a full
version rollback, restore the prior runtime and capability along with Knowledge
Flow. No data rollback is required.

## Limitations

Remote reranking configuration is global to Knowledge Flow on Weaver. A remote
failure does not fall back to the local model; reranking requests return 503.
