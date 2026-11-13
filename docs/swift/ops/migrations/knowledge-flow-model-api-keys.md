---
schema: 1
title: "Optional API keys for Knowledge Flow model uses"
impact: minor
configuration: production
configuration_reason: "The Fred chart adds four optional Knowledge Flow dotenv keys; using separate credentials requires setting them in the deployment and restarting the affected API and workers."
---
## Applicability

Knowledge Flow deployments using OpenAI-compatible chat, vision, or embedding models, or the remote Mistral OCR extractor. Existing deployments using only `OPENAI_API_KEY` continue to work after a normal upgrade.

## Prerequisites

For optional activation, obtain the credentials for each model endpoint. No database or document migration is needed.

## Configuration

Set any of `KNOWLEDGE_FLOW_CHAT_API_KEY`, `KNOWLEDGE_FLOW_VISION_API_KEY`, `KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY`, or `KNOWLEDGE_FLOW_OCR_API_KEY` in the Knowledge Flow environment or `applications.knowledge-flow-backend.dotenv` Helm values. A nonblank dedicated key takes precedence for its use. An unset or blank dedicated key falls back to `OPENAI_API_KEY`; setting only `OPENAI_API_KEY` remains valid for all four uses. Do not place credentials in model YAML.

## Upgrade

Deploy normally if retaining the single key. To activate separate keys, update the Knowledge Flow environment or Helm Secret values, then restart the Knowledge Flow API and affected workers so they load the new environment. No special rollout order is required.

## Validation

Exercise the configured chat, vision, and embedding paths with their intended endpoints. When using the remote OCR extractor directly, exercise its configured endpoint as well. Confirm requests succeed with the dedicated credentials, then verify that removing a dedicated variable restores the `OPENAI_API_KEY` fallback after restart. Never log or print credential values.

## Rollback

Remove the dedicated variables and restart the affected API and workers to restore the single-key configuration, or roll back the deployment. Keep `OPENAI_API_KEY` available for any role that no longer has a dedicated key. No data rollback is required.

## Limitations

Environment changes require a pod restart. The remote OCR extractor is not currently connected to the standard PDF ingestion pipeline, which uses local OCR; setting its key alone does not switch ingestion to remote OCR.
