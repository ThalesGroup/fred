# RFC — Prompt System Completion and Hardening

**Status:** Proposed  
**Author:** Dimitri Tombroff / Codex  
**Date:** 2026-06-26  
**Area:** `control-plane-backend`, `frontend`, `fred-sdk`, `fred-runtime`  
**Current design:** [`PROMPTS.md`](../design/PROMPTS.md)  
**Tracks:** `PROMPT-04`, `PROMPT-06`, `PROMPT-07`

## 1. Problem

The shipped prompt system is usable and covered by the current design document,
but the code audit found remaining gaps that should be handled as explicit
implementation work rather than left buried in historical RFCs.

The important gaps are:

- `AgentFormModal` prompt workflows are still incomplete: import, save as prompt,
  version drift, and inline 422 prompt-template errors.
- `prompt_refs_json` exists on agent instances, but frontend-backed import
  traceability is not fully closed.
- `promote_prompt` copies the prompt name, description, and text, but drops
  category, emoji, and tags.
- Context prompt resolution still uses a raw `PromptStore.get(prompt_id)` during
  prepare-execution. The session row is user/team scoped, but the prompt lookup
  itself should be made explicitly scope-aware to keep the invariant local.
- The prompt validator intentionally rejects only unknown simple `{identifier}`
  tokens. The UI and docs must keep saying that non-simple brace patterns are
  literals, not validation errors.
- Global marketplace publication and per-prompt token KPI aggregation remain
  deferred despite fields and UI placeholders already existing.

## 2. Proposed Work

### 2.1 Complete Agent-Form Prompt UX (`PROMPT-04`)

Add prompt controls to every agent form field declared with `type == "prompt"`:

- Import from library: picker shows personal, team, and default prompts, with
  name, scope, version, usage count, score, and preview.
- Save as prompt: copies the current field text into a new prompt-library record.
- Version drift badge: when `prompt_refs_json` exists, show whether the copied
  prompt text came from the current source version or an older one.
- Inline 422 rendering: prompt-template validation errors appear below the
  textarea, not only as a generic toast.

Acceptance:

- importing a prompt copies text into `prompts.*`
- manual edits clear or mark the reference stale
- save-as-prompt uses the same validation behavior as prompt-library create
- frontend tests cover import, save, stale badge, and inline validation error UX

### 2.2 Close Prompt Reference Traceability

Make `prompt_refs_json` a reliable metadata map from prompt-tuning field to the
source library prompt snapshot:

```json
{
  "prompts.system": {
    "prompt_id": "abc-123",
    "version": 4,
    "scope": "team",
    "team_id": "bid-and-capture"
  }
}
```

Rules:

- import writes the reference and increments `import_count`
- manual overwrite clears the reference for that field
- deleting the source prompt never breaks the agent because the text remains
  copied into tuning

### 2.3 Harden Scope-Aware Resolution

Replace prepare-execution prompt resolution with an explicitly scoped resolver.
For a session in team `T` owned by user `U`, each non-default context prompt must
resolve only if it is:

- a prompt in `T`
- or a prompt in `personal_team_id(U)`

Deleted or no-longer-readable prompt ids should still be skipped rather than
breaking the conversation.

Acceptance:

- unit tests prove a prompt from another team is not injected into
  `context_prompt_text`
- raw `PromptStore.get(prompt_id)` is not used in auth-sensitive prompt
  resolution paths

### 2.4 Preserve Metadata On Promotion

Update prompt promotion so copy-by-value preserves:

- `category`
- `emoji`
- `tags`
- text, name, and description

Acceptance:

- promotion tests assert the full authoring metadata is copied
- target-team name conflicts still return HTTP 409

### 2.5 Keep Validation Semantics Explicit

Do not reintroduce the old strict-brace assumption unless the team makes a new
product decision. Current behavior is:

- unknown simple tokens such as `{customer_name}` are rejected
- non-simple brace patterns such as `{}`, `{0}`, `{object.attr}`, and code braces
  are literals

Acceptance:

- SDK tests continue to cover literal brace preservation
- UI helper text matches the actual validator

### 2.6 Marketplace (`PROMPT-06`)

Add a separate published-prompt resource for global marketplace entries. This
must remain copy-by-value:

- team prompt to marketplace creates a published snapshot
- marketplace import copies text into the target context
- editing a team prompt never mutates already-published marketplace entries

The marketplace should not reuse mutable team prompt rows as global records.

### 2.7 Token KPI Aggregation (`PROMPT-07`)

Connect the existing nullable fields to real measurements:

- emit or derive labels for context prompt id and agent prompt version
- aggregate average input and output tokens per prompt
- write `avg_input_tokens` and `avg_output_tokens` back to prompt summaries

This likely depends on the evaluation/KPI track and should not block `PROMPT-04`.

## 3. Non-Goals

- No change to the runtime scalar `RuntimeContext.context_prompt_text` contract.
- No live binding from an agent instance back to mutable prompt-library text.
- No marketplace moderation model in this RFC.
- No change to the shipped default prompt catalog.
