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

| Component         | Path                     | Purpose                                                     |
| ----------------- | ------------------------ | ----------------------------------------------------------- |
| `MessageBubble`   | `atoms/MessageBubble/`   | Styled container: role variant, padding, radius, max-width  |
| `StreamingCursor` | `atoms/StreamingCursor/` | Blinking inline cursor visible during delta streaming       |
| `ToolBadge`       | `atoms/ToolBadge/`       | Chip showing tool name + status (running / success / error) |
| `SourceBadge`     | `atoms/SourceBadge/`     | Inline superscript `[N]` linking to nth source card         |

#### Molecules

| Component           | Path                                        | Purpose                                                                                            |
| ------------------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `UserMessage`       | `molecules/UserMessage/`                    | Right-aligned bubble + timestamp                                                                   |
| `AssistantMessage`  | `molecules/AssistantMessage/`               | Left-aligned bubble, streaming cursor, plain text (markdown deferred)                              |
| `ThoughtTrace`      | `molecules/ThoughtTrace/`                   | Collapsible reasoning trace — entry grouping, status chips, detail drawer (see §1.6 for full spec) |
| `TraceEntryRow`     | `molecules/ThoughtTrace/TraceEntryRow/`     | One step row: index, status chip, channel/node/tool badges, primary text, detail-open trigger      |
| `TraceDetailDrawer` | `molecules/ThoughtTrace/TraceDetailDrawer/` | Slide-in Monaco JSON drawer for full step or call+result payload; theme-aware                      |
| `SourceCard`        | `molecules/SourcesPanel/SourceCard/`        | One citation: index, title, score, excerpt                                                         |
| `SourcesPanel`      | `molecules/SourcesPanel/`                   | List of SourceCards, visible after `final` event                                                   |
| `ChatInputBar`      | `molecules/ChatInputBar/`                   | TextArea atom + send IconButton, disabled during streaming                                         |

#### Organisms

| Component           | Path                           | Purpose                                                                                                                                                                                                                                                                                                                        |
| ------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ChatMessagesArea`  | `organisms/ChatMessagesArea/`  | Scrollable message list, auto-scroll, empty state                                                                                                                                                                                                                                                                              |
| `AssistantTurn`     | `organisms/AssistantTurn/`     | Groups ThoughtTrace + AssistantMessage + SourcesPanel for one exchange                                                                                                                                                                                                                                                         |
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
  id: string; // exchange_id + ":" + rank
  role: "user" | "assistant";
  text: string;
  isStreaming: boolean;
  thinkingSteps: ThinkingStep[];
  sources: VectorSearchHit[];
  statusText?: string; // from status events, cleared on final
  error?: string; // from node_error events
}

type ThinkingStep =
  | {
      kind: "tool_call";
      callId: string;
      name: string;
      args: Record<string, unknown>;
      status: "running" | "done" | "error";
    }
  | {
      kind: "tool_result";
      callId: string;
      ok: boolean;
      latencyMs?: number;
      content: string;
    };
```

---

### 1.5 SSE Event → UI Mapping

| Runtime event     | State mutation                                                                                                         | Visible effect                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `assistant_delta` | Append delta to current assistant message                                                                              | Text grows, `StreamingCursor` pulses                                    |
| `tool_call`       | Push `ThinkingStep {kind:'tool_call', status:'running'}`                                                               | `ThoughtTrace` appears (open by default), `ToolCallStep` with spinner   |
| `tool_result`     | Match `call_id`, update to `status:'done'` or `status:'error'`, add `tool_result` step                                 | `ToolCallStep` → `ToolResultStep`                                       |
| `final`           | Replace text with final content, attach sources, clear `isStreaming`                                                   | `StreamingCursor` disappears, `SourcesPanel` appears if sources present |
| `status`          | Set `statusText` on current message                                                                                    | Italic status line below bubble                                         |
| `awaiting_human`  | Existing `HitlPrompt` path — unchanged                                                                                 | HITL inline prompt                                                      |
| `node_error`      | Set `error` on current message                                                                                         | Error chip in bubble                                                    |
| `turn_persisted`  | Update `sessionId` in URL + call `PATCH /teams/{teamId}/sessions/{sessionId}` with `updated_at` to keep sidebar sorted | Silent — fire-and-forget, failure does not interrupt chat               |

#### HITL History Schema (fixed 2026-04-26)

When loading history from `messages_url_template`, HITL interactions appear as structured
`ChatMessage` rows rather than flat text — the runtime persists them this way since 2026-04-26.

| Channel         | Role     | Part type          | Content                                                                                |
| --------------- | -------- | ------------------ | -------------------------------------------------------------------------------------- |
| `hitl_request`  | `system` | `HitlRequestPart`  | Full gate definition: `question`, `choices[]{id, label}`, optional `stage` and `title` |
| `hitl_response` | `user`   | `HitlResponsePart` | User's selection: `choice_id` + optional `label`                                       |

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

**Reference implementation:** `apps/frontend/src/components/chatbot/ReasoningStepsAccordion.tsx` and
`ReasoningStepBadge.tsx`. Port the logic and enrich the visual presentation for the rework
design system. Do not delete the legacy component until `ManagedChatPage` fully replaces the
old chat surface.

#### Entry grouping model

Steps are not rendered one-to-one from SSE events. They are first grouped into `TraceEntry`
objects before rendering:

```typescript
type TraceEntry =
  | { kind: "solo"; message: ChatMessage }
  | { kind: "combo"; call: ChatMessage; result?: ChatMessage };
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

| Field          | Source                                                |
| -------------- | ----------------------------------------------------- |
| Index          | Sequential position (1-based), fixed-width column     |
| Status chip    | `ok` / `error` / `pending` — see status table below   |
| Channel badge  | `message.channel` with underscores replaced by spaces |
| Node chip      | `extras.node` string when present                     |
| Task chip      | `extras.task` string when present and no node chip    |
| Tool name chip | `tool_call.name` for combo entries                    |
| Primary text   | Smart summary — see derivation rules below            |
| Detail button  | Opens `TraceDetailDrawer` for this entry              |

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

| Chip      | Condition                                                                               |
| --------- | --------------------------------------------------------------------------------------- |
| `ok`      | combo with `result.ok === true`; solo tool_result with `ok === true`                    |
| `error`   | combo with `result.ok === false`; solo tool_result with `ok === false`; channel `error` |
| `pending` | combo with no result yet (streaming)                                                    |
| _(none)_  | non-tool solo entries                                                                   |

#### Detail drawer (`TraceDetailDrawer`)

- slides in from the right (640 px, full screen on mobile)
- header: `channel · tool name · node/task` joined by `·`, with a close button
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

**Execution:** GitHub issue `#1730`

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

| Component           | Path                       | Purpose                                                     |
| ------------------- | -------------------------- | ----------------------------------------------------------- |
| `TogglePanelButton` | `atoms/TogglePanelButton/` | Header icon button that shows/hides the right panel         |
| `OptionChip`        | `atoms/OptionChip/`        | Small interactive chip for enum-type agent options          |
| `DebugActionButton` | `atoms/DebugActionButton/` | Icon + label button for one debug action; has loading state |

#### Molecules

| Component             | Path                                               | Purpose                                                               |
| --------------------- | -------------------------------------------------- | --------------------------------------------------------------------- |
| `AgentOptionSection`  | `molecules/AgentOptionsPanel/AgentOptionSection/`  | Renders one named group of controls from an `AgentOptionDescriptor`   |
| `FolderScopeSelector` | `molecules/AgentOptionsPanel/FolderScopeSelector/` | Breadcrumb-style folder/subfolder picker — first concrete option kind |
| `DebugToolsSection`   | `molecules/AgentOptionsPanel/DebugToolsSection/`   | Admin-only block with the three `DebugActionButton` items             |
| `DebugDrawer`         | `molecules/DebugDrawer/`                           | Slide-in drawer for debug output; body slot accepts any renderer      |

#### Organism

`AgentOptionsPanel` (already declared in §1.3): header, list of `AgentOptionSection`, optional
`DebugToolsSection`.

---

### 3.4 Agent Options Contract

Agent-specific options are described by an `AgentOptionDescriptor` union. The frontend
renders options generically — it must never branch on agent name or instance ID.

```typescript
// Discriminated union — add new kinds here as agents declare them
type AgentOptionDescriptor = FolderScopeDescriptor;
// | ModelOverrideDescriptor  ← future
// | TemperatureDescriptor    ← future

type FolderScopeDescriptor = {
  kind: "folder_scope";
  label: string;
  multiSelect: boolean;
  options: { id: string; label: string; parentId?: string }[];
};
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

| Tool                | `DebugActionButton` label     | `DebugDrawer` content                                          |
| ------------------- | ----------------------------- | -------------------------------------------------------------- |
| Log Genius          | "Investigate with Log Genius" | Markdown result of a log analysis call                         |
| Session performance | "Session performance"         | KPI table: exchange, latency, LLM latency, tool count, tokens  |
| Response detail     | "Raw response detail"         | Monaco JSON viewer of the full `ChatMessage[]` for the session |

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
  type DebugTool = "log_genius" | "performance" | "response_detail";
  const [debugDrawer, setDebugDrawer] = useState<{
    open: boolean;
    tool: DebugTool | null;
  }>;
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

| Element             | Source                                       | Rule                                                      |
| ------------------- | -------------------------------------------- | --------------------------------------------------------- |
| Agent display name  | `ManagedAgentInstanceSummary.display_name`   | Prominent, always visible — never the `agent_instance_id` |
| Team context        | `FrontendBootstrap.active_team.display_name` | Secondary, e.g. "Personal" or the team name               |
| Session title       | `SessionMetadata.title` (control-plane)      | Editable inline; defaults to a generated label if absent  |
| `TogglePanelButton` | local state                                  | Shows/hides the right options panel                       |
| "New chat" button   | local action                                 | Clears state, generates new `session_id`                  |

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

## 4 Phase CHAT-04 — Chat Attachments & Advanced Message Parts

**ID:** CHAT-04
**Status:** done — persistence + drawer extension delivered 2026-06-11
**Execution:** GitHub issue #1706
**Decision:** first slice is "Option A": composer upload UX only. MCP filesystem
hardening, SDK `ctx.fs`, and generated-output download links are tracked in FILES-01.
**Validation:** `apps/control-plane-backend make code-quality`, `apps/control-plane-backend make test`, `apps/knowledge-flow-backend make code-quality`, `apps/knowledge-flow-backend make test`, `apps/frontend make code-quality`, `apps/frontend make test`

### 4.1 Goal

Restore conversation attachments in `ManagedChatPage` using the Swift rework
composer architecture instead of porting the legacy `ChatBot.tsx` drawer.

The first slice uploads files to the existing Knowledge Flow user storage endpoint
and passes the returned workspace paths to the runtime context. It does not add
binary filesystem methods or download-link generation. Those are now tracked in
FILES-01 as part of the MCP filesystem-first target.

The completed slice now also persists attachments at conversation scope via
`session_attachments`, hydrates them back on session reload, exposes them in a
right-side drawer with markdown preview, and allows explicit deletion with
Knowledge Flow cleanup.

### 4.2 Scope — Option A

- [x] Add an attach-file `IconButton` in `RichInputField.leftSlot`
- [x] Upload selected files with `POST /knowledge-flow/v1/storage/user/upload`
- [x] Store uploaded-file view state locally in `ManagedChatPage` / `useManagedChat`
- [x] Render quiet attachment chips in the composer `topSlot`, alongside existing
      `ComposerSettingsControls` chips
- [x] Allow removing a pending attachment chip before sending the next turn
- [x] On send, include attached file paths in `RuntimeContext.attachments_markdown`
      so the agent receives explicit `/workspace/uploads/...` references
- [x] For image attachments, add a base64 conversation-context path: encode selected
      images client-side (with size/type guardrails) and include them in the turn context
      so multimodal-capable agents can consume the image content directly
- [x] Add drag-and-drop on the chat surface/composer for files; dropped files start the
      Knowledge Flow ingestion pipeline and surface scheduler task progress in the chat UI
- [x] Keep `include_session_scope` unchanged in this slice; session-scoped RAG
      ingestion remains a follow-up, not part of Option A
- [x] Persist conversation-level attachment metadata in control-plane
      `session_attachments` (keep `summary_md`, add `storage_key`)
- [x] Rehydrate persisted attachments on `ManagedChatPage` reload through
      `GET /teams/{team_id}/sessions/{session_id}/attachments`
- [x] Add a right-side attachment drawer near the paperclip, with file list,
      count badge, markdown preview, and delete action
- [x] Delete persisted attachments through control-plane orchestration plus
      Knowledge Flow strong cleanup (`document_uid` + `storage_key`)

### 4.3 Scheduler Task UI Integration

Attachment upload/processing feedback must reuse the task UI primitives introduced
by commit `f2fba80726e3516a4fb8716d55dfd575c4749c07`:

- `TaskStateBadge` for compact upload / processing state
- `TaskProgressBar` when a task exposes progress
- `TaskIndicator` for inline task status affordances
- `TaskTray` / `TaskTrayTrigger` for active and historical scheduler tasks
- `useTaskSseManager` and the task slice for scheduler event subscription

No duplicate upload progress modal or bespoke attachment drawer should be
reintroduced from the legacy `frontend/src/components/chatbot` tree.

### 4.4 Follow-ups Outside This Slice

- [ ] `LinkPart kind=download` rendering via `DownloadLinkBadge`
- [ ] Geo/Map rendering (`GeoPart`)
- [ ] Message expand/collapse for long messages
- [ ] Thumbs feedback per message
- [ ] PDF viewer integration

### 4.5 FILES-01 — MCP Filesystem-First Template And Artifact Exchange

**ID:** FILES-01
**RFC:** [`AGENT-FILESYSTEM-RFC.md`](../rfc/AGENT-FILESYSTEM-RFC.md)
**Status:** in progress — MCP-first target refreshed 2026-06-18
**Execution:** TBD

This slice makes the Knowledge Flow MCP filesystem the canonical file exchange
contract for a fresh Swift install. There is no backward-compatibility requirement for
old conversations, generated artifacts, old download links, or previous artifact/resource
keys. The migration keeps agents, prompts, users, teams, and required product metadata;
generated content starts fresh.

The target authoring model is:

- ReAct agents use the Knowledge Flow filesystem MCP tools when they need direct file
  operations.
- `fred-sdk` exposes `ctx.fs` helpers over that same MCP filesystem.
- Graph nodes use `context.fs` helpers over the same authenticated capability.
- Generated files are written to filesystem paths such as `/workspace/outputs/...`.
- Download references are returned as typed `LinkPart` values and rendered by managed chat.

#### 4.5.A Knowledge Flow MCP filesystem hardening

- [ ] Add binary read/write support to the Knowledge Flow MCP filesystem
- [ ] Add `link(path)` / download-reference generation to the MCP filesystem
- [ ] Return stable metadata: path, name, MIME type, size, updated timestamp, and href
      when applicable
- [ ] Add path traversal, authorization, read-only corpus, local-backend, and
      mocked-object-storage tests

#### 4.5.B SDK filesystem helpers

- [ ] Add `ctx.fs` and graph `context.fs` helper APIs over MCP
- [ ] Expose helpers for `read_text`, `read_bytes`, `write_text`, `write_bytes`,
      `link`, and `write_download`
- [ ] Make helpers return Python `str`, `bytes`, metadata objects, and `LinkPart`
      without exposing MCP transport details
- [ ] Remove or stop exporting `ArtifactPublishRequest`, `PublishedArtifact`,
      `ResourceFetchRequest`, `FetchedResource`, `ArtifactScope`, `ResourceScope`,
      `ArtifactPublisherPort`, and `ResourceReaderPort`

#### 4.5.C Runtime MCP integration

- [ ] Ensure file-capable agents declare or receive the Knowledge Flow filesystem MCP
      server
- [ ] Route ReAct filesystem tool calls through the MCP tool catalog
- [ ] Route graph `context.fs` helper calls through the same authenticated MCP capability
- [ ] Remove `FredArtifactPublisher` and `FredResourceReader` after callers migrate
- [ ] Add runtime tests proving execution identity is propagated to filesystem calls

#### 4.5.D LinkPart rendering and replay

- [ ] Render `LinkPart(kind="download")` entries in `AssistantTurn` with a small
      `DownloadLinkBadge`
- [ ] Preserve `ui_parts` in runtime history so live SSE and `messages_url_template`
      replay show the same download links
- [ ] Add frontend tests for live/history-loaded download link rendering
- [ ] Add runtime tests proving `ui_parts` are persisted and returned in session history

#### 4.5.E Minimal slide-template validation agent

- [ ] Add a fixture-backed validation path that reads a `.pptx` template from
      `/team/{team_id}/...` or `/agent/{agent_id}/config/...`, writes a generated
      `.pptx` to `/workspace/outputs/...`, and returns `LinkPart(kind="download")`
- [ ] Keep the happy path no-LLM and deterministic
- [ ] Use the official PPTX MIME type:
      `application/vnd.openxmlformats-officedocument.presentationml.presentation`

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
      names and justification. _(validated 2026-05-14 — see RFC §4)_
- [x] **Step 2 — Organism signatures** — TypeScript prop/callback interfaces for each organism _(validated 2026-05-14)_
- [x] **Step 3 — Data model** — `Conversation`, `Message` (tree), `Source`, `UserCapabilities`,
      `ConversationSettings` _(validated 2026-05-14 — `src/rework/types/conversation.ts`)_
- [x] **Step 4 — Page composition** — skeleton of `ManagedChatPage` showing organism assembly
      and hooks, under 80 lines _(validated 2026-05-14)_
- [x] **Step 5 — Implementation order** — atoms → molecules → organisms, each step demonstrable _(validated 2026-05-14)_

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

| Gap                                  | What the UI does today                                                                                                                                                                                       | What's needed                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Blocking                                          |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Session title                        | ~~Shows `abc12345…` (first 8 chars of UUID) when `title` is null~~ **Fixed.**                                                                                                                                | `ManagedChatPage` now passes `title: text.slice(0, 120)` (first user message) in the `CreateSessionRequest`. `ChatList` already displayed `session.title` with UUID fallback — no change needed there. LLM-generated summaries remain a future enhancement.                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Done                                              |
| Agent card — whole-card click        | Only the "Start Chat" button at the bottom is clickable. The develop branch had the entire card as a `<Link>` with `e.preventDefault()` on action buttons.                                                   | ~~Restore card as `<Link>` for enabled instances — frontend only, no backend change.~~ **Fixed.**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | ~~None~~ Done                                     |
| Agent settings / edit                | ~~Button visible but disabled on agent card~~ **Fixed.**                                                                                                                                                     | `EnrollManagedAgentModal` renamed to `AgentFormModal`, pre-fills from instance, dispatches PATCH via `usePatchTeamAgentInstance…` mutation. Frozen-snapshot policy in place (no re-merge with current template).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | ~~Backend + frontend~~ Done                       |
| Agent tuning fields at creation      | ~~Modal only captures `display_name` + `description`~~ **Fixed.**                                                                                                                                            | `AgentFormModal` fully refactored per RFC. `TemplateBrowser` card grid replaces raw `<select>`. All field types implemented: string, number/integer, boolean (`SwitchRow`), enum, secret, url, prompt/multiline. Field grouping via `ui.group`. Inline validation. Edit mode context bar + metadata footer. MCP tools read-only section.                                                                                                                                                                                                                                                                                                                                                                                                | ~~Backend + frontend~~ Done                       |
| `mcp_servers` pass-through           | Control plane dropped `available_mcp_servers` from runtime's `/agents/templates` response.                                                                                                                   | **Fixed.** `ManagedMcpServerRef` extended with `display_name` + `config_fields`. `AgentTemplateSummary` now includes `mcp_servers`. Runtime's `available_mcp_servers` mapped to `ManagedMcpServerRef` with `display_name` enriched from catalog. Frontend renders read-only MCP tools section.                                                                                                                                                                                                                                                                                                                                                                                                                                          | ~~Backend + frontend~~ Done                       |
| Orphaned components                  | `AgentCreateEditModal/KfVectorSearchForm` and `SwitchRow` exist. `KfVectorSearchForm` imports from `agenticOpenApi` (legacy). `SwitchRow` now re-used by `TuningFieldRenderer`.                              | `KfVectorSearchForm` is still used by old-tree `AgentToolsSelection` via `TOOL_PARAMS_REGISTRY` — cannot delete until that old component is migrated.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | None — defer until `AgentToolsSelection` migrates |
| File attachments                     | ~~No file attachment UI in `ManagedChatPage`.~~ **Fixed by CHAT-04.** Old `POST /agentic/v1/chatbot/upload` remains deprecated.                                                                               | CHAT-04 now uploads through `POST /knowledge-flow/v1/storage/user/upload`, persists session attachment metadata, and passes `/workspace/uploads/...` paths through `RuntimeContext.attachments_markdown`. Remaining file-exchange work moved to FILES-01 §4.5: Knowledge Flow MCP FS binary/link hardening, SDK `ctx.fs`/`context.fs`, durable `LinkPart` rendering/replay, and slide-template validation.                                                                                                                                                                                                                                                                    | CHAT-04 done; FILES-01 §4.5 remains              |
| Agent-library hard binding indicator | `ComposerSettingsControls` library chip is always interactive. When an agent's MCP server declares `document_library_tags_ids`, the chip should switch to read-only (lock icon) showing the bound libraries. | Backend contract is now in place: `ManagedAgentInstanceSummary.mcp_config_values` is exposed and `prepare-execution` resolves typed `effective_chat_options`. **Remaining:** frontend must derive/read the bound-library state from that data instead of leaving the chip always interactive. (`AgentOptionsPanel` retired 2026-05-24 — this gap now targets `ComposerSettingsControls`.)                                                                                                                                                                                                                                                                                                                                               | Frontend only                                     |
| `chat_options.*` in wrong form tab   | Library picker, search policy, RAG scope appear in "Settings" tab of `AgentFormBody`. They belong in the "Tools" tab, rendered beneath the KF search server checkbox when that server is active.             | **Partially fixed (2026-05-06):** `McpServerCard` now reads/writes per-server `configValues` (not flat `tuningFieldValues`); `AgentFormBody` passes server-scoped slices; `AgentFormModal` stores `mcpConfigValues` separately and tri-state selection is preserved (`[]` ≠ `null`); `TeamAgentsPage` forwards `mcp_config_values` to create/update API calls. `ManagedChatPage` now consumes `effective_chat_options` from `useChatSse` and passes it to `ComposerSettingsControls` which gates its sections. **Remaining:** move MCP `config_fields` controls to the "Tools" tab (currently rendered inline inside `McpServerCard` in the Tools tab — layout is correct, but they are not yet in a dedicated sub-section per server). | Frontend only                                     |
| Stream abort — backend gap           | Frontend abort is fully wired: `useChatSse.abort()` closes the `AbortController`, `waitResponse` resets to false, `ManagedChatPage` surfaces the stop button via `RichInputField.onInterrupt`.               | **Backend has no abort endpoint.** After the client disconnects, the agent/LLM execution continues to completion. The full response may appear in session history on next load. Partial streaming message is not cleaned up in the UI on abort. Needed: (1) `POST /control-plane/v1/teams/{team_id}/sessions/{session_id}/abort` or equivalent cancel signal on the runtime side; (2) frontend cleanup of the partial assistant message bubble on abort.                                                                                                                                                                                                                                                                                | Backend (no abort endpoint in `agent_app.py`)     |

---

## 8 Phase CHAT-07 — Composer state hardening

> **ID:** `CHAT-07` — `docs/swift/data/id-legend.yaml` > **RFC:** [`docs/swift/rfc/CHAT-COMPOSER-STATE-RFC.md`](../rfc/CHAT-COMPOSER-STATE-RFC.md) > **Scope:** frontend-only except Step 3 (one additive backend field + OpenAPI regen)
> **Rule:** Steps 1–2 can ship independently. Steps 3–5 must be implemented together.

---

### 8.1 Goal

Close five state-management gaps in `useChatSse` / `useManagedChat` /
`ComposerSettingsControls` that cause incorrect control visibility, wrong
defaults after navigation, and half-streaming state on session switch.

---

### 8.2 Tasks

#### Step 1 — `reset()` cancels in-flight streaming

- [x] `useChatSse.reset()` calls `abort()` before clearing messages (`useChatSse.ts` — 1 line) (2026-05-24)

#### Step 2 — True per-agent component isolation

- [x] Add `key={agentInstanceId}` to the `<ManagedChatPage>` element at the route definition (2026-05-24)
- [x] Remove the `agentInstanceId` dep from the `useManagedChat` reset effect (redundant once key is in place) (2026-05-24)

#### Step 3 — `effective_chat_options` in agent instance summary (backend)

- [x] Add `effective_chat_options: EffectiveChatOptions` to `_record_to_summary()` in `product/service.py` (2026-05-24)
- [x] Update `CONTROL-PLANE-PRODUCT-CONTRACT.md §3.2` — dated entry noting the field addition (2026-05-24)
- [x] Regenerate `controlPlaneOpenApi.ts` from the updated OpenAPI spec (2026-05-24)

#### Step 4 — Initialize composer defaults from agent summary

- [x] In `useManagedChat`, read `effectiveChatOptions` baseline from the agent instance summary at mount (2026-05-24)
- [x] Initialize `searchPolicy` and `ragScope` from `agentChatOptions` via `useComposerSettings`, not hardcoded `"hybrid"` (2026-05-24)
- [x] `useChatSse` value still overrides via `effectiveChatOptions ?? agentChatOptions` merge in return (2026-05-24)

#### Step 5 — Per-session composer persistence

- [x] Create `useComposerSettings(sessionId, agentDefaults)` hook in `pages/ManagedChatPage/` (2026-05-24)
- [x] Reads initial state from `sessionStorage` key `chat.composer.{sessionId}` if present; otherwise from `agentDefaults` (2026-05-24)
- [x] Writes through to `sessionStorage` on every setter call (2026-05-24)
- [x] `useManagedChat` delegates `searchPolicy`, `ragScope`, `selectedLibraryIds` to this hook (2026-05-24)

---

### 8.3 Validation

- [x] No-tools agent: composer controls never appear (before and after first message) — opt-in logic in `ComposerSettingsControls` + `hasComposerControls` gate in `ManagedChatPage`
- [x] KF-search agent: controls appear immediately on page load — `agentChatOptions` from summary feeds `hasComposerControls` at mount; async arrival handled by reactive `useEffect` in `useComposerSettings`
- [x] Default search policy matches agent configuration on first render — `useComposerSettings` initialises from `agentOptions.default_search_policy`; late-arrival effect re-applies if query was in-flight at mount
- [x] Navigate away from session X, return — search policy and library selection restored from `sessionStorage` key `chat.composer.{sessionId}`
- [x] Switch from Agent A to Agent B while streaming — `key={agentInstanceId}` on route forces full remount; `reset()` in `useChatSse` aborts in-flight SSE before clearing state
- [x] `tsc --noEmit` passes; `prettier --write` applied to `useComposerSettings.ts` (2026-05-24)

---

## 9 Phase CHAT-08 — Source-to-document navigation

> **ID:** `CHAT-08` — `docs/swift/data/id-legend.yaml`  
> **RFC:** [`docs/swift/rfc/RAG-AGENT-QUALITY-RFC.md`](../rfc/RAG-AGENT-QUALITY-RFC.md)  
> **Scope:** frontend only  
> **Depends on:** RUNTIME-06 (Rico prompt + tool result pruning, independent but companion)

---

### 9.1 Goal

Allow users to navigate from a cited source in the chat to the full source document.
Today `SourceDetailModal` shows the chunk extract but has no link to the document.
`VectorSearchHit.citation_url` already carries a `/documents/{uid}` path — but the
frontend router has no route to receive it.

This phase registers that route and adds the "Open document" link.

---

### 9.2 Background — why no signed URLs are needed

The document viewer (`MarkdownDocumentViewer`) authenticates via the Keycloak session
token present in all RTK Query calls. It calls `GET /knowledge-flow/v1/markdown/{uid}`,
which the backend serves by fetching from MinIO and injecting presigned MinIO URLs for
embedded images (1-minute TTL, transparent to the frontend). No signed URL is needed
for the navigation layer itself.

---

### 9.3 Tasks

#### Step 1 — `/documents/:uid` route

- [x] Create `DocumentViewerPage` component at
      `src/rework/components/pages/DocumentViewerPage/DocumentViewerPage.tsx`  
       Renders `MarkdownDocumentViewer` (from `src/common/`) with `document_uid` from
      `useParams`, in a page layout with a back-navigation button.
- [x] Register route `{ path: "documents/:uid", element: <DocumentViewerPage /> }` in
      `src/common/router.tsx`
- [x] Update `src/common/router.tsx` header comment documenting the new path.

#### Step 2 — "Open document" link in `SourceDetailModal`

- [x] `SourceDetailModal` receives `source: VectorSearchHit` (already does).
       Add an "Open document" button/link rendered only when `source.uid !== "Unknown"`.
       Uses `<a href={`/documents/${source.uid}`} target="_blank">` — no callback threading.

#### Step 3 — Documentation

- [x] Update `CONTROL-PLANE-PRODUCT-CONTRACT.md` — note that `citation_url` in
      `VectorSearchHit` now has a valid target route.
- [x] Update `COMPONENT-UX.md` — `SourceDetailModal` now has an open-document action.

---

### 9.4 Non-changes

- `VectorSearchHit` schema unchanged.
- No backend changes.
- No SSE contract changes.
- Chunk highlight via `#chunk=...` fragment deferred (out of scope for CHAT-08).
- PDF viewer route deferred (markdown only for now).

---

### 9.5 Validation

- [x] Clicking "Open document" in `SourceDetailModal` opens a new tab at `/documents/{uid}` rendering the correct document
- [x] When `source.uid === "Unknown"` the link is absent (defensive — metadata gap)
- [x] `tsc --noEmit` passes; `prettier --check` passes
- [ ] Navigating directly to `/documents/{uid}` in the browser works (deep-link)

---

## 7 Phase CHAT-06 — test_assistant rich content scenarios

> **ID:** `CHAT-06` — `docs/swift/data/id-legend.yaml` > **Scope:** backend only — `apps/fred-agents/fred_agents/test_assistant/` > **Purpose:** make `fred.github.test_assistant` a complete rendering test harness for the chat UI,
> covering every content type the new `MarkdownRenderer` must handle without requiring a live LLM.

---

### 7.1 Current gaps

The test agent covers SSE events (streaming, HITL, error, sources) and all FieldSpec form types.
It does **not** exercise rich content rendering. No existing scenario produces:

| Content type                                          | Needed for              |
| ----------------------------------------------------- | ----------------------- |
| Fenced code block with language (`python`, `bash`, …) | Syntax highlighting     |
| Mermaid diagram                                       | `Mermaid` renderer      |
| GFM table                                             | Table rendering         |
| GeoJSON `FeatureCollection`                           | Leaflet map renderer    |
| KaTeX inline math                                     | Math rendering          |
| KaTeX block math                                      | Math rendering          |
| `:::details` collapsible                              | remark-directive plugin |

---

### 7.2 New scenario: `markdown`

Add a `markdown_step` triggered by the keyword prefix `markdown`.
The step emits a single static assistant message that contains one well-formed
example of each content type listed in §7.1.

**Content requirements per block:**

| Block       | Minimum content                                                                  |
| ----------- | -------------------------------------------------------------------------------- |
| Code        | A short Python function (5–8 lines), fenced ` ```python `                        |
| Mermaid     | A 4-node flowchart (`graph TD`), fenced ` ```mermaid `                           |
| Table       | 3 columns × 3 data rows, GFM pipe syntax                                         |
| GeoJSON     | Inline JSON literal: `FeatureCollection` with 2 `Point` features and 1 `Polygon` |
| Math inline | One expression rendered with `$…$`                                               |
| Math block  | One expression rendered with `$$…$$`                                             |
| Details     | One `:::details[Title]` block wrapping a short paragraph                         |

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

## 10 Phase CHAT-09 — Streaming render guard

**RFC:** `docs/swift/rfc/STREAMING-RENDER-GUARD-RFC.md`  
**ID:** CHAT-09  
**Status:** done (2026-05-28)  
**Priority:** high — visible rendering errors on every streaming reply containing a diagram or code block
Execution: GitHub issue `#1654`

### 10.1 Goal

Eliminate transient `Diagram error` / broken-highlight / KaTeX parse-error states
that appear during streaming whenever a chunk boundary falls inside a fenced block
(` ```mermaid `, ` ```python `, `$$`, `:::details`), while keeping useful visual
feedback whenever the reply starts streaming any supported block fence.

A single generic utility now splits the accumulated text into:

- safe markdown that can be rendered immediately
- one pending fence preview, if the last block is still open

The preview uses a single source-first shell for all open fences:

- any backtick fence, including ` ```mermaid ` → `CodeBlock` shell with the raw source text
- `$$` blocks → `CodeBlock` shell labelled `math`
- `:::details` and other supported directives → `CodeBlock` shell labelled with the directive name

Once a Mermaid fence closes, the final markdown pipeline mounts `MermaidBlock`
and renders the SVG.

Companion hardening under the same execution issue: the standalone `fred-agents`
pod now packages one shared Mermaid output contract and appends it to every
shipped default agent prompt via SDK prompt-composition helpers. This does not
replace the frontend guard; it lowers the chance that the final closed fence is
invalid Mermaid in the first place.

### 10.2 Tasks

#### Step 1 — `streamingGuard` utility

- [x] Create `apps/apps/frontend/src/rework/components/shared/molecules/MarkdownRenderer/streamingGuard.ts`
      — linear scan that detects open backtick fences, `$$` blocks, and `:::` directives,
      returning both the safe markdown prefix and pending-fence metadata
- [x] Create `streamingGuard.test.ts` with the unit-test cases specified in RFC §5.2
      plus pending metadata coverage for Mermaid, code, math, and directive previews

#### Step 2 — `MarkdownRenderer` integration

- [x] Add `streaming?: boolean` prop to `MarkdownRenderer` (default `false`)
- [x] When `streaming={true}`, render the safe markdown prefix through `react-markdown`
      and append a `CodeBlock` pending preview for the last open fence, including Mermaid
- [x] Wire `streaming` prop in `AssistantMessage`

#### Step 3 — Verification

- [x] Local streaming path verified: pending code / Mermaid / math / directive fences show a
      `CodeBlock` shell instead of rendering errors or raw leaked fence syntax; complete fences still
      render through the normal final path (`MermaidBlock` for finished Mermaid, specialized final
      renderers for the others)
- [x] `tsc --noEmit` passes; `prettier --check` passes
- [x] Frontend unit tests cover both safe-prefix truncation and pending preview metadata for
      Mermaid, code, math, and directives
- [x] Live-pod manual validation explicitly deferred — same non-blocking posture as CHAT-06

#### Step 4 — Doc update

- [x] Amend `docs/swift/rfc/CHAT-RENDERING-SPEC.md` §1.3 and §5 to reference the guard
- [x] Update execution/tracking docs (`id-legend.yaml`, `sprint.yaml`, `PMO-BOARD.md`, `COMPONENT-UX.md`)

### 10.3 Non-changes

- No backend changes
- No new npm dependencies
- `streaming=false` path is a no-op — no behaviour change for already-complete messages

---

## 11 Phase CHAT-10 — Mindmap block rendering

**ID:** CHAT-10  
**Status:** done (2026-06-05)  
**Priority:** medium — structured visual rendering for agent-generated mindmap payloads  
Execution: working branch `feature/swift-test`

### 11.1 Goal

Support fenced `mindmap` / `mindmap-json` blocks in `MarkdownRenderer` by handing
them off to a dedicated `MindMapBlock` molecule instead of falling back to a raw
code block.

The delivered component renders a validated JSON payload as an interactive tree,
keeps the existing markdown pipeline unchanged for Mermaid and generic code fences,
and degrades safely when the payload is invalid.

### 11.2 Tasks

#### Step 1 — `MindMapBlock` molecule

- [x] Create `apps/frontend/src/rework/components/shared/molecules/MindMapBlock/`
      with interactive tree rendering, copy action, breadcrumb/detail pane, token-aware
      light/dark styling, and raw-payload fallback on parse failure
- [x] Add `mindmapParser.ts` helpers for payload validation, fallback node ids,
      node-count guardrails, breadcrumb lookup, and tooltip-safe escaping
- [x] Document the accepted payload shape in `MindMapBlock/README.md`

#### Step 2 — `MarkdownRenderer` integration

- [x] Extend the fenced-language detection regex to support hyphenated labels such
      as `mindmap-json`
- [x] Route `mindmap` and `mindmap-json` fences to `MindMapBlock`
- [x] Keep `mermaid` fences on `MermaidBlock` and preserve the generic `CodeBlock`
      fallback for every other fenced language

#### Step 3 — Verification

- [x] Unit tests cover valid payload parsing, invalid JSON, missing root label, and
      breadcrumb resolution in `mindmapParser.test.ts`
- [ ] Manual chat validation with a real `mindmap-json` fenced response in
      `ManagedChatPage`

### 11.3 Non-changes

- No backend, runtime, or SSE contract changes
- No automatic schema negotiation with agents — the renderer only consumes fenced JSON
- No change to Mermaid rendering beyond coexistence in the markdown dispatch path

---

## 12 Phase CHAT-11 — Voice dictation into chat input

**ID:** CHAT-11  
**Status:** in progress  
**Priority:** medium — composer input accessibility and faster capture of short prompts  
Execution: waived GitHub issue for this local Codex session

### 12.1 Goal

Add an MVP dictation flow to the managed chat composer:

- microphone button in `RichInputField`
- short browser-recorded clip via `MediaRecorder`
- synchronous transcription through Knowledge Flow
- returned transcript appended into the existing chat input
- user reviews/edits before normal send

### 12.2 Tasks

#### Step 1 — Knowledge Flow transcription endpoint

- [ ] Add `POST /knowledge-flow/v1/audio/transcriptions`
- [ ] Accept `multipart/form-data` with `file` and optional `language`
- [ ] Reuse local Whisper / `faster-whisper` capability through a small dedicated
      helper, without document ingestion persistence
- [ ] Reject empty files and unsupported extensions/MIME hints
- [ ] Enforce a small synchronous upload cap for MVP safety
- [ ] Add offline backend tests with fake transcription service / monkeypatch

#### Step 2 — Composer mic control

- [ ] Extend `RichInputField` with optional voice-input props and UI states:
      idle, recording, transcribing
- [ ] Use `navigator.mediaDevices.getUserMedia({ audio: true })`
- [ ] Record with `MediaRecorder`, stop on second click, convert blob to `File`
- [ ] Keep styling token-based and aligned with existing composer layout

#### Step 3 — Managed chat wiring

- [ ] Wire the Knowledge Flow transcription mutation through existing frontend
      API conventions
- [ ] Pass dictation props from `ManagedChatPage`
- [ ] Append transcript into `chat.input` via controlled state without auto-send
- [ ] Disable the voice control while streaming or while session history loads
- [ ] Surface failures through existing toast conventions
- [ ] Add English and French labels

#### Step 4 — Verification

- [ ] Knowledge Flow: `make code-quality`
- [ ] Knowledge Flow: `make test`
- [ ] Frontend: regenerate Knowledge Flow API client if backend OpenAPI changes
- [ ] Frontend: `npm run typecheck`
- [ ] Frontend: `npm run test`

### 12.3 Non-changes

- No realtime transcription
- No voice assistant or auto-send
- No browser `SpeechRecognition`
- No OpenAI audio API
- No runtime/SSE protocol changes

---

## 6 Progress

| Phase                                       | Status               | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AgentFormModal refactor                     | ✅ Done (2026-04-28) | `TemplateBrowser` + `TemplateCard` + `TuningFieldRenderer` + `AgentFormBody` extracted; all field types; grouping; MCP read-only section; edit context bar + metadata footer. RFC: `docs/rfc/AGENT-INSTANCE-FORM-RFC.md`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| CHAT-01 – Architecture & layout             | ✅ Done (2026-04-27) | All atoms + molecules + organisms created; three-column layout; `ConversationMessage` state model + `toConversationMessages`; HITL history channels (hitl_request frozen card, hitl_response user bubble); sources from `assistant/final` metadata. Prettier + `tsc` pass.                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| CHAT-02 – Markdown & content                | ✅ Done (2026-05-04) | `MarkdownRenderer` (react-markdown + remark-gfm + rehype-sanitize + rehypeCitations plugin); `CodeBlock` (monospace + copy); `SourceBadge` atom; wired into `AssistantMessage`; `AssistantTurn` threads `onSourceClick` → `SourcesPanel` activeIndex highlight. Prettier + `tsc` pass.                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Code quality audit                          | ✅ Done (2026-05-04) | MUI removed from `Breadcrumb` (→ `Icon` atom) and `MainLayout` (`CssBaseline` dropped); `Menu` moved from `organisms/` → `molecules/`; hex fallbacks removed from `HitlPrompt.module.css`; Apache 2.0 license headers added to all 51 rework `.tsx` files. `KfVectorSearchForm` kept (still used by old-tree `AgentToolsSelection` via `TOOL_PARAMS_REGISTRY`).                                                                                                                                                                                                                                                                                                                                                                     |
| CHAT-03 – Agent options & debug tools       | 🔄 In progress       | `AgentOptionsPanel` organism done (2026-05-06): library picker + search-policy/scope controls wired to `RuntimeContext`. Backend contract freeze done (2026-05-06). Frontend wiring done (2026-05-06): `mcp_config_values` correctly separated from `tuning_field_values` in form + API calls; tri-state MCP selection preserved through form round-trip; `useChatSse` exposes `effectiveChatOptions`; `AgentOptionsPanel` gates sections on `options` prop; `ManagedChatPage` syncs search defaults from agent config. **Routine controls retired (2026-05-24):** library picker, search policy, RAG scope moved to `ComposerSettingsControls` chips (CHAT-05). Remaining: debug tools section (`DebugDrawer` via `InlineDrawer`). |
| CHAT-04 – Chat attachments & advanced parts | ✅ Done (2026-06-11) | Completed the Option A attachment slice with persistence: composer attach-file control, upload to existing `/knowledge-flow/v1/storage/user/upload`, chips in `RichInputField.topSlot`, runtime context paths via `attachments_markdown`, base64 image context, drag-and-drop ingestion, scheduler task UI reuse, control-plane `session_attachments` persistence (`summary_md` kept, `storage_key` added), session reload hydration, right-side conversation files drawer with markdown preview, and strong delete orchestration through Knowledge Flow cleanup. FILES-01 now tracks the MCP filesystem-first generated-content path: KF MCP FS binary/link hardening, SDK `ctx.fs`/`context.fs`, runtime MCP integration, LinkPart replay/rendering, and minimal slide-template validation. Validation: control-plane, knowledge-flow, and frontend `make code-quality` + `make test`. |
| CHAT-05 – DS enrichment & refonte           | 🔄 In progress       | Steps 1–5 validated (2026-05-14). Waves 0–8 implemented (2026-05-18): types, 5 atoms, 8 molecules, 6 organisms, 4 hooks/utils. `ManagedChatPage` reduced to 80 lines. MarkdownRenderer extended (2026-05-21): `remark-math`, `rehype-katex`, `remark-directive`, `MermaidBlock`, `hr` suppression. Rendering spec RFC: `docs/swift/rfc/CHAT-RENDERING-SPEC.md`. Remaining: `ConversationSidebar`, `SourceDetailDrawer`, `DebugDrawer`.                                                                                                                                                                                                                                                                                              |
| CHAT-06 – test_assistant rich content       | ✅ Done (2026-05-21) | Backend: `markdown_step` in `apps/fred-agents` with 7 content types (code, mermaid, table, GeoJSON, math inline+block, details). Manual live verification pending pod.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| CHAT-07 – Composer state hardening          | ✅ Done (2026-05-24) | RFC: `docs/swift/rfc/CHAT-COMPOSER-STATE-RFC.md`. All 5 steps implemented.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| CHAT-09 – Streaming render guard            | ✅ Done (2026-05-28) | RFC: `docs/swift/rfc/STREAMING-RENDER-GUARD-RFC.md`. Streaming markdown now splits into safe rendered prose plus one pending fence preview block. Any supported open fence (` ```lang `, ` ```mermaid `, `$$`, `:::`) shows a `CodeBlock` shell until completion; Mermaid then hands off to `MermaidBlock` for final SVG rendering. No backend changes, no new deps. Manual live-pod validation remains a non-blocking follow-up.                                                                                                                                                                                                                                                                                                   |
| CHAT-10 – Mindmap block rendering           | ✅ Done (2026-06-05) | Frontend-only. `MarkdownRenderer` now routes `mindmap` / `mindmap-json` fences to `MindMapBlock`, while Mermaid and generic code paths stay unchanged. `MindMapBlock` validates JSON payloads, enforces safe node-count limits, renders an interactive tree with breadcrumb/detail support, and falls back to raw payload display on parse errors. Manual live-chat validation remains open.                                                                                                                                                                                                                                                                                                                                        |
| CHAT-11 – Voice dictation into chat input   | 🔄 In progress       | RFC: `docs/swift/rfc/CHAT-VOICE-DICTATION-RFC.md`. MVP scope: authenticated Knowledge Flow transcription endpoint plus `RichInputField` microphone control in `ManagedChatPage`. Transcript must append into the controlled composer without auto-send, while preserving attachment flow and existing typed message flow. |

> **UX review status** (functional ≠ UX-validated): see [`docs/ux/COMPONENT-UX.md`](../ux/COMPONENT-UX.md).
