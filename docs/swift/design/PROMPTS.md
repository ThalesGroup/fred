# Prompt System

**Status:** Current as-built design (consolidated 2026-07-06, updated 2026-07-30 for PROMPT-09)

**Covers:** `PROMPT-01`, `PROMPT-02`, `PROMPT-03`, `PROMPT-05`, `PROMPT-08`, `PROMPT-09`

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

Any `{…}` the renderer does not recognize is left exactly as written. That covers
unknown simple tokens such as `{name}`, and equally non-simple patterns such as
`{}`, `{0}`, `{object.attr}`, JSON, and code blocks containing braces. The
renderer never raises: substitution falls back to the matched text.

**There is no persistence-time validation of prompt tokens** (#2277). Prompt text
is stored verbatim on managed-agent create/update (`type == "prompt"` field specs)
and on prompt-library create/update.

Rejecting unknown tokens with HTTP 422 was removed because it was a false
positive — the renderer already handled those prompts correctly, so the check only
blocked authors from writing legitimate text such as `Hello {name}`, with no
in-product documentation or UI hint to explain the rule. The accepted trade-off is
that a typo (`{todya}` for `{today}`) now reaches the prompt as literal text
instead of being caught on write; that failure is visible to the author in the
agent's output.

`PROMPT_SAFE_TOKENS` remains the single source of truth for the renderer, and is
the intended source for a prompt-editor UI hint that would make the feature
discoverable.

## 3. Prompt Library

Stored prompts use the `prompt` table and `PromptRow` ORM model.

Core fields:

- `prompt_id`, `team_id`, `name`, `description`, `text`, `created_by`
- `category_id`, `emoji`, `tags`
- `version`, `published`, `import_count`, `session_count`, `score`
- `avg_input_tokens`, `avg_output_tokens`
- `created_at`, `updated_at`

Prompt names are unique within one stored `team_id`. Updates replace the record
and increment `version`. `published` (default `false`) is the prompts-marketplace
visibility flag — see §6.

The main API surface is:

- `POST /control-plane/v1/teams/{team_id}/prompts`
- `GET /control-plane/v1/teams/{team_id}/prompts`
- `GET /control-plane/v1/teams/{team_id}/prompts/{prompt_id}`
- `PUT /control-plane/v1/teams/{team_id}/prompts/{prompt_id}`
- `DELETE /control-plane/v1/teams/{team_id}/prompts/{prompt_id}`
- `PATCH /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/score`
- `POST /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/promote`
- `POST /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/use`
- `POST /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/publish`
- `POST /control-plane/v1/teams/{team_id}/prompts/{prompt_id}/unpublish`

**There is no platform default-prompt catalog (PROMPT-09).** Every prompt is a
real row in the `prompt` table, owned and fully editable by its team. New teams
are seeded with a 4-category / 4-prompt starter kit at creation time
(`_seed_starter_kit`, best-effort — a seeding failure never fails team
creation); personal spaces, being virtual, are seeded lazily on first access
instead (`_ensure_personal_starter_kit`, #2410 — only a library with zero
prompts *and* zero categories). From that point on the starter kit is ordinary
team content.

### 3.1 Prompt categories

Categories are team-owned content, not a shared taxonomy: table
`prompt_category` (`category_id`, `team_id`, `name`), one set per team,
created/renamed/deleted by that team's `team_editor`s. `prompt.category_id` is
a nullable reference into this table, scoped to the same team.

- `GET /control-plane/v1/teams/{team_id}/prompt-categories`
- `POST /control-plane/v1/teams/{team_id}/prompt-categories`
- `PUT /control-plane/v1/teams/{team_id}/prompt-categories/{category_id}`
- `DELETE /control-plane/v1/teams/{team_id}/prompt-categories/{category_id}`
  — returns 409 while ≥1 prompt in the team still references the category
  (hard block, never an automatic reassignment)

No icon/color field: category pills use the same hash-based fallback palette
already used for uncategorized prompts (`hashColorIndex`, frontend).

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
| `prompt_id` | Library prompt id |
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
team plus the caller's personal team (`PromptStore.get_for_team`). This is wider
than what the context picker surfaces (§6): the picker no longer offers personal
prompts in a team space, but an already-attached personal prompt keeps resolving.
A session cannot resolve a prompt owned by an unrelated team by id.

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

Library prompts are stored verbatim (language-agnostic) — neither
`/prompts/context` nor `/prepare-execution` take a `lang` query parameter
(PROMPT-09 removed it along with the default-prompt catalog it used to
localize).

Usage counters increment on first attach only, via `PromptRow.session_count` —
uniformly for every prompt, since there is no separate default-prompt counter
table anymore.

## 6. Frontend Surfaces

The shipped prompt UI has two parts:

- `PromptsPage`: prompt-library CRUD, plus category management
  (`ManageCategoriesDialog`: Créer/Éditer/Supprimer)
- chat composer prompt picker: `SearchConfig` opens `ContextPromptPicker`, and
  selected prompts render as removable `ContextPromptChips`

The context picker reads
`GET /control-plane/v1/teams/{team_id}/prompts/context`, which returns only
the space's own prompts (no platform defaults — PROMPT-09). Personal prompts
appear only in the personal space — a team context never exposes the caller's
personal prompts (changed 2026-07-20, #2023; previously the endpoint returned
the union). Prompts are ordered by usage.

Agent-form import/save/version-drift UX is not complete; it is tracked as
`PROMPT-04` in the hardening RFC.

The prompts marketplace (§6.1) adds a `MarketplacePrompts` page ("Prompts de la
communauté"), reached from a nav item under the teams marketplace, plus a
marketplace variant of the shared `PromptCard`.

### 6.1 Prompts marketplace (PROMPT-06)

Shipped 2026-08-10 (#2317). The marketplace lets a team publish its best prompts
to the whole community, where anyone can use (copy) or import them.

**Live-mirror model, not a snapshot.** Publishing sets a boolean `published`
flag on the team's own `PromptRow` — the marketplace shows that same live
record. Editing a published prompt propagates immediately, and the
`session_count` usage counter is shared between origin-team usage and external
usage (it reflects total, global usage). This intentionally diverges from the
original `PROMPT-06` sketch, which proposed a frozen published snapshot: a
snapshot was unnecessary here because nothing persistently references the
published row — **use = clipboard copy** (no pointer) and **import = copy-by-value**
(a fresh row via the `promote` primitive, with the counter reset to 0). Only
real team prompts are publishable; personal-space prompts stay private.

Endpoints:

- `POST /teams/{team_id}/prompts/{prompt_id}/publish` / `.../unpublish` — flip
  the flag; `can_update_resources` on the author team (personal-space prompt →
  400 on publish).
- `GET /control-plane/v1/marketplace/prompts` — every published prompt across
  all teams, most-used first, each with the author team's display name; any
  authenticated user (not team-scoped). Carries only `text_preview` — the
  listing payload stays small however many prompts are published.
- `GET /control-plane/v1/marketplace/prompts/{prompt_id}` — one published
  prompt's full text, fetched on demand when a card is opened (for the copy
  action); any authenticated user, published prompts only.
- `POST /control-plane/v1/marketplace/prompts/{prompt_id}/use` — increment the
  shared counter without requiring team membership (published prompts only).
- `POST /control-plane/v1/marketplace/prompts/{prompt_id}/import` — copy-by-value
  into every `target_team_ids` the caller can edit; targets are deduped and
  imported concurrently, each authorized independently (per-target
  `can_update_resources`, per-target result), and a name collision in a target
  team is avoided with an `_imported-N` suffix.

There is no moderation surface in v1; unpublish is available to editors of the
author team, including directly from the marketplace (UX convenience).

## 7. Known Deferred Work

The current system intentionally leaves these items outside the shipped design:

- complete `AgentFormModal` prompt import, save-as-prompt, drift badges, and
  inline 422 rendering (`PROMPT-04`)
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
