---
schema: 1
title: "Discover chat models from an OpenAI-compatible gateway"
impact: minor
configuration: production
configuration_reason: "The Fred chart's models_catalog gains an optional discovery source; enabling it requires a gateway URL, model selection and an OPENAI_API_KEY available to the agent pod."
---
## Applicability

Agent pods whose operators want to list chat models from an OpenAI-compatible gateway. Existing static catalogs continue to work without a configuration change.

## Prerequisites

The gateway must serve an authenticated `GET /models` under its inference base URL and return a JSON `data` array. Selected model ids must be distinct and valid. The source must contain chat-capable models only, or the operator must select chat ids with `include_model_ids`.

## Configuration

Set `applications.fred-agents.models_catalog.discovery` in the Fred chart values with a stable `source_id`, the gateway's `base_url`, and optionally `default_model_id` and `include_model_ids`. Provide `OPENAI_API_KEY` in the agent pod environment through the deployment's secret mechanism. When using a discovered default, remove the static `default_profile_by_capability.chat` value. Existing static profiles can remain during a gradual move.

## Upgrade

Deploy the runtime, control plane and frontend changes, then configure discovery and restart the agent pods. Confirm that all model-capable pods use consistent source ids and inventories before selecting a discovered profile as a team default. Enable intended discovered models for teams in the admin Models view. New models are not granted automatically. Without the optional configuration, deploy normally.

## Validation

Check that each restarted pod's `/agents/models-catalog` lists the selected ids, the admin Models view shows them with any supplied metadata, and a granted model can be selected and used by a team. A missing gateway or invalid inventory prevents an opted-in pod from starting.

## Rollback

Remove the discovery block, restore the previous static chat default and profiles if changed, and restart the pods with the prior image or catalog. No database migration is required. Grants to discovery-only capability ids remain dormant until those ids are advertised again.

## Limitations

The OpenAI model-list response does not define chat capability or token limits. Discovery refreshes only on pod restart; upstream id or source-id changes create new grant identities.
