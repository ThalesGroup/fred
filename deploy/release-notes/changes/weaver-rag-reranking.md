---
schema: 1
title: "Configure RAG reranking per organization"
impact: minor
configuration: production
configuration_reason: "Operators may approve a rerank model source and choose it per organization through the Control Plane model policy."
---

## Applicability

Weaver deployments using agent document search through Knowledge Flow.

## Prerequisites

Deploy the matching Control Plane, Knowledge Flow, agent runtime and capability versions. A remote reranker needs an approved declared model source with the `rerank` inference wire and an existing credential binding.

## Configuration

Reranking is enabled by default in the agent's advanced document access settings. It can improve relevance but adds noticeable search latency, so an agent can disable it. To use a remote model, declare its offer in the Control Plane model source, permit it for the organization and select it as that organization's reranker. Without a remote selection, Knowledge Flow uses its packaged CrossEncoder.

## Upgrade

Apply the normal Control Plane SQL migrations before starting the updated services. The new organization policy column is nullable, so existing organizations keep the local fallback. No document reindexing is required.

## Validation

Run an authorized document search with the default agent setting. Confirm that the selected remote offer is used when configured, or that local reranking works without a selection. Disable reranking for the agent and confirm that search keeps the original retrieval order.

## Rollback

Clear remote reranker selections before rolling back the Control Plane. Use the normal database backup and rollback procedure for the SQL migration; older binaries should not be run against an unsupported schema version.

## Limitations

The remote endpoint must implement the supported rerank request and response format. A selected remote reranker that is unavailable returns an error instead of silently switching to the local model.
