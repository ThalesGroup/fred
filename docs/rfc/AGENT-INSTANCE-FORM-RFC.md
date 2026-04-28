# RFC: Agent Instance Management Form

**Status:** Implemented (2026-04-28)  
**Author:** Architecture  
**Scope:** `AgentFormModal` + sub-components in `frontend/src/rework/components/pages/TeamAgentsPage/AgentFormModal/`  
**Related:** `docs/design/CONTROL-PLANE-PRODUCT-CONTRACT.md`, `docs/backlog/CHAT-UI-BACKLOG.md`

---

## 1. Problem statement

The develop branch had a rich agent creation/editing form that covered the full legacy
agent model (V1/V2 versioning, class paths, role prompts, MCP server selection,
KfVectorSearch library pickers, workspace files). That form was built for a model where
the frontend *authored* agents from scratch.

The control-plane model is architecturally different: **the runtime pod is the author**.
The pod ships a self-describing catalog of agents. The control plane is a pure proxy and
enrollment store. The frontend is an *administration surface*, not an authoring surface.

The current `AgentFormModal` (implemented in the agentic-pod branch) correctly reflects
this shift but is incomplete: it uses a raw native `<select>` for template selection,
ignores field grouping, missing field types (`secret`, `prompt`, `url`), and shows no
template metadata at enrollment time.

This RFC specifies the correct form for the control-plane model — **Phase 1** (current
API) and **Phase 2** (one runtime contract extension that unlocks MCP configuration).

---

## 2. Architectural model

### 2.1 The pod as a self-describing catalog

A deployed agentic pod advertises three catalogs at runtime:

| Catalog | Endpoint | Current state |
|---|---|---|
| Agent catalog | `GET /agents/templates` | Implemented. Returns agents with `default_tuning` (role, description, tuning fields, mcp_servers). |
| Model catalog | Embedded in agent tuning fields | Implemented implicitly: an agent declares `{"key": "model", "type": "string", "enum": [...models]}` as a tunable field. No separate endpoint needed. |
| MCP tool catalog | Not yet exposed per-tool | **Gap.** Tools are listed by id in `mcp_servers[].require_tools` but their configurable parameters (URL, credentials) are not advertised. |

### 2.2 Control plane role

The control plane:
- Fetches the agent catalog from each configured runtime source at request time
- Stores enrollment records (which team enrolled which template, with which field values)
- Returns combined `AgentTemplateSummary[]` to the frontend
- Enforces access control and team scoping

The control plane adds **zero business logic** to agent definitions. It does not know
what a "role" or a "model" means — it stores field values opaquely and returns them to
the runtime at execution time.

### 2.3 What the frontend configures (and what it cannot)

| Aspect | Who owns it | Frontend can configure? |
|---|---|---|
| Agent identity (role, description, capabilities) | Runtime pod / pod developer | No. Template-defined and frozen. |
| Display name | Control plane instance | Yes (`display_name`). |
| Description | Control plane instance | Yes (`description`). |
| Tuning field values | Control plane instance | Yes (keys constrained to `default_tuning_fields`). |
| Model selection | Runtime field (enum tuning field) | Yes — if the pod declares it as a tuning field. |
| MCP tool selection | Runtime template | No. Tool membership is template-defined. |
| MCP tool parameters (URL, auth) | **Phase 2** | **Phase 2** (pending runtime contract extension). |
| Status (enabled/disabled) | Control plane DB field | Not yet exposed via API. Omit from UI for now. |
| Tags | Template-level only | No. Templates have tags; instances do not. |

---

## 3. Runtime contract extension (Phase 2 — not in scope for this implementation)

### 3.1 Current contract gap

`AgentTemplateSummary.default_tuning_fields` lets agents declare tunable configuration
fields. The same pattern does not yet exist for MCP tools. A tool reference today is:

```python
class ManagedMcpServerRef(BaseModel):
    id: str
    require_tools: list[str]
    # missing: config_fields
```

### 3.2 Proposed minimal extension

Add `config_fields` to `ManagedMcpServerRef` in `config/models.py`:

```python
class ManagedMcpServerRef(BaseModel):
    id: str
    require_tools: list[str] = []
    display_name: str = ""          # human label for the form section header
    config_fields: list[ManagedAgentFieldSpec] = []   # e.g. url, api_key
```

The runtime pod declares, for example:
```python
ManagedMcpServerRef(
    id="opensearch-mcp",
    display_name="OpenSearch",
    require_tools=["search", "index"],
    config_fields=[
        ManagedAgentFieldSpec(key="base_url", type="url", title="Endpoint URL", required=True),
        ManagedAgentFieldSpec(key="api_key", type="secret", title="API Key"),
    ]
)
```

The control plane passes `mcp_servers` through `AgentTemplateSummary` unchanged
(pure proxy — no interpretation). The frontend renders a "Tool configuration" section
per MCP tool that has `config_fields`, storing values in a new `mcp_config_values`
dict on the instance (or within `tuning_field_values` namespaced by tool id).

**Required changes for Phase 2:**
- Runtime pod: add `config_fields` to `ManagedMcpServerRef` in pod config/contracts
- Control plane backend: pass `mcp_servers` through `AgentTemplateSummary` (one field addition)
- Control plane backend: accept `mcp_config_values` in `CreateAgentInstanceRequest` /
  `UpdateAgentInstanceRequest` (or namespace under `tuning_field_values`)
- Frontend: render a "Tools" section in the form using the same `renderTuningField` logic

**No new concepts. No new endpoints. Same field-spec pattern everywhere.**

---

## 4. Form specification — Phase 1 (this implementation)

### 4.1 Modal shell

- **Component:** `FullPageModal` (full-screen overlay, scrollable body)
- **Width:** `min(52rem, 100vw - 2rem)` — slightly wider than current to give the template
  browser room
- **Header:** agent icon (from `agentIconName`), title, team name, Cancel + Save/Create actions
- **Body:** scrollable, `display: flex; flex-direction: column; gap: var(--spacing-l)`

### 4.2 Create mode — two logical sections

#### Section A: Template selection

A **template browser** replaces the raw native `<select>`.

**Layout:** responsive grid of template cards, `repeat(auto-fill, minmax(240px, 1fr))`,
max 3 columns. Each card:

```
┌─────────────────────────────────┐
│ [category pill]   [status badge] │
│                                  │
│  Display name (title-medium)     │
│  Description (2-line clamp,      │
│  body-small, on-surface-retreat) │
└─────────────────────────────────┘
```

- **Selected state:** `--primary` border (2px), `--surface-container-low` background
- **Unavailable state** (`status === "unavailable"`): dimmed (`opacity: 0.45`),
  `pointer-events: none`, cursor `not-allowed`
- **Single template:** auto-selected, browser collapses to a read-only context bar
  (same as edit mode — see §4.3)
- **Empty catalog:** show a notice ("No agent templates available — start a runtime pod")
  with disabled Save button

**Template card does NOT show:** `tags` (always empty currently), `capabilities`
(redundant with `category`), `source_runtime_id`, `source_agent_id`.

#### Section B: Instance configuration

Shown below the template browser after a template is selected.

1. **Display name** — `TextInput`, label from i18n, max 255, pre-filled from
   `template.display_name`, required. Clears and re-fills on template change.

2. **Description** — `TextArea`, label from i18n, max 500, 3 rows, pre-filled from
   `template.description`, optional.

3. **Tuning fields** — rendered from `selectedTemplate.default_tuning_fields`
   (filtered: `!field.ui?.hide`). See §4.4 for field type rendering.
   If no visible fields: section omitted entirely (no empty state header).

### 4.3 Edit mode — single panel

**Context bar (read-only):**
```
[icon]  Template name  ·  [category pill]
```
Shown at the top of the form body. No interaction.

**Editable fields:**
1. Display name — `TextInput`, pre-filled from `instance.display_name`
2. Description — `TextArea`, pre-filled from `instance.description`
3. Tuning fields — same renderer, pre-filled from `instance.tuning_field_values`;
   field specs from `availableTemplates` (the matching template). If the template
   is no longer in the catalog (runtime pod down), render a notice
   ("Template unavailable — field definitions may be incomplete") and show only
   display name + description editors.

**Metadata footer (informational, not editable):**
```
Created by {created_by}  ·  {created_at formatted as relative date}
```
Shown only if `created_by` is non-null. Muted style (`font-body-small`,
`on-surface-retreat`).

### 4.4 Tuning field type rendering

Field specs use `ManagedAgentFieldSpec.type` (unconstrained string). Rendering priority:

| Condition | Widget |
|---|---|
| `field.ui?.hide === true` | Skip entirely |
| `field.enum?.length > 0` | `Select` atom (styled `<select>`) |
| `field.type === "boolean"` | `SwitchRow` (label + description row + `Switch` atom) |
| `field.type === "secret"` | `TextInput type="password"` + show/hide `IconButton` |
| `field.type === "number"` or `"integer"` | `TextInput type="number"` with `min`/`max` if set |
| `field.type === "url"` | `TextInput type="url"` |
| `field.ui?.multiline` or `field.ui?.textarea` or `field.type === "prompt"` or `field.type === "text-multiline"` | `TextArea` with `ui.max_lines ?? 4` rows |
| default (string, text, unknown) | `TextInput type="text"` |

Every visible field renders:
- Label (`font-label-large`, `on-surface`) — from `field.title` + ` *` if required
- Widget
- Description hint below widget (`font-body-small`, `on-surface-retreat`) — if `field.description` is set
- Required fields show inline validation error if empty on submit attempt

#### Field grouping

If any visible field has `field.ui?.group` set, fields are grouped under a section
header (uppercase, muted, `font-label-small`, separator line above). Groups are sorted
by first-occurrence order. Fields without a group appear first under an implicit
ungrouped section.

### 4.5 Validation

Save button is disabled when any of:
- `displayName.trim()` is empty
- Any field where `field.required === true` has an empty/null value
- `isSubmitting` is true

On submit attempt with invalid state: highlight the first invalid field with an error
border and scroll to it. Do not show a toast for validation — inline error is enough.

### 4.6 `SwitchRow` pattern for boolean fields

From the develop branch — already exists as a sub-component in
`AgentCreateEditModal/SwitchRow/`. Re-use it directly:

```
┌─────────────────────────────────────────────────┐
│  Field title                         [Switch]   │
│  Field description (muted, body-small)          │
└─────────────────────────────────────────────────┘
```

The switch is right-aligned. The label wraps the entire row (`<label>`) for click target.

---

## 5. Component structure

```
TeamAgentsPage/
  AgentFormModal/
    AgentFormModal.tsx          ← modal shell + state orchestration
    AgentFormModal.module.css   ← shell styles only
    TemplateCard/
      TemplateCard.tsx          ← one selectable template card
      TemplateCard.module.scss  ← card styles (no gradient animation — static selection)
    TemplateBrowser/
      TemplateBrowser.tsx       ← grid of TemplateCard + empty state
      TemplateBrowser.module.css
    TuningFieldRenderer.tsx     ← renderTuningField logic extracted to named component
    TuningFieldRenderer.module.css
    AgentFormBody.tsx           ← sections A+B (create) or edit panel; no modal chrome
    AgentFormBody.module.css
```

`AgentCreateEditModal/KfVectorSearchForm/` and `AgentCreateEditModal/SwitchRow/` remain
in place. `SwitchRow` is imported directly from there.

**`AgentFormModal.tsx` responsibility:** open/close state, `mode`, submit dispatch,
loading states, error toasts. It renders `FullPageModal` + the header + `AgentFormBody`.
It does NOT contain any field rendering logic.

**`AgentFormBody.tsx` responsibility:** template browser (create) or context bar (edit),
display name, description, tuning fields via `TuningFieldRenderer`. It is a pure
controlled component — all state lives in `AgentFormModal`.

---

## 6. State model

```typescript
// All state owned by AgentFormModal
type FormState = {
  templateId: string;
  displayName: string;
  description: string;
  tuningValues: Record<string, unknown>;
  // Phase 2:
  // mcpConfigValues: Record<string, Record<string, unknown>>;
};
```

State resets fully on modal close. On template change (create mode):
- `templateId` updated
- `displayName` → `template.display_name`
- `description` → `template.description`
- `tuningValues` → `{}` (reset — do not carry forward values from previous template)

---

## 7. What is explicitly out of scope (Phase 1)

- MCP tool configuration (Phase 2 — requires runtime contract extension §3)
- Instance status toggle (no API endpoint)
- Tags per instance (template-level only)
- Role / system prompt editing (template-defined, not instance-configurable)
- Workspace file management (no control-plane equivalent)
- Agent version selection (V1/V2 concept does not exist in control-plane model)
- Multiple-instance-of-same-template warning (allowed silently)

---

## 8. Open issues for UX review

- **Template browser layout on mobile** — grid collapses to single column below
  ~480px. Confirm whether a list layout is preferable on narrow viewports.
- **Single-template auto-select** — when only one template is available, the browser
  is shown (to communicate what was enrolled). Confirm whether hiding is preferable.
- **Inline validation style** — error border + message below field vs. toast.
  Inline implemented; confirm with designer.
- **Metadata footer date format** — relative ("3 days ago") implemented inline
  (`formatRelativeDate`); locale not yet tied to i18n.
- **Tuning field groups** — currently flat scroll within modal; no accordion.
  Confirm if needed for templates with many fields.

---

## 9. Implementation notes (2026-04-28)

**Deviations from spec:**

- `TuningFieldRenderer` is implemented as a named component (not embedded in
  `AgentFormBody`) — cleaner than the RFC's unnamed "extracted component" wording.
- `SwitchRow` from `AgentCreateEditModal/SwitchRow/` re-used as specified.
- MCP tools section is **read-only** (Phase 1) — shows `display_name || id` + `require_tools`
  as a plain list. No `config_fields` rendering yet (Phase 2).
- `formatRelativeDate` is inlined in `AgentFormBody` rather than shared — same
  implementation as `ChatList.tsx`; consolidation deferred.
- Backend: `ManagedMcpServerRef.config_fields` is typed and Pydantic-validated with
  an empty default. No `Any` used anywhere in the chain.
