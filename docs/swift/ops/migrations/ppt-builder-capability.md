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
- No new secret, endpoint or permission: labelling goes through the agent's
  own routed chat model, within the team's usable models.

## Upgrade

1. Deploy normally; the migration hook applies two schema changes before the
   pods roll: the control-plane column `agent_instance.suspension_detail`
   (nullable text) and the fred-agents tables `cap_ppt_builder_analysis` and
   `cap_ppt_builder_deck_plan` (the last deck plan per conversation, a few KB
   per row, written once per build call).
2. Roll fred-agents before the control plane where possible. The control plane
   now asks the agent pod for capability readiness (`POST
   /capabilities/readiness`) after a save and when listing agents; an older pod
   gives no answer and nothing changes.
3. Cost: each template upload (or vision setting change) makes one vision call
   per example slide, at most four at a time, once per template hash. A
   20-slide template is about 20 calls.
4. Native charts raise the template analysis version. Templates already
   analysed keep working and are read again in the background (the agent form
   says when a save is needed), at the cost of an upload; until then their
   chart slides stay set aside. The built-in template ships already analysed.
   Stacked bar, radar, scatter and bubble charts raise it once more (example
   charts of those types are recognised and reused); the same background
   refresh applies, with no action. Example slides holding two to four charts
   are now used and filled: the version is raised again and templates are
   re-read in the background, with no action.
5. Storytelling checks (takeaway per slide, one measure per chart, sourced
   figures) are always on and need no action. The agent setting "Validate the
   plan before building" is off by default; a proposed plan is stored in the
   existing `cap_ppt_builder_deck_plan` row, with no schema change.
6. Emphasis fields (a chart's highlighted category, a table's total row or
   highlighted row and column, a key figure's trend arrow) need no action and
   leave a deck without them unchanged, except one fix: a template table whose
   own properties flag a total row no longer styles the last data row as a
   total unless the plan says it is one. Template zones named for the key
   message raise the analysis version once more (re-read in the background,
   no action); they show a slide's takeaway only when the user asks for the
   key messages on the slides, otherwise they are filled as before.

## Validation

- `cap_ppt_builder_analysis`, `cap_ppt_builder_deck_plan` and
  `cap_ppt_builder_alembic_version` exist in the fred-agents database; `agent_instance.suspension_detail` exists in the control
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
2. Then roll back the code and chart normally. The fred-agents tables
   `cap_ppt_builder_analysis` and `cap_ppt_builder_deck_plan` are unread by
   older versions; leave them in place.

Agents configured with `ppt_builder` stop working on an older release, which
does not know the capability; their stored configs are kept.

## Limitations

- `cap_ppt_builder_deck_plan` rows are not deleted with their conversation;
  each is a few KB. They can be deleted at any time: a later edit of that
  conversation's deck then asks the model for the whole deck again.

- An analysis interrupted by a pod restart is resumed on the next save, chat
  turn or readiness check, from any replica, up to three attempts; a resumed
  analysis on a replica that did not take the save labels by rules.
- Until the control plane re-checks readiness (agent listing, form poll or the
  reconciliation sweep), a freshly analysed agent may stay unavailable for a
  short while.
