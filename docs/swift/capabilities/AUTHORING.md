# Authoring a Fred capability

> **The code is the spec; this doc is the map.** Every field, model, and hook named
> here is defined in `fred-sdk` and worked end-to-end in one in-tree reference
> capability. This page tells you *which* file to read and *when* — it never restates
> a field. When the SDK surface changes, the SDK changes; this map does not need a
> rewrite. (RFC [`AGENT-CAPABILITY-RFC.md`](../rfc/AGENT-CAPABILITY-RFC.md) §14.)
>
> Authoring a capability with an assistant? Use the **`add-fred-capability` Skill**
> (`.claude/skills/add-fred-capability/`) — it is the executable form of this map.

Tier tags (`[T0]…[T4]`) mark which tier a mechanism lands in, so a reader at an early
tier is not misled by machinery that does not exist yet (RFC §6). Unmarked = live today.

---

## Mental model — a capability is manifest + middleware

A capability is **one modular agent feature carried end to end by one object**, not a
feature scattered across the codebase (RFC §1, §2). It has two halves:

- **Declaration** — a `CapabilityManifest`: agent-creation fields, upload slots, chat
  parts, side panels, an optional router, owned tables, required env, team scope.
- **Runtime** — a stack of LangChain `AgentMiddleware` carrying the capability's tools
  and hooks, bound per turn to a typed `CapabilityContext`.

Both live on one `AgentCapability` subclass. **Installing the package that declares it
IS the registration** — no central list to edit (RFC §4).

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
| `libs/fred-runtime/fred_runtime/capabilities/demo.py` (`DemoEchoCapability`) | **Minimal tracer**: one static tool, one scalar config field, plus one router + one owned table + one chat part + one side panel — the full vertical, smallest possible. |
| `libs/fred-runtime/fred_runtime/capabilities/document_access/` (`DocumentAccessCapability`, #1906) | **Canonical real capability**: a live vector-search tool reaching a platform service through a typed `RuntimeServices` port, static config-field scoping, and one computed chat-turn control. The tutorial. |
| `libs/fred-runtime/fred_runtime/capabilities/mcp.py` (`McpCapability`, #1978, id contract fixed #1988) | An MCP catalog server surfaced *as* a capability — the zero-Fred-code lane, in code. Capability id is the catalog server id verbatim (no `mcp:` prefix); `fred_sdk.contracts.capability.mcp_ids` and its `is_mcp_capability_id` helper are retired — MCP-ness is detected via catalog/registry membership, never id sniffing. |

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

## Requirement → middleware hook (RFC §5.1)

Map a runtime need to a LangChain primitive; do not invent a new hook.

| Need | Hook |
| --- | --- |
| Add tools | `middleware.tools` (static) |
| Tool built at chat time | `wrap_model_call` editing `request.tools` `[T2]` |
| Runtime context split from LLM args | `CapabilityContext` via the middleware closure |
| Edit conversation state (edit notice, attachment note) | `before_model` returning a state-update dict `[T2]` |
| Contribute a system-prompt fragment | `wrap_model_call` / `modify_model_request` editing the prompt |
| Guardrails / summarization / PII / retries | prebuilt LangChain middleware — free |
| Tool approval (HITL) | declare `HitlSpec`s from `hitl_specs()`; the single platform gate merges them — capabilities never ship interrupt middleware (RFC §5.4) |

Chat-time controls: return `ChatControlSpec`s from `chat_controls(config)` (computed at
session-prep, never persisted — RFC §3.3, §3.7). Chat parts: extend the `UiPart` union
by declaring a part with a `Literal` `type` discriminator in `manifest.chat_parts`
(RFC §3.6). Both are shown in `document_access` / `demo.py`.

---

## The three authoring lanes (RFC §7)

| You need | You author | Fred code written |
| --- | --- | --- |
| Tools + config + prompt fragment | an **MCP server** registered in the catalog → it *is* a capability, id == the catalog server id (no prefix — #1988) | **zero** `[T1]` |
| Full vertical (`validate_config`, middleware, `router`, `tables`, team settings) | a **capability package** built on `fred-sdk` | the package only |
| First-party | same package model, installed in the shared `fred-agents` pod (`fred-capabilities-core`) | in-tree |

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

## Ships a router? Regenerate its API slice (#1979)

A capability whose manifest declares a `router` gets its own OpenAPI doc and its own
generated RTK Query slice under `apps/frontend/src/rework/features/capabilities/<id>/api/`.
Touched the router → regenerate that capability's slice:

```
cd apps/frontend && make update-<id>-capability-api    # e.g. update-demo-echo-capability-api
```

The generated slice + dumped schema are `.prettierignore`d (see `apps/frontend/Makefile`
and `apps/frontend/.prettierignore`). Never hand-edit them.

---

## Testing expectations

Unit-test the capability in isolation (see `libs/fred-runtime/tests/test_capability_*`):
register it and call `registry.validate()` to prove it passes the boot invariant; exercise
`validate_config`, `chat_controls`, and each tool with a stubbed `RuntimeServices` port
(a bare harness may inject `None` — fail loud, as `document_access` does). Run
`make test` + `make code-quality` in `libs/fred-runtime` (and `libs/fred-sdk` if you
touched the contract surface) — green before you claim done.

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
