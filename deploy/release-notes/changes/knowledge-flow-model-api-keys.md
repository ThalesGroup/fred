---
schema: 1
title: "Configure separate Knowledge Flow model credentials on Weaver"
impact: minor
configuration: production
configuration_reason: "The API chart adds the optional KNOWLEDGE_FLOW_RERANKER_API_KEY; other document models retain their existing per-connection credential bindings."
---
## Applicability

Weaver Knowledge Flow API and worker deployments using admitted models, and APIs
that opt into the deployment-level remote reranker.

## Prerequisites

Configure each document model's connection in the Control Plane and attest it
with the matching workload `inference_credentials` entry. Each entry references
its own environment variable; keys are never copied into model metadata.

## Configuration

Existing chat, vision and embedding paths already accept distinct credentials
through `inference_credentials[].api_key_env`. Swift's role-specific chat,
vision, embeddings and OCR configuration is not introduced into Weaver.
For the optional remote reranker, supply `KNOWLEDGE_FLOW_RERANKER_API_KEY` in
`applications.knowledge-flow-backend.dotenv`. A blank value falls back to
`OPENAI_API_KEY`. See [API configuration](../../../apps/knowledge-flow-backend/config/README.md#document-models-and-reranking).

## Upgrade

Weaver supports fresh installations only. This change adds no database migration.
Restart the API after changing reranker configuration or environment variables;
restart affected workloads when changing their admitted-model credentials.

## Validation

Check document ingestion and retrieval with their admitted destinations and
separate keys. With remote reranking enabled, verify a valid indexed response,
a 503 on endpoint failure, and refusal to start without either reranker key.
Do not print credential values.

## Rollback

Remove `reranker_model` to use the bundled local CrossEncoder, or disable the
agent's `rerank` option. Keep document-model credential bindings unchanged.

## Limitations

The remote OCR extractor removed from Weaver is not restored. Reranker choice
is deployment-wide; other document model choices remain organization-bound.
