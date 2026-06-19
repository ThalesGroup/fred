> **⚠️ Historical — superseded 2026-06-19.** The locked decisions in this amendment
> (personal = `personal/{user_id}`, team-curated write rules, scope-aware resolution,
> `prompt_refs` traceability) have been folded into the authoritative, compact as-built
> contract [`PROMPT-LIBRARY-RFC.md`](PROMPT-LIBRARY-RFC.md) §"Scope & authorization".
> Retained for rationale; no longer the current contract.

# RFC Amendment — Prompt Library Team Scope and Governance

**Status:** Draft for team review  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-23  
**Area:** `control-plane-backend`, `frontend`, `fred-runtime`  
**Amends:** `PROMPT-LIBRARY-RFC.md`

---

## 1. Why this amendment exists

The prompt library RFC established the right product direction, but three points
must be tightened before implementation continues:

1. personal prompts must be truly personal, not a shared `personal` namespace
2. shared team prompts must follow the same governance boundary as other team
   resources
3. prompt import into agents must preserve traceability through `prompt_refs`

This amendment keeps the original prompt-library architecture, but corrects the
scope and authorization rules.

---

## 2. Locked decisions

### 2.1 Route surface stays the same

The public route family remains:

```text
/control-plane/v1/teams/personal/prompts
/control-plane/v1/teams/{team_id}/prompts
```

There is still no separate `/users/{user_id}/prompts` API.

### 2.2 Personal scope no longer means shared team id only

The reserved `personal` route family remains for UX and navigation continuity,
but persistence must distinguish one caller's personal library from another's.

Logical rule:

- `personal` means `personal/{caller_user_id}`

Shared team rule:

- collaborative team prompts mean `team/{team_id}`

---

## 3. Logical data model

This amendment locks semantic identity, not one exact SQL shape.

```python
class PromptScope(BaseModel):
    kind: Literal["personal", "team"]
    team_id: TeamId
    owner_user_id: str | None = None
```

Semantic invariants:

- if `kind == "personal"`, then `team_id == "personal"` and `owner_user_id` is
  required
- if `kind == "team"`, then `team_id != "personal"` and `owner_user_id` is null

Logical uniqueness:

- personal prompt names are unique per `(owner_user_id, name)`
- team prompt names are unique per `(team_id, name)`

The implementation may choose columns or partial indexes as needed, but these
logical rules are fixed.

---

## 4. Authorization model

### 4.1 Personal prompts

Allowed:

- caller creates, reads, updates, deletes their own personal prompts

Rejected:

- any user reads or mutates another user's personal prompt

### 4.2 Shared team prompts

Read:

- any member of the team

Write:

- team manager
- team owner

Product meaning:

- shared team prompts are curated team resources
- they do not use simple membership as a write rule

### 4.3 Prompt score

`score` is team curation metadata.

Rules:

- team prompts only
- writable by team manager or team owner
- not allowed on personal prompts in V1

### 4.4 Promotion

Personal -> team:

- caller must own the personal prompt
- caller must be manager or owner of the target team

Team -> team:

- caller must be manager or owner of the source team
- caller must be manager or owner of the target team

Promotion remains copy-by-value only.

---

## 5. Context-picker rule

For one team conversation in team `X`, the context picker must return:

- the caller's personal prompts
- plus the shared prompts of team `X`

If `X == personal`, the result contains only the caller's personal prompts.

This keeps the product behavior simple:

- personal prompts follow the user
- team prompts follow the active team

---

## 6. Session context authorization

When the frontend sends:

```text
PATCH /teams/{team_id}/sessions/{session_id}
{ "context_prompt_id": "..." }
```

the backend must accept the prompt only if it resolves to exactly one of:

1. a personal prompt owned by the caller
2. a team prompt readable in the current `team_id`

If the prompt does not resolve under those rules, the request is rejected.

`prepare_execution` then resolves `context_prompt_text` using the same scope
rules. Deleted prompts are treated as:

- no context text injected
- session remains valid

---

## 7. Agent import contract

Importing a prompt into an agent remains copy-by-value.

The imported text is copied into the matching `prompts.*` field, and the control
plane writes a metadata back-reference:

```json
{
  "prompts.system": {
    "prompt_id": "abc-123",
    "version": 4,
    "scope_kind": "team",
    "team_id": "bid-and-capture"
  }
}
```

If the source was personal, the metadata also carries the logical owner:

```json
{
  "prompts.system": {
    "prompt_id": "abc-123",
    "version": 2,
    "scope_kind": "personal",
    "team_id": "personal",
    "owner_user_id": "alice"
  }
}
```

Rules:

- writing or replacing a prompt import increments `import_count`
- manually overwriting the field clears the corresponding `prompt_ref`
- deleting the source library prompt never breaks the agent because the agent
  still stores copied text

---

## 8. Store and service rules

The following service rule becomes mandatory:

- raw `get(prompt_id)` is not sufficient for personal-prompt authorization

Any auth-sensitive resolution must include logical scope:

- personal prompt lookup must filter by `owner_user_id`
- team prompt lookup must filter by `team_id`

This applies to:

- CRUD
- context picker
- session context resolution
- prompt promotion
- prompt score updates
- prompt import / `prompt_refs`

---

## 9. Superseded assumptions from the original prompt RFC

This amendment supersedes the following product assumptions in
`PROMPT-LIBRARY-RFC.md`:

1. "`personal` is sufficient as a stored prompt scope"
2. "team prompt CRUD may be treated as generic team membership writes"
3. "set score is a generic admin action without explicit team-resource
   ownership mapping"
4. "prompt import metadata may stay deferred without affecting governance"

Everything else remains valid:

- prompt library as a first-class control-plane resource
- copy-by-value import into agents
- live session reference for chat context
- marketplace as a later, separate resource

---

## 10. Non-goals

This amendment still does not introduce:

- live prompt binding into agents
- per-prompt ACLs beyond personal versus team scope
- a global marketplace implementation
- automatic score derivation

It only makes the existing prompt-library direction safe and unambiguous at team
scope.
