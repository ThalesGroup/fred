# RFC — Safe Prompt Authoring, Validation, and Library

**Status**: Slices A + B + C implemented (2026-05-07) · Slice D backend implemented (2026-05-08) · P1-D1b in progress · Slice E / P1-E deferred  
**Author**: Dimitri Tombroff  
**Date**: 2026-05-07 (safety) — 2026-05-09 (library extension)  
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

| Pattern in template | What Python does | Result |
|---|---|---|
| `{toto.toto}` | resolves `dict['toto']` → returns `"{toto}"` (str), then accesses `.toto` on it | `AttributeError: 'str' object has no attribute 'toto'` |
| `{}` | empty field name | `ValueError: Single '}' encountered in format string` |
| `function main() { ... }` | unbalanced brace, depending on surrounding chars | `ValueError` |
| `{0}` | positional reference | accesses index 0 of the dict values — unexpected |

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

| Surface | Authored by | Token set | Validated at persistence |
|---|---|---|---|
| `prompts.*` tuning value (UI form) | Team admin / end user | `PROMPT_SAFE_TOKENS` only | Yes — strict (Slice B) |
| `system_prompt_template` in Python `AgentDefinition` | Agent developer | `PROMPT_SAFE_TOKENS` + runtime extras | No — developer responsibility |

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

| Found | Error reason |
|---|---|
| `{}` | "Empty placeholder — not a valid template token" |
| `{0}`, `{1}` | "Positional placeholder — not supported in prompt templates" |
| `{toto.toto}` | "Dotted attribute syntax is not supported in prompt templates" |
| `{ space }` | "Whitespace in placeholder — not a valid template token" |

**Pass 2 — Unknown simple tokens:**

Any `{identifier}` not in `PROMPT_SAFE_TOKENS` is an error. The error message lists all supported tokens.

**Validation policy:**

| Situation | HTTP response |
|---|---|
| Any non-simple brace pattern | `422` with list of `PromptTemplateError` |
| Any unknown `{identifier}` token | `422` with list of `PromptTemplateError` |
| Template contains no `{...}` patterns | `200` / `201` |
| Template uses only canonical tokens | `200` / `201` |

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
    { "pattern": "{toto.toto}", "reason": "Dotted attribute syntax is not supported in prompt templates" },
    { "pattern": "{}", "reason": "Empty placeholder — not a valid template token" }
  ]
}
```

- The frontend `AgentFormModal` must surface these errors next to the prompt textarea, not as a generic toast. (UI implementation tracked as a TODO in `CHAT-UI-BACKLOG.md`.)

---

## Part 2 — Library Architecture (Slices D, E / P1-D1b through P1-F)

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

The current `AgentOptionsPanel` exposes a free textarea for conversation context. Without curation or a quality signal, every user invents their own version of the same prompt.

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
                 (copy)             (copy, P1-E)
```

All three levels use the same `PromptRow` structure (scoped by `team_id`). The marketplace uses a separate `PublishedPromptRow` table — unchanged from §Slice E, deferred to P1-E.

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
                                Set by admin or by the evaluation track (O1).
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
> *"prompts.system was imported from "Bid Expert v2" — current version is v5. [Review and update]"*

#### 8.4 Chat context integration — live reference at session level

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
  { "id": "...", "name": "Analyse appel d'offres", "scope": "personal", "session_count": 12, "score": null },
  { "id": "...", "name": "Répondre en français",  "scope": "team",     "session_count": 48, "score": 4.5  }
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

**Authorization:** caller must be a member of both source and target team. Promotion to marketplace is a separate flow (P1-E).

#### 8.7 Analytics model

Three tiers, implemented progressively.

**Tier 1 — Usage counters (in scope, P1-D1b)**

| Field | Source event | Updated by |
|---|---|---|
| `import_count` | Admin imports prompt into agent | `service.py` — agent create/update path |
| `session_count` | User selects prompt as chat context | `service.py` — session PATCH path |

Counters are incremented atomically: `UPDATE prompt SET import_count = import_count + 1`.

**Tier 2 — Score (in scope, P1-D2 UI)**

`score: float | null` is exposed in `PromptSummary`. Admin sets it via `PATCH /teams/{team_id}/prompts/{id}` with `{ "score": 4.5 }`. The evaluation track (O1) may also set it programmatically.

**Tier 3 — Token cost (out of scope, deferred to P1-F)**

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

| Operation | Required membership |
|---|---|
| CRUD own personal prompts | None (personal team is always self) |
| CRUD team prompts | Member of that team |
| GET /context for team X | Member of team X (personal prompts appended automatically) |
| Promote personal → team X | Member of team X |
| Promote team X → team Y | Member of both X and Y |
| Set score | Team admin |
| Promote to marketplace | Global admin (P1-E, out of scope) |

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

Rejected for V1: requires evaluation track (O1) to land first. The admin-settable float keeps the field live without coupling the release to O1.

### 9.11 Separate context_template table for chat context prompts

Rejected: the difference is in *how* a prompt is used, not *what* it is. One table with `import_count` vs `session_count` is cleaner.

---

## 10. Impact on Existing Contracts

| Area | Change | Backward compatible |
|---|---|---|
| `fred_sdk.contracts.prompt_utils` | New module: `PROMPT_SAFE_TOKENS` + `PromptTemplateError` + `validate_prompt_template()` | Additive |
| `fred_runtime/react/react_prompting.py` | `render_prompt_template` reimplemented; `_LiteralFriendlyDict` removed | Yes — same signature, broader safety |
| `fred_runtime/deep/deep_runtime.py` | Same `render_prompt_template` import | Yes |
| `control_plane_backend/product/service.py` | `_validate_tuning_field_values` calls `validate_prompt_template` for `"prompt"` type fields | New 422s for previously accepted bad input — intentional |
| `prompt` DB table | 6 new columns via Alembic migration | Yes — nullable or defaulted |
| `agent_instance` DB table | `prompt_refs jsonb` column | Yes — nullable |
| `session` DB table | `context_prompt_id` column | Yes — nullable |
| `PromptSummary` schema | 6 new fields | Breaking for strict deserializers — OpenAPI regen required |
| `ExecutionPreparation` response | `context_prompt_text: str \| null` | Additive |
| `PATCH /sessions/{id}` body | `context_prompt_id` optional field | Additive |
| `AgentFormModal` | Inline 422 errors next to textarea; import/save actions (Slice D UI); version-drift banner | UI addition |
| `controlPlaneOpenApi.ts` | Regenerated after P1-D1b lands | Required |

---

## 11. Out of Scope

| Item | Where tracked |
|---|---|
| Global prompt marketplace (`PublishedPromptRow`, publish/unpublish) | P1-E |
| Token cost KPI integration (`avg_input/output_tokens` computation) | P1-F |
| Automatic score derivation from evaluation results | O1 + P1-F |
| Full text version history (`PromptVersion` table) | Future RFC if needed |
| Prompt admin role distinct from team admin | Future RFC if needed |
| Prompt search / tagging / categorisation | Future RFC |

---

## 12. Implementation Sequence

```
Slice A   (fred-sdk prompt_utils module + fred-runtime safe renderer)
  ↓
Slice B   (control-plane-backend: validate_prompt_template called at save time)
  ↓
Slice C   (test coverage + 422 error shape — done when B lands)
  ↓
Slice D1  (team/personal prompt CRUD + OpenAPI regen)                ← done (Codex 2026-05-08)
  ↓
P1-D1b   (DB schema extension: version, counters, score, token fields;
          /prompts/context endpoint; session PATCH with context_prompt_id;
          ExecutionPreparation gains context_prompt_text)
  ↓
P1-D2    (frontend: PromptsPage + AgentFormModal import/save + version-drift banner)
  ↓
P1-D3    (frontend: chat context picker replaces free textarea)
  ↓
P1-F     (token cost KPI integration — deferred, requires O1 + simon)
  ↓
P1-E     (global prompt marketplace — separate track)
```

### P1-D1b — Backend extension

**Owner**: Dimitri | **Depends on**: P1-D1 (done)

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

### P1-D2 — Frontend: PromptsPage + AgentFormModal

**Owner**: Félix or Dimitri | **Depends on**: P1-D1b (OpenAPI regenerated)

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

### P1-D3 — Chat context picker

**Owner**: Félix | **Depends on**: P1-D1b

```
AgentOptionsPanel or session init surface:
  Replace free textarea with library picker
  Source: GET /teams/{team_id}/prompts/context
  Personal prompts (grouped) + team prompts (grouped), ordered by session_count DESC
  Score stars when non-null
  User selects → PATCH /sessions/{id} { context_prompt_id }
  "Clear context" → PATCH with context_prompt_id: null
```

### P1-F — Token cost KPI integration (DEFERRED)

**Owner**: Simon + Dimitri | **Depends on**: O1, fred-core KPI store changes

Fields `avg_input_tokens` / `avg_output_tokens` exist in DB and schema. UI displays "N/A". When P1-F starts it will need its own RFC amendment covering: `context_prompt_id` label in fred-core KPI turn events, aggregation worker, and write-back to `PromptRow`.

---

## 13. Resolved Decisions

| Question | Resolution |
|---|---|
| Unknown tokens → warn or block? | Block with 422 — no warnings accepted |
| User-authored prompts: which tokens? | `PROMPT_SAFE_TOKENS` only — internal `extra_tokens` not in user-facing validation |
| Live link at agent instance level? | No. Snapshot text + `prompt_refs` metadata for drift detection |
| Live link at session level? | Yes — session is ephemeral, no permanence risk |
| Personal prompts visible in team chat? | Yes — union query via `/prompts/context` endpoint |
| Score source? | Admin-set float; evaluation track (O1) may set it later |
| Token cost computation? | Deferred to P1-F. Fields reserved, display "N/A" |
| Promotion: conflict on same name? | 409 Conflict — caller renames first |
| Promotion: transfer or copy? | Always copy. Source unchanged |
| Versioning: immutable history vs counter? | Counter only (V1). Additive history table if demand materialises |
| Prompt CRUD scope? | Team-scoped only; personal uses reserved `personal` team |
| Agent instances: live prompt id or text copy? | Text copy only — no live library reference |
| Global marketplace: same branch as team library? | No — Slice E is a separate follow-up track |
