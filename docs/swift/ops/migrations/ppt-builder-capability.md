---
schema: 1
title: "Add the ppt_builder capability with background template analysis, agent readiness and a platform default template"
impact: minor
configuration: production
configuration_reason: "The bundled model catalogue in deploy/charts/fred/values.yaml flags multimodal chat profiles with the new optional supports_vision key; ppt_builder only labels template slides with a profile that declares it."
---
## Applicability

Fred deployments upgrading fred-agents, the control plane and the frontend. The
`ppt_builder` capability ships in the existing `fred-capability-ppt-filler`
package, so every fred-agents pod that installs that package registers it.

## Prerequisites

- fred-core, fred-sdk and fred-runtime 4.6.0. The ppt-filler package needs
  fred-core and fred-sdk 4.6.0 or later, the control plane fred-sdk 4.6.0, and
  fred-agents fred-runtime 4.6.0 (the readiness hook, the capability model port
  and the route team authorizer ship there).
- The fred-agents migration hook (`python -m fred_runtime migrate`) must run, as
  for any release: it now also creates `cap_ppt_builder_analysis` and
  `cap_ppt_builder_deck_plan` under their own version table
  `cap_ppt_builder_alembic_version`.
- LibreOffice in the fred-agents image (already required by `ppt_filler`
  previews) renders template thumbnails and the images sent for labelling.

## Configuration

- `supports_vision` (optional, default `false`) on a model catalogue profile
  declares that it accepts images. The chart values flag the bundled OpenAI,
  Azure and Mistral Medium profiles. Operators with a private catalogue overlay
  add `supports_vision: true` to their multimodal profiles; without it, template
  slides are labelled by rules only and the agent form says so.
- Add `supports_vision` to an overlay only once the new fred-agents image is
  rolled out: older pods reject unknown model profile keys and fail to boot.
- No new secret or permission: labelling goes through the agent's own routed
  chat model, within the team's usable models. The platform default template
  is labelled through the pod's default chat model, or the model a capability
  manager picks, with no team restriction.
- Optional activation: a platform admin or feature manager can replace the
  default template of agents without their own in Admin > Features, on the
  "Presentation builder" row. Nothing changes until someone does.

## Upgrade

1. Deploy normally; the migration hook applies the schema changes before the
   pods roll: the control-plane column `agent_instance.suspension_detail`
   (nullable text) and the fred-agents tables `cap_ppt_builder_analysis` and
   `cap_ppt_builder_deck_plan` (the last deck plan per conversation, a few KB
   per row).
2. Roll fred-agents before the control plane where possible. The control plane
   now asks the agent pod for capability readiness (`POST
   /capabilities/readiness`) after a save and when listing agents; an older pod
   gives no answer and nothing changes.
3. Cost: each template upload (or vision setting change) makes one vision call
   per example slide, at most four at a time, once per template hash. A
   20-slide template is about 20 calls. The built-in template ships analysed.
4. A platform default template takes up to two `cap_ppt_builder_analysis` rows
   (in use, and a replacement being analysed; bytes in Postgres, 50 MB at most
   each). A replacement applies once its analysis succeeds. Each fred-agents
   replica reads it at most every 30 s, so replicas may differ for that long.

## Validation

- `cap_ppt_builder_analysis`, `cap_ppt_builder_deck_plan` and
  `cap_ppt_builder_alembic_version` exist in the fred-agents database;
  `agent_instance.suspension_detail` exists in the control-plane database.
- Create an agent with the "Presentation builder" pack and upload a `.pptx`:
  the save returns at once, the form shows "analysis in progress", the agent is
  unavailable in chat until the analysis succeeds, then a request such as
  "prepare a 6-slide deck on our Q3 results" returns a preview and a download.
- Optional: as a platform admin, upload a `.pptx` in the "Presentation builder"
  settings of Admin > Features; once analysed, an agent without its own
  template builds on it, and "Reset" brings back the Fred template.

## Rollback

1. Downgrade the control-plane schema first, while the new code still runs:
   `alembic downgrade b5d2e8f7c031` in the control-plane backend. The
   downgrade lifts every `capability_pending` suspension and drops
   `agent_instance.suspension_detail`. An older control plane does not know
   `capability_pending` and fails listing a team's agents if one row still
   carries it.
2. Then roll back the code and chart normally. The fred-agents tables
   `cap_ppt_builder_analysis` and `cap_ppt_builder_deck_plan` are unread by
   older versions; leave them in place. To drop them anyway (stored templates,
   analyses and deck plans are lost), run from `apps/fred-agents`, before the
   rollback, `make db-downgrade MIGRATION_TREE=capability:ppt_builder
   ALEMBIC_CONFIG_FILE=/path/to/configuration_prod.yaml` three times: each
   call reverts one of the tree's three revisions.

Agents configured with `ppt_builder` stop working on an older release, which
does not know the capability; their stored configs are kept.

## Limitations

- `cap_ppt_builder_deck_plan` rows are not deleted with their conversation;
  each is a few KB. They can be deleted at any time: a later edit of that
  conversation's deck then asks the model for the whole deck again.
- An analysis interrupted by a pod restart is resumed on the next save, chat
  turn or readiness check, from any replica, up to three attempts; a resumed
  analysis on a replica that did not take the save labels by rules.
- Until the control plane re-checks readiness (agent listing or form poll), a
  freshly analysed agent may stay unavailable for a short while.
