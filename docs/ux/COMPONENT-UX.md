# Component UX State

Tracks UX review status for every implemented chat UI component.

**Two separate concerns:**
- **Functional** (`[x]`) — component exists, data flows correctly, no TypeScript errors.
- **UX-reviewed** (`[ux]`) — a designer or product owner has validated the visual rendering,
  proportions, and interaction behaviour. Not a code review — a design review.

A component can be `[x]` functional and still have open UX issues. This file is the canonical
list of those issues, organized per component. It feeds the UX review session agenda.

**Related:** implementation tasks → [`docs/backlog/CHAT-UI-BACKLOG.md`](../backlog/CHAT-UI-BACKLOG.md)
| visual specs → [`docs/design/CHAT-COMPONENT-SPECS.md`](../design/CHAT-COMPONENT-SPECS.md)

---

## Design token reference

Token names confirmed from `src/styles/colors-semantic-{light,dark}.css`.
Use **only** these names — no hardcoded hex fallbacks for color tokens.

| Purpose | Correct token | Common wrong names |
|---|---|---|
| Elevated surface (hover states) | `--surface-container-hight` | ~~`--surface-container-high`~~ (missing `h`) |
| Surfaces | `--surface-container`, `--surface-container-low`, `--surface-container-lowest`, `--surface-container-highest` | |
| Text | `--on-surface`, `--on-surface-retreat`, `--on-surface-muted` | ~~`--on-surface-variant`~~ (doesn't exist) |
| Status colours | `--success`, `--error`, `--warning`, `--primary` | ~~`--success-main`~~, ~~`--error-main`~~, ~~`--warning-main`~~, ~~`--primary-main`~~ |
| Borders | `--outline-muted` | |

Spacing and font tokens (`--spacing-*`, `--font-*`, `--radius-*`) are safe to use with numeric fallbacks since they are theme-neutral.

---

## How to use this file

- When you implement a component, add a row here with status `Functional`.
- When you notice a visual problem, add it under **Open UX issues** with enough context
  for a designer to reproduce without running the app.
- After a UX review session, move resolved items to **Resolved** and update the status.
- The **UX review agenda** section at the bottom collects the priority order for the next session.

---

## Status legend

| Status | Meaning |
|---|---|
| `Functional` | Code works, not yet design-reviewed |
| `Needs revision` | Design review revealed issues, not yet fixed |
| `Approved` | Designer + product owner signed off |

---

## Components

---

### `ThoughtTrace`

**Location:** `src/rework/components/shared/molecules/ThoughtTrace/ThoughtTrace.tsx`
**Spec:** [`CHAT-COMPONENT-SPECS.md §1`](../design/CHAT-COMPONENT-SPECS.md)
**Status:** `Functional`

#### Open UX issues

- **Column width** — `ThoughtTrace` is now in a fixed 210px left column alongside the agent
  response. Validate this width at different viewport sizes: is 210px too wide on small
  screens, and should it collapse below a breakpoint? On mobile the two-column layout
  likely needs to stack vertically.

- **Label chip style** — channel labels (`THOUGHT`, `TOOL_CALL`, etc.) are uppercase
  monospace on a light background. May be too visually heavy for secondary UI. Consider
  lowercase with a subtler pill, or icon-only at narrow widths.

- **Collapse behaviour** — the accordion collapses only when `done=true` is passed, but
  "done" is inferred from `finalMessages.length > 0`. During history load all turns
  arrive simultaneously, so all `ThoughtTrace` blocks start collapsed even for past turns.
  Discuss: should past turns always be collapsed, or should the most recent one start open?

- **Timeline guideline alignment** — the vertical guideline (`.guideline`) is positioned
  at `left: 16px` in the parent but the dot in `TraceEntryRow` is in a grid column.
  Verify the guideline visually threads through the dots on all viewport widths.

- **Chevron legibility** — the `›` character used as chevron may render inconsistently
  across operating systems. Consider replacing with an SVG icon from the existing `Icon`
  atom.

#### Resolved

_(none yet)_

---

### `TraceEntryRow`

**Location:** `src/rework/components/shared/molecules/ThoughtTrace/TraceEntryRow/TraceEntryRow.tsx`
**Spec:** [`CHAT-COMPONENT-SPECS.md §2`](../design/CHAT-COMPONENT-SPECS.md)
**Status:** `Functional`

#### Open UX issues

- **Grid column widths** — `grid-template-columns: 10px 20px auto 1fr` means the channel
  label column (`auto`) can grow unbounded for long channel names. Consider `max-width` on
  the label chip or a fixed column width.

- **Primary text truncation** — text truncates with `text-overflow: ellipsis` at the grid
  boundary. Confirm with designer whether one-line truncation is acceptable or whether two
  lines are preferable for `thought` entries (which often have longer text).

- **Secondary text (result summary)** — the `.secondary` grid row starts at column 4,
  which visually aligns it under the primary text but skips the dot + index + label
  columns. Confirm this is the intended layout.

- **Hover-reveal index** — the index number appears on row hover. This is a subtle
  affordance. Validate whether it is discoverable enough, or if a permanent light indicator
  is better.

#### Resolved

_(none yet)_

---

### `TraceDetailDrawer`

**Location:** `src/rework/components/shared/molecules/ThoughtTrace/TraceDetailDrawer/TraceDetailDrawer.tsx`
**Spec:** [`CHAT-COMPONENT-SPECS.md §3`](../design/CHAT-COMPONENT-SPECS.md)
**Status:** `Functional`

#### Open UX issues

- **Theme** — Monaco is always `vs-dark`. The spec says theme-aware (`vs` / `vs-dark`
  following MUI palette mode). Not yet wired to the app theme context.

- **Drawer width** — `min(480px, 90vw)`. The spec mentions ≥ 720px for debug drawers
  (Phase 6C). Confirm whether `TraceDetailDrawer` should follow the same wider spec or
  stay narrower.

- **Lazy load flash** — Monaco loads lazily; the `<pre>` fallback shows briefly. Consider
  a skeleton / spinner instead of raw text.

- **Close affordance** — `✕` plain text character. Should be the `Icon` atom for
  consistency with the rest of the design system.

#### Resolved

_(none yet)_

---

### `StreamingCursor`

**Location:** `src/rework/components/shared/atoms/StreamingCursor/StreamingCursor.tsx`
**Status:** `Functional`

#### Open UX issues

- **Cursor size** — `2px` wide, `1em` tall. Validate visibility against the font size of
  `AssistantMessage` once that component exists.

- **Colour** — `currentColor`. Confirm it is visually distinct on all background variants
  (streaming inside `ThoughtTrace` vs inside final reply bubble).

#### Resolved

_(none yet)_

---

### `HitlPrompt`

**Location:** `src/rework/components/shared/molecules/HitlPrompt/HitlPrompt.tsx`
**Status:** `Functional`

#### Open UX issues

- **Elevation / containment** — currently rendered inline in the message stream. A card
  with a stronger border or shadow may better signal that this is an action required from
  the user, not just a message.

- **Focus management** — when `HitlPrompt` appears, focus should move to the first
  actionable element (first choice button or the free-text input). Not yet implemented.

#### Resolved

_(none yet)_

---

## UX review agenda

_Priority order for the next UX session. Update before each session._

1. **ThoughtTrace — mobile column collapse** (210px column stacks badly on small viewports — breakpoint decision needed)
2. **ThoughtTrace — collapse behaviour** for history-loaded turns (product decision needed)
3. **TraceEntryRow — primary text truncation** (one line vs two lines for `thought` entries)
4. **TraceDetailDrawer — theme wiring** (quick code change once design decision is made)
5. **HitlPrompt — elevation and focus** (interaction design; may require Figma update)
