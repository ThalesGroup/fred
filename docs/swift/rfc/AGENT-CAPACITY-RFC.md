# RFC: Agent Capacity — a single abstraction for modular agent features

**Status:** Draft for team review (2026-07-08)
**Author:** Florian Muller
**Scope:** `fred-sdk` (contracts, capacity manifest, middleware base), `fred-runtime`
(agent assembly, `create_agent` migration, capacity registry), `control-plane-backend`
(capacity catalog proxy, ReBAC team-scoping), `apps/frontend` (widget + part-renderer +
side-panel registries), `fred-core` (OpenFGA schema)
**Related:**
- `docs/swift/rfc/MCP-CATALOG-CONFIG-FIELDS-RFC.md` — the "tool declares its capabilities" principle this generalizes
- `docs/swift/rfc/TEAM-PLATFORM-POLICY-RFC.md` — "allowed MCP servers per team", which Tier 3 extends to capacities
- `docs/swift/rfc/SDK-V2-RFC.md` — bounded-capability philosophy
- `docs/swift/rfc/AGENTIC-POD-RFC.md`, `DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md` — pod topology this is scoped against
- GitHub issues #1903 (PPT filler), #1905 (WritableDocument), #1906 (document-access) — the three port targets that motivate this
- `docs/swift/platform/REBAC.md` — the OpenFGA model Tier 3 adds a type to

**Task ID:** `CAPAC-01` (new domain code `CAPAC` — must be added to the `CLAUDE.md`
task-ID table and `docs/swift/data/id-legend.yaml` before implementation).

> **Nature of this RFC.** This is a *direction-setting proposal* for the team, not a
> merge-ready implementation plan. It defines one target abstraction and a set of
> **maturity tiers** so the team can decide *how far* to go. Each tier is independently
> shippable and a strict superset of the previous one. Tier 0 pays for itself on its own.

---

## 1. Problem

Swift needs several "agent features" that are far more than a single tool: PPT filler,
WritableDocument, document-access. Each one spans agent-creation config, chat-time
options, dynamic tools, custom chat rendering, side panels, persisted state, custom
routes, and conversation-state edits. On `main` (Kea) these were shipped fast by
**scattering code across the codebase**. Porting them to swift (#1903/#1905/#1906) with
the same approach would re-create that scatter.

### 1.1 The scatter, measured

Adding **one** such feature end-to-end on `main` touches:

- **~8 central backend union/registry files**: the `ToolParams` discriminated union,
  the in-process toolkit registry, the `MessagePart` union in **four** places
  (`chat_schema` model, `chat_schema` union, `message_part.hydrate_fred_parts`,
  `context.UiPart`), the stream transcoder allow-set, and `mcp_catalog.yaml`.
- **~8 cross-cutting wiring points**: `session_orchestrator` system-note injection,
  `application_context` store accessor, `main.py` router include, alembic env +
  migration, the `agent_service` asset hook, `AgentChatOptions`.
- **~10 central frontend files**: `toolParamsRegistry`, the `MessageCard` part switch,
  the `ChatBot`/`ChatBotView`/`MessagesArea` side-pane wiring, the `Type.ts` part
  union, the router, i18n, and the regenerated API client.

The two worst hotspots are **chat-part plumbing** (a new part must be declared in four
backend places and mirrored in four frontend places) and **tool + params registration**
(spread across five registries). This is the wrong shape: a feature is a horizontal cut
through the system, but it *should* be a vertical module.

### 1.2 What swift already has (and what it lacks)

Swift is a better starting point than Kea:

- The agent-creation form is **already metadata-driven** — `TuningFieldRenderer`
  switches on `ManagedAgentFieldSpec.type`, so scalar config needs zero frontend code.
- There is a typed context (`RuntimeContext` / `BoundRuntimeContext` / `PortableContext`),
  typed tool results (`ToolInvocationResult(blocks, sources, ui_parts)`), and a
  `transport: "inprocess"` MCP-provider seam (`inprocess_toolkit_registry.py`,
  `kf_vector_search`) that is exactly where these features plug in.
- The MCP-CATALOG-CONFIG-FIELDS RFC already established the right principle:
  **"the tool declares its user-facing capabilities; the agent decides which tools to
  activate."**

But it lacks: per-instance dynamic tool construction (only MCP filtering exists), a
conversation-state-editing hook, a frontend part-renderer registry (part dispatch is
scattered and the `ThreadMessage` view-model **drops unknown parts** — it is lossy), a
side-panel contribution slot, an asset-upload/validation seam, and any per-team scoping
of tools (the catalog is pod-global; `TeamPlatformPolicy` is design-only).

---

## 2. Architectural principle: one abstraction

> **Everything an agent can be given beyond its base prompt is a *capacity*.
> A capacity = a runtime middleware + a manifest. There is no second concept.**

This generalizes the MCP-CATALOG principle from "MCP servers declare options" to "any
capability declares its whole vertical surface, in one place." Concretely:

- **MCP is not special.** A remote MCP server is a *generic capacity* (`McpCapacity`)
  parameterized by a server config. Built-in tools, authored toolsets, PPT filler,
  WritableDocument, and document-access are all capacities too. One registry, one
  product contract, one Tools tab.
- **A capacity owns its whole vertical**: the tools it exposes, its agent-creation and
  chat-time fields, the custom chat parts it emits (§3.6), its side panel, its routes,
  its tables, and its per-team enablement policy — declared together, registered once.
- **Runtime behavior is expressed as LangChain middleware.** Adding tools, building
  tools dynamically per turn, editing conversation state, and intercepting model/tool
  calls are all `AgentMiddleware` hooks (§5). This is not a Fred-invented hook system;
  it is the stock LangChain `create_agent` middleware API, which swift **already runs in
  production** for `DeepAgentRuntime`.

### 2.1 Why LangChain middleware as the spine

- It is already installed and used: lockfiles resolve `langchain==1.3.x` /
  `langgraph==1.2.5`; `AgentMiddleware` is already imported in `deep_runtime.py`.
- Every runtime need maps to an existing hook (§5.1), so we add capability by
  *composition*, not by editing core.
- We get the **prebuilt middleware suite for free**: model fallback, retries,
  tool-call limits (`ToolCallLimitMiddleware` — swift currently `raise
  NotImplementedError`s on `max_tool_calls_per_turn`), summarization, context editing,
  HITL.
- Fred capacities become **publishable as standalone LangChain middleware**, and any
  third-party LangChain middleware drops into Fred.

---

## 3. The `AgentCapacity` shape

A capacity is one backend package + one frontend folder + one registration line per side.

### 3.1 Manifest (declaration — drives product contract + generated UI)

```python
class CapacityManifest(BaseModel):
    id: str                              # "ppt_filler", "document_access", "mcp:<server>"
    name: str                            # i18n key
    description: str                     # i18n key
    icon: str

    fields: list[CapacityField]          # §3.3 — agent-creation AND chat-time, unified
    asset: AssetSpec | None              # §3.4 — required upload + accepted types + validator
    chat_parts: list[type[UiPart]]       # custom chat parts this capacity emits (see §3.6)
    side_panels: list[SidePanelSpec]     # panels this capacity mounts beside the chat

    router: APIRouter | None             # auto-mounted under /capacities/{id}/...
    tables: list[type[DeclarativeBase]]  # auto-registered for alembic autogenerate

    team_scope: TeamScopePolicy          # §7 — default_on | admin_gated (ReBAC)
```

### 3.2 The capacity class

```python
class AgentCapacity(ABC):
    manifest: ClassVar[CapacityManifest]
    ConfigModel: ClassVar[type[BaseModel]]     # typed agent-creation params

    async def validate_config(                 # agent-save time (§4)
        self, config: ConfigModel, upload: bytes | None, ctx: SaveContext
    ) -> ConfigModel: ...

    def middleware(self, ctx: CapacityContext) -> AgentMiddleware: ...   # runtime half (§5)
```

- `validate_config` is Kea's `ToolkitAssetProcessor`, generalized: parse the upload,
  derive persisted schema, raise typed `422` validation errors, strip the transient
  upload before persist. Mechanical fixes for capacities without an asset just return
  `config` unchanged.
- `middleware(ctx)` returns the LangChain middleware that carries this capacity's tools
  and hooks, bound to the turn's context.

### 3.3 Unified fields (retires chat-options)

**Decision:** the `chat_options.*` taxonomy and `EffectiveChatOptions` are retired. A
capacity declares **one** `fields` list; each field is tagged with *when* it is set and
*whether it is conditional*:

```python
class CapacityField(BaseModel):
    key: str
    type: FieldType                      # enum | boolean | text | array | prompt | ...
    phase: Literal["agent_creation", "chat_turn"]
    ui: FieldUi | None                   # ui.widget selects a custom renderer (§8)
    visible_when: FieldCondition | None  # gate on another field's value
    required: bool = False
```

This fixes two current incoherences:

1. **The generated-vs-hardcoded split.** Today the agent form is metadata-generated but
   chat options are a hand-built `SearchConfig` component. With unified fields, the
   composer renders whatever `chat_turn` fields the active capacities contribute, through
   the *same* widget mechanism as the agent form (generated for scalars, custom widget
   for complex ones like the scope selector).
2. **Conditional chat controls.** document-access wants "let the user add session
   attachments" — a `chat_turn` field gated on an `agent_creation` boolean. `visible_when`
   expresses this directly. The scope selector becomes *part of the document-access
   capacity*, not a global composer feature.

### 3.4 Assets

```python
class AssetSpec(BaseModel):
    required: bool                       # gates agent Save when true (PPT filler)
    accepted_types: list[str]            # [".pptx"]
```

The capacity's `validate_config` receives the uploaded bytes and owns validation. A
stateless analyze endpoint (for inline pre-save feedback, e.g. PPT slide errors) is just
a route on the capacity's `router`.

### 3.5 `CapacityContext` — the typed runtime/LLM split

This is the "don't mix runtime info with LLM-exposed params" requirement, formalized:

```python
@dataclass
class CapacityContext:
    identity: Identity            # user_id, session_id, team_id, agent_instance_id
    config: BaseModel             # this capacity's typed agent-creation params
    turn_options: BaseModel       # this capacity's chat-time field values
    services: RuntimeServices     # ports: KF client, workspace fs, stores, model factory
```

Tools receive **only LLM args** in their signature; identity/config/options/services
reach the tool through the middleware closure and (Tier 2+) `runtime.context`.

### 3.6 Terminology: "chat part"

A **chat part** is a typed, structured card that an agent emits as (part of) a tool or
turn result and that renders **inline in the conversation stream** — e.g. a download
link, a map, the PPT-preview card, the WritableDocument reference chip. It is the thing
carried in `ToolInvocationResult.ui_parts` and on the `tool_result`/`final` runtime
events.

The **existing frozen SDK type is `UiPart`** (`fred_sdk/contracts/context.py`, today the
`LinkPart | GeoPart` union). This RFC uses **"chat part"** as the reader-facing name for
the concept (the bare term "UI part" is ambiguous — fields, panels, and widgets are all
"UI" too), while continuing to reference the actual type as `UiPart` so no frozen
contract is silently renamed. A capacity's `manifest.chat_parts` entries are the
`UiPart` subclasses it contributes to that union (§4).

> If the team prefers, renaming the type `UiPart → ChatPart` is a reasonable but separate
> **contract amendment** (RUNTIME-EXECUTION-CONTRACT §10.1 + OpenAPI regen + frontend
> `Type.ts`), out of scope for this RFC.

---

## 4. Registration collapses the scatter

One registry replaces the five it subsumes. Registering a capacity:

- adds its tools/middleware to the agent (replacing the `inprocess_toolkit_registry`
  `if provider ==` chain and, at Tier 1, the `ToolParams` union role),
- contributes its `chat_parts` to the `UiPart` union (§3.6) at model-build time so
  OpenAPI regen picks them up — **the union stops being a hand-edited hotspot**,
- auto-mounts its `router` and auto-registers its `tables` for alembic,
- publishes its manifest to the control-plane catalog (the way templates are published
  today),
- declares its ReBAC team-scope (Tier 3).

The frontend mirror is one plugin object per capacity (§8), registered in one index.

---

## 5. How `create_agent` + middleware is inserted

### 5.1 Requirement → hook mapping

| Capacity requirement | LangChain middleware primitive |
| --- | --- |
| Add tools to the agent | `middleware.tools` (static) |
| Dynamic tool built at chat time (PPT filler: schema from parsed template) | `wrap_model_call` editing `request.tools` per model call |
| Runtime context split from LLM args | `context_schema` → `runtime.context` = `CapacityContext` |
| Edit conversation state (WritableDocument edit notice; attachment-added note) | `before_model` returning a state-update dict via reducers |
| Custom conversation state (the document itself) | `state_schema` with `NotRequired` fields + reducers |
| Guardrails / summarization / HITL / PII / retries | **prebuilt LangChain middleware — free** |

This answers the open "do we need a bespoke `HistoryStorePort` seam for the WritableDoc
system-note?" question: **no** — a state-schema field with a reducer carries it, and
LangChain's checkpointer persists/replays it. (Implementation must confirm swift's
existing `FredSqlCheckpointer` coexists with the middleware state schema; see §9.)

### 5.2 The migration (Tier 2), and why it is low-risk

Today `_create_compiled_react_agent` builds a **hand-rolled `StateGraph`**
(`support/tool_loop.py build_tool_loop`, ~200 lines) — a 4-node loop
(`reasoner`/`tools`/`gate_tools`/`tool_exec`). It predates the middleware API. The
`DeepAgentRuntime` path already uses `create_deep_agent` (built on `AgentMiddleware`)
**through the exact same streaming executor**, proving the rest of the runtime is
graph-agnostic.

The migration replaces `build_tool_loop_compiled_react_agent` with a call to
`create_agent(model, tools, prompt, middleware=[...], checkpointer=...)` and **re-homes
the custom `reasoner`/`gate_tools` logic as middleware** — it is not deleted, it moves:

| Today (custom node logic) | Becomes |
| --- | --- |
| `_sanitize_dangling_tool_calls` (poisoned-checkpoint → OpenAI 400 guard) | `before_model` middleware — **load-bearing, needs a test** |
| `strip_reasoning_from_history` (Mistral 422 guard on replay) | `before_model` middleware |
| `_trim_to_human_boundary` (bounded history) | `before_model` middleware |
| Per-turn dynamic system prompt (filesystem browsing context) | `modify_model_request` hook |
| Per-operation model routing (`_model_for_state`) | `modify_model_request` / model-selection hook |
| Model-call tracing + KPI span | `wrap_model_call` hook |
| HITL gate (`gate_tools` + `interrupt`, custom French payload) | thin custom middleware calling `interrupt()` with Fred's payload, **or** `HumanInTheLoopMiddleware` |

The four helpers are already **pure functions**, so they port directly.

**What does NOT change** — the reassuring part:

- The `RuntimeEvent` transcoder (`_TransportBackedReActExecutor.stream`,
  `react_runtime.py:292`, ~270 lines) is the large, fragile, stateful stream-translator
  that turns LangGraph's `stream_mode=["messages","updates"]` firehose into Fred's typed
  events (thought blocks, deltas, tool call/result, sources, ui_parts, token usage,
  interrupts). It depends only on **stream shapes, not node names**, and Deep already
  runs a different graph through it in production. **It is out of the migration's blast
  radius.** This is precisely why a "rewrite the core execution loop" change is rated
  low-risk: the risk normally lives in the transcoder, and the transcoder is untouched.
- Tool resolution/binding, `content_and_artifact` typed results, token accounting,
  checkpointer/`thread_id` wiring, prompt composition (static part), and agent-as-tool
  routing all stay as-is.

**New middleware we would author** (the Tier 2 deliverable), all thin wrappers over
existing pure logic:

1. `CheckpointHygieneMiddleware` — `before_model`: dangling-tool-call sanitize + reasoning-strip + history trim.
2. `DynamicPromptMiddleware` — `modify_model_request`: per-turn filesystem/context suffix.
3. `ModelRoutingMiddleware` — model selection per inferred operation.
4. `TracingKpiMiddleware` — `wrap_model_call`: span + latency timer.
5. `FredHitlMiddleware` — the interrupt gate with Fred's `HumanInputRequest` payload.
6. Per-capacity middleware — one per capacity, carrying its tools + `before_model`
   state edits.

**Must-test regressions:** (1) HITL interrupt payload round-trip, (2) dangling-tool
sanitize on a poisoned checkpoint, (3) Mistral reasoning-strip on replay, (4)
per-operation model routing still selects the right model.

---

## 6. Maturity tiers

Each tier is independently shippable and a strict superset of the previous. The team can
stop at any rung. **Tiers are ordered by risk**, not by dependency — the product-facing
work lands before the core-execution rewrite.

| Tier | Deliverable | Touches execution loop? | Risk |
| --- | --- | --- | --- |
| **0 — Capacity model + registry** | `AgentCapacity`/manifest + one registry that collapses the scatter. Runtime half plugs into the **existing** `inprocess_toolkit_registry` seam via a thin adapter. | No | Low |
| **1 — Unified fields + MCP-as-capacity** | Retire chat-options/`EffectiveChatOptions`; capacities own agent-creation + chat-time fields via one widget mechanism. Generic `McpCapacity`; `mcp_catalog.yaml` = pre-registered MCP-capacity instances. One Tools tab. | No | Low |
| **2 — Middleware runtime** | Migrate `_create_compiled_react_agent` → `create_agent`; capacity runtime half becomes a real `AgentMiddleware`; author the 5 core middleware (§5.2). ReAct + Deep converge. | **Yes** | Medium, contained |
| **3 — ReBAC team-scoping** | New `capacity` OpenFGA object type; per-team enablement (default-on set + admin-gated). Extends `TEAM-PLATFORM-POLICY-RFC`. | No | Low |
| **4 — Capacity SDK** | Formalize manifest + middleware + typed parts as a published `fred-sdk` surface; capacities authored like agents. | No | Low |

> **Interim scaffolding, called out deliberately:** the Tier-0/1 adapter (capacity →
> inprocess toolkit) is throwaway that Tier 2 replaces with native middleware. This is an
> intentional bridge, not accidental debt — it lets the entire product-facing capacity
> system ship **without touching the execution loop**, and makes the middleware migration
> an optional internal cleanup rather than a prerequisite.

**Non-goal (documented):** Tier 4 stops short of *untrusted third-party* capacity
authoring and *sandboxed/iframe UI parts*. The current topology — static
`runtime_catalog_sources` config, no dynamic pod registry, pod-local invocation only
(only `LocalRegistryAgentInvoker` is wired) — is nowhere near needing this. Capacities
are **in-tree / SDK-authored and trusted**; UI parts are React components committed to
Fred. A clean manifest (typed parts, declared fields) keeps the door open to a
sandboxed renderer later without paying for it now. This belongs in a **future RFC**, not
this one.

---

## 7. Pod & topology placement (open question, with a recommendation)

**Facts (verified):** multiple `fred-runtime` pods, each a static in-code agent registry;
control-plane maps template→pod via static config + DB `RuntimeBinding`; cross-pod
invocation is abstraction-ready (`RemoteSseAgentInvoker`) but **unwired** —
`invoke_agent` is pod-local. `fred-sdk` + `fred-runtime` are already the fork-free SDK.

**Recommendation:** capacities live **in the pod, with the agent, shipped via the SDK** —
the same story as agents today. A pod serves N agents and the capacities they declare.
Control-plane stays the proxy/registry/team-policy authority (it aggregates capacity
manifests from pods the way it aggregates templates). **Do not** build a "capacity pod"
and **do not** put capacity runtime code in control-plane. Cross-pod capacity use is out
of scope initially (it would require wiring `RemoteSseAgentInvoker` + a remote capacity
protocol — a separate RFC).

---

## 8. ReBAC team-scoping (Tier 3)

Today the catalog is pod-global; there is no per-team tool scoping. `TEAM-PLATFORM-POLICY`
already reserves "allowed MCP servers for the team" as future work — Tier 3 realizes it
for capacities. The OpenFGA model (`fred-core/.../rebac/schema.fga`) has types `user,
organization, team, agent, tag, document, resource` and **no capability type**, but is a
standard Zanzibar schema, trivially extended:

```
type capacity
  relations
    define parent: [organization]     # org-level = available platform-wide (default-on set)
    define enabled: [team]            # explicit per-team enablement (admin-gated capacities)
    define can_use: enabled or admin from parent
```

Default-on capacities get an `organization:fred` parent; admin-gated ones (custom
per-team capacities, admin/self-monitoring capacities) require an explicit `enabled`
tuple per team, granted by an admin. Flows through the existing `sync_schema_on_init`
bootstrap.

---

## 9. Frontend (mix of generated + custom widgets — confirmed direction)

Simple fields render through the existing metadata-driven form (zero code). Complex
fields declare `ui.widget` and resolve against a **widget registry** extending
`TuningFieldRenderer`'s type-switch. Each capacity ships one folder
`rework/features/capacities/<id>/` exporting a single plugin, registered in one index —
the only shared edit:

```ts
export const documentAccessCapacity: CapacityUiPlugin = {
  id: "document_access",
  configWidgets: { scope_selector: ScopeSelectorField },
  chatTurnControls: { scope_narrow: ScopeNarrowControl },
  partRenderers: { /* none */ },
  sidePanels: { /* none */ },
};
```

Four frontend infrastructure pieces are needed (three already on the backlog):

1. **Part-renderer registry** keyed by part `type` — centralizes dispatch currently
   scattered across `ConversationThread`/`useManagedChat`/`traceUtils`. **`ThreadMessage`
   must carry raw/unknown parts instead of pre-folding them** (it is lossy today;
   CHAT-UI §3.4 already specs "skip unknown kind").
2. **Chat-turn controls renderer** — the specced-but-unbuilt `AgentOptionDescriptor`
   system (CHAT-UI §3.9), driven by capacity `chat_turn` fields.
3. **Side-panel contribution slot** — generalizing `InlineDrawer layout="push"` +
   `TraceDrawerProvider` into a reserved right-column slot capacities mount into.
4. **Widget registry** for custom config/turn field widgets.

Custom chat parts stay **strongly typed** end-to-end: capacity `chat_parts` extend the
frozen `UiPart` union (§3.6) via registration + OpenAPI regen; the part-renderer registry
is typed against the regenerated union. No generic envelope.

---

## 10. Worked mapping of the three port targets

| Feature | Exercises | Tier that unblocks it |
| --- | --- | --- |
| **#1906 document-access** (tree + summarize + rename) | multiple tools from one capacity; agent-creation scoping + chat-turn narrowing via unified fields; no new part/panel | Tier 0 (as inprocess adapter) → **pilot**; polished by Tier 1 |
| **#1903 PPT filler** | `validate_config` + asset upload; dynamic tools; custom widget; custom part; side panel; analyze route on `router` | Tier 0/1 for the vertical; Tier 2 for native dynamic-tool middleware |
| **#1905 WritableDocument** | `tables` + `router` (CRUD/export); `before_model` state edit (edit detection → system note); custom part; editor side panel | Tier 0/1 vertical; **Tier 2 makes the state-edit a clean middleware hook** |

**#1906 is the pilot** — smallest surface, validates the abstraction (and the frontend
registries) before #1903/#1905 build on it.

---

## 11. Alternatives considered

- **A parallel Fred hook system (my first sketch: `before_turn`/`build_tools` on the
  capacity).** Rejected: it duplicates LangChain's middleware API, forgoes the prebuilt
  suite, and can't be published as LangChain-compatible. Adopting `AgentMiddleware`
  directly is strictly better.
- **Keep MCP as a separate tool family beside capacities.** Rejected: it keeps two
  product contracts, two Tools-tab code paths, and two registries. `McpCapacity`
  parameterized by a server config unifies them.
- **A generic `CapacityPart{capacity_id, kind, payload}` envelope** instead of extending
  the typed `UiPart` union. Rejected: loses end-to-end generated types; the union
  extension via OpenAPI regen keeps strong typing.
- **Wrapper, not rewrite** (keep the hand-rolled graph; adapt middleware-shaped hooks
  internally). Viable as a fallback if Tier 2 is deferred, but forgoes the prebuilt
  middleware and keeps ReAct/Deep divergent. Documented as the "stop at Tier 1" state.

---

## 12. Open questions for the team

1. **Tier depth.** How far does the team want to commit — Tier 1 (product-facing, no
   execution rewrite), or through Tier 2 (middleware runtime)? This RFC recommends
   Tier 0+1 first with #1906, then Tier 2.
2. **HITL migration (Tier 2).** Thin custom middleware preserving Fred's
   `HumanInputRequest` payload (lowest risk, keeps `extract_interrupt_request`), or adapt
   to the stock `HumanInTheLoopMiddleware` payload?
3. **State persistence (Tier 2).** Confirm `FredSqlCheckpointer` + middleware
   `state_schema` reducers coexist for the WritableDoc state across replay — needs a
   spike before committing §5.1's "no `HistoryStorePort` needed" claim.
4. **`capacity` ReBAC relations (Tier 3).** Is `parent: [organization]` + `enabled:
   [team]` the right shape, or should it mirror the `tag`/`document` `parent: [team]`
   pattern?

---

## 13. Next steps (per repo workflow)

1. Add `CAPAC` to the task-ID table in `CLAUDE.md` and create `CAPAC-01` in
   `docs/swift/data/id-legend.yaml` (this RFC as `refs.rfc`).
2. Add backlog entries (Tier 0 pilot = #1906 as a capacity) in the relevant backlog file.
3. Create the GitHub issue linking `CAPAC-01`, this RFC, and the backlog entry.
4. **Do not implement until the team confirms tier depth (Q1).**
