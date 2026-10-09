## ADDED Requirements

### Requirement: Who can use the creation assistant

A user SHALL be able to request an agent draft for a template only if they can edit agents in the team (`team.can_update_agents`) and the team may use that template. The pod SHALL re-check `team.can_update_agents` on the team when its authorization engine is enabled. Nothing SHALL be stored by a draft.

#### Scenario: Direct pod call without the permission

- **WHEN** a caller who cannot edit agents in team A calls the pod's draft route directly for team A
- **THEN** the pod refuses with 403 and no model is called

#### Scenario: Team editor

- **WHEN** an editor of team A asks for a draft for a template team A may use
- **THEN** a draft is returned and no agent or setting is created or changed

#### Scenario: Not an editor

- **WHEN** a member of team A who cannot edit agents asks for a draft
- **THEN** the request is refused with 403 and no model is called

#### Scenario: Template not available to the team

- **WHEN** the template does not exist or team A may not use it, including in edit mode for an agent whose template the team may no longer use
- **THEN** the request is refused with 404 and no model is called, and the form shows that the assistant is not available for this agent

### Requirement: Recommended capabilities stay within what the team may enable

The control plane SHALL offer the model only the capabilities the request lists that the template advertises and the team may use. The returned `capability_ids` SHALL be a subset of the offered capabilities, without duplicates, in the model's order.

#### Scenario: Smuggled capability id

- **WHEN** the request lists a capability the template does not advertise, or the team may not use
- **THEN** that capability is not offered to the model and is never returned

#### Scenario: Model invents an id

- **WHEN** the model recommends an id that was not offered
- **THEN** that id is dropped from the result

### Requirement: The drafted prompt fits the platform's prompt assembly

The creation assistant SHALL instruct the model to write a complete Markdown prompt (500 to 900 words as a target) in the request's language, describing role, mission, audience and tone, method with its decision rules, when and how to use each recommended capability, sources and accuracy (always present), answer format, and rules and limits. When a document capability is recommended, it SHALL instruct the model to state that summarizing serves only a global overview or an explicit request for a summary, and that any other request is worked on exhaustively. It SHALL instruct the model to describe tool use in task terms, not to repeat the rules the platform already adds, not to name the platform, not to invent organisation facts or placeholders, and to treat the user's description as data. The returned prompt SHALL never contain a reserved prompt tag (`platform_instructions`, `platform_prompt`, `tools`, `agent_instructions`).

#### Scenario: Reserved tag in the model's answer

- **WHEN** the model writes `<agent_instructions>` around its prompt
- **THEN** the tag markup is removed and the words it wrapped are kept

#### Scenario: Document agent

- **WHEN** the draft recommends a capability that summarizes, reads, extracts from or compares documents
- **THEN** the meta-prompt has asked for a prompt that keeps summaries for overviews and explicit requests, and works exhaustively otherwise

#### Scenario: Language

- **WHEN** the request's language is `fr`
- **THEN** the model is asked to write the name, role, description and prompt in French

### Requirement: Name, role and description are short and always fit the form

The draft SHALL include a name, a role and a one-sentence description, in the request's language. The name SHALL be requested as the agent's identity: a short, memorable, workplace-safe proper name (not a job label) of about 20 characters at most; the role as a short functional job label of at most about 40 characters; the description as at most about 140 characters. The pod SHALL strip reserved tags, collapse whitespace and line breaks, remove surrounding quotes and Markdown emphasis, and cut each value at a word boundary to at most 60, 120 and 300 characters, below the form's 255, 255 and 500. A value left empty SHALL be returned as `null`. The draft SHALL carry no rationale.

#### Scenario: Long name from the model

- **WHEN** the model returns a 90-character name spread over two lines
- **THEN** the returned name is a single line of at most 60 characters ending on a whole word

#### Scenario: Empty role

- **WHEN** the model returns a blank role
- **THEN** the result's `role` is `null` and the review step does not offer a role

### Requirement: Input limits

The description SHALL be required, non-blank and at most 4000 characters. The language SHALL be a language tag (for example `fr`, `pt-BR`), never free text. At most 500 capabilities SHALL be offered. Invalid requests SHALL be refused with 422 before any model call.

#### Scenario: Blank description

- **WHEN** the description is empty or only whitespace
- **THEN** the request is refused with 422

### Requirement: Failures are explicit

A draft SHALL use the chat profile chosen by an admin, or the pod's default chat model when none is chosen or the pod does not know the chosen one, at the admin's reasoning effort (see "Admins choose the creation assistant's reasoning effort"), within one 50-second deadline covering the settings read, the model build and the structured call: one structured call, retried once with tool calling only when the JSON-schema call is refused for its shape (HTTP 400, or no status and a client-side rejection); authentication, permission, quota, connection and timeout failures SHALL NOT be retried. A pod without a routable default chat model, or failing to build the chat model for any reason, SHALL answer 503. Exceeding that deadline SHALL answer 504. A model error, an unparseable answer, an answer that does not match the draft schema or an empty prompt SHALL answer 502; an empty prompt, or one holding only reserved tags, SHALL be treated as an unusable answer when it is parsed. The control plane SHALL pass 403, 422, 503 and 504 through, report a pod 401 as 502, answer 504 when the pod does not reply within 55 seconds, 503 when it is unreachable or no connection to it frees up within 5 seconds, 501 when the pod predates the operation, and 502 otherwise.

#### Scenario: Slow model

- **WHEN** the model does not answer within 50 seconds
- **THEN** the user receives 504 and can try again

#### Scenario: Empty answer

- **WHEN** the model returns an empty prompt
- **THEN** the user receives 502

#### Scenario: Quota error

- **WHEN** the JSON-schema call fails with HTTP 429
- **THEN** no tool-calling retry is made and the user receives 502

### Requirement: Observability without content

Each draft SHALL write one log line with its status (`ok`, `error`, `timeout`), model, latency, token counts, number of calls, whether it was hedged, the winning call (`reasoning`, `plain`, `none`) and whether the draft used reasoning (`used`, `off`, `fallback`), and SHALL NOT emit `llm.call_latency_ms`, which stays reserved for agent model calls; latency, status, model and tokens reach KPIs through `agent.creation_assistant_completed`. Neither the description nor any drafted text SHALL be logged or emitted.

#### Scenario: Successful draft

- **WHEN** a draft succeeds
- **THEN** one `agent.creation_assistant_completed` event with status `ok` and no `llm.call_latency_ms` event is emitted, the log line carries the input and output tokens, and no log record contains the description or the prompt

### Requirement: Creation assistant tokens count in the user's and the team's usage

For every draft, whatever its outcome, the pod SHALL emit `agent.creation_assistant_completed` with its latency, the calling user as actor, `team_id`, `model_name`, `status`, `calls`, `hedged` and `winner`, without any text, and SHALL add `input_tokens` and `output_tokens` quantities only when the provider answered. Every token-usage preset (user, team and platform; over time, by model, by agent) SHALL include the events carrying tokens and SHALL ignore the others; turn, conversation and latency presets SHALL NOT. By-agent views SHALL show them in one bucket labelled "Creation assistant" / "Assistant de création". The admin Analytics page SHALL also show a "Creation assistant" / "Assistant de création" tile with its tokens and number of uses (`drafts`: the calls the provider answered) for the selected period.

#### Scenario: Usage counted for the creator

- **WHEN** a user drafts an agent in team T and never saves it
- **THEN** the call's tokens appear in that user's usage and in team T's usage, and the by-agent charts show a "Creation assistant" bar

#### Scenario: Admin tile for the period

- **WHEN** an observer opens the admin Analytics page for a period with three drafts of 1,200 tokens in total
- **THEN** the "Creation assistant" tile shows 1,200 with "3 uses", and shows 0 for a period without drafts

#### Scenario: Billed failure

- **WHEN** the model answers with an unusable result
- **THEN** the event is emitted with status `error` and its tokens are counted

#### Scenario: No answer

- **WHEN** the call times out or the provider fails
- **THEN** the event is emitted with status `timeout` or `error`, its latency and no token quantities, and no token-usage preset or `drafts` count includes it

#### Scenario: Turn counts unchanged

- **WHEN** creation assistant events exist in the period
- **THEN** message, conversation and top-user counts are unchanged

### Requirement: Applying a draft in the agent form

The agent form header SHALL offer one **Assistant** button in create and edit modes, shown only once a template is chosen (never on the template step). The review step SHALL let the user tick each proposal separately (system prompt, name, role, description, each recommended capability, and all capabilities at once), all ticked by default, and Apply SHALL be disabled when nothing is ticked. Wherever the form offers reasoning, the capabilities column SHALL always propose it first, ticked by default and counted in the column's select-all, even when no capability is recommended. Applying SHALL write only the ticked items; ticked capabilities SHALL replace the selection with those the team may enable, keeping the reasoning setting; ticked reasoning SHALL turn reasoning on as the form's reasoning switch does (new conversations start in it when reasoning was off), a recommended `document_access` SHALL turn on both document sources (attachments and team documents), and unticked reasoning SHALL leave the reasoning settings unchanged. Turning reasoning on SHALL NOT require an overwrite confirmation. When a ticked item would replace a non-empty, different value in the form, the user SHALL confirm in a critical confirmation listing what will be replaced; cancelling SHALL return to the review unchanged. Nothing SHALL be saved until the user saves the agent.

#### Scenario: No template yet

- **WHEN** the user has not chosen a template
- **THEN** the Assistant button is not shown

#### Scenario: Apply into an empty form

- **WHEN** the user applies a draft recommending one capability the team may enable and one it may not, into a form whose name, role, description and prompt are empty
- **THEN** no confirmation is shown, the fields hold the draft, only the first capability is selected, reasoning is turned on with conversations starting in it, and the agent is not saved

#### Scenario: Reasoning always proposed

- **WHEN** the form offers reasoning and the draft recommends no capability
- **THEN** the capabilities column holds a ticked reasoning tile and its header can select or clear it, and no "no capability recommended" hint is shown

#### Scenario: Reasoning unticked

- **WHEN** the user unticks reasoning and applies
- **THEN** the form's reasoning settings are unchanged

#### Scenario: Only ticked items

- **WHEN** the user unticks the name and the capabilities and applies
- **THEN** the name and the capability selection are unchanged and the other ticked items are written

#### Scenario: Overwrite confirmation

- **WHEN** the form already has a different name and the name is ticked
- **THEN** Apply opens a confirmation listing the name; confirming applies the draft, cancelling returns to the review and changes nothing

#### Scenario: Escape in the dialog

- **WHEN** the user presses Escape while the creation assistant dialog is open
- **THEN** the dialog closes and the agent form stays open with its input

### Requirement: Admins can override the creation assistant's instructions

Holders of `can_edit_platform_prompt` SHALL be able to read, override and reset the creation assistant's meta-prompt through `/control-plane/v1/admin/platform/creation-assistant`. The read SHALL return the text in force and the pod's built-in default. An override SHALL be non-blank, at most 20,000 characters and free of reserved prompt tags; a missing `{language}` placeholder SHALL be accepted and flagged. Every draft SHALL use the saved override. The pod SHALL read the saved settings from the control plane with the caller's credentials, on a route requiring `team.can_update_agents`, and SHALL never take a meta-prompt or a model profile from a request body, whoever sends it. Because that route answers every team editor, team editors SHALL be able to read the meta-prompt override and the chosen model id: the override is instructions, not a secret, and admins must not put confidential notes in it. When the settings cannot be read, the pod SHALL use its defaults and log a warning without content. Without an override, the pod's built-in meta-prompt SHALL apply.

#### Scenario: Override used

- **WHEN** an admin saves an override and a team editor then requests a draft
- **THEN** the pod's system message is the override with `{language}` replaced by the request language

#### Scenario: Client cannot inject

- **WHEN** a draft request body, sent to the control plane or directly to the pod, contains `creation_assistant_prompt` or `model_profile_id`
- **THEN** those values are ignored and the draft uses the stored settings, or the pod defaults when nothing is saved

#### Scenario: Settings unreadable

- **WHEN** the pod cannot read the settings from the control plane
- **THEN** the draft uses the pod's built-in meta-prompt and default model, and the log line names only the error type

#### Scenario: Missing placeholder

- **WHEN** an admin saves a text without `{language}`
- **THEN** the save succeeds, the response flags `missing_language_placeholder` and the admin page shows a warning

#### Scenario: Reset

- **WHEN** an admin resets the override
- **THEN** the stored meta-prompt is cleared, the chosen model is kept, and the read reports the pod default with `is_default` true

#### Scenario: Not a prompt editor

- **WHEN** a user without `can_edit_platform_prompt` calls any of the three routes
- **THEN** the request is refused

### Requirement: Admins are told when the built-in instructions change after their override

The pod SHALL report the date its built-in meta-prompt was last revised on `/agents/platform-prompt` (`creation_assistant_prompt_revised_at`), and a test SHALL fail when the built-in text changes without that date. The admin read SHALL return that date as `default_revised_at` and SHALL set `default_changed_since_override` only when an override is saved and the revision date is later than the override's `updated_at` date. The admin page SHALL show a non-blocking warning with a way to read the built-in text, and SHALL store no acknowledgement: saving again or resetting clears the warning. No new storage SHALL be added.

#### Scenario: Default revised after the override

- **WHEN** an override was saved on 2026-10-01 and the pod reports a revision on 2026-10-09
- **THEN** the read returns `default_changed_since_override` true and the admin page shows the warning with a **View default** button revealing the built-in text read-only

#### Scenario: Same day or older revision

- **WHEN** the revision date is on or before the override's `updated_at` date, no override is saved, or the pod omits the date
- **THEN** `default_changed_since_override` is false and no warning is shown

#### Scenario: Saved again

- **WHEN** the admin saves the override again after the warning appeared
- **THEN** the override's `updated_at` moves past the revision date and the warning is gone

#### Scenario: Model-only change

- **WHEN** the admin changes only the model after the warning appeared
- **THEN** `updated_at` and `updated_by` are unchanged and the warning stays

### Requirement: Admins choose the creation assistant's model

The admin read SHALL return the chosen `model_profile_id` (or `null` for the platform default) and the chat profiles it may be set to: those every enabled pod advertises, each with its catalog name. A write SHALL refuse a profile outside that set with 422, unless it is the profile already stored. The choice SHALL only select the model the creation assistant calls; the created agent's model SHALL stay the one model routing gives it.

#### Scenario: Model chosen

- **WHEN** an admin chooses chat profile P and a team editor then requests a draft
- **THEN** the pod builds P at the admin's reasoning effort as P allows it, and the KPI events carry P's model name

#### Scenario: Unknown profile on save

- **WHEN** an admin saves a profile no pod advertises
- **THEN** the request is refused with 422 and nothing is stored

#### Scenario: Stored profile left the catalog

- **WHEN** the stored profile is no longer advertised, or no pod answers, and the admin saves a new meta-prompt with the same profile
- **THEN** the save succeeds

#### Scenario: Profile removed later

- **WHEN** the chosen profile is no longer in a pod's catalog at draft time
- **THEN** the pod uses its default chat model and logs a warning

#### Scenario: Agent model untouched

- **WHEN** a user applies a draft
- **THEN** no model setting of the agent is changed

### Requirement: Admins choose the creation assistant's reasoning effort

The admin settings SHALL carry `reasoning_effort`, one of `off`, `low`, `medium`, `high`, `off` by default and kept on reset; a write SHALL refuse any other value with 422 and SHALL NOT check it against the model. Each model option SHALL report `supports_reasoning` and its selectable `reasoning_efforts`: the levels its catalog profile declares when two or more, else none; `supports_reasoning` SHALL be false for a thinking profile with no level the pod can send (no selectable levels, no single declared level and no own `reasoning_effort`). The pod SHALL apply the effort to the creation assistant's call only, independently of the per-model reasoning toggle used for agent chat: `off` or a profile without `supports_thinking` strips reasoning; a profile with selectable levels gets the nearest declared level, ties going to the stronger; any other thinking profile sends, for every non-`off` value, its own `reasoning_effort`, else its single declared level, and does not reason when it has neither. A reasoning call still running 23 s after it started SHALL be hedged: the same call without reasoning SHALL start beside it, the first usable draft SHALL be returned and the other call cancelled; a reasoning call that answers unusably or is refused before then SHALL start the call without reasoning at once. The call without reasoning SHALL NOT start when less than 12 s remain before the deadline; the reasoning call is then awaited alone, or its failure answered. Both calls SHALL stay within the same deadline, which cancels any call still running, and the tokens of every answered call SHALL be counted. A catalog profile's `reasoning_efforts` SHALL require `supports_thinking`, hold only `low`, `medium` or `high`, and include the profile's own `reasoning_effort` when set, or the pod SHALL refuse to boot.

#### Scenario: Default off

- **WHEN** no setting is stored, the control plane omits the field, or the pod cannot read the settings
- **THEN** the pod builds the model without any reasoning setting and the admin control shows reasoning off

#### Scenario: Level clamped to the profile

- **WHEN** the stored effort is `medium` and the chosen profile declares `[low, high]`
- **THEN** the pod sends `high` for this call and the catalog config is unchanged

#### Scenario: On/off profile

- **WHEN** the stored effort is `low` and the chosen profile declares no levels with `reasoning_effort: high`
- **THEN** the pod sends `high`

#### Scenario: Single declared level

- **WHEN** the stored effort is `low` and the chosen profile declares `reasoning_efforts: [high]` without its own `reasoning_effort`
- **THEN** the pod sends `high`

#### Scenario: Thinking profile with nothing to send

- **WHEN** the chosen profile declares `supports_thinking` with neither declared levels nor its own `reasoning_effort`
- **THEN** its model option reports `supports_reasoning: false`, the admin sees the disabled switch, and the pod builds the model without any reasoning setting and no fallback model for any stored effort

#### Scenario: Stored effort kept when the control is unknown

- **WHEN** the pods disagree on the default chat profile, the platform default is selected with `high` stored, and the admin saves only a text change
- **THEN** the saved effort is still `high`

#### Scenario: Off

- **WHEN** the stored effort is `off`
- **THEN** the pod builds the model without any reasoning setting and no fallback model

#### Scenario: Admin control follows the model

- **WHEN** the selected option offers two or more levels, only on/off, or no reasoning
- **THEN** the admin sees a button group of Off and those levels, the reasoning switch, or a disabled switch with a tooltip, respectively

#### Scenario: Value normalised on a model change

- **WHEN** the admin moves from a levelled model set to `high` to an on/off model and saves
- **THEN** the saved effort is `medium`

#### Scenario: Unknown effort refused

- **WHEN** an admin saves an effort outside `off`, `low`, `medium`, `high`
- **THEN** the request is refused with 422

#### Scenario: Reasoning-only save

- **WHEN** an admin changes only the effort
- **THEN** it is stored and `updated_at` / `updated_by` are unchanged

#### Scenario: Catalog levels invalid

- **WHEN** a catalog profile declares `reasoning_efforts` without `supports_thinking`, with an unknown level, or without its own `reasoning_effort` among the declared levels
- **THEN** the pod fails to load the catalog

#### Scenario: Reasoning answer unusable

- **WHEN** the reasoning call's answer cannot be parsed, or its request is refused
- **THEN** the same structured call runs once without reasoning, the log carries only the error type, and the KPI counts both calls' tokens

#### Scenario: Reasoning call returns an empty prompt

- **WHEN** the reasoning call returns a draft whose prompt is empty or holds only reserved tags
- **THEN** it does not win: the call without reasoning starts at once and its draft is returned; when both return such a prompt the user receives 502

#### Scenario: Reasoning answers before the hedge

- **WHEN** the reasoning call returns a usable draft within 23 s
- **THEN** no call without reasoning is made and the log carries `calls=1 hedged=false winner=reasoning`

#### Scenario: Reasoning too slow

- **WHEN** the reasoning call is still running after 23 s
- **THEN** the call without reasoning starts beside it, the first usable draft is returned, the other call is cancelled, and the log and KPI carry `calls=2 hedged=true` and the winner

#### Scenario: One hedged call fails

- **WHEN** after the hedge one call fails and the other later returns a usable draft
- **THEN** that draft is returned and both calls' tokens are counted; when both fail the user gets 502

#### Scenario: Deadline during the hedge

- **WHEN** neither call answers before the deadline
- **THEN** both are cancelled, the user gets 504 and the event is emitted with status `timeout` and no token quantities

#### Scenario: Too little time left for the call without reasoning

- **WHEN** the hedge time is reached, or the reasoning call fails retryably, with less than 12 s left before the deadline
- **THEN** no call without reasoning starts: the reasoning call is awaited alone until the deadline, or its failure answers 502, and the log carries `calls=1 hedged=false`

#### Scenario: Provider error

- **WHEN** the reasoning call fails with an authentication, quota or network error
- **THEN** it is not retried and the user gets 502
