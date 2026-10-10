## Why

Today the model is chosen once per team, by a team editor: a member cannot pick
a model for a conversation, and an agent author cannot steer one instance
towards a better-suited model. Teams also cannot narrow the platform's offer or
set reasoning defaults per model. Meanwhile, reasoning is offered or withheld
per agent in the form, which hides it on agents whose model could reason. The
product owner decided (2026-10-09) to move each choice to the person who owns
it:
- the team curates its models;
- the agent recommends one;
- the user picks one per conversation;
- reasoning follows the model.

Tracking: #3029.

## What Changes

- **Team "Models" settings section.** It replaces the per-template rows of
  `TeamSettingsRouting`. It lists the models the platform allows the team
  (`can_use`). Each row has:
  - a "Default" badge, or a "Set as default" button, as on the admin UI themes page;
  - an "enabled for the team" switch, disabled on the default model;
  - a "reasoning on by default" switch, shown only when the platform admin
    enabled reasoning for that model.

  Only team admins can edit it: this narrows today's team_editor write gate.
  Disabling a model opens a confirmation dialog that lists its impact. The write
  is atomic and clears the affected agents' recommendations. Team-disabled
  models and reasoning-off models are stored as exceptions, so a newly allowed
  model arrives enabled, with reasoning on by default.
- **BREAKING (team routing API): team per-template overrides are removed.**
  `agent_profile_overrides` leaves the routing policy, its schemas, prepare-execution,
  `RuntimeContext` and the resolver. An Alembic data migration copies each
  override into `recommended_chat_profile_id` of the team's instances created
  from that template, where none is set. Old export bundles are mapped the same way.
- **Agent instance "Recommended model".** A new `recommended_chat_profile_id`
  field is stored in the instance tuning and edited in the form's General
  section. The form's "Default model (<name>)" option (null) names the current team default
  and follows later changes to it.
- **Composer model picker.** The existing model chip becomes one menu. It shows
  the selectable models (`can_use` ∩ team-enabled ∩ served by the agent's pod),
  plus the reasoning row when the chosen model can reason. The row starts in the
  team's reasoning default for that model. The choice lasts for the conversation
  only (browser session storage), and a new conversation starts on the
  recommended model.
- **Selectable models on the member read.** The members-readable
  effective-chat-model read (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §41) returns
  the selectable models when the chat page opens. Prepare-execution stays free
  of catalog fetches.
- **Per-turn `runtime_context.chat_profile_id`.** The pod validates it, and the
  instance recommendation, against `can_use`, the team-disabled set and its
  catalog, and ignores an invalid value. The team-disabled set reaches the pod
  on the trusted per-turn runtime binding.
- **Precedence**, high to low: platform binding > pod YAML per-agent override >
  user's choice > instance recommended model > team default > pod default.
- **Per-agent reasoning settings are retired.** `reasoning_enabled` /
  `reasoning_default_on` leave `AgentTuning`, the control-plane tuning, the
  product schemas, the form, i18n and the "reasoning" tool pack. On
  `AgentDefinition` they stay one SDK minor as deprecated no-ops (design Q1).
  Stored rows and old bundles still load.
- **Reasoning ceiling.** The platform per-model activation (REASON-01 level 2)
  alone is the ceiling. A turn reasons only on an explicit `reasoning: true`,
  which the composer always sends. The effort picker stays withdrawn (§8.48).

## Capabilities

### New Capabilities

- `team-model-settings`: a team's enabled models, default model, per-model
  reasoning default, and the disable-impact flow.
- `chat-composer-model-choice`: per-conversation model and reasoning choice in
  the composer, and the member-readable list it is built from.
- `agent-recommended-model`: an agent instance's recommended chat model,
  migration of the former per-template overrides, and retirement of the
  per-agent reasoning settings.

### Modified Capabilities

None under `openspec/specs/`. This change adds requirements to `model-routing`,
which the shipped but unarchived `model-profile-identity` change introduces, so
that change must be archived first. That archive is not done here.

## Impact

- **SDK / runtime**: `fred_sdk/contracts/context.py` (`RuntimeContext`, resolver
  levels), `fred_sdk/contracts/models.py`, `fred_runtime/model_routing/provider.py`,
  `fred_runtime/app/agent_app.py`, `apps/fred-agents/fred_agents/platform_ops.py`,
  `test_assistant/conformance.py`.
- **Control plane**:
  - schema: `config/models.py`;
  - product: `product/{schemas,service}.py`;
  - routing policy: `routing_policy/{schemas,service,store,api}.py` (policy
    shape, new disable-impact read, effective-chat-model);
  - other code: `capabilities/service.py` (revocation cleanup),
    `import_export/{exporter,importer}.py`;
  - new Alembic revision on `team_routing_policy` + `agent_instance.tuning_json`;
  - API surface: authz matrix, regenerated `controlPlaneOpenApi.ts`.
- **Frontend**: `TeamSettingsRouting` (becomes the Models section), `ReasoningChip`,
  `useComposerSettings`, `runtimeContextBuilder`, `useManagedChat`, `AgentFormModal`/`AgentFormBody`,
  `toolPacks`/`toolPackLogic`, `SimpleCapabilitiesView`, fr/en locales, Help Center.
- **Docs**: `RUNTIME-EXECUTION-CONTRACT.md` and `CONTROL-PLANE-PRODUCT-CONTRACT.md`
  dated entries, `COMPONENT-UX.md`, `TEAM-PLATFORM-POLICY-RFC.md` (trim line 63),
  migration note.
- **Cross-repo**: `fred-agent-evaluator` must forward `ExecutionPreparation.chat_profile_id`
  instead of `agent_profile_overrides`.
- **Migration impact: minor.**
  - Data: one Alembic data migration moves per-template overrides into instance
    recommendations.
  - Defaults: reasoning now starts on for every allowed model whose reasoning an
    admin enabled, so admins should review platform reasoning switches and team
    reasoning defaults.
  - Pod authors: they should drop the deprecated `AgentDefinition` fields,
    which now log a warning and have no effect.
  - Team editors lose the team routing write: only team admins now edit the
    team's models.
