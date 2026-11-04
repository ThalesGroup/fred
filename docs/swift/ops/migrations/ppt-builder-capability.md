---
schema: 1
after: [platform-skills-evolution]
title: "Add the ppt_builder capability with background template analysis, agent readiness and a platform default template"
impact: minor
configuration: production
configuration_reason: "The bundled model catalogue in deploy/charts/fred/values.yaml flags multimodal chat profiles with the new optional supports_vision key; ppt_builder only labels template slides with a profile that declares it."
---
## Applicability

Fred deployments upgrading fred-agents, the control plane and the frontend. The
`ppt_builder` capability ships in the existing `fred-capability-ppt-filler`
package, so every agent-pod that installs that package registers it.

## Prerequisites

- fred-core, fred-sdk and fred-runtime 4.6.0. The ppt-filler package needs
  fred-core and fred-sdk 4.6.0 or later, the control plane fred-sdk 4.6.0, and
  fred-agents fred-runtime 4.6.0 (the readiness hook, the capability model port
  and the route team authorizer ship there).
- The fred-agents migration hook (`python -m fred_runtime migrate`) must run, as
  for any release: it now also creates `cap_ppt_builder_analysis` and
  `cap_ppt_builder_deck_plan` under their own version table
  `cap_ppt_builder_alembic_version`.
- Every agent-pod image that installs this package needs headless LibreOffice
  Impress for previews and template analysis, plus suitable fonts and
  Fontconfig aliases for its templates. The package README lists the Ubuntu
  packages used by `fred-agents`; these system dependencies do not come with
  the Python package.

## Configuration

- `supports_vision` (optional, default `false`) on a model catalogue profile
  declares that it accepts images. The chart values flag the bundled OpenAI,
  Azure and Mistral Medium profiles. Operators with a private catalogue overlay
  add `supports_vision: true` to their multimodal profiles; without it, template
  slides are labelled by rules only and the agent form says so.
- While any older runtime can read the catalogue, omit `supports_vision`
  entirely, including the keys supplied by the new chart and private overlays.
  Older pods reject unknown model profile keys and fail to boot. After all
  runtime replicas use the new image, enable the intended flags and restart
  those replicas. Without these flags, template analysis uses rules only.
- No new secret or permission: labelling goes through the agent's own routed
  chat model, within the team's usable models. The platform default template
  is labelled through the pod's default chat model, or the model a capability
  manager picks, with no team restriction.
- Optional activation: a platform admin or feature manager can replace the
  default template of agents without their own in Admin > Features, on the
  "Presentation builder" row. Nothing changes until someone does.

## Upgrade

1. Back up the databases and apply the complete release migration chains as
   described in the discovery note. The control-plane head is
   `b8e1f4a2c6d9`; its parent is `d7b24ef08361`. The runtime head remains
   `f6a7b8c9d0e1`, and the independent `capability:ppt_builder` tree advances
   from base to `r9d3f4a5b6c7`. Its migration creates the analysis and deck-plan
   tables under `cap_ppt_builder_alembic_version`.
2. Deploy the control plane before all runtime replicas, then the frontend,
   following the release's skill-policy rollout. Avoid agent writes while old
   and new control-plane replicas coexist: new replicas can persist
   `capability_pending`, which old replicas cannot read. The new control plane
   treats an older runtime's readiness endpoint returning 404 as ready; other
   readiness failures can leave an agent suspended until a successful check.
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

1. Follow the release's skill-policy rollback precautions. Keep the new control
   plane available while rolling back every runtime replica: new runtimes need
   its skill-policy endpoint for direct turns. Remove `supports_vision` from
   retained catalogue overlays before starting any old runtime.
2. Once all new runtimes have stopped, drain and stop every new control-plane
   replica before removing its mapped column. Using the new image and the
   deployment's database configuration, execute
   `alembic downgrade d7b24ef08361` for the control-plane tree. This reverts
   only the PPT revision, clears `capability_pending` suspensions and drops
   `agent_instance.suspension_detail`, preserving global skill policies.
   Verify that no agent retains `capability_pending`, then start the prior
   control-plane version and roll back the frontend. Do not run new replicas
   against the downgraded schema.
3. Keep the additive PPT analysis and deck-plan tables; older versions do not
   read them. If removal is required, stop all replicas that can analyse
   templates or save decks, then use the new image's migration tooling and the
   deployment's database configuration to downgrade the independent
   `capability:ppt_builder` tree to base. This permanently deletes stored
   templates, analyses and plans.

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
