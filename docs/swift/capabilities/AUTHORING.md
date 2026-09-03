# Authoring a Fred capability

> **The code is the spec; this doc is the map.** Every field, model, and hook named
> here is defined in `fred-sdk` and worked end-to-end in one in-tree reference
> capability. This page tells you *which* file to read and *when* — it never restates
> a field. When the SDK surface changes, the SDK changes; this map does not need a
> rewrite.
>
> Authoring a capability with an assistant? Use the **`add-fred-capability` Skill**
> (`.claude/skills/add-fred-capability/`) — it is the executable form of this map.

Tier tags (`[T0]…[T4]`) mark which tier a mechanism lands in, so a reader at an early
tier is not misled by machinery that does not exist yet (RFC §6). Unmarked = live today.

---

## Mental model — a capability is manifest + tools

A capability is **one modular agent feature carried end to end by one object**, not a
feature scattered across the codebase (RFC §1, §2). It has two halves:

- **Declaration** — a `CapabilityManifest`: agent-creation fields, upload slots, chat
  parts, side panels, an optional router, owned tables, required env, team scope.
- **Runtime** — plain LangChain tools bound per turn to a typed `CapabilityContext`,
  returned from `tools()`. This runs unchanged under a ReAct agent (`create_agent`) and a
  Graph agent (`context.invoke_runtime_tool(...)`) — implement `tools()` and both work.

Both live on one `AgentCapability` subclass. **Installing the package that declares it
IS the registration** — no central list to edit (RFC §4).

`middleware()` exists as a ReAct-only escape hatch for the rare hook `tools()` cannot
express (a tool schema built dynamically per turn, a conversation-state edit, a
prompt-fragment injection) — see the hook table below. **Most capabilities never touch
it.** A capability that overrides `middleware()` without also implementing `tools()`
**must** declare `manifest.execution_models = ("react",)` exactly — it has zero
Graph-visible runtime contribution, so `"graph"` is always wrong for this shape, whether
left at the default (`("react", "graph")`) or written out explicitly. `ppt_filler`/
`writable_document` below are the worked example. **You cannot get this wrong and ship
it anyway**: pod boot itself refuses ANY `middleware()`-only capability whose
`execution_models` contains `"graph"` — never declared (kept the default) or explicitly
written that way, either fails startup (`InvalidExecutionModelError`). This is a
mechanical guarantee, not a rule that depends on the author reading this page.

Contract surface (import from here, never re-declare):
`libs/fred-sdk/fred_sdk/contracts/capability/` — `base.py` (`AgentCapability`),
`manifest.py` (`CapabilityManifest`, `FieldSpec` via `..models`, `AssetSlot`,
`ChatControlSpec`, `SidePanelSpec`, `TeamScopePolicy`, `UploadedFile`),
`context.py` (`CapabilityContext`, `CapabilityIdentity`, `SaveContext`, `EmptyModel`),
`hitl.py` (`HitlSpec`, `HitlGateRequest`), and
`libs/fred-sdk/fred_sdk/contracts/runtime.py` (`RuntimeServices` + its typed ports).

---

## The worked examples (read these, not a sample)

| File | What it shows |
| --- | --- |
| `libs/fred-runtime/fred_runtime/capabilities/demo.py` (`DemoEchoCapability`) | **Minimal tracer**: one static tool, one scalar config field, plus one router + one owned table + one chat part + one side panel — the full vertical, smallest possible. Implements `tools()` — works on ReAct and Graph agents. |
| `libs/fred-runtime/fred_runtime/capabilities/document_access/` (`DocumentAccessCapability`, #1906) | **Canonical real capability**: three live tools (vector search, `list_document_tree`, `summarize_document`) each reaching a platform service through its typed `RuntimeServices` port (`document_search` / `document_tree` / `document_summarize`), static config-field scoping, one computed chat-turn control, and transport failures rendered as `is_error` tool results via the SDK-typed `DocumentPortCallError`. The tutorial. Implements `tools()` — works on ReAct and Graph agents. |
| `libs/fred-runtime/fred_runtime/capabilities/mcp.py` (`McpCapability`, #1978, id contract fixed #1988) | An MCP catalog server surfaced *as* a capability — the zero-Fred-code lane, in code. Capability id is the catalog server id verbatim (no `mcp:` prefix); `fred_sdk.contracts.capability.mcp_ids` and its `is_mcp_capability_id` helper are retired — MCP-ness is detected via catalog/registry membership, never id sniffing. Its own tool loading is a separate, pre-existing path (`FredMcpToolProvider`) already common to ReAct and Graph — it legitimately overrides `middleware()` only for its prompt fragment. |
| `libs/fred-capability-ppt-filler/` (`PptFillerCapability`, #1903) | **First OUT-OF-TREE capability package** and the asset-bearing reference: its own pip package installed in the `fred-agents` pod (entry point in ITS `pyproject.toml`), an `AssetSlot` upload parsed and stored in `validate_config` (via `ctx.services.agent_assets` — keys only in the stored config), config-derived dynamic tools, a custom form widget (`FieldSpec.ui.widget` → plugin `configWidgets`), a contributed chat part + side panel, and a stateless `/analyze` route on `manifest.router`. Copy its shape for any capability that uploads a file or ships its own package. Implements only `middleware()` (its tool schema is built per turn from the parsed template — a genuine ReAct-specific need) and declares `execution_models=("react",)` — selecting it on a Graph agent fails loudly at assembly rather than silently contributing nothing. |
| `libs/fred-capability-platform-ops/` (`PlatformPostgresCapability`, #2458) | **First capability package of the admin-ops family** (same `libs/fred-capability-*` packaging as `ppt-filler`): two tools (`postgres_list_tables`, `postgres_run_query`) reaching the platform database through the typed `RuntimeServices.platform_sql` port (`PlatformSqlPort`, fred-sdk) — Tier B credentials never enter the package; transport/server failures rendered as `is_error` tool results via the SDK-typed `PlatformSqlPortError`. Implements `tools()` only — works on ReAct and Graph agents. |

---

## The four typed models — when each applies

Declared as ClassVars on the `AgentCapability` subclass; see `base.py` docstring for the
authoritative rules. In one line each:

- **`ConfigModel`** — what the user *sends* at agent creation (drives
  `manifest.config_fields`). A `FieldSpec` may set `ui=UIHints(widget=...)` to
  name a frontend stock **form** widget for the agent-creation form (#2023) —
  distinct from chat-turn controls. Known ids: `document_libraries` (the
  library/document tree picker for an array of library tag ids; see
  `document_access.library_tag_ids`). Unknown ids fall back to the
  type-derived default input, so older frontends degrade gracefully.
  `ui.visible_when="<sibling_key>"` hides the field while that sibling's
  effective value is falsy — display-only, the stored value is kept, so the
  capability must still handle the field's value when its gate is off.
  `FieldSpec.title`/`description`, like `manifest.name`/`description`, are
  **i18n keys** (`capability.<id>.fields.<field_key>.title`/`.description`),
  resolved by `TuningFieldRenderer` via `t()` — never plain text. Add the
  matching entries to both `apps/frontend/src/locales/{en,fr}/translation.json`
  in the same change (`document_access`/`demo_echo` are the worked examples).
  A widget-owned field (`ui.widget` resolving in the plugin's `configWidgets`,
  e.g. `ppt_filler_template`) is the one exception — the generic renderer
  never displays its title/description, so the plugin owns that field's
  strings under its own key namespace instead.
- **`StoredConfigModel`** — what the platform *persists* after `validate_config`
  enrichment; defaults to `ConfigModel` (RFC §3.2, §3.8).
- **`TurnOptionsModel`** — typed chat-time values from a chat control; `EmptyModel` if
  none (RFC §3.5). `[T0]`
- **`TeamSettingsModel`** — typed per-team enablement settings; `EmptyModel` until
  Tier 3 (RFC §8.2). `[T3]`

The **hard split** (RFC §3.5): a tool's signature exposes *only* LLM arguments; identity,
config, turn options, and platform services reach the tool through the middleware closure
over `CapabilityContext` — **never** through the tool schema the model sees. The per-turn
binding and the raw access token **never** enter `CapabilityContext`; platform access is
only via typed `RuntimeServices` ports (RFC §3.8, §10). `document_access` is the reference.

---

## Evolving a capability's config — additive vs breaking (RFC §3.8, §3.9)

Every persisted `capability_config` slice is stamped `{"schema_version":
manifest.version, "config": {...}}` at save time. `resolve_stored_config`
(`fred_runtime/capabilities/assembly.py`) reads it back: version matches →
plain `StoredConfigModel.model_validate(...)`; version differs → the
capability's `upgrade_config()` hook runs lazily, once, at read time — never a
mass row migration. This is a **separate mechanism** from the Alembic table
migrations described under "Registration, boot invariants, tables" below
(RFC §7.1): that's for a capability's *owned SQL tables*, this is for the
*stored config JSON blob* every capability has.

- **Adding an optional field with a default** — the common case, free: leave
  `manifest.version` unchanged, no `upgrade_config` override needed. An old
  stored slice missing the new key validates fine; Pydantic fills the
  default. Proof pattern: `test_default_upgrade_hook_validates_additive_old_shape`
  (`libs/fred-runtime/tests/test_capability_selection_1974.py`) — the
  default `upgrade_config` (plain `StoredConfigModel` validation) is
  correct for this case, nothing to write.
- **Removing, renaming, or retyping a field** — a real breaking change: bump
  `manifest.version` **and** override `upgrade_config(stored, from_version)`
  to map the old shape onto the new one. Copy the pattern from
  `GreeterCapability` in the same test file (lines ~75-99) — a worked
  `salutation` → `greeting` rename, with its own round-trip test
  (`test_version_mismatch_runs_upgrade_hook_lazily`). Write an equivalent
  test for your own migration; there is no other way to prove it works.
- **If `upgrade_config` is missing or raises** for a real mismatch, the
  failure surfaces as the named `CapabilityConfigInvalidError` → the
  `capability_config_invalid` suspension reason (RFC §3.9) — the agent is
  suspended with an actionable message ("reset its parameters and re-save"),
  never a silent misbehavior or a crash. Still worth avoiding by preferring
  the additive path whenever the change allows it — a suspension is visible
  and disruptive to whoever owns that agent instance.
- **Current policy, pre-GA:** `manifest.version` stays unbumped ("config-surface
  changes land without bumps" — see `document_summarize/capability.py`) while
  the platform has no real production installs to protect. No in-tree
  capability has ever shipped a non-default `upgrade_config()` — the
  mechanism is proven by the `GreeterCapability` test fixture, not by real
  capability code. Before GA, dry-run at least one real breaking change
  through this path deliberately, rather than discovering rough edges the
  first time it actually matters.

---

## Requirement → hook (RFC §5.1)

Map a runtime need to a primitive; do not invent a new hook. The first row runs on
ReAct **and** Graph agents; every other row is `middleware()`-only — ReAct agents alone.

| Need | Hook |
| --- | --- |
| Add tools | `tools(ctx)` — works on ReAct and Graph agents |
| Tool built at chat time | `middleware()` override, `wrap_model_call` editing `request.tools` — ReAct only |
| Runtime context split from LLM args | `CapabilityContext` via the middleware closure |
| Edit conversation state (edit notice, attachment note) | `before_model` returning a state-update dict `[T2]` |
| Contribute a system-prompt fragment | `wrap_model_call` / `modify_model_request` editing the prompt |
| Guardrails / summarization / PII / retries | prebuilt LangChain middleware — free |
| Tool approval (HITL) | declare `HitlSpec`s from `hitl_specs()`; the single platform gate merges them — capabilities never ship interrupt middleware (RFC §5.4) |

Chat-time controls: return `ChatControlSpec`s from `chat_controls(config)` (computed at
session-prep, never persisted — RFC §3.3, §3.7). Chat parts: extend the `UiPart` union
by declaring a part with a `Literal` `type` discriminator in `manifest.chat_parts`
(RFC §3.6). Both are shown in `document_access` / `demo.py`.

**Used a `middleware()`-only row above?** Declare `manifest.execution_models =
("react",)` — the default is `("react", "graph")`. Skipping this is not a safe default:
a Graph agent selecting a `middleware()`-only capability that left the default fails
loudly at assembly (`CapabilityError`) rather than silently getting no tools.

**Is it even a capability?** If the thing you want to add adjusts *how the model
is called* rather than *what the model can call*, it is probably not one.
Reasoning went through a full capability implementation before being withdrawn
for exactly this reason (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §33): an agent does
not *use* reasoning the way it uses document search, so offering it in the Tools
tab put the decision in the wrong mental model. It now ships as a plain agent
field plus a platform-emitted chat control. Model-call parameters, per-turn
platform options, and anything an author would not describe as "a thing this
agent can do" belong outside the capability system.

---

## The three authoring lanes (RFC §7)

| You need | You author | Fred code written |
| --- | --- | --- |
| Tools + config + prompt fragment | an **MCP server** registered in the catalog → it *is* a capability, id == the catalog server id (no prefix — #1988) | **zero** `[T1]` |
| Full vertical (`validate_config`, middleware, `router`, `tables`, team settings) | a **capability package** built on `fred-sdk` | the package only |
| First-party | same package model, installed in the `fred-agents` pod via a `pyproject.toml` dependency (worked example: `libs/fred-capability-ppt-filler`, #1903) | the package only |

**Do not** build a "capability pod" and **do not** put capability runtime code in
control-plane — it stays the proxy/registry/team-policy authority (RFC §7).

---

## Registration, boot invariants, tables

Declare a `fred.capabilities` entry point pointing at the subclass — see
`libs/fred-runtime/pyproject.toml` (`demo_echo`, `document_access`). The registry
auto-discovers installed packages at pod boot and **fails startup loudly** on any invalid
registration (`libs/fred-runtime/fred_runtime/capabilities/registry.py`,
`boot_capability_registry`): `DuplicateCapabilityIdError`, `DuplicateChatPartKindError`,
`MissingRequiredEnvError`, `DefaultOnRequiredSettingsError` (RFC §4). Never register a
capability twice (entry point *and* manual `register`) — that trips the duplicate gate.

Owns tables? Put them under the capability's **own** `DeclarativeBase`, name them
`cap_<id>_*`, use no foreign keys into core, ship an Alembic tree beside the package, and
return its path from `migrations_location()`. `python -m fred_runtime migrate` applies it
under `cap_<id>_alembic_version` (RFC §7.1). `demo.py` + `demo_migrations/` is the pattern.

**Team scope** (RFC §8.3): `TeamScopePolicy.DEFAULT_ON` (usable without an admin gate — a
capability with a *required* team-settings field cannot be default-on) or `ADMIN_GATED`
(default). `document_access` is default-on. MCP catalog servers carry the same policy via
`MCPServerConfiguration.team_scope` in `mcp_catalog.yaml` (default `admin_gated` — a
deployment must explicitly opt a server into `default_on`, #1988); there is no separate
MCP enablement mechanism.

**Manifest id pattern (#1988):** `CapabilityManifest.id` must match
`^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$` (FGA- and URL-safe) — a bad id fails pod boot
loudly instead of crashing control-plane FGA tuple writes later. No capability id may
carry a `:` or other separator; this is why MCP capability ids are the bare catalog
server id, not a `mcp:`-prefixed string.

**Manifest icon:** `CapabilityManifest.icon` is a **Material Symbols name in
snake_case** (e.g. `graphic_eq`, `find_in_page`, `extension`) — the frontend renders
it as a font ligature, so a name outside the supported set shows as raw text. The
supported set is the `materialIcons` list in
`apps/frontend/src/rework/components/shared/utils/Type.ts`; to use a new glyph, add
its name there (any name from https://fonts.google.com/icons works). Unknown names
fall back to a generic capability icon in the admin catalog.

---

## Ships a side panel? Declare its launcher (#2459)

A side panel is declared in the capability's frontend plugin
(`apps/frontend/src/rework/features/capabilities/<id>/plugin.ts`), keyed by the
manifest's `SidePanelSpec.widget`. The value is a spec, not a bare component:

```ts
sidePanels: {
  ppt_preview_pane: { Component: PptPreviewPane, icon: "slideshow", useHasContent: useHasPptPreview },
},
```

- `icon` - the glyph of the panel's launcher in the chat page's floating rail, from
  the same `materialIcons` set as the manifest icon above. Reuse the glyph the
  capability's own chat card and pane header already carry, so the launcher reads as
  the same thing they open (`slideshow` for the ppt_filler deck, `edit_document` for
  the writable_document editor).
- `useHasContent` - a hook answering "does this panel have anything to show for the
  OPEN conversation?". Omit it and the launcher is always offered; a capability that
  produces something on demand should implement it, or every session that merely
  ACTIVATES the capability gets a button onto an empty panel. Scope the answer to the
  conversation in the URL - capability slices are global, so state from a previous
  conversation otherwise lights the launcher up on a fresh chat. Read the id with
  `useOpenSessionId()` (`features/capabilities/useOpenSessionId.ts`), and answer from
  the capability's own list endpoint when it has one: `writable_document` does, so its
  launcher is right as soon as the conversation loads, while `ppt_filler` has to wait
  for its chat cards to render and register their deck.

---

## Ships a router? Regenerate its API slice (#1979)

A capability whose manifest declares a `router` gets its own OpenAPI doc and its own
generated RTK Query slice under `apps/frontend/src/rework/features/capabilities/<id>/api/`.
Touched the router → regenerate that capability's slice:

```
cd apps/frontend && make update-<id>-capability-api    # e.g. update-demo-echo-capability-api
```

The generated slice + dumped schema are `.prettierignore`d (see `apps/frontend/Makefile`
and `apps/frontend/.prettierignore`). Never hand-edit them.

**Skip every query until the capability is routed.** `createCapabilityBaseQuery`
resolves the pod's base URL from `capabilityRoutingSlice` at request time and fails
loudly when it is not there yet. On a hard page load that answer lands after the
first render, so a query fired too early gets its failure cached against args that
never change again - the capability then looks empty for the whole page load, while a
client-side navigation into the same page works (routing is already in the store).
Guard every hook on the capability's own API:

```ts
const routed = useCapabilityRouted(CAPABILITY_ID);
const { currentData } = useListThingsQuery({ sessionId }, { skip: !sessionId || !routed });
```

Prefer `currentData` over `data` for anything scoped to the open conversation: `data`
deliberately keeps the last resolved result across an arg change, so on a session
switch it answers for the conversation the user just left.

---

## Testing expectations

Unit-test the capability in isolation (see `libs/fred-runtime/tests/test_capability_*`):
register it and call `registry.validate()` to prove it passes the boot invariant; exercise
`validate_config`, `chat_controls`, and each tool with a stubbed `RuntimeServices` port
(a bare harness may inject `None` — fail loud, as `document_access` does). Shipped a
breaking config change (removed/renamed/retyped a field)? Add a `resolve_stored_config`
round-trip test for the `upgrade_config` path too — see "Evolving a capability's config"
above. Run `make test` + `make code-quality` in `libs/fred-runtime` (and `libs/fred-sdk`
if you touched the contract surface) — green before you claim done.

---

## Hard rules (do not break)

- **Link, don't duplicate** — import the SDK models and reference the pilot by path;
  never restate a manifest field inline (RFC §14).
- **Never hand-edit the central union/registry hotspots** the abstraction exists to
  eliminate (RFC §1.1); extend the `UiPart` union by *declaring* a chat part, not by
  editing the union.
- **No capability runtime code in control-plane** (RFC §7).
- **Never persist asset blobs in `tuning_json`** — store binaries through a service in
  `validate_config` and keep only their keys (RFC §3.8).
- **Keep runtime info out of LLM-exposed tool signatures** (RFC §3.5).
