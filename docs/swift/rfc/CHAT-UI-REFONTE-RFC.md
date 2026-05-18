# RFC — Chat UI Refonte (CHAT-05)

**Status:** in-progress — design validation underway  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-14  
**Backlog ref:** `docs/swift/backlog/CHAT-UI-BACKLOG.md §5`

---

## 1. Problem

Phases CHAT-01 through CHAT-03 delivered a functional managed chat UI.
The implementation works but was built incrementally — each phase patched the
previous one. The result is a page that mixes layout, business logic, and fetch
concerns, with no new generic DS primitives emerging from the work.

The UI is also designed for occasional use. The product is used 4+ hours/day
by expert users. That changes everything about density, hierarchy, and the cost
of visual noise.

This RFC defines a comprehensive redesign that:

1. Enriches the design system with 5 atoms and 7 molecules that are reusable
   outside the chat feature.
2. Decomposes `ManagedChatPage` into a thin composition of organisms, each
   under 150 lines, communicating only through props and callbacks.
3. Establishes the correct visual hierarchy for sustained intensive use.
4. Makes user capabilities (debug, admin) a first-class prop concern, never a
   hidden conditional inside a component.

---

## 2. Design Principles

These principles are binding for all components built under CHAT-05. Any
implementation that violates them must be stopped and redesigned.

### 2.1 Hierarchy of attention

From most to least visually prominent:

1. Assistant response body — this is the content, it dominates everything
2. User question — anchors the context
3. Input field — always accessible, never buried
4. Sources — present but discreet, they support trust
5. Reasoning chain — available but collapsed by default
6. Actions and metadata — appear only when needed
7. Navigation and settings — peripheral

If any secondary element draws the eye more than the response body, it is
over-styled.

### 2.2 Controlled density

Many options to expose, never all at once:

- **Permanent** — critical state only: active source scope, search mode
- **On hover** — contextual actions: copy, edit, regenerate
- **On demand** — detail: full reasoning, source detail, debug

### 2.3 Transitions

Every state change is animated (200–300ms, ease-out). Animations are
utilitarian, not decorative. They answer "what changed and where did it come
from", not "look how smooth this is". No generic spinners — prefer explicit
streaming states ("Searching documents…").

### 2.4 Dark mode as first-class citizen

Design dark first, verify light holds. No hardcoded colour values anywhere.
Every colour, spacing, radius, typography, shadow, and transition goes through
a DS token. If a token is missing, propose its addition rather than hardcoding.

### 2.5 No blocking modals

Drawers only. The conversation stays visible and interactive at all times.
Nothing overlays the input. Focus mode (⌘. / Ctrl.) hides sidebar + reasoning
+ sources and keeps only Q/A/input.

### 2.6 Layout fundamentals — non-negotiable

These rules are not stylistic preferences. Violating any of them makes the
product feel broken to a daily user. They must survive every refactor.

**Single width constraint.**
The 720px centered lane (`max-width: 720px; margin: 0 auto`) is the one and
only place where content width is determined. No component below this level
may impose its own `max-width` or `align-self` to constrain width. The
`RichInputField` uses the same 720px so messages and input share a visible
column edge.

**Scrollbar at the column edge.**
The scroll container is `.chatColumn` — the element that fills the remaining
viewport height after the header. No inner element may carry `overflow-y: auto`
for the main conversation scroll. The scrollbar track must run the full height
of the visible area so users can navigate the entire conversation without
leaving the column.

**Input always visible.**
`RichInputField` uses `position: sticky; bottom: 0` inside the scroll
container. It is never outside the scroll container as a flex sibling — that
would truncate the scrollbar track at the input's top edge.

**Native controls follow the active theme.**
`color-scheme: dark` / `color-scheme: light` must be declared on the
`[data-theme]` selectors in `colors-semantic-dark.css` and
`colors-semantic-light.css`. Without this, the browser renders native
scrollbars, form inputs, and select dropdowns in light mode regardless of
the active theme.

**Streaming auto-scroll respects the user.**
While `isStreaming` is true, the UI scrolls to the bottom on every render —
but only when the user is within 120px of the bottom. If the user has scrolled
up to read history, the auto-scroll is suspended for the rest of that turn.
It resumes automatically on the next turn (when `scrollVersion` increments).

**No blinking cursor during streaming.**
A text cursor (`|`) during streaming is not a professional affordance. The
waiting state (before the first chunk arrives) uses `ThinkingDots` — three
animated dots with a wave. Once text is flowing, the text appearing is the
signal. No cursor element is rendered alongside or after streaming text.

---

## 3. Layout Contract

```
┌─ Sidebar (260px, collapsible) ──┬─── Chat Column (flex:1) — scroll container ┬─ Right Drawer (480–560px, optional) ─┐
│  New conversation button        │  ↑                                ↑ scroll │                                      │
│  History grouped by date        │  ConversationHeader (fixed)       │  bar   │  Source detail / Debug / Settings    │
│  ─────────────────────────────  │  ─────────────────────────────────│──────  │  (InlineDrawer, non-blocking)        │
│  Libraries                      │  ┌─ 720px lane (margin: 0 auto) ──│──────┐ │                                      │
│  Files                          │  │  UserTurn × N                  │      │ │                                      │
│  Agents / Templates             │  │  AssistantTurn × N             │      │ │                                      │
│  Settings                       │  │    ThinkingDots (waiting)      │      │ │                                      │
│                                 │  │    MarkdownRenderer (streaming) │      │ │                                      │
│                                 │  │    HorizontalScrollRow sources  │      │ │                                      │
│                                 │  │    ActionBar (hover)            │      │ │                                      │
│                                 │  └────────────────────────────────┘      │ │                                      │
│                                 │  ─────────────────────────────────│──────  │                                      │
│                                 │  RichInputField (sticky bottom:0)  ↓      │ │                                      │
│                                 │    leftSlot: ContextualPicker × 2         │ │                                      │
│                                 │    rightSlot: send IconButton             │ │                                      │
│                                 │    topSlot: AttachmentChips               │ │                                      │
└─────────────────────────────────┴────────────────────────────────────────────┴──────────────────────────────────────┘

Scroll bar tracks the full Chat Column height (header bottom → browser bottom).
720px lane is the single width constraint — no component inside may add its own.
RichInputField is sticky inside the scroll container, not a flex sibling below it.
```

---

## 4. Component Catalog — Step 1 (validated 2026-05-14)

The workflow requires five validation steps before any component is written.
This section records each step's output as it is validated.

### 4.1 DS primitives — what already exists (do not recreate)

| Component | Level | Notes |
|---|---|---|
| `Button`, `IconButton`, `Icon` | atom | foundation — unchanged |
| `MarkdownRenderer` | molecule | complete |
| `Menu`, `IconButtonMenu` | molecule | popovers available |
| `FullPageModal` + `Portal` | molecule | Portal pattern reused for drawers |
| `ThoughtTrace` | molecule | to be audited: rename if name is chat-specific |
| `SourcesPanel` | molecule | to be refactored: becomes `HorizontalScrollRow` of `SourceCard` |

### 4.2 New atoms to create

| Atom | Intention | Generic reuse beyond chat |
|---|---|---|
| `NumberedChip` | Small chip `[1]` `[2]`, cliquable ou non | Step indicators, footnotes, ordered result lists |
| `AccentBar` | Left-border block wrapper, `color` token param | Callouts, notes, warnings, blockquotes in any DS surface |
| `RestrictedBadge` | Lock icon + short label, non-interactive | Protected content in libraries, agents, admin features |
| `FaviconIcon` | Favicon from URL, fallback to generic doc icon | Link previews, library entries, any external URL display |
| `IndicatorDot` | Coloured status dot, optional pulse animation | Streaming state, connection status, agent execution state |

### 4.3 New molecules to create

| Molecule | Intention | Generic reuse beyond chat |
|---|---|---|
| `CollapsibleBlock` | Expand/collapse inline section — `summary` + `children`, animated | Agent detail sections, changelog entries, long form descriptions |
| `SourceCard` | `FaviconIcon` + 2-line title + domain metadata + optional `RestrictedBadge`, cliquable | Search results, document library items, referenced links |
| `HorizontalScrollRow` | Horizontal scroll with gradient fade at edges indicating overflow | Tag lists, agent chips, any pill list that may overflow |
| `ContextualPicker` | Trigger button showing current selection + popover with options | RAG scope, search policy, model picker, date filters throughout the app |
| `ActionBar` | Row of `IconButton` + tooltips, opacity 0 at rest / 1 on parent hover | Message actions, document card actions, prompt card actions |
| `InlineDrawer` | Non-blocking right-side panel, slides in/out, main content stays interactive | Source detail, debug, settings — replaces all blocking modals in the app |
| `RichInputField` | Auto-growing textarea with `leftSlot`, `rightSlot`, `topSlot` all optional | Comment boxes, search bars with filters, any annotated text input |

### 4.4 Existing components to refactor

| Component | Current issue | Target state |
|---|---|---|
| `ChatInputBar` | Too simple — no slots, no context indicators | Replaced by `RichInputField` with left/right/top slots |
| `SourcesPanel` | Monolithic, chat-specific name | Becomes `HorizontalScrollRow` of `SourceCard` — name `SourcesPanel` retired |
| `ThoughtTrace` | If internals reference chat concepts | Audit — rename to `CollapsibleBlock` wrapper if appropriate |

---

## 5. Steps 2–5 (validated and implemented 2026-05-18)

### 5.1 Step 2 — Organism signatures (validated 2026-05-14)

Organisms and their prop contracts:

| Organism | Props | Notes |
|---|---|---|
| `ConversationHeader` | `agentDisplayName, sessionId, sessionTitle, rightPanelOpen, onTitleCommit, onNewConversation, onToggleRightPanel` | Pure display + callbacks |
| `ConversationThread` | `messages: ThreadMessage[], pendingHitl, isLoading, isStreaming, scrollVersion, onHitlAnswer` | Absorbs message list rendering |
| `UserTurn` | `text, onEdit?` | Wraps `UserMessage` + `ActionBar` |
| `AssistantTurn` | `text, traceMessages, sources, isStreaming` | `CollapsibleBlock` + `HorizontalScrollRow` of `SourceCard`s |

### 5.2 Step 3 — Data model (validated 2026-05-14, implemented 2026-05-18)

File: `src/rework/types/conversation.ts`

- `Message` tree: `parentId: string | null`, `childrenIds: string[]`, `activeChildId: string | null`
- `MessageContent` discriminated union: `{ kind: "text" | "error" | "streaming" }`
- `UserCapabilities` — explicit typed prop, derived once in `useUserCapabilities` hook
- `ConversationSettings` — single object replacing scattered `selectedLibraryIds + searchPolicy + ragScope`
- `DEFAULT_CONVERSATION_SETTINGS` — stable default value, imported where needed

Utilities: `conversationUtils.ts` — `buildConversation`, `activeThread`, `hitToSource`, `chatMessagesToMessage`

### 5.3 Step 4 — Page composition skeleton (validated 2026-05-14, implemented 2026-05-18)

`ManagedChatPage` is 80 lines (14 license header + 66 code). No fetch logic. No business rules.
All state and side-effects live in `useManagedChat`. The page is a thin composition of:
`ConversationHeader` + `ConversationThread` + `RichInputField` + `AgentOptionsPanel`.

### 5.4 Step 5 — Implementation order (validated 2026-05-14, implemented 2026-05-18)

Delivered in waves, each independently demonstrable:

| Wave | Deliverables |
|---|---|
| 0 | `conversation.ts` types |
| 1 | 5 atoms: `IndicatorDot`, `AccentBar`, `RestrictedBadge`, `NumberedChip`, `FaviconIcon` |
| 2 | 4 molecules: `CollapsibleBlock`, `HorizontalScrollRow`, `ActionBar`, `InlineDrawer` |
| 3 | 2 molecules: `SourceCard`, `ContextualPicker` |
| 4 | 2 molecules: `SessionTitleEditor`, `RichInputField` |
| 5 | Utils + hooks: `conversationUtils.ts`, `useUserCapabilities`, `useSessionManager` |
| 6 | Organisms: `UserTurn` (new), `AssistantTurn` (refactored internals) |
| 7 | Organisms: `ConversationHeader`, `ConversationThread` |
| 8 | `ManagedChatPage` refactored to 80 lines via `useManagedChat` hook |

---

## 6. Alternatives considered

**Keep CHAT-03 approach, patch forward**  
Rejected. CHAT-03 produces a working UI but creates no reusable DS primitives.
The debt compounds with each phase. The refonte is the lower long-term cost.

**Separate "DS enrichment" sprint, chat later**  
Rejected. The DS primitives are best designed in the context of their first
real use case. Abstract-first design produces primitives that fit nothing well.

**Full rewrite of `ManagedChatPage` in one PR**  
Rejected. Big-bang rewrites create merge conflicts and regression risk. The
five-step validation process forces incremental delivery: each atom is usable
and reviewed before molecules are built on top.

---

## 7. Impact on existing contracts

- `useChatSse` — unchanged. This RFC does not touch the SSE execution wire.
- `controlPlaneOpenApi` — unchanged. Session metadata reads stay as-is.
- `ManagedChatPage` — shrinks from ~400 lines to under 80. Decomposed into
  organisms. No logic change — only structural reorganisation.
- `ChatInputBar` — deprecated in favour of `RichInputField`. Removal after
  `RichInputField` is stable.
- `SourcesPanel` — deprecated in favour of `HorizontalScrollRow` + `SourceCard`.
  Removal after organisms are migrated.
- Design tokens — new tokens may be proposed for missing semantic values
  (e.g. streaming accent colour, restricted content indicator). All proposals
  go through the token addition process before use.
