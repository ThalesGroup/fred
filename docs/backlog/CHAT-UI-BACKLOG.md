# Chat UI Backlog

## 0 Overview

### 0.1 Context

Phase 5D delivered a functional `ManagedChatPage` wired to the SSE runtime
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

- All new components live under `src/rework/components/shared/` following the
  atoms → molecules → organisms hierarchy.
- CSS modules only. Use existing design tokens (`--spacing-*`, `--radius-*`,
  `--font-*`, color variables).
- No new global state. Conversation state stays local to `ManagedChatPage`
  via `useState`.
- The SSE connector (`useChatSse`) is the only execution wire. Do not add
  WebSocket or REST polling for message content.
- Keep existing `HitlPrompt` component unchanged in Phase 6A.
- Never hand-edit `runtimeOpenApi.ts` — it is generated.

---

## 1 Phase 6A — Page Architecture & Core Layout

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
│                │  │         │  ThinkingAccordion        │ │ │
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
| `ThinkingAccordion` | `molecules/ThinkingAccordion/` | Collapsible reasoning trace container |
| `ToolCallStep` | `molecules/ThinkingAccordion/ToolCallStep/` | Tool name + args (collapsed JSON) |
| `ToolResultStep` | `molecules/ThinkingAccordion/ToolResultStep/` | Result status + latency + preview |
| `SourceCard` | `molecules/SourcesPanel/SourceCard/` | One citation: index, title, score, excerpt |
| `SourcesPanel` | `molecules/SourcesPanel/` | List of SourceCards, visible after `final` event |
| `ChatInputBar` | `molecules/ChatInputBar/` | TextArea atom + send IconButton, disabled during streaming |

#### Organisms

| Component | Path | Purpose |
|---|---|---|
| `ChatMessagesArea` | `organisms/ChatMessagesArea/` | Scrollable message list, auto-scroll, empty state |
| `AssistantTurn` | `organisms/AssistantTurn/` | Groups ThinkingAccordion + AssistantMessage + SourcesPanel for one exchange |

---

### 1.4 Local Conversation State

`ManagedChatPage` owns this state via `useState`. No Redux slice.

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
| `tool_call` | Push `ThinkingStep {kind:'tool_call', status:'running'}` | `ThinkingAccordion` appears (open by default), `ToolCallStep` with spinner |
| `tool_result` | Match `call_id`, update to `status:'done'` or `status:'error'`, add `tool_result` step | `ToolCallStep` → `ToolResultStep` |
| `final` | Replace text with final content, attach sources, clear `isStreaming` | `StreamingCursor` disappears, `SourcesPanel` appears if sources present |
| `status` | Set `statusText` on current message | Italic status line below bubble |
| `awaiting_human` | Existing `HitlPrompt` path — unchanged | HITL inline prompt |
| `node_error` | Set `error` on current message | Error chip in bubble |
| `turn_persisted` | Update `sessionId` in URL — existing logic | Silent |

---

### 1.6 ThinkingAccordion Behaviour

- Opens automatically when the first `tool_call` event arrives.
- Stays open during streaming.
- **Auto-closes** when `final` event arrives (collapsed by default after turn completes).
- User can re-open manually by clicking the header.
- Header label: `N step(s)` where N = total count of steps.
- During streaming, shows a spinner next to the label.

---

### 1.7 Tasks

- [ ] Create `MessageBubble` atom with `role` variant prop
- [ ] Create `StreamingCursor` atom (CSS blink animation)
- [ ] Create `ToolBadge` atom (running / success / error variants)
- [ ] Create `SourceBadge` atom (superscript index, onClick scroll)
- [ ] Create `UserMessage` molecule
- [ ] Create `AssistantMessage` molecule (StreamingCursor + ToolBadge when streaming)
- [ ] Create `ToolCallStep` molecule (name + collapsed JSON args + ToolBadge)
- [ ] Create `ToolResultStep` molecule (ok/error icon + latency + 2-line preview)
- [ ] Create `ThinkingAccordion` molecule (accordion open/close, steps list)
- [ ] Create `SourceCard` molecule (index + title + score % + 2-line excerpt)
- [ ] Create `SourcesPanel` molecule (stack of SourceCards with "Sources" header)
- [ ] Create `ChatInputBar` molecule (TextArea + send IconButton, Shift+Enter = newline)
- [ ] Create `ChatMessagesArea` organism (scroll container, auto-scroll to bottom, empty state)
- [ ] Create `AssistantTurn` organism (ThinkingAccordion + AssistantMessage + SourcesPanel)
- [ ] Refactor `ManagedChatPage` to use all new components
- [ ] Map SSE events to `ConversationMessage` state (replace current flat state)
- [ ] Normalise history-loaded messages (from control-plane) to `ConversationMessage[]`
- [ ] Run `make code-quality` on frontend

---

### 1.8 Validation

- [ ] User messages appear right-aligned with `--surface-container-high` background
- [ ] Agent messages appear left-aligned with `--surface-container` background
- [ ] `StreamingCursor` visible during delta streaming, gone on `final`
- [ ] `ThinkingAccordion` opens on first `tool_call`, closes on `final`
- [ ] `ToolCallStep` transitions to `ToolResultStep` when matching `tool_result` received
- [ ] `SourcesPanel` appears below final message when `sources` non-empty
- [ ] `ChatInputBar` is disabled (send button + textarea) while streaming
- [ ] Existing HITL flow (`HitlPrompt`) is unaffected
- [ ] History loaded from control-plane renders identically to streamed messages
- [ ] No regressions in `ChatList` sidebar session links

---

## 2 Phase 6B — Markdown & Content Rendering

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

### 2.3 Tasks

- [ ] Audit whether `react-markdown` is already in `package.json`
- [ ] Decide and document markdown library choice
- [ ] Implement `MarkdownRenderer` molecule with safe subset
- [ ] Implement `SourceBadge` injection inside rendered markdown
- [ ] Implement `CodeBlock` molecule (monospace + copy button)
- [ ] Replace plain text in `AssistantMessage` with `MarkdownRenderer`
- [ ] Run `make code-quality` on frontend

---

### 2.4 Validation

- [ ] Bold, italic, lists, headings render correctly
- [ ] Code blocks render monospace with copy button
- [ ] Inline `[N]` markers render as `SourceBadge`, not as literal brackets
- [ ] No raw HTML injection possible
- [ ] User message bubbles still render plain text

---

## 3 Phase 6C — Agent Options & Chat Controls

### 3.1 Goal

Add the controls that surround the conversation: session title, new chat,
model/temperature settings if exposed by the agent, copy message, and
conversation-level actions.

---

### 3.2 Scope (to be refined)

- Session title editable inline in the header (PATCH to control-plane session).
- "New chat" button clears state and generates a new `session_id`.
- Per-message copy button on `AssistantMessage` (copy markdown as plain text).
- Agent runtime options panel (temperature, system prompt override) — only if
  `ExecutionPreparation` exposes configurable parameters.
- Conversation export (future, not Phase 6C).

---

### 3.3 Tasks

- [ ] Define which agent runtime options are exposable from `ExecutionPreparation`
- [ ] Add inline editable session title to chat header
- [ ] Wire PATCH `/teams/{team_id}/sessions/{session_id}` for title updates
- [ ] Add "New chat" button
- [ ] Add per-message copy button on `AssistantMessage`
- [ ] Decide agent options panel scope based on runtime contract

---

## 4 Phase 6D — Advanced Message Parts (deferred)

Features deferred until Phases 6A–6C are stable:

- Geo/Map rendering (`GeoPart`)
- Document download/view links (`LinkPart`)
- Token usage display
- Message expand/collapse for long messages
- Thumbs feedback per message
- PDF viewer integration

---

## 5 Progress

| Phase | Status | Notes |
|---|---|---|
| 6A – Architecture & layout | Planned | Starting point |
| 6B – Markdown & content | Planned | Depends on 6A |
| 6C – Agent options & controls | Planned | Depends on 6A |
| 6D – Advanced parts | Deferred | After 6C |
