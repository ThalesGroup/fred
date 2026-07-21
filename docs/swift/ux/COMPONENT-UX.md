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
| **full UX consolidation task → [`BACKLOG.md §UX-1`](../backlog/BACKLOG.md) — owner: Dimitri, reviewer: Maxime (UX-01)**

> **Scope note:** This file tracks chat UI components (CHAT-0x tracks).
> The consolidation task UX-01 extends the audit to all rework surfaces:
> agent creation form, team page, MCP tool cards, options panel. New issues
> found outside chat UI should still be recorded here under the relevant component section.

---

## Design token reference

Token names confirmed from `src/styles/colors-semantic-{light,dark}.css`.
Use **only** these names — no hardcoded hex fallbacks for color tokens.

| Purpose                         | Correct token                                                                                                 | Common wrong names                                                                   |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Elevated surface (hover states) | `--surface-container-high`                                                                                    | ~~`--surface-container-hight`~~ (extra `t`)                                          |
| Surfaces                        | `--surface-container`, `--surface-container-low`, `--surface-container-lowest`, `--surface-container-highest` |                                                                                      |
| Text                            | `--on-surface`, `--on-surface-retreat`, `--on-surface-muted`                                                  | ~~`--on-surface-variant`~~ (doesn't exist)                                           |
| Status colours                  | `--success`, `--error`, `--warning`, `--primary`                                                              | ~~`--success-main`~~, ~~`--error-main`~~, ~~`--warning-main`~~, ~~`--primary-main`~~ |
| Borders                         | `--outline-muted`, `--outline-variant`, `--outline-retreat`                                                   | ~~`--outline-variant`~~ was previously undefined — added to token files 2026-06-02   |

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

| Status           | Meaning                                      |
| ---------------- | -------------------------------------------- |
| `Functional`     | Code works, not yet design-reviewed          |
| `Needs revision` | Design review revealed issues, not yet fixed |
| `Approved`       | Designer + product owner signed off          |

---

## Components

---

### `SearchField`

**Location:** `src/rework/components/shared/molecules/SearchField/SearchField.tsx`
**Status:** `Functional`

Compact inline search input with a leading search Icon atom and a trailing clear IconButton atom.
Props: `value`, `onChange(value: string)`, optional `placeholder` and `clearAriaLabel`.
Used by `PromptsPage` (replaces native `<input>` + `<button>` search bar).

#### Open UX issues

_(none)_

---

### `FilterChips`

**Location:** `src/rework/components/shared/molecules/FilterChips/FilterChips.tsx`
**Status:** `Functional`

Horizontally-wrapping row of toggle chips for single-select filtering. Generic over chip ID type (`T extends string`).
Supports an optional "All" chip (via `allLabel`), expand/collapse beyond `maxVisible`, and full `aria-pressed` accessibility.
Used by `PromptsPage` (replaces native `<button>` category filter row).

#### Open UX issues

_(none)_

---

### `TagInput`

**Location:** `src/rework/components/shared/molecules/TagInput/TagInput.tsx`
**Status:** `Functional`

Tag chip input field: chips with inline remove button (Icon atom), keyboard commit (Enter, comma), Backspace-to-delete-last,
disabled state, error state, optional label, and `removeTagAriaLabel` callback for i18n.
Used by `TuningFieldRenderer` for `type: "array"` fields (replaces native chip `<input>`).

#### Open UX issues

_(none)_

---

### `PromptPicker`

**Location:** `src/rework/components/shared/molecules/PromptPicker/PromptPicker.tsx`
**Status:** `Functional`

Inline prompt library picker used inside `TuningFieldRenderer` for `type: "prompt"` tuning fields.
Renders a toggle button ("Pick from library"). When open, shows all available `ContextPromptSummary`
items as a card grid (auto-fill columns, min 240px). Each card: name + scope badge + description (2
lines clamped). Clicking a card calls `onSelect(id)` and closes itself; the parent fetches full text
and fills the `TextArea`.

#### Open UX issues

- **Content preview** — cards show name + description only. Full prompt text preview requires the
  backend `GET /teams/{id}/prompts/context` response to include a `text_snippet` field (tracked in
  PROMPT-03). No extra fetches until then.
- **Loading state** — no skeleton shown while `isLoadingSelection` is true; button goes disabled
  but the grid stays visible with stale content. Consider a spinner overlay on the grid during load.

---

### `MenuPopover` / `MenuPopoverItem`

**Location:** `src/rework/components/shared/molecules/MenuPopover/`
**Status:** `Functional` (CHAT-12, 2026-06-19)

Shared menu-popover grammar — a single component parameterised by its items, so every
contextual menu is born consistent. `MenuPopover` owns the visual surface (shadow, border,
radius, padding) plus an optional header and groups of rows separated by thin dividers;
it does **not** position itself (consumers place it). `MenuPopoverItem` is one homogeneous
row: leading icon + label + optional inline muted value + optional badge + optional trailing
affordance (e.g. `chevron_right` for sub-rows, `add` for actions), with a `danger` variant.
Sub-menu rows are rows with a chevron whose anchored panel is rendered by the parent as a
sibling. Uses the profile-menu token set (`--surface-container-*`, `--on-surface*`,
`--outline-variant`, `--radius-*`). Current instances: `UserProfile`, `SearchConfig`.

---

### `SearchConfig`

**Location:** `src/rework/components/shared/molecules/SearchConfig/SearchConfig.tsx`
**Status:** `Functional`

Conversation composer options menu opened from the `+` action in `ManagedChatPage`. As of
CHAT-12 it is an instance of `MenuPopover`: the former boxed "Attach files" button is now a
plain `Joindre des fichiers` row, and Document / Search / Scope are homogeneous rows with the
current value shown inline in muted text plus a chevron that opens an anchored sub-menu.
Uppercase section labels are gone (sentence case: "Recherche", "Portée"). SearchConfig now
only owns its box width and the anchored sub-menus; the surface and row grammar come from the
shared molecule.

#### Open UX issues

- **Desktop anchor space** — sub-menus open to the right of the row. Validate the behaviour
  close to the right edge on narrower laptop widths and decide whether a left-flip is worth adding later.
- **Prompts row (PROMPT-05)** — the harmonized menu is shaped to accept a `Prompts` sub-row
  (active count + chevron). Wiring is deferred: PROMPT-05 is blocked on PROMPT-03 and its
  multi-prompt session backend is not built yet.

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

- **Label chip style — partially (2026-06-18)** — thought rows now use subtle per-phase
  tinted pills (see `TraceEntryRow`) rather than the flat uppercase label; reasoning detail
  opens in the overlay drawer with markdown rendering instead of raw JSON.

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

- **Per-phase colour coding (2026-06-18, RUNTIME-05 follow-up)** — thought rows now render
  the phase as a subtle tinted pill (`.phaseBadge[data-phase=...]`): planning→tertiary,
  tool_use→secondary, observation→primary, reflection→warning, synthesis→success
  (each with its M3 `--on-*` text pairing). Non-thought rows keep the plain uppercase label.
  Clicking a row opens the shared page-level detail drawer (state lifted via `traceDrawerContext`).

---

### `TraceDetailDrawer`

**Location:** `src/rework/components/shared/molecules/ThoughtTrace/TraceDetailDrawer/TraceDetailDrawer.tsx`
**Spec:** [`CHAT-COMPONENT-SPECS.md §3`](../design/CHAT-COMPONENT-SPECS.md)
**Status:** `Functional`

#### Open UX issues

- **Theme** — Monaco is always `vs-dark` (now only used for tool call/result entries). The
  spec says theme-aware (`vs` / `vs-dark`). Not yet wired to the app theme context.

- **Tool entry rendering** — tool call/result entries still render as raw Monaco JSON.
  A prettier structured view (args table, result preview) is a follow-up; only reasoning /
  note entries got the markdown treatment in the 2026-06-18 pass.

#### Resolved

- **Single page-level instance (2026-06-18)** — the panel state is lifted to `ManagedChatPage`
  via `traceDrawerContext` and rendered once (instead of one drawer per trace row). It keeps the
  default `overlay` layout — `push` was trialled but `overlay` was preferred for this panel.

- **Markdown reasoning view (2026-06-18)** — reasoning / note entries (thought, plan,
  observation, system_note, error) now render their text through `MarkdownRenderer` on a raised
  `--surface-container-high` card, with a header showing the phase badge, a `Model` chip for
  `source="model_native"`, duration, and a conclusion footer — replacing the raw JSON view.
  Structural steps that carry no reasoning text (e.g. auto-synthesised `tool_use` thoughts)
  render header + conclusion only — no "no reasoning text" placeholder.

- **Close affordance** — `InlineDrawer` already uses the `Icon`-atom close button.

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

_(none — streaming indicator resolved 2026-05-18)_

#### Resolved

- **Markdown** — Phase CHAT-02: `AssistantMessage` now renders via `MarkdownRenderer` (2026-05-04).

- **Thinking indicator replaced with `ThinkingDots` (2026-05-18)** — the bare blinking cursor shown
  before the first chunk arrived was removed. `ThinkingDots` (three animated wave dots) is shown
  instead. It communicates processing without visual noise.

- **Inline streaming cursor removed (2026-05-18)** — the `StreamingCursor` rendered after the last
  markdown paragraph during streaming was removed. Text appearing continuously is the signal;
  a blinking artifact alongside it is redundant and distracting.

- **Pending block streaming preview (2026-05-28)** — when a reply opens a supported block fence
  during streaming, the assistant bubble now shows an immediate preview shell instead of a blank
  bubble or transient renderer error: a streaming `CodeBlock` for backtick fences (including
  ` ```mermaid `), `$$`, and `:::` directives. The final specialized renderer takes over once the
  closing delimiter arrives (`MermaidBlock` for finished Mermaid, final native renderers for the
  other block types).

---

### `MarkdownRenderer`

**Location:** `src/rework/components/shared/molecules/MarkdownRenderer/MarkdownRenderer.tsx`
**Status:** `Functional`

#### Open UX issues

- **Heading sizes** — `h1`/`h2`/`h3` use `--font-headline-small` (1.5rem). LLM responses rarely
  use top-level headings, but when they do the size may feel large inside an assistant bubble.
  Consider capping at `--font-title-large` (1.375rem) for headings inside chat.

- **Table overflow** — wide tables overflow the bubble width without horizontal scroll at
  narrow viewports. Consider `overflow-x: auto` on a wrapper.

- **Blockquote style** — left-border only, no background. Confirm whether a subtle background tint
  (`--surface-container`) would better distinguish blockquotes from regular text.

#### Resolved

- **Streaming previews for open fences (2026-05-28)** — `CodeBlock` now has a streaming mode used
  while any supported fence is still open, including Mermaid. The user sees the language header,
  copy action, and raw source text immediately during streaming, then the block switches to syntax
  highlighting / Mermaid / KaTeX / directive rendering once complete.

---

### `CodeBlock`

**Location:** `src/rework/components/shared/molecules/CodeBlock/CodeBlock.tsx`
**Status:** `Functional`

#### Open UX issues

- **No syntax highlighting** — plain monospace only. Consider adding `react-syntax-highlighter`
  (already in `package.json`) for a richer developer experience, especially for code-heavy agents.

- **Fenced code without language** — renders as inline code (no language class, so the block
  path is not triggered). Low-frequency edge case, but may surprise users who write unlabelled
  fenced blocks. Discuss whether to detect by trailing `\n` heuristic.

#### Resolved

_(none yet)_

---

### `SourceBadge`

**Location:** `src/rework/components/shared/atoms/SourceBadge/SourceBadge.tsx`
**Status:** `Functional`

#### Open UX issues

- **Discoverability** — the badge is small (0.7em superscript). Confirm whether a hover tooltip
  ("View source N") would improve clarity.

- **Active state** — clicking a badge highlights the card in `SourcesPanel` but the badge itself
  has no active/visited visual state. Consider a filled background when the corresponding card is
  `activeIndex`.

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

_(none — layout and scroll behaviour resolved 2026-05-18)_

#### Resolved

- **Scroll container promoted to `.chatColumn` (2026-05-18)** — `overflow-y: auto` was on `.area`
  (an inner element), which caused the scrollbar to stop at the top of the input field instead of
  spanning the full browser height. `.chatColumn` is now the single scroll container. `.area` uses
  `min-height: 100%` so the empty state still centres correctly.

- **Sticky input (2026-05-18)** — `RichInputField` was a flex sibling below the scroll container,
  which truncated the scrollbar track. It is now `position: sticky; bottom: 0` inside the scroll
  container so the scrollbar runs the full column height.

- **720px centered lane (2026-05-18)** — content was constrained by scattered `max-width`/`align-self`
  on individual components (`AssistantTurn`, `MessageBubble`). A single `.lane` wrapper
  (`max-width: 720px; margin: 0 auto`) is now the only width constraint. All components inside fill
  the lane width. `RichInputField` uses the same 720px so messages and input share a visible column edge.

- **Streaming auto-scroll with user override (2026-05-18)** — `useLayoutEffect` (no deps) scrolls
  to bottom on every render during streaming, but only when the user is within 120px of the bottom.
  If they scroll up to read history, auto-scroll suspends for the rest of that turn and resumes on
  the next `scrollVersion` increment.

- **Native scrollbar follows active theme (2026-05-18)** — `color-scheme: dark/light` added to
  `[data-theme]` selectors in the semantic CSS files. Without this, the browser rendered native
  scrollbars in light mode regardless of the active theme.

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

- **Artifact download links (2026-06-22, FILES-04)** — `AssistantTurn` now renders `ArtifactLinks`
  below the reply when the agent emits `LinkPart` ui_parts.

---

### `ArtifactLinks`

**Location:** `src/rework/components/shared/molecules/ArtifactLinks/ArtifactLinks.tsx`
**Status:** `Functional`

Renders agent-produced downloadable artifacts (`LinkPart` ui_parts on the final event) as download
chips below an assistant reply. The `/fs/download` route is session-authenticated, so a chip click
runs an **authenticated fetch (live Bearer) → blob → save** via the shared `downloadAuthed` util —
the same proxy-through-KF mechanism as the Resources file browser. A plain markdown anchor would
navigate without a token and fail ("No authentication token provided"). Signed share links
(`/fs/share` token-in-URL) are intentionally **not** used here — reserved for explicit external
sharing — to avoid credential leakage, link rot, and stale-authorization bypass of live ReBAC.

#### Open UX issues

- **Chip visual pass** — icon + filename chip styled from existing tokens (mirrors `AttachmentChips`);
  needs a designer pass for spacing/affordance, especially with multiple artifacts on one reply.

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

- **Detail modal design** — clicking a card opens `SourceDetailModal` (centered overlay, title/score/meta + full extract). The modal is functional but not yet design-reviewed: typography, spacing, and the metadata grid layout all need a designer pass. CHAT-08 added an "Open document ↗" link at the bottom of the modal body, navigating to `/documents/{uid}` in a new tab; the link is suppressed when `uid` is `"Unknown"`.

- **Grouping by document** — the old `Sources.tsx` grouped multiple hits from the same `uid` into one `SourceRow` (best score, page count, tag chips). The new `SourceCard` renders one card per `VectorSearchHit`. Discuss with designer: group by document UID or keep flat by hit?

#### Resolved

_(none yet)_

---

### `DocumentViewer`

**Location:** `src/rework/components/shared/organisms/DocumentViewer/DocumentViewer.tsx`
**Status:** `Functional`

Shared, chrome-less document content renderer used by both `DocumentViewerPage`
(`/documents/:uid`, chat-citation flow) and `DocumentWorkspace`'s corpus preview
drawer (`InlineDrawer`). Picks a render strategy from the file's real extension
(`isPdfFile` on `identity.document_name`, never the display title): `.pdf` renders
natively via `PdfStreamingDocumentViewer` (`react-pdf`); every other format renders
the existing markdown extraction (`GET /knowledge-flow/v1/markdown/{uid}`). Owns no
header/close affordance — both hosts already provide one. Landed 2026-07-19 (FRONT-13)
to close the "PDF viewer parity" regression from kea tracked on GitHub issue #1956.

#### Open UX issues

- **Assistant side panel** — FRONT-13's other half (collapsible "ask the assistant"
  panel next to the viewer) is not built yet, blocked on an agent-selection product
  decision — see `FRONTEND-BACKLOG.md` §19.
- **PDF toolbar** — no page count, zoom, or page-jump controls; pages render as one
  continuous scroll at a fixed 0.8 scale. Revisit if users report needing them.
- **Chunk highlighting** — `#chunk=...` fragment handling remains deferred (CHAT-08,
  RAG-AGENT-QUALITY-RFC.md §5), unaffected by this component.

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

### `Toast` / `ToastProvider`

**Location:** `src/rework/components/shared/molecules/Toast/Toast.tsx`
**Provider:** `src/components/ToastProvider.tsx` (rewrites the legacy MUI Snackbar in-place; same `useToast` API)
**Status:** `Approved`

#### Design intent — enterprise monitoring aesthetic

The toast is deliberately styled after the notification patterns found in **Datadog, Kibana, and Splunk**:
high-information-density, zero decoration, color used only as a semantic signal — never as decoration.

**What the component does:**

- A 340px card anchored `bottom-right`, stacking newest-closest-to-corner (`flex-direction: column-reverse`).
- The **only** colored element is a `3px solid border-left` in the severity color. Background and text are always neutral surface tokens.
- Detail text (the `detail` field) renders in `monospace`, 0.75rem — intentionally log-line aesthetic. Error details read like a console, not a UI message.
- Animation: 140ms opacity fade + 4px vertical lift on enter; 110ms fade-out on exit. Nothing slides or bounces.
- No icons, no progress bar, no colored background fills. Severity is inferred from the left border alone.

**Design rules that must not be regressed:**

| Rule                                         | Why                                                                                                              |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `border-radius: var(--radius-xs)` (4px) only | Larger radii (`--radius-m` = 16px) read as decorative / child-safe. Sharp corners signal a professional tool.    |
| Left border carries all color                | Colored surfaces or icons compete with content and look playful. One semantic signal is enough.                  |
| Detail font: monospace                       | Error messages, API traces, and validation strings come from technical systems. Monospace makes them scannable.  |
| No slide animation                           | Sliding from the edge is theatrical. A fast fade is unobtrusive — the notification informs, it does not perform. |
| No progress bar                              | Progress bars gamify the dismiss timer. Enterprise tools (DD, Kibana) don't use them.                            |

**Severity mapping:**

| Severity  | Left border   | Auto-dismiss                                         |
| --------- | ------------- | ---------------------------------------------------- |
| `success` | `--success`   | 6 s                                                  |
| `warning` | `--warning`   | 6 s                                                  |
| `info`    | `--secondary` | 6 s                                                  |
| `error`   | `--error`     | Manual only — errors persist until explicitly closed |

Error toasts additionally expose a copy-to-clipboard icon button (`content_copy`) for developer convenience.

#### Open UX issues

_(none — design approved at implementation)_

#### Resolved

- **Replaced MUI `Snackbar` + `Alert`** (2026-05-14) — legacy implementation used MUI components styled with `sx` props outside the design token system. Replaced with a zero-dependency CSS-module molecule using only design tokens.
- **Design: enterprise aesthetic** (2026-05-14) — initial implementation used `--radius-m`, colored surfaces, large severity icons, slide animation, and progress bar. Rejected as "toy-like". Final design follows the Datadog/Kibana pattern described above.

---

### `AgentFormModal`

**Location:** `src/rework/components/pages/TeamAgentsPage/AgentFormModal/`
**Status:** `Functional`

Complete create / edit modal for managed agent instances. Refactored per `docs/rfc/AGENT-INSTANCE-FORM-RFC.md` into a clean sub-component tree:

- `AgentFormModal.tsx` — modal shell + `FormState` ownership; no field rendering
- `AgentFormBody.tsx` — controlled form body; create or edit layout
- `TemplateBrowser/` — responsive card grid for template selection
- `TemplateCard/` — single selectable card with category pill, name, clamped description
- `TuningFieldRenderer.tsx` — handles all field types: string, number/integer, boolean (`SwitchRow`), enum (design-system `Select` molecule), secret (password+reveal), url, array (`TagInput` molecule), prompt/multiline (`TextArea`)

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

### `TeamUsagePage`

**Location:** `src/rework/components/pages/TeamUsagePage/TeamUsagePage.tsx`
**Status:** `Functional`

Personal token-usage dashboard (OBSERV-02 / `BACKLOG.md` §7b). Reuses `AnalyticsPage`'s chart
primitives (`TimeSeriesLineChart`, `BarChart`, `TimeRangeSelector`, `ServiceNotice`) at
`team/:teamId/usage`: a timeline of the requesting user's own token consumption plus
breakdowns by agent and by model, all self-scoped server-side (no team/agent picker). Entry
point is a new gear icon on the personal-space banner (`TeamContentNavbar.tsx`) — the same
slot team settings uses, gated on `isPersonalTeam` instead of `canOpenTeamSettings` since the
two are mutually exclusive.

#### Open UX issues

- Not yet design-reviewed. First functional pass only — layout and empty/loading states mirror
  `AnalyticsPage` but haven't been checked against a live stack with real token data.

---

---

## CHAT-05 atoms (Wave 1 + additions)

---

### `ThinkingDots`

**Location:** `src/rework/components/shared/atoms/ThinkingDots/ThinkingDots.tsx`
**Status:** `Approved`

Three 6px circles with a staggered wave animation (`0s / 0.15s / 0.30s` delay),
`--on-surface-retreat` colour. Shown in `AssistantMessage` when `isStreaming && !text` — the
agent is processing but no text has arrived yet (tool calls running, model warming up, etc.).
Dismissed automatically the moment the first text delta arrives.

**Design rules that must not be regressed:**

| Rule                           | Why                                                                            |
| ------------------------------ | ------------------------------------------------------------------------------ |
| Wave animation, not blink      | A blink cursor signals "type here". Dots signal "something is computing".      |
| `--on-surface-retreat` colour  | Subtle — does not compete with the response text that follows.                 |
| Hidden as soon as text arrives | The dots and the text must never coexist. Swap is instant.                     |
| No label ("Thinking…")         | Labels go stale (the agent may be retrieving, not thinking). Dots are neutral. |

#### Open UX issues

_(none — approved at implementation)_

#### Resolved

- **Implemented as replacement for `StreamingCursor` thinking state (2026-05-18)**.

---

### `IndicatorDot`

**Location:** `src/rework/components/shared/atoms/IndicatorDot/IndicatorDot.tsx`
**Status:** `Functional`

Coloured status dot. The `status` prop maps to a semantic color token via a `STATUS_COLOR` lookup table (`idle → --on-surface-retreat`, `active → --success`, `warning → --warning`, `error → --error`, `streaming → --primary`). The `streaming` status adds a CSS pulse animation via `data-status="streaming"`.

#### Open UX issues

- **Pulse animation speed** — 1.2 s infinite ease-in-out. Validate with designer: is this too fast (distracting) or too slow (unnoticeable) in the context of a live streaming session?
- **Size options** — single size (`10px`). If used as a connection-status indicator in a header or sidebar, a smaller `6px` variant may be needed.

#### Resolved

_(none yet)_

---

### `AccentBar`

**Location:** `src/rework/components/shared/atoms/AccentBar/AccentBar.tsx`
**Status:** `Functional`

Left-border block wrapper. `AccentColor` prop (`primary | success | warning | error | info`) sets `--accent-color` which drives a `4px solid` left border. Content renders in `children`. No background fill.

#### Open UX issues

- **Border width** — 4px is typical for blockquote-style accents. Confirm the width is appropriate when `AccentBar` is used inside dense agent option panels vs. wide chat layouts.

#### Resolved

_(none yet)_

---

### `RestrictedBadge`

**Location:** `src/rework/components/shared/atoms/RestrictedBadge/RestrictedBadge.tsx`
**Status:** `Functional`

Non-interactive lock icon + label. Uses `material-symbols-outlined` `lock` icon at 14px, `--on-surface-retreat` color, `--surface-container-high` background pill.

#### Open UX issues

- **Label truncation** — no max-width set. Validate with long label text (`"Administrateur seulement"`) inside narrow `SourceCard` widths.

#### Resolved

_(none yet)_

---

### `NumberedChip`

**Location:** `src/rework/components/shared/atoms/NumberedChip/NumberedChip.tsx`
**Status:** `Functional`

Renders as `<button>` when `onClick` is provided, `<span>` otherwise. Square pill, `--primary` background, white text. Used as source reference badges in `AssistantMessage`.

#### Open UX issues

- **Active state** — no visual distinction between active (currently selected source) and inactive chips. `SourceCard` active state is tracked in `AssistantTurn`, but the chip itself has no visual feedback. Decide if chips should also show an active ring.
- **Hover state** — `<button>` variant has a `background-color` transition but no distinct hover token. Confirm with designer.

#### Resolved

_(none yet)_

---

### `FaviconIcon`

**Location:** `src/rework/components/shared/atoms/FaviconIcon/FaviconIcon.tsx`
**Status:** `Functional`

`<img>` that falls back to `material-symbols-outlined` `description` icon on `onError`. 20×20 px, `object-fit: contain`.

#### Open UX issues

- **Fallback legibility** — the `description` material icon is generic. Consider a `language` (globe) icon as fallback for web URLs and `description` only for local documents.
- **CORS failures** — favicon URLs from external domains may be blocked by CORS. The `onError` fallback handles this gracefully, but the result is that all external sources look the same. Discuss with backend whether favicons should be proxied.

#### Resolved

_(none yet)_

---

## CHAT-05 molecules (Waves 2–4)

---

### `CollapsibleBlock`

**Location:** `src/rework/components/shared/molecules/CollapsibleBlock/CollapsibleBlock.tsx`
**Status:** `Functional`

Expand/collapse section with animated height. Supports both controlled (`open`/`onOpenChange`) and uncontrolled (`defaultOpen`) modes. Chevron rotates 90° via `data-open` attribute. Height animation uses `useRef<HTMLDivElement>` + `requestAnimationFrame` for the close transition.

#### Open UX issues

- **Animation jank** — `requestAnimationFrame` approach works but may jitter on slow devices when closing a tall section. Consider CSS `@keyframes` on `max-height` as an alternative if complaints arise.
- **Focus management** — when collapsing with keyboard (`Enter` on the trigger), focus stays on the trigger. Confirm this is correct; some patterns move focus to the first child on open.

#### Resolved

_(none yet)_

---

### `HorizontalScrollRow`

**Location:** `src/rework/components/shared/molecules/HorizontalScrollRow/HorizontalScrollRow.tsx`
**Status:** `Functional`

Horizontal scroll container with gradient fade overlays at left/right edges. ResizeObserver + scroll listener drive `data-fade-left`/`data-fade-right` data attributes. Gradient uses `--scroll-fade-bg` CSS variable (falls back to `--surface-container-lowest`). Callers set `--scroll-fade-bg` on their wrapper if background differs.

#### Open UX issues

- **Keyboard scrollability** — the scroll row has no tab stop of its own; individual children are focusable. Confirm that keyboard users can reach off-screen children via Tab without needing horizontal scroll input.
- **Fade width** — 32px gradient fade. Confirm visibility of the fade on dark theme backgrounds.

#### Resolved

_(none yet)_

---

### `ActionBar`

**Location:** `src/rework/components/shared/molecules/ActionBar/ActionBar.tsx`
**Status:** `Functional`

Row of icon buttons with tooltips. `opacity: 0` by default; parent controls visibility via `.turn:hover .actions { opacity: 1 }`. `alwaysVisible` prop overrides to `opacity: 1` for accessibility fallback.

#### Open UX issues

- **Touch / mobile** — hover-reveal pattern is invisible on touch devices. Discuss whether a long-press or a permanent reduced-opacity state is needed for mobile.
- **Tooltip delay** — using native `title` attribute. If the DS tooltip component is adopted, replace for consistent positioning and delay control.

#### Resolved

_(none yet)_

---

### `InlineDrawer`

**Location:** `src/rework/components/shared/molecules/InlineDrawer/InlineDrawer.tsx`
**Status:** `Functional`

Non-blocking right-side panel. `position: fixed`, slides in from the right via `transform: translateX(100%)` → `translateX(0)`. ESC key closes. `--drawer-width` CSS variable, default `480px`. Does not trap focus (main content stays interactive).

#### Open UX issues

- **Focus trap** — deliberately no focus trap (main content stays interactive per RFC §2.5). Confirm with accessibility review: WCAG 2.1 SC 2.1.2 applies to modal dialogs, not drawers; but screen reader users should be informed the drawer is open.
- **Mobile** — `480px` fixed width covers most of the screen on narrow viewports. Need a `100vw` breakpoint below ~600px.
- **Overlay backdrop** — no backdrop, per RFC "no blocking modals". Confirm with designer whether a light scrim (opacity 0.2) behind the drawer would help orient users without feeling modal.

#### Resolved

_(none yet)_

---

### `SourceCard`

**Location:** `src/rework/components/shared/molecules/SourceCard/SourceCard.tsx`
**Status:** `Functional`

`FaviconIcon` + optional index `NumberedChip` + optional `RestrictedBadge` + 2-line title + domain label. Clickable when `onClick` is provided. Renders `<button>` or `<div>` based on `onClick` presence.

#### Open UX issues

- **Card width** — fixed `200px`. May be too narrow for long document titles and too wide for a compact sources row. Consider `min-content` / `max-content` constraints.
- **Title clamping** — 2 lines clamped. On hover, confirm the full title is visible (tooltip?). No `title` attribute currently set.
- **Active visual state** — when the corresponding source is active (`activeSourceIndex === i + 1` in `AssistantTurn`), the card has no visual change. Requires a CSS class or `data-active` attribute passed from the parent.

#### Resolved

_(none yet)_

---

### `ContextualPicker`

**Location:** `src/rework/components/shared/molecules/ContextualPicker/ContextualPicker.tsx`
**Status:** `Functional`

Generic `<T extends string>` trigger button + dropdown listbox. Full ARIA: `role="listbox"`, `role="option"`, `aria-selected`, `aria-expanded`. Mousedown-outside + ESC close. `useId()` for listbox association.

#### Open UX issues

- **Keyboard navigation** — `ArrowUp`/`ArrowDown` through options not yet implemented. Currently Tab-stops on each option but no `aria-activedescendant` tracking.
- **Multi-select variant** — not implemented; single-value only. If RAG scope needs multi-select, a new variant is needed.

#### Resolved

_(none yet)_

---

### `SessionTitleEditor`

**Location:** `src/rework/components/shared/molecules/SessionTitleEditor/SessionTitleEditor.tsx`
**Status:** `Functional`

Popup title editor — Claude.com pattern. Display mode: `<button>` with `font: inherit` (font size set by parent context) and a pencil icon that appears on hover. Click opens a small anchored popup card (`position: absolute`, `--radius-l`, subtle `box-shadow`, `--surface-container-high` background) containing a "Rename conversation" label, a `TextInput` atom, and Cancel / Save `Button` atoms. Click outside or Escape closes without saving; Enter or Save commits. `aria-expanded` on the trigger; `role="dialog"` on the popup.

**Font size** is controlled by the parent container via CSS inheritance (`font: inherit` on `.display`). In `ManagedChatPage.topBarTitle`, this resolves to `--font-body-medium` (14px) — never `--font-title-*`.

#### Open UX issues

- **Empty state** — if the user clears the title and saves, the trimmed value is empty so `onCommit` is not called and the popup closes silently. Confirm this no-op is the intended UX (alternative: show an error state on the `TextInput`).
- **Popup overflow** — if the trigger is near the right edge of the viewport, the popup (min-width 280px) may overflow. No repositioning logic exists yet.

#### Resolved

- **Inline input replaced with popup card** (2026-05-24) — previous inline `<input>` used `--font-title-large` (22px) and created a layout shift. Replaced with anchored popup using `TextInput` + `Button` atoms.

---

### `RichInputField`

**Location:** `src/rework/components/shared/molecules/RichInputField/RichInputField.tsx`
**Status:** `Functional`

Auto-growing textarea with optional `topSlot`, `leftSlot`, `rightSlot`, and `showSendButton`. Height grows with content up to `maxHeight` (200px default); `overflowY` switches from `hidden` to `auto` at max height. Enter (no Shift) sends; Shift+Enter inserts newline. `.bar` uses a gradient fade (`transparent → --surface-container-lowest`) so the field floats above the thread visually.

#### Required composer-control pattern

Routine per-turn chat settings belong in or immediately above `RichInputField`,
not in a full-height page drawer. This includes search policy, RAG scope,
active library count, attachment count, and similar controls that affect the
next user message.

Target shape:

- compact chips in a slim `topSlot` settings row, e.g. `Hybrid`,
  `Corpus + web`, `3 libraries`
- `leftSlot` is reserved for one small icon/control such as attach-file; do
  not place a multi-chip settings cluster there because it compresses the
  textarea
- each chip opens an anchored popover sized to its task
- single-choice popovers close after selection
- multi-select library popovers stay open until dismissed and show selected
  libraries as quiet chips
- chips must remain visually lighter than assistant reply text and the composer
  text area
- chips may wrap inside the settings row, but the textarea must keep a
  comfortable typing width on desktop, tablet, and mobile
- no routine setting may open a full-height drawer or cover the answer body by
  default

Drawers remain valid for source detail, debug traces, raw response detail, and
admin diagnostics.

#### Open UX issues

- **Paste large content** — pasting 1000+ character text may cause a brief layout shift as the textarea jumps to max height. Not a bug, but worth validating visually.
- **Placeholder visibility** — the native `<textarea>` placeholder uses `::placeholder` pseudo-element. Confirm it uses `--on-surface-retreat` and is legible on all backgrounds.

#### Resolved

- **Re-click after reply** (2026-05-24) — textarea lost focus when `disabled` transitioned `true → false` at end of streaming. Fixed with `useEffect` on `disabled` that calls `textareaRef.current?.focus()`.
- **Square background on input bar** (2026-05-24) — `.bar` had a solid rectangular background making the field look trapped in a box. Replaced with a gradient fade and added `box-shadow` on `.field` for a floating appearance.
- **Routine options moved to composer topSlot** (2026-05-24) — `AgentOptionsPanel` full-height right overlay removed. Libraries, search policy, and RAG scope are now `ComposerSettingsControls` chips in `RichInputField`'s `topSlot`, with anchored popovers per chip. No full-height drawer for routine controls.
- **Settings cluster no longer compresses textarea** (2026-05-24) — `ComposerSettingsControls` moved from `leftSlot` to `topSlot` (dedicated settings row above textarea). Textarea now has full composer width.
- **Documents chip stays interactive on empty scope** (2026-06-12) — when `documents_selection` is enabled, the Documents chip must always open. Empty scope messaging is explicit: "Select a library first." when the library picker is visible but empty, and a configuration warning when documents are enabled without any library picker or bound library.
- **IME composition guard** (2026-05-24) — `handleKeyDown` now checks `!e.nativeEvent.isComposing` before calling `onSend`. CJK composition Enter no longer triggers send.

---

## CHAT-05 organisms (Waves 6–7)

---

### `UserTurn`

**Location:** `src/rework/components/shared/organisms/UserTurn/UserTurn.tsx`
**Status:** `Functional`

`UserMessage` + `ActionBar` (copy, optional edit). `.turn` has `position: relative`; hover shows actions. Edit action passes `onEdit` prop through to the action bar.

#### Open UX issues

- **Edit action** — `onEdit` prop exists but is not wired in `ConversationThread` yet. When wired, confirm that editing a message and re-sending correctly creates a new branch in the message tree.
- **Hover zone** — the hover area is the full `.turn` div. On mobile, confirm touch events correctly show/hide the action bar.

#### Resolved

_(none yet)_

---

### `ConversationHeader`

**Location:** `src/rework/components/shared/organisms/ConversationHeader/ConversationHeader.tsx`
**Status:** `Not active — kept for potential reuse`

Previously used in `ManagedChatPage`. Replaced by the floating topBar pattern (2026-05-24): `SessionTitleEditor` + `TogglePanelButton` placed directly in `ManagedChatPage` as a `position: absolute` overlay with `pointer-events: none` on the wrapper. No dedicated header bar exists in the chat page.

#### Open UX issues

_(none — component not in active use)_

#### Resolved

- **Replaced by floating topBar** (2026-05-24) — the persistent header bar created visual fragmentation ("squares"). Removed in favour of a zero-weight overlay following the claude.com pattern.

---

### `ConversationThread`

**Location:** `src/rework/components/pages/ManagedChatPage/ConversationThread/ConversationThread.tsx`
**Status:** `Functional`

Page-local composition that maps `ThreadMessage[]` to `UserTurn` / `AssistantTurn` / `HitlPrompt` inside `ChatMessagesArea`. Lives under `pages/` — may legally import shared organisms.
`ThreadMessage` type lives in `src/rework/types/thread.ts`.

#### Open UX issues

- **Loading skeleton** — `isLoading` state shows a `chatbot.loadingHistory` text hint while history fetches. A message skeleton (3 alternating user/assistant placeholder rows) would reduce layout shift on history load.

#### Resolved

- **Hierarchy debt** (2026-05-24) — moved from `shared/organisms/` to `pages/ManagedChatPage/ConversationThread/`. Organism→organism imports eliminated. `ThreadMessage` extracted to `@rework/types/thread`.
- **Empty state** (2026-05-24) — `ChatMessagesArea` renders `t("chatbot.startConversationHint")` when `!isLoading && isEmpty`. EN + FR translations present.

---

### `ManagedChatPage` composition

**Location:** `src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`
**Status:** `Functional`

Page composition: floating `topBar` (`position: absolute`) holding `SessionTitleEditor`;
single `chatArea` scroll container (`overflow-y: auto`) containing page-local
`ConversationThread` and sticky `RichInputField` with `ComposerSettingsControls` in
`topSlot`. No `AgentOptionsPanel`, no `ConversationHeader`.

#### Open UX issues

_(none — all prior issues resolved below)_

#### Resolved

- **Options drawer retired** (2026-05-24) — `AgentOptionsPanel` full-height right overlay removed. Search policy, RAG scope, and library selection are now `ComposerSettingsControls` chips in `RichInputField` `topSlot` with anchored popovers per chip.
- **Composer settings placement** (2026-05-24) — `ComposerSettingsControls` moved from `leftSlot` to `topSlot` (dedicated row above textarea). Textarea has full composer width.
- **Persistent setting summary** (2026-05-24) — active search policy, RAG scope, and library count are always visible as chips in the `topSlot` settings row, even while reading a reply.
- **Drawer role narrowing** (2026-05-24) — right-side drawers reserved for deep inspection only (source detail, debug, admin diagnostics). Routine controls do not use drawers.
- **Conversation files drawer** (2026-06-11) — attachment chips remain the transient per-turn affordance above the textarea, while persisted conversation files now live in a dedicated right drawer opened from a badge button next to the paperclip. This keeps routine composer controls lightweight while still exposing reload-safe file preview/delete flows.

---

### `SessionAttachmentsDrawer`

**Location:** `src/rework/components/shared/molecules/SessionAttachmentsDrawer/SessionAttachmentsDrawer.tsx`
**Status:** `Functional`

Right-side inline drawer for persisted conversation files. Shows one attachment per row
with filename, mime/size/timestamp metadata, delete action, and a markdown preview pane
backed by persisted `summary_md`.

#### Open UX issues

_(none)_

---

### `McpServerCard` + option selects (agent form Tools tab)

**Location:** `src/rework/components/pages/TeamAgentsPage/AgentFormModal/McpServerCard/McpServerCard.tsx`
**Status:** `Needs revision`

Renders each MCP server as a toggleable card. When active, exposes `config_fields` as
inline form controls: boolean fields as `SwitchRow`, enum fields as `Select` with per-option
descriptions sourced from `useEnumOptionDescriptions()`.

#### Open UX issues

- **Search policy option descriptions overflow** — `useEnumOptionDescriptions` returns long
  prose strings for `chat_options.search_policy` (`strict`, `hybrid`, `semantic`). These are
  passed as `description` to each `Select` option and render as a single non-wrapping line
  inside the dropdown. On typical viewport widths the text is clipped with no ellipsis or
  tooltip fallback. Fix: render descriptions below the option label with `white-space: normal`
  and a constrained `max-width`, or move to a separate tooltip with wrapping enabled.

- **RAG scope option descriptions overflow** — same issue for `chat_options.search_rag_scope`
  (`corpus_only`, `hybrid`, `general_only`). Translation values like
  `chatbot.ragScope.tooltipCorpus` are full French sentences; they overflow identically.

- **Card toggle area vs. description area** — the entire card header is clickable to toggle
  the server. With config fields expanded below, the boundary between "click to toggle" and
  "interact with a field" is not visually clear. Validate with Maxime whether a separator or
  explicit toggle zone is needed.

#### Resolved

_(none yet)_

---

## OPS-04 / AUTHZ-07 organisms

### `TaskActivity`

**Location:** `src/rework/components/shared/organisms/TaskActivity/TaskActivity.tsx`
**Status:** `Functional`

The one shared task/activity surface (OPS-04 §3.4), rendered identically for platform
and team admins: scheduled/running/completed groups for every task kind, driven by
`GET /tasks`. A `succeeded` migration (platform import) whose structured result carries
warnings shows an explicit "With warnings" flag next to the state badge, plus a
per-row `Disclosure` (AUTHZ-07 Step 3) listing the principal non-zero counters —
including every `*_skipped` counter and `users_processed`, not just the
granted/imported ones (AUTHZ-07 Step 3 close-out) — and the full warning list, open
by default when warnings are present. A `failed` task renders `task.error` inline.

#### Open UX issues

- **Not yet design-reviewed** — implemented and covered by unit tests
  (`TaskActivity.test.tsx`), but no designer/product-owner pass has validated the
  counter disclosure's layout, the "With warnings" flag's visual weight against the
  state badge, or density once a migration result has most of its ~15 counters
  populated at once.

#### Resolved

_(none yet)_

---

## Swift UX bug pass — #2023 / #1952 (2026-07-20)

Fixes shipped together from live-testing feedback; all `Functional`, awaiting
design review.

### `CapabilityCard` (agent form Tools tab)

Toggling a capability no longer changes the name's font size
(`--font-label-medium` → `--font-title-small` caused every card below to jump).
Active emphasis is now weight + `--primary` color at identical metrics; only
the config sub-form still expands, which is expected.

### `TeamFilesystemBrowser` / `AgentFilesystemBrowser` (Resources tabs)

Expanding an empty folder now shows the same explanatory hint pattern as the
corpus workspace (`.hint`, `--on-surface-muted`, body-small) instead of an
empty dropdown: generic `rework.resources.empty.folder` for folders, dedicated
`empty.agentFiles` inside an agent's space, and `empty.agents` when no agent
has files at all.

### `TuningFieldRenderer` — `document_libraries` widget (agent form)

An array field whose `ui.widget` is `document_libraries`
(document_access `library_tag_ids`) renders the `DocumentLibraryScopePicker`
tree instead of the raw tag-id `TagInput`. Unknown widget ids fall back to the
`TagInput`.

### `AgentFormBody` audit footer (#1952)

"Created by" resolves the uid to first/last name (fallback username, then uid)
via `GET /users/by-ids`, and shows "Updated by …" when the instance has been
user-edited (`updated_by`).

### `document_access` config/chat parity with the legacy search tool

The Document access capability now offers the exact configuration surface and
composer controls of "Document search (legacy)": Document library picker and
Document picker toggles (split), Bind to specific libraries gating the
bound-libraries tree (`ui.visible_when`; bound ids are inert while unbound,
like the legacy tool), File attachments, Search policy picker (configured
policy becomes the picker default; enforced only when the picker is hidden),
RAG scope picker + default. All emitted as the same stock widgets — the
choices travel on `RuntimeContext`, which the v2 document-search adapter
already honors. Manifest bumped to 0.3.0; stored older slices revalidate
unchanged (the single scope toggle maps onto the split ones, and a
pre-`bind_libraries` library scope stays binding). The legacy tool's "Bound
document libraries" raw tag-id input now renders as the library tree, gated
on its binding toggle, via `ui.widget` / `ui.visible_when` hints in the pod's
`mcp_catalog.yaml`.

### `DocumentWorkspace` — library deletion

Corpus library folders now carry a delete action (same `canUpdateResources`
gate as upload/new-folder), with a confirmation dialog. Deletion cascades
server-side: sub-folders and the untagging of contained documents are the
backend's `delete_tag_for_user`. Errors surface as a toast with the backend
detail. (Found live 2026-07-20: no delete affordance existed at all.)

### `CategoryPicker` / prompt category surfaces

Pickers and filters offer exactly 7 functional categories (doc-assist,
summary, extraction, writing, analysis, conversational, integration).
`monitoring`, `migration` and `other` are retired from selection but keep
their pill rendering on pre-existing prompts; the "show more" fold is gone
(7 visible).

---

## UX review agenda

_Priority order for the next UX session. Update before each session._

**CHAT-05 new components (first design review needed):**

1. **RichInputField — composer-control chips** — define final visual density for `Hybrid`, `Corpus + web`, `3 libraries`, and attachment chips so they stay quieter than replies and textarea content.
2. **InlineDrawer — mobile width** — `480px` covers most of a phone screen; need a `100vw` breakpoint (code change, blocked on breakpoint decision)
3. **InlineDrawer — WCAG / screen reader** — no focus trap; need `aria-live` region or `aria-label` on the drawer (accessibility review)
4. **ContextualPicker — keyboard navigation** — `ArrowUp`/`ArrowDown` not wired; `aria-activedescendant` missing (code change needed)
5. **SourceCard — active state** — no visual change when the corresponding source is selected (design decision: border? background?)
6. **IndicatorDot — pulse speed** — 1.2 s pulse; validate not distracting during long streaming turns
7. **ActionBar — touch / mobile** — hover-reveal invisible on touch; need a long-press or always-visible variant (design decision)
8. **FaviconIcon — fallback icon** — `description` vs `language` for web URLs (design decision)
9. **NumberedChip — active state** — no ring when the corresponding source is active (design decision)

**Existing components — pending decisions:**

13. **AgentCard — gradient colours** (are the hardcoded conic-gradient hex stops final branding or should they be tokenised?)
14. **AgentCard — disabled card affordance** (`cursor: default` + dimmed icon — confirm whether a label or overlay is needed)
15. **ThoughtTrace — mobile column collapse** (210px column stacks badly on small viewports — breakpoint decision needed)
16. **ThoughtTrace — collapse behaviour** for history-loaded turns (product decision needed)
17. **TraceEntryRow — primary text truncation** (one line vs two lines for `thought` entries)
18. **TraceDetailDrawer — theme wiring** (quick code change once design decision is made)
19. **SourcesPanel — grouping by document** (flat hits vs. grouped by UID — product decision)
20. **Session title fallback** — `"abc12345…"` vs `"New conversation"` (PM decision, no code change needed)
21. **AgentFormModal — tuning field groups** — accordion vs. flat scroll for agents with many fields (UX decision — still open)
22. **AgentFormModal — template browser on mobile** — single-column grid vs. list layout on narrow viewports (UX decision)
23. **AgentFormModal — single-template auto-collapse** — when one template available, hide browser or show non-interactive card?
24. **HitlPrompt — elevation and focus** (interaction design; may require Figma update)
