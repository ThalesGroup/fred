# Conversation Outline Rail RFC — navigating a long chat session

**Status:** Agreed, not yet built — V1 design settled 2026-09-09, no open
question. §6 lists what V1 deliberately leaves out to ship fast; those are
revisitable, not closed.
**ID:** `CHAT-OUTLINE-01` (informal label, no registry)
**Author:** Maxime
**Date:** 2026-09-09

---

## 1. Problem statement

A long managed-chat session has no navigation affordance. `ConversationThread`
renders every turn into one scroll container and the only way back to an
earlier exchange is to scroll and read until you recognise it. There is no
overview of the session's shape, no way to jump, and nothing that says where
in the conversation the current viewport sits.

The thread is not virtualised — `ConversationThread.tsx` maps `ThreadMessage[]`
straight to `UserTurn` / `AssistantTurn` — so every turn already has a real DOM
node. The missing piece is purely a navigation surface, not a data or rendering
change.

---

## 2. Proposed solution — a graphical outline rail

A thin vertical rail of marks along the left edge of the conversation column,
one mark per exchange, centred vertically. Marks carry no text: they are small
flattened shapes, narrow enough not to eat into the reading column. Hovering a
mark reveals a preview tile; clicking it jumps to that turn.

`.mainColumn` (`ManagedChatPage.module.css`) is already `position: relative`,
and the message lane is capped at 720px centred (`ChatMessagesArea.module.css`),
so at usual widths the rail sits in existing empty gutter and takes no width
from the reading column.

### 2.1 Magnification on hover

Hovering magnifies the hovered mark **and its two neighbours on each side**,
with a decreasing step, so the rail reads as a continuous deformation rather
than one mark popping alone.

The falloff is **discrete, not pointer-distance based**, and therefore expressed
in CSS through sibling combinators — no JavaScript runs on pointer movement.
A continuous Dock-style falloff was considered and rejected in §4.

### 2.2 Preview tile

The hovered mark shows a tile to its left, vertically centred on the mark, 12px
gap, containing:

| Content | Style | Limit |
|---|---|---|
| First sentence of the user request that opened the turn | `--font-label-large`, `--on-surface` | 2 lines, ellipsis |
| First two sentences of the agent's answer | `--font-body-medium`, `--on-surface-retreat` | 4 lines, ellipsis |

This reuses the existing `Tooltip` atom rather than adding a component: it
already supports `placement="left"` (panel left of the trigger, vertically
centred on it, flipping right when there is no room) and `content` for rich
nodes that widen and wrap. The only gap is `TOOLTIP_GAP_PX = 4`, hardcoded to
match `--spacing-2xs`; the tile needs 12px, so `Tooltip` gains an optional gap
prop. No new molecule.

### 2.3 Three mark heights

Marks take one of three heights, to give the rail a recognisable shape and let
the reader aim at "the long one in the middle".

The height is driven by the **character count of the agent's answer text**,
against **absolute** thresholds:

| Height | Answer length | Roughly |
|---|---|---|
| short | < 400 chars | a direct reply, one paragraph |
| medium | 400 – 1500 chars | a normal answer |
| tall | > 1500 chars | a long, structured analysis |

Thresholds are a starting point, to calibrate against real sessions.

Two rejected alternatives, both tempting:

- **Token counts.** Available per turn, but a ReAct turn re-sends the whole
  context on every model call, so `tokenUsage` grows with the session's age
  rather than with the turn's substance — the rail would show "everything gets
  bigger towards the end", which is false. `marginalTokenUsage` is the honest
  variant but is nullable on Graph agents and pre-#2403 history, which would
  make the rail inconsistent across sessions.
- **Relative thresholds** (terciles within the session). Always produces
  contrast, but a mark's height then *changes as the session grows*: the tall
  block you remember shrinks when a longer turn arrives. The rail is a spatial
  memory aid, and that memory is destroyed if marks move under the reader.
  Absolute thresholds are stable by construction.

### 2.4 Scroll-spy

The mark whose turn currently occupies the viewport is rendered in `--primary`.
Implemented with a single `IntersectionObserver` over the turn nodes — passive,
browser-side, firing only on threshold crossings, never per frame.

### 2.5 Rail overflow

While the marks fit, the rail is centred vertically. Once they exceed the
available height, the rail becomes its own scroll container, **bottom-aligned**:
new turns stack at the bottom and stay visible, old ones leave through the top —
the same reading model as the conversation itself. Expressible in CSS, no JS.

When scroll-spy marks a turn that is outside the rail's visible range (the
reader scrolled far back), the rail scrolls itself to reveal the active mark.

This rail scroll is on an element separate from the conversation container and
so does not interact with §3 at all.

---

## 3. Scroll ownership — why the rail is inert while a turn is live

`useChatAutoScroll` documents itself as the *sole owner* of the conversation
container's scroll position, on the grounds that a second mechanism on the same
element cannot be reasoned about. That is not a stylistic rule: while a turn is
live the hook re-decides the position on every animation frame and eases the
view towards its target, so any position written from outside is overwritten
one frame later. A jump-to-turn would appear to work on a finished conversation
and judder or silently fail while the agent is writing — a frame-timing bug,
therefore intermittent, therefore the kind that survives review.

**Decision: the rail is frozen and non-interactive while a turn is live**
(`isStreaming || isAwaitingHuman`) — visible but dimmed, clicks inert, contents
not recomputed. The mark for the running turn appears when its answer
completes.

This dissolves the conflict rather than working around it. The hook only ever
writes while a turn is live (`shouldFollowBottom` returns false in the `idle`
phase, so `follow()` returns before touching anything). If the rail can only be
clicked when the hook is quiescent, the two writers never overlap — the
invariant holds by construction, not by timing luck.

The hook needs **no behavioural change**. Its scroll listener already
interprets an outside jump correctly: a jump upwards reads as "the reader left
the bottom" and stops the follow, a jump to the end re-arms it. What does need
changing is the ownership comment itself — a future reader must find the
refined invariant ("sole owner while a turn is live; the outline rail may
scroll it while idle, and here is why that is safe") stated where the rule
lives, not only in this RFC.

**Known edge to handle at implementation:** a jump animation still in flight
when a new turn starts would race the hook's `turnKey` jump-to-bottom. Narrow
(it requires sending a message within the animation's duration of clicking a
mark) but real — the in-flight jump is cancelled when a turn starts.

Rendering the rail interactive during streaming is deliberately deferred, not
ruled out; it would require giving the hook an explicit jump command so the
jump declares its intent instead of writing pixels behind the hook's back.

---

## 4. Performance constraints

The rail must not cost anything on the chat's rendering path. Three specific
hazards, each with its decided answer:

1. **Per-keystroke re-render.** `ManagedChatPage` re-renders on every composer
   keystroke; `ConversationThread` is `memo()`-wrapped precisely because
   without that boundary every historical message re-rendered, markdown
   re-parse included, on every character typed (#2221). The rail derives from
   `messages` and must sit behind the same kind of boundary — memoised
   component, derived data in a `useMemo` keyed on the message list.

2. **Per-token recomputation.** During streaming the message list changes on
   every token received. Computing preview extracts for all turns on each
   change would redo string work across the whole conversation tens of times a
   second — #2221 again, worse. Two decisions close this: the rail's contents
   are frozen while a turn is live (§3), and extracts are computed **on hover,
   for the hovered turn only**.

3. **Extract cost at hover time.** Doing the work on hover is safe because it is
   one turn, once: string work on a few thousand characters, microseconds,
   far below a 16ms frame. Bounded further by slicing the first ~500 characters
   *before* sentence detection, making the cost constant regardless of answer
   size, and memoised per turn id so a second hover is free.

Continuous pointer-distance magnification is rejected on the same grounds: it
requires a `pointermove` listener writing per-mark values every frame, on a
surface that sits over the chat. The discrete falloff (§2.1) is CSS-only, costs
nothing, and is visually close enough.

---

## 5. Impact on existing contracts

| Contract / file | Change |
|---|---|
| `CONTROL-PLANE-PRODUCT-CONTRACT.md` | None — no API involved |
| `RUNTIME-EXECUTION-CONTRACT.md` | None |
| Generated API clients | None — the rail derives entirely from `ThreadMessage[]`, already in the frontend |
| `Tooltip` atom | Gains an optional gap prop (currently `TOOLTIP_GAP_PX = 4` hardcoded) |
| `useChatAutoScroll` | No logic change; its sole-owner comment is amended to state the refined invariant (§3) |
| `COMPONENT-UX.md` | New entry once implemented: the outline rail, its states, and the frozen-during-streaming behaviour |

Frontend-only. No backend, no schema, no SSE contract, no OpenAPI regeneration.

---

## 6. Out of scope for V1

Deferred by developer decision (2026-09-09) **to ship a first version quickly
and at low risk** — not because any of them was judged unnecessary. Each is
explicitly open to revisiting once the rail is in use and new ideas surface;
none of these decisions constrains a later iteration.

- **Narrow-viewport behaviour.** The rail lives in the gutter left by the 720px
  lane; what happens when that gutter disappears is not decided here.
- **Keyboard accessibility.** No tab order, arrow-key navigation, or
  focus-triggered preview tile in this iteration.
- **HITL rows.** `hitl_request` / `hitl_response` get no special treatment.
- **Interactivity during streaming.** See §3, which also sketches what taking
  it on would require.
