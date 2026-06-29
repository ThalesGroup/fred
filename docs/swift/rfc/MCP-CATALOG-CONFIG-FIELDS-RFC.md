# RFC: MCP Catalog config_fields — Tool-Declared Capability Options

**Status:** Partially implemented (status note updated 2026-06-29) — backend contract work is complete and `ManagedChatPage` consumes the resolved chat options. Open items: the `AgentFormBody` Tools tab rendering in §3.6, and the `attach_files` catalog migration in §10 (CHAT-15).
**Author:** Simon Cariou
**Scope:** `fred-sdk` `MCPServerConfiguration`, `mcp_catalog.yaml` format, control-plane
product service enrichment, `AgentFormBody` Tools tab, `fred-agents` agent templates
**Related:** `docs/swift/backlog/BACKLOG.md §3.10`,
`docs/swift/backlog/CHAT-UI-BACKLOG.md §3`

---

## 1. Problem

`chat_options.*` tuning field specs (library picker, search policy, RAG scope) are
currently declared inside agent template definitions in `fred-agents`. The frontend
routes them by `ui.group` into the Settings tab rather than the Tools tab, breaking
the intended UX association between "search options" and "the search MCP server is
active."

The root cause is an ownership misattribution: these options are intrinsic to the
Knowledge Flow MCP search server, not to any individual agent that uses it. The same
options apply identically to every ReAct agent that activates the KF search server.
If the KF team adds a new option, every agent template that declares it must be updated
independently — the wrong coupling.

A secondary defect: an earlier agent-form proposal put `config_fields` on
`ManagedMcpServerRef` populated from agent template definitions. That proposal
anticipated the correct data structure but placed ownership at the wrong layer.

---

## 2. Architectural principle

**The tool declares its user-facing capabilities. The agent decides which tools to activate.**

An MCP server is a capability provider. User-configurable options for that server
(e.g., which document library to search, which search mode to use) are properties of the
server, not of the agents that reference it. Multiple agents share the same server; they
should all automatically expose the same options when that server is active, without any
agent-level duplication.

This maps naturally onto the existing pod architecture: each agentic pod ships a
`mcp_catalog.yaml` that is the authoritative, team-local source of truth for all MCP
servers available in that pod. This is where server-level metadata belongs, including
the user-facing options the server exposes.

---

## 3. Proposed solution

### 3.1 Data flow (corrected)

```
mcp_catalog.yaml          MCPServerConfiguration     ManagedMcpServerRef     AgentFormBody
─────────────────          ──────────────────────     ───────────────────     ─────────────
config_fields: [...]  →   config_fields: [...]   →  config_fields: [...]  → rendered beneath
(YAML, team-authored)     (fred-sdk typed model)     (control-plane API)     server checkbox
                                                                              when server active
```

No agent template participates in this chain. The agent template only says
`MCPServerRef(id="mcp-knowledge-flow-mcp-text")` as it does today.

### 3.2 Schema change: `MCPServerConfiguration` in `fred-sdk`

Add one field:

```python
class MCPServerConfiguration(BaseModel):
    ...existing fields unchanged...
    config_fields: list[FieldSpec] = []
```

`FieldSpec` already exists in `fred-sdk.contracts.models`. No new type needed.

### 3.3 Catalog format extension: `mcp_catalog.yaml`

The catalog YAML format gains an optional `config_fields` list per server entry.
Example for the KF text search server:

```yaml
- id: "mcp-knowledge-flow-mcp-text"
  name: "mcp.servers.search_documents.name"
  description: "mcp.servers.search_documents.description"
  transport: "streamable_http"
  url: "http://localhost:8111/knowledge-flow/v1/mcp-text"
  sse_read_timeout: 2000
  enabled: true
  auth_mode: "user_token"
  config_fields:
    - key: "chat_options.libraries_selection"
      type: "string"
      title: "Document libraries"
      description: "Tag IDs of document libraries to search"
    - key: "chat_options.search_policy"
      type: "string"
      title: "Search policy"
      enum: ["strict", "hybrid", "semantic"]
    - key: "chat_options.search_rag_scope"
      type: "string"
      title: "RAG scope"
      enum: ["corpus_only", "hybrid", "general_only"]
```

`McpServerEntry` in `fred_runtime/app/mcp_config.py` already uses
`model_config = ConfigDict(extra="allow")` so new YAML keys are passed through
transparently without a model change. The `config_fields` list will be forwarded
opaquely by the runtime and parsed by the control-plane.

### 3.4 Control-plane enrichment

The existing enrichment loop in `_RuntimeTemplatePayload.model_validate` already copies
`display_name` from `available_mcp_servers` catalog entries into `ManagedMcpServerRef`.
It extends to also copy `config_fields`, mapping each raw dict entry into
`ManagedAgentFieldSpec` (the control-plane's version of `FieldSpec`).

`ManagedMcpServerRef.config_fields` already exists in `control_plane_backend/config/models.py`
with an empty default — no schema change needed there.

### 3.4.1 Status after backend contract freeze (updated 2026-05-26)

The backend side of this RFC is implemented, and the managed-chat follow-on that
consumes the resolved options is also landed:

- create/update payloads accept dedicated `mcp_config_values`
- `ManagedAgentInstanceSummary` exposes stored `mcp_config_values`
- `ExecutionPreparation` exposes resolved `effective_chat_options`
- `useChatSse` / `ManagedChatPage` consume `effective_chat_options` so runtime-owned
  chat options already drive the managed chat UI
- MCP selection semantics are tri-state:
  - `null` = inherit template default selection
  - `[]` = activate no MCP servers
  - non-empty list = exact subset
- duplicate MCP server ids are rejected when loading `mcp_catalog.yaml`

The only remaining work tracked by this RFC is frontend wiring in `AgentFormBody`
for the Tools tab rendering described in §3.6.

### 3.5 Agent template cleanup

`chat_options.*` field specs are removed from all agent template definitions in
`fred-agents` (`general_assistant.py`, `rag_expert.py`, and any other agent that
currently declares them). Those fields now live exclusively in the catalog.

### 3.6 Frontend: AgentFormBody Tools tab

`routeField()` is unaffected — `chat_options.*` fields no longer appear in
`default_tuning_fields` at all.

In the Tools tab, for each `ManagedMcpServerRef` that has non-empty `config_fields`
AND is currently checked (active), render those fields indented beneath the server
checkbox using the existing `TuningFieldRenderer`.

Values must be stored in a dedicated MCP config payload:

```typescript
type McpConfigValues = Record<string, Record<string, TuningValue>>;
```

That means:

- outer key = MCP server id
- inner key = `config_field.key`
- generic agent tuning state (`tuningFieldValues`) remains reserved for
  agent-authored `prompts.*` / `settings.*`

---

## 4. Alternatives considered

### 4.1 `ui.group` convention in agent templates (rejected)

Change `chat_options.*` field `ui.group` to `"mcp:mcp-knowledge-flow-mcp-text"` so the
control-plane routes them into `config_fields` of the matching server. Rejected because:

- ownership remains wrong: the agent template still declares tool capabilities
- every agent that uses the tool must repeat the declaration
- adding a new tool option requires touching every agent template

### 4.2 Hardcode KF server IDs in the frontend (rejected)

Frontend checks `server.id.includes("knowledge-flow")` to decide which servers get
chat_options below them. Rejected because:

- breaks if server IDs change
- frontend must know domain facts that belong to the tool provider
- does not generalise to other configurable MCP servers

---

## 5. Impact

| Layer                                             | Change                                                                                       | Required? |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------- | --------- |
| `fred-sdk` `MCPServerConfiguration`               | Add `config_fields: list[FieldSpec] = []`                                                    | Yes       |
| `mcp_catalog.yaml` (fred-agents)                  | Add `config_fields` to `mcp-knowledge-flow-mcp-text` and `mcp-knowledge-flow-corpus` entries | Yes       |
| `fred_runtime/app/mcp_config.py` `McpServerEntry` | No change — `extra="allow"` already forwards unknown YAML keys                               | No        |
| Control-plane product service enrichment loop     | Extend to copy `config_fields` from catalog entry into `ManagedMcpServerRef`                 | Yes       |
| `ManagedMcpServerRef` in `config/models.py`       | No change — `config_fields` already exists                                                   | No        |
| `fred-agents` agent templates                     | Remove `chat_options.*` `FieldSpec` declarations                                             | Yes       |
| Control-plane create/update/summary contracts     | Add dedicated `mcp_config_values` and `ExecutionPreparation.effective_chat_options`          | Yes       |
| Frontend `AgentFormBody`                          | Render `config_fields` beneath active server checkboxes using `mcp_config_values`            | Yes       |
| `controlPlaneOpenApi.ts`                          | Regenerate after `ManagedMcpServerRef.config_fields` is confirmed populated                  | Yes       |

---

## 6. Contract boundary

`config_fields` in the catalog are **user-facing configuration hints owned by the
tool layer**. They are not MCP protocol parameters. The values submitted by the
user are persisted in `mcp_config_values[server_id][field_key]`, not flattened
into generic `tuning_field_values`.

Control-plane may still resolve some of those tool-owned values into typed
frontend/runtime affordances. Phase 1 of that resolution is
`ExecutionPreparation.effective_chat_options`.

---

## 7. Locked MCP servers on specialized templates (decided 2026-05-22)

See `SDK-V2-RFC.md §18` for the full agent template taxonomy. This section records
the MCP-layer contract consequences.

### 7.1 Problem

Specialized templates (e.g. Sentinel, react_rag_mcp) pre-wire specific MCP servers
that define their identity. Allowing operators to toggle these servers off in the
enrollment form breaks the template's semantic contract — a Monitoring assistant
without its OpenSearch MCP is not a Monitoring assistant.

### 7.2 Decision

`MCPServerRef` gains a `locked: bool = False` field. When `True`:

- the server is displayed in the Tools tab with its `config_fields` fully visible
- its enable/disable toggle is rendered as **disabled (read-only)**
- the value is excluded from operator input in create/update requests; the
  control-plane treats it as always-active regardless of `selected_mcp_server_ids`

### 7.3 Schema changes

```python
# fred-sdk MCPServerRef
class MCPServerRef(BaseModel):
    id: str
    require_tools: list[str] = []
    locked: bool = False          # NEW — template declares this server as non-toggleable
```

```python
# control_plane_backend ManagedMcpServerRef — propagated from template
class ManagedMcpServerRef(BaseModel):
    ...
    locked: bool = False          # NEW — forwarded from MCPServerRef; frontend reads this
```

### 7.4 Impact table addition

| Layer                                                     | Change                                                                              | Required? |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------- | --------- |
| `fred-sdk` `MCPServerRef`                                 | Add `locked: bool = False`                                                          | Yes       |
| `ManagedMcpServerRef` in control-plane `config/models.py` | Add `locked: bool = False`                                                          | Yes       |
| Control-plane product service enrichment loop             | Forward `locked` from `MCPServerRef` into `ManagedMcpServerRef`                     | Yes       |
| Control-plane create/update validation                    | Always-include locked servers; reject attempts to exclude them via `mcp_server_ids` | Yes       |
| Frontend `McpServerCard`                                  | Render toggle as disabled when `server.locked === true`                             | Yes       |
| `fred-agents` specialized templates                       | Set `locked=True` on all `MCPServerRef` entries                                     | Yes       |
| `controlPlaneOpenApi.ts`                                  | Regenerate after `ManagedMcpServerRef.locked` is added                              | Yes       |

### 7.5 Config fields on locked servers

Locked servers still expose their `config_fields`. The operator can configure
library selection, search policy, or any other tool-owned option — they just
cannot remove the tool itself. Read-only toggle ≠ read-only configuration.

---

## 8. Tool-declared behavioral contracts (`agent_instructions`)

**Status:** Implemented (2026-05-22). This subsection is complete; the RFC as a
whole remains partially implemented until §3.6 lands.

### 8.1 Problem

Citation behavior (and any other behavior that is intrinsic to a tool being
active) is currently encoded in the agent template's system prompt. This has
three serious consequences:

1. **Fragility** — an operator who writes a custom `prompts.system` silently
   overrides all citation rules. The agent stops citing. No warning, no test
   failure, no signal.
2. **Duplication** — every template that activates a search server must copy
   the same citation rules. Adding a new rule requires touching every template.
3. **Wrong ownership** — citation is a contract of the _search tool_, not of
   any individual agent. Placing it in the agent prompt inverts the ownership
   that §2 of this RFC establishes for `config_fields`.

This is exactly the same structural problem that motivated `config_fields`: tool
capabilities declared in agent code instead of in the tool's catalog entry.

### 8.2 Principle extension

§2 states: _"The tool declares its user-facing capabilities."_

This extends to behavioral contracts: if activating a tool implies a mandatory
behavioral constraint on the agent (e.g., cite retrieved results, never invent
URLs, always disclose retrieval failure), that constraint belongs in the tool's
catalog entry — not in any system prompt.

**The operator's `prompts.system` sets the role and focus of the agent.
The tool's `agent_instructions` enforces the behavioral contract of that tool.
These are orthogonal. Neither should override the other.**

### 8.3 Proposed solution

#### 8.3.1 Catalog format extension

Each server entry in `mcp_catalog.yaml` may declare an optional
`agent_instructions` field — a plain text block that the runtime appends to
the effective system prompt whenever that server is active:

```yaml
- id: "mcp-knowledge-flow-mcp-text"
  name: "mcp.servers.search_documents.name"
  transport: "streamable_http"
  url: "http://localhost:8111/knowledge-flow/v1/mcp-text"
  enabled: true
  config_fields: [...] # existing
  agent_instructions: | # NEW
    ## Citation contract (enforced by the search tool — non-negotiable)

    Every claim derived from a search result MUST carry an inline citation
    immediately after the claim: **[Title, p. X]** where Title is the `title`
    field and X is `page`, then `section`, then `file_name` in that priority.

    End every response that cites a document with a **Sources** section.
    List each document once: title, file_name, page or section.

    NEVER generate, fabricate, or include any URL, hyperlink, or document ID.
    If the search tool returns no relevant results, say so explicitly before
    answering from general knowledge and label the claim accordingly.
```

`McpServerEntry` already uses `model_config = ConfigDict(extra="allow")`, so
this field passes through the catalog loader without any model change.

#### 8.3.2 Runtime injection

In `agent_app.py`, `_apply_runtime_tuning`, after resolving the operator's
`system_prompt_template` (current lines 887–891), append the `agent_instructions`
of every active MCP server:

```python
# Behavioral contracts from active tools — non-negotiable, always appended.
fragments = [
    catalog_entry.agent_instructions
    for server_ref in mcp_servers          # already filtered to active subset
    for catalog_entry in available_catalog  # pod-local MCPServerConfiguration list
    if catalog_entry.id == server_ref.id
    and catalog_entry.agent_instructions
]
if fragments:
    injected = "\n\n".join(fragments)
    base = update.get("system_prompt_template", definition.system_prompt_template)
    update["system_prompt_template"] = f"{base}\n\n{injected}"
```

The `available_catalog` (the loaded `MCPServerConfiguration` list) must be
passed into `_apply_runtime_tuning` as an additional parameter. The call sites
at lines 955 and 1011 already have access to it via `_available_mcp_servers_for_definition`.

#### 8.3.3 Contract guarantees

| Property                                                | Guaranteed by                                                |
| ------------------------------------------------------- | ------------------------------------------------------------ |
| Instructions are always present when the tool is active | Runtime injection, not prompt authoring                      |
| Operator's custom prompt is respected                   | Injected fragment is appended, not prepended                 |
| Adding a new instruction requires one catalog edit      | Single source of truth in `mcp_catalog.yaml`                 |
| Removing the tool removes its instructions              | Injection is conditional on the server being active          |
| No template duplication                                 | `agent_instructions` lives in the catalog, not in agent code |

### 8.4 Impact

| Layer                                  | Change                                                                                                      | Notes                                     |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| `mcp_catalog.yaml`                     | Add `agent_instructions` to `mcp-knowledge-flow-mcp-text` (and any other tool with behavioral requirements) | No schema change needed — `extra="allow"` |
| `MCPServerConfiguration` (fred-sdk)    | Add `agent_instructions: str \| None = None`                                                                | Typed access for runtime                  |
| `_apply_runtime_tuning` (fred-runtime) | Inject active servers' `agent_instructions` after operator's system prompt                                  | Core change                               |
| `fred-agents` templates                | Remove citation rules from `_SYSTEM_PROMPT` in `react_rag_mcp.py`; they move to the catalog                 | Simplification                            |
| Control-plane                          | No change required — `agent_instructions` is a runtime concern, not a form field                            | Intentional                               |
| Frontend                               | No change required — `agent_instructions` is never shown or edited by operators                             | Intentional                               |

### 8.5 Alternatives rejected

**Putting `agent_instructions` on `MCPServerRef` (fred-sdk authoring model) rather
than in the catalog:** `MCPServerRef` is an authoring-time reference. Behavioral
contracts belong to the catalog entry — the runtime source of truth — not to every
agent that references the server.

**Tool-level MCP protocol description fields:** The MCP `description` field on a
tool is what the model reads when deciding whether to call the tool. It is not
a behavioral instruction to the model as an agent. These are different things.

**Post-processing the model output to inject citations:** Fragile, changes the
model's context on the next turn, and doesn't help with partial streaming output.

### 8.6 What this does NOT change

- The operator's `prompts.system` field remains fully editable. It sets role,
  tone, and focus. It is prepended to — not replaced by — tool instructions.
- Templates that do not activate a search tool are unaffected.
- `config_fields` (user-configurable tool options) are unrelated to
  `agent_instructions` (non-negotiable behavioral contracts). Both can coexist
  on the same server entry.

---

## 9. Open questions

No design open questions remain. Two implementation items are still open:
frontend `AgentFormBody` rendering for `ManagedMcpServerRef.config_fields`
as described in §3.6, and the `attach_files` catalog migration in §10 (CHAT-15).

---

## 10. `chat_options.attach_files` — catalog migration + default-on with the search tool (CHAT-15, added 2026-06-29)

**Status:** Proposed. **Author:** Simon Cariou. **Task:** `CHAT-15`.

### 10.1 Problem

`chat_options.attach_files` is the **last** `chat_options.*` field still declared at
the agent layer — a `FieldSpec(key="chat_options.attach_files", default=False,
ui.hide=True)` carried by `general_assistant.py` and `react_rag_mcp.py`. This is the
exact ownership inversion §2 and §3.5 of this RFC set out to remove: the field is an
intrinsic capability of the Knowledge Flow search server, not of the agents that
reference it. §3.5 already migrated the library picker, search policy, and RAG scope
into the catalog; `attach_files` was left behind.

Two consequences follow:

1. **Wrong default.** The library picker (`chat_options.libraries_selection`) and the
   document picker (`chat_options.documents_selection`) default to `true` via their
   catalog `config_fields` entries, so a document-search agent shows them on by
   default. `attach_files` defaults to `false`, so an operator must manually enable
   attachments on every document agent even though attaching a file to a
   document-grounded conversation is the expected behavior.
2. **Cannot be cleanly toggled.** Because the value is stored agent-level
   (`tuning.values`) while the library/document defaults are resolved from per-server
   `config_fields`, there is no single store the operator toggle and the resolver
   agree on. The frontend special-cases the toggle (reads `tuning_field_values`,
   writes via `onTuningChange`) instead of using the generic `config_fields` renderer.

### 10.2 Decision

Make `attach_files` a catalog-owned `config_field` that mirrors `chat_options.documents_selection`
exactly — declared on the **same server entries** that already declare the document
picker, with the **same per-server default**:

- **Catalog.** Add a `chat_options.attach_files` `config_fields` entry next to
  `chat_options.documents_selection` on every server that declares it, copying that
  server's `documents_selection` default:
  - `mcp-knowledge-flow-mcp-text` → `default: true` (the search-documents tool — this
    is what makes attachments default-on "when the search document tool is active").
  - `mcp-knowledge-flow-corpus` → `default: false` (this server declares the full
    `chat_options.*` set with its pickers defaulted off; `attach_files` follows suit, so
    the toggle stays available there but off).

  Files: `apps/fred-agents/config/mcp_catalog.yaml` (both `mcp-text` and `corpus`
  entries) and `deploy/charts/fred/values.yaml` (only the `mcp-text` entry — the Helm
  copy's `mcp-knowledge-flow-corpus` entry carries no `config_fields` block today, a
  pre-existing divergence between the two catalog copies that is out of scope here).
- **Resolution.** In `_resolve_effective_chat_options`
  (`control_plane_backend/product/service.py`), resolve `attach_files` **purely** from
  active-server `config_fields`, OR-ing across active servers exactly like the
  `documents_selection` block. The previous agent-level read
  (`tuning.values.get("chat_options.attach_files")` in the `EffectiveChatOptions(...)`
  constructor) is **removed** — no deployed instances exist to retro-support, so no
  legacy seed is needed and §6's "values live in `mcp_config_values`, not
  `tuning_field_values`" boundary holds cleanly.
- **Frontend.** Remove the special-cased attach-files `SwitchRow` in `McpServerCard`
  so the generic `config_fields` loop renders it from `mcp_config_values`
  (default per the field default, toggleable through `onConfigChange`). The
  `tuningValues`/`onTuningChange` props become unused on `McpServerCard` and are dropped
  (the parent `AgentFormBody` keeps them for the agent settings form).
- **Agent templates.** Remove the `chat_options.attach_files` `FieldSpec` from
  `general_assistant.py` and `react_rag_mcp.py`. This also **fully completes §3.5**:
  the residual agent-level `chat_options.*` declarations in the test/diagnostic agents
  are removed too — `test_assistant` (`chat_options.attach_files` +
  `chat_options.libraries_selection`, plus their runtime debug echo) and `self_test`
  (`chat_options.libraries_selection`). These agents declare no catalog search server,
  so their agent-level chat-option fields never reached `EffectiveChatOptions` (the
  resolver reads chat options only from active-server `config_fields`); keeping them was
  dead/misleading. No `chat_options.*` `FieldSpec` remains at the agent layer.

### 10.3 Contract boundary

`attach_files` is now persisted in `mcp_config_values[<server_id>]["chat_options.attach_files"]`
and resolved into `ExecutionPreparation.effective_chat_options.attach_files` — the same
path the document picker already uses, fully consistent with §6. `EffectiveChatOptions.attach_files`
is unchanged (field already exists), so **no OpenAPI regeneration is required**. Runtime
reads of `attach_files` (`ctx.config(...)`, `context.tuning_values`) are a `test_assistant`
debug echo and an `fred-sdk` docstring example only; `mcp_config_values` is intentionally
not merged into the runtime `tuning_values` namespace, and the real consumer
(`ManagedChatPage`, via `effective_chat_options`) is unaffected.

### 10.4 Alternatives considered

- **Flip the agent `FieldSpec` default `False → True` (rejected).** FieldSpec defaults
  are not materialized into `tuning.values` at enrollment — the resolver reads
  `tuning.values.get(...)` which stays `None`, so the flip would have no effect. It
  would also apply to every agent that declares the field, not only when the search
  tool is active.
- **Frontend-only default-on (rejected).** Defaulting the toggle checked in React is
  not config-driven, does not persist, and re-creates the toggle/resolver store
  mismatch of §10.1.
- **Keeping a legacy agent-level seed in the resolver (rejected).** There are no
  deployed managed instances to retro-support, so reading the old `tuning.values`
  location would only re-introduce the two-store ambiguity that §10.1.2 and §6 warn
  against. The migration is therefore clean: per-server `config_fields` only.

### 10.5 Impact

| Layer | Change | Required? |
| ----- | ------ | --------- |
| `apps/fred-agents/config/mcp_catalog.yaml` | Add `chat_options.attach_files` next to `documents_selection` on `mcp-knowledge-flow-mcp-text` (default true) and `mcp-knowledge-flow-corpus` (default false) | Yes |
| `deploy/charts/fred/values.yaml` | Add `chat_options.attach_files` (default true) to `mcp-knowledge-flow-mcp-text` (the Helm corpus entry has no `config_fields` block — out of scope) | Yes |
| `control_plane_backend/product/service.py` | Resolve `attach_files` purely from active-server `config_fields` in `_resolve_effective_chat_options` (OR across servers); **remove** the agent-level read | Yes |
| `frontend McpServerCard.tsx` | Remove special-cased attach toggle; render via generic loop; drop `tuningValues`/`onTuningChange` props | Yes |
| `general_assistant.py`, `react_rag_mcp.py` | Remove agent-level `chat_options.attach_files` `FieldSpec` | Yes |
| `test_assistant`, `self_test` | Remove residual agent-level `chat_options.*` `FieldSpec`s + dead runtime echo (fully completes §3.5) | Yes |
| `controlPlaneOpenApi.ts` / OpenAPI | No change — `EffectiveChatOptions.attach_files` already exists; catalog change is data | No |
