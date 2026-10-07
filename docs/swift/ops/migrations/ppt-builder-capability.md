---
schema: 1
title: "Add the ppt_builder capability with background template analysis and agent readiness"
impact: minor
configuration: production
configuration_reason: "The bundled model catalogue in deploy/charts/fred/values.yaml flags multimodal chat profiles with the new optional supports_vision key; ppt_builder only labels template slides with a profile that declares it."
---
## Applicability

Fred deployments upgrading fred-agents, the control plane and the frontend. The
`ppt_builder` capability ships in the existing `fred-capability-ppt-filler`
package, so every fred-agents pod that installs that package registers it.

## Prerequisites

- The fred-agents migration hook (`python -m fred_runtime migrate`) must run, as
  for any release: it now also creates `cap_ppt_builder_analysis` under its own
  version table `cap_ppt_builder_alembic_version`.
- LibreOffice in the fred-agents image (already required by `ppt_filler`
  previews) renders template thumbnails and the images sent for labelling.

## Configuration

- `supports_vision` (optional, default `false`) on a model catalogue profile
  declares that it accepts images. The chart values flag the bundled OpenAI,
  Azure and Mistral Medium profiles. Operators with a private catalogue overlay
  add `supports_vision: true` to their multimodal profiles; without it, template
  slides are labelled by rules only and the agent form says so.
- No new secret, endpoint or permission: labelling goes through the agent's
  own routed chat model, within the team's usable models.

## Upgrade

1. Deploy normally; the migration hook applies two schema changes before the
   pods roll: the control-plane column `agent_instance.suspension_detail`
   (nullable text) and the fred-agents table `cap_ppt_builder_analysis`.
2. Roll fred-agents before the control plane where possible. The control plane
   now asks the agent pod for capability readiness (`POST
   /capabilities/readiness`) after a save and when listing agents; an older pod
   gives no answer and nothing changes.
3. Cost: each template upload (or vision setting change) makes one vision call
   per example slide, at most four at a time, once per template hash. A
   20-slide template is about 20 calls.

## Validation

- `cap_ppt_builder_analysis` and `cap_ppt_builder_alembic_version` exist in the
  fred-agents database; `agent_instance.suspension_detail` exists in the control
  plane database.
- Create an agent with the "Presentation builder" pack and upload a `.pptx`:
  the save returns at once, the form shows "analysis in progress", the agent is
  unavailable in chat until the analysis succeeds, then a request such as
  "prepare a 6-slide deck on our Q3 results" returns a preview and a download.

## Rollback

1. Downgrade the control-plane schema first, while the new code still runs:
   `alembic downgrade aac66348e27b` in the control-plane backend. The
   downgrade lifts every `capability_pending` suspension and drops
   `agent_instance.suspension_detail`. An older control plane does not know
   `capability_pending` and fails listing a team's agents if one row still
   carries it.
2. Then roll back the code and chart normally. The fred-agents table
   `cap_ppt_builder_analysis` is unread by older versions; leave it in place.

Agents configured with `ppt_builder` stop working on an older release, which
does not know the capability; their stored configs are kept.

## Limitations

- An analysis interrupted by a pod restart is resumed on the next save, chat
  turn or readiness check, from any replica, up to three attempts; a resumed
  analysis on a replica that did not take the save labels by rules.
- Until the control plane re-checks readiness (agent listing, form poll or the
  reconciliation sweep), a freshly analysed agent may stay unavailable for a
  short while.
