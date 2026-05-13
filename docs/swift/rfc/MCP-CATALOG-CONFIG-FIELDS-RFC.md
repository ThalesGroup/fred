# RFC: MCP Catalog config_fields — Tool-Declared Capability Options

**Status:** Partially implemented (2026-05-06) — backend complete, frontend AgentFormBody rendering pending
**Author:** Architecture
**Scope:** `fred-sdk` `MCPServerConfiguration`, `mcp_catalog.yaml` format, control-plane
product service enrichment, `AgentFormBody` Tools tab, `fred-agents` agent templates
**Related:** `docs/rfc/AGENT-INSTANCE-FORM-RFC.md §3`, `docs/backlog/BACKLOG.md §3.7`,
`docs/backlog/CHAT-UI-BACKLOG.md §3`

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

A secondary defect: the existing AGENT-INSTANCE-FORM-RFC.md §3.2 proposed `config_fields`
on `ManagedMcpServerRef` populated from agent template definitions. That RFC anticipated
the correct data structure but placed ownership at the wrong layer.

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

### 3.4.1 Status after backend contract freeze (2026-05-06)

The backend side of this RFC is now implemented:

- create/update payloads accept dedicated `mcp_config_values`
- `ManagedAgentInstanceSummary` exposes stored `mcp_config_values`
- `ExecutionPreparation` exposes resolved `effective_chat_options`
- MCP selection semantics are tri-state:
  - `null` = inherit template default selection
  - `[]` = activate no MCP servers
  - non-empty list = exact subset
- duplicate MCP server ids are rejected when loading `mcp_catalog.yaml`

The remaining work is frontend wiring in `AgentFormBody` and `ManagedChatPage`.

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
type McpConfigValues = Record<string, Record<string, TuningValue>>
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

| Layer | Change | Required? |
|---|---|---|
| `fred-sdk` `MCPServerConfiguration` | Add `config_fields: list[FieldSpec] = []` | Yes |
| `mcp_catalog.yaml` (fred-agents) | Add `config_fields` to `mcp-knowledge-flow-mcp-text` and `mcp-knowledge-flow-corpus` entries | Yes |
| `fred_runtime/app/mcp_config.py` `McpServerEntry` | No change — `extra="allow"` already forwards unknown YAML keys | No |
| Control-plane product service enrichment loop | Extend to copy `config_fields` from catalog entry into `ManagedMcpServerRef` | Yes |
| `ManagedMcpServerRef` in `config/models.py` | No change — `config_fields` already exists | No |
| `fred-agents` agent templates | Remove `chat_options.*` `FieldSpec` declarations | Yes |
| Control-plane create/update/summary contracts | Add dedicated `mcp_config_values` and `ExecutionPreparation.effective_chat_options` | Yes |
| Frontend `AgentFormBody` | Render `config_fields` beneath active server checkboxes using `mcp_config_values` | Yes |
| `controlPlaneOpenApi.ts` | Regenerate after `ManagedMcpServerRef.config_fields` is confirmed populated | Yes |

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

## 7. Open questions

None. The design is agreed. This RFC records the decision for traceability.
