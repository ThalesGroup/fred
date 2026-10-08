Evidence sections dated before "Creation assistant evolution evidence" were recorded under the feature's first name, the prompt generator; identifiers below are the current ones.

## Backend evidence (2026-10-08)

Proven offline:
- `libs/fred-sdk`: `make code-quality` clean; `make test` 565 passed (includes `strip_reserved_prompt_tags`).
- `libs/fred-runtime`: `make code-quality` 0 errors (5 existing warnings in untouched files); `make test` 1833 passed. `tests/test_creation_assistant.py` covers offered-id filtering, reserved-tag stripping, prompt language, 502/503/504 mapping, the tool-calling fallback, input limits and KPI/log content. `tests/test_model_routing_provider.py` covers the default chat helper (now `build_chat_for_profile()`).
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1577 passed. `tests/test_creation_assistant.py` covers candidate narrowing (template and team `can_use`), token forwarding, 404 for an unknown or unusable template, pod error mapping and the `CAN_UPDATE_AGENTS` gate; `test_authz_endpoint_matrix.py` covers the matrix entry.
- `apps/fred-agents`: `make test` 120 passed against the changed runtime.
- `openspec validate add-agent-creation-assistant --strict` valid; `scripts/migration_guides.py check-pr` valid.
- Independent read-only review of the backend diff: no blocking issue. Its findings were fixed (call-time JSON-schema fallback, language tag validation, name/role inside the data markers, pod 401 and 422 detail mapping, added tests) or recorded in `design.md` open questions 3, 4 and 10.

Not proven yet:
- Prompt quality in en, and without candidate capabilities (task 5.1; fr is below).
- Pod-side ReBAC denial with an enabled engine (no test; the check reuses `check_user_team_permission_or_raise`).

## Frontend evidence (2026-10-08)

Proven offline, from `apps/frontend` (npx, not the make targets, to keep a running Vite intact):
- `npx tsc --noEmit -p .` clean; `npx eslint` and `npx prettier --check` clean on every touched file.
- `npx vitest run src/rework/components/pages/TeamAgentsPage src/rework/components/shared`: 104 files, 1223 tests passed; `src/rework/features/helpCenter`: 17 passed.
- `promptGeneration.test.ts` covers the system-prompt field choice, the request (translated names, base language, trimmed name and role), unavailable and duplicate ids dropped, selection replacement keeping reasoning and settings, `document_access` through the resource pack, and the error copy per status.
- `CreationAssistantDialog.test.tsx` covers generate then apply (encoded template id, only available recommendations), the replace warning, an inline 504 message keeping the description, and Escape closing the dialog but not the agent form.
- `FullPageModal.test.tsx` covers Escape on a lone modal, under a nested dialog, and when already consumed; the nested case fails without the fix.
- `TuningFieldRenderer.test.tsx` covers the button above both the library grid and the editor.

Not proven yet:
- The whole flow in a browser against a real model (task 5.1).

## Prompt quality smoke test, fr (2026-10-08)

`draft_agent` called directly (no HTTP, no ReBAC) from `apps/fred-agents` with its `config/` (`load_agent_pod_config`, `MockAwareModelProvider`), default chat profile `chat.mistral.small` (`mistral-small-latest`). Language `fr`; candidates: the nine French capability names and descriptions of `document_access`, `document_summarize`, `document_verbatim`, `document_extract`, `document_similarity`, `writable_document`, `ppt_filler`, `html_artifact`, `team_wiki` (`mcp-knowledge-flow-mcp-tabular` has no translation entry). Six model calls in total, no structured-output failure, no fallback.

Every run: valid structure, French, "tu", no "Fred", no tag, no reserved tag, opening sentence plus `##` sections.

First run, original meta-prompt:

| Case | Latency | capability_ids | Verdict |
| --- | --- | --- | --- |
| HR leave/mutuelle assistant | 4.3 s | document_access, document_extract | Good prompt; extract not needed; invented refusals ("salaire, évaluation"). |
| Meeting notes to minutes | 6.9 s | writable_document | 546 words; headings "Sources et accuracy", "Answer format"; invented styling ("interligne 1,15") and refusals. |
| Sales PowerPoint from product sheets | 6.6 s | document_access, document_extract, ppt_filler | Sound method; placeholder `Présentation_[NomProduit]_[Date].pptx`; invented refusals. |

All three rationales named capability ids. Fix (`fix(prompt-generator)` commit): headings in the prompt's language, no invented restrictions, no placeholders even in examples, capabilities named by name in the rationale.

Second run, revised meta-prompt:

| Case | Latency | capability_ids | Verdict |
| --- | --- | --- | --- |
| HR leave/mutuelle assistant | 5.0 s | document_access | Good; minimal selection; residual "Réponse format" heading and one `[email]` placeholder. |
| Meeting notes to minutes | 4.6 s | writable_document | Good; 384 words, French headings, rules from the description. |
| Sales PowerPoint from product sheets | 6.1 s | document_access, document_extract, ppt_filler | Usable; still some invented refusals, `{today}` misused as a document version, "réponds en français" fixes the reply language. |

Rationales now use capability names. Residual issues are small-model slips that the meta-prompt already forbids; worth re-checking on a larger default model before more tuning.

Excerpt (case 1, second run): "Tu es un assistant RH dédié aux salariés. Ton rôle est de répondre à leurs questions sur les congés et la mutuelle en t'appuyant uniquement sur les documents internes de l'entreprise."

`libs/fred-runtime` after the fix: `make code-quality` 0 errors (same 5 warnings); `make test` 1833 passed.

## Admin meta-prompt override evidence (2026-10-08)

Proven offline:
- `libs/fred-sdk`: `make code-quality` clean; `make test` 565 passed.
- `libs/fred-runtime`: `make code-quality` 0 errors (same 5 existing warnings); `make test` 1834 passed. `test_route_uses_the_admin_override_and_exposes_the_default` covers the override reaching the system message with `{language}` substituted and the default on `/agents/platform-prompt`.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1587 passed (before the pod-fetch parse tests were added; `tests/test_platform_prompt.py` 30 passed after). Covered: store set/get/delete on SQLite, default projection, older pod (`source_unavailable`), save with a missing placeholder flagged, reset, the gate on all three routes, request validation (blank, over cap, reserved tag), pod fetch with and without the new field, and the relay forwarding the stored override while ignoring a client-sent one.
- Migration `93427a5fe874` (down `aac66348e27b`): single Alembic head; `alembic upgrade head`, `alembic check` and `alembic downgrade base` on a scratch SQLite database.
- Frontend: `npx tsc --noEmit -p .`, `npx eslint` and `npx prettier` clean on touched files; `npx vitest run` on admin pages, locales, `TeamAgentsPage` and `Protected`: 31 files, 352 tests passed; Help Center 17 passed. `PlatformPromptPage.test.tsx` covers tab switching, the missing-placeholder warning with Save still enabled, a blank override refused, and reset through the confirmation.
- `make migration-check` valid.

Not proven yet:
- The PostgreSQL migration check (`make db-check-postgres-full` needs Docker).
- The admin tab and an overridden generation in a browser against a real pod.

## Default revision warning evidence (2026-10-08)

- `libs/fred-runtime`: `make code-quality` 0 errors (same 5 existing warnings); `make test` 1835 passed. `test_default_prompt_edit_bumps_its_revision_date` pins the default's sha256 with `CREATION_ASSISTANT_REVISED_AT` and fails with "update CREATION_ASSISTANT_REVISED_AT ... and this hash"; the route test checks `creation_assistant_prompt_revised_at` on `/agents/platform-prompt`.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1594 passed. `test_generator_prompt_flags_a_default_revised_after_the_override` covers later day (true), same day, older day, pod without a date, and no override (false); the pod-fetch test parses the date and reads `None` from an older pod.
- Frontend: `npx tsc --noEmit -p .`, `npx eslint` and `npx prettier` clean on touched files; `npx vitest run src/rework/components/pages/admin/`: 16 files, 223 passed, including the warning with **View default** revealing the built-in text and no warning once the flag clears.
- `make migration-check`: notes valid; no Alembic revision added for this step.
- Not verified: the warning in a running UI against a real pod.

## Generator token usage evidence (2026-10-08)

- `libs/fred-runtime`: `make code-quality` 0 errors (same 5 existing warnings); `make test` 1839 passed. New tests: the usage event carries the given actor, `{team_id, model_name, status}` dims, `{input_tokens, output_tokens}` quantities and no description or prompt text; an unusable answer still emits it with status `error`; a provider failure emits none; the route passes the body's `team_id` (no actor with security off).
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1604 passed. `tests/test_kpi_creation_assistant_usage.py`: all six token presets filter on both metric names; both by-agent presets keep generator events and return them under `__creation_assistant__`; the team filter still applies; `messages_over_time` still reads turns only.
- Frontend: tsc, eslint and prettier clean on touched files; vitest on `agentUsageRows`, `TeamUsagePage`, admin pages, `HomePage` and locales: 21 files, 249 passed.
- `make migration-check`: notes valid; no Alembic revision added.
- Not verified: the event in a live OpenSearch index and the charts with real data.

## Analytics tile evidence (2026-10-08)

- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1606 passed. `tests/test_kpi_creation_assistant_usage.py`: `creation_assistant_usage` filters on `agent.creation_assistant_completed` only and on the requested period, sums input and output tokens, counts drafts from the hit total, and returns zeros without events; `test_authz_endpoint_matrix.py` covers the new route.
- Client regenerated (`make generate-openapi`, then `npx @rtk-query/codegen-openapi src/slices/controlPlane/controlPlaneOpenApiConfig.json`).
- Frontend: tsc, eslint and prettier clean on touched files; vitest on `AnalyticsPage` and `KpiStatCard`: 3 files, 13 passed (tile rendered with fr/en keys; caption shown with a zero value, hidden while loading).
- `openspec validate add-agent-creation-assistant --strict`: valid.
- Not verified: the tile against a live OpenSearch index with real drafts.

## Creation assistant evolution evidence (2026-10-08)

Proven offline:
- `libs/fred-sdk`: `make code-quality` clean; `make test` 565 passed.
- `libs/fred-runtime`: `make code-quality` 0 errors (5 existing warnings in untouched files); `make test` 1846 passed. `tests/test_creation_assistant.py`: name/role/description returned, cleaned (Markdown, reserved tags, line breaks) and cut at a word boundary under 60/120/300, blank values `null`, an over-long single word hard-cut, the new meta-prompt hash pinned with `CREATION_ASSISTANT_REVISED_AT`, the route building the admin profile (`model_profile_id`) or the default. `tests/test_model_routing_provider.py`: `build_chat_for_profile()` builds the default without reasoning, a known chat profile, and falls back with a warning for an unknown or non-chat profile.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1610 passed. `tests/test_platform_prompt.py`: settings store round trip on SQLite (nullable text and model), defaults, model-only save keeping the built-in text, unknown profile refused with 422 and nothing stored, reset clearing the text and keeping the model, the gate on all routes, model options limited to profiles every pod serves and named after the catalog model (profile id appended when two share a name). `tests/test_creation_assistant.py`: drafted fields relayed; stored text and model forwarded, client-sent values ignored.
- `apps/fred-agents`: `make code-quality` clean; `make test` 120 passed.
- Migration `93427a5fe874` rewritten in place (down `aac66348e27b`): one head; `alembic upgrade head`, `alembic check` (no drift) and `alembic downgrade base` on a scratch SQLite database. `make migration-check` valid.
- Frontend: `npx tsc --noEmit -p .`, `npx eslint` and `npx prettier --check` clean on every touched file; vitest on `TeamAgentsPage`, `shared`, `admin`, `TeamUsagePage`, `utils`, Help Center and locales: 135 files, 1777 passed. `AgentFormModalAssistant.test.tsx`: header button disabled with its tooltip before a template, enabled after and in edit mode, applied draft written into the form. `CreationAssistantDialog.test.tsx`: all proposals ticked by default, only ticked items applied, group checkbox indeterminate, Apply disabled when nothing is ticked, no prompt item without a prompt field, overwrite confirmation listing replaced fields (cancel returns to the review), Escape closing only the confirmation. `creationAssistant.test.ts` and `AgentFormModal.test.ts`: selection, overwrite detection, template seeds counted as empty. `PlatformPromptPage.test.tsx`: model selector saving `{text: null, model_profile_id}`, text saved with the current model, a vanished profile kept visible.
- Reasoning proposal (task 5.8): `npx tsc --noEmit -p .`, `npx eslint` and `npx prettier --check` clean on the touched files; vitest on `AgentFormModal/`: 9 files, 87 passed. `creationAssistant.test.ts`: offered under the Simple view's pack rule and title, applied only when ticked, never an overwrite, `applyReasoning` setting both flags. `CreationAssistantDialog.test.tsx`: reasoning tile first and ticked, applied with the draft; unticking it and the column header (mixed, all, none) leaves it out; hidden when not offered; a selectable column with no recommended or available capability. `AgentFormModalAssistant.test.tsx`: reasoning offered to the dialog, both flags set only by a draft carrying it.
- `openspec validate add-agent-creation-assistant --strict` valid.

Not proven yet:
- Drafts against a real model (short fields in fr and en, chosen model actually used) and the whole flow in a browser (task 6.1).
- The PostgreSQL migration check (`make db-check-postgres-full` needs Docker).

## Name as identity, role as function (2026-10-08)

- `libs/fred-runtime`: meta-prompt name/role rules rewritten, hash re-pinned (`CREATION_ASSISTANT_REVISED_AT` unchanged, same day); `make code-quality` 0 errors (5 existing warnings); `make test` 1846 passed. Pod caps (60 / 120 / 300) unchanged: they stay above the new soft targets (about 20 / 40 / 140).
- Smoke, `draft_agent` called directly (no HTTP) on the pod default model `mistral-small-latest`, 4 cases x 2 runs (one prompt tweak between them):

| Case | Run 1 name / role | Run 2 name / role |
| --- | --- | --- |
| fr RH congés et mutuelle | Congeix / Assistant RH congés et mutuelle | CongeMut / Assistant RH congés et mutuelle |
| fr notes de réunion en CR | CompteRendu / Compte rendu de réunion | CompteRendu / Compte rendu de réunion |
| fr présentations PowerPoint | Présento / Assistant de présentations commerciales | Présento / Assistant de présentations commerciales |
| en contract risky clauses | ClauseGuard / Contract risk reviewer | ClauseGuard / Contract risk reviewer |

- Roles: short functional labels in every run (22-39 characters). Names: short and workplace-safe, but this model favours task words run together (CompteRendu, CongeMut) over an evocative identity, never picks a mythology figure, and ignored the tweak forbidding run-together task words.
- Not proven: name quality on a stronger model; whether drafting the name after the prompt (field order) improves it.

### Draft field order (2026-10-08)

`_GeneratedDraft` now lists `system_prompt`, `capability_ids`, `description`, `role`, `name`, `rationale`, so the model drafts the identity fields after working the mission out. Same 4 smoke cases on `mistral-small-latest` (4 calls): names Hélia, Réunote, Présento, ClauseGuard (previously Congeix/CongeMut, CompteRendu, Présento, ClauseGuard); roles 13-52 characters (one above the 40-character target, within the 120 cap). `make code-quality` 0 errors; `tests/test_creation_assistant.py` 29 passed.

### Apply with reasoning (2026-10-08)

- `applyDraft` merged `applyReasoning(prev)` (a full copy of the old form) over the drafted values, so Apply with reasoning ticked left every field unchanged; reasoning is now applied last on the merged state. `AgentFormModalAssistantFlow.test.tsx` (real modal, body and dialog) proves the visible fields, the prompt, and reasoning surviving a capability apply; failed on the old code. TeamAgentsPage vitest: 15 files, 119 tests passed.

### Rebase onto the Attachments / Team documents split (2026-10-08)

- `applyReasoning` deleted in favour of the form's `withReasoning`; a recommended `document_access` now turns on both document packs. `creationAssistant.test.ts` proves both sources set and both packs checked, even from a stored config with one source off. `npx tsc --noEmit -p .` clean; vitest on TeamAgentsPage, admin, shared, utils and helpCenter: 135 files, 1793 tests passed.

### Final review follow-ups (2026-10-08)

- `llm.call_latency_ms` no longer emitted by the draft (agent turns emit it with another label set, and `PrometheusKPIStore` fixes labels from the first event); `agent.creation_assistant_completed` stays the only KPI. `test_observability_carries_counts_and_no_content` asserts it is the only event; the 502/504 tests read the status from the log line.
- One 50 s deadline (`asyncio.timeout_at`) covers settings read, model build and the structured call with its retry; settings read timeout 2 s. `test_settings_read_and_draft_share_one_deadline` (each step fits alone, both together answer 504) and `test_settings_read_that_hangs_is_504` (no model built).
- `team_id` URL-encoded in the settings URL: `test_settings_url_encodes_the_team_id` (`../admin?x=1#` stays one path segment).
- `libs/fred-runtime`: `make code-quality` 0 errors (5 existing warnings in untouched files); `make test` 1893 passed, 11 skipped; `tests/test_creation_assistant.py` 53 passed. Help Center vitest 17 passed, prettier clean on both `administration.md`.
- Not changed, separate issue: the synchronous OpenSearch `store.client.search` in the async KPI presets (`kpi/api.py`).

## Manual browser check (2026-10-08)

- The developer created an agent from the assistant alone (create mode, fr), after switching the admin model to `chat.mistral.medium`. The pod log shows `event=creation_assistant_completed status=ok model=mistral-medium-latest`, so the admin model was picked up on the next draft without a restart.
- English was exercised against the real model by the name smoke script (`ClauseGuard`, see "Name as identity, role as function"). A draft recommending no capability was not exercised against a real model; unit tests cover an empty `capability_ids`.
- Streamed structured output in `langchain-openai` logged a Pydantic serializer warning quoting the generated draft. The draft call now runs without streaming; `test_streaming_model_is_called_whole_without_serializer_warnings` pins it, and the pod log after the fix shows no warning.

## Reasoning switch and richer prompts (2026-10-08)

Live risk check first (`chat.mistral.medium`, `reasoning_effort: high`, `ChatOpenAI` on `api.mistral.ai`): with reasoning kept, the answer content is a list `[thinking, text]`; `with_structured_output(<Pydantic class>, method="json_schema")` raised the OpenAI SDK's `ValidationError` ("JSON input should be string"), and the `function_calling` retry returned no tool call (`OutputParserException`). Passing the same schema as a JSON-schema dict parsed correctly (LangChain reads the text blocks): 14.5 s with reasoning, 3.3 s without. Hence decision 3: dict schema for reasoning calls, plus one retry without reasoning on an unusable answer, a refused request, or a call still running at `deadline - 15 s`.

Live drafts through `draft_agent` (smoke script outside the repo, nine fr/en capability candidates), before vs after the meta-prompt rewrite, words per drafted prompt:

| Case | Before (reasoning on) | After, reasoning on | After, reasoning off |
| --- | --- | --- | --- |
| HR assistant (fr) | 212 w, 23.9 s | 623 w, 22.2 s | - |
| Supplier contract review (en, documents) | 204 w, 17.4 s | 920 w, 47.1 s; rerun fell back at 35 s, 570 w, 42.4 s total | 609 w, 7.5 s |
| Meeting minutes (fr) | 197 w, 37.2 s | 562 w, 33.6 s | 724 w, 10.1 s |
| Sales PowerPoint (en) | - | 358 w, 25.0 s | - |

Every after-draft has a "using your capabilities" section; every draft recommending document capabilities states the summarize-only-for-overview rule. One reasoning draft addressed the agent with "vous" despite the "tu" rule. Output tokens: 3.5-7.5k with reasoning, 0.9-1.3k without.

Offline:
- `libs/fred-sdk`: `make code-quality` clean; `make test` 565 passed.
- `libs/fred-runtime`: `make code-quality` 0 errors (same 5 existing warnings); `make test` 1903 passed. New: `keep_reasoning` kept for a thinking profile and ignored without `supports_thinking`, `chat_profile_reasons()`, the dict schema on reasoning calls, the retry without reasoning for an unusable answer, a refused request and a too-slow call (tokens summed), no retry on a provider error, no fallback model when the profile cannot reason or the switch is off, the route passing `reasoning_enabled`, the settings default.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1615 passed. New: column default true and round trip on SQLite, reasoning-only save keeps `updated_at` / `updated_by`, reset keeps model and reasoning, `supports_reasoning` from `model_thinking_profile_ids`, PUT forwarding the switch, the pod settings route returning it.
- `apps/fred-agents`: `make test` 120 passed.
- Migration `93427a5fe874` edited in place: single head; dev PostgreSQL downgraded to `aac66348e27b` and upgraded to head (`reasoning_enabled boolean not null default true`). `make migration-check MIGRATION_BASE=origin/swift` valid.
- Frontend: `npx tsc --noEmit -p .`, `npx eslint` and `npx prettier --check` clean on touched files; `npx vitest run src/rework/components/pages/admin src/rework/features/helpCenter src/locales`: 19 files, 257 passed, including the switch on by default, saved alone, and disabled for a profile without `supports_reasoning`.

Not proven: the switch in a running browser session; the cost of an abandoned reasoning call (no usage is returned when it is cut short).

## Meta-prompt review fixes (2026-10-08)

Product-owner review of two French drafts: half-English headings, the agent addressed as "vous", invented organisation facts (document names, labels, versions, numeric limits), documents-only grounding, a promised output no capability produces, a confirmation step forced before every task. The meta-prompt now: describes sections as meanings to write in `{language}`, not titles; requires "tu" in French without exception; forbids invented names, labels, versions, dates and numeric limits, including made-up example citations; asks for team documents first with a declared fallback on general expertise; promises only what a capability's description says; asks questions only when blocking; and asks the model to check its rules do not contradict each other.

Live draft (fr, data thinking facilitator, ten real capability candidates), one call per row:

| Profile | Reasoning | Latency | Words | Headings fr | "tu" | No invented facts | Balanced grounding | No overpromise | Ask only if blocking |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mistral-small | off | 15.7 s | 1164 | yes | yes | yes | yes | no (Word, not recommended) | yes |
| mistral-small | on | 18.1 s | 1100 | yes | yes | no (example citation) | no | yes | yes |
| mistral-medium | off | 13.9 s | 1021 | yes | one slip | no (example citation) | yes | yes | yes |
| mistral-medium | on, fell back at 35 s | 49.9 s | 1007 | yes | yes | no (example date) | partly | yes | yes |

The two remaining failures (made-up example citations, a minimum number of documents) led to two tightened sentences after these runs; they are not covered by a live call. Every draft overshoots the 500-900 word target (1,000-1,160, under the 1,200 cap). `libs/fred-runtime`: `make code-quality` 0 errors; `make test` 1903 passed.

## Reasoning effort instead of the switch (2026-10-08)

Live gate first: one draft call (`ca._attempt`, reasoning schema, no time cut) with the data-thinking description, `reasoning_effort` overridden on a copy of the profile config:

| Profile | `reasoning_effort` | Result | Latency |
| --- | --- | --- | --- |
| chat.mistral.medium | low | HTTP 400 "reasoning_effort low is not supported for this model, supported values: [high, none]" | 0.6 s |
| chat.mistral.medium | medium | HTTP 400, same, supported values [high, none] | 0.6 s |
| chat.mistral.small | low | HTTP 400 "Must be one of (none, high)" | 0.3 s |
| chat.mistral.medium | high | answers (earlier run: cut at 35 s, retried without reasoning, 49.9 s total) | - |
| chat.mistral.small | high | answers (earlier run: 18.1 s, 2,524 output tokens vs 2,054 off) | - |

Mistral exposes two states (`none`, `high`) and rejects other levels, so levels are declared explicitly per profile (`reasoning_efforts`), never inferred; the Mistral profiles declare none and keep an on/off switch. No profile declares levels yet: a selectable level is proven offline only. The 15 s reasoning cut is unchanged.

Dev database: the edited migration `93427a5fe874` was applied to the live dev table by a one-off transaction (as the table owner) instead of a downgrade: add `reasoning_effort varchar not null default 'medium'`, set it from `reasoning_enabled` (true → `medium`, false → `off`), drop `reasoning_enabled`, add the check constraint. The one row kept `id`, `model_profile_id` (null), `text` (null), `updated_by` and `updated_at` (2026-10-08 18:13:19 UTC) unchanged; `reasoning_enabled = t` became `reasoning_effort = medium`. `alembic current` still `93427a5fe874`. The DDL rendered by `alembic upgrade aac66348e27b:93427a5fe874 --sql`, run on a throwaway `fred_migcheck` database, gives the same columns, types, defaults, nullability and constraints as the converted dev table (only the column order differs).

Offline:
- `libs/fred-sdk`: `make code-quality` clean; `make test` 565 passed.
- `libs/fred-runtime`: `make code-quality` 0 errors (5 existing warnings); `make test` 1915 passed. New: `reasoning_efforts` absent by default, ordered, single level is on/off, refused without `supports_thinking`, empty, unknown or missing the profile's own value; projection lists only levelled profiles; the clamp per level (ties to the stronger), `off` strips, on/off profile keeps its own value, the catalog config is not mutated; the fallback built only when the call reasons; settings default `medium`, `reasoning_enabled` ignored, unknown value refused; the route passing the effort.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1621 passed. New: column default `medium` and round trip on SQLite, reasoning-only save keeps `updated_at` / `updated_by`, reset keeps model and effort, 422 only for a value outside the four, any value saved whatever the model offers, options carrying `reasoning_efforts`, `default_model_profile_id` set when pods agree and `null` otherwise, pod payload levels filtered to the known ones.
- `apps/fred-agents`: `make code-quality` clean; `make test` 120 passed (loads the catalog with its new comments).
- Frontend: `npx tsc --noEmit` clean, `npx eslint` and `npx prettier --check` clean on touched files; `npx vitest run src/rework/components/pages/admin src/rework/features/helpCenter src/locales src/rework/components/shared/atoms/ButtonGroup`: 21 files, 273 passed. New: button group with Off plus the declared levels saving `high`, a level normalised to `medium` on an on/off model, the platform default using the pods' default profile's control, and the normalisation rule.
- `alembic heads`: single head `93427a5fe874`; `make migration-check MIGRATION_BASE=origin/swift` valid; `openspec validate add-agent-creation-assistant --strict` valid.

Not proven: the button group in a running browser session (no levelled profile in the local catalog); a live call at a declared level on a provider that accepts levels.

## Hedged reasoning call (2026-10-08)

Trigger, live: Mistral Medium with reasoning cut at 35 s, the retry without reasoning (~14 s for a ~1,000-word draft) missed the 50 s deadline: `status=timeout`, 504, 0 tokens. The reasoning call is now hedged at 23 s instead (decision 3); `REASONING_RESERVE_S` is deleted.

Live (`chat.mistral.medium`, effort `medium` sent as `high`, data-thinking description, 10 capabilities, through `draft_agent`):

| Run | Latency | Calls | Winner | Plain call | Reasoning call | Words | Tokens counted (in / out) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 36.5 s | 2 (hedged) | plain | 13.5 s | cancelled at 36.5 s | 1000 | 1,802 out |
| 2 | 38.9 s | 2 (hedged) | plain | 15.9 s | cancelled at 38.9 s | 1062 | 2,902 / 1,851 |

Run 2 log: `event=creation_assistant_completed status=ok ... input_tokens=2902 output_tokens=1851 capabilities_offered=10 calls=2 hedged=true winner=plain reasoning=fallback`. Both drafts would have timed out under the former cut.

- `libs/fred-runtime`: `make code-quality` 0 errors (5 existing warnings in untouched files); `make test` 1921 passed. `tests/test_creation_assistant.py` (hedge constant monkeypatched to 50 ms): reasoning before the hedge is one call; slow reasoning hedged, plain wins, reasoning cancelled and its tokens not counted; reasoning finishing after the hedge wins, plain cancelled; an unusable or refused reasoning answer starts plain at once (hedge at 30 s); one call failing after the hedge waits for the other (both answers counted); both failing is 502 with `winner=none`; the deadline cancels both calls, leaks no task, answers 504 and emits no usage; KPI dims `calls`, `hedged`, `winner`; log `reasoning=used|off|fallback`. The old reserve test is replaced.
- Frontend Help Center: `npx vitest run src/rework/features/helpCenter` 17 passed; `npx prettier --check` clean on both `administration.md`.

Not proven: what the provider bills for a cancelled reasoning call (no usage is returned for it); a live run where the reasoning call wins after the hedge.

## Reasoning off by default (2026-10-08)

Trigger: a blind comparison of the current meta-prompt (3 descriptions, fr/en, rubric of 9 criteria scored /18, prompts scored under random labels before the reveal; one run per cell, LLM scorer, so variance is unmeasured):

| Config | Mean score (usable drafts) | Mean latency | Mean output tokens | Usable |
| --- | --- | --- | --- | --- |
| `chat.mistral.small`, reasoning on (`high`), no hedge | 13.5 (n=2) | 17.1 s | 2,446 | 2/3 (one unparseable answer, 502) |
| `chat.mistral.medium`, reasoning off | 13.3 (n=3) | 11.9 s | 1,420 | 3/3 |

Same quality within noise, ~30% faster, ~40% fewer output tokens; with Medium and reasoning on, the reasoning call never finished before the hedged call without it (see "Hedged reasoning call"). Both configs share the same remaining slips (documents-only wording beside a fallback rule, realistic example citations), which are meta-prompt issues. Product-owner decision: `reasoning_effort` defaults to `off` everywhere; the hedge is unchanged.

Dev database: the migration `93427a5fe874` was edited in place (server default `off`); the live dev column default was aligned with `ALTER TABLE creation_assistant_settings ALTER COLUMN reasoning_effort SET DEFAULT 'off'` as the table owner (`fred`); `information_schema.columns.column_default` now reads `'off'::character varying`. The stored row (the admin's current setting: `chat.mistral.medium`, `medium`) was left untouched. `alembic current` and `alembic heads`: `93427a5fe874`.

Offline:
- `libs/fred-sdk`: `make code-quality` clean; `make test` 565 passed.
- `libs/fred-runtime`: `make code-quality` 0 errors (5 existing warnings); `make test` 1921 passed. `CreationAssistantRuntimeSettings()` and an older control plane omitting the field give `off`; an unreadable settings read and a pod without a control plane fall back to `off`.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1622 passed. New: a row inserted without `reasoning_effort` gets the column's server default `off` (SQLite); the ORM default, the GET with nothing stored, the pod-facing read and the PUT request default are `off`.
- Frontend: `npx tsc --noEmit` clean; `npx prettier --check` clean on touched files; `npx vitest run src/rework/components/pages/admin/PlatformPromptPage src/rework/features/helpCenter`: 4 files, 40 passed. New: settings without an effort show the switch off, and turning it on saves `medium`.
- `openspec validate add-agent-creation-assistant --strict` valid; `make migration-check MIGRATION_BASE=origin/swift` valid. The generated `controlPlaneOpenApi.ts` carries no field defaults, so it is unchanged.

## Performance review (2026-10-08)

Independent review (`fred-performance-reviewer`) of the pod route, the hedge, the relay and the KPI presets: no blocking I/O on the async path, no task leak (every hedged call is cancelled and awaited on any exit, deadline included), no mutation of shared configuration (the reasoning effort is applied on a copy of the profile config).

| Finding | Disposition |
| --- | --- |
| F1 `agent.creation_assistant_completed` skipped on timeouts and provider errors: Grafana never saw the failure/latency tail | Fixed: emitted for every outcome, `quantities` only when the provider answered; token presets and `drafts` keep only events carrying `quantities.input_tokens` |
| F2 the call without reasoning could start too late to finish | Guard fixed: not started with less than `MIN_PLAIN_CALL_S` (12 s, plain calls measured 7.5-16 s for ~1k words) left; the hedge cap is a reviewer question (design.md open question 17) |
| F3 `calls` / `hedged` / `winner` are not Prometheus labels | Documented (`OBSERVABILITY-AND-AUDIT.md`); adding one is a reviewer question (open question 18) |
| F4 relay `httpx.Timeout(55, connect=5)` also set a 55 s pool wait on the shared runtime client | Fixed: `pool=5.0`; `httpx.PoolTimeout` answers 503 "the control plane is busy", not the slow-draft 504 |
| F5 under control-plane or pool saturation the settings read silently falls back to the pod defaults | By design (decision 9), documented; WARNING log carries the error type |
| F6 `fred_core/model/factory.py` builds a new `ClientSecretCredential` per model, so its sync token provider makes a blocking AAD round-trip on the event loop for every `azure_apim` model (twice per hedged draft); separately, KPI presets call the synchronous OpenSearch `search` inside async handlers | Pre-existing, outside this change: separate issues |
| F7 Fallback model built up front even when unused; per-build `get_shared_stack` warning when a profile declares its own timeout; a few sequential awaits in the relay (ReBAC, template fetch, usable capabilities) and in the admin settings projection | Negligible next to a 7-50 s model call, no action |

Offline:
- `libs/fred-runtime`: `make code-quality` 0 errors (5 existing warnings in untouched files); `make test` 1923 passed. New or changed in `tests/test_creation_assistant.py` (69 passed): a timeout and a provider error emit the event with their status, latency and `quantities=None`; the deadline during the hedge emits `status=timeout` without tokens; the call without reasoning is not started when the time left at the hedge is under `MIN_PLAIN_CALL_S` (reasoning awaited alone, `calls=1 hedged=false`, `event=creation_assistant_plain_skipped`); an early retryable failure without time left answers 502 without a second call.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1626 passed. New: the relay sends `pool=5.0, connect=5.0, read=55.0` and maps `httpx.PoolTimeout` to 503 without "too long"; a small evaluator of the presets' filter clauses shows `TOKEN_USAGE_FILTER` keeps turns and answered creation assistant events and drops a timed-out one, and `creation_assistant_usage` counts answered calls only.

Not proven: Grafana panels on the new timeout/error events (no live run); the guard against a live provider (only the 50 s budget's arithmetic: the 23 s hedge leaves 27 s).

## Code review 2 (2026-10-08)

| Finding | Disposition |
| --- | --- |
| R1 an empty or tag-only prompt from the reasoning call won the hedge (checked only after the race), cancelling the plain call and answering 502 | Fixed: checked in `_parsed_draft`, so it is an unusable answer (`_retryable`); the plain call starts or keeps running; both empty answer 502 |
| R2 `rationale` generated, capped and sent but never shown | Removed end to end: meta-prompt, `_GeneratedDraft`, `MAX_DRAFT_RATIONALE_CHARS`, `AgentDraftResult`, both generated clients, test fixtures, contracts, OpenSpec, `COMPONENT-UX.md`; the "say what detail would improve it" hint dropped with it (no other field to carry it) |
| R3 franchise name examples in the meta-prompt; one over-long source line | Replaced by coined "Brivel" / "Solvane"; line wrapped; `CREATION_ASSISTANT_REVISED_AT` already 2026-10-08, hash re-pinned |
| R4 spec said drafts run "with reasoning turned off" | Now refers to the admin's reasoning effort requirement |
| R5 stale authz matrix comments, design decision 9, §8.105 name/role lengths, migration note button label | Fixed (name about 20, role at most 40, **Assistant**) |
| R6 a switch "on" that sends nothing: single declared level ignored; thinking profile without any level | Single declared level is "on" (`ModelProfile.reasoning_on_effort`); a thinking profile with nothing to send is projected as `reasoning_efforts: {id: []}`, reported `supports_reasoning: false` (disabled control), and the pod builds it without reasoning. Boot validation unchanged |
| R7 Help Center recommended the "Medium" model | "an intermediate model" / "un modèle intermédiaire" |
| R8 `_chat_profile` warning wrong for a non-chat profile and logged twice | One warning saying "not in this pod's catalog" or "not a chat profile (<capability>)"; `build_chat_for_profile` now resolves once and returns `(model, name, plain fallback or None)`, `chat_profile_reasoning_effort` deleted |
| R9 no test of the `model_reasoning_efforts` merge across pods | Added to `test_aggregation_unions_model_profile_ids_across_pods` |
| R10 `platform_prompt/service.py` imports private `product.service` helpers | Not changed: `routing_policy/service.py`, `capabilities/catalog.py` and `capabilities/service.py` already import the same two names on `swift`; renaming them touches ~40 sites outside this change, so it belongs in its own refactor PR |
| R11 admin pane overwrote a stored `low`/`high` with `medium` when the model's control is unknown | New `unknown` control (rendered as the switch) keeps the stored effort until toggled; `unsupported` keeps it too |

Offline:
- `libs/fred-sdk`: `make code-quality` clean; `make test` 565 passed.
- `libs/fred-runtime`: `make code-quality` 0 errors (5 existing warnings in untouched files); `make test` 1927 passed. New: reasoning call returning a blank or tag-only prompt loses to the plain call, both empty answer 502; single declared level sends it, a bare thinking profile builds without reasoning and no fallback; the fallback returned only when the call reasons; warning wording per case; projection maps a bare thinking profile to `[]`.
- `apps/control-plane-backend`: `make code-quality` clean; `make test` 1626 passed. New: empty levels kept from the pod payload, option with empty levels reports `supports_reasoning: false`, levels merged across pods.
- `apps/fred-agents`: `make code-quality` clean; `make test` 120 passed.
- Frontend: `npx tsc --noEmit -p .` clean; `npx prettier --check` clean on changed files; `npx vitest run src/rework/components/pages/admin src/rework/components/pages/TeamAgentsPage src/rework/features/helpCenter src/locales`: 36 files, 413 passed. New: unknown control keeps `high`, unsupported keeps `low` on a text-only save.
- `openspec validate add-agent-creation-assistant --strict` valid; `make migration-check MIGRATION_BASE=origin/swift` valid; the old franchise name examples are gone from the repository.

Not proven: no live model run after these changes (the meta-prompt only lost the rationale and changed two example names).

## Grounding and invented sources (2026-10-08)

The meta-prompt's sources section now asks for "team documents or data first and cited, then general expertise said as such", keeps general questions related to the role in scope, and forbids absolute grounding formulas and minimum source counts unless the description demands them. The invented-facts rule now also covers file names, section or page numbers, years and figures inside examples, and gives the citation pattern "(document title, section)".

Live, `chat.mistral.medium` without reasoning, one call per description (4 calls):

| Description | Latency / words | Grounding | Invented sources or figures |
| --- | --- | --- | --- |
| HR (fr) | 13.0 s / 972 | Partial: sources section has the fallback, opening still says "exclusivement" | Mostly pass: "(document titre, section)"; residual "5 jours de congés en août" |
| Contracts (en) | 7.3 s / 631 | Pass | Pass |
| Data thinking (fr) | 10.4 s / 808 | Pass, no absolute formula | Fail: "(Retour atelier Data Sprint, mars {today})" |
| Tabular (fr, tabular capability offered) | 10.9 s / 819 | Fail: refuses analyses outside the files, no sources section | Fail: "Ventes_2023.xlsx", "150 000 €", "ligne 45" |

Both defects pass 2/4 against 1/3 for the same config before the change. Offline: `libs/fred-runtime` `make code-quality` 0 errors (5 existing warnings), `make test` 1927 passed (default prompt hash re-pinned).

Not proven: the example-heavy drafts (tabular, data thinking) still invent concrete examples; one run per description.

## Meta-prompt v7 (2026-10-08)

Changes: the sources section is in every drafted prompt; the banned grounding formulas add "exclusively", "solely", "exclusivement", "seulement" and apply everywhere, opening sentence and mission included; examples are few and carry no values; headings, labels and bold markers carry no English word in another language; the method never opens with a rephrase-to-confirm step nor asks validation before delivering.

Live, `chat.mistral.medium` without reasoning, 5 calls:

| Description | Latency / words | Grounding | Invented values | Other |
| --- | --- | --- | --- | --- |
| HR (fr) | 10.5 s / 760 | Pass | Fail: "guide des congés 2024, section 3.2" | Labels in French; invented out-of-scope topics |
| Contracts (en) | 9.4 s / 769 | Pass | Minor: "Amend clause 4.2" | Pass |
| Data thinking (fr) | 13.3 s / 1008 | Partial: no proposal without the documents unless asked | Fail: "Compte-rendu atelier du 15/05", "80 %" | Labels in French; no validation step |
| Tabular (fr) | 9.2 s / 752 | Fail: "uniquement" inside the sources section | Fail: "Ventas_2024", "15 000 €", "lignes 10 à 50" | No confirmation step 1 |
| Tabular (en) | 6.6 s / 605 | Pass, general SQL questions answered from expertise | Fail: "sales_2024.xlsx, Revenue column" | Invented restrictions |

Fixed: sources section present 5/5, no English labels, no systematic confirmation or validation step. Not fixed: invented example values (0/5 clean) and one "uniquement". Offline: `libs/fred-runtime` `make code-quality` 0 errors (5 existing warnings), `make test` 1927 passed.
