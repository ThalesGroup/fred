---
schema: 1
title: "Delegate Platform Access administration"
impact: minor
configuration: none
configuration_reason: "No new chart setting or default is introduced. Deployments that pin authorization_model_id must update that existing value to the new model ID."
---

## Applicability

Existing Fred deployments upgrading to this release. The default
`sync_schema_on_init: true` publishes the updated model at control-plane startup.
Deployments with `sync_schema_on_init: false` and a pinned
`authorization_model_id` must update their model and pinned ID manually.

## Prerequisites

For pinned-model deployments, publish this release's
`libs/fred-core/fred_core/security/rebac/schema.fga.json` to OpenFGA and capture
the new model ID before deploying the new control plane and frontend.

## Configuration

No chart key or default changes. For pinned-model deployments, set the existing
`authorization_model_id` to the new model ID before deploying the new services.

## Upgrade

For pinned-model deployments, publish and pin the new model before the coordinated
rollout. With the default automatic synchronization, the new control plane writes
the model at startup; start it before relying on the delegated permissions in the
frontend. Complete the other release prerequisites before rolling out services.
Existing role tuples and Free links remain valid. No delegated role is assigned automatically.
A platform administrator may grant `platform_access_manager` after deployment.

## Validation

Grant `platform_access_manager` to a test user and confirm they can manage
filtering, the whitelist and a Free link while being denied unrelated admin
routes. Grant `team_manager` to another test user and confirm they can create
and list teams while registry editing and Free links are denied.

## Rollback

Roll back the application before reverting the OpenFGA model. Pinned-model
deployments can then restore the previous `authorization_model_id`. The added
model relations are inert to the older application, and no data migration is needed.

## Limitations

The new role does not grant team content or member administration.
