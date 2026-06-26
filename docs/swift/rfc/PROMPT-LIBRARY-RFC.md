# RFC — Prompt Library & Multi-Prompt Chat Context (as-built)

**Status:** Implemented. Prompt safety (PROMPT-01), library backend CRUD (PROMPT-02),
library extension (PROMPT-03) and multi-prompt chat context (PROMPT-05) shipped
2026-06-19. PROMPT-04 (agent-form prompt CRUD UI) partial; PROMPT-06 (global
marketplace) and PROMPT-07 (per-prompt token KPI) deferred.
**Author:** Dimitri Tombroff
**Date:** 2026-05-07 → 2026-06-19 (consolidated)
**Area:** `control-plane-backend`, `frontend` — `fred-sdk` / `fred-runtime` unchanged
**Consolidates / supersedes:**
[`PROMPT-LIBRARY-RFC-ORIGINAL-DESIGN.md`](PROMPT-LIBRARY-RFC-ORIGINAL-DESIGN.md)
(original three-part design + Part 3 amendment) and
[`PROMPT-LIBRARY-TEAM-SCOPE-AMENDMENT-RFC.md`](PROMPT-LIBRARY-TEAM-SCOPE-AMENDMENT-RFC.md).
Both are retained as historical rationale; **this file is the authoritative
contract.** Frozen-surface details mirror
`docs/swift/design/CONTROL-PLANE-PRODUCT-CONTRACT.md` (§3.6, §13).

---

## 1. Problem

A system prompt was an inline string on an agent instance — no reuse, no curation,
no usage signal — and `str.format_map()` rendering crashed agents at turn-start on
ordinary brace patterns (e.g. VBA `{ ... }`). The chat composer also lost the
pre-migration ability to attach **several** reusable contexts to a conversation.

This RFC makes a prompt a first-class, team-scoped control-plane resource, renders
and validates it safely, and lets a conversation carry **0, 1, or many** library
prompts as cumulative, ordered chat context.

---

## 2. Prompt safety (PROMPT-01)

- **Rendering:** `_LiteralFriendlyDict` guards `str.format_map()` so unknown keys,
  empty fields, positional refs, and unbalanced braces render literally instead of
  raising. Applied wherever a stored prompt is rendered (`react_prompting.py`).
- **Save-time validation:** `prompts.*` tuning values and library `text` are
  validated for template safety at write time → `422` with an actionable message,
  not a mid-conversation crash.
- **Atomic create:** managed-agent creation validates before persisting, so a
  rejected prompt never leaves an unusable agent shell behind.

---

## 3. Prompt as a control-plane resource (PROMPT-02 / PROMPT-03)

**Design rule — resource and binding stay separate.** A `Prompt` is a product
resource with its own CRUD lifecycle. A managed agent stores prompt text **only**
as copied `prompts.*` tuning values plus an informational `prompt_refs`
back-reference — never a live link. Deleting a library prompt never breaks an agent
or an open conversation.

### 3.1 Data model — `PromptRow` (table `prompt`)

Core: `prompt_id` (PK), `team_id`, `name`, `description`, `category`, `emoji`,
`tags`, `text`, `created_by`, `created_at`, `updated_at`. Uniqueness: `(team_id, name)`.

| Field                                    | Meaning                                                       |
| ---------------------------------------- | ------------------------------------------------------------- |
| `version`                                | monotonic, +1 per PUT; no history table (current only)        |
| `import_count`                           | +1 each time imported into an agent instance                  |
| `session_count`                          | +1 on **first attach** to a session as chat context (§4.4)    |
| `score`                                  | explicit quality rating 0.0–5.0, team-curated; null = unrated |
| `avg_input_tokens` / `avg_output_tokens` | reserved nullable; populated by PROMPT-07                     |

Platform **defaults** are not rows: 9 in-memory `DefaultPromptSpec`s (localized
fr/en), with per-team usage tracked in `default_prompt_usage (team_id, category)`.

### 3.2 Scope & ownership (folds the team-scope amendment)

Route family is unchanged — `/teams/personal/prompts` and `/teams/{team_id}/prompts`;
there is no `/users/{id}/prompts`. Logical identity (locked):

- **personal** → `personal/{caller_user_id}`; names unique per `(owner_user_id, name)`;
  visible and mutable only by the owner.
- **team** → `team/{team_id}`; names unique per `(team_id, name)`; **read** = any
  member, **write** (create/update/delete/`score`) = team **manager or owner** only
  (curated team resource, not generic membership writes).

Auth-sensitive resolution must always filter by logical scope (owner for personal,
team for team) — a raw `get(prompt_id)` is never sufficient. This applies to CRUD,
the context picker, session-context resolution, promotion, score, and import.

### 3.3 Agent import — `prompt_refs`

Importing copies the prompt text into the matching `prompts.*` field and writes a
metadata-only back-reference (`prompt_id`, `version`, `scope_kind`, `team_id`,
and `owner_user_id` for personal sources). Import increments `import_count`; manually
overwriting a field clears its ref. When the live version outranks the stored ref,
`AgentFormModal` shows a non-blocking "update available" banner.

### 3.4 Promotion (PROMPT-06 is the marketplace; promote ships now)

`POST /teams/{team_id}/prompts/{id}/promote { target_team_id }` — **copy-by-value**;
the destination starts fresh (`version=1`, counters 0, `score=null`); `409` on name
clash. Caller must be manager/owner of both source and target.

### 3.5 Endpoints (prompt library)

```
GET   /teams/{team_id}/prompts                 → list[PromptSummary]   (+defaults)
POST  /teams/{team_id}/prompts                 → 201 PromptSummary
GET   /teams/{team_id}/prompts/{id}            → PromptDetail
PUT   /teams/{team_id}/prompts/{id}            → PromptSummary          (version +1)
DELETE/teams/{team_id}/prompts/{id}            → 204
PATCH /teams/{team_id}/prompts/{id}            → PromptSummary          (score only)
POST  /teams/{team_id}/prompts/{id}/promote    → 201 PromptSummary
POST  /teams/{team_id}/prompts/{id}/use        → 204                    (usage bump)
GET   /teams/{team_id}/prompts/context         → list[ContextPromptSummary]  (§4.5)
```

---

## 4. Multi-prompt chat context (PROMPT-05) — as-built

A conversation may have **0, 1, or many** prompts attached, cumulative and ordered,
persisted with the session and sourced from the personal + team library + defaults.
**Control-plane + frontend only — the runtime execution contract is untouched.**

### 4.1 Persistence — ordered association

The scalar `session_metadata.context_prompt_id` is replaced by an ordered table
(Alembic `e7f8a9b0c1d2`, backfills each scalar as `position=0`, drops the column):

```
session_context_prompts
  session_id   FK → session_metadata.session_id  ON DELETE CASCADE
  prompt_id    str   -- prompt UUID, or "default:{category}"
  position     int   -- 0-based; selection + concatenation order
  PRIMARY KEY (session_id, prompt_id)
```

`prompt_id` is intentionally not an FK so a deleted prompt never breaks a
conversation. The association is also removed explicitly on session delete (SQLite
does not enforce the FK cascade).

### 4.2 API contract

```
PATCH /teams/{team_id}/sessions/{session_id}
  body: context_prompt_ids: list[str] | null   -- full ordered replacement set
GET   …/sessions/{session_id}  /  …/sessions    -- SessionListItem.context_prompt_ids: list[str]
```

**Full-set replacement** (idempotent): the server diffs against the current set —
detaches removed ids, attaches new ones, rewrites `position` from payload order, and
de-duplicates while preserving order. Semantics for the field:

| Body                                       | Effect                        |
| ------------------------------------------ | ----------------------------- |
| `context_prompt_ids: [a, b]`               | replace set, order = `[a, b]` |
| `context_prompt_ids: []` or present `null` | **clear**                     |
| field **absent**                           | **leave unchanged**           |

The "absent = unchanged / present-null = clear" distinction (via Pydantic
`model_fields_set`) is required because the same endpoint serves per-turn
freshness PATCHes (`{updated_at}`), which must not wipe attached prompts. Unknown /
deleted ids are skipped at resolution, never `422` — a stale shared prompt never
breaks an open conversation.

### 4.3 Execution resolution — concatenate into one runtime field

At `prepare_execution(session_id=…)` the control-plane loads the attached ids in
`position` order, resolves each to current text (library via `PromptStore`,
`default:{category}` via the in-memory specs), skips unresolved ids, and concatenates
into the **existing scalar** `ExecutionPreparation.context_prompt_text` with `\n\n`:

```
context_prompt_text = "\n\n".join(resolved_texts) or None
```

Concatenation is control-plane-side, so `RuntimeContext.context_prompt_text` stays a
scalar. The runtime must preserve that scalar when rebuilding `RuntimeContext`; VALID-02
caught and fixed the earlier drop in `fred-runtime`. **The frontend must pass
`session_id` to `prepare-execution`** for this to resolve, then forward the returned
`context_prompt_text` in the per-turn runtime context. The dead
`RuntimeContext.selected_chat_context_ids` field stays unused (separate cleanup). No
per-prompt delimiter/label in V1.

### 4.4 Usage counters

`session_count` (or `default_prompt_usage` for defaults) increments on **first
attach only** — ids present in the new set but absent from the previous set.
Re-sending an attached id does not double-count; removing never decrements.

### 4.5 Context-picker endpoint

```
GET /teams/{team_id}/prompts/context → list[ContextPromptSummary]
```

Returns the **union** of the caller's personal prompts + team `{team_id}` prompts +
the 9 platform defaults, ordered `session_count DESC, name ASC` (defaults appended).
If `team_id == personal`, only the caller's personal prompts (+ defaults). Each item
carries a `scope` (`personal` / `team` / `default`) separator and a `category`
(see §6). Read-only.

```python
class ContextPromptSummary(BaseModel):
    id: str; name: str; description: str | None
    scope: Literal["personal", "team", "default"]
    category: PromptCategory | None        # as-built (§6)
    version: int; session_count: int; score: float | None
    text: str | None                       # populated for defaults only
```

### 4.6 Frontend (composer)

- **Selection** — a `Prompts` row in the composer options panel (`+` →
  `ComposerActionsMenu` → `SearchConfig`), always shown, with an active-count value,
  opening a multi-select **`ContextPromptPicker`**: scope-grouped
  (personal / team / suggested), category icon + colour from `promptCategories.ts`,
  score stars, usage count.
- **Active state** — attached prompts render as removable **`ContextPromptChips`**
  in the composer `aboveTextSlot` (beside attachment chips); zero attached → no
  chrome.
- **Persistence & hydration** — every change `PATCH`es the full
  `context_prompt_ids`; on session open `SessionListItem.context_prompt_ids`
  rehydrates the pills (survives reload). A brand-new conversation lazily creates its
  session before the first PATCH.

---

## 5. As-built deltas vs. the original design

| Delta                                                                    | Why                                                                                                                                   |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| `ContextPromptSummary.category` added (backend + union query + defaults) | pills/picker need the design-system category icon + colour (§4.6)                                                                     |
| `prepare-execution` now receives `session_id` from `useChatSse`          | the resolution chain (§4.3) was otherwise dead — `context_prompt_text` stayed null                                                    |
| PATCH "absent = unchanged / present-null = clear" via `model_fields_set` | refines the RFC's literal "null clears" so freshness-only PATCHes don't wipe context                                                  |
| `Prompts` row always shown (not gated by `effective_chat_options`)       | prompts are universal (personal + team + defaults); no per-agent flag exists                                                          |
| Picker is a compact scope-grouped **list**, not the `PromptCard` grid    | adapts the original "reuse PromptCard in multi-select" to the narrow composer popover; `PromptCard` remains the `PromptsPage` surface |

---

## 6. Contracts touched

| Surface                                    | Change                                                |
| ------------------------------------------ | ----------------------------------------------------- |
| `session_context_prompts` table            | new ordered association (Alembic `e7f8a9b0c1d2`)      |
| `session_metadata.context_prompt_id`       | dropped (backfilled into the association)             |
| `UpdateSessionRequest` / `SessionListItem` | `context_prompt_id` → `context_prompt_ids: list[str]` |
| `ContextPromptSummary`                     | `+ category`                                          |
| `ExecutionPreparation.context_prompt_text` | unchanged scalar; now a `\n\n` concatenation          |
| `RuntimeContext` (`fred-sdk`)              | existing scalar field reused                          |
| `fred-runtime` RuntimeContext rebuild      | preserves `context_prompt_text` after VALID-02        |
| `controlPlaneOpenApi.ts`                   | regenerated                                           |
| `CONTROL-PLANE-PRODUCT-CONTRACT.md`        | §3.5.4 + dated §13                                    |

---

## 7. Non-goals / deferred

- Live prompt binding into agents (import stays copy-by-value).
- Per-prompt ACLs beyond personal-vs-team scope.
- Global marketplace implementation (PROMPT-06).
- Per-prompt token-cost KPI (PROMPT-07; fields reserved nullable now).
- Per-prompt labeled delimiters in the concatenated context, and drag-to-reorder
  pills (V1 order = selection order).
