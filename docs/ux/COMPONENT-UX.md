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

- **Collapse behaviour** — the accordion collapses only when `done=true` is passed, which
  is `!isStreaming` (set by `AssistantTurn`). During history load all turns arrive
  simultaneously so all `ThoughtTrace` blocks start collapsed (past turns are not streaming).
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

### `MessageBubble`

**Location:** `src/rework/components/shared/atoms/MessageBubble/MessageBubble.tsx`
**Status:** `Functional`

#### Open UX issues

- **Assistant variant padding** — currently `padding: 0` (no bubble chrome). Confirm with designer
  whether the `assistant` role needs any left padding or border-left accent to visually distinguish it from
  plain prose text in the page.

#### Resolved

_(none yet)_

---

### `ToolBadge`

**Location:** `src/rework/components/shared/atoms/ToolBadge/ToolBadge.tsx`
**Status:** `Functional`

#### Open UX issues

- **`color-mix` fallback** — uses `color-mix(in srgb, ...)` for background tints. Verify browser
  support in the target deployment (Firefox 113+, Chrome 111+). Add a plain-color fallback if
  older browsers are in scope.

#### Resolved

_(none yet)_

---

### `UserMessage`

**Location:** `src/rework/components/shared/molecules/UserMessage/UserMessage.tsx`
**Status:** `Functional`

#### Open UX issues

- **Timestamp** — `UserMessage` accepts no timestamp yet. Decide whether to show relative time
  (e.g. "2 min ago") or ISO time on hover, and from which source (optimistic client time vs.
  `ChatMessage.timestamp`).

#### Resolved

_(none yet)_

---

### `AssistantMessage`

**Location:** `src/rework/components/shared/molecules/AssistantMessage/AssistantMessage.tsx`
**Status:** `Functional`

#### Open UX issues

- **Thinking indicator** — when streaming starts but no delta text has arrived yet (tools running),
  `AssistantMessage` shows a bare blinking cursor. Confirm whether a label ("Thinking…") or a
  three-dot animation would be a clearer affordance.

- **Markdown** — Phase 6B will replace the `<p>` with `MarkdownRenderer`. No UX issue yet.

#### Resolved

_(none yet)_

---

### `ChatInputBar`

**Location:** `src/rework/components/shared/molecules/ChatInputBar/ChatInputBar.tsx`
**Status:** `Functional`

#### Open UX issues

- **Send icon alignment** — `IconButton` (filled, primary) is `align-items: flex-end` with the
  `TextArea`. Validate that the button bottom-aligns cleanly with the textarea bottom when the
  textarea is at its minimum 2-row height.

- **Disabled state** — both `TextArea` and `IconButton` are disabled while `waitResponse` is true.
  Confirm the disabled visual is perceptible enough (contrast on send icon button in particular).

#### Resolved

_(none yet)_

---

### `ChatMessagesArea`

**Location:** `src/rework/components/shared/organisms/ChatMessagesArea/ChatMessagesArea.tsx`
**Status:** `Functional`

#### Open UX issues

- **Auto-scroll override** — currently always scrolls to bottom on any `scrollVersion` bump.
  If the user has scrolled up to read history and the agent produces a new delta, it will yank them
  back to the bottom. Discuss: should auto-scroll be paused while the user is scrolled up?

#### Resolved

_(none yet)_

---

### `AssistantTurn`

**Location:** `src/rework/components/shared/organisms/AssistantTurn/AssistantTurn.tsx`
**Status:** `Functional`

#### Open UX issues

- **`ThoughtTrace` + `AssistantMessage` stacking** — components now stack vertically (trace on top,
  reply below) per spec §1.2. Previous implementation placed them side-by-side. Validate on a real
  conversation that the vertical flow reads well, particularly when `ThoughtTrace` is long.

- **`max-width: 75%`** on `AssistantTurn` — validates alignment with the `MessageBubble` assistant
  variant. Confirm both are visually consistent across viewport widths.

#### Resolved

- **Props changed (2026-04-27)** — `finalMessages: ChatMessage[]` replaced by `text: string`.
  Text is now pre-extracted by `toConversationMessages` in `ManagedChatPage` and passed directly.

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

### `SourcesPanel` + `SourceCard`

**Location:** `src/rework/components/shared/molecules/SourcesPanel/`
**Spec:** [`CHAT-COMPONENT-SPECS.md §7`](../design/CHAT-COMPONENT-SPECS.md)
**Status:** `Functional`

#### Open UX issues

- **Max-width alignment** — `SourcesPanel` sits inside `.responseColumn` (flex: 1) without its own `max-width`. Validate whether the cards should be constrained to the same `680px` as the agent response text, or whether a wider layout is acceptable for sources.

- **Card density** — on turns with many sources (> 5), the panel becomes long. Discuss whether to cap at N visible cards with a "Show more" affordance.

- **Score display threshold** — currently shows score for all sources. Discuss whether to hide scores below a relevance threshold (e.g. < 40%) to reduce noise.

- **Detail modal design** — clicking a card opens `SourceDetailModal` (centered overlay, title/score/meta + full extract). The modal is functional but not yet design-reviewed: typography, spacing, and the metadata grid layout all need a designer pass.

- **Grouping by document** — the old `Sources.tsx` grouped multiple hits from the same `uid` into one `SourceRow` (best score, page count, tag chips). The new `SourceCard` renders one card per `VectorSearchHit`. Discuss with designer: group by document UID or keep flat by hit?

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

- **Frozen card visual distinction** — `readonly` mode (history replay) disables choice
  buttons but does not visually differentiate the frozen state from a live prompt. A
  muted/greyed style on the card or buttons would signal "past interaction" more clearly.

#### Resolved

- **`readonly` prop added (2026-04-27)** — `HitlPrompt` now accepts `readonly?: boolean`.
  When set, choice buttons are disabled and the free-text section is hidden. Used by
  `ManagedChatPage` when rendering `hitl_request` history rows.

---

---

### Session title in `ChatList`

**Location:** `src/rework/components/shared/organisms/ChatList/ChatList.tsx`
**Status:** `Functional` (fallback only — awaiting backend)

#### Open UX issues

- **Fallback label** — when `SessionListItem.title` is null the list shows
  `abc12345…` (first 8 chars of UUID). This is readable but not meaningful.
  The backend needs to generate a title after the first exchange; once it does,
  `ChatList` will display it automatically — no frontend change needed.
  Discuss with PM whether the fallback should be `"New conversation"` + date
  instead of the UUID fragment while waiting for the backend feature.

#### Resolved

_(none yet)_

---

### `AgentCard`

**Location:** `src/rework/components/shared/organisms/AgentCard/AgentCard.tsx`
**Status:** `Functional`

Displays one managed agent instance. Enabled cards are wrapped by `TeamAgentsPage` in a `<Link>` to the managed-chat route. On hover: descriptive content blurs, a "Start Chat" overlay appears, and the border plays a rotating conic-gradient animation. Footer action buttons (Settings, Delete) stay unblurred so they remain accessible during the hover state. Disabled cards render with muted colours and no hover effects, driven by a `data-enabled` CSS custom-property cascade.

#### Open UX issues

- **Gradient animation colours** — the conic-gradient uses hardcoded hex stops (`#65e0f6`, `#9299ff`, `#e1c39c`, `#d665b4`). These are intentional branding colours not in the design token system. Confirm with designer whether they should be tokenised or kept as-is.

- **Status badge — `color-mix`** — uses `color-mix(in srgb, var(--success) 12%, transparent)` for the badge background. Verify browser support aligns with deployment targets (Chrome 111+, Firefox 113+).

- **Disabled card affordance** — renders with `cursor: default` and dimmed icon. Confirm whether a `not-allowed` cursor or a muted overlay label (e.g. "Disabled") would better communicate non-interactivity to end users.

- **Card height** — no `min-height` set; height is driven by content. Validate grid row alignment when instances have very short vs. very long descriptions.

- **"Start Chat" label** — uses i18n key `rework.agentCard.startChat`. Confirm translation exists in all supported locales.

#### Resolved

- **Gradient animation + "Start Chat" overlay restored** — the rotating conic-gradient border and blur/overlay hover interaction from the develop branch were lost in the agentic-pod migration. Both are restored in `AgentCard.module.scss`.
- **`data-enabled` CSS cascade restored** — enabled/disabled state drives name colour, icon opacity, and background via CSS custom properties, matching develop branch behaviour.
- **Extracted to reusable organism** — card logic was previously inlined (575 lines) in `TeamAgentsPage.tsx`. Now in `shared/organisms/AgentCard/` with a clean prop interface against `ManagedAgentInstanceSummary`.
- **Whole-card click** — enabled cards are wrapped in `<Link>`; action buttons call `e.stopPropagation()` so they don't trigger navigation.

---

### `AgentFormModal`

**Location:** `src/rework/components/pages/TeamAgentsPage/AgentFormModal/`
**Status:** `Functional`

Complete create / edit modal for managed agent instances. Refactored per `docs/rfc/AGENT-INSTANCE-FORM-RFC.md` into a clean sub-component tree:

- `AgentFormModal.tsx` — modal shell + `FormState` ownership; no field rendering
- `AgentFormBody.tsx` — controlled form body; create or edit layout
- `TemplateBrowser/` — responsive card grid for template selection
- `TemplateCard/` — single selectable card with category pill, name, clamped description
- `TuningFieldRenderer.tsx` — handles all field types: string, number/integer, boolean (`SwitchRow`), enum (`<select>`), secret (password+reveal), url, prompt/multiline (`TextArea`)

Create mode: template browser → display name → description → tuning fields (grouped by `ui.group`) → MCP tools (read-only list). Edit mode: context bar (template name + category) → same editable fields → metadata footer (created_by · relative date).

#### Open UX issues

- **Tuning field groups** — flat scroll within modal; no accordion. Decide if needed for agents with many fields.
- **Template browser on mobile** — grid collapses to single column below ~480px; confirm whether list layout is preferable.
- **Single-template auto-select** — single available template is auto-selected; browser is still shown. Decide if it should collapse to a context bar immediately.

#### Resolved

- **Template browser** — replaced raw `<select>` with responsive card grid; selected state uses `--primary` border.
- **All field types** — secret, url, prompt, number/integer, enum, boolean (`SwitchRow`), multiline all implemented.
- **Field grouping** — `ui.group` groups fields under labeled sections; ungrouped fields appear first.
- **MCP tools section** — read-only list of tools advertised by the selected template (display_name or id + require_tools).
- **Edit mode context bar** — template name + category pill; no interaction.
- **Metadata footer** — created_by + relative date shown in edit mode when `created_by` is set.
- **Inline validation** — `submitAttempted` gates required-field errors; no toast for validation.
- **State isolation** — `FormState` resets fully on modal close; template change resets tuning values.

---

## UX review agenda

_Priority order for the next UX session. Update before each session._

1. **AgentCard — gradient colours** (are the hardcoded conic-gradient hex stops final branding or should they be tokenised?)
2. **AgentCard — disabled card affordance** (`cursor: default` + dimmed icon — confirm whether a label or overlay is needed)
3. **ThoughtTrace — mobile column collapse** (210px column stacks badly on small viewports — breakpoint decision needed)
4. **ThoughtTrace — collapse behaviour** for history-loaded turns (product decision needed)
5. **TraceEntryRow — primary text truncation** (one line vs two lines for `thought` entries)
6. **TraceDetailDrawer — theme wiring** (quick code change once design decision is made)
7. **SourcesPanel — grouping by document** (flat hits vs. grouped by UID — product decision)
8. **SourceDetailModal — full design pass** (metadata grid, typography, size — functional but unreviewed)
9. **Session title fallback** — `"abc12345…"` vs `"New conversation"` (PM decision, no code change needed)
10. **AgentFormModal — tuning field groups** — accordion vs. flat scroll for agents with many fields (UX decision — still open)
11. **AgentFormModal — template browser on mobile** — single-column grid vs. list layout on narrow viewports (UX decision)
12. **AgentFormModal — single-template auto-collapse** — when one template available, hide browser or show non-interactive card?
11. **HitlPrompt — elevation and focus** (interaction design; may require Figma update)
