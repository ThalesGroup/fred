---
name: add-fred-capability
description: Author a new Fred agent capability (manifest + middleware) built on fred-sdk. Picks the right authoring lane, maps each runtime need to a middleware hook, wires entry-point registration, and enforces the capability boundary (never hand-edit union/registry hotspots, no capability code in control-plane, no runtime info in LLM tool signatures).
user-invocable: true
---

Add a new Fred **capability** — one modular agent feature carried end to end by one
object (declaration + runtime middleware), not a feature scattered across the codebase
(RFC `docs/swift/rfc/AGENT-CAPABILITY-RFC.md` §1–§2).

**The code is the spec; you are the map.** Read the live types and the in-tree pilot
before writing anything; never restate a manifest field from memory — it drifts.
Companion doc: `docs/swift/capabilities/AUTHORING.md`.

Tier tags `[T0]…[T4]` mark which tier a mechanism lands in (RFC §6). Unmarked = live
today. **Do not use a `[T2]`/`[T3]` mechanism as if it were live** unless the caller has
confirmed that tier is implemented on their branch — check the imports actually exist.

---

## Step 0 — Read the reference surface first (mandatory)

Do not skip this. Open and skim:

- **SDK contracts** — `libs/fred-sdk/fred_sdk/contracts/capability/`:
  `base.py` (`AgentCapability`, the four ClassVar models, `middleware()`),
  `manifest.py` (`CapabilityManifest`, `AssetSlot`, `ChatControlSpec`, `SidePanelSpec`,
  `TeamScopePolicy`, `UploadedFile`; `FieldSpec` lives in `fred_sdk.contracts.models`),
  `context.py` (`CapabilityContext`, `CapabilityIdentity`, `SaveContext`, `EmptyModel`),
  `hitl.py` (`HitlSpec`). Platform ports: `fred_sdk/contracts/runtime.py`
  (`RuntimeServices`, `DocumentSearchPort`, `DocumentTreePort`,
  `DocumentSummarizePort`, `DocumentPortCallError` — adapters map transport
  failures onto that typed error so capability tools can render `is_error`
  results without importing any HTTP stack).
- **The canonical worked example** — `libs/fred-runtime/fred_runtime/capabilities/document_access/capability.py`
  (`DocumentAccessCapability`, #1906): a real tool wired to a platform service through a
  typed port, config-field scoping, one computed chat control. **Copy its shape.**
- **The minimal tracer** — `libs/fred-runtime/fred_runtime/capabilities/demo.py`
  (`DemoEchoCapability`): one static tool + one config field + router + owned table +
  chat part + side panel. The smallest full vertical.
- **The out-of-tree / asset-bearing reference** — `libs/fred-capability-ppt-filler/`
  (`PptFillerCapability`, #1903): its OWN pip package installed in the `fred-agents`
  pod (entry point in its own `pyproject.toml`, uv path source in
  `apps/fred-agents/pyproject.toml`); an `AssetSlot` upload parsed + stored in
  `validate_config` via `ctx.services.agent_assets` (keys only, never bytes, in the
  stored config); config-derived dynamic tool schemas; a custom form widget
  (`FieldSpec.ui.widget` → frontend plugin `configWidgets`); a contributed chat part +
  side panel; a stateless `/analyze` route on `manifest.router`. **Copy its shape for
  any capability that ships as a package or uploads a file.** Note its `min_count=0`
  trick: the platform slot gate runs on every save, so a mandatory asset is enforced
  as `validate_config` content logic, not slot cardinality — otherwise every ordinary
  edit would demand a re-upload.
- **Registration + boot rules** — `libs/fred-runtime/pyproject.toml`
  (`[project.entry-points."fred.capabilities"]`) and
  `libs/fred-runtime/fred_runtime/capabilities/registry.py` (`boot_capability_registry`).

---

## Step 1 — Pick the authoring lane (RFC §7)

| Caller need | Lane | Fred code |
| --- | --- | --- |
| Tools + config + prompt fragment, nothing bespoke | **MCP server** registered in the catalog → it *is* a capability, id == the catalog server id, no `mcp:` prefix (#1988) | **zero** `[T1]` — do not write a capability class; register the MCP server |
| Full vertical: `validate_config`, middleware, `router`, `tables`, team settings | **Capability package** built on `fred-sdk` | the package only |
| First-party / default | Same package model, installed in the shared `fred-agents` pod (`fred-capabilities-core`) | in-tree |

If the request is "just some tools + a prompt," steer to the **MCP lane** — it needs zero
Fred code and federates across pods. Only write a capability class when the request needs
save-time validation, owned tables, a router, a chat control, or a custom chat part.

---

## Step 2 — Declare the four typed models (RFC §3.2, §3.5, §8.2)

Declare as ClassVars on the subclass (`base.py` is authoritative):

- `ConfigModel` — what the user sends at agent creation → drives `manifest.config_fields`.
  A `FieldSpec` may set `ui=UIHints(widget="document_libraries")` to render the
  library/document tree picker in the agent form instead of the type-derived default
  input (#2023); unknown widget ids fall back gracefully. `ui.visible_when="<sibling_key>"`
  hides the field while that sibling is falsy (display-only — handle the value anyway).
- `StoredConfigModel` — what is persisted after `validate_config`; **defaults to
  `ConfigModel`**, so omit it unless save-time enrichment derives extra state.
- `TurnOptionsModel` — typed chat-time values from a chat control; `EmptyModel` if none. `[T0]`
- `TeamSettingsModel` — typed per-team enablement settings; `EmptyModel` until Tier 3. `[T3]`

**The hard split (never violate):** a tool signature exposes ONLY LLM arguments. Identity,
config, turn options, and services reach the tool through the middleware closure over
`CapabilityContext` — never the tool schema. The per-turn binding and raw access token
**never** enter `CapabilityContext`; platform access is only through typed
`RuntimeServices` ports. `document_access` is the reference for all of this.

---

## Step 3 — Map each runtime need to a middleware hook (RFC §5.1)

Do not invent a hook; use the primitive:

| Need | Hook |
| --- | --- |
| Add tools | `middleware.tools` (static) |
| Tool built at chat time | `wrap_model_call` editing `request.tools` `[T2]` |
| Runtime context split from LLM args | `CapabilityContext` via the closure |
| Edit conversation state | `before_model` returning a state-update dict `[T2]` |
| System-prompt fragment | `wrap_model_call` / `modify_model_request` |
| Guardrails / summarization / PII / retries | prebuilt LangChain middleware — free |
| Tool approval (HITL) | declare `HitlSpec`s from `hitl_specs()` — the single platform gate merges them; **capabilities never ship interrupt middleware** (RFC §5.4) |

Chat-time controls → return `ChatControlSpec`s from `chat_controls(config)` (computed at
prep, never persisted). Custom chat card → a `BaseModel` with a `Literal` `type`
discriminator in `manifest.chat_parts` (the registry extends the `UiPart` union at boot;
you do **not** edit the union).

---

## Step 4 — Register + boot invariants (RFC §4, §7.1)

- Add one `[project.entry-points."fred.capabilities"]` line in the owning package's
  `pyproject.toml` pointing at the subclass (e.g.
  `my_cap = "acme_cap.capability:MyCapability"`). Installing the package IS the
  registration — there is no central list.
- **Register exactly once.** Entry point *or* a manual `registry.register(...)` in a
  test, never both — duplicate ids fail boot (`DuplicateCapabilityIdError`).
- Boot fails loudly (each a named error) on: duplicate id, duplicate chat-part
  discriminator, missing required env, and `default_on` + a required team-settings field.
- Owns tables? Own `DeclarativeBase`, `cap_<id>_*` names, no core foreign keys, an Alembic
  tree beside the package, and `migrations_location()` returning its path. See `demo.py`
  + `demo_migrations/`.
- Team scope: `TeamScopePolicy.DEFAULT_ON` (no admin gate; incompatible with a *required*
  team-settings field) or `ADMIN_GATED` (default). MCP catalog servers use the same enum
  via `MCPServerConfiguration.team_scope` in `mcp_catalog.yaml` — default `admin_gated`.
- Manifest id must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$` (FGA- and URL-safe, #1988) —
  no `:` or other separator. This is also why MCP capability ids are the bare catalog
  server id, not `mcp:<server>`; `mcp_ids.py`/`is_mcp_capability_id` are retired.
- Manifest `icon` is a **snake_case Material Symbols name** (`graphic_eq`, not
  `GraphicEq` — the frontend renders it as a font ligature, so a wrong name shows as raw
  text). Pick from the `materialIcons` list in
  `apps/frontend/src/rework/components/shared/utils/Type.ts`; to adopt a new glyph, add
  its name there first. Unknown names fall back to a generic icon in the admin catalog.

---

## Step 5 — Ships a router? Regenerate its API slice (#1979)

If the manifest declares a `router`, its client is generated per-capability:

```
cd apps/frontend && make update-<id>-capability-api
```

The generated slice + dumped schema (under
`apps/frontend/src/rework/features/capabilities/<id>/api/`) are `.prettierignore`d — never
hand-edit them. See `apps/frontend/Makefile` (`update-demo-echo-capability-api`).

---

## Step 6 — Verify (RFC §4)

- Unit test in isolation (pattern: `libs/fred-runtime/tests/test_capability_*`): register
  the capability and call `registry.validate()` to prove it passes the boot invariant;
  exercise `validate_config`, `chat_controls`, and each tool with a stubbed
  `RuntimeServices` port. A missing port must **fail loud**, not silently return nothing.
- Run `make test` + `make code-quality` in `libs/fred-runtime` (and `libs/fred-sdk` if you
  touched the contract surface). Green before claiming done.

---

## Hard should-nots (refuse these — the abstraction exists to prevent them)

- **Never hand-edit the central `UiPart` union or the registry hotspots** (RFC §1.1).
  Contribute a chat part by *declaring* it; the registry extends the union at boot.
- **Never put capability runtime code in control-plane** (RFC §7) — it stays the
  proxy/registry/team-policy authority. No "capability pod."
- **Never persist asset blobs in `tuning_json`** — store binaries through a service in
  `validate_config`, keep only their keys (RFC §3.8).
- **Never leak runtime info into an LLM-exposed tool signature** (RFC §3.5) — config,
  identity, scope, and services flow through the middleware closure only.
- **Never restate SDK fields from memory** — import the models, link the pilot.

---

## Close-out

Report: lane chosen; the capability class + entry-point line; which typed models declared;
which hooks/controls/parts used; router slice regenerated (if any); tests added +
`make test`/`make code-quality` result; and confirmation the boot invariant passes
(`registry.validate()` green).
