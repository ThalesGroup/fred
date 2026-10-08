## 1. Runtime and SDK

- [x] 1.1 Add the wire models (`AgentDraftRequest`, `AgentDraftPodRequest`, `AgentDraftCapabilityCandidate`, `AgentDraftResult`) to `fred_sdk.contracts.agent_draft` and `strip_reserved_prompt_tags` to `prompt_utils`; verify with the SDK prompt-utils tests
- [x] 1.2 Add a `RoutedChatModelFactory` helper building a chat profile outside any turn (reasoning stripped, factory provider; now `build_chat_for_profile()`, 5.3); verify with provider tests
- [x] 1.3 Add the `creation_assistant` module with its meta-prompt and `POST /agents/creation-assistant/draft` (pod-side `CAN_UPDATE_AGENTS` re-check, 50 s deadline, unknown ids dropped, reserved tags stripped, 502/503/504 mapping, KPI without content); verify with runtime tests
- [x] 1.4 Regenerate the runtime OpenAPI client; add the `RUNTIME-EXECUTION-CONTRACT.md` §8 entry

## 2. Control plane

- [x] 2.1 Extract `_resolve_enrollable_template` from enrollment and reuse it
- [x] 2.2 Add `POST /control-plane/v1/teams/{team_id}/agent-templates/{template_id}/draft-agent` (`CAN_UPDATE_AGENTS`, candidate ids narrowed to the template's team-usable capabilities, caller's token forwarded on the shared runtime client, pod failures mapped); verify with route tests
- [x] 2.3 Add the `authz-endpoint-matrix.yaml` entry and the `CONTROL-PLANE-PRODUCT-CONTRACT.md` section; regenerate `controlPlaneOpenApi.ts`
- [x] 2.4 Add the migration note; verify `make code-quality` and `make test` in fred-sdk, fred-runtime and the control plane

## 3. Frontend and Help Center

- [x] 3.1 Add the dialog (description, draft, preview, apply / discard), sending translated capability names; first opened from a button above the prompt field (moved to the form header in 5.5)
- [x] 3.2 Apply the result: fill the prompt field, tick the recommended capabilities (the rationale, never shown, was removed in 5.15)
- [x] 3.3 Add fr and en strings and the Help Center pages; verify tsc, eslint, prettier and the touched vitest suites

## 4. Admin override of the meta-prompt

- [x] 4.1 Let the pod read the admin meta-prompt from the control plane (decision 9; first carried on `AgentDraftPodRequest`, since removed); use it with a fallback to the built-in text; expose the built-in text on `/agents/platform-prompt`; verify with runtime tests
- [x] 4.2 Add the `creation_assistant_settings` table, migration, store and `GET`/`PUT`/`DELETE /admin/platform/creation-assistant` (`can_edit_platform_prompt`, non-blank, 20k cap, reserved tags refused, missing `{language}` flagged); forward the override from the relay; add the matrix entries; verify with control-plane tests and the SQLite migration check
- [x] 4.3 Rename the admin page to "Platform prompts" with two tabs and add the generator pane (save, confirmed restore default, placeholder warning); regenerate the clients; verify tsc, eslint, prettier and vitest
- [x] 4.4 Update the contract docs, the migration note (now `minor`), the Help Center administration page and `COMPONENT-UX.md`
- [x] 4.5 Add `CREATION_ASSISTANT_REVISED_AT` pinned to the default's sha256 by a test, expose it on `/agents/platform-prompt`, return `default_revised_at` and `default_changed_since_override` from the admin read, show the warning with a read-only **View default** in the creation assistant tab; regenerate the clients; update the contract docs and Help Center; verify on each layer, no new migration
- [x] 4.6 Emit `agent.creation_assistant_completed` with the caller, `team_id`, `model_name`, `status` and token quantities; widen the six token-usage presets to both metric names and bucket creation assistant calls under `__creation_assistant__` in by-agent views; translate the label in the frontend; verify with runtime, control-plane and vitest tests
- [x] 4.7 Add the platform `creation_assistant_usage` preset (tokens, input/output split, number of uses) and a "Creation assistant" tile in the admin Analytics token-usage section; add the matrix entry and regenerate the client; verify with control-plane and vitest tests

## 5. Creation assistant evolution

- [x] 5.1 Rename the feature to the creation assistant on every layer (routes, SDK module, KPI event and preset, table, components, strings, docs, this change)
- [x] 5.2 Draft `name`, `role` and `description` too: meta-prompt targets (~30 / ~60 / ~140 characters), pod-side cleaning and word-boundary caps (60 / 120 / 300) below the form limits, `null` when empty; bump `CREATION_ASSISTANT_REVISED_AT`; verify with runtime tests
- [x] 5.3 Store `text` (nullable) and `model_profile_id` (nullable) in `creation_assistant_settings` (migration rewritten in place); list the selectable chat profiles on the admin read, refuse unknown ones on `PUT` (422), keep the model on `DELETE`; forward `model_profile_id` to the pod; add `RoutedChatModelFactory.build_chat_for_profile()` with a logged fallback to the default; verify with control-plane, runtime and SQLite migration checks
- [x] 5.4 Admin tab: model selector next to the meta-prompt editor, saved with the text; regenerate the clients; verify with vitest
- [x] 5.5 Move the entry point to a tonal header button (hidden on the template step, no tooltip), remove the prompt-field button and its `headerAction` plumbing; add `variant="tonal"` to `Button`
- [x] 5.6 Review step: checkboxes for prompt, name, role, description, all capabilities and each capability; apply only ticked items; critical confirmation before overwriting non-empty values; verify with vitest
- [x] 5.7 Update the contract docs, `OBSERVABILITY-AND-AUDIT.md`, the authz matrix, `COMPONENT-UX.md`, the migration note and the Help Center (fr, en); run the verification of every touched layer
- [x] 5.8 Always propose reasoning first in the capabilities column wherever the Simple view offers its pack (frontend only), ticked by default and in the column's select-all; applied, it turns reasoning on with conversations starting in it; never an overwrite; update `COMPONENT-UX.md` and the Help Center (fr, en); verify with vitest

- [x] 5.9 Reasoning switch (replaced by the effort of 5.11): `reasoning_enabled` (default true) in `creation_assistant_settings` (migration edited in place), admin `GET`/`PUT` (reasoning-only save keeps `updated_at`), `supports_reasoning` per model option, `CreationAssistantRuntimeSettings.reasoning_enabled`; `build_chat_for_profile(keep_reasoning=)` and `chat_profile_reasons()`; reasoning call parsed from a JSON-schema dict, retried once without reasoning when unusable, refused or past `deadline - 15 s`; admin `Switch` beside the model selector; regenerate the clients; verify with runtime, control-plane and vitest tests and a live Mistral Medium run
- [x] 5.10 Rewrite the meta-prompt for complete prompts (500-900 words, decision rules, a capabilities section, document summarize-versus-exhaustive rule); bump `CREATION_ASSISTANT_REVISED_AT` and its pinned hash; compare live samples before and after
- [x] 5.11 Reasoning effort instead of the switch: optional per-profile `reasoning_efforts` in the model catalog (boot validation, projected per profile as `model_reasoning_efforts`), `reasoning_effort` (off/low/medium/high, default medium) in `creation_assistant_settings` (migration edited in place, dev row converted), admin `GET`/`PUT` with `reasoning_efforts` per option and `default_model_profile_id`, pod clamp for this call only; admin button group, switch or disabled control by model; verify with a live Mistral probe of each level and runtime, control-plane and vitest tests
- [x] 5.12 Hedge the reasoning call instead of cutting it: after `REASONING_HEDGE_AFTER_S` (23 s) start the call without reasoning beside it, first usable draft wins, the other cancelled and awaited; remove `REASONING_RESERVE_S`; `calls`, `hedged`, `winner` in the log and KPI dims, `reasoning` in the log; update the contract, observability doc and Help Center (fr, en); verify with runtime tests and a live Mistral Medium run
- [x] 5.13 Reasoning off by default (product-owner decision after the blind v5 comparison): `reasoning_effort` default `off` in the migration (edited in place, dev column default aligned, dev row untouched), ORM, store, schemas, `CreationAssistantRuntimeSettings` and the admin pane's initial state; update the contracts, migration note, `COMPONENT-UX.md` and the Help Center (fr, en); verify with runtime, control-plane and vitest tests

- [x] 5.14 Performance review fixes: emit `agent.creation_assistant_completed` for every outcome with tokens only when the provider answered, token presets and `drafts` filtered on answered events; skip the call without reasoning when less than `MIN_PLAIN_CALL_S` (12 s) remain; relay pool timeout 5 s mapped to 503; update the contracts, `OBSERVABILITY-AND-AUDIT.md` and this change; verify with runtime and control-plane tests
- [x] 5.15 Code review 2 fixes: an empty or tag-only prompt is an unusable answer at parse time (never a hedge winner); remove `rationale` end to end (meta-prompt, SDK, clients, docs); neutral coined name examples and a new pinned hash; a single declared level is "on", a thinking profile with nothing to send is reported as not supporting reasoning (empty `model_reasoning_efforts` entry); `build_chat_for_profile` returns the fallback model and resolves the profile once (one accurate warning); the admin control keeps the stored effort when the model's control is unknown; doc and Help Center wording fixes; verify with runtime, control-plane and vitest tests

## 6. Close-out

- [x] 6.1 Manual check against a real model in fr and en, with and without capabilities (browser in fr; en through the smoke script; no-capability answer only unit-tested, see verification.md)
- [ ] 6.2 Review the open questions in `design.md` with the developer
- [ ] 6.3 Create the GitHub issue, record verification evidence, archive the change
