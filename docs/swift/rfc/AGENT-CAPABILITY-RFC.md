# RFC: Agent Capability — a single abstraction for modular agent features

**Status:** Team-approved (2026-07-09) — all tiers. Implementation starts with the
Tier 2 `create_agent` migration. Amended 2026-07-09 with design-review resolutions
(§3.9, §5.3, §5.4, §7.1, §7.2, §9.1, §12).
**Author:** Florian Muller
**Scope:** `fred-sdk` (contracts, capability manifest, middleware base), `fred-runtime`
(agent assembly, `create_agent` migration, capability registry), `control-plane-backend`
(capability catalog proxy, ReBAC team-scoping), `apps/frontend` (widget + part-renderer +
side-panel registries), `fred-core` (OpenFGA schema)
**Related:**
- `docs/swift/rfc/MCP-CATALOG-CONFIG-FIELDS-RFC.md` — the "tool declares its capabilities" principle this generalizes
- `docs/swift/rfc/TEAM-PLATFORM-POLICY-RFC.md` — "allowed MCP servers per team", which Tier 3 extends to capabilities
- `docs/swift/rfc/SDK-V2-RFC.md` — bounded-capability philosophy
- `docs/swift/rfc/AGENTIC-POD-RFC.md`, `DISTRIBUTED-AGENT-ARCHITECTURE-RFC.md` — pod topology this is scoped against
- GitHub issues #1903 (PPT filler), #1905 (WritableDocument), #1906 (document-access) — the three port targets that motivate this
- `docs/swift/platform/REBAC.md` — the OpenFGA model Tier 3 adds a type to

**Task ID:** `CAPAB-01` (new domain code `CAPAB` — must be added to the `CLAUDE.md`
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

> **Everything an agent can be given beyond its base prompt is a *capability*.
> A capability = a runtime middleware stack + a manifest. There is no second concept.**

This generalizes the MCP-CATALOG principle from "MCP servers declare options" to "any
capability declares its whole vertical surface, in one place." Concretely:

- **MCP is not special.** A remote MCP server is a *generic capability* (`McpCapability`)
  parameterized by a server config. Built-in tools, authored toolsets, PPT filler,
  WritableDocument, and document-access are all capabilities too. One registry, one
  product contract, one Tools tab. Whether an MCP server happens to be operated by
  Knowledge Flow or by a third party is likewise invisible above the capability
  boundary — both are the exact same `McpCapability` mechanism, gated and cataloged
  identically. Today a capability's vertical is realized by exactly one of two
  mechanisms — a call to an MCP server, or native code — and later, per the RFC's
  horizon (§13), by a full app; the mechanism is a private implementation detail the
  catalog, the authorization model, and a template's declared defaults never see.
- **A template's defaults are just capability ids, resolved uniformly.** An agent
  template's `default_mcp_servers` list is not an MCP-only lookup — each id is
  checked at boot against the same pod capability registry that backs the catalog,
  whether the id names an MCP-derived capability or a native one. An id the pod has
  genuinely never heard of fails boot loudly (`UnknownCapabilityError`), the same
  doctrine already applied to a duplicate id or a missing `required_env` (§4) — never
  a silently-dropped tool. A server merely *disabled* in the MCP catalog stays the
  already-documented tolerated state (warning-only, §3.8) — boot only rejects an id
  absent from both the capability registry and the MCP catalog.
- **A capability owns its whole vertical**: the tools it exposes, its agent-creation and
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
- Fred capabilities become **publishable as standalone LangChain middleware**, and any
  third-party LangChain middleware drops into Fred.

---

## 3. The `AgentCapability` shape

A capability is one backend package + one frontend folder + one registration line per side.

### 3.1 Manifest (declaration — drives product contract + generated UI)

```python
class CapabilityManifest(BaseModel):
    id: str                              # "ppt_filler", "document_access", "mcp-bank-core-demo" (catalog server id, no prefix — #1988)
    version: str                         # bumped per release — cache key for computed surfaces (§3.7)
    name: str                            # i18n key
    description: str                     # i18n key
    icon: str

    config_fields: list[ManagedAgentFieldSpec]  # §3.3 — agent-creation form (static, reuses existing spec)
    assets: list[AssetSlot]              # §3.4 — named upload slots: accepted types + cardinality; [] = none
    chat_parts: list[type[UiPart]]       # custom chat parts this capability emits (see §3.6)
    side_panels: list[SidePanelSpec]     # panels this capability mounts beside the chat

    router: APIRouter | None             # auto-mounted under /capabilities/{id}/... (§9.1)
    tables: list[type[DeclarativeBase]]  # capability-owned tables; migrations ship with the package (§7.1)
    required_env: list[str]              # env vars this capability needs — checked at pod boot (§7.2)

    team_scope: TeamScopePolicy          # §7 — default_on | admin_gated (ReBAC)
```

> **As implemented (2026-07-10, #1973 — `fred_sdk/contracts/capability/`).**
> `config_fields` uses the SDK-owned `FieldSpec` (`fred_sdk.contracts.models`),
> not control-plane's local `ManagedAgentFieldSpec` copy. `router` and `tables`
> are typed `Any` — fred-sdk depends on neither fastapi nor sqlalchemy. One
> added field: `state_models: list[type[BaseModel]]`, the per-capability
> typed-state opt-in for the checkpointer msgpack allowlist (§5.2 spike rule);
> the registry composes the entries into
> `FredSqlCheckpointer(extra_msgpack_allowlist=...)`. The §3.5 `identity`
> parameter is the model `CapabilityIdentity` (user/session/team/agent-instance
> ids).

### 3.2 The capability class

```python
class AgentCapability(ABC, Generic[ConfigT, StoredT, TurnOptionsT]):
    manifest: ClassVar[CapabilityManifest]
    ConfigModel: ClassVar[type[BaseModel]]        # typed user input — agent-creation params (drives config_fields)
    StoredConfigModel: ClassVar[type[BaseModel]]  # persisted shape after validation/enrichment (§3.8); = ConfigModel by default
    TurnOptionsModel: ClassVar[type[BaseModel]]   # typed chat-time values (§3.5); EmptyModel if none
    TeamSettingsModel: ClassVar[type[BaseModel]]  # typed per-team enablement settings (§8.2); EmptyModel if none

    async def validate_config(                    # agent-save time (§4) — input → stored transform
        self, config: ConfigT, uploads: Mapping[str, list[UploadedFile]], ctx: SaveContext
    ) -> StoredT: ...                             # uploads keyed by AssetSlot.key (§3.4)

    def chat_controls(self, config: StoredT) -> list[ChatControlSpec]: ...  # §3.3 — computed chat surface

    def upgrade_config(self, stored: dict, from_version: str) -> StoredT: ...  # optional — old stored shapes (§3.9)

    def middleware(self, ctx: CapabilityContext[StoredT, TurnOptionsT]) -> Sequence[AgentMiddleware]: ...  # runtime half (§5)
```

- **Two config schemas, deliberately.** `ConfigModel` is what the user *sends* (it
  drives the agent-creation form); `StoredConfigModel` is what the platform *persists*
  after validation and enrichment (§3.8). For most capabilities they are the same class.
  A capability that derives state at save time declares `StoredConfigModel` as a
  **subclass** of `ConfigModel` adding the derived fields — e.g. PPT filler's input is
  its options plus the raw upload, while its stored config adds `asset_key` (the KF
  blob reference, §3.8) and the parsed slide schema. Subclassing rather than a disjoint
  type keeps the user-editable fields inside the stored config, so the edit form
  re-renders from it directly.
- `validate_config` is Kea's `ToolkitAssetProcessor`, generalized and typed: parse the
  uploads, raise typed `422` validation errors, store the asset binaries and keep only
  their keys (§3.8), return the stored config. The Kea hook was already an untyped
  params→params transform whose input shape differed from its persisted shape; here the
  two shapes get names. Capabilities without enrichment validate and return `config`
  unchanged (their `StoredConfigModel` *is* `ConfigModel`).
- `chat_controls(config)` computes the chat-time control descriptors for one agent
  instance — evaluated at session-prep time, never persisted (§3.3, §3.7).
- `middleware(ctx)` returns the LangChain middleware **stack** that carries this
  capability's tools and hooks, bound to the turn's context. A list, deliberately: most
  capabilities return one middleware, but the list lets a capability compose its custom
  hook with **prebuilt LangChain middleware** (e.g. `ToolCallLimitMiddleware` scoped to
  its own tools) instead of hand-wrapping them, and lets a capability with several
  concerns (tools + a `before_model` state edit) keep each middleware small. List order
  is preserved within the capability's block (§5.3). Two guardrails: returned middleware
  must act only on the capability's own tools/state channels — agent-global concerns
  (summarization, model fallback, context editing) belong to the platform frame or
  assembly config, never a capability return (they would break §5.3
  order-independence); and interrupt/HITL middleware is excluded — capabilities declare
  `HitlSpec`s instead (§5.4).

### 3.3 Config fields (static) + chat controls (computed) — retires chat-options

**Decision:** the `chat_options.*` taxonomy and `EffectiveChatOptions` are retired —
but the agent-creation and chat-time surfaces are **not** one unified fields list. They
have deliberately different shapes:

**Agent-creation config is a static declaration.** Every instance of a capability is
created through the same form, so `config_fields` reuses the existing metadata-driven
mechanism (`ManagedAgentFieldSpec` → `TuningFieldRenderer`): generated rendering for
scalars, `ui.widget` custom renderer for complex fields (§9). Nothing new here.

**The chat-time surface is a computed projection.** Which controls a chatting user sees
(often not the user who created the agent) depends on what the creator chose at
agent-creation time — e.g. document-access shows its scope-narrowing control only when
the creator enabled session attachments, and passes the bound library ids through as
widget params. Instead of a declarative fields-plus-conditions list, the capability
implements a function:

```python
class ChatControlSpec(BaseModel):
    widget: str                  # id resolved against the composer-control registry (§9)
    params: BaseModel | None     # widget-specific, typed, exported to OpenAPI (§3.5)

def chat_controls(self, config: StoredConfigModel) -> list[ChatControlSpec]:
    """Computed per agent instance at session-prep time (§3.7). List order = display order."""
```

Design points:

- **A function, not a `visible_when` condition language.** A declarative gate would
  inevitably grow comparisons, boolean combinators, then identity references — a worse
  programming language. The function subsumes all of that and stays readable (§11).
- **No chat-time form generation.** Every real chat control today (document picker,
  context prompts, search policy, rag scope, attach) is a bespoke composer widget —
  popover rows and stateful dialogs, some of them *actions* rather than values. The
  backend just names widgets, **in order**; the composer resolves each `widget` id
  against the plugin registry (§9) and silently skips unknown ids (forward-compatible,
  same rule as chat parts). If a family of look-alike simple controls emerges later, the
  kit gains a stock `generic_toggle`/`generic_select` *widget* — one more widget id, not
  a field-metadata system.
- **Ordering across capabilities:** capability registration order, then the returned list
  order within each capability. The composer owns the shared menu shell (§9).
- **v1 boundary — no `identity` parameter.** Controls may depend on agent config, not
  yet on the viewer; this is what makes the result cacheable per instance (§3.7).
  Viewer-dependent gating (e.g. permission-based hiding) can be applied control-plane
  side as a filter on the returned list; adding an `identity` parameter later is a
  trivial in-tree signature change.
- `EffectiveChatOptions` still retires cleanly: its booleans (`attach_files`,
  `libraries_selection`, …) were exactly this projection, hand-computed for one
  hardcoded component (`SearchConfig`), and `bound_library_ids` becomes widget
  `params`.

### 3.4 Assets

A capability declares **zero or more named upload slots**. Each slot has its own accepted
types and its own cardinality, so one shape covers "exactly one `.pptx`" (PPT filler),
"up to N reference PDFs", and mixed cases like "any number of `.pdf` plus exactly one
`.csv`" — two slots, no special mechanism.

```python
class UploadedFile(BaseModel):
    filename: str
    content: bytes

class AssetSlot(BaseModel):
    key: str                             # "template", "reference_docs" — stable id; i18n
                                         #   label key for the generated dropzone; key
                                         #   into validate_config's `uploads` mapping
    accepted_types: list[str]            # [".pptx"]
    min_count: int = 0                   # 0 = optional; >= 1 gates agent Save (PPT filler: 1)
    max_count: int | None = 1            # 1 = single file; None = unbounded
```

`min_count`/`max_count` subsumes the earlier `required: bool` (required ⇔
`min_count >= 1`). The platform enforces cardinality and extension per slot **before**
calling the capability — generic, uniformly-worded `422`s — so `validate_config` only owns
content validation. It receives `uploads: Mapping[str, list[UploadedFile]]` keyed by
slot key; a single-slot capability reads `uploads["template"][0]`. A stateless analyze
endpoint (for inline pre-save feedback, e.g. PPT slide errors) is just a route on the
capability's `router`. Binaries are never persisted with the agent config —
`validate_config` stores each through the KF-backed asset store and keeps only the
storage keys in the stored config (§3.8); multi-file slots store a `list[str]` of keys.

### 3.5 `CapabilityContext` — the typed runtime/LLM split

This is the "don't mix runtime info with LLM-exposed params" requirement, formalized:

```python
@dataclass
class CapabilityContext(Generic[StoredT, TurnOptionsT]):
    identity: Identity            # user_id, session_id, team_id, agent_instance_id
    config: StoredT               # this capability's typed stored config (§3.2, §3.8)
    turn_options: TurnOptionsT    # this capability's typed chat-time values
    team_settings: BaseModel      # this capability's typed per-team enablement settings (§8.2); EmptyModel until Tier 3
    services: RuntimeServices     # ports: KF client, workspace fs, stores, model factory
```

Tools receive **only LLM args** in their signature; identity/config/options/services
reach the tool through the middleware closure and (Tier 2+) `runtime.context`.

**Typing turn options when active capabilities vary per agent.** Nothing ever consumes
"all turn options" as one type — each capability reads only its own slice. So there is no
per-agent composite type; the envelope is namespaced with typed leaves:

- **Wire:** `RuntimeExecuteRequest.turn_options: dict[str, dict]`, keyed by capability id.
  The envelope is generic; the key is the discriminator.
- **Turn start:** the runtime resolves the instance's active capabilities and validates
  each slice against that capability's `TurnOptionsModel` (unknown capability id or invalid
  slice → typed `422`, same style as `validate_config`). Each capability's middleware gets
  a `CapabilityContext[StoredT, TurnOptionsT]` carrying only its own typed models — inside
  a capability everything is statically typed; only the assembly loop is generic.
- **Frontend:** every `TurnOptionsModel` and `ChatControlSpec.params` model is exported
  into the OpenAPI schema (the same way `chat_parts` extend the `UiPart` union), so
  codegen yields `DocumentAccessTurnOptions`, `PptFillerTurnOptions`, …. Each composer
  widget is typed against *its* generated model and writes into
  `turnOptions[capabilityId]`; no component ever reads the whole envelope.

This is **not** the generic-envelope anti-pattern rejected for chat parts (§11): parts
need union dispatch — a renderer receives a part of unknown kind and must discriminate.
Turn options are never dispatched; producer (widget) and consumer (capability middleware)
both know the capability id statically, so a keyed map with typed leaves is the correct
shape.

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
contract is silently renamed. A capability's `manifest.chat_parts` entries are the
`UiPart` subclasses it contributes to that union (§4).

> If the team prefers, renaming the type `UiPart → ChatPart` is a reasonable but separate
> **contract amendment** (RUNTIME-EXECUTION-CONTRACT §10.1 + OpenAPI regen + frontend
> `Type.ts`), out of scope for this RFC.

### 3.7 Where chat controls are computed — and cached

Capability code lives in the pod (§7); the frontend gets its session prep from
control-plane. Two existing facts make prep-time evaluation the cheap option:

1. **The control-plane→pod channel already exists on request paths** —
   `_fetch_runtime_templates` / `_fetch_mcp_catalog`
   (`control_plane_backend/product/service.py`) are live HTTP calls made during catalog
   listing and instance creation.
2. **Agent save already round-trips to the pod regardless**: `validate_config` is
   capability code (PPT filler parses the uploaded `.pptx`) and §7 forbids capability code
   in control-plane. `chat_controls` reuses the same capability endpoint at a different
   moment.

**Model: the function is the only truth; nothing derived is persisted.**

- At session prep, control-plane asks the instance's pod to evaluate
  `chat_controls(config)` and ships the descriptors on `ExecutionPreparation` — the slot
  CHAT-UI §3.4 already reserves for `effective_chat_options`.
- Control-plane may cache the result **cache-aside only**, keyed by
  `(capability_id, manifest.version, config_hash)`. A pod deploy bumps `manifest.version`
  → old entries miss → next prep recomputes. There is **no recompute-all-agents
  migration, ever**; rolling deploys with mixed pod versions each key their own entries.
- Do **not** "optimize" this into a computed-at-save persisted field: it saves no
  round-trip (save calls the pod anyway for `validate_config`) and silently serves stale
  controls after every capability-logic change until someone remembers to run a backfill.

Flow: **agent save** → pod `validate_config` → stored config persisted (§3.8) ·
**session prep** → pod `chat_controls(config)` (version-keyed cache) →
`ExecutionPreparation` → composer resolves widget ids (§9).

> **As implemented (2026-07-11, #1976).** `AgentCapability.chat_controls(config)
> -> list[ChatControlSpec]` (default `[]`) is evaluated on the pod by
> `POST /agents/capabilities/chat-controls` (`evaluate_chat_controls_batch`,
> same bearer as `/agents/*`), which returns one `ChatControlsResult` per
> requested capability — its installed `manifest_version`, the JSON-safe
> `ChatControlItem`s in returned-list order, or a per-entry `error` (an
> uninstalled capability or an unresolvable stored slice, RFC §3.9, is skipped,
> never a failed batch). Control-plane `_resolve_chat_controls` (in
> `product/service.py`) resolves the instance's selected capabilities in the
> pod-advertised catalog (registration) order, serves the in-process LRU keyed
> `(capability_id, manifest.version, config_hash)`, batch-evaluates only the
> misses, and — guarding a mid-deploy version skew (`key.version ==
> result.manifest_version`) — caches nothing derived. The flattened
> `ChatControlDescriptor`s (each tagged with `capability_id`) ship on
> `ExecutionPreparation.chat_controls`, the slot the retired
> `EffectiveChatOptions` occupied. **Retirement:** `EffectiveChatOptions`, the
> control-plane `_resolve_effective_chat_options` resolver, and the
> `chat_options.*` control-plane reader are removed; the projection now lives in
> `McpCapability.chat_controls` (§3.3), which emits the stock widgets
> `attach_files` / `document_scope` (carrying `bound_library_ids` as params) /
> `search_policy` / `rag_scope` — restoring visibility/defaults/bound-ids
> without rebuilding the bespoke interlocking UX #1978 dropped (the chosen
> search values still travel on `RuntimeContext` Group C, not `turn_options`).
> The `ManagedAgentInstanceSummary` chat-affordance hint is **dropped** (not
> re-added as controls): chat controls are a session-prep projection, so the
> composer fetches them via an eager prepare-execution at chat open, not off the
> admin listing. `turn_options: dict[str, dict]` on the execute request is
> validated at turn start by `validate_turn_options` against each capability's
> `TurnOptionsModel` (unknown/unselected id or invalid slice → typed 422 before
> streaming); each capability's middleware receives only its own typed slice.

### 3.8 Persistence — where a capability instance lives

A **capability instance** — capability X enabled on agent instance Y with parameters Z — is
not a new entity and gets no new table or backend. It persists where all per-instance
agent config already persists: the control-plane's `agent_instance` row, inside the
serialized `ManagedAgentTuning` (`tuning_json` — `models/agent_instance_models.py`,
`config/models.py`). Swift already holds the proto-shape of this: MCP activation is a
list of enabled items plus per-item params (`selected_mcp_server_ids`,
`mcp_config_values`). The capability system generalizes that trio — and then **retires
it**:

```python
class ManagedAgentTuning(BaseModel):
    ...
    selected_capability_ids: list[str] | None   # None = template default; [] = none; else exact set
    capability_config: dict[str, dict]          # capability_id -> {"schema_version": manifest.version,
                                              #   "config": StoredConfigModel dump} — opaque to control-plane (§3.9)
    # REMOVED (Tier 1): mcp_servers, selected_mcp_server_ids, mcp_config_values
    #   — an MCP server IS a capability, id == the catalog server id (no prefix,
    #     #1988); its selection and per-server config become ordinary capability
    #     slices. One mechanism, not two.
```

Design points:

- **Control-plane stores opaque, pod-validated JSON.** §7 forbids capability code in
  control-plane, so it cannot hold the typed `StoredConfigModel`s — and does not need
  to. Agent save already round-trips to the pod (§3.7); what comes back from
  `validate_config` is the stored config, persisted verbatim. The pod is the schema
  authority; the control-plane is the durable store. Same trust boundary as tuning
  today — "config only, never a secret" — and now also **never a blob** (below).
- **Delivery to the runtime is the existing pull, unchanged.** Config is not shipped on
  the execute request. The pod resolves the instance through the team-scoped runtime
  binding (`GET /teams/{team_id}/agent-instances/{id}/runtime` →
  `ManagedAgentRuntimeBinding.tuning`), then validates each `capability_config[id]` slice
  against that capability's `StoredConfigModel` at agent-assembly time — the same
  slice-validation pattern §3.5 uses for `turn_options`. The typed result is what
  `CapabilityContext.config` carries.
- **Save-time availability check.** `selected_capability_ids` is only meaningful against
  the pod the instance is bound to: at agent save, control-plane validates the selected
  set against the capabilities that pod advertises (aggregated manifests, §7) and rejects
  unknown ids with a typed `422` — same style as the slice validation above. This is
  what keeps §7's install-time mixing safe: an instance can never reference a capability
  its pod does not have installed.
- **The MCP trio removal lands with Tier 1** (`McpCapability`): Tier 0 adds the two new
  fields alongside the existing ones; Tier 1 migrates MCP selection/config into
  `mcp:<server>` capability slices and deletes `mcp_servers`,
  `selected_mcp_server_ids`, and `mcp_config_values` from `ManagedAgentTuning` (and
  their mirrors on the SDK `AgentTuning`). **Resolved 2026-07-09:** existing rows are
  converted by a one-shot alembic data migration in control-plane (the mapping is
  mechanical and 1:1 — `selected_mcp_server_ids` → `mcp:<id>` entries in
  `selected_capability_ids`, `mcp_config_values[id]` → `capability_config["mcp:<id>"]`,
  `None`/`[]`/exact-set semantics carry over). Model change, data migration, and pod
  release ship together in a single release — downtime is acceptable; no dual-read
  window.
- **Asset binaries never enter `tuning_json`.** Kea already solved this: agents stored
  blobs through a KF-backed asset service (KF `AssetController` `/agent-assets/*` +
  `AssetService`; `ToolkitAssetProcessor` uploaded the blob at save time and persisted
  **only the storage key** in agent params). Swift has the underlying plumbing —
  `BaseContentStore.put_object` (whose docstring already names "agent assets"),
  `/fs/upload`, `KfWorkspaceClient.fs_upload` — but the agent-asset scope and the
  `upload_agent_config_blob` client method were not ported (the `KfWorkspaceClient`
  docstring still advertises them). **This RFC does not change that service.** Porting
  the KF agent-asset scope is a small, separate dependency of the first asset-bearing
  capability (#1903 PPT filler); the pilot #1906 does not need it. In capability terms:
  `validate_config` uploads via the KF client on `SaveContext.services`, writes the
  returned keys into the stored config (one per uploaded file, grouped by slot), and
  the upload bytes are discarded (§3.4).

> **As implemented (2026-07-11, #1978 — `fred_runtime/capabilities/mcp.py`,
> `fred_runtime/app/agent_app.py`, `control_plane_backend/product/service.py`,
> alembic `f5b6c7d8e9a0`).** The MCP trio is retired. An MCP server is an
> `mcp:<catalog id>` capability: `build_mcp_capability(server)` builds one
> `McpCapability` per **enabled** `mcp_catalog.yaml` entry, registered at pod
> boot by `boot_capability_registry(mcp_servers=...)` alongside entry-point
> discovery, so a catalog id colliding with an installed capability still fails
> boot loudly. The `mcp:<server>` id contract lives in
> `fred_sdk.contracts.capability.mcp_ids` (shared by runtime + control-plane).
> **Contained Tier-1 shape (execution loop untouched):** an `McpCapability`
> contributes ONLY a prompt-fragment middleware carrying the catalog server's
> `agent_instructions` (delivered through `awrap_model_call`, replacing the
> `_apply_runtime_tuning` system-prompt append). Live MCP tool loading stays in
> `FredMcpToolProvider`, now driven by `_PodAgentSettings.active_mcp_servers`
> (not `AgentTuning.mcp_servers`), which agent assembly derives from the
> selected `mcp:<id>` capabilities. **The `None` fix pinned by tests:** the
> migration MATERIALIZES every MCP-bearing row's `selected_capability_ids` to an
> exact set (never `None`, because `selected_mcp_server_ids=None` meant "all",
> whereas `selected_capability_ids=None` means "none"), and the runtime maps a
> `None` selection to `definition.default_mcp_servers` — that pair is what makes
> "behaves identically after upgrade" true, and it also covers the direct /
> inline-tuning execution paths (which synthesize a template-default tuning so
> their grounding instructions survive). Per-server config moved from
> `mcp_config_values[id]` to `capability_config["mcp:<id>"]`; it has no runtime
> consumer, so the only reader is control-plane `_resolve_effective_chat_options`,
> re-pointed to the `mcp:<id>` slices with declared defaults fetched from the
> pod-advertised `CapabilityCatalogEntry.config_fields`. **Deviation:** the
> catalog-default fallback there depends on the pod being reachable at read time;
> the durable move of chat-option resolution to computed `chat_controls` (§3.3)
> stays with the chat-controls sibling ticket.

> **As implemented (2026-07-15, #1988 — amends #1978/#1980; supersedes the
> `mcp:<id>` prefix everywhere it appears above and below).** Control-plane
> startup crashed seeding capability defaults: MCP-derived capabilities carried
> hardcoded `team_scope=DEFAULT_ON`, so the seeder wrote FGA tuples for them, but
> `mcp:<server>` contains `:`, which OpenFGA rejects in object ids (HTTP 400).
> Root cause was architectural, not a formatting bug: MCP capabilities had been
> carved OUT of the FGA capability type, leaving fragile `is_mcp_capability_id`
> skips scattered across every FGA path — the seeder simply missed its skip.
> **Fix: MCP servers become first-class team-gated capabilities, not a
> special-cased id shape.**
> - **No more prefix.** Capability id == the MCP catalog server id verbatim
>   (e.g. `mcp-bank-core-demo`). `fred_sdk.contracts.capability.mcp_ids` and all
>   its helpers (`is_mcp_capability_id` included) are retired. `CapabilityManifest.id`
>   now enforces `^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$` (FGA- and URL-safe) so a bad
>   id fails pod boot (still via `DuplicateCapabilityIdError` on collision with an
>   installed capability id) instead of crashing control-plane tuple writes later.
> - **`MCPServerConfiguration` gains `team_scope: default_on | admin_gated`**
>   (default `admin_gated` — deployments must opt a server into `default_on`;
>   this deliberately breaks the old "every MCP server usable by every team"
>   retro-compat default). `TeamScopePolicy` moved to `fred_sdk.contracts.models`,
>   re-exported from `capability/manifest.py`.
> - **FGA now gates MCP capabilities exactly like any other**: `can_use` at
>   agent save, catalog filtering, `default_on` seeding, admin per-team
>   enable/disable, and disable → dependent-instance suspension
>   (`CAPABILITY_ACCESS_REVOKED`) all apply uniformly. §8.1's "MCP capabilities
>   are out of the FGA type's scope and never filtered" (below) no longer holds.
> - **Nuance kept:** a catalog server *disabled* in the pod yaml stays
>   warning-only (never availability-suspension — the live tool provider skips
>   it at assembly); MCP-ness is now detected via the pod's MCP catalog fetch
>   (control-plane) / registry membership (runtime), never by id sniffing. A
>   server *removed* from the yaml now suspends dependents like any vanished
>   capability — this reverses §3.9/#1975's "MCP selections never suspend"
>   (below), which was itself downstream of the carve-out this issue fixes.
> - **Data migration:** a follow-up alembic migration rewrites persisted
>   `mcp:X` ids to `X` in agent-instance tuning (`selected_capability_ids` and
>   `capability_config` keys).

> **As implemented (2026-07-11, #1906 — `fred_runtime/capabilities/document_access/`,
> `fred_sdk/contracts/runtime.py`, `fred_runtime/integrations/v2_runtime/adapters.py`,
> `fred_runtime/app/agent_app.py`).** The #1906 pilot introduces the platform-service
> seam capabilities use: **capabilities reach platform services only through typed
> optional ports on `RuntimeServices`; the per-turn binding and the raw access token
> never enter `CapabilityContext`.** `DocumentSearchPort` (a new optional, additive
> field on the frozen `RuntimeServices` — RUNTIME-EXECUTION-CONTRACT §8.15) takes scope
> PARAMETERS only; `DocumentSearchAdapter` captures the binding + token privately and
> exposes only `search(...)`, wired in `_build_runtime_services` and reaching the
> capability as `ctx.services.document_search`. Rejected alternatives: (a) passing the
> binding into `CapabilityContext` (token-leak / security regression); (b)
> `services.tool_invoker` with `tool_ref="knowledge.search"` (cannot express
> per-capability config scoping — reads scope from `runtime_context`, not the payload).
> Full as-implemented notes (scoping precedence, deferred tools, duplicate-tool story,
> rename) are in §10.1.

### 3.9 Instance lifecycle — suspension and config upgrades (resolved 2026-07-09)

Save-time validation (§3.8) covers saves, which are rare; pods deploy far more often.
The mismatches therefore appear at **agent-assembly time**:

1. the instance references a capability its pod no longer advertises (package removed,
   rollback), or the team's ReBAC `can_use` grant was revoked (§8) — expected to be
   common with temporary grants;
2. the persisted `capability_config` slice no longer validates against the current
   `StoredConfigModel`.

**Rule: a broken capability suspends the agent — it never silently degrades.** An agent
missing its document-access tools would confidently answer from priors; that trust
failure is worse than unavailability.

`suspended` is a **platform-forced state distinct from the editor's `disabled`
toggle**, carrying a typed reason: `capability_unavailable`, `capability_access_revoked`,
or `capability_config_invalid`. A suspended agent is hidden from chat-only team members;
editors/owners see it with a warning and a **locked** enable toggle. The edit form
renders the broken capability in an error state with a plain-language message and the
two fix paths: untick the capability and re-enable (the agent works without it), or
contact a platform admin. **A successful save clears the suspension** — save-time
validation already exists, so no second mechanism is needed.

**Detection is both lazy and proactive.** The pod hitting the mismatch at assembly
returns a typed error naming the capability (safety net; control-plane flips the
state), and the control-plane Temporal worker (`control-plane-lifecycle` queue) runs
a low-priority reconciliation sweep whenever the aggregated manifests change (pod
deploy/registration) or an enablement tuple is deleted — so agents disappear from the
catalog *before* anyone hits an error. v1 admin surface: a structured log + metric
per suspension and the suspended state visible in agent lists; a per-capability health
column joins the Tier 3 dashboard (§8.5).

**Config versioning.** Each `capability_config` slice is stored as
`{"schema_version": manifest.version, "config": {...}}`. The optional hook

```python
def upgrade_config(self, stored: dict, from_version: str) -> StoredT:
    """Default: plain StoredConfigModel validation. Override to migrate old shapes."""
```

runs **lazily at read time** (assembly, `chat_controls`) — never as a mass row
migration (§3.7's rule) — and the upgraded form is persisted at the next save. If it
raises → `suspended(capability_config_invalid)` ("parameters for capability X are no
longer valid — reset them and re-save the agent"). The convention keeping this rare:
`StoredConfigModel` changes should be additive with defaults.

> **As implemented (2026-07-11, #1974 — selection end-to-end across
> `fred_sdk`, `fred_runtime/capabilities/` + `app/agent_app.py`,
> `control_plane_backend/product/`, and `apps/frontend` TeamAgentsPage).**
> The Tier 0 selection path is live end-to-end (create/edit → save-time
> validation → assembly → execution) with these decisions, some deviating from
> the prose above:
> - **Wire models live once in fred-sdk** and are imported by both the pod and
>   control-plane: `StoredCapabilityConfig` (the `{schema_version, config}`
>   envelope) and `CapabilityCatalogEntry` (the JSON-safe manifest projection).
>   No parallel type is declared in either backend or in the frontend (the
>   frontend consumes the generated `CapabilityCatalogEntry`/`FieldSpec` types).
> - **Catalog is advertised per template, not via a new endpoint.**
>   `GET /agents/templates` gained `available_capabilities: list[CapabilityCatalogEntry]`
>   (pod-scoped, mirrored per template like `available_mcp_servers`);
>   control-plane aggregates it into `AgentTemplateSummary.available_capabilities`.
>   No second catalog fetch on either the control-plane or the frontend.
> - **`selected_capability_ids = None` currently means "no capabilities"**, not a
>   non-empty template default: templates do not yet declare default capability
>   sets, so `None`/`[]` are behaviourally equivalent today. The tri-state field
>   is kept for forward-compatibility; the frontend always submits an explicit
>   list, and omits the capability fields entirely for capability-less templates
>   so a plain edit never triggers the live-pod re-validation.
> - **"Typed 422" is the existing convention, not a structured field-error
>   envelope.** Unknown-id and config-invalid failures surface as
>   `EnrollmentError(..., http_status=422)` / `HTTPException(422, detail=...)`
>   with the pod's plain-language wording propagated verbatim; no per-field error
>   envelope exists anywhere in the stack, so none was introduced. Pod-unreachable
>   on a capability write is a `503`; a malformed pod envelope is a `502`.
> - **Asset-slot enforcement lives pod-side** in generic platform code
>   (`enforce_asset_slots`, runs before capability code) with uniform 422 wording;
>   control-plane propagates that wording. **Control-plane upload forwarding**
>   (multipart agent save for asset-bearing capabilities) **is deferred to the
>   first asset-bearing capability port (#1903 PPT filler)** — the pod-side
>   `POST /agents/capabilities/{id}/validate-config` path is in place and
>   test-covered; only the control-plane→pod multipart relay is pending.
> - **Execution is ReAct-only.** A graph agent definition that carries a capability
>   selection fails loudly with `CapabilityError` (§5.4 / §3.9 "never silently
>   degrade"); typed contexts + the `HitlSpec` gate reach the tool loop through the
>   #1973 middleware frame.

> **As implemented (2026-07-11, #1975 — suspension lifecycle in
> `control_plane_backend/agent_instances/suspension.py`, `product/service.py`,
> the `agent_instance.suspension_reason` column, and `apps/frontend` AgentCard).**
> The three-reason suspension state is live; decisions and deviations from the
> prose above:
> - **Storage is one nullable column, not a state machine.**
>   `agent_instance.suspension_reason` (`VARCHAR(64)`, migration
>   `a6b7c8d9e0f1`): `NULL` = not suspended; else a `SuspensionReason` value
>   (`capability_unavailable` / `capability_access_revoked` /
>   `capability_config_invalid`). It is orthogonal to the editor's `enabled`
>   toggle — a dedicated `AgentInstanceStore.set_suspension(...)` writes it and
>   deliberately does NOT bump `updated_at` (a platform sweep must not look like
>   a user edit). Exposed read-only on `ManagedAgentInstanceSummary`.
> - **Suspension is a pure control-plane product decision — not a checkpointer
>   concern (per the #1971 spike).** The spike proved LangGraph surfaces no
>   assembly/run-time signal and that capability state survives a capability-less
>   turn through `FredSqlCheckpointer` (a missing-channel mismatch is silent, and
>   state survives reinstall). Suspension therefore lives entirely in the
>   control-plane: nothing is written to or read from the checkpointer, so a
>   suspended-then-cleared instance resumes its existing thread unchanged.
> - **Detection is proactive-first via a sweep, with the pod's typed 422 as the
>   assembly-time verdict.** `run_capability_reconciliation_sweep(deps)` walks
>   every instance and, per instance, runs availability
>   (`reconcile_instance_suspension` — a selected non-MCP capability absent from
>   the pod's advertised catalog → `capability_unavailable`) then config health
>   (`reconcile_instance_config_health` — each active stored slice round-trips
>   the pod's `validate-config`; a 422 → `SliceInvalid` → `capability_config_invalid`,
>   which is exactly the typed error the pod raises at assembly, incl. a failing
>   `upgrade_config`). A pod unreachable during the sweep skips its instances
>   (never suspend on a transient outage). The sweep is intended to run on the
>   `control-plane-lifecycle` Temporal queue on manifest change; wiring the
>   Temporal activity is left to the lifecycle-worker slice — the callable is the
>   contract.
> - **MCP selections never suspend.** `mcp:<id>` selections are tolerated at
>   assembly (the live tool provider skips unknown/disabled servers), so a missing
>   MCP server is a catalog warning, mirroring the runtime's
>   `_build_capability_block` — only real capabilities are loud. **Superseded by
>   #1988** (§3.8 note): a server *removed* from the catalog now suspends
>   dependents like any other capability; only a server *disabled* in the pod
>   yaml stays warning-only.
> - **One clearing mechanism: a successful save.** `update_agent_instance` clears
>   any suspension after the save re-validated every active slice through the pod
>   (untick-and-re-save is the fix path for all three reasons). An availability
>   reconcile may additionally clear an availability suspension when the
>   capability returns, but `capability_config_invalid` is cleared ONLY by a save
>   — no second mechanism (RFC §3.9).
> - **Enforcement: `prepare_execution` refuses a suspended instance with a typed
>   409** before issuing any runtime URL — a broken agent fails loudly rather than
>   degrading. Observability: a structured `[capability-suspension]` log + a
>   `agent.suspended_total` / `agent.suspension_cleared_total` KPI counter
>   (dims: team, instance, reason) per transition.
> - **#1980 suspension-trigger entry-point contract (for ReBAC access-revocation,
>   sequenced after #1975).** #1980 exposes no new mechanism: on enablement-tuple
>   deletion it recomputes the capability ids the team may still use and calls
>   the entry point #1975 exposes —
>   `reconcile_instance_suspension(instance, store, available_capability_ids=<remaining>,
>   revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED, kpi_writer=...)`
>   (in `agent_instances/suspension.py`). #1975 performs NO ReBAC check itself; it
>   only exposes this trigger. The `revoked_reason` default
>   (`CAPABILITY_UNAVAILABLE`) is what the manifest-change sweep passes.
> - **Frontend (TeamAgentsPage + AgentFormModal).** A suspended instance is
>   hidden from chat-only members (`TeamAgentsPage` filters on `can_update_agents`)
>   and shown to editors/owners with an error-token warning banner and a **locked**
>   enable toggle (`AgentCard`); it never gets a chat `<Link>` even if its stored
>   status is still `enabled`. The edit form (`AgentFormBody`) renders a
>   plain-language error banner keyed off the reason with both fix paths — for the
>   availability reasons it names the offending capability ids (derived: selected
>   non-MCP ids the template no longer advertises), for `capability_config_invalid`
>   it shows the generic "reset the parameters and re-save" wording (the pod's
>   422 text is not carried on the instance summary). Untick/reset + save clears
>   the suspension via the existing save path — no new frontend mechanism.

---

## 4. Registration collapses the scatter

One registry replaces the five it subsumes. Registering a capability:

- adds its tools/middleware to the agent (replacing the `inprocess_toolkit_registry`
  `if provider ==` chain and, at Tier 1, the `ToolParams` union role),
- contributes its `chat_parts` to the `UiPart` union (§3.6) at model-build time so
  OpenAPI regen picks them up — **the union stops being a hand-edited hotspot**,
- auto-mounts its `router` and auto-registers its `tables` for alembic,
- publishes its manifest to the control-plane catalog (the way templates are published
  today),
- declares its ReBAC team-scope (Tier 3),
- is validated at boot, loudly (resolved 2026-07-09): duplicate capability ids across
  installed packages, duplicate chat-part `kind` discriminators (the `UiPart` union
  must stay unambiguous), missing `required_env` (§7.2), and a required-fields
  `TeamSettingsModel` combined with `default_on` (§8.2) all **fail pod startup**.

The frontend mirror is one plugin object per capability (§8), registered in one index.

Backend registration is one line — or zero: a capability package may declare a
`fred.capabilities` Python entry point and be auto-discovered at pod startup (§7), so for
an externally-authored package, *installing it is the registration*.

> **As implemented (2026-07-10, #1973 — `fred_runtime/capabilities/`).**
> `CapabilityRegistry` + `boot_capability_registry()` (called from the
> `create_agent_app` lifespan) land the discovery and the four named boot
> failures: `DuplicateCapabilityIdError`, `DuplicateChatPartKindError` (also
> guards the builtin `link`/`geo` kinds), `MissingRequiredEnvError`,
> `DefaultOnRequiredSettingsError`. Router mounting, table/alembic
> registration, catalog publication, and the ReBAC scope are later slices
> (#1974+) — the manifest already declares them.

> **As implemented (2026-07-11, #1977 — chat parts land on the `UiPart` union).**
> Five decisions that deviate from or refine the above:
> 1. **Boot moved lifespan → app construction.** `boot_capability_registry()` now
>    runs inside `create_agent_app` construction, before routes capture their
>    response schemas. This is what makes the *offline* OpenAPI export
>    (`scripts/generate_openapi.py`, which never runs the lifespan) include
>    capability chat parts with zero hand edits. Failure is still "pod startup
>    aborts"; `app.state.capability_registry` is set at construction, so any
>    lifespan/route code that reads it (e.g. #1974's endpoints) still works.
> 2. **Union rebuild mechanism** (`fred_sdk/contracts/ui_part_union.py`):
>    `rebuild_ui_part_union(extra)` = base (`link`, `geo`) + extras, rebuilt from
>    scratch every time (never cumulative; `rebuild_ui_part_union(())` restores the
>    frozen contract). It swaps the `UiPart` alias in every importing module's
>    globals **and** rewrites resolved `FieldInfo.annotation` objects before a
>    topo-sorted `model_rebuild(force=True)` — `model_rebuild` alone does *not*
>    pick up a swapped module global (pydantic 2.13 resolves annotations at class
>    creation; verified empirically). Validators resolve the union lazily via
>    `current_ui_part_union()` identity as a cache key.
> 3. **`geo` got a builtin summary-chip renderer.** The RFC assumed `geo` already
>    rendered; it did not (it was silently dropped). A builtin renderer was added
>    alongside `link` so the registry dispatch is uniform across builtin and
>    capability parts.
> 4. **Frontend plugin index** (`src/rework/features/capabilities/index.ts`) ships
>    with `partRenderers` strongly typed and the other three slots
>    (configWidgets / chatTurnControls / sidePanels) typed loosely, to be tightened
>    by their host slices in #1974+. Unknown part kinds are skip-at-render,
>    retain-in-data; a duplicate renderer kind is first-wins + `console.warn`
>    (the backend boot failure is the real guard).
> 5. **Emission pattern** is a documented `cast(UiPart, ...)`: the static alias is
>    the frozen base union, the runtime union is the extended one, so a capability
>    emitting its own part casts through the base type deliberately.

---

## 5. How `create_agent` + middleware is inserted

### 5.1 Requirement → hook mapping

| Capability requirement | LangChain middleware primitive |
| --- | --- |
| Add tools to the agent | `middleware.tools` (static) |
| Dynamic tool built at chat time (PPT filler: schema from parsed template) | `wrap_model_call` editing `request.tools` per model call |
| Runtime context split from LLM args | `context_schema` → `runtime.context` = `CapabilityContext` |
| Edit conversation state (WritableDocument edit notice; attachment-added note) | `before_model` returning a state-update dict via reducers |
| Custom conversation state (small bookkeeping — see below) | `state_schema` with `NotRequired` fields + reducers |
| Contribute a system-prompt fragment (doc-access instructions; `McpCapability` maps the catalog's `agent_instructions` here) | `wrap_model_call` / `modify_model_request` editing the system prompt — no first-class manifest hook needed |
| Guardrails / summarization / PII / retries | **prebuilt LangChain middleware — free** |
| Tool approval (HITL) | custom `FredHitlMiddleware` (§5.4) |

**State is edited only from inside the graph** (a middleware hook or a tool) —
resolved 2026-07-09; no out-of-band conversation-state write seam exists or is
planned. WritableDocument's worked shape: document *content* lives in the capability's
own table (edited by the side panel via the capability `router`, §9.1, and by the agent
tool via `services`); graph state carries only a small `doc_versions_seen` channel;
`before_model` compares the table's version counter against it and injects the
"document was edited" note lazily at the next turn (a version counter, not
timestamps, so the agent's own tool edits never self-notify). The persistence half of
this claim is validated by the §12 Q3 checkpointer spike.

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
| HITL gate (`gate_tools` + `interrupt`, custom French payload) | `FredHitlMiddleware` — resolved 2026-07-09, see §5.4 |

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
5. `FredHitlMiddleware` — the interrupt gate with Fred's `HumanInputRequest` payload (§5.4).
6. Per-capability middleware — one *stack* per capability (usually a single middleware),
   carrying its tools + `before_model` state edits, possibly alongside tool-scoped
   prebuilts (§3.2).

**Must-test regressions:** (1) HITL interrupt payload round-trip, (2) dangling-tool
sanitize on a poisoned checkpoint, (3) Mistral reasoning-strip on replay, (4)
per-operation model routing still selects the right model.

**Gating spike (first task of this migration — resolved §12 Q3):** before the five
middleware are written in anger, a toy middleware with one `state_schema` field + a
reducer runs against `FredSqlCheckpointer` through *write → executor rebuild → read →
`interrupt()` → resume*, with JSON-primitive and Pydantic-model values. Known risk to
probe: the checkpointer's `JsonPlusSerializer` msgpack allowlist is closed (one legacy
entry), so Pydantic values will likely come back degraded — expected outcome is the
rule "capability state is JSON-primitive, or registration extends the allowlist". The
mismatch case (checkpoint carries a channel from a capability no longer installed) also
gets probed — its behavior feeds §3.9.

> **Spike result (2026-07-10, #1971 —
> `libs/fred-runtime/tests/test_spike_capability_state_1971.py`).** Validated on
> SQLite and live Postgres, langgraph 1.2.5 / langgraph-checkpoint 4.1.1. The rule
> holds as expected: **capability state is JSON-primitive, or registration extends
> the msgpack allowlist.** Observations: (1) JSON-primitive channels round-trip
> intact through rebuild, `interrupt()` and resume; reducers keep accumulating from
> SQL-loaded state. (2) Pydantic channel values come back **degraded to a plain
> dict** (raw constructor payload) with a logged
> `Blocked deserialization of <module>.<name>` warning — no exception; the same
> stored bytes are restored to the typed instance by
> `serde.with_msgpack_allowlist([Model])`, so capability registration extending the
> allowlist is a viable per-capability opt-in. (3) Mismatch: orphaned channels are
> **silently hidden** at graph level (`aget_state` omits them, turns succeed with no
> error) while the raw checkpoint keeps carrying their versions forward, so
> reinstalling the capability **recovers the state**. Consequence for §3.9: LangGraph
> provides *no* signal at assembly or run time — suspension detection must be Fred's
> own (assembly-time manifest check), and because state survives a capability-less
> turn, suspension is a product decision (silent degradation is the failure §3.9
> forbids), not a technical necessity. Default SDK rule: capability `state_schema`
> channels are JSON-primitive; allowlist extension at registration is the escape
> hatch for typed channels.

### 5.3 Composition order (resolved 2026-07-09)

Middleware list order is semantic in `create_agent` (`before_model` runs in list
order; `wrap_model_call` nests, first = outermost). The rule:

- **The platform owns a fixed frame**: `CheckpointHygieneMiddleware` first (nothing
  may read unsanitized history), `TracingKpiMiddleware` outermost on model calls,
  routing/prompt/HITL at fixed positions. Capability middleware is inserted as a block
  *inside* that frame; capability authors never position themselves relative to core —
  they cannot get it wrong.
- **Within the capability block: sorted by capability id** — the same deterministic order
  used for chat controls and prompt contributions. Not `selected_capability_ids` order
  (a UI reorder must not change behavior), not registration order (varies per
  assembly). Within one capability's returned stack, the list order is preserved as
  authored — the same "list order is meaningful" rule as `chat_controls` (§3.3).
- **Capabilities must be mutually order-independent** (SDK contract rule): no capability
  reads another capability's state channels or depends on its prompt contributions. If
  a genuine cross-capability dependency ever appears, an explicit
  `run_before`/`run_after` declaration is future work — never implicit ordering.

> **As implemented (2026-07-10, #1972 —
> `libs/fred-runtime/fred_runtime/react/react_middleware.py`,
> `build_react_platform_middleware_frame`).** The frame, in list order:
> `CheckpointHygiene` → `ModelRouting` → `DynamicPrompt` → **capability block
> slot** → `TracingKpi` → `FredHitl` → `ToolCallLimit` (only when
> `max_tool_calls_per_turn` is set). Two deviations from the wording above,
> both forced by behavior preservation:
> (1) hygiene is a `wrap_model_call` request override, not a `before_model`
> state hook — the legacy loop sanitized/trimmed/stripped the *model input
> only*; a `before_model` state update would rewrite the checkpoint and
> destroy history. As the first (outermost) wrap it still guarantees nothing
> inside sees an unsanitized model request.
> (2) `TracingKpi` is the *innermost* wrap, not outermost: the legacy wrapper
> timed the bare `model.ainvoke(...)` after routing had already selected the
> model, so span/KPI `model_name` dims record the routed model — an outermost
> span would tag the pre-routing model and change operator-visible metrics.
> `after_model` hooks run in reverse list order, so `ToolCallLimit` (last)
> gates before `FredHitl` — over-limit calls are blocked before a human is
> asked to approve them.

### 5.4 Tool approval (HITL) — resolved 2026-07-09 (§12 Q2)

Keep Fred's gate and wire format; make the *declaration* capability-owned:

- **One platform `FredHitlMiddleware` per agent** — multiple HITL middlewares do not
  compose (each independently rewrites the last AI message). It preserves today's
  semantics byte-for-byte: sequential per-call interrupts, the localized
  `HumanInputRequest` payload, the existing resume flow — zero transcoder, frontend,
  or contract change inside the Tier 2 migration.
- **Capabilities flag their tools** with an `HitlSpec` on the tool declaration:
  `require: bool`, optional `when: Callable[[HitlGateRequest], bool]` (LangChain's
  `when` idea, upgraded: `HitlGateRequest` carries the tool call, the real tool
  object, **and the capability's typed `CapabilityContext`** — so a gate condition can
  read instance config, e.g. "pause writes outside this agent's configured workspace
  root"), an optional `question` override, and `allowed_decisions` (forward-compat:
  the gate renders proceed/cancel today; richer decisions such as edit-args are a
  later, deliberate contract amendment that changes no capability declarations).
- **Fail-closed:** a `when` predicate that raises counts as "interrupt". Predicates
  must be pure and fast; anything needing I/O is its own middleware.
- **Assembly merges three sources** into the one gate: operator policy
  (`ToolApprovalPolicy.always_require_tools`, kept as the admin override), capability
  `HitlSpec`s, and the legacy name-prefix heuristics as fallback for non-capability
  tools — the heuristics retire at Tier 1, when every tool belongs to a capability.

> **As implemented (2026-07-10, #1973 —
> `FredHitlMiddleware._gate_decision`, `fred_runtime/capabilities/assembly.py`).**
> Declaration surface: `HitlSpec.tool` names the gated tool and specs are
> returned from `AgentCapability.hitl_specs()`; assembly binds each spec to its
> capability's typed context + tool object (`CapabilityHitlBinding`) for the one
> gate. Merge semantics pinned by tests: (1) for a declared tool the spec is
> authoritative over the name-prefix heuristics; (2) a raising `when` fails
> closed to interrupt; (3) the operator exact list still forces approval;
> (4) **a capability's `require`/`when` gates even when the operator approval
> toggle is disabled** — the toggle controls *platform* gating and does not
> silence a capability author's own safety declaration (fail-closed reading of
> "admin override": the override adds gates, it does not remove declared ones).
> `HitlSpec.question` replaces the approval question verbatim (capability owns
> its i18n); title, choices, and wire shape are unchanged.

> **As implemented (2026-07-11, #1978 — `FredHitlMiddleware`,
> `fred_runtime/support/tool_approval.py` deleted).** The legacy name-prefix
> heuristics (`READ_ONLY_TOOL_PREFIXES` / `MUTATING_TOOL_PREFIXES`) are retired
> at Tier 1. A tool that NO capability declares is now gated only by the operator
> exact list: approval is required iff `approval_policy.enabled` AND the tool is
> in `always_require_tools`. Capability `require`/`when` still gate regardless of
> the toggle (per the #1973 note above). This is behavior-preserving for every
> shipped configuration — no in-tree definition enables the approval toggle, so
> the prefixes were latent. **Deviation from §5.4's premise:** under the
> contained Tier-1 MCP design, MCP tools come from `FredMcpToolProvider` (not a
> capability middleware), so they are not capability-`HitlSpec`-owned; for
> deployments that had enabled the toggle, mutating-prefix tools are no longer
> heuristically gated — the operator list and capability specs are the only
> sources.

---

## 6. Maturity tiers

Each tier is a strict superset of the previous. **Decision (2026-07-09): the team
approved all tiers.** Implementation starts with the Tier 2 `create_agent` migration
(so capabilities are native middleware from day one), then the Tier 0/1 product
surface, with Tier 3 following shortly after — implementation tickets may cross tier
boundaries. Tiers are now *scoping units*, not a commitment ladder.

| Tier | Deliverable | Touches execution loop? | Risk |
| --- | --- | --- | --- |
| **0 — Capability model + registry** | `AgentCapability`/manifest + one registry that collapses the scatter. Runtime half is native middleware (Tier 2 lands first). | No | Low |
| **1 — Capability chat surface + MCP-as-capability** | Retire chat-options/`EffectiveChatOptions`; capabilities declare static `config_fields` and compute chat controls (§3.3), rendered through the composer slot (§9). Generic `McpCapability`; `mcp_catalog.yaml` = pre-registered MCP-capability instances; retire `ManagedAgentTuning.{mcp_servers, selected_mcp_server_ids, mcp_config_values}` in favor of capability slices (§3.8). One Tools tab. | No | Low |
| **2 — Middleware runtime** | Migrate `_create_compiled_react_agent` → `create_agent`; capability runtime half becomes a real `AgentMiddleware`; author the 5 core middleware (§5.2). ReAct + Deep converge. | **Yes** | Medium, contained |
| **3 — Team scoping & enablement** | `capability` OpenFGA type (§8.1); per-team enablement with typed `TeamSettingsModel` settings (§8.2); admin Capabilities dashboard (§8.5). Extends `TEAM-PLATFORM-POLICY-RFC`. | No | Low–Medium |
| **4 — Capability SDK** | Formalize manifest + middleware + typed parts as a published `fred-sdk` surface; capabilities authored like agents. | No | Low |

> **Dropped (2026-07-09): the Tier-0/1 inprocess adapter.** An earlier revision bridged
> capabilities onto the `inprocess_toolkit_registry` seam so Tiers 0/1 could ship before
> the execution-loop migration. With the team committing to Tier 2 first, the adapter
> is dead weight and is **not built**: the capability runtime half is `AgentMiddleware`
> from the start (this also removes the need for any interim prompt-fragment bridge —
> middleware edits the model request directly, §5.1).

**Non-goal (documented):** Tier 4 stops short of *untrusted third-party* capability
authoring and *sandboxed/iframe UI parts*. The current topology — static
`runtime_catalog_sources` config, no dynamic pod registry, pod-local invocation only
(only `LocalRegistryAgentInvoker` is wired) — is nowhere near needing this. Capabilities
are **in-tree / SDK-authored and trusted**; UI parts are React components committed to
Fred. A clean manifest (typed parts, declared fields) keeps the door open to a
sandboxed renderer later without paying for it now. This belongs in a **future RFC**, not
this one (candidate mechanisms — build-time npm widget packages mirroring §7's backend
package model, then a sandboxed iframe renderer — are sketched at the end of §9).

---

## 7. Distribution & topology — capabilities are packages, pods are assemblies (resolved 2026-07-09)

**Facts (verified):** multiple `fred-runtime` pods, each a static in-code agent registry;
control-plane maps template→pod via static config + DB `RuntimeBinding`; cross-pod
invocation is abstraction-ready (`RemoteSseAgentInvoker`) but **unwired** —
`invoke_agent` is pod-local. `fred-sdk` + `fred-runtime` are already the fork-free SDK,
and a pod is already a **thin assembly**: `fred_agents/registry.py` + a
`create_agent_app(registry=...)` call, ~60 lines — everything real lives in the
libraries.

An earlier draft of this section said "capabilities live in the pod, with the agent". That
sentence conflated two units. The pod is a *deployment* unit, not a *code-ownership*
unit: if a capability were owned by the pod that authored it, a team shipping only a new
capability could never mix it with the default set — an agent instance runs on one pod —
and we would recreate the private-fork problem the pod topology was built to end. The
platform bet is that **nobody writes agent code**: the ReAct loop is done; a new agent is
a new *context* (prompt + capabilities + their UI). For that bet to hold, the unit teams
author and share must be the capability, and mixing must be cheap.

**Resolution: mixing happens at install time (package composition), not at runtime
(pod federation).** Three authoring lanes, by how much of the vertical the team needs:

| Team need | What they author | Fred code written |
| --- | --- | --- |
| **Tools + config fields + prompt fragment** | An **MCP server**, registered in the catalog → it *is* a capability (Tier 1), id == the catalog server id (no prefix, #1988) | **Zero.** Mixable with everything, on any pod — MCP is already a network protocol, so this lane federates across pods for free |
| **Full vertical** (`validate_config`, middleware, `router`, `tables`, team settings) | A **capability Python package** built on `fred-sdk` | The package only — no fred code copied or modified, same non-fork guarantee agents have |
| **First-party** (document-access, PPT filler, WritableDocument) | Same package model — a `fred-capabilities-core` package installed in the shared `fred-agents` pod | In-tree |

Design points:

- **A team pod becomes an assembly:** base image + `pip install fred-capabilities-core
  acme-drive-capability`. The generic ReAct template ships in `fred-runtime`, so a
  capability-only team writes no agent code: their pod exposes the stock template with an
  extended capability catalog, and users mix `selected_capability_ids` freely in the UI.
  If the platform operator trusts the package, they install it into the shared
  `fred-agents` pod instead — no team pod at all.
- **Default capabilities move out of app code** into the installable
  `fred-capabilities-core` package, so every assembly gets them by default. This is the
  concrete guarantee against the fork nightmare: "my capability + the defaults" is one
  `pip install` line, not a fork.
- **Entry-point discovery:** capability packages declare a
  `[project.entry-points."fred.capabilities"]` entry; the registry auto-discovers
  installed capabilities at pod startup, shrinking a team pod to a Dockerfile + config
  (§4).
- **Save-time guardrail:** control-plane validates `selected_capability_ids` against the
  capabilities the instance's bound pod advertises (§3.8) — install-time mixing stays
  safe because an instance can never reference a capability its pod lacks.
- Control-plane stays the proxy/registry/team-policy authority (it aggregates capability
  manifests from pods the way it aggregates templates). **Do not** build a "capability
  pod" and **do not** put capability runtime code in control-plane.
- **Runtime cross-pod capability federation is rejected for now.** Tools already federate
  via the MCP lane. Federating the *full* vertical would mean remote middleware —
  `before_model`/`wrap_model_call` as network calls on every model invocation — a
  distributed-interceptor protocol requiring `RemoteSseAgentInvoker`-class work, with
  hard latency and failure modes. The package model removes the need for the
  private-team story; if a genuine case appears, it is a separate RFC.

### 7.1 Capability tables ship their own migrations (resolved 2026-07-09)

The runtime pod's alembic env deliberately isolates its metadata (it copies only the
session-history table into a fresh `MetaData`); one shared autogenerate across
independently-versioned pip packages cannot produce a coherent history. Instead:

- **Each capability package ships its own migration scripts** (authors run autogenerate
  locally, inside the package) applied through a **per-capability alembic version
  table** (`cap_<id>_alembic_version`) — histories are fully self-contained, never
  rebased against fred-runtime's tree or each other.
- **A runtime CLI** (`python -m fred_runtime migrate`) runs fred-runtime's own tree,
  then discovers installed capability packages via the same `fred.capabilities` entry
  points and applies each package's migrations. The Helm migration job
  (`applications.fred-agents.migration.enabled: true`) overrides `command`/`args` to
  this CLI — *installing the package is the registration, deploying the pod is the
  migration*, one discovery mechanism for both.
- **Hygiene:** capability tables are prefixed `cap_<id>_`; **no cross-capability foreign
  keys** (core-table ids may be referenced as plain columns), so install/uninstall
  ordering stays free.

> **As implemented (2026-07-11, #1979 — `fred_runtime/migrations.py`,
> `fred_runtime/__main__.py`, `capabilities/registry.py`, `capabilities/demo_migrations/`).**
> `AgentCapability.migrations_location()` returns a capability's own Alembic
> script dir (default `None`); the demo capability ships one under
> `cap_demo_echo_alembic_version`. `python -m fred_runtime migrate` upgrades
> fred-runtime's tree, then every discovered capability's tree via
> `CapabilityRegistry.migration_locations()`. Hygiene is a registry boot check
> (`_validate_table_hygiene` → `CapabilityTableHygieneError`): the `cap_<id>_`
> prefix and a **no-foreign-key** rule (stricter than "no cross-capability FK" —
> core ids stay plain columns). The Helm `fred-agents` migration job overrides
> `command`/`args` to `python -m fred_runtime migrate` (values.yaml).

### 7.2 Deployment secrets (resolved 2026-07-09)

`manifest.required_env` lists the env vars a capability needs (e.g. a corporate-drive
service credential). The registry checks them at pod boot and **fails startup**
naming the capability and the variable — a deterministic operator error surfaces at
deploy, not at a user's first turn. Values arrive the classic way (env / dotenv, K8s
Secret in prod — the existing per-app `dotenv:` chart block); capabilities read
`os.environ` directly. Deliberately **no** wrapper accessor: in-process code can
always read the environment, and a restricted accessor would imply an isolation
boundary that does not exist (sandboxing remains the §6 non-goal). Secrets never
enter `capability_config`, `TeamSettingsModel`, or the published manifest (§3.8).
Noted as a future extension (not v1): a **non-gating** per-capability `health_check()`
feeding logs and the §8.5 dashboard — never a boot gate, since a transient
third-party outage must not crash-loop the whole pod.

---

## 8. ReBAC team-scoping and enablement settings (Tier 3)

Today the catalog is pod-global; there is no per-team tool scoping. `TEAM-PLATFORM-POLICY`
already reserves "allowed MCP servers for the team" as future work — Tier 3 realizes it
for capabilities. Once MCP servers are capabilities (Tier 1), that RFC's
`tool_guardrails.allowed_mcp_server_ids` and capability enablement answer the same
question; they must converge (see §12 Q4c).

### 8.1 Schema (resolved 2026-07-09; check subject corrected 2026-07-16)

The `tag`/`document` `parent: [team]` pattern was considered and **rejected**: it models
*ownership* of an object by one team, while a capability is one platform-wide object many
teams are *enabled for*. With `parent: [team]`, default-on capabilities would require one
tuple per (team × capability) plus team-creation and backfill hooks — exactly the
drift-prone fan-out ReBAC is meant to eliminate.

The OpenFGA model (`fred-core/.../rebac/schema.fga`) has no capability type, but is a
standard Zanzibar schema, extended as:

```
type organization
  relations
    ...
    define team: [team]   # reverse index of team.organization — supplied as a
                          # CONTEXTUAL tuple at check time, never persisted

type capability
  relations
    define organization: [organization]      # platform anchor — every capability has one
    define default_on: [organization]  # tuple present ⇔ enabled for all teams (§8.3)
    define enabled: [team]             # explicit per-team grant (admin-gated path)
    define disabled: [team]            # per-team opt-out of a default-on capability

    define can_manage: platform_admin from organization  # amended 2026-07-16 (AUTHZ-05 merge, see below)
    define can_use: (enabled or team from default_on) but not disabled
```

Design notes:

- **The `can_use` subject is the TEAM the agent belongs to, never a user**
  (corrected 2026-07-16 — see the dated amendment below). Enablement is a
  per-team fact; the original user-subject shape
  (`member from enabled …`, queried as `ListObjects(user, can_use, capability)`)
  answered "is this user in ANY enabled team" and therefore leaked a capability
  enabled for one team into every team context its members browsed — visible in
  the create-agent catalog of other teams and savable there. The user's
  membership in the browsed team is already enforced by the route
  (`get_team_by_id`); `can_use` only has to answer "may agents of team T use C".
- `organization` on the capability is pure anchoring (admin management rights). It
  does not double as the default-on marker — `default_on` is its own relation so it
  is **runtime state**, toggleable by writing/deleting one tuple, not a code
  property (§8.3).
- The `default_on` path resolves through the organization's `team` reverse edge
  (FGA cannot traverse `team.organization` backwards). The edge is **derived, not
  stored**: every team belongs to the singleton organization, so callers inject
  `organization:fred#team@team:{id}` as a contextual tuple on every team-subject
  check — no per-team tuple writes, no backfill, and personal teams are covered
  for free.
- **Callers check `can_use`, never the structural relations.** UI listing =
  `ListObjects(team:{ctx}, can_use, capability)`; enforcement at agent save and
  session prep = `Check(team:{ctx}, can_use, capability:{id})` — both with the
  contextual reverse edge. Structural tuples are written only by the enablement
  API (§8.5).
- The `but not` exclusion is the one non-trivial construct; it exists solely to give
  the admin dashboard a tri-state (inherited-on / enabled / disabled). If the team
  prefers to avoid exclusion in v1, drop `disabled`: removing a default-on capability
  from one team then requires flipping the capability to admin-gated. (With a team
  subject the exclusion is over direct relations — none of OpenFGA's documented
  userset-subject + exclusion caveats apply.)

Flows through the existing `sync_schema_on_init` bootstrap.

### 8.2 Team-level capability settings — enablement is not a boolean

Motivating case: a capability exposing a corporate internal drive that does not speak
OIDC. The platform holds one service credential; each team must be pinned to its own
root folder. Enabling for team A means "enabled, rooted at folder 123"; for team B,
"enabled, rooted at folder 456".

ReBAC tuples cannot carry payloads — and should not: authorization and configuration
are different data with different lifecycles. Split:

- **Authorization** (may team T use capability C?) → the FGA tuples of §8.1.
- **Configuration** (with what settings?) → a control-plane table
  `team_capability_settings(team_id, capability_id, settings JSONB, updated_by, updated_at)`,
  validated against a third typed model on the capability class:

```python
class AgentCapability(...):
    TeamSettingsModel: ClassVar[type[BaseModel]]  # per-team enablement settings; EmptyModel if none
```

- Declared and OpenAPI-exported like `ConfigModel`/`TurnOptionsModel`, so the admin
  enablement form (§8.5) renders through the existing metadata-driven mechanism
  (`ManagedAgentFieldSpec` → `TuningFieldRenderer`) — zero bespoke UI for scalar
  settings.
- At session prep, control-plane resolves the team's settings row and ships it to the
  pod; `CapabilityContext` carries it as `team_settings` (§3.5). Tools never see it in
  their signature — same runtime/LLM split as `config`.
- **Constraint (validated at registration):** a capability whose `TeamSettingsModel` has
  required fields cannot be `default_on` — nobody has filled the settings. Anything
  with per-team settings or external reach is therefore admin-gated by construction.
- This completes a four-layer typed narrowing:
  **platform** (manifest + deployment secrets) → **team** (`TeamSettingsModel`,
  admin-set) → **agent instance** (`ConfigModel`, creator-set) → **turn**
  (`TurnOptionsModel`, chatting user).

Two boundaries, stated so they are not re-litigated:

- **v1: `chat_controls(config)` does not take team settings**, keeping the §3.7 cache
  key `(capability_id, manifest.version, config_hash)` valid. If a control ever needs
  them, the signature gains a parameter and the cache key a settings hash — a trivial
  in-tree change.
- **Write ordering:** enable = write settings row, then tuple (tuple last — a
  half-failure leaves the capability disabled, never enabled-without-settings);
  disable = delete tuple, keep the row (re-enable restores prior settings).

### 8.3 Default-on: keep the mechanism, constrain the use

Do we want default-on at all? Arguments:

- **For:** baseline capabilities (e.g. document-access) should work without a per-team
  admin ceremony; a deployment with 50 teams should not need 50 grants for table
  stakes.
- **Against:** a new capability silently reaching every team is a security footgun —
  especially one touching external systems — and explicit grants give admins an audit
  moment.

Recommendation:

1. `manifest.team_scope` is only the **seed**: at first registration a `default_on`
   capability gets its `default_on` tuple written. After that the tuple is runtime state
   owned by admins, toggleable from the dashboard (§8.5).
2. The §8.2 constraint already fences the risk: required team settings or external
   reach ⇒ admin-gated by construction. `default_on` is for self-contained,
   no-settings capabilities.
3. A deployment flag (`capabilities.default_policy: seed | explicit`) lets
   security-sensitive on-prem operators ignore manifest seeds and start everything
   admin-gated.

> **Platform policy ratified (2026-07-17, CVSSI review).** This deployment
> takes the "against" branch above for every capability, both kinds: no
> manifest ever sets `team_scope: DEFAULT_ON`; every team's access to every
> tool and every agent is an explicit, auditable admin grant
> (`capabilities.default_policy` need not even be set to `explicit` — nothing
> declares `DEFAULT_ON` in the first place, so `seed_registration_defaults`
> has nothing to act on). The mechanism above is kept, not removed — a
> genuinely benign future capability may still use it after a documented
> security review, which is exactly what the guard tests below enforce
> instead of a comment someone could miss: `kind="tool"` static manifests are
> scanned for an un-allowlisted `DEFAULT_ON`
> (`apps/fred-agents/tests/test_capability_team_scope_policy.py`); `kind="agent"`
> projections have no such field to scan (`AgentDefinition` declares no
> `team_scope`), so that guard is a narrow unit test asserting the projection
> function hardcodes `ADMIN_GATED`
> (`control-plane-backend/tests/test_capability_selection_1974.py::test_agent_projection_always_hardcodes_admin_gated`).
>
> **Known, accepted trade-off**: no team-creation-time capability seeding
> hook exists (only `seed_registration_defaults`, at first capability
> registration, and `seed_personal_team_capabilities`, at personal-space
> first-touch — neither fires when a regular team is created). A brand-new
> collaborative team gets zero working agents/tools until an admin grants
> some. Extending the `capabilities.personal_defaults` pattern to regular
> team creation would close this gap without reintroducing `DEFAULT_ON`
> (grants only new teams, stays revocable, doesn't retroactively open
> existing teams) — tracked as a separate, non-blocking follow-up, not solved
> here.

### 8.4 Personal spaces

> **Amended 2026-07-16 (updated in place).** The original v1 answer here — a
> `platform.capabilities.personal_defaults` deployment-config list seeded into each
> personal space at first bootstrap — shipped in #1980 and is **withdrawn**.
> First-touch seeding proved operationally wrong in live testing: changing the list
> required a redeploy, removing an id revoked nothing (the promised backfill command
> was never built), and the net effect was silent rights drift between users
> depending on when they first logged in. The seeding path
> (`seed_personal_team_capabilities`, the frontend-bootstrap hook, the
> `personal_defaults` config field) is removed. The replacement below is pure FGA
> runtime state, admin-toggleable like `default_on`. (`default_policy` and the §8.3
> registration seeding are untouched.)

Personal spaces are real teams (`personal-{uid}`, TEAM-PLATFORM-POLICY §12.3), so
`enabled: [team]` already covers enabling a capability for one personal space.

"Enable for **all** personal spaces but not regular teams" was originally rejected as
having no clean FGA expression — the schema does not discriminate team types. The
2026-07-16 `can_use` team-subject fix (§8.1) dissolved that objection: every
team-subject check now flows through one helper that injects derived organization
reverse edges as **contextual tuples**, and that caller knows the team type
(`is_personal_team_id`). The class "all personal teams" is therefore expressible at
check time without persisting a single per-team tuple:

```
type organization
  define team: [team]            # existing — contextual, never persisted
  define personal_team: [team]   # NEW — contextual, injected only for personal-{uid} subjects

type capability
  define personal_on: [organization]        # class grant — one platform-wide tuple
  define personal_disabled: [organization]  # class opt-out — one platform-wide tuple
  define personal_grant: personal_team from personal_on
  define personal_block: personal_team from personal_disabled
  define inherited: (team from default_on or personal_grant) but not personal_block
  define can_use: (enabled or inherited) but not disabled
```

- **Precedence — most specific wins**, one uniform rule across the whole matrix: a
  team's explicit `enabled`/`disabled` beats the personal-class position, which beats
  `default_on`. The intermediate `inherited` relation exists exactly so the class
  opt-out subtracts only from the inherited layer, never from a per-space explicit
  grant.
- **The class is a tri-state**, mirroring a normal team row: *Enabled* =
  `personal_on` tuple present; *Disabled* = `personal_disabled` tuple present;
  *Default* = neither, personal spaces follow `default_on` like any team. Toggling
  writes/deletes one tuple and applies instantly to ALL personal spaces — past,
  future, and users who never log in. No seeding, no backfill, no per-user fan-out.
- **§8.2 constraint carries over:** a capability whose `TeamSettingsModel` has
  required fields cannot be class-enabled (nobody filled the settings) — same rule
  and error as `default_on`. A class transition that loses access for personal
  spaces (enabled→disabled, enabled→default without `default_on`, or
  default→disabled with `default_on`) suspends dependent personal-space instances
  through the same #1975 sweep as `set_capability_default_on(False)`.
- **Admin surface (§8.5):** the team matrix gains one synthetic **pinned first row
  "All personal spaces"** driven by the class state, rendered with the same
  tri-state control as team rows. The admin's own personal team no longer appears as
  an ordinary row — live testing (2026-07-16) showed it reads as a global
  personal-space control, which it is not. API:
  `PUT /admin/capabilities/{id}/personal-scope` with body
  `{scope: "enabled" | "disabled" | "default"}` (idempotent setter beside
  `/default-on`; response carries the suspended-instance count); the admin list
  response gains `personal_scope`.
- Resolving per-type defaults dynamically control-plane side (mirroring
  TEAM-PLATFORM-POLICY §12.2) remains rejected **for authorization**: it would split
  `can_use` across FGA and a config merge, so a bare FGA check would no longer be
  authoritative.

### 8.5 Admin dashboard

Tier 3 is not shippable without a management surface — tuples writable only via
scripts is not a product. The control-plane admin area gains a **Capabilities** page:

- catalog list from aggregated manifests: name, version, scope badge
  (default-on / admin-gated), enabled-team count;
- per-capability team matrix with tri-state (inherited via default-on / explicitly
  enabled / disabled), and the enablement form rendered from `TeamSettingsModel`
  (§8.2);
- the default-on toggle (writes/deletes the `default_on` tuple) and the
  personal-spaces class tri-state (§8.4, amended 2026-07-16 — formerly a
  config-only default list);
- a per-capability **health column**: suspended-instance counts from the §3.9
  reconciliation (and, later, `health_check()` probe results, §7.2).

API sketch (control-plane, gated on `capability#can_manage`): `GET /admin/capabilities`,
`PUT`/`DELETE /admin/capabilities/{id}/teams/{team_id}` (enable-with-settings /
disable), `PUT /admin/capabilities/{id}/default-on`. Exact routes are fixed in a
`CONTROL-PLANE-PRODUCT-CONTRACT` amendment when Tier 3 is picked up.

> **As implemented (2026-07-11, #1980).** The backend of §8.1–§8.5 landed (the
> admin dashboard UI remains its own issue).
>
> - **Schema (§8.1).** `type capability` added to `fred-core/.../rebac/schema.fga`
>   with `organization` (anchor) / `default_on` / `enabled` / `disabled` and the
>   computed `can_use` (the tri-state `difference`) + `can_manage`. Regenerated
>   `schema.fga.json` via `make transform-openfga-schema`; flows through
>   `sync_schema_on_init`. **Deviation:** `can_manage` is `admin from organization`
>   (the anchor relation is named `organization`, not `parent` as the §8.1 snippet
>   wrote) — **superseded 2026-07-16** (merge with swift): AUTHZ-05 retired the
>   legacy `admin`/`editor`/`viewer` organization-role bridge before this branch
>   merged, so `can_manage` is now `platform_admin from organization`; no other
>   part of this deviation note changes. New `Resource.CAPABILITY`, `RelationType.{DEFAULT_ON,ENABLED,DISABLED}`,
>   and `CapabilityPermission.{CAN_USE,CAN_MANAGE}`. Tri-state proven in fred-core's
>   OpenFGA integration suite (offline structural test covers the generated schema).
> - **Enforcement (§8.1).** Catalog listing filters each template's
>   `available_capabilities` via `ListObjects(user, can_use, capability)`
>   (`list_agent_templates(..., user=)`); agent save `Check`s `can_use` per selected
>   non-MCP capability in `_apply_capability_selection` (403 on denial). MCP
>   (`mcp:<id>`) capabilities are out of the FGA type's scope and never filtered.
>   **This carve-out is the root cause of the #1988 startup crash and is
>   reversed there: MCP capabilities are now first-class in the FGA type and
>   `can_use`-filtered like any other** (§3.8 note above).
> - **Settings (§8.2).** `team_capability_settings(team_id, capability_id, settings,
>   updated_by, updated_at)` table + `TeamCapabilitySettingsStore`. The typed
>   `TeamSettingsModel` is advertised on the wire as `manifest.team_settings_fields`
>   (mirror of `config_fields`) so control-plane validates the enable-with-settings
>   form against the field specs; the pod still re-validates against
>   `TeamSettingsModel` at assembly. Write ordering enforced in
>   `enable_capability_for_team` (settings row → tuple). Resolved settings ride
>   `ManagedAgentRuntimeBinding.team_capability_settings` (restricted to selected
>   caps) → `_ResolvedExecutionTarget.team_settings` → `build_capability_contexts` →
>   `CapabilityContext.team_settings`; never in an LLM tool signature.
> - **Revocation → suspension (#1975 seam).** `disable_capability_for_team` deletes
>   the `enabled` tuple (keeps the settings row; writes a `disabled` opt-out for a
>   default-on cap) then calls `reconcile_instance_suspension(...,
>   revoked_reason=CAPABILITY_ACCESS_REVOKED)` for each dependent instance
>   (available set = `selected − {revoked}`). `set_capability_default_on(False)`
>   revokes inherited access team-by-team the same way.
> - **Defaults (§8.3–§8.4).** `seed_registration_defaults` seeds the `default_on`
>   tuple at first registration only (detected by the absence of the org anchor),
>   gated by `platform.capabilities.default_policy: seed | explicit` and skipped for
>   caps with required team settings. Personal-space seeding
>   (`seed_personal_team_capabilities`, from `platform.capabilities.personal_defaults`)
>   is wired at frontend-bootstrap first-touch (idempotent via the settings-row
>   marker). **Deviation:** config lives under `platform.capabilities.*` rather than
>   a top-level `capability_defaults` block. *(Personal-space seeding withdrawn by
>   the 2026-07-16 §8.4 amendment — replaced by the `personal_on`/`personal_disabled`
>   class relations; registration seeding and `default_policy` remain.)*
> - **API (§8.5).** Routes live under `control_plane_backend/capabilities/api.py`,
>   each mutation gated on `capability#can_manage` (anchor-ensured first); the
>   aggregate list gated on the equivalent org-admin relation. Generated
>   control-plane client regenerated.

> **Fixed (2026-07-17, PR review finding — closes an unmet #1980 acceptance
> criterion: "Check at agent save AND session prep").** `selected_capability_ids
> = None` (the default "no explicit selection" save — the common path, since
> General Assistant and Sentinel both declare non-empty `default_mcp_servers`,
> all `admin_gated`, none `default_on`-seeded) skipped `can_use` **entirely**:
> `_apply_capability_selection`'s whole ReBAC block was nested inside `if
> selected_ids is not None:`. The runtime pod then activated every template
> default MCP server with zero authorization check — the exact "session prep"
> enforcement #1980 promised and never shipped. A team could obtain an
> admin-gated capability for free by submitting no selection at all.
>
> **Corrected semantics** — `None` is no longer a live-inheriting sentinel; it
> is resolved **once, at save time**, into an explicit, ReBAC-filtered list:
> `effective_ids = template_default_capability_ids ∩ usable_capability_ids(team)`,
> filtered silently (no 403 — an implicit default degrades gracefully to
> "whatever this team already has" rather than blocking every fresh team's
> first save) and **always persisted as an explicit list**, never left `None`.
> This is what lets the existing revocation sweeps (`suspend_dependent_instances`,
> `set_capability_default_on`) — which scan `selected_capability_ids` and
> previously skipped `None` rows silently — correctly track these instances
> going forward. Explicit selections are unchanged (still 403 on denial).
>
> Threaded the runtime's per-template `available_mcp_servers` (already on the
> `/agents/templates` wire, previously parsed and dropped by
> `_RuntimeTemplatePayload.model_validate`) into control-plane as
> `default_capability_ids`, so `_apply_capability_selection` knows what a
> template's `None` case resolves to. A one-off backfill
> (`materialize_default_capability_selections`) re-resolves any
> already-persisted `None` row — required at/before deploy, not a follow-up;
> "0 remaining NULL `selected_capability_ids` rows" is the closure proof, not
> "the sweep ran once." **Operational consequence, not a code bug**: any team
> without an explicit grant for a template's default capabilities will now see
> that agent run with fewer/zero MCP tools until an admin grants them — correct
> enforcement of the ReBAC model this RFC already specified, but a visible
> behavior change at rollout. Whether to seed any of these `default_on` is a
> deployment decision, not made here.

> **Extended (2026-07-17, CAPAB-01 — agent templates join this same
> capability model).** `CapabilityManifest`/`CapabilityCatalogEntry` gained
> `kind: Literal["tool", "agent"] = "tool"`. Every mechanism on this page
> (schema, `can_use`, enablement API, seeding, admin dashboard) now governs
> BOTH kinds uniformly — no new FGA type, no parallel system. Agent templates
> are projected control-plane side into `kind="agent"` catalog entries
> (`product/service.py` `_agent_capabilities_for_source`), gated on
> `list_agent_templates`/`enroll_agent_instance`, with their own required
> compatibility migration (`grant_existing_teams_served_templates`). Full
> design and rationale — including why the runtime pod's own capability
> registry is deliberately NOT the projection target — lives in
> `AGENT-VISIBILITY-RFC.md` §7.5, since it answers that RFC's §7.1 bullet 5
> ("compatible with the caller's team capability"), not a new concern of this
> one. Platform policy ratified the same day: this deployment never uses
> `team_scope: DEFAULT_ON` (§8.3 below), for either kind — enforced by a
> scan-based guard test for `kind="tool"` static manifests
> (`apps/fred-agents/tests/test_capability_team_scope_policy.py`) and a
> narrow unit test on the projection function for `kind="agent"` (which has
> no `team_scope`-equivalent field to scan at all).

> **As implemented (2026-07-11, #1981 — admin dashboard UI).** The management
> surface deferred by #1980. A control-plane admin **Capabilities** page at
> `/admin/capabilities` (`apps/frontend/src/rework/components/pages/admin/CapabilitiesPage/`),
> reached from the admin sidebar and gated by the admin-role route guard (the
> client-side equivalent of the backend's org-admin `can_manage` list gate).
>
> - **Catalog table.** One row per aggregated capability: icon + i18n name +
>   version, the **enabled-team count** (`enabled_team_ids.length`), an inline
>   **default-on toggle**, a **health** cell, and a "manage teams" action. Renders
>   through the shared `DataTable`; loading / error / empty states use the
>   existing page primitives. A **scope badge** column (the manifest
>   `team_scope`) shipped initially but was dropped (2026-07-16, live-testing
>   feedback): the manifest value is only the registration seed, and showing it
>   next to the authoritative default-on toggle read as two conflicting
>   defaults. Admins manage the live state; the seed stays visible in the
>   manifest itself.
> - **Team matrix** (`CapabilityTeamMatrixDrawer`, an `InlineDrawer`). One row per
>   team with the tri-state badge (`enabled` / `on-by-default` / `off`) and the
>   enable / disable actions. **Enable-with-settings** renders the capability's
>   `team_settings_fields` through the shared metadata-driven `TuningFieldRenderer`
>   — zero bespoke UI for scalar settings — then `PUT`s `{settings}`; disable
>   `DELETE`s and toasts the returned suspended-instance delta.
> - **Default-on toggle.** `PUT …/default-on`; turning it **off** is confirmed
>   first (it revokes inherited access team-by-team and can suspend instances).
> - **Data path.** Consumes only the generated hooks via the friendly aliases in
>   `controlPlaneApiEnhancements.ts` (`useAdminCapabilitiesQuery`,
>   `useEnableTeamCapabilityMutation`, `useDisableTeamCapabilityMutation`,
>   `useSetCapabilityDefaultOnMutation`); a `ControlPlaneCapability` cache tag makes
>   every mutation re-read the catalog. No hand-written fetch or response type.
>   Contract fixed in `CONTROL-PLANE-PRODUCT-CONTRACT.md §14`.
> - **Deferred (backend seams, not built here).** The **health column** shows only
>   the mutation-reported suspended **delta** (session-scoped), not a resting
>   per-capability count — the suspension row records a typed reason, not the
>   causing capability id (needs the #1975 sweep to attribute + expose a count).
>   The **explicit `disabled` opt-out** of a default-on capability is not
>   distinguishable from inheritance in the matrix (the list response carries
>   `enabled_team_ids` + `default_on` but no `disabled_team_ids`). The
>   **personal-spaces default list** (§8.4) stays config-only
>   (`platform.capabilities.personal_defaults`, changing it needs a backfill) — no
>   read/write API exists to make it editable, so that half of the criterion is
>   deferred rather than faked. *(Resolved by the 2026-07-16 §8.4 amendment: the
>   config list is withdrawn in favor of the `personal_scope` class tri-state and
>   its "All personal spaces" matrix row.)* All three are additive backend
>   extensions; the dashboard consumes them the moment the fields land.

> **As implemented (2026-07-16 — `can_use` team-subject fix).** Live testing of
> #1980/#1988 surfaced a cross-team leak: a capability enabled for team A
> appeared in (and was savable from) EVERY team its members browsed, because
> `can_use` was checked with the USER as subject — a user-level FGA fact that
> ignores the browsed team context. Fixed by re-shaping `can_use` to a
> team-subject permission (§8.1 above, updated in place):
>
> - **Schema.** `capability#can_use` is now
>   `(enabled or team from default_on) but not disabled`; `organization` gained
>   the `team: [team]` reverse edge, injected as a **contextual tuple**
>   (`organization:fred#team@team:{id}`) on every team-subject check — never
>   persisted, so no backfill and personal teams are covered. New
>   `RelationType.TEAM` in fred-core. `schema.fga.json` regenerated via
>   `make transform-openfga-schema`; rolls out through `sync_schema_on_init`.
> - **Enforcement.** `capabilities/authz.py` helpers now take the team id:
>   catalog filtering = `lookup_resources(team:{ctx}, can_use, capability)`
>   (`list_agent_templates` no longer takes `user`), agent save =
>   `has_permission(team:{ctx}, can_use, capability:{id})` in
>   `_apply_capability_selection` (403 unchanged). The write path
>   (`enablement.py`) was already team-scoped and is untouched; the browsing
>   user's membership stays enforced by the route (`get_team_by_id`).
> - **Semantic shift.** A default-on capability is now "usable by every TEAM"
>   rather than "usable by every org viewer" — save and session prep always
>   run in a team context, so this is strictly more precise. Nested teams do
>   not inherit `enabled` grants (explicit-grant philosophy).
> - **Tests.** fred-core integration suite re-pins the tri-state with team
>   subjects, the cross-team leak regression, and the
>   contextual-edge-required behavior; the offline schema-shape test asserts
>   the new `difference` tree; control-plane fakes assert the team-subject +
>   contextual-edge check shape and a `team-a`-enabled / `team-b`-denied case.

### 8.6 Agent templates as capabilities (CAPAB-01, 2026-07-17)

`AGENT-VISIBILITY-RFC.md` needed the same "team-gated, admin-managed"
treatment for agent template VISIBILITY that this section already built for
tool ACTIVATION. Rather than a parallel FGA type + admin surface (rejected —
see `AGENT-VISIBILITY-RFC.md` §7.5 for why), an agent template is a
capability of `kind="agent"` in this exact same object space:

- `kind: Literal["tool", "agent"] = "tool"` on `CapabilityManifest`/
  `CapabilityCatalogEntry` — the only new field; every relation, API route,
  and seeding path above governs both kinds unchanged.
- Agent templates are never authored as `CapabilityManifest` — they stay
  `AgentDefinition` at the SDK level (same non-unification precedent as MCP
  servers, §3.8). Control-plane projects each registered template into a
  `kind="agent"` `CapabilityCatalogEntry` purely for catalog/authz purposes
  (`product/service.py` `_agent_capabilities_for_source`), deliberately NOT
  by injecting them into the runtime pod's own capability registry (that
  registry backs every template's `available_capabilities` tool picker,
  shared identically across templates — see `AGENT-VISIBILITY-RFC.md` §7.5
  for the concrete leak this avoids).
- `id`: `template_capability_id(runtime_id, agent_id) ->
  f"{runtime_id}__{agent_id}"` — colon-free (§3.8's `mcp:<id>` crash class,
  applied to templates: `template_id`, used for routing, contains `:`).
- `team_scope` is hardcoded `ADMIN_GATED` in the projection function, no
  parameter to override — consistent with the §8.3 platform policy (never
  `DEFAULT_ON`) and enforced by its own guard test (a template author cannot
  even express `DEFAULT_ON`; `AgentDefinition` has no such field).
- Enforcement reuses `list_agent_templates`/`enroll_agent_instance`'s
  existing ReBAC call sites (`AGENT-VISIBILITY-RFC.md` §7.1/§7.2) rather than
  adding new ones.
- Compatibility migration (`grant_existing_teams_served_templates`) is
  required, not optional, and companions Part 1's
  `materialize_default_capability_selections` — see that RFC section for the
  deploy-sequencing note.
- Not built in this pass: `depends_on` (a capability declaring which others
  it needs) and the admin-facing "refuse and tell me what's missing" UX when
  enabling an agent without its tool dependencies granted. Tracked as a
  fast-follow, not silently dropped.

---

## 9. Frontend (mix of generated + custom widgets — confirmed direction)

**Agent-creation config fields:** simple fields render through the existing
metadata-driven form (zero code); complex fields declare `ui.widget` and resolve against
a **form-widget registry** extending `TuningFieldRenderer`'s type-switch. **Chat-time
controls never render through the form** — they mount into the composer slot (item 2),
a different surface with a different idiom. Each capability ships one folder
`rework/features/capabilities/<id>/` exporting a single plugin, registered in one index —
the only shared edit:

```ts
export const documentAccessCapability: CapabilityUiPlugin = {
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
2. **Composer control slot** — the same contribution model as item 3's side-panel slot,
   fed by the `chat_controls()` descriptors arriving on `ExecutionPreparation` (§3.7).
   The host owns the shared `MenuPopover` shell and cross-capability grouping/ordering;
   each `widget` id resolves against the plugin's `chatTurnControls`; unknown ids are
   silently skipped. Ships with a small stock kit extracted from `SearchConfig` (enum
   row, toggle row, action row) so trivially simple controls need no new component.
   This **supersedes** the `AgentOptionDescriptor` generic-rendering contract
   (CHAT-UI §3.4, task in §3.9) — that spec is the form-generation idea this RFC
   rejects (§11); CHAT-UI must be amended to point here.
3. **Side-panel contribution slot** — generalizing `InlineDrawer layout="push"` +
   `TraceDrawerProvider` into a reserved right-column slot capabilities mount into.
4. **Two widget registries** — form widgets (agent creation: `value/onChange/error`
   contract) and composer controls (chat: `value/onChange` plus popover-open state and
   `onRequestClose`). The contracts differ; separate registries prevent a form field
   from being mounted in the composer by accident.

Custom chat parts stay **strongly typed** end-to-end: capability `chat_parts` extend the
frozen `UiPart` union (§3.6) via registration + OpenAPI regen; the part-renderer registry
is typed against the regenerated union. No generic envelope.

### 9.1 Capability routes: reachability and typed clients (resolved 2026-07-09)

**No control-plane proxy.** Capability routes follow the platform idiom already used for
execution: control-plane hands the browser **ingress-relative pod URLs** and the
frontend calls the pod directly (the `ExecutionPreparation` / `createDynamicBaseQuery`
pattern — the prepare endpoint explicitly does not proxy runtime SSE, and capability
routes get the same treatment). The capability catalog response carries each capability's
base URL for the **template-bound** pod (pre-save case, e.g. the PPT analyze
endpoint), and `ExecutionPreparation` carries it for the **instance-bound** pod
(in-session case, e.g. the WritableDocument panel's CRUD). Auth = the same bearer the
pod already validates for `/agents/*`.

**End-to-end typing, per capability.** The existing per-backend codegen trio (config
json → generated `<name>OpenApi.ts` → base slice with a dynamic base query) is
applied per capability: an SDK utility dumps a capability `router`'s own OpenAPI document
(throwaway `FastAPI()` wrap — only that capability's routes and schemas, no neighbors);
the frontend folder `rework/features/capabilities/<id>/api/` holds the codegen config
and the generated RTK Query slice, whose dynamic base query resolves
`capabilityBaseUrl(capabilityId)` from the catalog/preparation state. Generated hooks are
imported **only** by that capability's plugin components (folder convention, lintable
with an import-boundary rule). The repo rule extends verbatim: *touched a capability
router → regenerate that capability's slice in the same change.* This mechanism is
in-tree-only — which is exactly the v1 UI boundary below: external packages ship no
custom components, and custom components are the only consumers of capability routes.

> **As implemented (2026-07-11, #1979).** Routes: `create_agent_app` auto-mounts
> each `manifest.router` under `{pod_base_url}/capabilities/{id}` with the same
> bearer dependency as `/agents/*` (`_mount_capability_routers`, no proxy). The
> template catalog carries `CapabilityCatalogEntry.route_base_url` (template-bound)
> and control-plane `ExecutionPreparation.capability_base_urls` carries the same
> ingress-relative URLs for the selected capabilities (instance-bound). Typed
> client: `python -m fred_runtime dump-openapi <id>` wraps only that capability's
> router in a throwaway `FastAPI()`; `features/capabilities/<id>/api/` holds the
> codegen config + generated slice, whose base query resolves the URL from
> `capabilityRoutingSlice` (populated on prepare-execution). Side panels: a typed
> `sidePanels` plugin slot + `sidePanelRegistry` (mirror of the part-renderer
> registry); `CapabilitySidePanelHost` mounts a session's active-capability panels
> in a push `InlineDrawer`, keyed off `selected_capability_ids`. The `demo_echo`
> capability exercises all three end-to-end (`/analyze` route, generated
> `useAnalyzeAnalyzePostMutation`, `DemoNotesPanel`).

**External capabilities and the UI boundary (v1).** The plugin registries above are
build-time, in-tree code — so an externally-authored capability package (§7, lane 2)
cannot ship custom widgets, parts, or panels in v1. It is bound to the **generated
surface**: scalar `config_fields` through the metadata-driven form, the stock composer
kit (item 2 above), and the existing `UiPart` types (e.g. `LinkPart`). That honestly
covers most integrations. Custom UI for external capabilities is deliberate future work,
noted so the door stays open: the natural mechanism is the same assembly model as the
backend — **frontend widget plugins as npm packages**, registered in the one plugin
index at frontend-image build time — with a **sandboxed iframe renderer** as the
further step for untrusted authors (§6 non-goal). Both belong to a future RFC.

---

## 10. Worked mapping of the three port targets

| Feature | Exercises | Tier that unblocks it |
| --- | --- | --- |
| **#1906 document-access** (tree + summarize + rename) | multiple tools from one capability; static config-field scoping + a computed chat-turn narrowing control (§3.3); no new part/panel | Tier 0 (native middleware, after the Tier 2 migration) → **pilot**; polished by Tier 1 |
| **#1903 PPT filler** | `validate_config` + asset upload; dynamic tools; custom widget; custom part; side panel; analyze route on `router` | Tier 0/1 for the vertical; Tier 2 for native dynamic-tool middleware |
| **#1905 WritableDocument** | `tables` + `router` (CRUD/export); `before_model` state edit (edit detection → system note); custom part; editor side panel | Tier 0/1 vertical; **Tier 2 makes the state-edit a clean middleware hook** |

**#1906 is the pilot** — smallest surface, validates the abstraction (and the frontend
registries) before #1903/#1905 build on it.

### 10.1 As-implemented (CAPAB-01 #1906, July 2026)

Shipped `DocumentAccessCapability`
(`fred_runtime/capabilities/document_access/`) with ONLY the vector-search tool
(`search_documents_using_vectorization`) wired live, registered via the
`fred.capabilities` entry point (`document_access`; auto-discovered at app
construction). It exercises: multiple-tools-from-one-capability (validated via
assembly tests, not shipped mock tools), static `config_fields` scoping, and one
computed `document_scope` chat-turn narrowing control (§3.3).

**Platform-service doctrine (Tier-0 `RuntimeServices` extension).** Capabilities
reach platform services ONLY through typed optional ports on `RuntimeServices`;
**the per-turn binding and the raw access token never enter
`CapabilityContext`.** The new `DocumentSearchPort` (`fred-sdk`,
RUNTIME-EXECUTION-CONTRACT §8.15) takes scope PARAMETERS only; the runtime
`DocumentSearchAdapter` captures the binding + token privately and exposes only
`search(...)`. Rejected alternatives: (a) passing the binding into
`CapabilityContext` (token-leak / security regression); (b)
`services.tool_invoker` with `tool_ref="knowledge.search"` (cannot express
per-capability config scoping — reads scope from `runtime_context`, not the
payload).

**Scoping precedence — `turn_option ⊆ capability_config ⊆ session_binding`,
enforced across two seams.** The capability narrows its stored-config scope by
the per-turn `document_scope` selection (`turn_option ⊆ capability_config`); the
adapter then intersects the result with the session binding's own scope
(`⊆ session_binding`). Both seams use one intersection primitive; covered by an
end-to-end test through the real adapter.

**Duplicate-search-tool story (pilot decision).** The builtin `knowledge.search`
(`TOOL_REF_KNOWLEDGE_SEARCH`) and the inprocess `mcp-knowledge-flow-mcp-text`
catalog server (capability id, no `mcp:` prefix since #1988) both still expose a
vector-search tool that reads scope from
`RuntimeContext` only. An instance that BOTH wires one of those AND selects this
capability would get two vector-search tools with different scoping. For the
pilot, `DocumentAccessCapability` is the forward path (it adds per-capability
config + turn scoping the builtin cannot express); the builtin/catalog path
stays reachable for back-compat and its retirement is a follow-up. Documented in
the capability docstring; do NOT wire both on one instance.

**Deferred: `list_document_tree` + `summarize_document`.** NOT registered
(a registered tool the LLM can call but that returns "not implemented" erodes
trust). They are blocked pending Knowledge Flow backend endpoints
(`POST /documents/tree`; a synchronous `POST /documents/{uid}/summarize`) and
pod-reachable session-attachment enumeration, none of which exist on Swift yet.
Follow-up will add them once KF ships those endpoints.

**Rename.** `mcp.servers.search_documents.name` → "Document access" (EN) /
"Accès aux documents" (FR); verified it shadows no other `mcp_catalog.yaml`
entry's display name.

---

## 11. Alternatives considered

- **A parallel Fred hook system (my first sketch: `before_turn`/`build_tools` on the
  capability).** Rejected: it duplicates LangChain's middleware API, forgoes the prebuilt
  suite, and can't be published as LangChain-compatible. Adopting `AgentMiddleware`
  directly is strictly better.
- **Keep MCP as a separate tool family beside capabilities.** Rejected: it keeps two
  product contracts, two Tools-tab code paths, and two registries. `McpCapability`
  parameterized by a server config unifies them.
- **A generic `CapabilityPart{capability_id, kind, payload}` envelope** instead of extending
  the typed `UiPart` union. Rejected: loses end-to-end generated types; the union
  extension via OpenAPI regen keeps strong typing.
- **Wrapper, not rewrite** (keep the hand-rolled graph; adapt middleware-shaped hooks
  internally). Viable as a fallback if Tier 2 is deferred, but forgoes the prebuilt
  middleware and keeps ReAct/Deep divergent. Documented as the "stop at Tier 1" state.
- **One unified `fields` list for agent-creation and chat-time, with a declarative
  `visible_when` condition** (an earlier draft of §3.3). Rejected on both halves:
  (a) the chat surface is a *projection* of creator config — a condition mini-language
  would grow comparisons, combinators, then identity references; the `chat_controls()`
  function is simpler and strictly more powerful. (b) Rendering chat-time fields
  through the same generated form as agent creation mistakes the composer for a form:
  it is a different idiom (popover rows, nested pickers, viewport clamping) with a
  different lifecycle (live per-session state, no save/validate moment), and some
  controls are *actions* or stateful dialogs, not values — the "generated for scalars"
  promise would have covered approximately zero real controls.
- **A discriminated union for turn options** (mirroring chat parts). Not needed: parts
  require union dispatch by a renderer that does not know the kind in advance; turn
  options are read only by their owning capability, so the capability-id-keyed map with
  OpenAPI-typed leaves (§3.5) keeps end-to-end typing without union maintenance.

---

## 12. Open questions for the team — all resolved 2026-07-09

1. **Tier depth — resolved.** All tiers approved. Implementation starts with the
   Tier 2 `create_agent` migration, then Tiers 0/1, Tier 3 shortly after; tickets may
   cross tier boundaries (§6). The Tier-0/1 inprocess adapter is dropped.
2. **HITL migration — resolved.** Custom `FredHitlMiddleware` keeping the
   `HumanInputRequest` payload verbatim; capability-owned `HitlSpec` with a `when`
   predicate; fail-closed. Full shape in §5.4.
3. **State persistence — resolved as a gating spike** (first task inside the Tier 2
   migration, §5.2): a toy middleware with one `state_schema` field + reducer against
   `FredSqlCheckpointer`, through write → executor rebuild → read → `interrupt()` →
   resume, in JSON-primitive and Pydantic flavors. Known risk: the checkpointer's
   `JsonPlusSerializer` msgpack allowlist is closed (one legacy entry) — expected
   outcome is the rule "capability state is JSON-primitive, or registration extends the
   allowlist". `HistoryStorePort` is dead: state is edited only from inside the graph
   (§5.1); document content lives in capability tables, not graph state.
4. **`capability` ReBAC relations — resolved.** Schema and rationale in §8.1.
   (a) the `but not disabled` tri-state exclusion is **kept** (admin-dashboard
   tri-state; one line of FGA);
   (b) per-team-type default-on is the §8.4 personal-class relations (amended
   2026-07-16; the original no-schema-change seeding approach shipped in #1980 and
   was withdrawn);
   (c) `TeamPlatformPolicy` / `tool_guardrails.allowed_mcp_server_ids` is verified
   **docs-only** (zero code anywhere in the repo) — capability enablement supersedes
   it; amend that draft RFC when Tier 3 lands. Nothing coexists, nothing migrates.

---

## 13. Horizon (eye-opener, explicit non-goal): Knowledge Flow as a capability

A thought experiment the team should hold while judging this abstraction. The entire
Knowledge Flow surface — library/corpus management UI, document processors, the
vectorization pipeline, the vector-search endpoint — is shaped exactly like one very
large capability:

- the query side is already becoming capability tools (#1906 document-access);
- ingestion, processors, and corpus admin are `router` routes + `tables`;
- library pickers and scope narrowing are `config_fields` + `chat_controls`;
- per-team enablement with settings (which stores, which embedder) is Tier 3's
  `TeamSettingsModel`, to the letter;
- the management UI is a **full-page surface in the team menu** — which no current
  slot provides.

Nothing in the manifest forbids this; two things fall short today: (1) UI contribution
stops at side panels — a capability cannot mount a full page; (2) KF is a separate
backend with its own lifecycle, while capabilities are in-pod packages. Neither is a
reason to do the refactor — KF works, and the migration would be enormous. The point is
a **design test: if the capability abstraction could not in principle absorb Knowledge
Flow, it is too small.** When shaping the manifest and registries, prefer the shape
that keeps this door open — e.g. a future page-slot should be a natural extension of
the side-panel slot (§9 item 3), not a different mechanism. Any actual move is its own
RFC series, far out of scope here.

---

## 14. Developer documentation & the `add-fred-capability` Skill

An abstraction whose whole point is "author a capability without touching Fred core" is
only real if an author (human or model) can discover *how* to author one. That knowledge
must ship with the abstraction — but it must stay **small**, because a capability's shape
(manifest fields, the four typed models, the middleware hooks) is exactly the kind of
thing that changes across tiers. Long prose here rots; a code author reading a stale
tutorial writes a stale capability.

**Two artifacts, deliberately minimal:**

1. **A short authoring guide** (`docs/swift/capabilities/AUTHORING.md`, ~1 page): the
   mental model (capability = manifest + middleware, §2), the four typed models and when
   each is used (§3.2, §3.5, §8.2), the three authoring lanes (§7), and a pointer to one
   *canonical reference capability in-tree* (the #1906 document-access pilot) as the
   worked example. It states the shape and links to code; it does **not** re-document
   every field — the manifest/class definitions in `fred-sdk` are the source of truth,
   and the guide points at them rather than copying them. This is the anti-obsolescence
   rule: **the code is the spec; the doc is the map.**

2. **An `add-fred-capability` Skill** — the primary, model-facing artifact. When a
   developer asks an assistant to "add a capability for X", the Skill instructs the model
   on: what a capability is and is not (it is not a scattered feature — §1), which of the
   three lanes (§7) fits the request (MCP server → zero Fred code; full vertical →
   package; first-party → `fred-capabilities-core`), which typed models to declare and
   what each carries, which middleware hook maps to each runtime need (§5.1 table), the
   registration line(s) per side (§4), and — critically — **what a capability author
   should and should not do**: never edit the central union/registry hotspots by hand
   (§1.1), never put capability code in control-plane (§7), never persist asset blobs in
   `tuning_json` (§3.8), keep runtime info out of LLM-exposed tool signatures (§3.5).

**Why a Skill, not just a doc.** The Skill is the executable form of the guide: it is
loaded on demand exactly when a capability is being authored, it can enforce the tier
boundary (refuse to hand-edit a hotspot the abstraction is meant to eliminate), and it
can point the model at the live reference capability and the current `fred-sdk` types
rather than a frozen copy. It keeps the guidance *actionable and current* where static
prose drifts.

**Staying non-obsolete — hard rules for both artifacts:**

- **Link, don't duplicate.** Reference the `CapabilityManifest` / `AgentCapability`
  definitions and the reference capability by path; never restate their fields inline.
- **One worked example, in-tree.** The pilot capability is the tutorial; when it changes,
  the example changes with it — no separate sample to keep in sync.
- **Tier-tagged.** Anything the guide/Skill says about middleware (§5), team scoping
  (§8), or the SDK surface (§6 Tier 4) is marked with the tier it lands in, so a reader
  at Tier 1 is not misled by Tier 3 mechanics that do not exist yet.
- **Versioned with the SDK, not the RFC.** When Tier 4 formalizes the `fred-sdk`
  capability surface, the guide and Skill move to live beside that surface and are updated
  in the same change — the doc-update checklist (Step 6) gains a row: *capability
  authoring surface changed → update `AUTHORING.md` + `add-fred-capability` Skill.*

The authoring guide and Skill are a **Tier 4 deliverable** (they formalize the authoring
experience), but a first, deliberately-thin version should ship alongside the #1906 pilot
so the pilot doubles as the reference example from day one.

> **As implemented 2026-07-11 (#1982, CAPAB-01) — thin v1 shipped.** Both artifacts
> landed against the merged capability surface, deliberately map-not-spec:
> - `docs/swift/capabilities/AUTHORING.md` — the ~1-page map: mental model (manifest +
>   middleware), the four typed models, the §5.1 hook table, the three lanes, registration
>   + boot invariants, the ships-a-router API-slice workflow (#1979), testing, and the hard
>   should-nots. It links the SDK contracts (`fred-sdk/contracts/capability/`,
>   `contracts/runtime.py`) and the `document_access` pilot / `demo.py` tracer by path
>   rather than restating fields.
> - `.claude/skills/add-fred-capability/SKILL.md` — the model-facing Skill (repo
>   instruction-file convention, same as `add-kpi-to-dashboard`): lane selector, the four
>   models, the §5.1 hook map, entry-point registration + boot rules, the router API-slice
>   step, and the refuse-these should-nots. Points at the live reference capability, not a
>   frozen copy.
> Both are tier-tagged (`[T0]…[T4]`). The Step 6 doc-update checklist (`CLAUDE.md`) gained
> the *capability authoring surface changed* row. When Tier 4 formalizes the `fred-sdk`
> capability surface, both artifacts move beside it and update in the same change.

---

## 15. Next steps (per repo workflow)

1. Add `CAPAB` to the task-ID table in `CLAUDE.md` and create `CAPAB-01` in
   `docs/swift/data/id-legend.yaml` (this RFC as `refs.rfc`).
2. Add backlog entries (Tier 0 pilot = #1906 as a capability) in the relevant backlog file.
3. Create the GitHub issue linking `CAPAB-01`, this RFC, and the backlog entry.
4. Cut implementation tickets from the tiers (all approved 2026-07-09; §6 order:
   Tier 2 migration — starting with the §5.2 checkpointer spike — then Tiers 0/1,
   then Tier 3).
