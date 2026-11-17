# Migration guide - v3.12.0

Upgrade from: `code/v3.11.1`
Operational impact: **minor** (minimum version: `3.12.0`).

Review these procedures together in the listed dependency order before deployment. Customer-specific values remain in their private repositories; Fred chart values are the production reference. Configuration files named configuration_prod.yaml are for local development only.

No-operation declarations describe ordinary deployment only. Conditional activation steps still require preparation. Validate combined upgrade and rollback in staging before production.

## Configure Knowledge Flow reranking for document search

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/3536-knowledge-flow-reranking.md)

### Applicability

Fred deployments using document access or Knowledge Flow vector search.

### Prerequisites

Keep the existing local CrossEncoder available in the Knowledge Flow image if
using local reranking. For optional remote inference, provide an HTTPS endpoint
that supports the indexed-results `/rerank` interface.

### Configuration

Omitting `reranker_model` uses the local CrossEncoder. To select a remote
model, set `reranker_model.provider: rerank`, `name`, and `settings.base_url`
in Knowledge Flow's configuration. Use the service base URL without the final
`/rerank` path. Configure credentials using the procedure "Optional API
keys for Knowledge Flow model uses", before deploying the remote model. The
optional chart value defaults to `null` for both API and worker.

Document access's advanced `rerank` setting defaults to off for new agents and
stored configurations that omit it. Turn it on per agent when the relevance
gain justifies the extra search latency.

### Upgrade

Upgrade Knowledge Flow and the agent runtime and capability with the normal
deployment procedure. Finish rolling out all Knowledge Flow API replicas before
enabling reranking on agents or asking `/vector/search` to rerank. Older API
replicas ignore the new request flag. No data migration or re-ingestion is needed.

### Validation

Search a document through a default document access agent and check that its
search skips reranking. Turn on the agent's advanced `rerank` switch and check
that reranking metrics record a successful request. If remote inference is
configured, check the endpoint succeeds and that an unavailable endpoint
returns `503 reranker_unavailable`.

### Rollback

To resume local reranking, remove `reranker_model` and roll out the affected
Knowledge Flow pods with the restored configuration. To skip reranking during a
full rollback to v3.11.1, turn off the agent setting before restoring the prior
runtime and capability. Restore the prior Knowledge Flow configuration as well.
No data rollback is required.

### Limitations

Remote reranking configuration is global to Knowledge Flow on Swift. A remote
failure does not fall back to the local model; reranking requests return 503.

## Shorten tabular SQL quoting instructions

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/concise-tabular-sql-quoting.md)

The shorter instructions load with the normal agent pod deployment; existing data, APIs and query execution need no migration.

See the source note for applicability, validation and rollback.

## Add the Fred platform health Grafana dashboard

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/fred-platform-health-dashboard.md)

The Fred upgrade leaves Grafana dashboards, scrape configuration, and stored metrics unchanged.

See the source note for applicability, validation and rollback.

## Log LLM provider rejection reasons and gateway correlation IDs

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/llm-provider-error-diagnostics.md)

The new fields are additive to operational logs and require no migration or client change.

See the source note for applicability, validation and rollback.

## Preserve tool-call IDs in Chat Completions streams

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/normalize-streamed-tool-call-ids.md)

### Applicability

Fred model profiles using OpenAI-compatible or Azure Chat Completions streaming.

### Prerequisites

Use the normal deployment procedure.

### Configuration

Normalization is enabled by default. For an individual model profile, set
`normalize_streamed_tool_call_ids: false` under its model `settings` to opt out.

```yaml
model:
  provider: openai
  name: mistral-medium-latest
  settings:
    normalize_streamed_tool_call_ids: false
```

### Upgrade

Deploy Fred normally. Apply the optional model setting only if the profile
should receive the original streaming deltas.

### Validation

Run a streaming turn that calls a tool. Check that the tool receives complete
arguments and that the model continues after its result.

### Rollback

Disable the normalization on the affected model profile or use the normal
deployment rollback. There is no data migration.

### Limitations

The correction applies to incoming Chat Completions streams. Previously saved
conversation history is outside its scope.

## Prepare Fred v3.12.0 and review dependency updates

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/release-preparation-v3.12.0.md)

The OpenTelemetry, Soup Sieve and dnspython lockfile updates ship with the rebuilt images. They introduce no extra configuration or data migration. Follow the other notes for feature activation.

See the source note for applicability, validation and rollback.

## Clarify DuckDB string literal quoting for tabular queries

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/tabular-sql-literal-quotes.md)

Existing data, APIs and query execution are unchanged; the updated instructions load with a normal agent pod deployment.

See the source note for applicability, validation and rollback.

## Share the chat and HTTP lookback on the platform health dashboard

Impact: **none** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/fred-platform-health-shared-lookback.md)

The Fred upgrade does not manage imported Grafana dashboards or change telemetry. Operators can re-import the dashboard independently.

See the source note for applicability, validation and rollback.

## Optional API keys for Knowledge Flow model uses

Impact: **minor** - [Source](https://github.com/ThalesGroup/fred/blob/code/v3.12.0/docs/swift/ops/migrations/knowledge-flow-model-api-keys.md)

### Applicability

Knowledge Flow deployments using OpenAI-compatible chat, vision, or embedding models, the remote Mistral OCR extractor, or the remote reranker. Existing v3.11.1 deployments using only `OPENAI_API_KEY` continue to work after a normal upgrade.

### Prerequisites

For optional activation, obtain the credentials for each model endpoint. No database or document migration is needed.

### Configuration

Set any of `KNOWLEDGE_FLOW_CHAT_API_KEY`, `KNOWLEDGE_FLOW_VISION_API_KEY`, `KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY`, `KNOWLEDGE_FLOW_OCR_API_KEY`, or `KNOWLEDGE_FLOW_RERANKER_API_KEY` in the Knowledge Flow environment or `applications.knowledge-flow-backend.dotenv` Helm values. A nonblank dedicated key takes precedence for its use. An unset or blank dedicated key falls back to `OPENAI_API_KEY`. If a deployment tested the unreleased `reranker_model.settings.api_key_env` field, remove that field and supply the reranker credential through `KNOWLEDGE_FLOW_RERANKER_API_KEY` or `OPENAI_API_KEY` before applying v3.12.0. Keep credentials out of model YAML.

### Upgrade

To activate separate keys, update the Knowledge Flow environment or Helm Secret values, then restart the Knowledge Flow API and affected workers so they load the new environment. When enabling reranking at the same time, follow the preceding rollout instructions before turning it on for agents.

### Validation

Exercise the configured chat, vision, embedding, and remote reranking paths with their intended endpoints. When using the remote OCR extractor directly, exercise its configured endpoint as well. Confirm requests succeed with the dedicated credentials, then verify that removing a dedicated variable restores the `OPENAI_API_KEY` fallback after restart. Never log or print credential values.

### Rollback

To return to one key on this version, clear the dedicated variables, then restart the affected API and workers with `OPENAI_API_KEY` available. When rolling back to v3.11.1, restore the prior Knowledge Flow configuration and keep the shared key available. If rolling back to an unreleased build that required `settings.api_key_env`, restore the matching field and named environment variable or disable `reranker_model`. No data rollback is required.

### Limitations

Environment changes require a pod restart. The remote OCR extractor is not currently connected to the standard PDF ingestion pipeline, which uses local OCR; setting its key alone does not switch ingestion to remote OCR.
