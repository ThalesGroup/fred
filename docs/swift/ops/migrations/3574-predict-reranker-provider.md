---
schema: 1
title: "Configure the positional predict reranker provider"
impact: minor
configuration: production
configuration_reason: "Deployments can select a new positional predict protocol for remote reranking; the endpoint and credential header differ from the existing rerank protocol."
after: [3536-knowledge-flow-reranking]
---
## Applicability

Knowledge Flow deployments that want to use a model `:predict` endpoint for document reranking. Existing `rerank` and local CrossEncoder configurations continue to work without changes.

## Prerequisites

Use a Fred chart and Knowledge Flow image containing the `predict` provider. Confirm that the model endpoint accepts `POST /models/<name>:predict` with a `query` string and `documents` array and returns one positional numeric score per document.

## Configuration

Set `reranker_model` in both Knowledge Flow API and worker configuration:

```yaml
reranker_model:
  provider: predict
  name: example-model
  settings:
    base_url: https://models.example/v1
```

The adapter calls `POST https://models.example/v1/models/example-model:predict`, sends the selected reranker key in the `apikey` header, and maps `predictions` to the input documents by position. Supply `KNOWLEDGE_FLOW_RERANKER_API_KEY` or its `OPENAI_API_KEY` fallback through the existing environment secret. Keep keys out of model YAML. The existing `rerank` provider continues to use `POST {base_url}/rerank`, a bearer token, and indexed `results`.

## Upgrade

Deploy the compatible chart and image, set the model configuration, then restart the Knowledge Flow API and worker pods. The per-agent document access reranking switch remains off by default.

## Validation

From each environment, verify an authenticated predict request and a reranked document search with the switch enabled on a test agent. Check that the returned hits remain tied to their original documents, and that a remote failure returns `503 reranker_unavailable`. Do not log credentials or document content during validation.

## Rollback

Remove `reranker_model` from API and worker configuration and restart the affected pods to resume the local CrossEncoder. No data migration is needed.

## Limitations

The remote model is selected globally for Knowledge Flow. A remote failure does not fall back to local inference.
