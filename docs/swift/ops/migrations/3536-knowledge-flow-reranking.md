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

Keep the existing local CrossEncoder available in the Knowledge Flow image if
using local reranking. For optional remote inference, provide an HTTPS endpoint
that supports the indexed-results `/rerank` interface.

## Configuration

Omitting `reranker_model` uses the local CrossEncoder. To select a remote
model, set `reranker_model.provider: rerank`, `name`, and `settings.base_url`
in Knowledge Flow's configuration. Use the service base URL without the final
`/rerank` path. Configure credentials using the procedure "Optional API
keys for Knowledge Flow model uses", before deploying the remote model. The
optional chart value defaults to `null` for both API and worker.

Document access's advanced `rerank` setting defaults to off for new agents and
stored configurations that omit it. Turn it on per agent when the relevance
gain justifies the extra search latency.

## Upgrade

Upgrade Knowledge Flow and the agent runtime and capability with the normal
deployment procedure. Finish rolling out all Knowledge Flow API replicas before
enabling reranking on agents or asking `/vector/search` to rerank. Older API
replicas ignore the new request flag. No data migration or re-ingestion is needed.

## Validation

Search a document through a default document access agent and check that its
search skips reranking. Turn on the agent's advanced `rerank` switch and check
that reranking metrics record a successful request. If remote inference is
configured, check the endpoint succeeds and that an unavailable endpoint
returns `503 reranker_unavailable`.

## Rollback

To resume local reranking, remove `reranker_model` and roll out the affected
Knowledge Flow pods with the restored configuration. To skip reranking during a
full rollback to v3.11.1, turn off the agent setting before restoring the prior
runtime and capability. Restore the prior Knowledge Flow configuration as well.
No data rollback is required.

## Limitations

Remote reranking configuration is global to Knowledge Flow on Swift. A remote
failure does not fall back to the local model; reranking requests return 503.
