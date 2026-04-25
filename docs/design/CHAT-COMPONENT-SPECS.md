# Chat UI — Component Specifications

Design reference for the managed chat interface components.
This document is the implementation authority — it takes precedence over the
high-level descriptions in `CHAT-UI-BACKLOG.md` when they diverge.

**Naming decision:** the reasoning-trace component is called `ThoughtTrace`
(not `ThinkingAccordion`). All backlog references to `ThinkingAccordion` are
superseded by this document.

**Scope:** `ManagedChatPage` and its child components only.
Legacy `ChatBot.tsx` components are not covered here.

---

## Table of Contents

1. [ThoughtTrace](#1-thoughttrace)
2. [TraceEntryRow](#2-traceentryrow)
3. [TraceDetailDrawer](#3-tracedetaildrawer)
4. [AssistantTurn](#4-assistantturn)
5. [AssistantMessage](#5-assistantmessage)
6. [UserMessage](#6-usermessage)
7. [SourcesPanel & SourceCard](#7-sourcespanel--sourcecard)
8. [ChatInputBar](#8-chatinputbar)
9. [ChatMessagesArea](#9-chatmessagesarea)

---

## 1. ThoughtTrace

**Path:** `src/rework/components/shared/molecules/ThoughtTrace/ThoughtTrace.tsx`
**Replaces:** `ThinkingAccordion` in all backlog references.

### 1.1 Concept

Progressive-disclosure component that renders the agent's internal reasoning
and tool usage. It sits at the top of an `AssistantTurn` and uses a
**vertical timeline metaphor**.

The component has two visual states driven by the streaming lifecycle:

| State | When | Appearance |
|---|---|---|
| **Streaming** | After first trace step, before `final` | Expanded, steps animated |
| **Collapsed** | After `final` event | Single summary line with elapsed time |
| **Reopened** | User clicks summary | Expanded again, static (no animations) |

### 1.2 Entry Model

Steps are grouped into `TraceEntry` objects before rendering.
The grouping logic lives in `src/rework/utils/traceUtils.ts`.

```typescript
type TraceEntry =
  | { kind: 'solo';  message: ChatMessage }
  | { kind: 'combo'; call: ChatMessage; result?: ChatMessage }
```

Rules (see `CHAT-UI-BACKLOG.md §1.6` for the full grouping algorithm):
- `tool_call` opens a `combo`; its matching `tool_result` closes it in-place
- all other channels (`plan`, `thought`, `observation`, `system_note`, `error`) are `solo`
- only channels in `TRACE_CHANNELS` are shown
- ordered by `rank` ascending

### 1.3 Timer Logic

ThoughtTrace records its own wall-clock elapsed time independently of backend
latency fields:

```typescript
// On first trace step received:
const startTimeRef = useRef<number>(Date.now());

// On final event:
const elapsedMs = Date.now() - startTimeRef.current;
const elapsedLabel = elapsedMs < 1000
  ? `${elapsedMs}ms`
  : `${(elapsedMs / 1000).toFixed(1)}s`;
// → summary: "Thought for 1.4s"
```

The elapsed time is display-only. It is not sent to any API.

### 1.4 Summary Line (Collapsed Header)

```
🧠  Thought for 1.4s                                          ›
```

| Element | Spec |
|---|---|
| Left icon | 14 px "brain" or "sparkle" icon (`var(--on-surface-retreat)`) |
| Text | `"Thought for {elapsed}"` when collapsed; live status text while streaming (e.g. `"Searching documentation…"`) |
| Right icon | Chevron-down when collapsed, chevron-up when expanded |
| Typography | `var(--font-label-small)`, weight `500`, `var(--on-surface-retreat)` |
| Cursor | `pointer` |
| Click target | Full width of the summary line |

**Live status text while streaming:** use the `primaryText` of the last
received `TraceEntry` as the running label. Fall back to `"Thinking…"` if no
step has arrived yet.

### 1.5 Timeline (Expanded View)

A vertically stacked list of `TraceEntryRow` molecules connected by a left-hand
guideline.

```
│  ● Tool call   get_relevant_documents(…)          1.2s   [<>]
│  ● Thought     Analysing the retrieved content…
│  ● Tool call   summarise_document(…)     waiting…        [<>]
```

**Guideline:**
- `1.5px` solid `var(--outline-variant)`, positioned `10px` from the left edge
- runs from the centre of the first dot to the centre of the last dot
- implemented as a pseudo-element on the container (avoids layout side effects)

**Container:**
- `background: transparent`
- no border, no box-shadow
- `padding-left: var(--spacing-sm)` to offset rows from the guideline
- `margin-bottom: var(--spacing-md)` to separate from `AssistantMessage`

### 1.6 Entry Dot States

Each `TraceEntryRow` has an 8 px circle centred on the guideline.

| State | Colour | Animation |
|---|---|---|
| Active (streaming, no result yet) | `var(--primary-main)` | `pulse` keyframe, 1.2 s ease-in-out |
| Success | `var(--outline-variant)` | None |
| Error | `var(--error-main)` | None |
| Neutral (non-tool solo) | `var(--outline-variant)` | None |

```css
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--primary-main) 40%, transparent); }
  50%       { box-shadow: 0 0 0 4px transparent; }
}
```

### 1.7 Lifecycle

1. `ThoughtTrace` renders `null` until the first trace step arrives.
2. On first step: `startTimeRef.current = Date.now()`, `isOpen = true`.
3. While streaming: `isOpen = true`, summary text = last step primary text.
4. On `final`: calculate elapsed, `isOpen = false`, summary text = `"Thought for {elapsed}"`.
5. User can click summary line to toggle `isOpen` at any time after `final`.

### 1.8 CSS Module Blueprint

```css
.container {
  position: relative;
  display: flex;
  flex-direction: column;
  padding-left: var(--spacing-sm, 0.5rem);
  margin-bottom: var(--spacing-md, 1rem);
}

.container::before {
  content: '';
  position: absolute;
  left: 10px;
  top: 12px;
  bottom: 12px;
  width: 1.5px;
  background: var(--outline-variant, #cac4d0);
}

.summaryLine {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 0.5rem);
  cursor: pointer;
  font: var(--font-label-small, 500 0.75rem/1.25 sans-serif);
  color: var(--on-surface-retreat, #6e6e7a);
  padding: var(--spacing-2xs, 0.25rem) 0;
  user-select: none;
}

.summaryLine:hover {
  color: var(--on-surface, #1c1b1f);
}

.summaryText {
  flex: 1;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 0;
}
```

---

## 2. TraceEntryRow

**Path:** `src/rework/components/shared/molecules/ThoughtTrace/TraceEntryRow/TraceEntryRow.tsx`

### 2.1 Layout

```
  ●  [LABEL]  Primary text summary                  1.2s   [<>]
```

Single-line row, `min-height: 28px`, `align-items: center`.

| Column | Width | Content |
|---|---|---|
| Dot | `20px` fixed | Entry dot (see §1.6) |
| Index | `auto`, hover-only | `12px` monospace, `var(--on-surface-disabled)`, `opacity: 0` → `1` on row hover |
| Label chip | `auto` | `"TOOL"` / `"THOUGHT"` / `"PLAN"` / `"OBS"` / `"ERROR"` — 10 px all-caps, `var(--on-surface-retreat)` |
| Primary text | `flex: 1`, max 400px, ellipsis | Summary string (see `CHAT-UI-BACKLOG.md §1.6` derivation rules) |
| Secondary text | `auto` | Latency or `"waiting…"`, `var(--on-surface-retreat)` |
| Detail trigger | `24px` icon button | Visible `opacity: 0` → `1` on row hover; opens `TraceDetailDrawer` |

### 2.2 Label Values

| Entry type | Label |
|---|---|
| `combo` (tool call) | `TOOL` |
| `solo`, channel `thought` | `THOUGHT` |
| `solo`, channel `plan` | `PLAN` |
| `solo`, channel `observation` | `OBS` |
| `solo`, channel `system_note` | `NOTE` |
| `solo`, channel `error` | `ERROR` |

### 2.3 Streaming Variants

While a `combo` has no result yet (`combo.result === undefined`):
- primary text is italic
- a `…` suffix is appended to the text
- dot pulses (see §1.6)
- secondary text: `"waiting…"`

### 2.4 CSS Blueprint

```css
.row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 0.75rem);
  position: relative;
  min-height: 28px;
  font-size: 13px;
  font-family: var(--font-family-sans);
  padding: var(--spacing-2xs, 0.25rem) var(--spacing-xs, 0.5rem);
  border-radius: var(--radius-xs, 0.25rem);
  transition: background 0.1s;
}

.row:hover {
  background: var(--surface-container-hover, rgba(0,0,0,0.04));
}

.index {
  font-family: monospace;
  font-size: 12px;
  color: var(--on-surface-disabled);
  opacity: 0;
  transition: opacity 0.1s;
  min-width: 2ch;
  text-align: right;
}

.row:hover .index {
  opacity: 1;
}

.label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--on-surface-retreat);
  min-width: 40px;
}

.primary {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 400px;
}

.primaryPending {
  font-style: italic;
  color: var(--on-surface-retreat);
}

.secondary {
  font-size: 12px;
  color: var(--on-surface-retreat);
  white-space: nowrap;
}

.detailTrigger {
  opacity: 0;
  transition: opacity 0.1s;
}

.row:hover .detailTrigger {
  opacity: 1;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

.dotNeutral  { background: var(--outline-variant, #cac4d0); }
.dotSuccess  { background: var(--outline-variant, #cac4d0); }
.dotError    { background: var(--error-main, #b3261e); }
.dotActive   { background: var(--primary-main, #6750a4); animation: pulse 1.2s ease-in-out infinite; }
```

---

## 3. TraceDetailDrawer

**Path:** `src/rework/components/shared/molecules/ThoughtTrace/TraceDetailDrawer/TraceDetailDrawer.tsx`

### 3.1 Behaviour

- MUI `<Drawer anchor="right">`, width `640px`, full-screen on `xs`
- Opens when user clicks the detail trigger on any `TraceEntryRow`
- Closed by the × button in the header or by clicking the backdrop

### 3.2 Header

```
[channel · tool name · node/task]                              ×
```

- Typography: `var(--font-subtitle-1)`, weight `600`
- Parts joined by ` · `, built from: `formatChannel(channel)`, tool name (combo
  entries), `extras.node` or `extras.task`
- Background: `var(--background-paper)` — solid readable surface
- `color: var(--on-surface)` — explicit to survive MUI Drawer theme inheritance

### 3.3 Body

Monaco editor filling remaining height:

```typescript
<Editor
  height="100%"
  defaultLanguage="json"
  value={safeStringify(payload, 2)}
  theme={muiMode === 'dark' ? 'vs-dark' : 'vs'}
  options={{
    readOnly: true,
    wordWrap: 'on',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    lineNumbers: 'on',
    automaticLayout: true,
  }}
/>
```

**Payload:**
- `combo` entry: `{ tool_call: ChatMessage, tool_result: ChatMessage | null }`
- `solo` entry: full `ChatMessage`

---

## 4. AssistantTurn

**Path:** `src/rework/components/shared/organisms/AssistantTurn/AssistantTurn.tsx`

### 4.1 Concept

Container organism that groups all output for one assistant exchange.

### 4.2 Vertical Stack

```
┌──────────────────────────────────────── max-width 75% ─────┐
│  ThoughtTrace          (null when no trace steps)           │
│  AssistantMessage      (always present)                     │
│  SourcesPanel          (null when no sources)               │
└─────────────────────────────────────────────────────────────┘
```

- `align-self: flex-start` — left-aligned in the messages column
- `max-width: 75%`
- `display: flex; flex-direction: column; gap: 0` — internal gap owned by children

### 4.3 Props

```typescript
interface AssistantTurnProps {
  message: ConversationMessage;   // the presentation model owned by ManagedChatPage
  isStreaming: boolean;
}
```

`ThoughtTrace` receives the raw `ChatMessage[]` steps filtered to trace channels.
`AssistantMessage` receives the current text and streaming state.
`SourcesPanel` receives `sources` — renders null when the array is empty.

---

## 5. AssistantMessage

**Path:** `src/rework/components/shared/molecules/AssistantMessage/AssistantMessage.tsx`

### 5.1 Layout

Left-aligned bubble, `background: var(--surface-container)`,
`color: var(--on-surface)`, `border-radius: var(--radius-s)`.

No role label — the position (left) conveys the speaker.

### 5.2 Content

- **Phase 6A:** plain text rendered in a `<p>` with `white-space: pre-wrap`
- **Phase 6B:** replaced by `<MarkdownRenderer>` — no structural change to `AssistantMessage`

### 5.3 Streaming Cursor

When `isStreaming === true`, append a `<StreamingCursor />` atom after the text.
Remove it on `final`.

```css
/* StreamingCursor atom */
.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: currentColor;
  margin-left: 1px;
  vertical-align: text-bottom;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}
```

### 5.4 Error State

When `ConversationMessage.error` is set, render a small error chip below the
text instead of (or alongside) the cursor:

```
⚠ Agent error: {error message}
```

- `color: var(--error-main)`, `font: var(--font-label-small)`

---

## 6. UserMessage

**Path:** `src/rework/components/shared/molecules/UserMessage/UserMessage.tsx`

### 6.1 Layout

Right-aligned bubble.

- `align-self: flex-end`
- `max-width: 65%`
- `background: var(--primary-container)`
- `color: var(--on-primary-container)`
- `border-radius: var(--radius-s)`
- `padding: var(--spacing-s) var(--spacing-m)`

### 6.2 Content

Plain text only — no markdown, no streaming cursor.
`white-space: pre-wrap`, `word-break: break-word`.

### 6.3 Timestamp

`opacity: 0` → `1` on bubble hover.
Format: `HH:mm` (locale time).
`font: var(--font-label-small)`, `color: var(--on-surface-retreat)`.
Positioned below the bubble text, right-aligned.

---

## 7. SourcesPanel & SourceCard

**Paths:**
- `src/rework/components/shared/molecules/SourcesPanel/SourcesPanel.tsx`
- `src/rework/components/shared/molecules/SourcesPanel/SourceCard/SourceCard.tsx`

### 7.1 SourcesPanel

Appears below `AssistantMessage` after `final`, only when `sources.length > 0`.

**Header:**
```
Sources  (3)
```
- `font: var(--font-label-medium)`, weight `600`, `var(--on-surface-retreat)`
- `margin-top: var(--spacing-s)`

**Body:** vertical stack of `SourceCard`, `gap: var(--spacing-xs)`.

Collapsible: the "Sources (N)" header toggles the card list.
Default: expanded.

### 7.2 SourceCard

One citation per card.

```
 [1]  Document title here                              87%
      Two-line excerpt of the relevant passage…
      Two-line excerpt continued if needed…
```

| Element | Spec |
|---|---|
| Index badge | `[N]` — `var(--font-label-small)`, monospace, `var(--primary-main)` |
| Title | `var(--font-body-medium)`, weight `500`, single line with ellipsis |
| Score | `N%` right-aligned, `var(--font-label-small)`, `var(--on-surface-retreat)` |
| Excerpt | 2-line clamp, `var(--font-body-small)`, `var(--on-surface-retreat)` |
| Background | `var(--surface-container-low)` |
| Border-radius | `var(--radius-xs)` |
| Padding | `var(--spacing-s)` |

Score derivation: `Math.round(source.score * 100)` — shown only when `source.score`
is a number.

---

## 8. ChatInputBar

**Path:** `src/rework/components/shared/molecules/ChatInputBar/ChatInputBar.tsx`

### 8.1 Layout

Horizontal flex row, `align-items: flex-end`.

```
┌──────────────────────────────────────────────┐  [Send ›]
│  TextArea (auto-grow, max 6 rows)            │
└──────────────────────────────────────────────┘
```

- TextArea takes `flex: 1`
- Send button is an `IconButton` variant (arrow or paper-plane icon) with a
  text fallback accessible label `"Send message"`

### 8.2 Disabled State

Both TextArea and Send button are `disabled` while `isStreaming === true` or
`isLoadingHistory === true`.

### 8.3 Key Behaviour

- `Enter` → submit (calls `onSend`)
- `Shift+Enter` → newline
- Implemented via `onKeyDown` in the parent or passed as a prop

### 8.4 Props

```typescript
interface ChatInputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
  placeholder?: string;
}
```

---

## 9. ChatMessagesArea

**Path:** `src/rework/components/shared/organisms/ChatMessagesArea/ChatMessagesArea.tsx`

### 9.1 Behaviour

- `flex: 1`, `overflow-y: auto`, `display: flex; flex-direction: column`
- `gap: var(--spacing-m)` between turns
- `padding: var(--spacing-m)`
- Auto-scrolls to bottom on new message (via `scrollIntoView` on a bottom anchor ref)
- Auto-scroll is suppressed when the user has manually scrolled up (scroll-lock detection)

### 9.2 Empty State

When no messages and not loading:

```
Send a message to start the conversation.
```

- Centred, `var(--on-surface-retreat)`, `var(--font-body-large)`
- `margin: auto` in the flex column

### 9.3 Loading State

When `isLoadingHistory`:

```
🔄  Loading conversation history…   (animated)
```

- Left-aligned, italic, pulsing opacity animation
- Replaced by messages once loaded

### 9.4 Scroll-Lock Rule

If the user has scrolled up more than `100px` from the bottom, disable
auto-scroll until:
- The user scrolls back to the bottom, OR
- A new user message is sent (force-scroll on send)

This prevents the view jumping while the user reviews earlier messages.

---

## Cross-Cutting Rules

These rules apply to every component in this document.

1. **Design tokens only.** No hardcoded hex colours or pixel values. Every
   visual property uses a `var(--…)` token. This is the contract that makes
   future Figma revisions structural rather than a search-and-replace exercise.

2. **No technical IDs in visible text.** `agent_instance_id`, session UUIDs,
   exchange IDs — never rendered as user-visible strings.

3. **CSS Modules.** One `.module.css` per component. No global class names.
   No inline `style={{}}` except for dynamic values that cannot be expressed
   with a class (e.g. a width derived from state).

4. **No new global state.** All conversation state lives in `ManagedChatPage`
   via `useState`. Components receive data as props and call callbacks.

5. **Accessibility.** Meaningful `aria-label` on icon-only buttons. `role="log"`
   on the messages area. `aria-live="polite"` for streaming updates.
