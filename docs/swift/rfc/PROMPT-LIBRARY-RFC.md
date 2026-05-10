# RFC — Prompt Library Architecture (Extended)

**Status**: Proposed  
**Date**: 2026-05-09  
**Author**: Dimitri Tombroff  
**Supersedes**: `PROMPT-SAFETY-RFC.md §Slice D` (basic library) — this RFC extends and partially revises that slice.  
**Related backlog items**: P1-D1b, P1-D2, P1-D3, P1-F

---

## 1. Context — what Slice D established

`PROMPT-SAFETY-RFC.md §Slice D` defined a minimal first-class prompt library:

- `PromptRow` scoped to a `team_id`
- CRUD endpoints `POST/GET/PUT/DELETE /teams/{id}/prompts`
- Import into agent = snapshot copy of text (no live reference)
- Personal prompts = reserved `personal` team (no separate user API)
- No versioning, no analytics, no cross-team visibility — explicitly deferred

Slice D backend was implemented by Codex (2026-05-08):
`PromptRow`, `PromptStore`, Alembic migration, Pydantic schemas, API endpoints.

This RFC covers the follow-up: **versioning, analytics, personal→team visibility,
chat context integration as a live library reference, and promotion flows.**

---

## 2. Problem

### 2.1 No quality signal

Without versioning and usage analytics, the library is a flat list with no
indication of which prompts are mature, how often they are used, or whether
a given agent is running on an outdated prompt version. After three months,
the library becomes a graveyard — no one knows what is still relevant.

### 2.2 Personal prompts are invisible in team conversations

Alice works in the `bid-and-capture` team. She experiments with a useful
context prompt in her personal space. When she opens a conversation with the
team Bid agent, she has no way to apply her personal prompt — the context
picker only shows team prompts. She either rewrites it by hand or gives up.
The team never benefits from her work.

### 2.3 Chat context is a free textarea

The current `AgentOptionsPanel` exposes a free textarea for conversation
context. This reproduces the "foire à l'empoigne" problem: every user
invents a mediocre "respond in French" rather than picking the curated
version the team agreed on. There is no usage data, no curation, no
quality signal.

### 2.4 No token cost visibility

Prompt quality cannot be assessed purely by usage count. A prompt that
produces short, precise answers is cheaper than one that generates verbose
outputs. Without token cost data per prompt, the team has no way to evaluate
whether a change improved or degraded efficiency.

### 2.5 No path to influence the library

A team member who writes a good personal prompt has no mechanism to share
it. The team library can only grow via admin action. This creates a bottleneck
and discourages experimentation.

---

## 3. Proposed Design

### 3.1 Scope hierarchy

Three levels, strictly ordered. Promotion between levels is always
**copy-by-value** — never a live link.

```
personal/{user_id}          team/{team_id}          marketplace
─────────────────          ──────────────          ───────────
Alice's private space  →   Shared team space  →    Global catalog
                 promote            promote
                 (copy)             (copy, P1-E)
```

All three levels use the same `PromptRow` structure (scoped by `team_id`).
The marketplace uses a separate `PublishedPromptRow` table — unchanged from
`PROMPT-SAFETY-RFC.md §Slice E`, deferred to P1-E.

**Reserved team ids:**
- `personal` resolves to the calling user's personal team (existing control-plane convention)
- Named team ids resolve normally

### 3.2 Data model — extended PromptRow

Extends the Codex-built `PromptRow` via a new Alembic migration:

```
PromptRow (additions to existing schema)
─────────────────────────────────────────────────────────────────────
version              int        NOT NULL  DEFAULT 1
                                Auto-incremented on every PUT.
                                Starts at 1 on creation.
                                Monotonic, never reused.
                                There is no history table — only the
                                current version is stored.

import_count         int        NOT NULL  DEFAULT 0
                                Incremented each time this prompt is
                                imported into a managed agent instance.

session_count        int        NOT NULL  DEFAULT 0
                                Incremented each time a user selects
                                this prompt as their chat context for
                                a session.

score                float      NULLABLE  DEFAULT NULL
                                Explicit quality rating, range 0.0–5.0.
                                Set by admin or by the evaluation track
                                (O1). Never auto-computed in this RFC.
                                NULL = not yet rated. Displayed as
                                star rating in the UI when non-null.

avg_input_tokens     int        NULLABLE  DEFAULT NULL
avg_output_tokens    int        NULLABLE  DEFAULT NULL
                                Average token counts per turn in
                                conversations where this prompt was
                                active (as agent system prompt or chat
                                context). Updated by background
                                aggregation — see §3.6. NULL = no
                                data yet. Displayed as "N/A" in UI.
```

**No history table.** The monotonic `version` counter is the only versioning
artifact. If full history is needed later, a `PromptVersion` table can be
added additively — the integer counter makes it unambiguous which row a
historical snapshot corresponds to.

**Uniqueness constraint unchanged:** `(team_id, name)` unique within team.

### 3.3 Agent integration — prompt_refs

**Revisiting PROMPT-SAFETY-RFC §3.4 rejection.**

The previous RFC rejected live references in agent instances to avoid
cascade-deletion and referential integrity complexity. That decision stands
for the *text* — the agent instance still stores a snapshot copy of the
prompt text in `prompts.*` tuning values.

What we add here is a **metadata-only back-reference** stored alongside the
snapshot: which library prompt was the source, and at which version. This
reference is purely informational — deleting the library prompt does not
break the agent (the text copy remains). There is no foreign key constraint.

```
ManagedAgentInstance
  prompt_refs:  jsonb | null   DEFAULT NULL

Shape:
{
  "prompts.system":   { "prompt_id": "abc-123", "version": 2 },
  "prompts.planning": { "prompt_id": "def-456", "version": 1 }
}
```

`prompt_refs` is written by the control-plane service when the admin
imports a library prompt. It is cleared for a field when the admin
overwrites that field manually (no library source → no ref).

**UI consequence:** when the current library version > stored ref version,
the `AgentFormModal` shows a non-blocking banner:

> *"prompts.system was imported from "Bid Expert v2" — current version is v5.
>  [Review and update]"*

The admin can choose to reimport or ignore. This is informational only —
no action is forced.

### 3.4 Chat context integration — live reference at session level

**Why this is different from the §3.4 rejection.**

The previous RFC rejected live references at the *agent instance* level
because agent instances are long-lived configuration objects. Session context
is ephemeral: a session ends, the reference is gone. There is no cascade
problem, no "what happens if the prompt is deleted" permanence issue. A
missing or deleted prompt at session start simply means no context is injected
— the session continues normally.

**Design:**

```
Session (control-plane DB)
  context_prompt_id:  str | null   DEFAULT NULL
```

When a user selects a context from the library picker, `context_prompt_id`
is stored on the session (via the existing
`PATCH /sessions/{id}` endpoint — body extended with `context_prompt_id`).

At execution preparation time, control-plane resolves the prompt text:

```
ExecutionPreparation (response)
  context_prompt_text:  str | null
```

The runtime receives the current text of the referenced prompt and injects
it as a conversation-level context. If the prompt was updated since the user
selected it, they get the new text at next session start — intentional: live
reference means always-current.

**Incrementing session_count:** control-plane increments
`PromptRow.session_count` when `context_prompt_id` is written to the session.

### 3.5 Personal → team visibility in chat context picker

The chat context picker (in `AgentOptionsPanel` or session init surface)
fetches from a new endpoint:

```
GET /control-plane/v1/teams/{team_id}/prompts/context
```

This endpoint returns the **union** of:
1. Prompts scoped to the calling user's `personal` team
2. Prompts scoped to `team_id`

Ordered by `session_count DESC, name ASC`. The response includes a
`scope` field on each item (`"personal"` or `"team"`) so the UI can
render a visual separator.

```json
[
  { "id": "...", "name": "Analyse appel d'offres", "scope": "personal",
    "session_count": 12, "score": null },
  { "id": "...", "name": "Répondre en français",  "scope": "team",
    "session_count": 48, "score": 4.5 }
]
```

This endpoint is **read-only** — it does not mutate or cross-pollinate the
underlying team-scoped records.

### 3.6 Promotion flows

All promotion flows are **copy-by-value**. The source prompt is never modified.
The destination starts at `version=1`, `import_count=0`, `session_count=0`,
`score=null`.

```
POST /control-plane/v1/teams/{team_id}/prompts/{id}/promote
Body: { "target_team_id": "bid-and-capture" }
```

Creates a new `PromptRow` in `target_team_id` with the same name, description,
and text. If a prompt with the same name already exists in the target team, the
endpoint returns `409 Conflict` — the caller must rename first.

**Authorization:** the caller must be a member of **both** the source team and
the target team. Personal → team promotion requires team membership. Promotion
to marketplace is a separate flow (Slice E, P1-E).

Promotion does **not** update `import_count` or `session_count` on the source.
Those counters track active use, not lineage.

### 3.7 Analytics model

Three tiers, implemented progressively.

**Tier 1 — Usage counters (in scope, P1-D1b)**

| Field | Source event | Updated by |
|---|---|---|
| `import_count` | Admin imports prompt into agent | `service.py` — agent create/update path |
| `session_count` | User selects prompt as chat context | `service.py` — session PATCH path |

Counters are incremented atomically with `UPDATE prompt SET import_count = import_count + 1`.
No race condition handling required at this scale.

**Tier 2 — Score (in scope, P1-D2 UI)**

`score: float | null` is exposed in the `PromptSummary` response. The UI
renders it as a star rating (0–5) when non-null, as "-" when null.

Admin can set the score via:
```
PATCH /control-plane/v1/teams/{team_id}/prompts/{id}
Body: { "score": 4.5 }
```

The evaluation track (O1) may also set it programmatically via the same
endpoint once the evaluation harness is live.

**Tier 3 — Token cost (out of scope, deferred to P1-F)**

Fields `avg_input_tokens` and `avg_output_tokens` are added to the schema
now (nullable) so the UI can display "N/A" with a tooltip explaining what
the metric will show. No computation logic is wired in this RFC.

**Required integration (P1-F):**
- KPI turn events must carry a `context_prompt_id` label (for chat context)
  and an optional `agent_prompt_version` label (for system prompts)
- A background aggregation job or Langfuse query computes the averages and
  writes them back to `PromptRow` via an internal service call
- This requires changes to `fred-core` (KPI store), `fred-runtime` (turn events),
  and a new aggregation worker — separate track, coordinate with Simon

### 3.8 API surface — full delta

**New or modified endpoints (control-plane-backend):**

```
# Extended response (add version, import_count, session_count, score, avg_input_tokens, avg_output_tokens)
GET  /teams/{team_id}/prompts               → list[PromptSummary]  ← breaking: adds fields
GET  /teams/{team_id}/prompts/{id}          → PromptDetail         ← breaking: adds fields
PUT  /teams/{team_id}/prompts/{id}          → PromptSummary        ← auto-increments version

# New
GET  /teams/{team_id}/prompts/context       → list[ContextPromptSummary]  (union personal+team)
POST /teams/{team_id}/prompts/{id}/promote  → 201 PromptSummary
PATCH /teams/{team_id}/prompts/{id}         → 200 PromptSummary    (score update only)

# Extended (add context_prompt_id to body)
PATCH /sessions/{session_id}                → existing endpoint, body gains context_prompt_id

# Extended (add context_prompt_text to response)
POST /execution/prepare                     → existing endpoint, response gains context_prompt_text
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

**Extended schemas (additive — backward compatible reads, but new required
fields on PromptSummary means clients that deserialize strictly will need
an update after OpenAPI regen):**

```python
class PromptSummary(BaseModel):  # additions
    version: int
    import_count: int
    session_count: int
    score: float | None
    avg_input_tokens: int | None
    avg_output_tokens: int | None

class PromptDetail(PromptSummary):  # unchanged inheritance
    team_id: TeamId
    text: str
```

### 3.9 Authorization

| Operation | Required membership |
|---|---|
| CRUD own personal prompts | None (personal team is always self) |
| CRUD team prompts | Member of that team |
| GET /context for team X | Member of team X (personal prompts appended automatically) |
| Promote personal → team X | Member of team X |
| Promote team X → team Y | Member of both X and Y |
| Set score | Team admin (same rule as agent instance admin) |
| Promote to marketplace | Global admin (P1-E, out of scope) |

---

## 4. Alternatives Considered

### 4.1 Full version history table

A `PromptVersion(prompt_id, version, text, updated_at, updated_by)` table
would allow diff views and text rollback. Rejected for V1: the simple
monotonic counter plus snapshot gives 80% of the value (detecting drift
between agent config and current library) at 5% of the complexity. Add if
user demand materialises.

### 4.2 Auto-propagate library updates to agents (live binding)

When the library prompt changes, all agents using it update automatically.
Rejected: same reasoning as PROMPT-SAFETY-RFC §3.4. Agents in production
would silently change behavior. The `prompt_refs` metadata + "update
available" banner gives the signal without the risk.

### 4.3 Denormalized "last used by" instead of counters

Storing the last user/session to use a prompt rather than counters.
Rejected: privacy concern (personal prompts would reveal which team members
used which prompts). Counters are sufficient for curation decisions and
reveal no individual behavior.

### 4.4 Score computed automatically from agent KPIs

Derive score from HITL rate, session length, user feedback signals.
Rejected for V1: requires evaluation track (O1) to land first. The admin-
settable float keeps the field live without coupling the release to O1
completion.

### 4.5 Separate context_template table for chat context prompts

A distinct table for "context prompts" vs "library prompts". Rejected:
the difference is in *how* a prompt is used, not in what it is. The same
text can serve as an agent system prompt and as a user's chat context.
One table with usage counters separated by type (`import_count` vs
`session_count`) is cleaner and avoids duplicated curation effort.

---

## 5. Impact on Existing Contracts

| Area | Change | Backward compatible |
|---|---|---|
| `prompt` DB table | 6 new columns via migration | Yes — nullable or defaulted |
| `agent_instance` DB table / JSON | `prompt_refs jsonb` column | Yes — nullable |
| `session` DB table | `context_prompt_id` column | Yes — nullable |
| `PromptSummary` schema | 6 new fields | Breaking for strict deserializers — OpenAPI regen required |
| `ExecutionPreparation` response | `context_prompt_text: str \| null` | Additive |
| `PATCH /sessions/{id}` body | `context_prompt_id` optional field | Additive |
| `controlPlaneOpenApi.ts` | Regenerate after P1-D1b backend lands | Required |
| `runtimeOpenApi.ts` | Regenerate after context_prompt_text lands in ExecutionPreparation | Required |

---

## 6. Out of Scope — This RFC

| Item | Where tracked |
|---|---|
| Global prompt marketplace (`PublishedPromptRow`, publish/unpublish) | P1-E |
| Token cost KPI integration (avg_input/output_tokens computation) | P1-F |
| Automatic score derivation from evaluation results | O1 + P1-F |
| Full text version history (PromptVersion table) | Future RFC if needed |
| "Prompt admin" role distinct from team admin | Future RFC if needed |
| Prompt search / tagging / categorisation | Future RFC |

---

## 7. Implementation Sequence

Four tasks in dependency order.

### P1-D1b — Backend extension (amends Codex's work)

**Owner**: Dimitri  
**Depends on**: P1-D1 (done)

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
  agent create/update → write prompt_refs when source is library import
  agent create/update → call increment_import_count
  session PATCH → accept context_prompt_id, call increment_session_count
  prepare_execution → resolve context_prompt_text from context_prompt_id

API (product/api.py):
  GET  /teams/{id}/prompts/context          → new endpoint
  POST /teams/{id}/prompts/{id}/promote     → new endpoint
  PATCH /teams/{id}/prompts/{id}            → new (score update)

Schemas (product/schemas.py):
  PromptSummary          ← add 6 analytics fields
  ContextPromptSummary   ← new
  PromptScoreUpdateRequest ← new
  PromptPromoteRequest   ← new
  ExecutionPreparation   ← add context_prompt_text

generate-openapi + commit controlPlaneOpenApi.ts
make code-quality && make test (control-plane-backend)
```

### P1-D2 — Frontend: PromptsPage + AgentFormModal

**Owner**: Félix or Dimitri  
**Depends on**: P1-D1b (OpenAPI regenerated)

```
PromptsPage (new rework page):
  Route: /teams/:teamId/prompts
  Nav entry in sidebar
  Table: name, description, version badge, import_count,
         session_count, score (stars | -), updated_at, actions
  Create modal: name (required), description, text textarea
  Edit modal: same fields, shows current version
  Delete with confirmation
  Score edit inline (admin only)
  "Promote to team" action → target team picker → POST promote

AgentFormModal (extends existing):
  [Import from library] → PromptPickerModal
    - shows team library (name, version, session_count, score)
    - search by name
    - preview panel
    - [Use] → copies text into textarea, stores prompt_ref internally
  [Save as prompt] → SavePromptModal (name, description → POST to team library)
  version badge when field has a prompt_ref:
    "Imported from [name] v2" — if version matches current → green
    "Imported from [name] v2 — current is v5" → amber + [Review]
  Inline 422 error display below textarea (list of PromptTemplateError)

tsc --noEmit + npm run build pass
```

### P1-D3 — Chat context picker

**Owner**: Félix  
**Depends on**: P1-D1b

```
AgentOptionsPanel or session init surface:
  Replace free textarea with a library picker
  Source: GET /teams/{team_id}/prompts/context
  Shows personal prompts (grouped) + team prompts (grouped)
  Ordered by session_count DESC
  Displays score stars when non-null
  User selects → PATCH /sessions/{id} { context_prompt_id }
  "Clear context" action → PATCH with context_prompt_id: null
  "Edit in personal library" shortcut → navigates to PromptsPage

make code-quality on frontend
```

### P1-F — Token cost KPI integration (DEFERRED)

**Owner**: Simon + Dimitri  
**Depends on**: O1 evaluation track, fred-core KPI store changes

```
Not in scope for this sprint.
Fields avg_input_tokens / avg_output_tokens exist in DB and schema.
UI displays "N/A" with tooltip: "Token data available after evaluation
integration lands."

When P1-F starts it will need its own RFC amendment covering:
  - context_prompt_id label in fred-core KPI turn events
  - aggregation query / worker
  - update path back to PromptRow
```

---

## 8. Open Questions — Resolved

| Question | Resolution |
|---|---|
| Versioning: immutable history vs counter? | Counter only (V1). Additive history table if demand materialises. |
| Live link at agent level? | No. Snapshot text + metadata prompt_refs for drift detection. |
| Live link at session level? | Yes — session is ephemeral, no permanence risk. |
| Personal prompts visible in team chat? | Yes — union query via /prompts/context endpoint. |
| Score source? | Admin-set float. Evaluation track (O1) may set it later via PATCH. |
| Token cost computation? | Deferred to P1-F. Fields reserved, display "N/A". |
| Promotion: conflict on same name? | 409 Conflict — caller renames first. |
| Promotion: does it transfer or copy? | Always copy. Source unchanged. |
