> **⚠️ Historical — superseded 2026-06-19.** This is the original three-part design
> record (safety → library extension → multi-prompt amendment). The authoritative,
> compact **as-built** contract is now [`PROMPT-LIBRARY-RFC.md`](PROMPT-LIBRARY-RFC.md).
> Retained only for full design rationale and alternatives-considered history; it is
> no longer the current contract.

# RFC — Safe Prompt Authoring, Validation, and Library

**Status**: Slices A + B + C implemented (2026-05-07) · Slice D backend implemented (2026-05-08) · PROMPT-03 in progress · Slice E / PROMPT-06 deferred · **PROMPT-05 revised from single to multi-prompt chat context (2026-06-19 — see Part 3)**  
**Author**: Dimitri Tombroff  
**Date**: 2026-05-07 (safety) — 2026-05-09 (library extension) — 2026-06-19 (multi-prompt chat context amendment)  
**Area**: `fred-sdk`, `fred-runtime`, `control-plane-backend`, `frontend`  
**Supersedes**: `PROMPT-SAFETY-RFC.md` (deleted — all content absorbed here)

---

## Part 1 — Safety: Rendering, Validation, and Atomic Creation (Slices A, B, C)

### 1. The problem

#### 1.1 The rendering crash

System prompt templates are rendered at execution time using Python's `str.format_map()`.
The `_LiteralFriendlyDict` guard handles one case — a simple unknown key:

```
{unknown_key}  →  __missing__("unknown_key")  →  literal "{unknown_key}"   ✓
```

But it does not protect against:

| Pattern in template       | What Python does                                                                | Result                                                 |
| ------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `{toto.toto}`             | resolves `dict['toto']` → returns `"{toto}"` (str), then accesses `.toto` on it | `AttributeError: 'str' object has no attribute 'toto'` |
| `{}`                      | empty field name                                                                | `ValueError: Single '}' encountered in format string`  |
| `function main() { ... }` | unbalanced brace, depending on surrounding chars                                | `ValueError`                                           |
| `{0}`                     | positional reference                                                            | accesses index 0 of the dict values — unexpected       |

All of these crash the agent silently at turn-start with no indication that the system prompt is the cause.

Real production incident (2026-05-06): a system prompt containing Excel VBA with curly braces (`function main(workbook: ExcelScript.Workbook) { ... }`) triggered:

```
AttributeError: 'str' object has no attribute 'toto'
  File "react_prompting.py", line 111, in render_prompt_template
      return template.format_map(
```

#### 1.2 No validation at save time

The control-plane `_validate_tuning_field_values` treats `"prompt"` fields as free-form strings — any text is stored unconditionally. Validation (and the crash) only surfaces when the user sends their first message.

#### 1.3 Poor creation UX

The `develop` (kea) flow creates an empty agent shell first and applies the system prompt in a second update call. If the prompt is rejected at step 2, the empty agent record already exists and must be manually deleted. Swift's atomic `CreateAgentInstanceRequest` avoids this, but without save-time validation the outcome is identical: the agent is created, the user cannot chat with it, and they have no actionable error message.

#### 1.4 No independent prompt management

A prompt lives only as an inline string inside an agent instance. There is no way to author a prompt separately, reuse it across agents, or maintain a team-scoped prompt library as a first-class control-plane object.

---

### 2. Design rule — prompt resources and agent bindings stay separate

- a `Prompt` is a control-plane product resource with its own CRUD lifecycle
- a managed agent instance stores prompt text only through its `prompts.*` tuning values
- importing a prompt into an agent is a **copy** operation, not a live binding
- publishing a team prompt to a global catalog is also a **copy** operation
- the personal prompt library reuses the reserved control-plane team `personal`; no parallel user-scoped prompt API is introduced

---

### 3. Slice A — Canonical token registry + safe rendering engine

#### A.1 Central token registry (`fred-sdk`)

`fred_sdk.contracts.prompt_utils` defines the canonical set of supported template tokens — the single source of truth imported by the renderer, the validator, and (eventually) the UI hint API.

```python
PROMPT_SAFE_TOKENS: dict[str, str] = {
    "today":             "ISO-8601 date at execution time (e.g. 2026-05-07)",
    "response_language": "Human-readable response language (e.g. English, français)",
    "session_id":        "Active session identifier",
    "user_id":           "Authenticated user identifier",
    "agent_id":          "Agent definition identifier",
}
```

Adding a new supported token requires editing exactly this dict — no other site needs to change.

> **TODO (UI, deferred):** Expose `PROMPT_SAFE_TOKENS` via a lightweight read-only endpoint (e.g. `GET /control-plane/v1/prompt-tokens`) so that the prompt textarea can show an inline "supported variables" hint panel. Until that endpoint exists, the frontend hard-codes the list. Tracked in BACKLOG as a UX improvement.

#### A.2 Safe rendering engine (`fred-runtime`)

Replace `str.format_map()` with a regex-based substitution that only rewrites tokens present in the merged token map and passes everything else through unchanged.

```
{today}              →  "2026-05-07"      (canonical token, substituted)
{response_language}  →  "English"         (canonical token, substituted)
{my_custom_var}      →  "{my_custom_var}" (not in map, preserved as literal)
{toto.toto}          →  "{toto.toto}"     (not a simple identifier, untouched)
{}                   →  "{}"              (not a simple identifier, untouched)
function() { ... }   →  "function() { ... }" (no brace pattern match, untouched)
```

```python
_SIMPLE_TOKEN_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')

def render_prompt_template(template: str, *, tokens: dict[str, str]) -> str:
    def _replace(m: re.Match) -> str:
        return tokens.get(m.group(1), m.group(0))
    return _SIMPLE_TOKEN_RE.sub(_replace, template)
```

The pattern `[a-zA-Z_][a-zA-Z0-9_]*` never matches `toto.toto`, `0`, or the empty string. Those pass through unchanged.

**Two-tier token map:**

| Surface                                              | Authored by           | Token set                             | Validated at persistence      |
| ---------------------------------------------------- | --------------------- | ------------------------------------- | ----------------------------- |
| `prompts.*` tuning value (UI form)                   | Team admin / end user | `PROMPT_SAFE_TOKENS` only             | Yes — strict (Slice B)        |
| `system_prompt_template` in Python `AgentDefinition` | Agent developer       | `PROMPT_SAFE_TOKENS` + runtime extras | No — developer responsibility |

**Scope**: `fred_runtime/react/react_prompting.py` (`render_prompt_template` + `_LiteralFriendlyDict` removed). Same change applies to `fred_runtime/deep/deep_runtime.py`.  
**No API contract change. No migration. No schema change.**

---

### 4. Slice B — Prompt template validation at persistence (`control-plane-backend`)

`validate_prompt_template(text: str) -> list[PromptTemplateError]` in `fred_sdk.contracts.prompt_utils`. Called by the control-plane service before storing any `prompts.*` field value.

```python
class PromptTemplateError(BaseModel):
    pattern: str          # the offending text fragment
    reason: str           # human-readable explanation
    token_hint: str | None = None  # set when a close-but-wrong token is detected
```

The validator runs two passes:

**Pass 1 — Non-simple brace patterns (always an error):**

| Found         | Error reason                                                   |
| ------------- | -------------------------------------------------------------- |
| `{}`          | "Empty placeholder — not a valid template token"               |
| `{0}`, `{1}`  | "Positional placeholder — not supported in prompt templates"   |
| `{toto.toto}` | "Dotted attribute syntax is not supported in prompt templates" |
| `{ space }`   | "Whitespace in placeholder — not a valid template token"       |

**Pass 2 — Unknown simple tokens:**

Any `{identifier}` not in `PROMPT_SAFE_TOKENS` is an error. The error message lists all supported tokens.

**Validation policy:**

| Situation                             | HTTP response                            |
| ------------------------------------- | ---------------------------------------- |
| Any non-simple brace pattern          | `422` with list of `PromptTemplateError` |
| Any unknown `{identifier}` token      | `422` with list of `PromptTemplateError` |
| Template contains no `{...}` patterns | `200` / `201`                            |
| Template uses only canonical tokens   | `200` / `201`                            |

No warnings, no partial acceptance. The error payload lists every offending pattern in one response.

**Where validation is called:**

- `_validate_tuning_field_values()` — when `field.type == "prompt"`
- Prompt library create/update (Slice D)

---

### 5. Slice C — Atomic creation guarantee

Swift already sends the full payload in a single `CreateAgentInstanceRequest`. With Slice B in place, validation runs before the INSERT — the agent is either created fully valid or not created at all.

**What this slice adds:**

- Explicit test coverage for the create-then-reject scenario (bad prompt → 422, no agent row written; fix prompt → 201, agent created).
- The structured error shape from Slice B is forwarded as-is from the 422 body:

```json
{
  "detail": "prompts.system contains invalid template patterns",
  "errors": [
    {
      "pattern": "{toto.toto}",
      "reason": "Dotted attribute syntax is not supported in prompt templates"
    },
    {
      "pattern": "{}",
      "reason": "Empty placeholder — not a valid template token"
    }
  ]
}
```

- The frontend `AgentFormModal` must surface these errors next to the prompt textarea, not as a generic toast. (UI implementation tracked as a TODO in `CHAT-UI-BACKLOG.md`.)

---

## Part 2 — Library Architecture (Slices D, E / PROMPT-03 through PROMPT-07)

### 6. Context — what Slice D established

`§Slice D` in the original safety RFC defined a minimal first-class prompt library:

- `PromptRow` scoped to a `team_id`
- CRUD endpoints `POST/GET/PUT/DELETE /teams/{id}/prompts`
- Import into agent = snapshot copy of text (no live reference)
- Personal prompts = reserved `personal` team (no separate user API)
- No versioning, no analytics, no cross-team visibility — explicitly deferred

Slice D backend was implemented by Codex (2026-05-08): `PromptRow`, `PromptStore`, Alembic migration, Pydantic schemas, API endpoints.

This part covers the follow-up: **versioning, analytics, personal→team visibility, chat context integration, and promotion flows.**

---

### 7. Extended problem

#### 7.1 No quality signal

Without versioning and usage analytics, the library is a flat list with no indication of which prompts are mature, how often they are used, or whether a given agent is running on an outdated prompt version.

#### 7.2 Personal prompts are invisible in team conversations

When a user opens a conversation with a team agent, she has no way to apply a personal prompt — the context picker only shows team prompts.

#### 7.3 Chat context is a free textarea

The current session init surface exposes a free textarea for conversation context (`AgentOptionsPanel` was retired 2026-05-24; context input is not yet surfaced in `ComposerSettingsControls`). Without curation or a quality signal, every user invents their own version of the same prompt.

#### 7.4 No token cost visibility

A prompt that produces short, precise answers is cheaper than a verbose one. Without token cost data per prompt, the team cannot evaluate efficiency changes.

#### 7.5 No path to influence the library

A team member who writes a good personal prompt has no mechanism to share it. The library can only grow via admin action.

---

### 8. Proposed Design

#### 8.1 Scope hierarchy

Three levels, strictly ordered. Promotion between levels is always **copy-by-value** — never a live link.

```
personal/{user_id}          team/{team_id}          marketplace
─────────────────          ──────────────          ───────────
Alice's private space  →   Shared team space  →    Global catalog
                 promote            promote
                 (copy)             (copy, PROMPT-06)
```

All three levels use the same `PromptRow` structure (scoped by `team_id`). The marketplace uses a separate `PublishedPromptRow` table — unchanged from §Slice E, deferred to PROMPT-06.

**Reserved team ids:**

- `personal` resolves to the calling user's personal team (existing control-plane convention)
- Named team ids resolve normally

#### 8.2 Data model — extended PromptRow

Extends the Codex-built `PromptRow` via a new Alembic migration:

```
PromptRow (additions to existing schema)
─────────────────────────────────────────────────────────────────────
version              int        NOT NULL  DEFAULT 1
                                Auto-incremented on every PUT.
                                Monotonic, never reused.
                                No history table — only current version stored.

import_count         int        NOT NULL  DEFAULT 0
                                Incremented each time this prompt is
                                imported into a managed agent instance.

session_count        int        NOT NULL  DEFAULT 0
                                Incremented each time a user selects
                                this prompt as their chat context for a session.

score                float      NULLABLE  DEFAULT NULL
                                Explicit quality rating, range 0.0–5.0.
                                Set by admin or by the evaluation track (EVAL-01).
                                NULL = not yet rated.

avg_input_tokens     int        NULLABLE  DEFAULT NULL
avg_output_tokens    int        NULLABLE  DEFAULT NULL
                                Average token counts per turn in conversations
                                where this prompt was active. Updated by
                                background aggregation — see §8.7. NULL = no data yet.
```

**Uniqueness constraint unchanged:** `(team_id, name)` unique within team.

#### 8.3 Agent integration — prompt_refs

The agent instance still stores a snapshot copy of the prompt text in `prompts.*` tuning values. We add a **metadata-only back-reference** alongside the snapshot: which library prompt was the source, and at which version. This reference is purely informational — deleting the library prompt does not break the agent (the text copy remains). There is no foreign key constraint.

```
ManagedAgentInstance
  prompt_refs:  jsonb | null   DEFAULT NULL

Shape:
{
  "prompts.system":   { "prompt_id": "abc-123", "version": 2 },
  "prompts.planning": { "prompt_id": "def-456", "version": 1 }
}
```

`prompt_refs` is written by the control-plane service when the admin imports a library prompt. It is cleared for a field when the admin overwrites that field manually.

**UI consequence:** when the current library version > stored ref version, `AgentFormModal` shows a non-blocking banner:

> _"prompts.system was imported from "Bid Expert v2" — current version is v5. [Review and update]"_

#### 8.4 Chat context integration — live reference at session level

> **Revised 2026-06-19 (Part 3).** The single `context_prompt_id` model below is
> superseded by a multi-prompt association (`0..N` prompts per session). Read this
> section for the original mono design and resolution flow, then **Part 3** for the
> authoritative multi-prompt contract. The resolution/concatenation and runtime
> wiring described here remain valid; only the cardinality changed.

Session context is ephemeral: a session ends, the reference is gone. A missing or deleted prompt at session start simply means no context is injected — the session continues normally.

```
Session (control-plane DB)
  context_prompt_id:  str | null   DEFAULT NULL
```

When a user selects a context from the library picker, `context_prompt_id` is stored on the session (via the existing `PATCH /sessions/{id}` endpoint — body extended with `context_prompt_id`).

At execution preparation time, control-plane resolves the prompt text:

```
ExecutionPreparation (response)
  context_prompt_text:  str | null
```

The runtime receives the current text of the referenced prompt and injects it as a conversation-level context. `PromptRow.session_count` is incremented when `context_prompt_id` is written to the session.

#### 8.5 Personal → team visibility in chat context picker

The chat context picker fetches from a new endpoint:

```
GET /control-plane/v1/teams/{team_id}/prompts/context
```

Returns the **union** of the calling user's `personal` prompts and `team_id` prompts. Ordered by `session_count DESC, name ASC`. Each item carries a `scope` field (`"personal"` or `"team"`) so the UI can render a visual separator.

```json
[
  {
    "id": "...",
    "name": "Analyse appel d'offres",
    "scope": "personal",
    "session_count": 12,
    "score": null
  },
  {
    "id": "...",
    "name": "Répondre en français",
    "scope": "team",
    "session_count": 48,
    "score": 4.5
  }
]
```

This endpoint is **read-only** — it does not mutate the underlying records.

#### 8.6 Promotion flows

All promotion flows are **copy-by-value**. The source prompt is never modified. The destination starts at `version=1`, `import_count=0`, `session_count=0`, `score=null`.

```
POST /control-plane/v1/teams/{team_id}/prompts/{id}/promote
Body: { "target_team_id": "bid-and-capture" }
```

Creates a new `PromptRow` in `target_team_id` with the same name, description, and text. Returns `409 Conflict` if the same name already exists in the target team.

**Authorization:** caller must be a member of both source and target team. Promotion to marketplace is a separate flow (PROMPT-06).

#### 8.7 Analytics model

Three tiers, implemented progressively.

**Tier 1 — Usage counters (in scope, PROMPT-03)**

| Field           | Source event                        | Updated by                              |
| --------------- | ----------------------------------- | --------------------------------------- |
| `import_count`  | Admin imports prompt into agent     | `service.py` — agent create/update path |
| `session_count` | User selects prompt as chat context | `service.py` — session PATCH path       |

Counters are incremented atomically: `UPDATE prompt SET import_count = import_count + 1`.

**Tier 2 — Score (in scope, PROMPT-04 UI)**

`score: float | null` is exposed in `PromptSummary`. Admin sets it via `PATCH /teams/{team_id}/prompts/{id}` with `{ "score": 4.5 }`. The evaluation track (EVAL-01) may also set it programmatically.

**Tier 3 — Token cost (out of scope, deferred to PROMPT-07)**

Fields `avg_input_tokens` and `avg_output_tokens` are reserved in the schema now (nullable). UI displays "N/A" with tooltip. Computation requires KPI integration — separate track.

#### 8.8 API surface — full delta

```
# Extended response (adds version, import_count, session_count, score, avg_input/output_tokens)
GET   /teams/{team_id}/prompts                 → list[PromptSummary]  ← breaking: adds fields
GET   /teams/{team_id}/prompts/{id}            → PromptDetail         ← breaking: adds fields
PUT   /teams/{team_id}/prompts/{id}            → PromptSummary        ← auto-increments version

# New
GET   /teams/{team_id}/prompts/context         → list[ContextPromptSummary]
POST  /teams/{team_id}/prompts/{id}/promote    → 201 PromptSummary
PATCH /teams/{team_id}/prompts/{id}            → 200 PromptSummary (score update only)

# Extended body
PATCH /sessions/{session_id}                   → gains context_prompt_id

# Extended response
POST  /execution/prepare                       → gains context_prompt_text
```

**New Pydantic schemas:**

```python
class ContextPromptSummary(BaseModel):
    id: str
    name: str
    description: str | None
    scope: Literal["personal", "team"]
    version: int
    session_count: int
    score: float | None

class PromptScoreUpdateRequest(BaseModel):
    score: float = Field(..., ge=0.0, le=5.0)

class PromptPromoteRequest(BaseModel):
    target_team_id: str
```

**Extended schemas (additive on reads, but `PromptSummary` gains required fields — OpenAPI regen required):**

```python
class PromptSummary(BaseModel):  # additions
    version: int
    import_count: int
    session_count: int
    score: float | None
    avg_input_tokens: int | None
    avg_output_tokens: int | None

class PromptDetail(PromptSummary):
    team_id: TeamId
    text: str
```

#### 8.9 Authorization

| Operation                 | Required membership                                        |
| ------------------------- | ---------------------------------------------------------- |
| CRUD own personal prompts | None (personal team is always self)                        |
| CRUD team prompts         | Member of that team                                        |
| GET /context for team X   | Member of team X (personal prompts appended automatically) |
| Promote personal → team X | Member of team X                                           |
| Promote team X → team Y   | Member of both X and Y                                     |
| Set score                 | Team admin                                                 |
| Promote to marketplace    | Global admin (PROMPT-06, out of scope)                     |

---

## 9. Alternatives Considered

### 9.1 Keep `format_map` but wrap in try/except and return an error event

Rejected. An error event mid-conversation is worse than a 422 at save time — the agent appears broken with no actionable message.

### 9.2 Escape all literal braces at save time (`{` → `{{`)

Rejected. Permanently mutates the stored text. A prompt containing `{today}` would be stored as `{{today}}`. Round-trips break.

### 9.3 Use a full template engine (Jinja2, Mako)

Rejected. The template surface is intentionally small — five canonical tokens, strict whitelist. A full template engine adds a dependency, a security surface (template injection), and a much more complex validation story.

### 9.4 Store prompt by live reference in agent instance

Rejected. Adds referential integrity constraints, cascade semantics, and policy decisions ("what happens to agents when the prompt is deleted") we do not want to decide now. Snapshot copy is conservative and reversible.

### 9.5 Add a separate user-scoped prompt API

Rejected. `personal` already exists as a first-class reserved team. A parallel user-owned prompt surface would duplicate authorization, navigation, and product semantics.

### 9.6 Mix team library and global marketplace in one mutable record

Rejected. One record flipping between "team-only" and "global" creates awkward moderation, audit, and update semantics. They are distinct product records.

### 9.7 Full version history table

A `PromptVersion(prompt_id, version, text, updated_at, updated_by)` table would allow diff views and rollback. Rejected for V1: the monotonic counter + snapshot gives 80% of the value at 5% of the complexity. Add if demand materialises.

### 9.8 Auto-propagate library updates to agents (live binding)

When the library prompt changes, all agents update automatically. Rejected: agents in production would silently change behavior. The `prompt_refs` metadata + "update available" banner gives the signal without the risk.

### 9.9 Denormalized "last used by" instead of counters

Rejected: privacy concern (personal prompts would reveal which team members used which prompts). Counters are sufficient for curation decisions.

### 9.10 Score computed automatically from agent KPIs

Rejected for V1: requires evaluation track (EVAL-01) to land first. The admin-settable float keeps the field live without coupling the release to EVAL-01.

### 9.11 Separate context_template table for chat context prompts

Rejected: the difference is in _how_ a prompt is used, not _what_ it is. One table with `import_count` vs `session_count` is cleaner.

---

## 10. Impact on Existing Contracts

| Area                                       | Change                                                                                      | Backward compatible                                        |
| ------------------------------------------ | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `fred_sdk.contracts.prompt_utils`          | New module: `PROMPT_SAFE_TOKENS` + `PromptTemplateError` + `validate_prompt_template()`     | Additive                                                   |
| `fred_runtime/react/react_prompting.py`    | `render_prompt_template` reimplemented; `_LiteralFriendlyDict` removed                      | Yes — same signature, broader safety                       |
| `fred_runtime/deep/deep_runtime.py`        | Same `render_prompt_template` import                                                        | Yes                                                        |
| `control_plane_backend/product/service.py` | `_validate_tuning_field_values` calls `validate_prompt_template` for `"prompt"` type fields | New 422s for previously accepted bad input — intentional   |
| `prompt` DB table                          | 6 new columns via Alembic migration                                                         | Yes — nullable or defaulted                                |
| `agent_instance` DB table                  | `prompt_refs jsonb` column                                                                  | Yes — nullable                                             |
| `session` DB table                         | `context_prompt_id` column                                                                  | Yes — nullable                                             |
| `PromptSummary` schema                     | 6 new fields                                                                                | Breaking for strict deserializers — OpenAPI regen required |
| `ExecutionPreparation` response            | `context_prompt_text: str \| null`                                                          | Additive                                                   |
| `PATCH /sessions/{id}` body                | `context_prompt_id` optional field                                                          | Additive                                                   |
| `AgentFormModal`                           | Inline 422 errors next to textarea; import/save actions (Slice D UI); version-drift banner  | UI addition                                                |
| `controlPlaneOpenApi.ts`                   | Regenerated after PROMPT-03 lands                                                           | Required                                                   |

**Revised 2026-06-19 (Part 3) — multi-prompt chat context.** The following rows in
this table are superseded by Part 3: the `session` `context_prompt_id` column (now an
ordered `session_context_prompts` association), the `PATCH /sessions/{id}` body (now
`context_prompt_ids: list[str]`), and `SessionListItem` (now exposes
`context_prompt_ids`). `ExecutionPreparation.context_prompt_text` is **unchanged** —
control-plane concatenates the resolved prompt texts, so the runtime contract
(`fred-sdk` / `fred-runtime`) is not touched.

---

## 11. Out of Scope

| Item                                                                | Where tracked        |
| ------------------------------------------------------------------- | -------------------- |
| Global prompt marketplace (`PublishedPromptRow`, publish/unpublish) | PROMPT-06            |
| Token cost KPI integration (`avg_input/output_tokens` computation)  | PROMPT-07            |
| Automatic score derivation from evaluation results                  | EVAL-01 + PROMPT-07  |
| Full text version history (`PromptVersion` table)                   | Future RFC if needed |
| Prompt admin role distinct from team admin                          | Future RFC if needed |
| Prompt search / tagging / categorisation                            | Future RFC           |

---

## 12. Implementation Sequence

```
Slice A   (fred-sdk prompt_utils module + fred-runtime safe renderer)
  ↓
Slice B   (control-plane-backend: validate_prompt_template called at save time)
  ↓
Slice C   (test coverage + 422 error shape — done when B lands)
  ↓
Slice PROMPT-02  (team/personal prompt CRUD + OpenAPI regen)                ← done (Codex 2026-05-08)
  ↓
PROMPT-03   (DB schema extension: version, counters, score, token fields;
          /prompts/context endpoint; session PATCH with context_prompt_id;
          ExecutionPreparation gains context_prompt_text)
  ↓
PROMPT-04    (frontend: PromptsPage + AgentFormModal import/save + version-drift banner)
  ↓
PROMPT-05    (frontend: chat context picker replaces free textarea)
  ↓
PROMPT-07     (token cost KPI integration — deferred, requires EVAL-01 + simon)
  ↓
PROMPT-06     (global prompt marketplace — separate track)
```

### PROMPT-03 — Backend extension

**Owner**: Dimitri | **Depends on**: PROMPT-02 (done)

```
Alembic migration:
  ALTER TABLE prompt ADD COLUMN version int NOT NULL DEFAULT 1;
  ALTER TABLE prompt ADD COLUMN import_count int NOT NULL DEFAULT 0;
  ALTER TABLE prompt ADD COLUMN session_count int NOT NULL DEFAULT 0;
  ALTER TABLE prompt ADD COLUMN score float NULLABLE;
  ALTER TABLE prompt ADD COLUMN avg_input_tokens int NULLABLE;
  ALTER TABLE prompt ADD COLUMN avg_output_tokens int NULLABLE;
  ALTER TABLE agent_instance ADD COLUMN prompt_refs jsonb NULLABLE;
  ALTER TABLE session ADD COLUMN context_prompt_id varchar NULLABLE;

PromptStore:
  update() → auto-increment version
  increment_import_count(prompt_id, team_id)
  increment_session_count(prompt_id, team_id)
  list_context_prompts(personal_team_id, team_id) → union query

ProductService:
  agent create/update → write prompt_refs + call increment_import_count
  session PATCH → accept context_prompt_id, call increment_session_count
  prepare_execution → resolve context_prompt_text from context_prompt_id

API endpoints: GET /prompts/context, POST /prompts/{id}/promote, PATCH /prompts/{id}
```

### PROMPT-04 — Frontend: PromptsPage + AgentFormModal

**Owner**: Dimitri or Dimitri | **Depends on**: PROMPT-03 (OpenAPI regenerated)

```
PromptsPage (new rework page):
  Route: /teams/:teamId/prompts
  Table: name, description, version badge, import_count, session_count, score, updated_at
  Create/edit/delete modals; score edit inline (admin); "Promote to team" action

AgentFormModal:
  [Import from library] → PromptPickerModal (preview panel, [Use] copies text + stores prompt_ref)
  [Save as prompt] → SavePromptModal (name, description → POST to team library)
  Version-drift banner when prompt_ref version < current library version
  Inline 422 error display below textarea
```

### PROMPT-05 — Chat context picker (revised 2026-06-19 → multi-prompt)

**Owner**: Dimitri | **Depends on**: PROMPT-03

> Scope revised from single to **multi-prompt** (`0..N` per session). The
> authoritative spec — persistence, contract delta, execution resolution, and the
> validated composer UX (options-panel entry + removable pills) — is in **Part 3**.
> The sketch below is kept for history; it describes the superseded single-prompt
> picker.

```
ComposerSettingsControls chip + popover (or session init surface):
  Replace free textarea with library picker
  (AgentOptionsPanel retired 2026-05-24 — this feature targets ComposerSettingsControls topSlot chip)
  Source: GET /teams/{team_id}/prompts/context
  Personal prompts (grouped) + team prompts (grouped), ordered by session_count DESC
  Score stars when non-null
  User selects → PATCH /sessions/{id} { context_prompt_id }
  "Clear context" → PATCH with context_prompt_id: null
```

### PROMPT-07 — Token cost KPI integration (DEFERRED)

**Owner**: Simon + Dimitri | **Depends on**: EVAL-01, fred-core KPI store changes

Fields `avg_input_tokens` / `avg_output_tokens` exist in DB and schema. UI displays "N/A". When PROMPT-07 starts it will need its own RFC amendment covering: `context_prompt_id` label in fred-core KPI turn events, aggregation worker, and write-back to `PromptRow`.

---

## 13. Resolved Decisions

| Question                                         | Resolution                                                                        |
| ------------------------------------------------ | --------------------------------------------------------------------------------- |
| Unknown tokens → warn or block?                  | Block with 422 — no warnings accepted                                             |
| User-authored prompts: which tokens?             | `PROMPT_SAFE_TOKENS` only — internal `extra_tokens` not in user-facing validation |
| Live link at agent instance level?               | No. Snapshot text + `prompt_refs` metadata for drift detection                    |
| Live link at session level?                      | Yes — session is ephemeral, no permanence risk                                    |
| Single or multiple prompts per session?          | **Revised 2026-06-19: multiple (`0..N`), cumulative and ordered — see Part 3** (was: single) |
| Multi-prompt persistence model?                  | Ordered `session_context_prompts` association table (not JSON column) — Part 3    |
| Multi-prompt → runtime: N fields or concatenate? | Concatenate control-plane-side into the existing `context_prompt_text`; runtime contract unchanged — Part 3 |
| Personal prompts visible in team chat?           | Yes — union query via `/prompts/context` endpoint                                 |
| Score source?                                    | Admin-set float; evaluation track (EVAL-01) may set it later                      |
| Token cost computation?                          | Deferred to PROMPT-07. Fields reserved, display "N/A"                             |
| Promotion: conflict on same name?                | 409 Conflict — caller renames first                                               |
| Promotion: transfer or copy?                     | Always copy. Source unchanged                                                     |
| Versioning: immutable history vs counter?        | Counter only (V1). Additive history table if demand materialises                  |
| Prompt CRUD scope?                               | Team-scoped only; personal uses reserved `personal` team                          |
| Agent instances: live prompt id or text copy?    | Text copy only — no live library reference                                        |
| Global marketplace: same branch as team library? | No — Slice E is a separate follow-up track                                        |

---

## Part 3 — Amendment (2026-06-19): Multi-prompt chat context (PROMPT-05 revised)

**Author**: Dimitri Tombroff · **Date**: 2026-06-19 · **Area**: `control-plane-backend`, `frontend`
**Supersedes**: the single-`context_prompt_id` cardinality in §8.4, the matching rows in §10, the §12 PROMPT-05 sketch, and the "Live link at session level → one" line in §13. Everything else in Parts 1–2 stands.

### 14. Motivation

Before the `rework` frontend migration, the product exposed a **chat-context** concept that let a user attach **several** contexts to a single conversation; the selection persisted across reloads. The migration removed that picker and Part 2 replaced the concept with a library-backed **single** `context_prompt_id` per session. Product decision (2026-06-19): restore the original ergonomics — a conversation may have **0, 1, or many** prompts attached, cumulatively, persisted with the session — now sourced from the personal + team prompt library instead of standalone chat-context resources.

This is a control-plane + frontend change only. The runtime execution contract is deliberately left untouched (see §17).

### 15. Persistence model — ordered association table

The scalar `session_metadata.context_prompt_id` column is replaced by an ordered association:

```
session_context_prompts                  (control-plane DB)
  session_id   varchar  NOT NULL  FK → session_metadata.session_id  ON DELETE CASCADE
  prompt_id    varchar  NOT NULL            -- prompt UUID, or "default:{category}" for platform defaults
  position     int      NOT NULL            -- 0-based; defines selection + concatenation order
  PRIMARY KEY (session_id, prompt_id)
```

**Why a join table, not a JSON column on `session_metadata`** (decided):

- preserves explicit ordering via `position` (concatenation order is user-visible);
- mirrors the existing per-session association pattern already used for session attachments;
- enables per-row usage attribution (`session_count` per prompt) without parsing a blob;
- avoids read-modify-write races on a JSON array under concurrent PATCHes.

**Migration** (single Alembic revision):

1. create `session_context_prompts`;
2. backfill: for every `session_metadata` row with a non-null `context_prompt_id`, insert one row `(session_id, context_prompt_id, 0)`;
3. drop `session_metadata.context_prompt_id`.

> Note: §8.4 / §12 wrote `ALTER TABLE session …`; the real table is `session_metadata`. The migration targets `session_metadata`.

### 16. API contract delta (revises §8.8)

```
PATCH /control-plane/v1/teams/{team_id}/sessions/{session_id}
  body: context_prompt_ids: list[str] | null     # full ordered replacement set
        (replaces scalar context_prompt_id; the clear_context_prompt flag is removed)

GET   /control-plane/v1/teams/{team_id}/sessions/{session_id}      → SessionListItem
GET   /control-plane/v1/teams/{team_id}/sessions                   → list[SessionListItem]
  SessionListItem.context_prompt_ids: list[str]  # was context_prompt_id: str | null
```

**PATCH semantics — full-set replacement, not append.** The client always sends the complete active set; the server diffs against the current set, deletes removed rows, inserts new ones, and rewrites `position` from the payload order. This is idempotent and lets a single endpoint cover add / remove / reorder / clear.

- **Clear** = `context_prompt_ids: []` (or `null`). The separate `clear_context_prompt` boolean from §8.4 is dropped — an empty list is unambiguous.
- **Validation**: unknown / deleted prompt ids are silently skipped at resolution time (consistent with §8.4: a missing prompt injects no context, the session continues normally). A 422 is *not* raised for stale ids, so a deleted shared prompt never breaks an open conversation.

```python
class UpdateSessionRequest(BaseModel):   # revised
    updated_at: datetime | None = None
    title: str | None = None
    context_prompt_ids: list[str] | None = None   # full replacement set; [] or None clears
    # context_prompt_id and clear_context_prompt removed

class SessionListItem(BaseModel):        # revised
    ...
    context_prompt_ids: list[str]        # ordered; empty when none attached
```

### 17. Execution resolution — concatenate, runtime contract unchanged

At `prepare_execution`, control-plane loads the attached prompts in `position` order, resolves each to its current text (library prompts via `PromptStore`, `default:{category}` via the default-prompt table), and concatenates into the **existing single** `ExecutionPreparation.context_prompt_text` field:

```
context_prompt_text = "\n\n".join(p.text for p in ordered_resolved_prompts) or None
```

**Key decision:** concatenation happens control-plane-side, so `RuntimeContext.context_prompt_text` stays a scalar and **`fred-sdk` / `fred-runtime` are not modified**. Blast radius is confined to `control-plane-backend` + `frontend`. The already-dead `RuntimeContext.selected_chat_context_ids` field stays unused (candidate for removal in a separate cleanup).

- **Separator**: two newlines (`\n\n`). No per-prompt header/label/delimiter in V1. If labeled boundaries prove necessary (e.g. the model conflates stacked instructions), a future amendment may introduce a delimiter — out of scope here.
- **Order**: ascending `position` = the order the user arranged the pills.

### 18. Usage counters (revises §8.7 Tier 1)

`session_count` is incremented per prompt on **first attach to a session** — i.e. for each id present in the new PATCH set but absent from the previous set. Re-sending an already-attached id does not double-count; removing a prompt does **not** decrement. `default:{category}` ids increment `default_prompt_usage` as today. This keeps "how many conversations adopted this prompt" meaningful under full-set-replacement PATCH semantics.

### 19. Frontend — multi-select picker + active pills (validated UX 2026-06-19)

Design reviewed and approved 2026-06-19. The principle: **separate the selection gesture from the displayed state.**

**Active state — removable pills above the input.**
Attached prompts render as pills in the composer's `aboveTextSlot` (the slot that already hosts `AttachmentChips`), each showing the prompt's category colour + icon from `promptCategories.ts`, removable via a `×`. Zero attached → no pills at all; the composer is byte-for-byte as today. This mirrors the attachments / tasks "0 → hidden" rule: chrome appears only when there is state to show.

**Selection gesture — entry in the existing options panel.**
A `Prompts` entry is added to the composer options panel (the `+` button → `ComposerActionsMenu` → `SearchConfig`), sitting alongside `Joindre des fichiers` and `Search policy`. The entry is a navigable sub-row showing the active count (`2 prompts actifs`) and opens the picker — consistent with the document picker and search-policy rows that already live there. No new permanent chip is added to the composer bar.

**Picker — multi-select, library-sourced.**
Reuses `PromptCard` in multi-select mode (checkbox/toggle), sourced from `GET /teams/{team_id}/prompts/context` (union of personal + team + defaults, ordered `session_count DESC`, score stars when non-null, `scope` separator personal / team / default). On close, the selected set is persisted via `PATCH /sessions/{id} { context_prompt_ids }` and becomes the pills.

**Hydration.**
On session open, `SessionListItem.context_prompt_ids` rehydrates the pills — attached prompts survive reload, which is what "associated with my conversation" requires.

### 20. Impact on existing contracts (delta vs §10)

| Area                                       | Change                                                                                   | Backward compatible                                  |
| ------------------------------------------ | ---------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `session_metadata` DB table                | drop `context_prompt_id` column                                                          | Migration backfills into `session_context_prompts`   |
| `session_context_prompts` DB table         | new ordered association table                                                            | Additive (new table)                                 |
| `PATCH /sessions/{id}` body                | `context_prompt_id` → `context_prompt_ids: list[str]`; `clear_context_prompt` removed    | **Breaking** — OpenAPI regen + frontend update       |
| `SessionListItem` schema                   | `context_prompt_id` → `context_prompt_ids: list[str]`                                     | **Breaking** — OpenAPI regen + frontend update       |
| `ExecutionPreparation.context_prompt_text` | now a concatenation of N resolved prompts                                                 | **Unchanged** — scalar field, same type              |
| `RuntimeContext` (`fred-sdk`)              | none                                                                                      | Untouched by design                                  |
| `PromptStore`                              | `increment_session_count` called per newly-attached prompt                               | Behavioural, additive                                |
| `controlPlaneOpenApi.ts`                   | regenerated after the backend lands                                                      | Required                                             |
| `CONTROL-PLANE-PRODUCT-CONTRACT.md`        | dated entry: session context becomes a list                                              | Doc change (frozen contract — dated entry required)  |

### 21. Resolved decisions (Part 3)

| Question                                          | Resolution                                                              |
| ------------------------------------------------- | ----------------------------------------------------------------------- |
| One prompt or many per session?                   | Many (`0..N`), cumulative and ordered                                   |
| Persistence shape?                                | Ordered `session_context_prompts` association table                     |
| PATCH semantics?                                  | Full ordered set replacement (idempotent); `[]`/`null` clears           |
| Expose N to the runtime or concatenate?           | Concatenate control-plane-side into existing `context_prompt_text`      |
| Separator between stacked prompts?                | `\n\n`, no labels in V1                                                  |
| Stale / deleted prompt id in the set?             | Silently skipped at resolution — never 422s an open conversation        |
| `session_count` on re-attach / remove?            | Increment on first attach only; never decrement                         |
| Selection surface?                                | Entry in the existing `+` options panel; active state as removable pills |

### 22. Out of scope (Part 3)

- Per-prompt labeled delimiters in the concatenated context (revisit only if the model conflates stacked instructions).
- Removal of the dead `RuntimeContext.selected_chat_context_ids` field (separate cleanup).
- Drag-to-reorder pills — V1 order = selection order; reordering is a later UX refinement.
- Exposing the attached-prompt list to KPI events (folds into PROMPT-07).
