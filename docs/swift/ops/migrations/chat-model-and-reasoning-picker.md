---
schema: 1
title: "Members pick the chat model per conversation; teams curate their models and reasoning defaults"
impact: minor
after: [user-profile-picture, 2965-platform-access-planning]
configuration: none
configuration_reason: "No configuration key, default, chart value or models_catalog.yaml entry changes; team model settings live in the existing team_routing_policy table and agent recommendations in agent_instance.tuning_json."
---
## Applicability

All Fred deployments upgrading the control-plane backend, the agent pods
(`fred-agents` and any custom pod built on `fred-runtime` / `fred-sdk`) and the
frontend. Also deployments running `fred-agent-evaluator`.

## Prerequisites

- Back up the control-plane database: the upgrade migrates data out of a
  column it then drops.
- Custom agent pods: `AgentDefinition.reasoning_enabled` and
  `reasoning_default_on` are now deprecated no-ops. A definition that sets them
  still loads, logs one deprecation warning per definition class, and its
  value has no effect: reasoning follows the model. Remove them before a later
  SDK minor drops them. `AgentTuning` no longer has them.
- `fred-agent-evaluator`: deploy a version that forwards
  `ExecutionPreparation.chat_profile_id` as `runtime_context.chat_profile_id`.
  An older evaluator still reads the removed `agent_profile_overrides` and
  silently loses its per-run model override. Tracked in #3032.

## Configuration

No configuration changes are required.

## Upgrade

1. Deploy control-plane, the agent pods and the frontend together. Run the
   normal control-plane `alembic upgrade head`. Revision `e9026d8e4db6` (after
   `f9a2c7d81e40`):
   - adds `disabled_model_ids_json` and `reasoning_default_off_model_ids_json`
     to `team_routing_policy`, both empty;
   - copies each team's per-template model override into
     `recommended_chat_profile_id` of that team's agents created from that
     template, where none is set;
   - drops `agent_profile_overrides_json`.
   The migration logs how many agents it updated. Former per-agent reasoning
   keys in stored agent settings are ignored and dropped on the next save.
2. Review reasoning, since the composer's reasoning row is now driven by the
   model, not the agent:
   - platform admins: check which models have reasoning enabled
     (admin **Features** page, **Models** filter). It is now offered with
     every agent, and a newly allowed model arrives with reasoning **on** by
     default for teams;
   - team admins: in team settings → **Models**, switch "Reasoning on by
     default" off for models where it should start off.
3. Tell team editors that only team admins (and a personal space's owner) can
   now change the team's models (default, enabled models, reasoning
   defaults). Editors keep a read-only view and set each agent's
   **Recommended model** in the agent form.

When the platform revokes a model that a team had set as its default, the
team's default is cleared and the pod default takes over, so conversations keep
working. The team admin can pick a new default in team settings → **Models**.

## Validation

- `alembic_version_control_plane` holds `e9026d8e4db6` (or a later head).
- An agent whose template had a team override shows that model as its
  **Recommended model** in the agent form.
- While one of the team's agent pods is unreachable, disabling a model in
  team settings → **Models** is refused (503) and can be retried once the pod
  is back.
- In a chat, the model button lists the team's enabled models; picking one
  answers with it (pod log `[V2][MODEL_ROUTING] … source=user_choice`), and a
  new conversation starts again on the recommended model.
- A team editor who is not team admin gets a read-only Models section; the
  `PATCH /teams/{team_id}/routing-policy` call returns 403 for them.

## Rollback

Downgrading `e9026d8e4db6` re-adds `agent_profile_overrides_json` **empty**
and drops the two new columns. It is lossy: per-template overrides are not
restored (re-enter them in the previous release's routing settings, or restore
the backup), and team-disabled models and reasoning defaults are lost. The
copied recommendations stay in `tuning_json` and the previous release ignores
them. Restore the previous `fred-agent-evaluator` with the previous release.

## Limitations

- The model choice lasts for one conversation in one browser tab; it is never
  stored server-side.
- After a team disables a model or the platform revokes it, members on it move
  to the agent's recommended model on their next page refresh; until then the pod
  ignores the stale choice and answers with the next model in line.
- The choice applies to the agent the user talks to; agents it calls through
  the agent registry keep their own model.
- Old export bundles carrying per-template overrides are mapped onto the
  imported agents the same way; the import report counts them.
