## Context

See proposal.md for motivation and the product decisions.

Current state:
- **Routing levels.** `resolve_effective_chat_profile` (fred-sdk) holds four
  profile-valued levels: pod YAML override, team per-agent override, team
  default, pod default. The platform binding short-circuits before it in
  `RoutedChatModelFactory.select`.
- **Client-forwarded team snapshot.** `chat_default_profile_id` and
  `agent_profile_overrides` come from prepare-execution and the browser
  forwards them. They are bounded only by the per-turn `usable_model_ids` gate
  (`can_use`, computed once per turn by the pod from ReBAC).
- **Trusted instance tuning.** Instance tuning reaches the pod server-side
  through `ManagedAgentRuntimeBinding`.
- **Policy storage.** Table `team_routing_policy` has columns `team_id`,
  `version`, `chat_default_profile_id`, `agent_profile_overrides_json`. The
  write gate today is `CAN_UPDATE_RESOURCES` (team_editor); team_admin and
  team_analyst get a read-only view. The runtime-binding call does not read
  the policy.
- **Instance tuning storage.** `agent_instance.tuning_json` is Text.
  `ManagedAgentTuning` and `AgentTuning` ignore unknown keys.
  `AgentDefinition` is `extra="forbid"`.
- **Effective-chat-model read (§41).** It is members-readable and per-pod. It
  already fetches the pod catalog, the reasoning store and
  `usable_capability_ids`. Prepare-execution is contractually free of
  pod-catalog fetches.
- **Reasoning today.** The ceiling is `platform activation AND
  tuning.reasoning_enabled` (§8.30). The composer seeds its row from
  `reasoning_default_on`.
- **Pattern to reuse.** The admin UI themes page (`UiSettingsPage.tsx`) has
  per-row `Switch` + "Set as default" `Button`, a default that cannot be hidden,
  and hidden themes stored as exceptions (`hidden_themes`).

## Goals / Non-Goals

**Goals:**
- Fewer routing levels than today, not more: the team per-template level goes;
  the user and instance levels arrive.
- No new per-turn I/O; atomic team writes with their side effects.

**Non-Goals:**
- Server-side storage of the user's choice; per-user routing policy.
- Propagating the choice to registry-invoked children.
- Changing the platform's `can_use` or reasoning admin surfaces, or re-adding
  an effort picker.

## Decisions

### D1 — User choice: `RuntimeContext.chat_profile_id: str | None`
It is a chat profile id, the key the team default already uses. A capability id
was rejected: one model can have several profiles, and routing keys on
profiles.

### D2 — Trust boundary: the pod checks `can_use` and the team-disabled set, ignores invalid values
In `select`, the user choice and the instance recommendation are accepted only
if the profile is known, chat-typed, its `capability_id ∈ usable_model_ids`
(or `None`, meaning ReBAC is off), and its `capability_id` is not in
`team_disabled_model_ids`. Otherwise the pod logs `[V2][MODEL_ROUTING]
… ignored` at debug (it runs on every model call) and falls through. A browser-held or stored preference can go stale
at any time, and must not break the turn. The team default keeps failing closed
as today.

**Team-disabled set, enforced pod-side (owner decision, 2026-10-09).**
- **Field.** `BoundRuntimeContext.team_disabled_model_ids: tuple[str, ...]`.
  It is trusted and has no `ctx.get`.
- **Channel.** It travels on `ManagedAgentRuntimeBinding`, the per-turn
  server-to-server call that already carries `reasoning_enabled_model_ids`.
  Prepare-execution is not that channel: its fields are forwarded by the
  browser, so they are not trusted.
- **Cost.** The runtime-binding call does not load the routing policy today
  (only prepare-execution does). It gains one primary-key read of
  `team_routing_policy`; see the implementation notes for the connection
  budget of that call.
- **Team default.** A team-disabled default cannot be stored (D4 validation).
  If one is ever seen, the turn keeps failing closed (`ModelNotUsableError`)
  rather than silently substituting a model.

### D3 — Instance recommendation: `recommended_chat_profile_id` in tuning
- **Where it lives.** The field is added to `AgentTuning` (SDK, read by the pod
  from the trusted binding) and to `ManagedAgentTuning`, inside `tuning_json`.
  This needs no schema change.
- **Null follows the team.** `null` means "follow team", so later default
  changes propagate.
- **Write validation.** Create and update validate against `can_use` ∩
  team-enabled ∩ the instance pod's chat profiles, reusing
  `check_profile_usable_for_team` extended with the team's disabled set.
- **Update semantics.** `UpdateAgentInstanceRequest` uses `model_fields_set` to
  tell "absent" from "clear".

A separate column was rejected: tuning already owns per-instance runtime
settings.

### D4 — Team model settings: stored as exceptions on `team_routing_policy`
- **New columns.** `disabled_model_ids_json` and
  `reasoning_default_off_model_ids_json` (Text JSON lists of model capability
  ids) replace `agent_profile_overrides_json`. `chat_default_profile_id` stays.
- **Why exceptions.** Storing exceptions makes "newly allowed model arrives
  enabled with reasoning ON" true with no write on platform grants. It mirrors
  `hidden_themes`. An allow-list was rejected: it would need a write hook on
  every platform grant, for every team.
- **Keyed by capability id.** Both lists use the model identity, as `can_use`
  and the reasoning store do. Profiles are just choice keys.
- **API.** `PATCH /teams/{id}/routing-policy` stays a full typed replacement:
  `chat_default_profile_id`, `disabled_model_ids`,
  `reasoning_default_off_model_ids`. **Gate: team_admin only**
  (`CAN_UPDATE_INFO`), a deliberate narrowing of today's team_editor gate
  (`CAN_UPDATE_RESOURCES`), by owner decision of 2026-10-09.
  - **No split.** After per-template overrides are removed, every remaining
    policy field belongs to the Models section, so the gate needs no split.
  - **What editors keep.** Team editors keep a read-only view, and keep
    editing each agent's recommended model through the agent form (its own
    gate, unchanged).
  - **Personal spaces.** The owner must still be able to write; the existing
    read gate's personal-space bypass is applied to the write too. A task
    tests this.
  - **Recorded in.** The authz matrix, a §37 dated entry and the migration
    note.
- **Validation.** The default profile's model must be usable and not disabled
  (422). Disabled ids must be usable ids; ids no longer allowed are pruned on
  write.
- **Atomic side effect.** When the new disabled set adds models, the same DB
  transaction clears `recommended_chat_profile_id` on the team's instances
  whose recommendation maps to them. This is one `UPDATE … agent_instance`
  pass over rows already loaded by `team_id`.
- **List read.** `GET …/available-models` (elevated read gate unchanged) gains
  `display_name` and `reasoning_available` per profile. The UI groups profiles
  into one row per `capability_id`, and the first chat profile is the "Set as
  default" key.

### D5 — Disable-impact read
`GET /teams/{team_id}/routing-policy/disable-impact?capability_id=` (team_admin, since it exposes agent names)
returns `{agents: [{agent_instance_id, display_name}]}`. It makes one `SELECT`
of the team's instances (indexed `team_id`), parses `tuning_json`, and maps
recommended profiles to capability ids with the pod catalogs already
aggregated for `available-models` (one fetch per distinct pod, no per-instance
call). The dialog's conversation line is static text: no server state exists
for it.

### D6 — Revocation by the platform
- **Turn time.** D2 ignores a recommendation whose model is no longer `can_use`.
- **Cleanup.** Where `capabilities/service.py` already reacts to a model being
  switched off (it clears reasoning there, REASON-01 §5.7), it also clears
  instance recommendations that map to it: across all teams for a
  platform-wide disable, or for the one team on a grant removal. It also prunes
  the model from the team exception lists.
- **No team dialog.**
- **Revoked default (owner decision, 2026-10-09).** The same cleanup clears a
  stored team default whose profile belongs to the revoked model, so the pod
  default takes over and turns keep working; the Models section then shows the
  pod default as the default. A default that stops resolving any other way
  (pod no longer serves it) still fails closed and is flagged.

### D7 — Per-template overrides removed, data migrated
- **Code.** `agent_profile_overrides` leaves `TeamRoutingPolicy`,
  `ExecutionPreparation`, `RuntimeContext`, `resolve_team_override`, the
  resolver and the conformance test assistant.
- **Alembic revision.** One new revision, parented on the current single head
  and re-parented on rebase per CLAUDE.md, never merged:
  1. add the two exception columns (default `'[]'`);
  2. for each policy row, for each `{source_agent_id: profile_id}` override,
     set `recommended_chat_profile_id` in `tuning_json` of instances with the
     same `team_id` and `source_agent_id` that have none;
  3. drop `agent_profile_overrides_json`.
- **Downgrade.** It re-adds the column empty. This is lossy, and is documented.
- **Import.** Old bundles map overrides the same way after instances are
  imported, with a warning counter. Ignoring them was rejected because it would
  silently change which model those agents run.
- **Evaluator.** `agent_model_override` now becomes
  `ExecutionPreparation.chat_profile_id` (user level, above the recommendation).

### D8 — Selectable models on the §41 read
- **New fields.** `EffectiveChatModel` gains `selectable_models:
  list[SelectableChatModel]` (`profile_id`, `capability_id`, `name`,
  `display_name`, `reasoning_enabled`, `reasoning_default_on`) and
  `choice_locked`.
- **Filter.** Rows are pod entries ∩ `can_use` ∩ not team-disabled.
- **No added I/O.** The read already fetches the pod catalog, the reasoning
  store, `can_use` and the policy row.
- **Recommended model.** `resolve_effective_chat_model` passes the instance
  recommendation and no user choice, so `name` and `capability_id` name the
  recommended model.

### D9 — Frontend state
- **Storage.** `useComposerSettings` gains `chatProfileId`, stored in
  `chat.composer.{sessionId}`.
- **Reasoning seed.** Reasoning seeds from the chosen row's
  `reasoning_default_on`, at conversation start and on each model switch.
- **Sending.** `runtimeContextBuilder` sends `chat_profile_id` when it is set,
  and sends an explicit `reasoning` while the row is visible.
- **Reconciliation.** On refetch, a choice missing from `selectable_models` is
  cleared with a snackbar. The read refetches on mount, on window focus and
  when another conversation opens (Q3), reusing `useRefetchOnWindowFocus`;
  mount and focus wait 30 s after the last read.
- **Settings UI.** `TeamSettingsRouting` becomes the Models section. It reuses
  the themes page grammar (`Switch`, `Button` with check icon, "Default"
  state) and the `Dialog` molecule for the impact confirmation. The
  per-template rows are deleted.

### D10 — Reasoning
- **What goes.** `reasoning_enabled` and `reasoning_default_on` are deleted
  everywhere listed in the proposal, except `AgentDefinition`, where they stay
  as deprecated no-ops for one SDK minor (Q1).
- **Control.** `_platform_reasoning_control` keeps only the platform gate. Its
  `params.default` is dropped; the composer seeds from the row.
- **Ceiling.** The pod ceiling is the platform list when tuning is present,
  else `[]`.
- **Tri-state, redefined explicitly.** `True` reasons within the ceiling.
  `False` and `None` both mean no reasoning. Without the agent gate, keeping
  "`None` = ceiling decides" would silently turn reasoning on for OpenAI-compat
  and evaluation callers that send nothing. The field stays `bool | None` for
  wire compatibility.
- **Strip point.** `build_for_chat` changes `turn_declined = reasoning is False`
  to `reasoning is not True` (Q2, decided).

### D11 — Sub-agents, other callers, KPIs
- **Sub-agents.** Registry children get only a `PortableContext`, so they never
  see the choice and keep their own resolution. Deep native sub-agents reuse
  the parent's model.
- **OpenAI-compatible router.** It sends no choice and runs by `agent_id`,
  so it gets the template's resolution and, with an empty ceiling, no
  reasoning, as on `swift` (Q2).
- **Conformance.** It forwards `chat_profile_id`.
- **KPIs.** No change: they group by the actual `model_name`, with no new label.

### D12 — Performance
- **Prepare-execution.** No new fetch.
- **Pod.** Per turn, it only adds set and dictionary lookups on data it
  already receives.
- **§41 read.** In-memory filtering only. Q3 makes it run more often (focus,
  conversation switch); mount and focus are limited to one read per 30 s per
  open chat, since each read also fetches the pod catalog.
- **Disable-impact.** One indexed query plus the already-needed catalog
  aggregation, on an explicit admin action.
- **Policy write.** One extra `UPDATE`, in the same transaction.
- **Runtime binding.** One more primary-key read per turn; the call's reads
  share two sessions (at most 2 pooled connections), see implementation notes.
- **Review.** The `fred-performance-reviewer` run is a task.

## Risks / Trade-offs

- **[Known risk] Reasoning ON by default for new models.** Reasoning re-issued
  duplicate tool calls (10/10 turns, `AGENT-THINKING-API-RFC.md` Amendment C;
  observed on Mistral Small), and it is slower and costlier. → Platform admins
  switch reasoning off per model, and teams switch the default off per model.
  The migration note asks for a review.
- **[Risk] Migration picks the wrong instance.** Only instances with an exact
  `team_id` + `source_agent_id` match and no recommendation are touched. →
  Tested on a fixture with mixed instances.
- **[Risk] Stale evaluator** still reads `agent_profile_overrides` and loses
  its model override. → Cross-repo task, shipped before or with this change.
- **[Risk] SDK break.** `AgentDefinition` is `extra="forbid"`. → Avoided: the
  fields stay as deprecated no-ops for one SDK minor (Q1).
- **[Risk] Team editors lose the routing write.** → This is announced in the
  migration note and the §37 entry. Editors still steer models per agent
  through the recommended model.

## Migration Plan

- **Impact: minor.**
- **Deploy.** Run the Alembic upgrade (data migration of per-template
  overrides). Old `tuning_json` keys are ignored and drop on the next save.
- **Operator action.** Review platform reasoning switches and team reasoning
  defaults. Tell team editors that only team admins now edit the team's
  models. Drop the deprecated `AgentDefinition` reasoning fields from custom
  pods before a later SDK minor removes them. Update `fred-agent-evaluator`.
- **Rollback.** The downgrade restores an empty overrides column. Migrated
  recommendations stay in `tuning_json`, and the old code ignores them, so
  per-template routing is lost until it is re-entered.

## Open questions for reviewers (dimitri-tombroff)

- **Q1 — decided (owner, 2026-10-09).** Keep `AgentDefinition.reasoning_enabled`
  / `reasoning_default_on` for one SDK minor as deprecated, inert fields:
  accepted (class attribute or constructor), ignored, one warning per
  definition class. `AgentTuning` keeps ignoring legacy keys. Removal follows in
  a later minor.
- **Q2 — decided (owner, 2026-10-10).** Keep D10: a turn that sends no
  reasoning value runs without reasoning. Only the composer and callers of the
  managed path that send `reasoning: true` reason. The OpenAI-compatible
  surface runs templates by `agent_id`, with no managed instance, so its
  ceiling is empty on `swift` as well: it never reasoned, and this change does
  not alter that. Letting it opt in would need a ceiling for direct runs (new
  I/O on that path), so it stays out of this change.
- **Q3 — decided (owner, 2026-10-10).** Yes, by refetch rather than push: the
  chat page re-reads the effective chat model on mount, when the window
  regains focus and when another conversation opens. Mount and focus skip the
  read when the last one is under 30 s old, since each read also fetches the
  pod catalog. A live push would add a long-lived connection per member for a
  rare admin action.

## Contract and doc divergence

- §37 is rewritten by a dated entry: per-template overrides removed, enabled
  set and reasoning defaults added, and the "per-message composer picker"
  non-goal reversed.
- §41's "chip stays read-only" non-goal is reversed.
- `TEAM-PLATFORM-POLICY-RFC.md:63` (per-user routing, out of V1) gets trimmed.
- `model-profile-identity` is shipped but not archived, and must be archived
  before this change.

## Implementation notes

- **Recommendation channel (1.2/1.3).** The pod carries the instance
  recommendation to `select` on a trusted `BoundRuntimeContext.recommended_chat_profile_id`,
  copied from the server-resolved tuning, beside `team_disabled_model_ids`.
- **Resolver contract (1.1).** `resolve_effective_chat_profile` stays pure: the
  caller validates the user and instance levels first and passes `None` when
  invalid, so resolution falls through. Control-plane (3.2) must do the same.
- **Log signal.** `ModelSelectionSource` gains `user_choice` and
  `instance_recommendation` for the `[V2][MODEL_ROUTING]` line. No KPI label.
- **Pod default.** The team-disabled set narrows the user, instance and team
  levels only; the ops-authored pod default stays gated by `can_use` alone.
- **Runtime client.** `RuntimeContext` and `AgentTuning` are in the runtime
  OpenAPI, so `runtimeOpenApi.ts` was regenerated with group 1.
- **Effective default (2.2/2.4).** With no stored team default, the pod default
  of the team's pods is the "Default" row: `available-models` returns it as
  `effective_default_profile_id` (only when those pods agree on the model), and
  the PATCH rejects disabling any of those pod defaults
  (`DefaultModelNotDisableableError`, 422).
- **Exceptions pruning (2.2).** Exception ids outside `usable_capability_ids`
  are dropped silently on write rather than rejected.
- **Atomic clear (2.2).** `TeamRoutingPolicyStore.upsert` clears the team's
  recommendations naming newly disabled models in its own session, editing the
  stored JSON in place (no `updated_at` bump). The ORM flush issues one UPDATE
  per cleared row, not a single statement.
- **Revocation (2.5).** A team grant removal (disable, reset to a default-off
  platform) cleans that team without a `can_use` check; a platform-wide
  default-on OFF and a personal-space scope revoke scan every team and clean
  only those that no longer `can_use` the model. The scan also finds teams
  whose stored default names the model (D6).
- **Selectable rows (3.2).** One row per model: the first chat profile, except
  the resolved model's row, keyed by the resolved profile.
- **Recommendation validation (3.1/3.3).** `check_profile_usable_for_team`
  also rejects a team-disabled model (`ModelDisabledForTeamError`, 422); it now
  backs the recommendation and the evaluator override.
- **Agent form options (5.3).** No per-pod model list exists for an instance
  being created, so the form offers `available-models` (chat profiles common
  to the team's pods) minus team-disabled models; the write still validates
  against the instance's own pod. An edit sends the recommendation only when it
  changed, so a stale stored value never blocks an unrelated save.
- **Personal space (5.1).** The personal-space DTO carries no `team_admin`
  relation, so the page grants the Models write by personal team id, matching
  the backend bypass.
- **Composer reconciliation (6.1).** An empty `selectable_models` (locked
  choice, unreachable pod) keeps the stored choice: it proves nothing, and the
  pod ignores an invalid choice anyway. With no row to read, reasoning seeds
  OFF.
- **Locked choice (6.3).** A locked choice lists no model rows; the menu keeps
  only the reasoning row when the resolved model can reason.
- **Evaluator field (6.2).** The chat UI does not forward
  `ExecutionPreparation.chat_profile_id`: it is evaluator-only and always null
  for the composer.
- **Cache tags.** `available-models` now carries the routing-policy tag, and an
  agent PATCH invalidates it, so the Models badge and the composer's
  recommended model refresh after a save.
- **Review fixes (2026-10-09).**
  - *Fail closed on an unreachable pod.* A PATCH that disables models is
    refused with 503 (`ModelCatalogUnavailableError`) when one of the team's
    pod catalogs returns nothing and either no default is stored (its pod
    default is unknown) or a model is newly disabled (its recommendations
    could not all be mapped). 503 rather than 422: the request is valid and
    succeeds once the pod is back.
  - *Optimistic concurrency.* `UpdateTeamRoutingPolicyRequest.expected_version`
    (optional; 0 = no row) is checked in the upsert transaction under a row
    lock; a mismatch is a 409. The Models section always sends it, reloads and
    warns on 409.
  - *Agent save vs disable.* The agent write re-checks its recommendation
    against `disabled_model_ids_json` read `FOR SHARE` in its own transaction,
    policy row first (the order a policy write takes, so no deadlock); an
    update that does not set the field keeps the row's stored value (`FOR
    UPDATE`). `clear_recommended_chat_profiles` locks the rows it edits.
  - *Direct template runs.* `agent_app` binds `chat_profile_id` only when
    `agent_instance_id` is set; `chat_default_profile_id` keeps its existing
    direct-run behaviour (covered by the existing regression test).
  - *Runtime-binding connection budget.* Before: one instance read, then a
    gather of 5 reads each on its own pooled session (peak 5 connections, 2
    sequential stages). After: two concurrent sessions, each running 3 short
    reads in sequence (instance, team settings, policy / reasoning list,
    platform binding, platform prompt): peak 2 connections, and a critical
    path of 6 round trips instead of 8 (pre-ping, `BEGIN`, 3 reads, `COMMIT`).
    Load test: `docs/swift/reviews/performance/2026-10-09-chat-model-picker/`. `ProductServiceDependencies.get_sql_session_factory`
    provides the shared session; without it (test fakes) each read opens its
    own session.
  - *Frontend.* The Models section locks writes while either read is
    fetching, writes the PATCH response into the policy cache, and invalidates
    the team's agent list; a read error shows a `ServiceNotice` instead of the
    empty state. `teamModelRows` keys a model's row by the first preferred
    profile it owns, so two profiles of one model never yield two rows or a
    false "unavailable". The composer re-checks a stored choice on
    conversation switch, against the agent's `currentData`.
  - *Agent form (owner reversal of the review's F5).* "Team default model"
    stays null and follows later changes; every enabled model, today's
    default included, can be pinned.
