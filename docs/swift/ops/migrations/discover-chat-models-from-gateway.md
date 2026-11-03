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

Set `applications.fred-agents.models_catalog.discovery` in the Fred chart values to a list of sources. Each entry needs a stable `source_id` and the gateway's `base_url`, and may set `include_model_ids`. A one-endpoint deployment still uses a one-item list. Provide `OPENAI_API_KEY` in the agent pod environment through the deployment's secret mechanism. All discovery URLs on that pod share this key. A sole manual chat profile becomes the pod default automatically; with multiple manual profiles, set `default_profile_by_capability.chat` explicitly. In Features > Models > Model defaults > Agent pods, the administrator can replace that YAML default with a chat profile advertised by the pod whose model is enabled platform-wide. A discovery-only pod can leave the YAML default unset and require an administrator to select one. Each pod can also select an enabled manual chat profile as its fallback when a selected discovered profile disappears. The Platform tab retains the existing provider/name/settings form for a global override that forces one model across managed turns. Existing catalogs without `discovery` require no change.

## Upgrade

Apply the control-plane Alembic migrations, then deploy the runtime, control plane and frontend changes. The follow-up revision repairs a development database already stamped at the earlier PR revision before the pod-default table was added; fresh installations create that table in the original revision. The inferred sole-manual-model default needs no separate migration. Configure discovery and restart the agent pods once to load the YAML. Later, a feature manager can refresh the URL currently active in a pod, while only a platform administrator can override its URL in Features > Models; both take effect without restarting pods. After a pod restart with a saved override, a platform administrator can refresh it, or a managed turn can restore it before a feature manager refreshes. Confirm that all model-capable pods use consistent source ids and inventories before selecting a discovered profile as a team default. Enable intended discovered models for teams in the admin Models view. An administrator can enter a display name there after discovery; it is saved in the control-plane database and appears in chat without a pod restart. A deployment with no effective pod chat default and no global override opens a required-choice dialog whenever a platform administrator selects Models; its action opens the Agent pods tab. The Platform tab keeps the existing global override form. New models are not granted automatically. Without the optional configuration, deploy normally.

## Validation

Check that each pod's `/agents/models-catalog` lists the selected ids and its YAML default, then use Refresh in Features > Models > Discovery to confirm the latest inventory without a restart. Open Model defaults > Agent pods and verify that each dropdown displays its YAML default when activated; an inactive current YAML or saved value appears as a separate status and cannot be saved again. Enable a model platform-wide before selecting it as a pod default or manual fallback. Save a discovered chat profile for one pod and confirm a managed turn without an explicit model uses it; other pods keep their own defaults. Reset the selection and confirm the YAML default returns. Select a manual fallback for that pod. The admin view shows optional upstream metadata and warns if an agent catalog cannot be checked, without marking models removed. After a successful refresh confirms a model is absent from `/models`, the model appears greyed out and cannot be activated in the discovery table or selected as a pod default. The compact absence button opens a scrolling list; its red removal action requires confirmation and hides that absence without changing existing grants or routing evidence. Absence from `/models` does not prove that chat requests fail. A managed turn selecting a confirmed-absent profile uses the pod's manual fallback, or its manual YAML default when no fallback override exists. Check that a granted available model can be selected and used by a team. Save a display name in the admin view and confirm that it appears in chat while inference still uses the gateway id; clear it to restore the gateway label or identifier. A missing gateway or invalid inventory logs a startup warning; static profiles remain available and a saved override can be restored on a managed turn.

## Rollback

Clear any admin URL, pod-default and pod-fallback overrides, remove the discovery block, restore the previous static chat default and profiles if changed, and restart the pods with the prior image or catalog. Keep the additive discovery, display-name and pod-default tables when rolling back application code; saved data remains dormant while its capability ids are absent. Grants to discovery-only capability ids also remain dormant until those ids are advertised again.

## Limitations

The standard OpenAI model-list response does not define chat capability or token limits; the admin view displays only metadata supplied by the endpoint. A pod must restart after its YAML changes, while admin refresh and URL overrides apply immediately. Upstream id or source-id changes create new grant identities. Separate pods are needed for endpoints that require different keys until per-source credentials are supported.
