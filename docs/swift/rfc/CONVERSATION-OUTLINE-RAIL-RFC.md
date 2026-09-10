# Conversation Outline Rail RFC — what V1 left open

**Status:** V1 shipped 2026-09-09 (issue #2602). The design and its rationale
now live in `docs/swift/ux/COMPONENT-UX.md` — "Conversation outline rail". This
file is trimmed to the parts that are still genuinely open.
**ID:** `CHAT-OUTLINE-01` (informal label, no registry)
**Author:** Maxime
**Date:** 2026-09-09

---

## What shipped

A rail of graphical marks along the conversation's left edge in
`ManagedChatPage`: one per turn, all the same size, with discrete hover
magnification over two neighbours each side, a preview tile, a scroll-spy
active mark, and an animated jump. Inert while a turn is live, which is what
keeps it clear of `useChatAutoScroll`'s ownership of the scroll position.

Mark heights varying with the answer's length were built and dropped
(2026-09-09): the rail reads better saying only where the turns are.

Read `COMPONENT-UX.md` for the behaviour and the reasoning behind each choice.
Nothing about V1 is still under discussion, so it is not restated here.

---

## Deferred from V1 — open, not decided against

These were set aside to ship a first version quickly and at low risk, **not**
because any was judged unnecessary. Each is open to revisiting once the rail
has been in use.

### 1. Narrow viewports

The rail sits against the page's left edge, and the message lane is centred and
capped at 720px. On a column barely wider than the lane — one with a side panel
open — there is no gutter left, so the rail lands **on top of the first
characters of every line and captures the pointer there**: clicks and text
selection over that strip go to the rail, not the conversation. That is the
concrete cost of the current placement, accepted for V1 rather than overlooked.

Anchoring the rail to the lane instead was tried and rejected: it kept the rail
clear of the text, but made it drift inward with the reading column instead of
staying where the eye learns to find it. So the answer is not simply to move it
back — hiding it, collapsing it to a thinner form, or overlaying it only on
demand are all still open.

### 2. Keyboard access

V1 marks the rail `aria-hidden` and keeps its marks out of the tab order,
because a row of unlabelled marks announced by a screen reader is worse than
silence. Making it genuinely reachable is a real piece of work — labels
(probably the same first sentence the tile shows), a tab stop with arrow-key
movement between marks, and the preview tile on focus as well as hover — not
just removing the attribute.

### 3. HITL rows

`hitl_request` / `hitl_response` currently get no marks. Whether a gate the
reader had to answer is worth navigating back to is a product question nobody
has needed to answer yet.

### 4. Interactivity while a turn streams

The rail is deliberately frozen while a turn is live. Making it clickable there
is possible but not free: the jump would have to declare its intent to
`useChatAutoScroll` — an explicit command on the hook that owns the scroll
position — rather than writing pixels behind its back, and the hook would have
to decide what a mid-turn jump means for its follow state. Worth doing only if
readers actually reach for the rail while an answer is being written.

---

## Wheel gestures over the rail

Not deferred so much as accepted, and worth revisiting if anyone reports it.
The rail is a sibling of the scroll container, so a wheel gesture over it has no
scrollable ancestor to chain to. V1 shrinks the rail to its marks so that
surface is only the few pixels the reader is deliberately pointing at, where
scrolling the rail is a reasonable reading of the gesture. If that proves
annoying, the fix is to forward the wheel to the conversation — safe for the
same reason the jump is, since the rail only takes input while the autoscroll is
quiescent.
