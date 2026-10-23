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

Set `applications.fred-agents.models_catalog.discovery` in the Fred chart values to a nonempty list of sources. Each entry needs a stable `source_id` and the gateway's `base_url`, and may set `include_model_ids`. A one-endpoint deployment still uses a one-item list. Provide `OPENAI_API_KEY` in the agent pod environment through the deployment's secret mechanism. All discovery URLs on that pod share this key. If a pod default is configured, keep `default_profile_by_capability.chat` pointed at a manually declared profile. A discovery-only deployment may leave it unset, then an administrator must select a platform binding before an otherwise unselected chat turn can run. The separate platform fallback is configured in the admin UI. Existing catalogs without `discovery` require no change.

## Upgrade

Apply the control-plane Alembic migration, then deploy the runtime, control plane and frontend changes. Configure discovery and restart the agent pods once to load the YAML. Later, a feature manager can refresh the URL currently active in a pod, while only a platform administrator can override its URL in Features > Models; both take effect without restarting pods. After a pod restart with a saved override, a platform administrator can refresh it, or a managed turn can restore it before a feature manager refreshes. Confirm that all model-capable pods use consistent source ids and inventories before selecting a discovered profile as a team default. Enable intended discovered models for teams in the admin Models view. An administrator can enter a display name there after discovery; it is saved in the control-plane database and appears in chat without a pod restart. A deployment with no pod chat default and no platform binding opens a required-choice dialog whenever a platform administrator selects Models, even if manual models are listed; its only action opens the platform binding editor. The editor groups available models under Catalog and Discovery, and reserves provider settings for its advanced form. New models are not granted automatically. Without the optional configuration, deploy normally.

## Validation

Check that each pod's `/agents/models-catalog` lists the selected ids, then use Refresh in Features > Models > Discovered models to confirm the latest inventory without a restart. The admin view shows optional upstream metadata and warns if an agent catalog cannot be checked, without marking models removed. Check that a granted model can be selected and used by a team. Save a display name in the admin view and confirm that it appears in chat while inference still uses the gateway id; clear it to restore the gateway label or identifier. A missing gateway or invalid inventory logs a startup warning; static profiles remain available and a saved override can be restored on a managed turn.

## Rollback

Clear any admin URL override, remove the discovery block, restore the previous static chat default and profiles if changed, and restart the pods with the prior image or catalog. Keep the additive discovery and display-name tables when rolling back application code; saved data remains dormant while its capability ids are absent. Grants to discovery-only capability ids also remain dormant until those ids are advertised again.

## Limitations

The standard OpenAI model-list response does not define chat capability or token limits; the admin view displays only metadata supplied by the endpoint. A pod must restart after its YAML changes, while admin refresh and URL overrides apply immediately. Upstream id or source-id changes create new grant identities. Separate pods are needed for endpoints that require different keys until per-source credentials are supported.
