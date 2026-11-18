## Context

Knowledge Flow already shares one bounded `DocumentReranker` and HTTP connection pool across requests. Its `rerank` provider posts to `<base_url>/rerank` with a bearer token and consumes indexed `results`. The supplied OpenAPI instead defines `POST /models/bge-reranker-v2-m3:predict`, requires an `apikey` header, accepts only `query` and `documents`, and returns positional `predictions`. This is a distinct wire protocol, and the model name belongs in the URL. The local PRISM values pin `v3.11.0`; the first released remote reranker implementation is v3.12.0 and does not support this protocol.

## Goals / Non-Goals

**Goals:**

- Keep both remote protocols inside the existing bounded reranker path and reuse its shared HTTP client, timeout, error mapping, and credential selection.
- Make the configured protocol explicit so existing `rerank` deployments retain their wire contract.
- Prepare both local PRISM environments to use the production BGE endpoint only after a compatible Fred release exists.

**Non-Goals:**

- Change the per-agent `rerank` default, search authorization, candidate limit, or result contract.
- Add a proxy service or place API keys in model settings or the untracked values files.

## Decisions

1. Add provider `predict` to `RerankerModelConfiguration` and retain `rerank`. Treat `name` as a model path segment for `predict`, with URL encoding or validation that prevents path manipulation. Reject base URLs containing a query or fragment so the protocol path cannot be swallowed by URL components. The provider names describe the response protocols, not a model vendor.
2. Branch request construction and response decoding by provider inside `DocumentReranker`. The `predict` branch posts `{"query": ..., "documents": [...]}` to `<base_url>/models/<name>:predict`, sends the selected key as `apikey`, and maps each prediction's array position to the input document index. Keep the existing body and text bounds, 15-second overall timeout, response size cap, connection pool, and finite score checks. Do not include an `Authorization` header for `predict`.
3. Continue using `api_key_for_role("reranker")`. In the requested PRISM setup, its `OPENAI_API_KEY` fallback supplies the `apikey` value; no secret is added to model YAML. `KNOWLEDGE_FLOW_RERANKER_API_KEY` remains available for later separation.
4. Configure `reranker_model` in both Knowledge Flow API and worker sections of each local values file after the new adapter is released. Use `https://api.corp.thales/corp/genai/reranker/v1` in both int and prod, as requested. Keep both files untracked, unstaged, and out of commits and pushes.

## Risks / Trade-offs

- [The production endpoint is used from integration] -> Validate network reachability and credentials from integration before enabling agent reranking; an unavailable remote model returns the existing 503 instead of falling back.
- [A malformed score array could reorder the wrong passages] -> Require exactly one finite numeric score per submitted document and reject booleans, missing entries, and extra entries.
- [A release or image tag may not yet exist] -> Keep local activation pending until a chart and image containing the adapter are available; do not point v3.11.0 or v3.12.0 images at this protocol.
- [Concurrent search load can stress the remote service] -> Reuse the existing bounded batches and shared HTTP pool; verify concurrent requests do not cross credentials or results.

## Migration Plan

1. Implement and test the new provider in Fred, including configuration validation and operator guidance. Release a chart and images containing it.
2. In the two local PRISM files, select that released image version, set `reranker_model.provider: predict` with model name `bge-reranker-v2-m3` for Knowledge Flow API and worker, and use the production service base URL. Supply the existing `OPENAI_API_KEY` through the current secret mechanism.
3. Validate one authenticated predict request and a reranked document search in integration, then validate production. Agent reranking remains controlled by each agent's advanced setting.
4. Roll back by removing `reranker_model` from both Knowledge Flow configurations and restarting affected pods; this restores the local CrossEncoder for agents with reranking enabled.
