# RFC: Safe Prompt Authoring, Validation, and Library

**Status**: Slices A + B + C implemented (2026-05-07) · Slice D pending  
**Author**: Dimitri Tombroff  
**Date**: 2026-05-07  
**Area**: `fred-runtime`, `control-plane-backend`, `frontend`

---

## 1. Problem

### 1.1 The rendering crash

System prompt templates are rendered at execution time using Python's `str.format_map()`.  
The current `_LiteralFriendlyDict` guard handles one case — a simple unknown key:

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

All of these crash the agent silently at turn-start, returning a streaming error to the
user with zero indication that the system prompt is the cause.

Real production incident (2026-05-06):

```
AttributeError: 'str' object has no attribute 'toto'
  File "react_prompting.py", line 111, in render_prompt_template
      return template.format_map(
```

The trigger was a system prompt containing Excel VBA with curly braces:
`function main(workbook: ExcelScript.Workbook) { ... }`.

### 1.2 No validation at save time

The control-plane `_validate_tuning_field_values` treats `"prompt"` fields as free-form
strings — it stores any text unconditionally. Validation (and the crash) only surfaces
when the user sends their first message.

### 1.3 Poor creation UX in develop

In the `develop` (kea) flow:
1. Agent is created first (empty shell).
2. The system prompt is applied in a second update call.
3. If the prompt is rejected at step 2, the empty agent record already exists and
   must be manually deleted.

Swift's create flow is already atomic (`CreateAgentInstanceRequest` carries the full
payload), but validation still happens at execution time, not at creation time. The
practical outcome is identical: the agent is created, the user cannot chat with it,
and they have no actionable error message.

### 1.4 No independent prompt management

Today a prompt lives only as an inline string inside an agent instance. There is no
way to:
- author a prompt separately and reuse it across agents
- import an existing prompt when creating a new agent
- maintain a team-scoped library of approved prompts

---

## 2. Proposed Solution

Four independent slices, ordered by urgency.

### Slice A — Canonical token registry + safe rendering engine (`fred-sdk` + `fred-runtime`)

#### A.1 Central token registry

A single new module `fred_sdk.contracts.prompt_utils` defines the **canonical set of
supported template tokens**. This is the single source of truth — imported by the
renderer, the validator, and (eventually) the UI hint API.

```python
# fred_sdk/contracts/prompt_utils.py

PROMPT_SAFE_TOKENS: dict[str, str] = {
    "today":             "ISO-8601 date at execution time (e.g. 2026-05-07)",
    "response_language": "Human-readable response language (e.g. English, français)",
    "session_id":        "Active session identifier",
    "user_id":           "Authenticated user identifier",
    "agent_id":          "Agent definition identifier",
}
```

The dict value is a human-readable description — the validator returns it verbatim
in error messages so control-plane can forward it to the frontend without
reformatting.

Adding a new supported token requires editing exactly this dict and bumping the
changelog — no other site needs to change.

> **TODO (UI, deferred):** Expose `PROMPT_SAFE_TOKENS` via a lightweight read-only
> control-plane endpoint (e.g. `GET /control-plane/v1/prompt-tokens`) so that the
> prompt textarea can show an inline "supported variables" hint panel. Until that
> endpoint exists, the frontend can hard-code the list (imported from the generated
> OpenAPI schema once the endpoint exists). Tracked in BACKLOG as a UX improvement.

#### A.2 Safe rendering engine (pure bugfix, `fred-runtime`)

Replace `str.format_map()` with a regex-based substitution that **only rewrites
tokens present in the merged token map** and passes everything else through unchanged.

```
{today}              →  "2026-05-07"               (canonical token, substituted)
{response_language}  →  "English"                  (canonical token, substituted)
{my_custom_var}      →  "{my_custom_var}"           (not in map, preserved as literal)
{toto.toto}          →  "{toto.toto}"              (not a simple identifier, untouched)
{}                   →  "{}"                       (not a simple identifier, untouched)
function() { ... }   →  "function() { ... }"       (no brace pattern match, untouched)
```

**Implementation sketch** (not final code — for RFC clarity only):

```python
_SIMPLE_TOKEN_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')

def render_prompt_template(template: str, *, tokens: dict[str, str]) -> str:
    """Substitute only simple {identifier} patterns present in `tokens`.
    Non-matching patterns and unknown identifiers are preserved as literals."""
    def _replace(m: re.Match) -> str:
        return tokens.get(m.group(1), m.group(0))
    return _SIMPLE_TOKEN_RE.sub(_replace, template)
```

The pattern `[a-zA-Z_][a-zA-Z0-9_]*` matches only simple identifiers — it never
matches `toto.toto`, `0`, or the empty string. Those pass through unchanged.

**Two-tier token map:**

The renderer receives a merged `tokens` dict. For user-authored prompts (`prompts.*`
tuning values) this is built exclusively from `PROMPT_SAFE_TOKENS` values at runtime.
For SDK-level `system_prompt_template` fields authored by agent developers, the
renderer may also receive internal runtime tokens (e.g. `prompts_planning` from
`extra_tokens`). These two authoring surfaces are distinct:

| Surface | Authored by | Token set | Validated at persistence |
|---|---|---|---|
| `prompts.*` tuning value (UI form) | Team admin / end user | `PROMPT_SAFE_TOKENS` only | Yes — strict (Slice B) |
| `system_prompt_template` in Python `AgentDefinition` | Agent developer | `PROMPT_SAFE_TOKENS` + runtime extras | No — developer responsibility |

This distinction is why `extra_tokens` stays on the renderer's internal call path
but is never part of the user-facing validation contract.

**Scope**: `fred_runtime/react/react_prompting.py` (`render_prompt_template` +
`_LiteralFriendlyDict` removed). Same change applies to
`fred_runtime/deep/deep_runtime.py` which imports the same function.

**No API contract change.** No migration. No schema change.

---

### Slice B — Prompt template validation at persistence (`control-plane-backend`)

Add `validate_prompt_template(text: str) -> list[PromptTemplateError]` to
`fred_sdk.contracts.prompt_utils`. The control-plane service calls this before
storing any `prompts.*` field value.

```python
class PromptTemplateError(BaseModel):
    pattern: str          # the offending text fragment
    reason: str           # human-readable explanation
    token_hint: str | None = None  # set when a close-but-wrong token is detected
```

The validator runs two passes:

**Pass 1 — Non-simple brace patterns (always an error):**

Scan for `{...}` sequences that do NOT match `[a-zA-Z_][a-zA-Z0-9_]*`. These
patterns are always errors regardless of intent — they cannot be valid template
tokens and would have crashed the old renderer:

| Found | Error reason |
|---|---|
| `{}` | "Empty placeholder — not a valid template token" |
| `{0}`, `{1}` | "Positional placeholder — not supported in prompt templates" |
| `{toto.toto}` | "Dotted attribute syntax is not supported in prompt templates" |
| `{ space }` | "Whitespace in placeholder — not a valid template token" |

**Pass 2 — Unknown simple tokens (also an error):**

Scan for `{identifier}` patterns. Any identifier **not in `PROMPT_SAFE_TOKENS`**
is an error. The error message includes the full list of supported tokens so the
user knows exactly what they can use:

```
"Unknown template token '{my_var}'. Supported tokens: {today}, {response_language},
{session_id}, {user_id}, {agent_id}."
```

**Validation policy at the API layer — strict:**

| Situation | HTTP response |
|---|---|
| Any non-simple brace pattern | `422` with list of `PromptTemplateError` |
| Any unknown `{identifier}` token | `422` with list of `PromptTemplateError` |
| Template contains no `{...}` patterns | `200` / `201` — plain text, always valid |
| Template uses only canonical tokens | `200` / `201` |

No warnings, no partial acceptance. A prompt either passes or the create/update is
rejected. The error payload lists every offending pattern in one response so the
user can fix all of them at once.

**Where validation is called:**

- `_validate_tuning_field_values()` — when `field.type == "prompt"`, run the validator.
- Same call added to Slice D prompt library create/update.

**Shared location**: `fred_sdk.contracts.prompt_utils` — imported by
`control-plane-backend` with no dependency on `fred-runtime`.

---

### Slice C — Atomic creation guarantee (control-plane-backend, already partially true)

Swift already sends the full payload in a single `CreateAgentInstanceRequest`.  
With Slice B in place, validation runs before the INSERT — the agent is either
created fully valid or not created at all.

**What this slice adds:**

- Explicit test coverage for the create-then-reject scenario (bad prompt → 422,
  no agent row written; fix prompt → 201, agent created).
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

- The frontend `AgentFormModal` must surface these errors **next to the prompt
  textarea**, not as a generic toast. The `errors[].reason` strings come directly
  from the backend and are human-readable enough to display without transformation.
  (UI implementation deferred — tracked as a TODO in `CHAT-UI-BACKLOG.md`.)

---

### Slice D — Prompt Library (new control-plane feature)

A team-scoped first-class `Prompt` entity, managed independently of agent instances.

#### D.1 Data model

```
Prompt
  id:           UUID (generated)
  team_id:      UUID (foreign key)
  name:         str   (human label, unique within team)
  description:  str | None
  text:         str   (the prompt template text)
  created_by:   str   (user_id of the author)
  created_at:   datetime
  updated_at:   datetime
```

Prompts are team-scoped. There is no cross-team sharing in this slice.

No versioning in this slice — a prompt is a mutable record. If versioning is needed
it will be an explicit follow-up RFC.

#### D.2 Endpoints (control-plane-backend)

```
POST   /control-plane/v1/teams/{team_id}/prompts            → 201 PromptSummary
GET    /control-plane/v1/teams/{team_id}/prompts            → 200 list[PromptSummary]
GET    /control-plane/v1/teams/{team_id}/prompts/{id}       → 200 PromptDetail
PUT    /control-plane/v1/teams/{team_id}/prompts/{id}       → 200 PromptSummary
DELETE /control-plane/v1/teams/{team_id}/prompts/{id}       → 204
```

`POST` and `PUT` run the Slice B validator — a prompt with an invalid template is
rejected before storage.

`PromptSummary`: `{ id, name, description, created_by, created_at, updated_at }` (no `text`).  
`PromptDetail`: all fields including `text`.

#### D.3 Import into an agent instance

When an agent creator opens the `AgentFormModal` and selects a prompt from the library,
the frontend copies the prompt `text` into the `prompts.system` field of the form.
**No live reference is stored** — the instance captures the text as a snapshot.

Rationale:
- Avoids broken agent instances when a library prompt is deleted or renamed.
- Agent configuration remains self-contained — operators can audit it without
  cross-referencing the prompt library.
- The cost is that changes to a library prompt do not propagate automatically. This is
  intentional at this stage; automatic propagation is a different feature and needs
  its own RFC.

The UX flow:

```
AgentFormModal
  └── [Prompts] tab
        ├── Prompt textarea (manual entry)
        └── [Import from library] button
              └── PromptPickerModal
                    ├── search / filter by name
                    ├── preview panel (read-only text)
                    └── [Use this prompt] → copies text into the textarea
```

After import, the textarea is editable — the user can refine the imported text.
The "source" prompt ID is not stored in the agent instance.

#### D.4 Authorization

Prompt CRUD uses the same team membership check as agent instance CRUD:
the caller must be a member of the team.

No separate "prompt admin" role in this slice.

---

## 3. Alternatives Considered

### 3.1 Keep `format_map` but wrap in try/except and return an error event

Rejected. An error event mid-conversation is worse than a 422 at save time.
The agent appears broken with no actionable message.

### 3.2 Escape all literal braces at save time (`{` → `{{`)

Rejected. This permanently mutates the stored text. A prompt containing
`{today}` would be stored as `{{today}}` and the author sees a different string
than what they typed. Round-trips break.

### 3.3 Use a full template engine (Jinja2, Mako)

Rejected. The template surface is intentionally small — five canonical tokens,
strict whitelist. A full template engine adds a dependency, a security surface
(template injection), and a much more complex validation story, with no
commensurate benefit at this scale.

### 3.4 Store prompt by reference in agent instance (live link)

Rejected for this slice. Adds referential integrity constraints, cascade
semantics, and "what happens to agents when the prompt is deleted" policy that
we do not want to decide now. Snapshot is conservative and reversible.

### 3.5 Prompt versioning

Deferred to a follow-up RFC. The library starts as a simple mutable record.

---

## 4. Impact on Existing Contracts

| Area | Change | Backward compatible |
|---|---|---|
| `fred_sdk.contracts.prompt_utils` | New module: `PROMPT_SAFE_TOKENS` constant + `PromptTemplateError` model + `validate_prompt_template()` | Additive |
| `fred_runtime/react/react_prompting.py` | `render_prompt_template` reimplemented using regex + `PROMPT_SAFE_TOKENS`; `_LiteralFriendlyDict` removed | Yes — same function signature, broader safety |
| `fred_runtime/deep/deep_runtime.py` | Same `render_prompt_template` import; no logic change needed | Yes |
| `control_plane_backend/product/service.py` | `_validate_tuning_field_values` calls `validate_prompt_template` for `"prompt"` type fields | New 422s for previously accepted bad input — intentional breaking change for correctness |
| Control-plane OpenAPI | New `/prompts` resource (Slice D); 422 error shape gains `errors: list[PromptTemplateError]` | Additive for `/prompts`; error shape is new field |
| `controlPlaneOpenApi.ts` | Regenerated after D lands | Additive |
| `AgentFormModal` | Inline error display next to prompt textarea; [Import from library] button (Slice D, UI) | UI addition |
| DB | New `prompts` table + migration (Slice D) | Additive |

---

## 5. Open Questions

| # | Question | Owner | Blocking |
|---|---|---|---|
| Q1 | Is the `PromptPickerModal` in scope for the same sprint as Slice D backend? Proposed: yes, but it blocks on the OpenAPI regen. | Félix | Slice D frontend |

**Resolved decisions:**
- Unknown tokens (simple or complex) → **block with 422**, no warnings accepted.  
- User-authored prompts (`prompts.*` via UI) are validated against `PROMPT_SAFE_TOKENS` only — internal `extra_tokens` used by agent developer-authored `system_prompt_template` are not part of the user-facing validation contract.  
- Library prompt `text` is validated with the same Slice B validator at create/update time.

---

## 6. Implementation Sequence

```
Slice A  (fred-runtime, no API change)
  ↓
Slice B  (control-plane-backend, shared validator in fred-sdk)
  ↓
Slice C  (test coverage + error shape — done when B lands)
  ↓
Slice D  (DB migration + endpoints + frontend picker — separate branch)
```

Slices A and B can land in the same PR (they are tightly coupled — fix the renderer
and validate at the gate in one move).

Slice D is independent and can start in parallel once A+B are merged.
