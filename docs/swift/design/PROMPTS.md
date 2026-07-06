# Prompt System

**Status:** Current as-built design (consolidated 2026-07-06)

**Covers:** `PROMPT-01`, `PROMPT-02`, `PROMPT-03`, `PROMPT-05`, `PROMPT-08`

**Forward work:** [`PROMPT-SYSTEM-HARDENING-RFC.md`](../rfc/PROMPT-SYSTEM-HARDENING-RFC.md)

This document is the stable prompt-system design record for Swift. It replaces
the previous prompt RFC stack and records what is shipped, not what was proposed
on the way there.

## 1. Product Model

Swift has three prompt surfaces:

- inline agent tuning prompts stored in `tuning_field_values["prompts.*"]`
- first-class prompt-library records stored in the control plane
- chat-context prompts attached to a session and resolved before execution

The prompt library is separate from managed agent instances. Importing a library
prompt into an agent is copy-by-value: the prompt text is copied into the target
`prompts.*` tuning field. Agent execution does not hold a live pointer to a
library prompt row.

## 2. Prompt Template Safety

Runtime prompt rendering is handled by
`fred_runtime.react.react_prompting.render_prompt_template`, reused by ReAct and
Deep runtimes. The renderer substitutes only simple `{identifier}` tokens from
the canonical registry in `fred_sdk.contracts.prompt_utils.PROMPT_SAFE_TOKENS`.

Supported user-authored tokens are:

| Token | Meaning |
| --- | --- |
| `{today}` | ISO-8601 date at execution time |
| `{response_language}` | Human-readable response language |
| `{session_id}` | Active session identifier |
| `{user_id}` | Authenticated user identifier |
| `{agent_id}` | Agent definition identifier |

Persistence-time validation rejects unknown simple tokens such as `{name}` with
HTTP 422 before writing the agent or prompt-library record. Non-simple brace
patterns such as `{}`, `{0}`, `{object.attr}`, and code blocks containing braces
are preserved as literals by the renderer and are not rejected by the current
validator.

Validation applies to:

- managed-agent create/update for field specs with `type == "prompt"`
- prompt-library create/update

Atomic agent creation follows from that validation: a bad prompt tuning value is
rejected before the agent instance row is created.

## 3. Prompt Library

Stored prompts use the `prompt` table and `PromptRow` ORM model.

Core fields:

- `prompt_id`, `team_id`, `name`, `description`, `text`, `created_by`
- `category`, `emoji`, `tags`
- `version`, `import_count`, `session_count`, `score`
- `avg_input_tokens`, `avg_output_tokens`
- `created_at`, `updated_at`

Prompt names are unique within one stored `team_id`. Updates replace the record
and increment `version`.

The main API surface is:

- `POST /control-plane/v1/teams/{team_id}/prompts`
- `GET /control-plane/v1/teams/{team_id}/prompts`
- `GET /control-plane/v1/teams/{team_id}/prompts/{prompt_id}`
- `PUT /control-plane/v1/teams/{team_id}/prompts/{prompt_id}`
- `DELETE /control-plane/v1/teams/{team_id}/prompts/{prompt_id}`
- `PATCH /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/score`
- `POST /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/promote`
- `POST /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/use`

Platform default prompts are in-memory `DefaultPromptSpec` records, not rows in
the `prompt` table. They appear as synthetic ids such as `default:technical` and
track use through `default_prompt_usage`.

## 4. Scope And Access

The public route family remains team-shaped, including the personal library:

- `/teams/personal/prompts`
- `/teams/{team_id}/prompts`

The personal route resolves through the caller-specific personal team id. Shared
team prompts resolve through the active team id. The store exposes raw
`get(prompt_id)` for internal use, but auth-sensitive routes use team-scoped
lookups such as `get_for_team(prompt_id, team_id)` or service-level resolution
that includes the caller's personal team id.

Team membership checks are performed by the product API before prompt service
operations run. Personal prompt isolation depends on the resolved personal team
identity, not on a global shared `personal` row namespace.

Promotion is copy-by-value from source team to target team and returns a new
prompt row. Name conflicts in the target team return HTTP 409.

## 5. Chat Context Prompts

A session may attach zero, one, or many prompts as ordered chat context. This is
persisted in the `session_context_prompts` association table:

| Column | Meaning |
| --- | --- |
| `session_id` | Session metadata id |
| `prompt_id` | Library prompt id or synthetic `default:{category}` id |
| `position` | Prompt order in the conversation context |

`UpdateSessionRequest.context_prompt_ids` is a full ordered replacement set:

- omitted field: leave attached prompts unchanged
- present `null` or `[]`: clear all attached prompts
- present list: replace the ordered set

`SessionListItem.context_prompt_ids` rehydrates the composer chips on session
open.

Before runtime execution, the frontend calls prepare-execution with `session_id`.
Control-plane resolves each attached prompt id in order, skips deleted, unknown,
or out-of-scope ids, joins the surviving prompt texts with `\n\n`, and returns the
existing scalar field `ExecutionPreparation.context_prompt_text`. The frontend
forwards that scalar into `RuntimeContext.context_prompt_text`; the runtime
contract does not know about the ordered prompt list.

Library-prompt resolution is scoped to the caller's authorized teams — the active
team plus the caller's personal team (`PromptStore.get_for_team`), matching the
union the context picker surfaces (§6). A session cannot resolve a prompt owned by
an unrelated team by id.

At execution the runtime folds `context_prompt_text` into the final system prompt.
`fred_runtime.react.react_prompting.compose_system_prompt` is the single composer
shared by the ReAct and Deep runtimes; it appends `build_context_prompt_suffix`
after the guardrail and global-base output contract, so a selected prompt such as
"respond in Spanish" reaches the model but stays subordinate to the agent's
guardrails. The suffix is rendered through the same safe token renderer as agent
templates (`render_prompt_template`), so a library prompt may use the validated
`PROMPT_SAFE_TOKENS` (`{today}`, `{response_language}`, …). Before `PROMPT-08` the
scalar reached the agent binding but no runtime appended it, so selected prompts
had no effect (issue #1915).

Default prompt text is localized by the `lang` query parameter on both
`/prompts/context` and `/prepare-execution`; stored library prompts are
language-agnostic.

Usage counters increment on first attach only:

- DB prompts increment `PromptRow.session_count`
- defaults increment `default_prompt_usage`

## 6. Frontend Surfaces

The shipped prompt UI has two parts:

- `PromptsPage`: basic prompt-library CRUD
- chat composer prompt picker: `SearchConfig` opens `ContextPromptPicker`, and
  selected prompts render as removable `ContextPromptChips`

The context picker reads
`GET /control-plane/v1/teams/{team_id}/prompts/context`, which returns the
caller's personal prompts, current team prompts, and platform defaults. DB
prompts are ordered by usage, and defaults are appended.

Agent-form import/save/version-drift UX is not complete; it is tracked as
`PROMPT-04` in the hardening RFC.

## 7. Known Deferred Work

The current system intentionally leaves these items outside the shipped design:

- complete `AgentFormModal` prompt import, save-as-prompt, drift badges, and
  inline 422 rendering (`PROMPT-04`)
- global prompt marketplace (`PROMPT-06`)
- per-prompt token-cost KPI aggregation (`PROMPT-07`)
- stronger service invariants around raw prompt lookup for promotion and
  promotion metadata copy (chat-context resolution is now scope-aware — `PROMPT-08`)
- scope the session lookup in `prepare_execution` to the caller's team/user, not
  just `SessionMetadataStore.get(session_id)` by id — `PROMPT-08` scoped the prompt
  text, so a foreign session id can no longer leak prompt text, but the session
  fetch itself remains unscoped (pre-existing; hardening follow-up)
- optional UX improvements such as labeled delimiters and drag reorder for
  multi-prompt chat context

See [`PROMPT-SYSTEM-HARDENING-RFC.md`](../rfc/PROMPT-SYSTEM-HARDENING-RFC.md)
for the improvement proposal.
