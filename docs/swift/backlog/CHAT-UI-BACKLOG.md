# Chat UI Backlog

## 0 Overview

### 0.1 Context

Phase FRONT-04 delivered a functional `ManagedChatPage` wired to the SSE runtime
connector. The page works but is minimal: plain text bubbles, no markdown, no
reasoning trace, no source citations.

This backlog defines the progressive build-out of the managed chat interface
into a production-quality UI, built from new atomic/molecular components that
integrate with the existing rework design system.

The reference bar for UX conventions is **OpenWebUI / OpenAI / Agno**:
user messages on the right, agent on the left, clean monochromatic palette,
progressive disclosure for reasoning chains.

---

### 0.2 Relationship to Other Backlogs

This backlog is **parallel to** `FRONTEND-BACKLOG.md` (Phase 5 migration work).
It does not depend on migration phase completion — `ManagedChatPage` is already
the target surface and already uses the correct SSE connector (`useChatSse`).

It is **not** a migration backlog. It concerns rendering quality, component
architecture, and progressive feature parity with the legacy `ChatBot.tsx`
surface.

---

### 0.3 Guiding Constraints

> **Per-component visual and interaction specs:** [`docs/design/CHAT-COMPONENT-SPECS.md`](../design/CHAT-COMPONENT-SPECS.md).
> That file is the implementation authority for each named component.

- All new components live under `src/rework/components/shared/` following the
  atoms → molecules → organisms hierarchy.
- CSS modules only. Use existing design tokens (`--spacing-*`, `--radius-*`,
  `--font-*`, color variables).
- No new global state. Conversation state stays local to `ManagedChatPage`
  via `useState`.
- The SSE connector (`useChatSse`) is the only execution wire. Do not add
  WebSocket or REST polling for message content.
- Keep existing `HitlPrompt` component unchanged in Phase CHAT-01.
- Never hand-edit `runtimeOpenApi.ts` — it is generated.
- **Never show technical identifiers in user-facing UI.** `agent_instance_id`, session UUIDs,
  runtime IDs, and any other internal key must never appear as visible text in a label,
  header, badge, or tooltip. Every user-facing surface must use human-readable display names
  sourced from the control-plane product surface (`ManagedAgentInstanceSummary.display_name`,
  team name, etc.). Technical IDs remain internal — for routing, API calls, and `data-*`
  attributes only.

### 0.4 History Ownership Contract

This backlog must stay aligned with the managed execution architecture.

Message history and session metadata have different owners.

- `fred-runtime` owns conversation message content
  - writes every turn to `session_history`
  - serves message history reads via runtime endpoints
  - remains the only backend on the hot path for conversation content
- `control-plane-backend` owns session metadata only
  - team-scoped session list, title, created/updated timestamps, status
  - agent/team binding and management-plane concerns
  - must not proxy, cache, or serve full message history

Consequences for the frontend:

- the chat page reads message history from runtime using the prepared
  `messages_url_template`
- the sidebar reads session metadata from control-plane
- control-plane is not the scalable conversation-history serving plane in this
  architecture
- this backlog must never introduce a control-plane dependency for message
  content reads or writes

### 0.5 Session Lifecycle Summary

The managed chat page must follow this lifecycle exactly:

1. the frontend generates a `session_id` before the first managed turn
2. the frontend calls `prepare-execution` for the selected `agent_instance_id`
3. the frontend sends the turn to runtime with `session_id`,
   `agent_instance_id`, and `execution_grant`
4. `fred-runtime` executes the turn and writes message content to
   `session_history`
5. `fred-runtime` owns later message-history reads for that `session_id`
6. `control-plane-backend` stores only the session metadata needed by the
   sidebar and management UI

Simple ownership rule:

- if the UI needs message content, the source is runtime
- if the UI needs session list / title / status / team grouping, the source is
  control-plane

---

## 1 Phase CHAT-01 — Page Architecture & Core Layout

### 1.1 Goal

Replace the current flat `ManagedChatPage` implementation with a structured
layout built from purpose-built components. No feature additions yet — only
architectural correctness and visual alignment with OpenWebUI conventions.

---

### 1.2 Layout Contract

```
┌─ Sidebar ──────┬─── Chat Area ──────────────────────────────┐
│  ChatList      │                                            │
│  (existing)    │  ┌─ ChatMessagesArea (scrollable flex) ─┐ │
│                │  │                                       │ │
│                │  │         ┌─── AssistantTurn ────────┐ │ │
│                │  │         │  ThoughtTrace        │ │ │
│                │  │         │  AssistantMessage         │ │ │
│                │  │         │  SourcesPanel             │ │ │
│                │  │         └──────────────────────────┘ │ │
│                │  │                                       │ │
│                │  │  ┌── UserMessage ──────────────────┐  │ │
│                │  │  └────────────────────────────────┘  │ │
│                │  └───────────────────────────────────────┘ │
│                │  ┌─ ChatInputBar ────────────────────────┐ │
│                │  └──────────────────────────────────────┘  │
└────────────────┴────────────────────────────────────────────┘
```

Alignment convention (OpenWebUI / OpenAI):

- **User message**: right-aligned, max-width 65%, background `--surface-container-high`
- **Agent turn**: left-aligned, max-width 75%, background `--surface-container`

> **Three-column layout note (Phase CHAT-03 prerequisite):** the page must be built with three
> columns from Phase CHAT-01 — left sidebar, centre chat area, right options panel. The right
> panel returns `null` while Phase CHAT-03 is not yet landed, so no structural refactor is needed
> later. See §3.7 for the full three-column spec.

---

### 1.3 New Component Map

#### Atoms

| Component | Path | Purpose |
|---|---|---|
| `MessageBubble` | `atoms/MessageBubble/` | Styled container: role variant, padding, radius, max-width |
| `StreamingCursor` | `atoms/StreamingCursor/` | Blinking inline cursor visible during delta streaming |
| `ToolBadge` | `atoms/ToolBadge/` | Chip showing tool name + status (running / success / error) |
| `SourceBadge` | `atoms/SourceBadge/` | Inline superscript `[N]` linking to nth source card |

#### Molecules

| Component | Path | Purpose |
|---|---|---|
| `UserMessage` | `molecules/UserMessage/` | Right-aligned bubble + timestamp |
| `AssistantMessage` | `molecules/AssistantMessage/` | Left-aligned bubble, streaming cursor, plain text (markdown deferred) |
| `ThoughtTrace` | `molecules/ThoughtTrace/` | Collapsible reasoning trace — entry grouping, status chips, detail drawer (see §1.6 for full spec) |
| `TraceEntryRow` | `molecules/ThoughtTrace/TraceEntryRow/` | One step row: index, status chip, channel/node/tool badges, primary text, detail-open trigger |
| `TraceDetailDrawer` | `molecules/ThoughtTrace/TraceDetailDrawer/` | Slide-in Monaco JSON drawer for full step or call+result payload; theme-aware |
| `SourceCard` | `molecules/SourcesPanel/SourceCard/` | One citation: index, title, score, excerpt |
| `SourcesPanel` | `molecules/SourcesPanel/` | List of SourceCards, visible after `final` event |
| `ChatInputBar` | `molecules/ChatInputBar/` | TextArea atom + send IconButton, disabled during streaming |

#### Organisms

| Component | Path | Purpose |
|---|---|---|
| `ChatMessagesArea` | `organisms/ChatMessagesArea/` | Scrollable message list, auto-scroll, empty state |
| `AssistantTurn` | `organisms/AssistantTurn/` | Groups ThoughtTrace + AssistantMessage + SourcesPanel for one exchange |
| `AgentOptionsPanel` | `organisms/AgentOptionsPanel/` | Right-side collapsible panel: agent-specific options + admin debug tools (Phase CHAT-03). **Retired (2026-05-24) for routine controls** — search policy, RAG scope, and library selection moved to `ComposerSettingsControls` chips in `RichInputField` `topSlot`. Debug/admin tools will use `InlineDrawer` when implemented. |

---

### 1.4 Local Conversation State

`ManagedChatPage` owns this state via `useState`. No Redux slice.

This state is a presentation model only.

It is populated from two sources:

- streamed runtime events during live execution
- runtime history loaded from `messages_url_template` for an existing
  `session_id`

It is not sourced from control-plane message-history APIs because none should
exist in the managed path.

```typescript
// Internal shape — not exported
interface ConversationMessage {
  id: string                      // exchange_id + ":" + rank
  role: 'user' | 'assistant'
  text: string
  isStreaming: boolean
  thinkingSteps: ThinkingStep[]
  sources: VectorSearchHit[]
  statusText?: string             // from status events, cleared on final
  error?: string                  // from node_error events
}

type ThinkingStep =
  | { kind: 'tool_call'; callId: string; name: string; args: Record<string, unknown>; status: 'running' | 'done' | 'error' }
  | { kind: 'tool_result'; callId: string; ok: boolean; latencyMs?: number; content: string }
```

---

### 1.5 SSE Event → UI Mapping

| Runtime event | State mutation | Visible effect |
|---|---|---|
| `assistant_delta` | Append delta to current assistant message | Text grows, `StreamingCursor` pulses |
| `tool_call` | Push `ThinkingStep {kind:'tool_call', status:'running'}` | `ThoughtTrace` appears (open by default), `ToolCallStep` with spinner |
| `tool_result` | Match `call_id`, update to `status:'done'` or `status:'error'`, add `tool_result` step | `ToolCallStep` → `ToolResultStep` |
| `final` | Replace text with final content, attach sources, clear `isStreaming` | `StreamingCursor` disappears, `SourcesPanel` appears if sources present |
| `status` | Set `statusText` on current message | Italic status line below bubble |
| `awaiting_human` | Existing `HitlPrompt` path — unchanged | HITL inline prompt |
| `node_error` | Set `error` on current message | Error chip in bubble |
| `turn_persisted` | Update `sessionId` in URL + call `PATCH /teams/{teamId}/sessions/{sessionId}` with `updated_at` to keep sidebar sorted | Silent — fire-and-forget, failure does not interrupt chat |

#### HITL History Schema (fixed 2026-04-26)

When loading history from `messages_url_template`, HITL interactions appear as structured
`ChatMessage` rows rather than flat text — the runtime persists them this way since 2026-04-26.

| Channel | Role | Part type | Content |
|---|---|---|---|
| `hitl_request` | `system` | `HitlRequestPart` | Full gate definition: `question`, `choices[]{id, label}`, optional `stage` and `title` |
| `hitl_response` | `user` | `HitlResponsePart` | User's selection: `choice_id` + optional `label` |

These are **main-conversation rows**, not trace entries. Rendering contract:

- `hitl_request` — render as an interactive choice card (or a frozen read-only version during
  history replay): question text + list of labelled choices. Use the same `HitlPrompt` visual
  shape, but in read-only mode (choices not clickable when replaying).
- `hitl_response` — render as a right-aligned user bubble with the selected label (or `choice_id`
  if `label` is absent). It looks like a regular user message and is positioned where the user
  made their choice in the conversation timeline.
- Do NOT include `hitl_request` or `hitl_response` in `TRACE_CHANNELS`.

**Sources in history (fixed 2026-04-26):** the `final` event payload now carries a `sources`
array; `_write_turn_history` extracts it and stores it in `ChatMetadata.sources`. When
normalising history, the sources for an exchange come from the `assistant / final` row's
`metadata.sources` field — not from a separate event.

---

### 1.6 ThoughtTrace Behaviour

> **Full visual and interaction spec:** [`docs/design/CHAT-COMPONENT-SPECS.md §1`](../design/CHAT-COMPONENT-SPECS.md).
> The spec file is the authority — the summary below covers the data model only.

**Reference implementation:** `frontend/src/components/chatbot/ReasoningStepsAccordion.tsx` and
`ReasoningStepBadge.tsx`. Port the logic and enrich the visual presentation for the rework
design system. Do not delete the legacy component until `ManagedChatPage` fully replaces the
old chat surface.

#### Entry grouping model

Steps are not rendered one-to-one from SSE events. They are first grouped into `TraceEntry`
objects before rendering:

```typescript
type TraceEntry =
  | { kind: 'solo';  message: ChatMessage }
  | { kind: 'combo'; call: ChatMessage; result?: ChatMessage }
```

Rules:
- every `tool_call` message opens a `combo` entry
- its matching `tool_result` (matched by `toolId`) closes the combo in-place
- all other channel types (`plan`, `thought`, `observation`, `system_note`, `error`) are `solo`
- only messages whose `channel` is in `TRACE_CHANNELS` are included:
  `plan | thought | observation | tool_call | tool_result | system_note | error`
- `hitl_request` and `hitl_response` are **excluded** from `TRACE_CHANNELS` — they are
  main-conversation rows rendered inline (see §1.5 HITL History Schema above)
- entries are ordered by `rank` ascending

#### Per-entry display (`TraceEntryRow`)

| Field | Source |
|---|---|
| Index | Sequential position (1-based), fixed-width column |
| Status chip | `ok` / `error` / `pending` — see status table below |
| Channel badge | `message.channel` with underscores replaced by spaces |
| Node chip | `extras.node` string when present |
| Task chip | `extras.task` string when present and no node chip |
| Tool name chip | `tool_call.name` for combo entries |
| Primary text | Smart summary — see derivation rules below |
| Detail button | Opens `TraceDetailDrawer` for this entry |

**Primary text — combo entry:**
1. `extras.summary` on the result if it is a non-empty string
2. `N result(s) in Xms` if source count > 0 and latency known
3. `N result(s)` if source count > 0 and latency unknown
4. `Completed in Xms` / `Failed in Xms` if latency known
5. `waiting for result…` while result is absent

Latency is read from `tool_result.latency_ms` first, then `message.metadata.latency_ms`.
Source count is `message.metadata.sources.length`.

**Primary text — solo entry:**
1. `tool_result` channel: same compact summary as combo result above
2. all others: `textPreview(message)` → `extras.node` → `extras.task` → channel label

#### Status chip values

| Chip | Condition |
|---|---|
| `ok` | combo with `result.ok === true`; solo tool_result with `ok === true` |
| `error` | combo with `result.ok === false`; solo tool_result with `ok === false`; channel `error` |
| `pending` | combo with no result yet (streaming) |
| _(none)_ | non-tool solo entries |

#### Detail drawer (`TraceDetailDrawer`)

- slides in from the right (640 px, full screen on mobile)
- header: `channel · tool name · node/task` joined by ` · `, with a close button
- body: Monaco editor — read-only, JSON language, `wordWrap: on`, `minimap: off`,
  `scrollBeyondLastLine: off`, `automaticLayout: on`
- theme: `vs-dark` when MUI palette mode is `dark`, `vs` otherwise
- payload for combo: `{ tool_call: <ChatMessage>, tool_result: <ChatMessage | null> }`
- payload for solo: full `ChatMessage`
- closed by the × button or clicking the backdrop

#### Accordion lifecycle

- opens automatically when the first trace step arrives during streaming
- stays open while streaming
- **auto-closes** when `final` event arrives (collapsed by default after turn completes)
- user can re-open manually
- header: info icon + `Trace` label + `N step(s)` count
- spinner visible next to the label while streaming

---

### 1.7 Tasks

**Atoms**

- [x] Create `MessageBubble` atom with `role` variant prop — `atoms/MessageBubble/MessageBubble.tsx`
- [x] Create `StreamingCursor` atom (CSS blink animation) — `atoms/StreamingCursor/StreamingCursor.tsx`
- [x] Create `ToolBadge` atom (running / success / error variants) — `atoms/ToolBadge/ToolBadge.tsx`
- [x] Create `SourceBadge` atom (superscript index, onClick scroll) — `atoms/SourceBadge/SourceBadge.tsx` (done Phase CHAT-02)

**Molecules**

- [x] Create `UserMessage` molecule — `molecules/UserMessage/UserMessage.tsx`
- [x] Create `AssistantMessage` molecule (StreamingCursor inline) — `molecules/AssistantMessage/AssistantMessage.tsx`
- [x] Extract trace entry grouping logic (`TraceEntry`, `toolId`, `isToolCall`, `isToolResult`,
  `TRACE_CHANNELS`, `groupTraceEntries`, `statusForEntry`) to `src/rework/utils/traceUtils.ts`
- [x] Extract primary-text helpers (`summarizeToolResultCompact`, `primaryTextForEntry`,
  `formatLatencyMs`, `thoughtSummaryLabel`, `entryLabel`) to `traceUtils.ts`
- [x] Create `TraceEntryRow` molecule (index column, status dot, channel label chip,
  primary text, click-to-open detail trigger) — at `molecules/ThoughtTrace/TraceEntryRow/`
- [x] Create `TraceDetailDrawer` molecule (slide-in drawer, Monaco read-only JSON,
  close on backdrop click or × button, Escape key) — at `molecules/ThoughtTrace/TraceDetailDrawer/`
- [x] Create `ThoughtTrace` molecule using `TraceEntry[]` model + `TraceEntryRow` list
  (toggle open/close, `done` prop auto-collapses on final, streaming pulse animation)
- [x] Wire `TraceDetailDrawer` inside `ThoughtTrace` (open/close via selected-entry state in `TraceEntryRow`)
- [x] Create `SourceCard` molecule (index + title + score % + 2-line excerpt) — `molecules/SourcesPanel/SourceCard/`
- [x] Create `SourcesPanel` molecule (collapsible, stack of SourceCards, "Sources (N)" header) — `molecules/SourcesPanel/`
- [x] Create `ChatInputBar` molecule (TextArea + send IconButton, Shift+Enter = newline) — `molecules/ChatInputBar/ChatInputBar.tsx`

**Organisms**

- [x] Create `ChatMessagesArea` organism (scroll container, auto-scroll to bottom, empty state) — `organisms/ChatMessagesArea/`
- [x] Create `AssistantTurn` organism (ThoughtTrace + AssistantMessage + SourcesPanel) — `organisms/AssistantTurn/`

**Page wiring**

- [x] Display the agent's human-readable name in the chat header — sourced from
  `ManagedAgentInstanceSummary.display_name`; **never display `agent_instance_id` or any UUID**
- [x] Group `messages[]` by `exchange_id` into turns in `ManagedChatPage`; render `ThoughtTrace`
  per turn for trace-channel messages alongside user / final reply bubbles
- [x] Wire `turn_persisted` → `PATCH /teams/{teamId}/sessions/{sessionId}` with `updated_at`
  (`onTurnPersisted` callback added to `ChatSseCallbacks`; `ManagedChatPage` owns the PATCH call)
- [x] Replace temp `MessageBubble` with `UserMessage` + `AssistantMessage` + `AssistantTurn`
- [x] Establish three-column layout in `ManagedChatPage` (left sidebar, chat area, right panel
  slot) — right slot renders `null` until Phase CHAT-03; no structural refactor needed later
- [x] Add `TogglePanelButton` atom to the chat header (wires to `rightPanelOpen: boolean` state)
- [x] Map SSE events to `ConversationMessage` state (replace current `Turn[]` grouping model)
- [x] Normalise history-loaded messages (from runtime `messages_url_template`) to `ConversationMessage[]`;
  handle `hitl_request` (`HitlRequestPart`) and `hitl_response` (`HitlResponsePart`) channels as
  main-conversation rows (not trace entries); read sources from `assistant/final` row `metadata.sources`
- [x] Run `make format` (Prettier) + `tsc --noEmit` on frontend — both pass (frontend has no `make code-quality` target)

> **UX refinements** for all implemented components are tracked separately in
> [`docs/ux/COMPONENT-UX.md`](../ux/COMPONENT-UX.md). Implementation tasks here track
> functional completeness only.

---

### 1.8 Validation

> **Test agent:** `fred.github.test_assistant` — a no-LLM, no-MCP graph agent in `apps/fred-agents`
> that exercises all major SSE event types without any external service.
> Keyword-prefix routing: `echo` | `hitl choice` | `hitl text` | `trace` | `error` | `long`.
> Enroll it in a local pod and use `fred-agents-cli` or the managed chat UI to run each scenario.

- [ ] User messages appear right-aligned with `--surface-container-high` background
- [ ] Agent messages appear left-aligned with `--surface-container` background
- [ ] `StreamingCursor` visible during delta streaming, gone on `final`
- [ ] `ThoughtTrace` opens on first trace step, auto-closes on `final`
- [ ] `tool_call` + matching `tool_result` rendered as a single combo `TraceEntryRow`
- [ ] Combo row shows `pending` chip while result absent; switches to `ok`/`error` on result
- [ ] Solo `thought`/`plan`/`observation` entries render with channel badge and preview text
- [ ] Primary text shows latency + source count summary when available from result metadata
- [ ] Detail icon opens `TraceDetailDrawer` with Monaco JSON payload for the selected entry
- [ ] Drawer theme follows MUI palette mode (`vs` / `vs-dark`)
- [ ] `SourcesPanel` appears below final message when `sources` non-empty
- [ ] `ChatInputBar` is disabled (send button + textarea) while streaming
- [ ] Existing HITL flow (`HitlPrompt`) is unaffected
- [ ] History loaded from runtime renders identically to streamed messages
- [x] `hitl_request` history rows render as read-only choice cards (question + labelled options, not clickable)
- [x] `hitl_response` history rows render as right-aligned user bubbles showing the selected label
- [x] Sources from history (`assistant/final` row `metadata.sources`) populate `SourcesPanel` correctly
- [ ] No regressions in `ChatList` sidebar session links

---

## 2 Phase CHAT-02 — Markdown & Content Rendering

### 2.1 Goal

Render assistant message content with safe markdown. User messages remain plain
text.

---

### 2.2 Scope

- Markdown in `AssistantMessage` only.
- Library decision: evaluate `react-markdown` (already a transitive dep?) vs
  lightweight alternative. Document choice in this backlog before implementing.
- Inline `SourceBadge` markers `[N]` must survive markdown parsing — implement
  as a rehype/remark plugin or post-render injection.
- Code blocks get monospace font and a copy button (atom reuse or new
  `CodeBlock` molecule).
- No HTML passthrough — `allowedElements` whitelist only.

---

### 2.2 Library Decision

**`react-markdown` ^9.1.0** — already in `package.json` as a direct dependency.
Plugins used: `remark-gfm` (GFM tables, strikethrough, task lists), `rehype-sanitize`
(default schema, extended to allow `sup[data-n]` for citation badges).
`rehype-raw` is intentionally **not** used — no arbitrary HTML passthrough.
Citation injection is handled via a custom `rehypeCitations` rehype plugin (inline, no new
dep) that converts `[N]` text patterns to `<sup class="fred-cite" data-n="N">` hast
elements before sanitization.

### 2.3 Tasks

- [x] Audit whether `react-markdown` is already in `package.json` — yes, `^9.1.0`
- [x] Decide and document markdown library choice — `react-markdown` + `remark-gfm` + `rehype-sanitize` (see §2.2)
- [x] Implement `MarkdownRenderer` molecule with safe subset — `molecules/MarkdownRenderer/MarkdownRenderer.tsx`
- [x] Implement `SourceBadge` injection inside rendered markdown — `rehypeCitations` plugin in `MarkdownRenderer`, renders `SourceBadge` atom via `components.sup`
- [x] Implement `CodeBlock` molecule (monospace + copy button) — `molecules/CodeBlock/CodeBlock.tsx`
- [x] Replace plain text in `AssistantMessage` with `MarkdownRenderer`
- [x] Run `make format` (Prettier) + `tsc --noEmit` on frontend — both pass (4 pre-existing errors in `config.tsx`, zero in new/modified files)

---

### 2.4 Validation

- [ ] Bold, italic, lists, headings render correctly
- [ ] Code blocks render monospace with copy button
- [ ] Inline `[N]` markers render as `SourceBadge`, not as literal brackets
- [ ] No raw HTML injection possible
- [ ] User message bubbles still render plain text

---

## 3 Phase CHAT-03 — Agent Options Panel & Debug Tools

### 3.1 Goal

Fill the right-side `AgentOptionsPanel` slot established in Phase CHAT-01 with two concerns:

1. **Agent-specific options** — configurable parameters declared by the agent and rendered
   generically by the frontend (folder/subfolder scope for RAG, model override if exposed, etc.)
2. **Debug tools** — admin-gated shortcuts to investigate the current session without
   polluting the main chat conversation

The main `ChatMessagesArea` must remain focused on the business exchange. Debug output
always opens in a separate `DebugDrawer`.

---

### 3.2 Core Design Rules

- `ChatMessagesArea` never contains debug output — ever.
- Debug results always render in `DebugDrawer`, which is a separate DOM subtree.
- Agent options are described by the agent via typed `ExecutionPreparation`
  contract data (`effective_chat_options` now, richer descriptors later) — they
  are never hardcoded per agent name or ID in frontend code.
- Debug tools are visible only when `FrontendBootstrap.permissions` includes `debug_tools`.
  The section is fully absent when the permission is missing — no placeholder shown.
- The panel is collapsible. The toggle button lives in the chat header (`TogglePanelButton`).
- All components use design tokens only. No hardcoded colours or spacing. This makes
  future Figma revisions structural changes only, not paint-over work.

---

### 3.3 Component Map

#### Atoms

| Component | Path | Purpose |
|---|---|---|
| `TogglePanelButton` | `atoms/TogglePanelButton/` | Header icon button that shows/hides the right panel |
| `OptionChip` | `atoms/OptionChip/` | Small interactive chip for enum-type agent options |
| `DebugActionButton` | `atoms/DebugActionButton/` | Icon + label button for one debug action; has loading state |

#### Molecules

| Component | Path | Purpose |
|---|---|---|
| `AgentOptionSection` | `molecules/AgentOptionsPanel/AgentOptionSection/` | Renders one named group of controls from an `AgentOptionDescriptor` |
| `FolderScopeSelector` | `molecules/AgentOptionsPanel/FolderScopeSelector/` | Breadcrumb-style folder/subfolder picker — first concrete option kind |
| `DebugToolsSection` | `molecules/AgentOptionsPanel/DebugToolsSection/` | Admin-only block with the three `DebugActionButton` items |
| `DebugDrawer` | `molecules/DebugDrawer/` | Slide-in drawer for debug output; body slot accepts any renderer |

#### Organism

`AgentOptionsPanel` (already declared in §1.3): header, list of `AgentOptionSection`, optional
`DebugToolsSection`.

---

### 3.4 Agent Options Contract

Agent-specific options are described by an `AgentOptionDescriptor` union. The frontend
renders options generically — it must never branch on agent name or instance ID.

```typescript
// Discriminated union — add new kinds here as agents declare them
type AgentOptionDescriptor =
  | FolderScopeDescriptor
  // | ModelOverrideDescriptor  ← future
  // | TemperatureDescriptor    ← future

type FolderScopeDescriptor = {
  kind: 'folder_scope'
  label: string
  multiSelect: boolean
  options: { id: string; label: string; parentId?: string }[]
}
```

**Source:** phase 1 now ships a typed `ExecutionPreparation.effective_chat_options`
surface from control-plane for the current search/attachment affordances. Richer
descriptor unions can still arrive via `ExecutionPreparation` later for
frontend-generic rendering. Unknown future `kind` values should still be
silently skipped (forward-compatible).

**Effect:** selected option values are passed to `RuntimeExecuteRequest` (in `runtime_context`
or a dedicated `options` field — to be defined with the backend). Until the wire protocol is
defined, the selection is held in local state and logged.

---

### 3.5 Debug Tools

Three tools, all gated by `debug_tools` permission.

| Tool | `DebugActionButton` label | `DebugDrawer` content |
|---|---|---|
| Log Genius | "Investigate with Log Genius" | Markdown result of a log analysis call |
| Session performance | "Session performance" | KPI table: exchange, latency, LLM latency, tool count, tokens |
| Response detail | "Raw response detail" | Monaco JSON viewer of the full `ChatMessage[]` for the session |

#### Log Genius

- Calls an external log investigation agent or API (endpoint TBD — stub the contract here
  when the team defines it; use a typed placeholder in the meantime).
- `DebugDrawer` shows a spinner while the call is in-flight, the markdown result on completion,
  and a typed error state on failure.

#### Session Performance

- Fetches structured KPI events for the current `session_id` (Phase 7 —
  `agent.turn_completed` and `agent.llm_call` rows).
- Renders a compact table: `exchange_id`, `total_latency_ms`, `llm_latency_ms`,
  `tool_count`, `model_name`, `input_tokens`, `output_tokens`.
- Falls back to "No KPI data available for this session" while Phase 7 KPI store is not
  yet populated.

#### Response Detail

- Fetches `GET {messages_url_template}` (already used by `ManagedChatPage` for history
  loading — reuse the same call, no new endpoint).
- Renders the raw `ChatMessage[]` in a Monaco JSON viewer inside `DebugDrawer`, using the
  same Monaco configuration as `TraceDetailDrawer` (read-only, wordWrap, theme-aware).
- Useful during agent development to inspect every channel, rank, and part without
  filtering.

---

### 3.6 DebugDrawer Contract

- Slides in from the right (width ≥ 720 px; full screen on mobile via MUI Drawer `anchor="right"`).
- Layered above `AgentOptionsPanel` — both can coexist in the layout tree.
- Header: tool label + `session_id` (truncated to 8 chars) + close button.
- Body: tool-specific renderer (markdown / table / Monaco).
- `ManagedChatPage` owns the drawer state:
  ```typescript
  type DebugTool = 'log_genius' | 'performance' | 'response_detail'
  const [debugDrawer, setDebugDrawer] = useState<{ open: boolean; tool: DebugTool | null }>
  ```
- Closing: × button or MUI `onClose` (backdrop click).

---

### 3.7 Three-Column Layout (reference)

```
┌─ Left Sidebar ──┬──── Chat Area ────────────────────────────┬─ Right Panel (collapsible) ──┐
│ ChatList        │                                           │                              │
│                 │  ChatMessagesArea (scrollable)            │  AgentOptionsPanel            │
│                 │    AssistantTurn × N                      │  ├─ AgentOptionSection(s)    │
│                 │      ThoughtTrace                    │  │   FolderScopeSelector …   │
│                 │      AssistantMessage                     │  └─ DebugToolsSection        │
│                 │      SourcesPanel                         │     [admin only]             │
│                 │    UserMessage × N                        │     DebugActionButton × 3    │
│                 │                                           │                              │
│                 │  ChatInputBar                             │  (DebugDrawer overlaid)       │
└─────────────────┴───────────────────────────────────────────┴──────────────────────────────┘
```

The toggle (`TogglePanelButton`) lives in the chat header. On viewport `< sm` the right
panel behaviour (bottom sheet vs hidden) is deferred to Figma confirmation.

---

### 3.8 Chat Header Design

The chat header is the primary identity surface of the conversation. It must answer in
plain language: **"who am I talking to, and in what context?"**

Required header content:

| Element | Source | Rule |
|---|---|---|
| Agent display name | `ManagedAgentInstanceSummary.display_name` | Prominent, always visible — never the `agent_instance_id` |
| Team context | `FrontendBootstrap.active_team.display_name` | Secondary, e.g. "Personal" or the team name |
| Session title | `SessionMetadata.title` (control-plane) | Editable inline; defaults to a generated label if absent |
| `TogglePanelButton` | local state | Shows/hides the right options panel |
| "New chat" button | local action | Clears state, generates new `session_id` |

**Agent switching — explicitly deferred.**
Switching the active agent within an open conversation is not in scope for Phase CHAT-03.
The entry point for changing agents remains the team agents page (`TeamAgentsPage`).
A future phase may add an in-chat agent picker — the header slot is reserved for it,
but no implementation is started now.

Additional per-message controls:

- Copy button on `AssistantMessage` (copies markdown as plain text)

---

### 3.9 Tasks

#### Layout

- [x] Confirm three-column layout slot is properly wired in `ManagedChatPage` (from Phase CHAT-01)
- [x] Mount `AgentOptionsPanel` in the right slot; verify panel open/close does not reflow
  `ChatMessagesArea`

#### Agent Options

- [ ] Define `AgentOptionDescriptor` TypeScript union (start with `FolderScopeDescriptor`)
- [ ] Create `OptionChip` atom
- [ ] Create `FolderScopeSelector` molecule (breadcrumb folder picker from descriptor options)
- [ ] Create `AgentOptionSection` molecule (renders one descriptor group generically)
- [x] Create `AgentOptionsPanel` organism — `organisms/AgentOptionsPanel/`. Implements two
  concrete sections: **Knowledge Libraries** (team document-tag picker via
  `useListAllTagsKnowledgeFlowV1TagsGetQuery`; bound-library read-only mode when
  `boundLibraryIds` prop is set) and **Search options** (policy: strict/hybrid/semantic;
  scope: corpus/hybrid/general — controlled pill groups backed by `ButtonGroupItem`).
- [ ] Replace the current local stub/hardcoded defaults with
  `ExecutionPreparation.effective_chat_options`, then layer richer descriptors on
  top when the backend exposes them
- [x] Hold selected option values (`selectedLibraryIds`, `searchPolicy`, `ragScope`) in
  `ManagedChatPage` state; pass as `RuntimeContext` to `send()` on every turn.

#### Debug Tools

- [ ] Add `debug_tools` permission check from `FrontendBootstrap.permissions`
- [ ] Create `DebugActionButton` atom (icon + label + loading spinner state)
- [ ] Create `DebugToolsSection` molecule (three buttons, visible only with permission)
- [ ] Create `DebugDrawer` molecule (slide-in, header, body slot, open/close state)
- [ ] Implement "Response detail": fetch `messages_url_template`, render in Monaco inside drawer
- [ ] Implement "Session performance": fetch KPI by `session_id`, render table; stub fallback
- [ ] Implement "Log Genius": define call stub, render markdown result; loading + error states
- [ ] Wire `debugDrawer` open/close state in `ManagedChatPage`

#### Header Controls

- [x] Add inline-editable session title to chat header — `SessionTitleEditor` molecule, rendered in `ManagedChatPage` top bar (2026-05-24)
- [x] Wire `PATCH /teams/{team_id}/sessions/{session_id}` for title save — `commitTitle` in `useManagedChat`, uses `refreshSession` mutation (2026-05-24)
- [ ] Add "New chat" button (clears state, new `session_id`)
- [ ] Add per-message copy button on `AssistantMessage`

---

### 3.10 Validation

- [ ] Toggling the right panel does not reflow or scroll `ChatMessagesArea`
- [ ] ~~`AgentOptionsPanel` renders `null` cleanly when no options and no `debug_tools` permission~~ **Superseded (2026-05-24)** — routine controls moved to `ComposerSettingsControls`; debug tools will use `InlineDrawer`
- [ ] `DebugToolsSection` is fully absent for users without `debug_tools` permission
- [ ] Opening a debug drawer injects nothing into `ChatMessagesArea`
- [ ] "Response detail" drawer shows raw `ChatMessage[]` in Monaco for the active session
- [ ] "Session performance" drawer shows a table or graceful "no KPI data" fallback
- [ ] "Log Genius" drawer shows spinner while in-flight, result on completion
- [ ] ~~`DebugDrawer` and `AgentOptionsPanel` coexist without z-index conflicts~~ **Superseded (2026-05-24)** — `InlineDrawer` replaces `AgentOptionsPanel` for debug; verify `InlineDrawer` z-index does not conflict with `ComposerSettingsControls` popovers
- [ ] All new components use design tokens only — no hardcoded colours or spacing
- [ ] `make code-quality` passes on the frontend

---

## 4 Phase CHAT-04 — Advanced Message Parts (deferred)

Features deferred until Phases CHAT-01–CHAT-03 are stable:

- Geo/Map rendering (`GeoPart`)
- Document download/view links (`LinkPart`)
- Token usage display
- Message expand/collapse for long messages
- Thumbs feedback per message
- PDF viewer integration

---

## 5 Phase CHAT-05 — Design System Enrichment & Enterprise UX Refonte

> **RFC:** [`docs/swift/rfc/CHAT-UI-REFONTE-RFC.md`](../rfc/CHAT-UI-REFONTE-RFC.md)  
> **Design validation:** 5-step process, each step requires explicit approval before the next begins.  
> **Rule:** no component is written before Step 4 is validated. Quality of decomposition over speed of delivery.

---

### 5.1 Goal

Enrich the design system with 5 atoms and 7 molecules that are reusable outside the chat
feature, then decompose `ManagedChatPage` into a thin composition of organisms.

A successful outcome means: a new developer reads the code and understands the structure
in 10 minutes; the DS has grown by 5–10 named primitives; the page root is under 80 lines.

---

### 5.2 Design validation steps

- [ ] **Step 1 — Component catalog** — atoms and molecules to create or reuse, with generic
  names and justification. *(validated 2026-05-14 — see RFC §4)*
- [x] **Step 2 — Organism signatures** — TypeScript prop/callback interfaces for each organism *(validated 2026-05-14)*
- [x] **Step 3 — Data model** — `Conversation`, `Message` (tree), `Source`, `UserCapabilities`,
  `ConversationSettings` *(validated 2026-05-14 — `src/rework/types/conversation.ts`)*
- [x] **Step 4 — Page composition** — skeleton of `ManagedChatPage` showing organism assembly
  and hooks, under 80 lines *(validated 2026-05-14)*
- [x] **Step 5 — Implementation order** — atoms → molecules → organisms, each step demonstrable *(validated 2026-05-14)*

---

### 5.3 New atoms (Step 1 validated)

- [x] `NumberedChip` — `atoms/NumberedChip/` — inline citation chip `[N]`, cliquable or static
- [x] `AccentBar` — `atoms/AccentBar/` — left-border block wrapper, `color` token param
- [x] `RestrictedBadge` — `atoms/RestrictedBadge/` — lock icon + short label, non-interactive
- [x] `FaviconIcon` — `atoms/FaviconIcon/` — favicon from URL with fallback to generic icon
- [x] `IndicatorDot` — `atoms/IndicatorDot/` — coloured status dot, optional pulse animation

### 5.4 New molecules (Step 1 validated)

- [x] `CollapsibleBlock` — `molecules/CollapsibleBlock/` — generic expand/collapse inline section
- [x] `SourceCard` — `molecules/SourceCard/` — `FaviconIcon` + title + domain + optional `RestrictedBadge`
- [x] `HorizontalScrollRow` — `molecules/HorizontalScrollRow/` — horizontal scroll + gradient edge fade
- [x] `ContextualPicker` — `molecules/ContextualPicker/` — trigger button showing current value + popover
- [x] `ActionBar` — `molecules/ActionBar/` — row of icon-actions, visible on parent hover
- [x] `InlineDrawer` — `molecules/InlineDrawer/` — non-blocking right-side panel
- [x] `RichInputField` — `molecules/RichInputField/` — auto-grow textarea with `leftSlot`, `rightSlot`, `topSlot`

### 5.5 Refactors (Step 1 validated)

- [x] `ChatInputBar` → `RichInputField` migration: `ManagedChatPage` now uses `RichInputField`; `ChatInputBar` kept for legacy callers until full migration
- [x] `SourcesPanel` → `HorizontalScrollRow` + `SourceCard` migration: `AssistantTurn` now uses new components internally; `SourcesPanel` kept for legacy callers
- [ ] `ThoughtTrace` — audit: if internals reference chat concepts, extract generic parts

### 5.6 Organisms (pending Step 2 validation)

_Signatures to be defined in Step 2._

- [x] `ConversationHeader` — agent name + `SessionTitleEditor` + actions — `organisms/ConversationHeader/`
- [x] `SessionTitleEditor` — inline editable title, extracted from `ManagedChatPage` — `molecules/SessionTitleEditor/`
- [x] `UserTurn` — `UserMessage` + `ActionBar` (copy, edit) — `organisms/UserTurn/`
- [x] `AssistantTurn` — refactored: `CollapsibleBlock` wrapping `ThoughtTrace` + `HorizontalScrollRow` of `SourceCard`s + `ActionBar` — `organisms/AssistantTurn/`
- [x] `ConversationThread` — maps `ThreadMessage[]` to `UserTurn` / `AssistantTurn` / `HitlPrompt` — page-local `pages/ManagedChatPage/ConversationThread/` (moved from `organisms/` 2026-05-24 to fix hierarchy)
- [ ] Sidebar — history grouped by date, fixed-bottom sections (Libraries, Files, Agents, Settings)

### 5.7 Hooks and utilities (pending Step 3 validation)

- [x] `useSessionManager` — session create, bind, title sync, title PATCH (extracted from page) — `core/hooks/useSessionManager.ts`
- [x] `useUserCapabilities` — single source of truth for `canDebug`, `canManageLibraries`, etc. — `core/hooks/useUserCapabilities.ts`
- [x] `conversationUtils.ts` — `buildConversation`, `activeThread`, `hitToSource`, `chatMessagesToMessage` — `utils/conversationUtils.ts`

### 5.8 Page refactor (pending Step 4 validation)

- [x] `ManagedChatPage` — reduced to 80 lines (66 code + 14 license header); `useManagedChat` hook extracts all business logic

### 5.9 UX correction — routine options stay in the composer

The CHAT-05 layout originally allowed `AgentOptionsPanel` to expose libraries,
search policy, and RAG scope in a full-height right overlay. UX review on
2026-05-24 found that this makes routine turn settings compete with the
assistant reply body.

Target correction:

- [x] Replace the routine `AgentOptionsPanel` interaction with compact
  composer-adjacent setting chips — `SettingChip` atom + `ComposerSettingsControls` organism (2026-05-24)
- [x] Render composer setting chips in a dedicated row above the textarea via `topSlot`
  of `RichInputField`; textarea never compressed (2026-05-24)
- [x] Use anchored popovers for search policy and RAG scope selection (2026-05-24)
- [x] Use an anchored multi-select popover for library selection, with selected
  libraries summarized as count chip (2026-05-24)
- [x] Popovers support Escape, click-outside close, and valid ARIA semantics
  (`role="dialog"`, `role="group"`) (2026-05-24)
- [x] Bound libraries: inspectable in a read-only popover (chip always clickable) (2026-05-24)
- [x] Right-side drawers removed for routine options; right panel gone from `useManagedChat` (2026-05-24)
- [x] Active policy/scope/library count visible in chips while user reads/types (2026-05-24)

---

## 6 Known gaps — requires backend work before unblocking frontend

These items are **not** implementation gaps in the frontend — the UI is ready to
display the data once the backend provides it. Each is blocked on a specific API
change.

| Gap | What the UI does today | What's needed | Blocking |
|---|---|---|---|
| Session title | ~~Shows `abc12345…` (first 8 chars of UUID) when `title` is null~~ **Fixed.** | `ManagedChatPage` now passes `title: text.slice(0, 120)` (first user message) in the `CreateSessionRequest`. `ChatList` already displayed `session.title` with UUID fallback — no change needed there. LLM-generated summaries remain a future enhancement. | Done |
| Agent card — whole-card click | Only the "Start Chat" button at the bottom is clickable. The develop branch had the entire card as a `<Link>` with `e.preventDefault()` on action buttons. | ~~Restore card as `<Link>` for enabled instances — frontend only, no backend change.~~ **Fixed.** | ~~None~~ Done |
| Agent settings / edit | ~~Button visible but disabled on agent card~~ **Fixed.** | `EnrollManagedAgentModal` renamed to `AgentFormModal`, pre-fills from instance, dispatches PATCH via `usePatchTeamAgentInstance…` mutation. Frozen-snapshot policy in place (no re-merge with current template). | ~~Backend + frontend~~ Done |
| Agent tuning fields at creation | ~~Modal only captures `display_name` + `description`~~ **Fixed.** | `AgentFormModal` fully refactored per RFC. `TemplateBrowser` card grid replaces raw `<select>`. All field types implemented: string, number/integer, boolean (`SwitchRow`), enum, secret, url, prompt/multiline. Field grouping via `ui.group`. Inline validation. Edit mode context bar + metadata footer. MCP tools read-only section. | ~~Backend + frontend~~ Done |
| `mcp_servers` pass-through | Control plane dropped `available_mcp_servers` from runtime's `/agents/templates` response. | **Fixed.** `ManagedMcpServerRef` extended with `display_name` + `config_fields`. `AgentTemplateSummary` now includes `mcp_servers`. Runtime's `available_mcp_servers` mapped to `ManagedMcpServerRef` with `display_name` enriched from catalog. Frontend renders read-only MCP tools section. | ~~Backend + frontend~~ Done |
| Orphaned components | `AgentCreateEditModal/KfVectorSearchForm` and `SwitchRow` exist. `KfVectorSearchForm` imports from `agenticOpenApi` (legacy). `SwitchRow` now re-used by `TuningFieldRenderer`. | `KfVectorSearchForm` is still used by old-tree `AgentToolsSelection` via `TOOL_PARAMS_REGISTRY` — cannot delete until that old component is migrated. | None — defer until `AgentToolsSelection` migrates |
| File attachments | No file attachment UI in `ManagedChatPage`. Old UI used `POST /agentic/v1/chatbot/upload` (deprecated). | Agreed direction: attachments upload directly to knowledge-flow. Spec needed: endpoint selection (new KF upload route vs. existing), returned document UID flow into `RuntimeContext.selected_document_uids`, UI as paperclip icon in `ChatInputBar`. | Spec + KF endpoint decision |
| Agent-library hard binding indicator | `ComposerSettingsControls` library chip is always interactive. When an agent's MCP server declares `document_library_tags_ids`, the chip should switch to read-only (lock icon) showing the bound libraries. | Backend contract is now in place: `ManagedAgentInstanceSummary.mcp_config_values` is exposed and `prepare-execution` resolves typed `effective_chat_options`. **Remaining:** frontend must derive/read the bound-library state from that data instead of leaving the chip always interactive. (`AgentOptionsPanel` retired 2026-05-24 — this gap now targets `ComposerSettingsControls`.) | Frontend only |
| `chat_options.*` in wrong form tab | Library picker, search policy, RAG scope appear in "Settings" tab of `AgentFormBody`. They belong in the "Tools" tab, rendered beneath the KF search server checkbox when that server is active. | **Partially fixed (2026-05-06):** `McpServerCard` now reads/writes per-server `configValues` (not flat `tuningFieldValues`); `AgentFormBody` passes server-scoped slices; `AgentFormModal` stores `mcpConfigValues` separately and tri-state selection is preserved (`[]` ≠ `null`); `TeamAgentsPage` forwards `mcp_config_values` to create/update API calls. `ManagedChatPage` now consumes `effective_chat_options` from `useChatSse` and passes it to `ComposerSettingsControls` which gates its sections. **Remaining:** move MCP `config_fields` controls to the "Tools" tab (currently rendered inline inside `McpServerCard` in the Tools tab — layout is correct, but they are not yet in a dedicated sub-section per server). | Frontend only |
| Stream abort — backend gap | Frontend abort is fully wired: `useChatSse.abort()` closes the `AbortController`, `waitResponse` resets to false, `ManagedChatPage` surfaces the stop button via `RichInputField.onInterrupt`. | **Backend has no abort endpoint.** After the client disconnects, the agent/LLM execution continues to completion. The full response may appear in session history on next load. Partial streaming message is not cleaned up in the UI on abort. Needed: (1) `POST /control-plane/v1/teams/{team_id}/sessions/{session_id}/abort` or equivalent cancel signal on the runtime side; (2) frontend cleanup of the partial assistant message bubble on abort. | Backend (no abort endpoint in `agent_app.py`) |

---

## 7 Phase CHAT-06 — test_assistant rich content scenarios

> **ID:** `CHAT-06` — `docs/swift/data/id-legend.yaml`
> **Scope:** backend only — `apps/fred-agents/fred_agents/test_assistant/`
> **Purpose:** make `fred.github.test_assistant` a complete rendering test harness for the chat UI,
> covering every content type the new `MarkdownRenderer` must handle without requiring a live LLM.

---

### 7.1 Current gaps

The test agent covers SSE events (streaming, HITL, error, sources) and all FieldSpec form types.
It does **not** exercise rich content rendering. No existing scenario produces:

| Content type | Needed for |
|---|---|
| Fenced code block with language (`python`, `bash`, …) | Syntax highlighting |
| Mermaid diagram | `Mermaid` renderer |
| GFM table | Table rendering |
| GeoJSON `FeatureCollection` | Leaflet map renderer |
| KaTeX inline math | Math rendering |
| KaTeX block math | Math rendering |
| `:::details` collapsible | remark-directive plugin |

---

### 7.2 New scenario: `markdown`

Add a `markdown_step` triggered by the keyword prefix `markdown`.
The step emits a single static assistant message that contains one well-formed
example of each content type listed in §7.1.

**Content requirements per block:**

| Block | Minimum content |
|---|---|
| Code | A short Python function (5–8 lines), fenced ` ```python ` |
| Mermaid | A 4-node flowchart (`graph TD`), fenced ` ```mermaid ` |
| Table | 3 columns × 3 data rows, GFM pipe syntax |
| GeoJSON | Inline JSON literal: `FeatureCollection` with 2 `Point` features and 1 `Polygon` |
| Math inline | One expression rendered with `$…$` |
| Math block | One expression rendered with `$$…$$` |
| Details | One `:::details[Title]` block wrapping a short paragraph |

**Routing wiring:**
- `dispatch_step`: add `elif text.startswith("markdown"): scenario = "markdown"`
- `graph_agent.py` workflow: add node `"markdown": markdown_step` and edge `"markdown": "finalize"`
- `_SCENARIO_TABLE` in `fallback_step`: add the `markdown` row

---

### 7.3 Tasks

- [x] Add `markdown_step` to `graph_steps.py` with static rich content payload
- [x] Wire `markdown` route in `dispatch_step`
- [x] Register node + edge in `GraphWorkflow` in `graph_agent.py`
- [x] Add `markdown` row to `_SCENARIO_TABLE` fallback menu
- [x] Run `make code-quality` in `apps/fred-agents` — passes (0 errors, 0 warnings)
- [ ] Manual verification: send `markdown` to the agent, confirm all 7 content blocks appear in the reply

---

### 7.4 Acceptance criteria

- Sending `markdown` to `fred.github.test_assistant` produces a reply containing all 7 content types
- No LLM or MCP server required
- `make code-quality` passes in `apps/fred-agents`
- `_SCENARIO_TABLE` in the fallback help menu includes the `markdown` row

---

## 6 Progress

| Phase | Status | Notes |
|---|---|---|
| AgentFormModal refactor | ✅ Done (2026-04-28) | `TemplateBrowser` + `TemplateCard` + `TuningFieldRenderer` + `AgentFormBody` extracted; all field types; grouping; MCP read-only section; edit context bar + metadata footer. RFC: `docs/rfc/AGENT-INSTANCE-FORM-RFC.md`. |
| CHAT-01 – Architecture & layout | ✅ Done (2026-04-27) | All atoms + molecules + organisms created; three-column layout; `ConversationMessage` state model + `toConversationMessages`; HITL history channels (hitl_request frozen card, hitl_response user bubble); sources from `assistant/final` metadata. Prettier + `tsc` pass. |
| CHAT-02 – Markdown & content | ✅ Done (2026-05-04) | `MarkdownRenderer` (react-markdown + remark-gfm + rehype-sanitize + rehypeCitations plugin); `CodeBlock` (monospace + copy); `SourceBadge` atom; wired into `AssistantMessage`; `AssistantTurn` threads `onSourceClick` → `SourcesPanel` activeIndex highlight. Prettier + `tsc` pass. |
| Code quality audit | ✅ Done (2026-05-04) | MUI removed from `Breadcrumb` (→ `Icon` atom) and `MainLayout` (`CssBaseline` dropped); `Menu` moved from `organisms/` → `molecules/`; hex fallbacks removed from `HitlPrompt.module.css`; Apache 2.0 license headers added to all 51 rework `.tsx` files. `KfVectorSearchForm` kept (still used by old-tree `AgentToolsSelection` via `TOOL_PARAMS_REGISTRY`). |
| CHAT-03 – Agent options & debug tools | 🔄 In progress | `AgentOptionsPanel` organism done (2026-05-06): library picker + search-policy/scope controls wired to `RuntimeContext`. Backend contract freeze done (2026-05-06). Frontend wiring done (2026-05-06): `mcp_config_values` correctly separated from `tuning_field_values` in form + API calls; tri-state MCP selection preserved through form round-trip; `useChatSse` exposes `effectiveChatOptions`; `AgentOptionsPanel` gates sections on `options` prop; `ManagedChatPage` syncs search defaults from agent config. **Routine controls retired (2026-05-24):** library picker, search policy, RAG scope moved to `ComposerSettingsControls` chips (CHAT-05). Remaining: debug tools section (`DebugDrawer` via `InlineDrawer`). |
| CHAT-04 – Advanced parts | Deferred | After CHAT-03 |
| CHAT-05 – DS enrichment & refonte | 🔄 In progress | Steps 1–5 validated (2026-05-14). Waves 0–8 implemented (2026-05-18): types, 5 atoms, 8 molecules, 6 organisms, 4 hooks/utils. `ManagedChatPage` reduced to 80 lines. MarkdownRenderer extended (2026-05-21): `remark-math`, `rehype-katex`, `remark-directive`, `MermaidBlock`, `hr` suppression. Rendering spec RFC: `docs/swift/rfc/CHAT-RENDERING-SPEC.md`. Remaining: `ConversationSidebar`, `SourceDetailDrawer`, `DebugDrawer`. |
| CHAT-06 – test_assistant rich content | ✅ Done (2026-05-21) | Backend: `markdown_step` in `apps/fred-agents` with 7 content types (code, mermaid, table, GeoJSON, math inline+block, details). Manual live verification pending pod. |

> **UX review status** (functional ≠ UX-validated): see [`docs/ux/COMPONENT-UX.md`](../ux/COMPONENT-UX.md).
