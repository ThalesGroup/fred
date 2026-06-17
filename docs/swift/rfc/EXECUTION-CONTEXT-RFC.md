# RFC — Execution Context: Data Model Audit and Cleanup

**Status**: Implemented (2026-05-11)  
**Author**: Dimitri Tombroff  
**Date**: 2026-05-11  
**Area**: `fred-sdk`, `control-plane-backend`, `fred-runtime`, `frontend`

---

## 1. Why This RFC Exists

Before implementing the PROMPT-05 chat context picker and the `bound_library_ids` feature,
we need to agree on the data model. The current model is not as clean as expected.
This RFC maps it precisely, names the problems, and proposes the minimum change.

The goal is **fewer models, better types, no new code** — not a redesign.

---

## 2. Complete Data Model As It Exists Today

### 2.1 The four context layers (from frontend to runtime)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONTROL-PLANE: ExecutionPreparation                                        │
│  Backend → Frontend (before each send)                                      │
│                                                                             │
│  effective_chat_options: EffectiveChatOptions   ← what to show the user    │
│  context_prompt_text: str | None                ← resolved prompt text      │
│  execution_grant: ExecutionGrant                ← authorization envelope    │
│  execute_stream_url: str                        ← where to send             │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ frontend reads, then sends:
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SDK: RuntimeExecuteRequest                                                 │
│  Frontend → Runtime (each turn)                                             │
│                                                                             │
│  agent_instance_id: str                         ← execution target          │
│  input: str                                     ← user turn text            │
│  session_id: str | None                         ← conversation continuity   │
│  execution_grant: ExecutionGrant                ← authorization (typed)     │
│  runtime_context: dict[str, Any] | None         ← ⚠ untyped bag            │
│  resume_payload: Any | None                     ← HITL resume data          │
│  invocation_turns: tuple[ConversationTurn, ...] ← sub-agent memory         │
│  inline_tuning: dict[str, TuningValue] | None   ← dev/CLI only             │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ runtime adapter unpacks dict into:
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SDK: BoundRuntimeContext                                                   │
│  Internal to runtime (during one agent turn)                                │
│                                                                             │
│  runtime_context: RuntimeContext     ← typed but large (18 fields, mutable) │
│  portable_context: PortableContext   ← clean identity + tracing (preferred) │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 `RuntimeContext` — the actual fields

`fred_sdk.contracts.context.RuntimeContext` (Pydantic `BaseModel`, **NOT frozen**):

```
Group A — Identity (superseded by ExecutionGrant)
  user_id:              str | None
  team_id:              str | None
  session_id:           str | None
  exchange_id:          str | None
  checkpoint_id:        str | None
  agent_instance_id:    str | None
  template_agent_id:    str | None
  trace_id:             str | None
  correlation_id:       str | None
  execution_action:     Literal["execute", "resume"] | None

Group B — Auth delegation (user token forwarded to knowledge backend calls)
  access_token:             str | None        ← MUTABLE (refreshed in place)
  refresh_token:            str | None        ← MUTABLE (refreshed in place)
  access_token_expires_at:  int | None        ← MUTABLE (refreshed in place)

Group C — Per-turn user retrieval selections
  selected_document_libraries_ids: list[str] | None
  selected_document_uids:          list[str] | None
  search_policy:                   str | None   ← ⚠ should be Literal
  search_rag_scope:                Literal["corpus_only","hybrid","general_only"] | None
  include_session_scope:           bool | None
  include_corpus_scope:            bool | None
  deep_search:                     bool | None
  selected_chat_context_ids:       list[str] | None

Group D — Content and preferences
  language:            str | None
  user_groups:         list[str] | None
  attachments_markdown: str | None
```

### 2.3 `PortableContext` — the clean model already in the SDK

`fred_sdk.contracts.context.PortableContext` (frozen, typed):

```
request_id, correlation_id, actor, tenant, environment,
trace_id, client_app, agent_id, agent_name, agent_version,
session_id, user_id, user_name, team_id, baggage
```

This is the "preferred v2 contract" per the code comment. It covers Group A from
`RuntimeContext` cleanly. But it is parallel to, not a replacement for,
`RuntimeContext` today — both live in `BoundRuntimeContext` side by side.

### 2.4 `EffectiveChatOptions` — what the backend declares

`control_plane_backend.product.schemas.EffectiveChatOptions`:

```python
attach_files: bool = False
libraries_selection: bool = False          # show library picker?
documents_selection: bool = False          # show document picker?
search_policy_selection: bool = False      # show policy picker?
default_search_policy: Literal[...]        # initial value
rag_scope_selection: bool = False          # show scope picker?
default_search_rag_scope: Literal[...]     # initial value
```

Missing: no remaining blocker in `EffectiveChatOptions`; `bound_library_ids` and
`documents_selection` belong to the same typed chat-affordance surface.

### 2.5 `ExecutionPreparation` — the full preparation response

Already has `context_prompt_text: str | None` (computed, but never consumed by the
frontend — the wire to `RuntimeContext` does not exist).

---

## 3. The Real Problems

### 3.1 `RuntimeContext` mixes four orthogonal concerns in one model

The model is not frozen. It is mutated at runtime for auth token refresh:

```python
# adapters.py line 1108 — direct mutation:
runtime_context.access_token = new_access_token
runtime_context.refresh_token = new_refresh_token
runtime_context.access_token_expires_at = int(expires_at)
```

A context model should not be mutable state. The auth token refresh pattern
works today but is an architectural smell: the context is used simultaneously as
an immutable execution descriptor AND as a mutable auth state bag.

### 3.2 Group A fields duplicate `ExecutionGrant`

`RuntimeExecuteRequest` already has a typed `execution_grant: ExecutionGrant` that
carries `user_id`, `team_id`, `agent_instance_id`, `session_id`, `trace_id`, etc.
`RuntimeContext.user_id`, `team_id`, etc. are duplicates. The runtime even has
`effective_user_id()` / `effective_team_id()` helpers that prefer the grant over
the dict — acknowledging the duplication explicitly.

### 3.3 `runtime_context` is `dict[str, Any]` in the execute request

`RuntimeExecuteRequest.runtime_context: dict[str, Any] | None` — even though
`RuntimeContext` (a typed Pydantic model with all the right fields) exists in the
same SDK. The dict type means:

- Pydantic does not validate the fields at the boundary
- The frontend-generated TypeScript type for `RuntimeContext` comes from the
  **agentic-backend** OpenAPI schema (a legacy service), not from fred-sdk
- Any new field added to `RuntimeContext` must be manually mirrored in
  `agenticOpenApi.ts` (or regenerated)

### 3.4 `search_policy` is weakly typed

`RuntimeContext.search_policy: str | None` — it should be:
`Literal["strict", "hybrid", "semantic"] | None`. The literal type already exists
on `EffectiveChatOptions.default_search_policy` but is not on `RuntimeContext`.

### 3.5 The EffectiveChatOptions → RuntimeContext round-trip is undocumented

No document states the mapping from "backend declares X" to "frontend sends Y".
The symmetry exists only in the code:

| EffectiveChatOptions declares   | Frontend state                                      | RuntimeContext field sent         |
| ------------------------------- | --------------------------------------------------- | --------------------------------- |
| `libraries_selection: true`     | `selectedLibraryIds: string[]`                      | `selected_document_libraries_ids` |
| `documents_selection: true`     | `selectedDocumentUids: string[]`                    | `selected_document_uids`          |
| `search_policy_selection: true` | `searchPolicy: "strict"\|"hybrid"\|"semantic"`      | `search_policy`                   |
| `rag_scope_selection: true`     | `ragScope: "corpus_only"\|"hybrid"\|"general_only"` | `search_rag_scope`                |

### 3.6 Two things missing

- `bound_library_ids` — absent from `EffectiveChatOptions`; `ComposerSettingsControls` has UI code for it (bound-library read-only chip); `AgentOptionsPanel` retired 2026-05-24
- `context_prompt_text` wire — `ExecutionPreparation` computes it; frontend ignores it; `RuntimeContext.selected_chat_context_ids` exists but holds IDs not text

---

## 4. What NOT to Do

Do not create a new `ChatContext` model. `RuntimeContext` already exists with all
the relevant typed fields (Group C). Creating a parallel model would be:

- more code, not less
- a second source of truth for the same fields
- another migration step later

Do not redesign the auth token pattern in this RFC. The mutation of
`access_token` / `refresh_token` is a real requirement (the runtime uses the
user's token to call knowledge backend APIs on behalf of the user). Removing or
replacing it requires a separate architectural decision about service-to-service
auth — out of scope here.

---

## 5. Proposed Changes — Minimum Necessary

### 5.1 Fix the type of `runtime_context` in `RuntimeExecuteRequest`

**One line change in `fred_sdk/contracts/execution.py`:**

```python
# Before:
runtime_context: dict[str, Any] | None = Field(default=None, description="...")

# After:
runtime_context: RuntimeContext | None = Field(
    default=None,
    description=(
        "Per-request execution context carrying per-turn user selections "
        "(library IDs, search policy, context prompt text) and user auth delegation. "
        "Identity fields (user_id, team_id, session_id) in this model are superseded "
        "by execution_grant for managed execution — set them only for dev/direct mode. "
        "Auth token fields (access_token, refresh_token) are required when the runtime "
        "makes authenticated upstream calls (knowledge flow) on behalf of the user."
    ),
)
```

This removes `Any` completely. Pydantic now validates the boundary. The frontend
TypeScript type for `RuntimeContext` is regenerated from the fred-runtime OpenAPI
schema (not the legacy agentic-backend schema).

**Import needed** — add to the imports at top of `execution.py`:

```python
from .context import ConversationTurn, RuntimeContext
```

### 5.2 Fix `search_policy` type in `RuntimeContext`

**One line change in `fred_sdk/contracts/context.py`:**

```python
# Before:
search_policy: str | None = None

# After:
search_policy: Literal["strict", "hybrid", "semantic"] | None = None
```

### 5.3 Add `context_prompt_text` to `RuntimeContext`

**One field addition in `fred_sdk/contracts/context.py`:**

```python
context_prompt_text: str | None = None
```

This is the resolved text forwarded from `ExecutionPreparation.context_prompt_text`.
The runtime injects it as a conversation-level context before the user message.

### 5.4 Add `bound_library_ids` to `EffectiveChatOptions`

**One field addition in `control_plane_backend/product/schemas.py`:**

```python
bound_library_ids: list[str] | None = Field(
    default=None,
    description=(
        "When non-null, the agent is configured to use exactly these library IDs. "
        "The frontend must render the library picker as read-only and must send "
        "exactly this list in RuntimeContext.selected_document_libraries_ids. "
        "Null means the user can freely select from all available libraries."
    ),
)
```

**Wire in `service.py`:** resolve from `chat_options.bound_library_ids` tuning field
value when present on the agent instance.

### 5.5 Deprecate Group A identity fields on `RuntimeContext`

Add a deprecation note to the docstring of `RuntimeContext` on the Group A fields.
No removal yet — backward compat required. Removal happens when `agentic-backend`
is retired from the execution path.

---

## 6. The Canonical Mapping Table (now a documented contract)

This table is the authoritative source for the EffectiveChatOptions → RuntimeContext round-trip.

| `EffectiveChatOptions`                     | Meaning                           | Frontend state                                   | `RuntimeContext` field sent                          |
| ------------------------------------------ | --------------------------------- | ------------------------------------------------ | ---------------------------------------------------- |
| `libraries_selection: true`                | Show library picker (free choice) | `selectedLibraryIds: string[]`                   | `selected_document_libraries_ids`                    |
| `documents_selection: true`                | Show document picker              | `selectedDocumentUids: string[]`                 | `selected_document_uids`                             |
| `libraries_selection: false`               | Hide library picker               | —                                                | `selected_document_libraries_ids: null`              |
| `documents_selection: false`               | Hide document picker              | —                                                | `selected_document_uids: null`                       |
| `bound_library_ids: string[]`              | Show picker read-only (locked)    | Fixed to `bound_library_ids`                     | `selected_document_libraries_ids` = those IDs        |
| `bound_library_ids: null`                  | Picker is free-choice             | User-selected                                    | `selected_document_libraries_ids` = user choice      |
| `search_policy_selection: true`            | Show search policy picker         | `searchPolicy` init from `default_search_policy` | `search_policy`                                      |
| `search_policy_selection: false`           | Hide search policy picker         | —                                                | `search_policy: null`                                |
| `default_search_policy`                    | Initial value for picker          | sets initial `searchPolicy` state                | —                                                    |
| `rag_scope_selection: true`                | Show RAG scope picker             | `ragScope` init from `default_search_rag_scope`  | `search_rag_scope`                                   |
| `rag_scope_selection: false`               | Hide RAG scope picker             | —                                                | `search_rag_scope: null`                             |
| `default_search_rag_scope`                 | Initial value for picker          | sets initial `ragScope` state                    | —                                                    |
| `attach_files: true/false`                 | Show/hide attachment UI           | —                                                | `attachments_markdown` (populated by upload handler) |
| `ExecutionPreparation.context_prompt_text` | Resolved context prompt text      | forwarded automatically                          | `context_prompt_text`                                |

**Rule:** before every send, the frontend constructs `RuntimeContext` from current local
state using this table exactly. Identity fields (`user_id`, `team_id`, `session_id`)
are NOT set by the frontend — they are set by the runtime adapter from `ExecutionGrant`.
Auth token fields (`access_token`, `refresh_token`) are set as they are today.
`context_prompt_text` is forwarded from the last `ExecutionPreparation` response;
it changes only when the user changes the session context prompt (PROMPT-05).

---

## 7. Frontend Changes Required

After OpenAPI regeneration from the fred-runtime schema (not the agentic-backend schema):

1. **`useChatSse.ts`**: switch to the regenerated `RuntimeContext` type from
   `runtimeOpenApi.ts` instead of the legacy type from `agenticOpenApi.ts`. Read
   `context_prompt_text` from the prep response and include it in the context object.

2. **`useManagedChat.ts`**: read `effective_chat_options.bound_library_ids` and
   expose it as `boundLibraryIds` to `ManagedChatPage`.

3. **`ComposerSettingsControls`**: `boundLibraryIds` prop is already wired in the UI
   code (bound-library read-only chip) — it just needs a real value from the backend
   (this is dead code becoming live). `AgentOptionsPanel` retired 2026-05-24.

---

## 8. The Bigger Picture: `RuntimeContext` Needs to Shrink

This RFC makes the minimum change. The longer-term direction — tracked separately,
not for this sprint — is to slim `RuntimeContext` by removing the groups that now
have better homes:

| Group                   | Current state                                                                                           | Target                                                   |
| ----------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| A — Identity            | Duplicates ExecutionGrant                                                                               | Remove once ExecutionGrant is enforced everywhere        |
| B — Auth delegation     | Mutable; required for upstream KF calls                                                                 | Replace with service-to-service auth when infra is ready |
| C — Per-turn selections | **CORE** — keep these, improve types                                                                    | Done by this RFC                                         |
| D — Content/preferences | `language` belongs in session preferences; `user_groups` in identity; `attachments_markdown` is content | Move to proper homes over time                           |

The right end state for `RuntimeContext` is Group C only:
a small, focused, typed model carrying exactly the per-turn user selections that
the runtime needs to route retrieval calls correctly. Until then, keep it as-is
minus the `dict[str, Any]` problem.

---

## 9. What This Enables (and What It Doesn't)

**Enabled immediately:**

- Typed execute request — Pydantic validates the boundary, no `Any`
- `bound_library_ids` works end to end
- `context_prompt_text` wired — PROMPT-05 can proceed
- Round-trip is documented — no developer needs to grep the frontend to understand what the runtime expects
- `search_policy` is now a literal type — frontend type system catches invalid values

**Not changed:**

- Auth token mutation pattern (still required, tracked separately)
- Group A identity field duplication (deprecated, removed when agentic-backend retires)
- The large shape of `RuntimeContext` (will shrink over time)
- agentic-backend legacy paths (still need the dict-compatible path temporarily)

**Future extensibility:**
Adding knowledge backend options (when that interaction is designed) means adding
fields to `RuntimeContext` Group C and a corresponding declaration to
`EffectiveChatOptions`. The round-trip protocol stays exactly the same.

---

## 10. Impact on Existing Contracts

| Area                                                         | Change                                                                             | Backward compatible                                                                                                                                |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fred_sdk.contracts.execution`                               | `runtime_context` field type: `dict[str, Any]` → `RuntimeContext`                  | Breaking at the Pydantic boundary — existing callers that pass a plain dict will need updating (the dict fields are unchanged, just now validated) |
| `fred_sdk.contracts.context.RuntimeContext`                  | `search_policy` typed as `Literal`; `context_prompt_text` field added              | Additive                                                                                                                                           |
| `control_plane_backend.product.schemas.EffectiveChatOptions` | `bound_library_ids` field added                                                    | Additive                                                                                                                                           |
| `runtimeOpenApi.ts`                                          | Regenerated — `RuntimeContext` type now correct and authoritative                  | Required                                                                                                                                           |
| `controlPlaneOpenApi.ts`                                     | Regenerated — `EffectiveChatOptions` gains `bound_library_ids`                     | Required                                                                                                                                           |
| `useChatSse.ts`                                              | Switch `RuntimeContext` import source; add `context_prompt_text` forwarding        | Required                                                                                                                                           |
| `useManagedChat.ts`                                          | Read `bound_library_ids`, expose as `boundLibraryIds` → `ComposerSettingsControls` | Required                                                                                                                                           |

---

## 11. Implementation Sequence

### Task RUNTIME-02 — `fred-sdk` changes (no runtime behavior change)

```
fred_sdk/contracts/execution.py:
  - import RuntimeContext from .context
  - runtime_context field: dict[str, Any] | None → RuntimeContext | None
  - update field description

fred_sdk/contracts/context.py:
  - search_policy: str | None → Literal["strict","hybrid","semantic"] | None
  - add context_prompt_text: str | None = None
  - add deprecation note to Group A fields in RuntimeContext docstring

make code-quality && make test in libs/fred-sdk
```

### Task RUNTIME-02 — Control-plane backend

```
control_plane_backend/product/schemas.py:
  - add bound_library_ids: list[str] | None to EffectiveChatOptions

control_plane_backend/product/service.py:
  - resolve bound_library_ids from agent chat_options.bound_library_ids tuning field

make code-quality && make test in apps/control-plane-backend
generate-openapi → commit controlPlaneOpenApi.ts
```

### Task RUNTIME-02 — Fred-runtime regeneration and compatibility check

```
Regenerate runtimeOpenApi.ts from fred-runtime OpenAPI schema.
Verify that internal callers of RuntimeContext still work with the typed model.
(adapters.py already uses RuntimeContext as the typed model — no change needed there.)

make code-quality && make test in libs/fred-runtime
```

### Task FRONT-06 — Frontend (depends on RUNTIME-02 and RUNTIME-02)

```
useChatSse.ts:
  - switch RuntimeContext import from agenticOpenApi → runtimeOpenApi
  - read context_prompt_text from prep response
  - include context_prompt_text in RuntimeContext sent per turn

ManagedChatPage.tsx:
  - read effective_chat_options.bound_library_ids
  - pass as boundLibraryIds to ComposerSettingsControls (via useManagedChat)

tsc --noEmit + prettier
```
