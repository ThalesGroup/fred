---
schema: 1
title: "Optional API keys for Knowledge Flow model uses"
impact: minor
configuration: production
configuration_reason: "The Fred chart adds five optional Knowledge Flow dotenv keys; using separate credentials requires setting them in the deployment and restarting the affected API and workers."
---
## Applicability

Knowledge Flow deployments using OpenAI-compatible chat, vision, or embedding models, the remote Mistral OCR extractor, or the remote reranker. Existing deployments using only `OPENAI_API_KEY` continue to work after a normal upgrade.

## Prerequisites

For optional activation, obtain the credentials for each model endpoint. No database or document migration is needed.

## Configuration

Set any of `KNOWLEDGE_FLOW_CHAT_API_KEY`, `KNOWLEDGE_FLOW_VISION_API_KEY`, `KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY`, `KNOWLEDGE_FLOW_OCR_API_KEY`, or `KNOWLEDGE_FLOW_RERANKER_API_KEY` in the Knowledge Flow environment or `applications.knowledge-flow-backend.dotenv` Helm values. A nonblank dedicated key takes precedence for its use. An unset or blank dedicated key falls back to `OPENAI_API_KEY`; setting only `OPENAI_API_KEY` remains valid for all five uses. For an existing remote reranker configuration, an explicitly named `settings.api_key_env` remains first priority; if that variable is blank, the dedicated key and global fallback apply. The reranker's `api_key_env` setting is now optional. Do not place credentials in model YAML.

## Upgrade

Deploy normally if retaining the single key. To activate separate keys, update the Knowledge Flow environment or Helm Secret values, then restart the Knowledge Flow API and affected workers so they load the new environment. No special rollout order is required.

## Validation

Exercise the configured chat, vision, embedding, and remote reranking paths with their intended endpoints. When using the remote OCR extractor directly, exercise its configured endpoint as well. Confirm requests succeed with the dedicated credentials, then verify that removing a dedicated variable restores the `OPENAI_API_KEY` fallback after restart. Never log or print credential values.

## Rollback

To return to one key on this version, clear the dedicated variables and any explicit reranker `settings.api_key_env` override, then restart the affected API and workers with `OPENAI_API_KEY` available. Before rolling back the code, restore a remote reranker's required `settings.api_key_env` and the named environment variable, or disable `reranker_model`; the previous version cannot start with only `base_url`. Keep `OPENAI_API_KEY` available for the other uses. No data rollback is required.

## Limitations

Environment changes require a pod restart. The remote OCR extractor is not currently connected to the standard PDF ingestion pipeline, which uses local OCR; setting its key alone does not switch ingestion to remote OCR.
