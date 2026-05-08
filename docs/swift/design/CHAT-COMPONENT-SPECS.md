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

## §0. Visual Design Reference — fredk8\_chat\_v5

> **Authority:** this section takes precedence over any visual spec in §1–9 where they
> diverge. Behavioural and data-model specs (props, SSE mapping, state shape) remain
> in their original sections.

### 0.1 Token Mapping

The mockup uses short token names. The canonical codebase tokens are below.
**Never add new CSS variables** — use only what exists in
`src/styles/colors-semantic-{light,dark}.css`, `radius.css`, `typography.css`.

| Mockup token | Codebase token | Value (light) |
|---|---|---|
| `--color-text-primary` | `--on-surface` | cold-grey-10 |
| `--color-text-secondary` | `--on-surface-retreat` | cold-grey-30 |
| `--color-text-tertiary` | `--on-surface-muted` | cold-grey-40 |
| `--color-background-primary` | `--surface-main` | cold-grey-98 |
| `--color-background-secondary` | `--surface-container` | cold-grey-94 |
| `--color-border-tertiary` | `--outline-muted` | cold-grey-80 |
| `--color-border-secondary` | `--outline-retreat` | cold-grey-80 |
| `--font-sans` | `--font-family-base` | "Geist", sans-serif |
| `--border-radius-lg` (12 px) | `--radius-m` (16 px) | closest available |
| `--border-radius-md` (8 px) | `--radius-s` (8 px) | exact |

### 0.2 Hardcoded Accent Colors (accepted exceptions)

These two accent values are stable in both light and dark themes and
are the only permitted hardcoded colors:

| Usage | Value | Where |
|---|---|---|
| Chain-of-thought / ThoughtTrace left border | `#9FE1CB` (teal-200) | `.thoughtBorder` |
| Source card active / selected border | `#5DCAA5` (teal-400) | `.sourceCardActive` |
| AgentOptionsPanel modified-value dot | `#EF9F27` (amber-400) | `.dotModified` |
| AgentOptionsPanel checkbox / multicheck accent | `#1D9E75` (teal-600) | `accent-color` |

### 0.3 Divergences from Previous Specs

The following sections of this document are **superseded** by the mockup design:

| Section | Old spec | New direction |
|---|---|---|
| §1 ThoughtTrace visual | Vertical timeline with dots | Left-border accordion — see §0.4 |
| §7 SourcesPanel layout | Vertical card stack | Horizontal scrollable row — see §0.5 |
| §8 ChatInputBar | TextArea + send IconButton | Borderless textarea, no send button — see §0.6 |
| §6 UserMessage | `background: --primary-container` | `background: --surface-container`, `border: 0.5px solid --outline-muted`, `border-radius: 16px 16px 4px 16px` |

Behavioural specs (data model, SSE wiring, props) remain unchanged in §1–9.

### 0.4 ThoughtTrace — Updated Visual

Replaces the "vertical timeline with dots" described in §1.4–1.8.

```css
.thoughtTrace {
  border-left: 1.5px solid #9FE1CB;
  padding: 5px 10px;
  margin-bottom: var(--spacing-m);
  cursor: pointer;
}

.thoughtHeader {
  display: flex;
  align-items: center;
  gap: 6px;
  font: var(--font-label-small);           /* 11px, weight 500 */
  color: var(--on-surface-retreat);
  letter-spacing: 0.04em;
  user-select: none;
}

.chevron {
  transition: transform 0.18s ease;
}
.chevron[data-open="true"] { transform: rotate(180deg); }

.thoughtBody {
  font-size: 12px;
  color: var(--on-surface-retreat);
  line-height: 1.6;
  padding-top: 4px;
}
```

- Header label: `"Raisonnement"` while streaming, `"Raisonnement (Xms)"` after `final`.
- Collapsed by default after `final`. Open by default while streaming.
- `▾` chevron rotates to `▴` when expanded.

### 0.5 SourcesPanel — Updated Visual

Replaces the vertical stack in §7.1.

- Label: `font-size: 11px`, `color: var(--on-surface-muted)`, `margin-top: var(--spacing-s)`
- Cards: **horizontal scrollable row**, `display: flex`, `gap: 6px`, `overflow-x: auto`
- Each card: `width: 148px`, `flex-shrink: 0`, `border: 0.5px solid var(--outline-muted)`,
  `border-radius: var(--radius-s)`, `padding: 8px 10px`
- Active card (selected): `border-color: #5DCAA5`
- Click on a card → inline extract panel expands **below the full card row**
  (`border-radius: var(--radius-s)`, `background: var(--surface-container)`, collapsible)

### 0.6 ChatInputBar — Updated Visual

Replaces the TextArea+IconButton layout in §8.1.

**No border on the textarea. No send button. `Enter` submits.**

```css
.inputArea {
  padding: 12px 24px 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  border-top: 0.5px solid var(--outline-muted);
}

.inputBox {
  width: 100%;
  max-width: 560px;
}

textarea {
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  resize: none;
  font-size: 15px;
  font-family: var(--font-family-base);
  color: var(--on-surface);
  line-height: 1.6;
}

textarea::placeholder {
  color: var(--on-surface-muted);
}

.hint {
  font-size: 11px;
  color: var(--on-surface-muted);
  text-align: center;
}
```

Hint text: `"Les agents Fred peuvent faire des erreurs · Shift+Entrée pour sauter une ligne"`

### 0.7 Responsive Breakpoints

| Breakpoint | Behaviour |
|---|---|
| `> 1024px` | Full layout, right panel can expand |
| `640–1024px` | Right panel collapsed by default, input `max-width: 100%` |
| `< 640px` | Right panel as overlay drawer, padding `12px 16px`, user bubble `max-width: 85%` |

- Use `height: 100dvh` (not `100vh`) — mobile Safari fix.
- `overflow-x: hidden` on the page shell.

---

## Table of Contents

- [§0. Visual Design Reference](#0-visual-design-reference--fredk8_chat_v5) ← **start here**
1. [ThoughtTrace](#1-thoughttrace) *(visual superseded by §0.4)*
2. [TraceEntryRow](#2-traceentryrow)
3. [TraceDetailDrawer](#3-tracedetaildrawer)
4. [AssistantTurn](#4-assistantturn)
5. [AssistantMessage](#5-assistantmessage)
6. [UserMessage](#6-usermessage) *(visual superseded by §0.3)*
7. [SourcesPanel & SourceCard](#7-sourcespanel--sourcecard) *(layout superseded by §0.5)*
8. [ChatInputBar](#8-chatinputbar) *(visual superseded by §0.6)*
9. [ChatMessagesArea](#9-chatmessagesarea)
10. [Page Layout — ManagedChatPage](#10-page-layout--managedchatpage)
11. [AgentOptionsPanel](#11-agentoptionspanel-right-sidebar)

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
- `1.5px` solid `var(--outline-muted)`, positioned `10px` from the left edge
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
| Active (streaming, no result yet) | `var(--primary)` | `pulse` keyframe, 1.2 s ease-in-out |
| Success | `var(--outline-muted)` | None |
| Error | `var(--error)` | None |
| Neutral (non-tool solo) | `var(--outline-muted)` | None |

```css
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--primary) 40%, transparent); }
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
  background: var(--outline-muted, #cac4d0);
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
| Index | `auto`, hover-only | `12px` monospace, `var(--on-surface-muted)`, `opacity: 0` → `1` on row hover |
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
  font-family: var(--font-family-base);
  padding: var(--spacing-2xs, 0.25rem) var(--spacing-xs, 0.5rem);
  border-radius: var(--radius-xs, 0.25rem);
  transition: background 0.1s;
}

.row:hover {
  background: var(--surface-container-low);
}

.index {
  font-family: monospace;
  font-size: 12px;
  color: var(--on-surface-muted);
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

.dotNeutral  { background: var(--outline-muted, #cac4d0); }
.dotSuccess  { background: var(--outline-muted, #cac4d0); }
.dotError    { background: var(--error, #b3261e); }
.dotActive   { background: var(--primary, #6750a4); animation: pulse 1.2s ease-in-out infinite; }
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

- Typography: `var(--font-title-medium)`, weight `600`
- Parts joined by ` · `, built from: `formatChannel(channel)`, tool name (combo
  entries), `extras.node` or `extras.task`
- Background: `var(--surface-container)` — solid readable surface
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

Left-aligned bubble. Above the bubble, the agent display name is shown as a small
label — this is the only place a role/name label appears in the message stream.

```
fred-doc-hr                          ← agent name label
┌────────────────────────────────┐
│  Response text…                │  ← bubble
└────────────────────────────────┘
```

**Agent name label:**
- `font-size: 11px`, `font-weight: 500`, `letter-spacing: 0.04em`
- `color: var(--on-surface-muted)`
- Source: `ManagedAgentInstanceSummary.display_name` — never the UUID

**Bubble:**
- `background: var(--surface-container)`, `color: var(--on-surface)`
- `border-radius: var(--radius-s)` (8 px)
- No border.

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

- `color: var(--error)`, `font: var(--font-label-small)`

---

## 6. UserMessage

**Path:** `src/rework/components/shared/molecules/UserMessage/UserMessage.tsx`

### 6.1 Layout

Right-aligned bubble. *(Visual spec from §0.3 — supersedes original.)*

- `align-self: flex-end`
- `max-width: 65%` (85% on mobile < 640px)
- `background: var(--surface-container)`
- `color: var(--on-surface)`
- `border: 0.5px solid var(--outline-muted)`
- `border-radius: 16px 16px 4px 16px`   ← top-right stays round, bottom-right pointed
- `padding: var(--spacing-s) var(--spacing-m)`
- `font-size: 14px`, `line-height: 1.5`

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
| Index badge | `[N]` — `var(--font-label-small)`, monospace, `var(--primary)` |
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

## 10. Page Layout — ManagedChatPage

**Path:** `src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`

### 10.1 Shell Structure

```
┌──────────────────────────────────────────┬────────────┐
│                                          │            │
│         ChatMessagesArea                 │  Agent     │
│         (flex: 1, overflow-y: auto)      │  Options   │
│                                          │  Panel     │
│                                          │  (right,   │
│                                          │  fixed w)  │
├──────────────────────────────────────────┴────────────┤
│              ChatInputBar (centred, max-w 560px)       │
└────────────────────────────────────────────────────────┘
```

```css
.shell {
  display: flex;
  flex-direction: row;
  height: 100dvh;          /* dvh for mobile Safari */
  overflow: hidden;
}

.chatColumn {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* ChatMessagesArea fills remaining height */
/* ChatInputBar sits at the bottom of .chatColumn */
```

- The left `ChatList` sidebar is **outside** this shell — it belongs to the parent
  route layout, not `ManagedChatPage`.
- The right `AgentOptionsPanel` is a sibling of `.chatColumn` inside `.shell`.
- The input bar is inside `.chatColumn` and is **not** affected by the right panel width —
  it centres within `.chatColumn`, not the full viewport.

### 10.2 Message Padding and Spacing

| Zone | Desktop | Mobile (< 640px) |
|---|---|---|
| Messages area padding | `20px 24px` | `16px` |
| Gap between exchanges | `20px` | `16px` |
| Input bar padding | `12px 24px 14px` | `12px 16px` |

### 10.3 Header

The chat header sits at the top of `.chatColumn`.

| Element | Source | Note |
|---|---|---|
| Agent name | `ManagedAgentInstanceSummary.display_name` | Prominent — never show UUID |
| Team context | `FrontendBootstrap.active_team.display_name` | Secondary label |
| "New chat" button | Local action | Clears state, generates new `session_id` |
| Panel toggle button | `AgentOptionsPanel` open/close | Hidden when `options === null` |

---

## 11. AgentOptionsPanel (Right Sidebar)

**Path:** `src/rework/components/shared/organisms/AgentOptionsPanel/AgentOptionsPanel.tsx`

### 11.1 Concept

A collapsible right panel that renders agent-declared options generically.
The panel knows nothing about specific agents — it receives `AgentOption[]` as props
and renders controls. Options are serialised and injected into each runtime request.

### 11.2 Props

```typescript
interface AgentOption {
  id: string
  icon: string          // single unicode character
  label: string
  type: 'select' | 'multicheck' | 'slider' | 'file' | 'action'
  default?: unknown
  value?: unknown
  tooltip?: string      // shown below the control when present
  // for type 'select'
  choices?: string[]
  // for type 'multicheck'
  items?: string[]
  // for type 'slider'
  min?: number
  max?: number
  step?: number
  // for type 'action'
  hint?: string         // text shown/hidden on click
}

interface AgentOptionsPanelProps {
  options: AgentOption[] | null
  values: Record<string, unknown>
  onChange: (id: string, value: unknown) => void
}
```

`values` and `onChange` are owned by `ManagedChatPage`. They are passed to the runtime
request at send time (field name TBD with backend — document here when defined).

### 11.3 Presence Rule

`options === null || options.length === 0` → panel is **completely absent** from the DOM.
The panel toggle button in the header is also hidden.

### 11.4 Collapsed State (28 px wide)

```css
.panelCollapsed {
  width: 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding-top: 8px;
  background: transparent;
}
```

- Toggle chevron at the top
- One `6px × 6px` dot per option, `border-radius: 50%`, `background: var(--outline-muted)`
- If `value !== default` for that option: orange indicator dot `4px`, `background: #EF9F27`,
  `position: absolute; top: -1px; right: -1px`

### 11.5 Expanded State (200 px wide)

```css
.panelExpanded {
  width: 200px;
  transition: width 0.22s ease;
  background: transparent;
  border: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 6px;
  overflow-y: auto;
}
```

No column background, no left border. Cards float on the page background.

On mobile (< 640px): overlay drawer from the right, semi-transparent backdrop,
closed by tap outside.

### 11.6 Option Cards (select / multicheck / slider / file)

```css
.optionCard {
  border: 0.5px solid var(--outline-muted);
  border-radius: var(--radius-m);      /* 16px */
  background: var(--surface-container-lowest);
}

.optionCard:hover {
  border-color: var(--outline-retreat);
}

.optionCardHeader {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  cursor: pointer;
}

.optionIcon   { font-size: 12px; opacity: 0.5; }
.optionLabel  { font-size: 11px; color: var(--on-surface-retreat); flex: 1; }
.optionChevron { transition: transform 0.15s; }
/* rotate 180° when expanded */

.optionBody {
  padding: 0 8px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--on-surface);
}

.optionTooltip {
  font-size: 10px;
  color: var(--on-surface-muted);
  border-top: 0.5px solid var(--outline-muted);
  padding-top: 4px;
  margin-top: 4px;
}
```

- Card body is **collapsed by default**; click header to expand.
- Orange dot (`#EF9F27`, 4 px) appears on header AND on the current value
  display when `value !== default`.
- `multicheck` uses `accent-color: #1D9E75` on checkboxes.

### 11.7 Action Cards (type: action)

- No chevron, no dot.
- Icon `opacity: 0.35`.
- Click → hint text appears/disappears below the title (toggle).
- Hover: `color: var(--on-surface)` on the title.

---

## Cross-Cutting Rules

These rules apply to every component in this document.

1. **Design tokens only.** No hardcoded hex values except the four functional
   accents listed in §0.2. Every other visual property uses a `var(--…)` token
   from the existing codebase — never invent new variables.

2. **No technical IDs in visible text.** `agent_instance_id`, session UUIDs,
   exchange IDs — never rendered as user-visible strings.

3. **CSS Modules.** One `.module.css` per component. No global class names.
   No inline `style={{}}` except for dynamic values that cannot be expressed
   with a class (e.g. a width derived from state).

4. **No new global state.** All conversation state lives in `ManagedChatPage`
   via `useState`. Components receive data as props and call callbacks.

5. **Accessibility.** Meaningful `aria-label` on icon-only buttons. `role="log"`
   on the messages area. `aria-live="polite"` for streaming updates.

6. **Both themes.** Every component must be tested in light and dark mode before
   marking done. The four hardcoded accent colors in §0.2 are the only values
   validated for both themes — all others must use tokens.
