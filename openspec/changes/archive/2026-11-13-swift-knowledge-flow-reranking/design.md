# Design

## Context

See proposal.md. Swift's `/vector/search` calls `VectorSearchService.search`, which filters corpus candidates through tag membership and document readability, filters attachments by user and session, enriches visible hits, and merges them with an attachment quota of three. The normal path has no rerank option. Targeted `/vector/similarity-search` and authenticated `/vector/rerank` already use `rerank_documents`, a local CrossEncoder loaded lazily by `ApplicationContext`. `DocumentAccessCapability` calls the typed SDK search port through `DocumentSearchAdapter` and `VectorSearchClient`; its advanced settings have no rerank field.

## Goals / Non-Goals

**Goals:**
- Keep remote model selection in Knowledge Flow's deployment configuration, using `ModelConfiguration` and the same `provider` / `name` / `settings` form as its chat and vision models.
- Share one ranking path across all Knowledge Flow consumers, with an explicit local choice only when no remote reranker is configured.
- Preserve Swift's source ceilings, authorization, attachment quota, citation metadata and direct API contracts.

**Non-Goals:**
- A Control Plane organization model policy, model picker or database migration on Swift.
- A model-callable reranking tool.
- Changing the score used by `min_source_score_ratio`, which remains the original retrieval score.

## Decisions

### Model configuration and remote protocol

Add `reranker_model: ModelConfiguration | None` to Knowledge Flow and its generated schema. A remote entry names a rerank-capable model, an HTTPS-compatible base URL under `settings.base_url`, and an environment variable binding for its API key under `settings.api_key_env`; validate required fields at startup without reading secrets into serialized configuration. The adapter calls `POST {base_url}/rerank` with `model`, `query`, `documents` and `top_n`, and validates indexed `results` with finite scores and unique in-range indices. This matches the indexed-results rerank API used by the Weaver change while keeping Swift's deployment-owned model configuration. It is deliberately a dedicated rerank adapter rather than sending the model through the chat factory, which has no rerank operation.

Keep the existing `crossencoder_model` local configuration for offline path and image-provided default. No remote entry selects the local CrossEncoder. A remote entry that fails request or validation raises a typed reranker-unavailable error surfaced as a 503; it never silently switches to local. Configuration errors fail during startup. Do not log request documents, response bodies or credentials. Bound the entire remote stream to 15 seconds and each serialized passage to 8 KiB. A configured remote model never falls back to local after a request failure.

### Ranking location and bounded work

Extend `/vector/search` with an optional `rerank` boolean whose wire default is false for non-agent callers. `DocumentAccessConfig.rerank` and the manifest's advanced field default to true; the capability passes it through the SDK port, runtime adapter and Knowledge Flow client. The model never sees a separate rerank tool or parameter on the RAG tool itself.

When enabled, ask each existing retrieval branch for a capped wider pool (`min(top_k * 5, 100)`), complete the existing visibility checks, and merge/deduplicate visible candidates before ranking. Keep a hard cap of 100 candidates per model request and a bounded text/response size. Limit to `top_k` only after reranking. Preserve the current attachment inclusion rule by selecting the required attachment slots from reranked visible attachment candidates, then filling the remaining slots from reranked visible candidates. Retain original hit objects and retrieval scores, so provenance and citation filtering remain stable. With reranking disabled, preserve current retrieval size, ordering and response behavior.

The local CrossEncoder runs off the event loop with lazy, concurrency-safe initialization, four prediction slots per pod, a three-second queue wait and a 30-second prediction deadline. A process-level model instance and a shared bounded async HTTP client are performance resources only; no correctness state depends on one pod. Configuration is identical across Knowledge Flow replicas during a deployment; each request carries all data required for ranking.

### Existing callers and observability

Route targeted similarity search and `/vector/rerank` through the same async model selector. Keep their request and response shapes and existing authorization checks. Direct REST requests longer than 100 passages are processed in sequential model batches of at most 100, then sorted globally by scores. Exclude the direct route from the Text MCP tool catalog. Preserve similarity's `rerank=false` path and its `min_score` semantics based on retrieval scores. Retain `rag.rerank_latency_ms`, `rag.rerank_total`, `rag.rerank_docs_total` and `rag.rerank_top_r_total`, with bounded model and status dimensions. Record failures as failures; avoid duplicate counts when a search invokes the shared reranker.

## Risks / Trade-offs

- [Mixed-scope ranking could displace attachments] -> Reapply the existing attachment inclusion policy after ranking, using only visible hits.
- [Remote latency or malformed output on a hot search path] -> Reuse a pooled client, cap candidates and body size, set connect/read timeouts, validate all returned indices and return a clear 503.
- [Local CrossEncoder blocks or races on first load] -> Initialize once behind synchronization and execute inference off the event loop.
- [Existing agents change behavior because the new field defaults on] -> Treat this as the requested behavior change, test absent-field deserialization and keep an explicit off choice.
- [Generated schema or deployment examples drift] -> Regenerate the schema from the typed configuration and verify each shipped configuration.

## Migration Plan

1. Deploy the Knowledge Flow API with the optional request flag and model setting; omitted `reranker_model` uses the baked local CrossEncoder. Keep the existing direct endpoint available.
2. Deploy the agent capability/runtime and UI changes. Missing saved `rerank` fields resolve to true; operators can set false in advanced settings.
3. Configure `reranker_model` in Knowledge Flow's deployment YAML and supply its API key through the named environment variable when remote inference is desired. Roll back by removing that entry to use the local image model; disabling the agent switch avoids reranking for that agent.
