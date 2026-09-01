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
Used by `CapabilityTeamMatrixDrawer`.

#### Open UX issues

_(none)_

---

### `SearchInput`

**Location:** `src/rework/components/shared/molecules/SearchInput/SearchInput.tsx`
**Status:** `Functional`

`TextInput`-based search field (search icon + inline clear button) — extracted from the pattern
originally inlined in `TeamSettingsMembers`. Props: `value`, `onChange(value: string)`, optional
`placeholder`, `ariaLabel`, `clearAriaLabel`, `autoFocus`.
Used by `PromptsPage` and `TeamSettingsMembers`.

#### Open UX issues

_(none)_

---

### `FilterChips`

**Location:** `src/rework/components/shared/molecules/FilterChips/FilterChips.tsx`
**Status:** `Functional`

Horizontally-wrapping row of toggle chips for single-select filtering. Generic over chip ID type (`T extends string`).
Supports an optional "All" chip (via `allLabel`), expand/collapse beyond `maxVisible`, and full `aria-pressed` accessibility.
Used by `PromptsPage` (replaces native `<button>` category filter row). `PromptsPage` prepends a
"Sans catégorie" pseudo-option (sentinel id, not a real `PromptCategorySummary`) right after the
"All" chip, matching prompts with no `category_id`. Each option can carry an optional `count`,
rendered right after the label with an 8px gap (`PromptsPage` computes a per-category prompt count
from the live prompt list); the "All" chip itself has no count.

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
items (personal + team scope pooled by `GetContextPromptsEarly`) reusing the exact same `PromptCard`
organism and `FilterChips` category filter bar as the team prompt library page (`PromptsPage`), for
visual consistency between the two prompt-browsing surfaces (PROMPT-09 follow-up). `canManage` is
always `false` here (no more-menu — picking, not managing) and the card's click handler is
rewired to `onSelect(id)` instead of opening the read-only view dialog. Categories come from
`GetTeamPromptCategories` scoped to the current team; a pooled prompt whose `category_id` doesn't
match any of those (e.g. a personal-scope prompt's own category) falls into the "Sans catégorie"
bucket rather than crashing or mismatching. The scope badge ("personal"/"team") the old plain-grid
version showed per card is gone — `PromptCard` doesn't render one, and reusing "the exact same card"
was the explicit ask.

---

### `PromptCard` variants + `MarketplacePrompts` (PROMPT-06, #2317)

**Location:** `src/rework/components/shared/organisms/PromptCard/PromptCard.tsx`,
`src/rework/components/pages/marketplace/MarketplacePrompts/MarketplacePrompts.tsx`
**Status:** `Functional`

`PromptCard` gained a `variant` prop (`"team"` | `"marketplace"`). The former
hover-edit pencil is now an always-visible **more-menu** (`IconButtonMenu`,
`more_vert`), mirroring `AgentCard`:

- **team** variant (team library): Edit / Duplicate / Publish|Unpublish / Delete,
  and a bottom-right `storefront` "Published" chip (success-container tokens)
  when the prompt is on the marketplace. Publish, unpublish, and saving an edit
  to a published prompt each go through a confirmation dialog (the spec's
  warnings). Duplicate reuses a prompt-flavoured fork of `DuplicateAgentDialog`.
- **marketplace** variant: the header shows the **author team name** in place of
  the category (each team has its own categories); the more-menu is Import
  (+ Remove from marketplace for editors of the author team). Clicking the card
  opens the read-only view whose only action is copy-to-clipboard — which records
  a marketplace "use" toward the shared counter.

`MarketplacePrompts` ("Prompts de la communauté") reuses the `MarketplaceTeams`
header pattern (`h1` + `SearchInput`) and `FilterChips` (one chip per author
team). Reached from a nav item under the teams marketplace (`MarketplaceNavbar`,
`description` icon) at `/marketplace/prompts`. Import opens `ImportPromptDialog`:
a multi-select of the personal space + every editable team, with an `xs`
`SearchInput` filter.

#### Open UX issues

- **Loading state** — no skeleton shown while `isLoadingSelection` is true; button goes disabled
  but the grid stays visible with stale content. Consider a spinner overlay on the grid during load.
- **Dropped scope badge** — personal vs. team origin is no longer visually distinguished per card
  (see above). Revisit if that turns out to matter in practice.

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

- **M3 alignment (2026-08-03)** — container corner moved from `--radius-m` to `--radius-s`
  (the M3 menu/text-field/chip radius), and a picked row now carries the dedicated
  `--state-on-surface-selected` state layer instead of reusing the transient
  `--state-on-surface-hover`, so a selected option reads as chosen at rest. Token-only, no
  content or row removed. Follow-up: the container border was dropped (the `--shadow-m`
  elevation alone separates it from the background) and the group dividers now use
  `--outline-retreat` (neutral borders must use an `outline-*` token, never `on-surface`)
  and bleed full width (negative horizontal margins cancel the popover padding).

- **Composer sub-menu container (2026-08-03)** — the composer's anchored sub-menus now reuse
  `MenuPopover` as their container instead of a bespoke `.pickerMenu` surface, so menus and
  sub-menus in the composer are all the same component (mirrors `EnumSelectRow`). Each consumer
  keeps only a positioning anchor (absolute placement) and passes its picker content as a single
  `groups` entry; a `pickerSurface` className adds internal scroll for tall content. Applied to
  `ComposerControlSlot` (prompt library) and `DocumentScopeControl` (document/library picker).

- **Pickers stop below the session top bar (2026-08-05, #2245)** — `usePickerMenuMaxHeight`
  clamped the upward-growing pickers against the viewport top, so once the session top bar
  landed (#2214/#2218) an expanded document tree slid under it and got clipped. The hook now
  honors an optional boundary element marked `data-picker-top-boundary` (measured from its
  bottom edge, tracked with a `ResizeObserver` while open); `ManagedChatPage` marks its
  `.topBar`. Pages without a marked boundary keep the viewport-top clamp.

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

As of REASON-01 (#2166) the platform contributed its first non-capability control: a
`Reasoning` On/Off row (`stockKit/ReasoningControl.tsx`). As of 2026-08-12 that row is
**gone from the tune menu**: reasoning is now a **plain text button + chevron**
(`features/capabilities/ReasoningChip.tsx`) pinned at the composer's **right
edge** before the mic — the designer's Composer.html mockup (2026-08-12) is the
reference. The button leads with the MODEL IDENTITY, followed by the reasoning
MODE: "Mistral Small · Boost" when on, "Mistral Small · Rapide" when off (bare
"Raisonnement"/mode labels when no model resolves at all); its menu opens
above, right-aligned, with the effort/latency explainer as a muted header and
the two modes as check-circle rows.

**Two modes, not an on/off switch (#2387).** "Mistral Small · Désactivé" read
as though the MODEL were disabled — the state word sat beside the model name
with nothing tying it to reasoning. Naming both modes removes that reading:
neither describes anything as off. EN uses Fast / Boost.

`Boost` also wears the Chat button's spectrum (`.state[data-on]`), so the one
"the AI is doing more" signal reads the same on the agent card and in the
composer. Two departures from that border: linear rather than conic (a conic
sweep across ~40px of text smears), and no white stops (white travels a border
but is a hole in text, invisible on the light theme) — leaving cyan → violet →
pink. A solid `--primary` sits underneath as the fallback for engines that
ignore `background-clip: text`, and `forced-colors` drops the gradient for the
system palette. The WORD carries the state either way, so colour is
reinforcement, never the only signal. 2026-08-21: the shared stops were
saturated and moderately darkened (same hues) in both places — the original
pastels were near-invisible on the light surface, a fully darkened pass sank
into the dark one; the retained stops sit halfway between, so the single
gradient reads on both themes.

Deliberately NOT a low/medium/high picker — a same-day effort picker was
withdrawn (providers 400 on values they don't support,
`RUNTIME-EXECUTION-CONTRACT.md` §8.48) — and since #2387 not a level DISPLAY
either. The level a reasoning turn runs with is the model's ops-authored
`settings.reasoning_effort`, applied live by the pod; showing it implied a
per-question choice that never existed, and it took two snapshot columns to
reach the composer at all (§8.54). The wire stays the on/off tri-state.

**Superseded in part by #2387 — see "Composer model label" below.** Until then
the model identity came from `params.model_id` on this very control, i.e. the
single model whose REASONING was enabled platform-wide, which is unrelated to
routing; and the chip as a whole was gated on the reasoning control existing.
Both changed: the identity now comes from
`GET /teams/{team_id}/routing-policy/effective-chat-model`, the model shows even
when no reasoning is offered, and the reasoning MENU additionally requires the
routed model to be reasoning-enabled. The author/admin gates below still decide
whether the control is emitted at all — a closed upstream gate removes it
entirely rather than disabling it (`CONTROL-PLANE-PRODUCT-CONTRACT.md` §33). The offer itself lived in the General
section until Amendment C (2026-08-02) moved it into the Capabilities tab, rendered
through the same `CapabilityCard` component every real capability uses (generalized
to a plain `name`/`description`/`subForm` API for this) even though the reasoning
offer still isn't a capability underneath.

As of Amendment B (#2175) that row's **starting** value is the agent author's, not a
constant: the reasoning card grows a second switch nested under `Reasoning` in its own
sub-form area — visible only while `Reasoning` is on, matching how a real capability's
own boolean config field renders — and it seeds the composer row's initial state for
every new conversation. Nothing about the row itself changes: still a per-question
choice the user can flip, still removed entirely when an upstream gate is closed. The
form hint carries the cost of the opt-in (slower, may repeat tool calls on tool-using
agents) so the decision is informed at the point it is made.

#### Open UX issues

- ~~**Boolean-row affordance (REASON-01)**~~ — resolved 2026-08-12 by removal: the
  reasoning row left the tune menu for the right-edge on/off picker chip, so the menu
  carries no boolean row anymore.
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

- **Reasoning preview length** — `ReasoningBlock` clamps the streaming preview to 2 lines.
  Validate that 2 lines is the right budget for long model-native reasoning, or whether the
  card should grow while streaming and clamp only once the block closes.

#### Resolved

- **Reasoning rendered as a tool step (2026-07-30, #2172)** — the trace was one flat list of
  look-alike rows, so the model-native reasoning block sat as row #1 of the tool pile and
  pulsed there for the whole turn (it is opened at the first reasoning token and closed only
  at the first answer delta, so it holds the lowest rank throughout — it read as a tool stuck
  in "running"). The trace is now split into two lanes by `traceUtils.splitTraceEntries()`:
  a reasoning lane rendered by `ReasoningBlock`, and a numbered tool-step lane rendered by
  `TraceEntryRow`. Both lanes are chrome-free (no card border, no fill, no chips) and are
  threaded by a single 1px timeline rail so the turn still reads as a process unfolding.

- **Misleading summary line (2026-07-30, #2172)** — the header read "Thought for 856ms" (the
  sum of *tool* latencies) directly above a reasoning row reading 16.4s. `traceSummary()`
  replaces `thoughtSummaryLabel()` and returns structured data — reasoning wall-clock (max,
  not sum: the model-native block brackets the tool calls), tool count, tool latency, running
  flag — which the component formats through i18n as e.g. "Reasoning 16.4s · 4 tools".

- **Collapse behaviour (2026-07-30, #2172)** — `expanded` was initialised `true` and never
  collapsed; `done` only drove the pulse animation, despite a comment claiming otherwise. The
  block is now open while streaming, auto-collapsed once the turn is done, and an explicit
  toggle is persisted in `localStorage` (`useTraceExpansion`, precedence rule unit-tested via
  the pure `resolveTraceExpanded()`). The stored preference is snapshotted at mount so
  toggling one turn does not retroactively flip every other trace on screen. This also settles
  the history-load question: past turns follow the stored preference, defaulting to collapsed.

- **Chevron legibility (2026-07-30)** — the `›` character is replaced by the `Icon` atom
  (`expand_more` / `expand_less`).

- **Timeline guideline alignment (2026-07-30)** — the guideline moved into `.entries` and is
  positioned off the step-number column width, and `TraceEntryRow` always renders the number
  slot (empty for unnumbered notes) so every status dot sits on the same vertical line.

- **i18n (2026-07-30)** — the trace surface was hardcoded English inside a translated app.
  Its static strings now live under `rework.chatTrace.*` (en + fr), including the reasoning
  phase labels. Tool labels themselves stay English — they are generated by
  `humanizeToolName()` from backend tool names (see #1774).

- **Label chip style — partially (2026-06-18)** — thought rows now use subtle per-phase
  tinted pills (see `TraceEntryRow`) rather than the flat uppercase label; reasoning detail
  opens in the overlay drawer with markdown rendering instead of raw JSON.

- **Repeated content-free "Done" rows (2026-07-22)** — every tool call previously produced
  two trace rows: a "Tool use" phase thought (title "Calling `<tool>`", secondary text always
  the hardcoded literal "Done"/"Error") and the paired `tool_call`/`tool_result` combo row.
  The thought row is now filtered out entirely (`traceUtils.groupTraceEntries()`) — it was
  pure bookkeeping duplication, not agent reasoning. The combo row alone now carries the
  humanized tool label, the status dot, and (new) the real execution latency. See
  `RUNTIME-EXECUTION-CONTRACT.md` §8.21.

---

### `ReasoningBlock`

**Location:** `src/rework/components/shared/molecules/ThoughtTrace/ReasoningBlock/ReasoningBlock.tsx`
**Status:** `Functional`

The reasoning lane of a trace (#2172): one line per reasoning entry — sparkle marker on the
timeline rail, phase label in small caps, duration, and a 2-line clamped preview of the
streaming text. Clicking opens the existing `TraceDetailDrawer` for the full markdown.

Deliberately not a `TraceEntryRow`: reasoning is not a tool step. Three weight decisions,
all from developer review of the first cut, which was judged visually too heavy:

- **No card chrome** — the first version had a bordered, filled card. Removed: the trace is
  secondary UI and must stay lighter than the answer next to it.
- **No phase pill** — the phase renders as plain small-caps retreat text, not the tinted
  `phaseBadge` chip (the chip survives in `TraceDetailDrawer`, where it is the header).
- **One label, not three** — a model-native block used to show a phase chip, the backend
  title ("Model reasoning") and a "Model" chip. The title and chip are dropped for
  `source="model_native"` (they say nothing the phase doesn't); authored titles are kept,
  since an author wrote them.

The marker aligns on `--trace-rail-x`, the rail geometry `ThoughtTrace` sets on `.body` and
cascades to both lanes — so the rail threads the reasoning marker and every step dot with no
per-component magic numbers.

---

### `TraceEntryRow`

**Location:** `src/rework/components/shared/molecules/ThoughtTrace/TraceEntryRow/TraceEntryRow.tsx`
**Spec:** [`CHAT-COMPONENT-SPECS.md §2`](../design/CHAT-COMPONENT-SPECS.md)
**Status:** `Functional`

#### Open UX issues

- **Long tool labels** — humanized labels can be long ("Getting tabular documents schemas").
  They ellipsis-truncate before the discriminator chip; validate the truncation point at
  narrow widths.

#### Resolved

- **Tool step showed "running" before the HITL confirmation was even answered, and one
  confirmation was asked per document instead of once for the whole folder (2026-08-03)** —
  a HITL-gated tool call (`document_access`'s `summarize_document` in particular) rendered its
  trace row as `running…` (pending status, same as any in-flight call) the instant the model
  proposed it, well before the user had answered the "Confirm tool execution" prompt: the
  backend streams the `ToolCallRuntimeEvent` when the model node commits, a separate and
  earlier graph step than the HITL gate that pauses for approval, and the two are otherwise
  indistinguishable to `statusForEntry()` (no result yet either way). Separately, asking to
  summarize N documents meant N sequential confirmation prompts — pure friction, since
  cancelling any one already skipped the whole batch (#2177).
  `TraceStatus` gains `awaiting_confirmation`; `HumanInputRequest.pending_calls` (a real typed
  field now, replacing an interim `metadata.tool_call_id` — see `RUNTIME-EXECUTION-CONTRACT.md`
  §8.36) carries every gated call's id in ONE combined prompt, so `statusForEntry`/`traceSummary`
  take a `pendingToolCallIds: string[]` and every row in a batch reads "awaiting confirmation…"
  (same amber pulse as `pending`) simultaneously, not just the first. The trace header follows
  suit via `TraceSummary.awaitingConfirmation`.

- **Step numbers + curated discriminator (2026-07-30, #2172)** — two calls to the same tool
  rendered as byte-identical rows ("READING QUERY" ×2), because the redaction rule from
  #1774/CHAT-13 shows neither the raw tool name nor the arguments. Rows now carry a permanent
  1-based step number (replacing the hover-reveal index, which was too subtle) and, when the
  result matches a recognised curated shape, a volume discriminator chip: `12 rows`
  (`SqlQueryResult`) or `5 sources` (`RagSearchResult`), from `traceUtils.toolDiscriminator()`.
  Only volume metadata is exposed — raw arguments and raw result content stay redacted.
  Failed and unrecognised results get no chip; the red status dot already carries the failure.

- **Row layout (2026-07-30)** — the two-row grid is replaced by a single flex line
  `[n] ● label · discriminator … latency`, with latency trailing right. The second grid row
  (which started at column 4 and skipped the dot/index columns) is gone, and with it the
  primary-text-truncation question for thought entries: reasoning text now lives in
  `ReasoningBlock`, not in this row.

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

- **Per-call source curation** — the RAG tool view reads `hits` straight out of the tool's
  raw `content` JSON (the same list the LLM sees), not the narrower, curated
  `ToolResultRuntimeEvent.sources` (built via `select_citable_sources()`, which drops
  dataset-pointer chunks and low-relevance hits). Wiring per-call `sources` through
  `ToolResultPart` would need a new additive field end-to-end (backend schema + persistence
  + SSE consumption) — a reasonable fast-follow, not required for the current fix since
  `content` already carries enough to render useful citations.

- **Unrecognized-tool fallback still raw JSON** — two content shapes (SQL
  `{sql_query, rows, error}`, RAG `{query, hits}`) plus two named first-party tools
  (`summarize_document`, `list_document_tree`, see Resolved below) are recognized; any
  other tool still falls back to the redacted `{action, status, latency}` JSON view.
  Intentional (see Resolved below) but the list of recognized tools/shapes may need to
  grow as more tools are added.

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

- **Curated tool-result views for SQL and RAG (2026-07-22)** — tool call/result entries no
  longer always render the blanket-redacted `{action, status, latency}` JSON (from
  #1774/CHAT-13). Two common, specifically useful content shapes are now recognized and
  rendered richly: a tabular/SQL result (`{sql_query, rows, error}`) shows the executed SQL
  plus a row-count and preview; a RAG/vector-search result (`{query, hits}`) shows the
  search query plus retrieved sources via the existing `SourcesPanel` molecule. Any other
  tool shape still falls back to the original redacted view — see
  `RUNTIME-EXECUTION-CONTRACT.md` §8.21.

- **Curated views for `summarize_document` and `list_document_tree` (2026-07-31)** — these
  two first-party document-capability tools return plain text (a prose summary / an
  indented tree listing), not a JSON envelope, so they can't be recognized by content
  shape like SQL/RAG — they're recognized by tool name instead (`isSummarizeDocumentTool`,
  `isDocumentTreeTool` in `traceUtils.ts`), still a curated allowlist rather than a
  blanket raw-text pass-through. `summarize_document` renders its summary through the
  existing `MarkdownRenderer` (same treatment as reasoning text) instead of a JSON dump.
  `list_document_tree` renders the tree in a plaintext `CodeBlock`, with the bracketed
  internal `document_uid` after each entry stripped before display (`stripDocumentUids()`)
  — the tool's own docstring already forbids the model from repeating that id to the end
  user; the drawer now honors the same identifier-hygiene rule. The header copy action
  copies the summary text / the uid-stripped tree text respectively.

- **Monaco replaced by `CodeBlock`, single header copy action (2026-07-22)** — manual UI
  testing found the Monaco JSON pane (forced `vs-dark`, editor chrome, imposed fixed
  heights — the theme open issue above) heavy for what's often a 3-line payload, and each
  view had its own scattered copy button. `MonacoPane` is no longer used anywhere in this
  drawer (nor anywhere else in the frontend — the atom, `@monaco-editor/react`, and
  `monaco-editor` were removed from the codebase entirely). `InlineDrawer` gained a
  `headerActions` slot (next to the close button) that now hosts a single copy action:
  the SQL query text for the SQL view, the curated JSON for the generic fallback, nothing
  for the RAG view (sources are browsed via `SourcesPanel`, not copied as text). The
  generic fallback and the SQL row preview render through the same lightweight `CodeBlock`
  used for the SQL query itself (Prism syntax highlighting, no editor chrome, no imposed
  height — the drawer body scrolls naturally instead).

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

- **`sanitizeSchema` drops `<ol start>` and GFM task-list `checked` (#2347)** — `rehype-sanitize`'s
  `defaultSchema` (extended here) whitelists neither `start` on `<ol>` nor `checked` on
  `<input type="checkbox">`, so both are stripped before the DOM exists — a renumbered ordered list
  always renders from 1, and a GFM checklist (`- [x] done`) loses its checked/unchecked state on
  screen. Not a rendering bug introduced elsewhere; the fix is whitelisting both in this schema.

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

### `Chip` atom + composer consolidation (`ManagedChatPage`, 2026-08-03)

**Location:** `src/rework/components/shared/atoms/Chip/`,
`src/rework/components/shared/molecules/RichInputField/`,
`src/rework/components/shared/atoms/IconButton/`

**Status:** `Functional`

Three related changes on the chat composer, all consolidating hand-rolled UI onto the shared
library:

- **`Chip` atom (new)** — a removable M3 input chip (`--radius-s`, neutral outline, no resting
  shadow): optional leading visual, truncating label, optional secondary line, optional trailing
  content, optional remove button, and a `tone="error"` that recolors the pill to the
  error-container role. `AttachmentChips` renders this atom instead of duplicating pill markup —
  it keeps only its own scroll row and its muted leading icon. (`ContextPromptChips` also used it
  briefly, before context prompts moved to insert-into-input — see the 2026-08-03 prompt-library
  entry below.)

- **`IconButton` tonal variant (new)** — adds the M3 _filled tonal_ style (container =
  scheme `container` role, icon = `on-container`, state layer in the `on-container` color;
  disabled inherits the shared on-surface 12%/38% rule). Spec taken from the official M3 icon
  button guidelines, mapped through the local scheme tokens.

- **Composer action buttons** — the send/stop/voice buttons in `RichInputField` were hand-rolled
  `<button>`s; they are now the shared `IconButton` atom (send/stop = `filled` `primary`, mic =
  `tonal` `secondary`, recording = `tonal` `error`, transcribing = `tonal` with the `loading`
  spinner). Consequence: the action buttons are now circular (the atom's shape) rather than the
  previous rounded square; the subtle pop-in on appearance is preserved.

- **Page surface** — the chat page background (`ManagedChatPage` `.page`/`.mainColumn`/`.topBar`
  and the composer's fade-to-page gradient) moved from `--surface-container-lowest` to
  `--surface-main`.

---

### Chat input length states (`RichInputField`, `HitlPrompt`, 2026-08-12, updated 2026-08-13)

**Location:** `src/rework/components/shared/atoms/CharacterLimitNotice/`,
`src/rework/components/shared/molecules/RichInputField/`,
`src/rework/components/shared/molecules/HitlPrompt/`,
`src/rework/components/pages/ManagedChatPage/`

**Status:** `Functional`

The managed-chat composer and active HITL free-text prompt enforce the optional
runtime-published character policy from execution preparation. Both count Unicode code points;
ordinary chat counts the trimmed value that will be submitted, while HITL counts the exact free
text. Both render the shared `CharacterLimitNotice`, which owns the states below — the field
itself owns only `aria-invalid` and its send gating.

- At or below the limit, nothing is visible — no counter, no error colour — and send stays
  available. An ordinary message sits far below a limit measured in thousands of code points
  (5,000 in the default template, but it is per-template and admin-configurable), so a
  permanently visible counter would report a non-problem for the whole life of the draft
  (2026-08-13, issue #2358).
- Above the limit, the error copy and the counter appear together as one error-coloured region,
  the input is marked `aria-invalid`, and only the corresponding free-text send action is
  disabled. Fixed HITL choices remain available because selecting one submits the identifier
  without the oversized free-text draft; the runtime still validates any submitted `choice_id`,
  `answer`, and `text` fields.
- The notice stays mounted whenever a limit is published, empty and out of flow while the draft is
  within it: an `aria-live` region inserted into the DOM at the same time as its text is not
  announced, and a permanently mounted node also keeps the field's `aria-describedby` from
  pointing at a removed id as the draft crosses back and forth. The count sits outside the live
  region — inside, it would re-announce on every keystroke.
- Text remains fully editable: neither component sets native `maxLength`, truncates pasted or
  dictated content, nor clears an oversized draft. A backend length rejection restores the
  ordinary draft or pending HITL prompt safely.
- During a rolling upgrade, an older runtime may omit the policy. In that state no counter is
  shown and the runtime remains the authoritative enforcement boundary.

---

### Prompt library → insert into composer (`ContextPromptPicker`, 2026-08-03)

**Location:** `src/rework/components/shared/molecules/ContextPromptPicker/`,
`src/rework/features/capabilities/ComposerControlSlot.tsx`,
`src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`

**Status:** `Functional`

Picking a prompt in the composer's `Prompts` row now **inserts the prompt's content into the
chat input** instead of attaching it as a session-context chip.

- `ContextPromptPicker` went from a multi-select toggle (checkboxes, `selectedIds`/`onChange`) to
  a one-shot action list (`onSelect(prompt)`, `role="menu"`/`menuitem`). Picking a row fetches the
  full prompt (`GetTeamPrompt` — the `text` lives on the record, not the `ContextPromptSummary`),
  appends it to the draft (`\n\n`-separated when the draft is non-empty), and closes the actions
  popover. Scope resolves the owning team: `personal` → the user's personal team, `team` → the
  chat team.
- `RichInputField` now resizes the textarea on any external value change (not just clear), so
  inserted (and voice-transcribed) text grows the box instead of being clipped at one row.
- The context-prompt **chip** UI was removed: `ContextPromptChips` (molecule + test) is deleted,
  and the composer no longer renders attached-prompt pills. The backend session-context channel
  (`contextPromptIds` → `context_prompt_text`, PROMPT-05) is left in place but is now **dormant**
  — nothing in the composer writes to it. Fully retiring it (store + runtime contract) is a
  separate change, not done here.
- Picker rows were simplified to name + description (+ score stars): the leading icon and the
  usage count were removed. The picker's `MenuPopover` uses an 8px padding for this instance via
  the `pickerSurface` className.

---

### Composer: split the actions menu into "add" + "tune" (2026-08-03)

**Location:** `src/rework/components/shared/molecules/ComposerActionsMenu/`,
`src/rework/features/capabilities/ComposerControlSlot.tsx`,
`src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`

**Status:** `Functional`

The composer now shows two trigger buttons side by side instead of one:

- **Add** (`add` icon) — the attach action + the always-on prompt-library row.
- **Tune** (`tune` icon, to its right) — the remaining tool controls (search policy, document
  scope, reasoning). It only renders when the agent exposes at least one such control. RAG scope
  moved out to an always-visible chip (2026-08-05) — see below. Which specific controls sit in
  the tune menu vs. a standalone chip is expected to keep changing as positioning is iterated on;
  check `COMPOSER_CHIP_WIDGETS` in `ComposerOptionChips.tsx` for the current split rather than
  trusting this bullet to stay exhaustive.

Both open the same `MenuPopover`-based popover. `ComposerActionsMenu` gained `icon` /
`openAriaLabel` / `dialogAriaLabel` props (defaulting to the add-menu values), and
`ComposerControlSlot` gained a `part: "primary" | "tools"` prop selecting which control groups it
renders — so the two buttons reuse the same component. The two triggers are spaced by the
composer's `commandSlot` gap. The tune popover (`.controlSlotBox`) hugs its content
(`width: fit-content`, capped at 380px / viewport, 2026-08-06) rather than a fixed 380px, so it's
as wide as its widest row.

---

### Composer option chips — scope (2026-08-05, iterated 2026-08-06)

**Location:** `src/rework/components/shared/molecules/ContextualPicker/`,
`src/rework/features/capabilities/ComposerOptionChips.tsx`,
`src/rework/features/capabilities/ComposerControlSlot.tsx`,
`src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`

**Status:** `Functional`

A row of `ContextualPicker` chips sits in the composer's bottom row, right after the add/tune
buttons (`RichInputField`'s `topSlot`) — one chip per closed-set chat-turn setting currently
promoted out of the tune menu, each showing an icon + its current value and opening a popover
above itself to change it. Visual reference: Gemini's "Deep Search" chip. Reuses existing composer
state (`useComposerSettings`) — no new backend concept.

- `ComposerOptionChips` (host) resolves `chat_controls` the same way `ComposerControlSlot` does
  and renders a chip only when the corresponding widget is actually present for the active agent —
  an agent without RAG scope enabled shows no scope chip, exactly like the tune-menu row it
  replaces.
- `COMPOSER_CHIP_WIDGETS`, exported from `ComposerOptionChips.tsx`, is the single source of truth
  for which widgets are promoted to a chip right now: `ComposerControlSlot` excludes them from its
  `part="tools"` render (avoids the same setting living in two places), and `ManagedChatPage`'s
  `hasToolControls` guard excludes them too — otherwise an agent exposing only chip-promoted
  controls would show a "tune" button opening onto an empty popover. **This set is expected to
  change often** as the developer iterates on where each control reads best — to move a widget
  back into the tune menu, remove it from the set and delete its chip JSX in
  `ComposerOptionChips.tsx`; its `EnumSelectRow`-based row in `stockKit/` was never deleted, so it
  reappears in the tune popover with no other change needed (see `SearchPolicyControl`, which did
  exactly this round-trip: chip 2026-08-05 → back in the tune menu 2026-08-06).
- Currently chipped: **scope** only (`rag_scope`, `book_2` icon — `hub` until 2026-08-06). Search
  mode (`search_policy`) is back in the tune menu as of 2026-08-06.
- RAG scope's value labels changed for readability outside the tune-menu row's fuller context:
  "Corpus" / "Corpus + web" / "Général" → **"Ressources" / "Modèle + Ressources" / "Modèle"**
  (`chatbot.composerSettings.scopeCorpus`/`scopeCorpusAndWeb`/`scopeGeneral` — same i18n keys, new
  values, fr and en) — this relabel stuck through the search-policy round-trip since it's
  independent of chip-vs-row placement.
- `SearchPolicyControl`/`RagScopeControl` (the `EnumSelectRow`-based stock-kit rows) stay
  registered in `stockChatTurnControlKit` regardless of chip/row placement — only excluded from
  `ComposerControlSlot`'s `"tools"` render while chipped, never deleted.
- **Active-choice accent (2026-08-06)** — in the search-mode submenu (the only `EnumSelectRow`
  still in the tune popover) and the scope chip's options popover (`ContextualPicker`), the picked
  option renders its label + trailing check in `--primary` over a `--state-primary-selected`
  (primary-tinted 16%) background layer, instead of the neutral on-surface selected layer. Opt-in
  via a new `accentSelected` prop threaded `SearchPolicyControl` → `EnumSelectRow` →
  `MenuPopoverItem`, and set directly by `ContextualPicker` on its own options
  (`data-accent-selected` + `data-selected` gate the CSS) — every other `MenuPopoverItem` selected
  state (RagScopeControl's tune-menu row, profile menu, …) is unaffected.

---

### Document-scope side panel (2026-08-06)

**Location:** `src/rework/components/shared/molecules/DocumentScopePanel/`,
`src/rework/features/capabilities/stockKit/DocumentScopeControl.tsx`,
`src/rework/components/shared/molecules/ComposerActionsMenu/`,
`src/rework/components/pages/ManagedChatPage/ManagedChatPage.tsx`

**Status:** `Functional`

The composer's `document_scope` control (the resource/library picker) moved out of a cramped
inline popover into a full-height right-side push panel (#2259).

- The `document_scope` row in the "tune" popover is now a **launcher**: clicking it closes the
  tune menu and opens `DocumentScopePanel` — an `InlineDrawer layout="push"` sharing
  `ManagedChatPage`'s single push-drawer slot (`activePushDrawer`), so it never stacks with the
  attachments / capability panels. The old inline `MenuPopover` + `usePickerMenuMaxHeight` anchor
  in `DocumentScopeControl` is gone; the row just computes the current-selection summary and calls
  `composer.onOpenDocumentScopePanel` (a new field on `ChatTurnControlComposerState`). The row has
  no trailing chevron (2026-08-06) — it opens a panel, not an inline sub-popover. Its
  library-count value label reads "N dossiers" (`librariesCount`, relabelled from
  "N bibliothèques" — this key is composer-only, so the agent-form wording is untouched; the
  picker's own shared strings, e.g. the empty state, still say "bibliothèque").
- Panel: rendered as a **floating card** (`InlineDrawer floating`, 2026-08-06) — inset from every
  edge with a single `outline-muted` 1px border, `--radius-m` (16px) corners and a subtle
  `--shadow-s` (border/radius softened from the initial `outline-retreat`/24px on 2026-08-06),
  dropping the push drawer's flush edge border and the header divider. Header title "Définir les
  ressources accessibles" + `InlineDrawer`'s built-in close, plus a **Réinitialiser** icon button
  (Tooltip) in `headerActions`. Body reuses the existing `DocumentLibraryScopePicker` at full
  height, `flushBody` + a 16px left/right/bottom inset (top stays flush under the header). The
  picker mounts only while the panel is open so its tag/document queries don't fire for every chat
  that merely exposes the control. In the tree, the folder tile is fully clickable to expand:
  `nodeTrigger` is an absolutely-positioned button filling the whole `nodeRow` (padding included),
  with the visible content above it (`pointer-events: none` on the non-interactive parts so clicks
  fall through, the checkbox kept interactive above). Tiles are borderless on a `surface-main`
  background and take the standard 8% `on-surface` hover state-layer (the trigger's hover
  background), matching buttons and other hoverable zones (2026-08-06).
- **Reset** reverts the per-turn selection to the agent's configured scope. For an agent that
  binds specific libraries at creation (`bind_libraries` → `bound_library_ids`), the library tree
  stays read-only and reset clears only any per-turn document narrowing back to that bound
  baseline; for an unbound agent, reset clears to empty (no per-agent *editable* default exists in
  the data today — this is frontend-only). Reset is disabled when the selection already equals the
  agent scope.
- **Tune badge**: `ComposerActionsMenu` gained a `badge` prop (a small `--error` dot over the
  trigger). `ManagedChatPage` sets it when a ponctual document-scope override is active
  (`hasPonctualDocumentScope`: a non-empty document selection, or — for unbound agents — a
  non-empty library selection), signalling the agent's resource access is narrowed for this
  conversation.

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

- **Multi-turn selection copy (#2346)** — a manual selection contained inside one reply gets the
  clean clipboard serialisation described below; one that spans multiple assistant replies (or
  includes chrome between them — `ActionBar`, source cards, `ThoughtTrace`) falls back to the
  browser's native copy, which reintroduces the theme-background leak this feature exists to fix.

#### Resolved

- **Props changed (2026-04-27)** — `finalMessages: ChatMessage[]` replaced by `text: string`.
  Text is now pre-extracted by `toConversationMessages` in `ManagedChatPage` and passed directly.

- **Artifact download links (2026-06-22, FILES-04)** — `AssistantTurn` now renders `ArtifactLinks`
  below the reply when the agent emits `LinkPart` ui_parts.

- **Copy response — always visible, email-safe clipboard (2026-08-12, #2336)** — the per-message
  copy action (`ActionBar`, `alwaysVisible`) was hover-only and easy to miss; it's now shown
  permanently and gives a transient "Copied" confirmation. Both the button and a manual text
  selection inside a reply write clipboard content built by `rework/utils/clipboardUtils.ts`
  instead of relying on the browser's default copy, which inlined the message surface's computed
  `background-color` into the pasted `text/html` — a pink or near-black highlight depending on
  theme. The serialiser emits email-safe HTML (inline `pt`-sized styles, no color/background/font
  overrides, so pasted text inherits the destination document's own typography — targets Outlook's
  Word rendering engine) alongside plain text. Mermaid/MindMap diagrams and KaTeX formulas degrade
  to a `[diagram: <label>]` / `[formula]` placeholder rather than leaking rendering chrome (button
  labels, breadcrumbs) or garbled glyph text — KaTeX runs with `output: "html"` here, so no
  TeX-source annotation exists in the DOM to recover the original formula from. Fixing that would
  mean switching to `output: "htmlAndMathml"` and whitelisting MathML in `sanitizeSchema` below —
  not yet tracked as its own issue. Known limitation: see multi-turn selection above (#2346).

- **Copy confirmation is now the shared one (2026-08-13, #2359)** — `UserTurn` had shipped a
  parallel copy affordance the same week; both turns now use the same `ActionBar` action,
  the same `content_copy` → `check` flip and the same 2s revert, and the labels are
  translated on both sides (they were hardcoded English here). The 2s revert timer is also
  now cancelled before re-arming and on unmount: clicking copy twice inside the window used
  to have the first click's timer cut the second confirmation short after ~0.1s. The
  clipboard *payload* stays asymmetric on purpose: assistant replies go through
  `clipboardUtils`, user messages are plain text and use `writeText`. See `UserTurn` below.

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

**Markdown toggle (2026-07-27).** A `mode` prop (`"original" | "markdown"`, default
`"original"`) lets a host force the markdown extraction for a format that has a native
renderer. The corpus preview drawer exposes it as an icon button in the `InlineDrawer`
header (`headerActions`, left of the close button), gated on `hasNativePreview(fileName)`
so it only appears for PDFs: `.docx`/`.xlsx`/`.csv` already display their markdown
extraction, so a toggle there would be inert. Mode resets to `"original"` on every newly
opened document. When the extraction is missing (endpoint 404s, or empty body), the body
renders a `preview.markdownUnavailable` notice instead of the former literal
"Error loading document." string, which read as document content.

**Virtualized PDF rendering (2026-08-07, #2273).** `PdfStreamingDocumentViewer`
previously mounted one live `<canvas>` per page of the document the moment it
loaded; at ~3.5 MB of bitmap per page that allocated gigabytes on a large PDF and
crashed the browser tab. The viewer now renders one cheap, correctly-sized
placeholder slot per page — so the scrollbar still reflects the document's real
length — and mounts a real `<Page>` only for slots inside a 600 px band around
the viewport, tracked by a single `IntersectionObserver`. Placeholders are sized
from page 1's own geometry (A4 portrait as fallback), so the scroll extent is
right for landscape and slide-shaped documents too. pdf.js is additionally given
`disableAutoFetch: true` so it fetches byte ranges on demand against the
`Accept-Ranges: bytes` support `/raw_content/stream/{uid}` already provides,
instead of buffering the whole file up front.

**Large-document guard (2026-08-07, #2273).** Past 500 pages the viewer shows an
opt-in panel (`preview.pdf.largeTitle` / `largeBody` / `largeConfirm`) reporting
the page count, with an "afficher quand même" action, instead of rendering
immediately. Virtualization bounds the canvases, but one placeholder plus one
observer entry per page is not free and pdf.js still walks the whole page tree —
so the pathological shape stays behind an explicit choice. The state resets on
every newly opened document.

#### Open UX issues

- **Assistant side panel** — FRONT-13's other half (collapsible "ask the assistant"
  panel next to the viewer) is not built yet, blocked on an agent-selection product
  decision — see `FRONTEND-BACKLOG.md` §19.
- **PDF toolbar** — no page count, zoom, or page-jump controls; pages render as one
  continuous scroll at the container's full width (`PDF_SCALE = 1.0`). Revisit if
  users report needing them.
- **Chunk highlighting** — `#chunk=...` fragment handling remains deferred (CHAT-08),
  unaffected by this component.

#### Resolved

_(none yet)_

---

### `HitlPrompt`

**Location:** `src/rework/components/shared/molecules/HitlPrompt/HitlPrompt.tsx`
**Status:** `Functional`

#### Open UX issues

- **Focus management** — when `HitlPrompt` appears, focus should move to the first
  actionable element (first choice button or the free-text input). Not yet implemented.

#### Resolved

- **Choice row hidden once answered; active-state border/shadow (2026-08-05)** — the
  choices row (and its right-alignment fix below) now renders only when `!readonly`:
  once a question is answered, the frozen `hitl_request` history row shows just the
  title/question, since the answer already appears as the `hitl_response` turn
  immediately after it in the thread — a disabled button row was redundant. This also
  resolves the former "Frozen card visual distinction" issue (there's no longer a button
  row to visually differentiate). Button right/left position now comes from an explicit
  `order` style (`order: 2` for the default choice, `order: 1` for the rest) rather than
  pre-sorting the array — the sort-based approach silently broke whenever a choice's
  `default` flag wasn't available (e.g. `HitlChoiceRecord`, the persisted-history type,
  never carried it), so `order` is the robust fix. A live (`!readonly`) card also gets
  `.active`: the same `border-color: var(--primary)` + primary-tinted glow `box-shadow`
  as `RichInputField`'s focused composer field (`RichInputField.module.css`
  `.field:focus-within`) — resolves the former "Elevation / containment" issue by
  signalling "needs your input" with the same visual language as the chat field.

- **Card containment + button restyle (2026-08-05)** — `.card` now uses
  `surface-container-high` background and an `outline-retreat` border (up from
  `surface-container`/`outline`). `.title` is `primary`/`title-medium` (was
  `on-surface`/`title-small`); `.question` is `body-medium` (was `body-large`). Choice
  buttons use the shared `Button` atom's `default` signal from
  `HumanChoiceOption.default` — the default choice (e.g. "Continuer"/"Proceed") renders
  `variant="filled" color="primary"`, non-default choices (e.g. "Annuler"/"Cancel")
  render `variant="text" color="on-surface-retreat"` — right-aligned
  (`justify-content: flex-end`) with the default choice ordered last so it lands
  rightmost.

- **`readonly` prop added (2026-04-27)** — `HitlPrompt` now accepts `readonly?: boolean`.
  When set, the choices row and free-text section are hidden entirely (2026-08-05 —
  previously choices were only disabled, not hidden; see above). Used by
  `ManagedChatPage` when rendering `hitl_request` history rows.

- **Dropped its own `max-width: 72%` / `align-self: flex-start` (2026-07-22)** — `HitlPrompt`
  was missed by the 720px centered lane refactor (2026-05-18): it kept a scattered per-component
  width constraint instead of filling `.lane` like its siblings, which cramped content-heavy
  cards (e.g. a multi-finding classification table) into a narrow column with excess whitespace
  beside it.

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

### Delete confirmation in `ChatList` (2026-07-26)

**Location:**
`src/rework/components/shared/organisms/ChatList/ChatList.tsx`,
`src/rework/components/shared/organisms/ChatList/ChatListItem/ChatListItem.tsx`
**Status:** `Functional`

Clicking a session tile's `DeleteIconButton` used to call the delete
mutation immediately, with no confirmation step (and swallowed the error
silently). Now opens the shared `ConfirmationDialog` (via
`useConfirmationDialog`, already wrapping the app in `App.tsx`) first —
the mutation only fires from `onConfirm`. Same inverted-emphasis
destructive pattern as "Delete agent" (`TeamAgentsPage`) and "Leave team"
(`LeaveTeamButton`): `criticalAction: true`, `cancelVariant: "filled"` /
`cancelColor: "primary"` (Cancel stays the visually dominant filled
button), `confirmVariant: "text"` (Delete drops to a low-emphasis text
button, colored `error` via `criticalAction`). New i18n keys under
`rework.sidebar.chatList.deleteDialog.{title,message,confirm,cancel}`,
message interpolates the session's own displayed label (title, or the
UUID-prefix fallback from the open issue above) — same shape as
`rework.agentCard.deleteDialog`.

---

### `ChatList` meta line and nav panel width (2026-08-20)

**Location:**
`src/rework/components/shared/organisms/ChatList/ChatListItem/ChatListItem.tsx`,
`src/rework/components/shared/organisms/ChatList/ChatList.module.scss`,
`Sidebar/{TeamContentNavbar,HomeNavPanel,MarketplaceNavbar,AdminNavbar}` stylesheets
**Status:** `Functional`

The conversation row's second line (`<agent name> · DD/MM/YY - HH:mm`) wrapped
onto a second line whenever the agent name was long, colliding with the next
row and making the list unreadable. Two changes:

- The meta line is now a nowrap flex row where **only the agent name flexes**
  (`flex: 1 1 auto; min-width: 0; text-overflow: ellipsis`, full name in
  `title`); the separator and the date are `flex: 0 0 auto`, so the date and
  time always render whole. Same ellipsis treatment on `.groupHeader`, the
  per-agent sub-list header shown when grouping is on.
- Vertical column alignment (2026-08-21): the agent name **grows** to fill the
  row, so its box is the same width on every line — short names leave a gap,
  long names ellipsize — and the `·` separator and date start at the same x
  everywhere. The date also uses `font-variant-numeric: tabular-nums`, so the
  fixed `DD/MM/YY - HH:mm` format always renders at the same width regardless
  of which digits it contains.
- All four nav panels went **240px → 272px**. They swap into the same sidebar
  grid column, so the width must stay identical across them or the column
  jumps when switching between Home / team / marketplace / admin.

---

### `AgentCard`

**Location:** `src/rework/components/shared/organisms/AgentCard/AgentCard.tsx`
**Status:** `Functional`

Displays one managed agent instance. Current layout (#2096, superseding the #2076 toolbar-restructure pass):

- Header row: icon, name, role (short one-liner) — and, only for users who can manage agents in the team, a `⋮` **more menu** flush to the top-right (`IconButtonMenu`), containing Edit, Activate/Deactivate, Duplicate, and Delete (rendered in the error color via `MenuItem`'s new `destructive` prop).
- Description (3-line clamp).
- Suspension/catalog warning banner, when applicable.
- Footer row: an always-visible `i` **info icon** (bottom-left, not gated on any permission) that reveals a rich instant-hover `Tooltip` above it — Origin (raw `source_runtime_id`) and Template on their own rows, plus Created-by/Last-updated-by (name + short date, only shown when set) — and the **Chat** button (bottom-right), disabled unless the instance is enabled.
- The origin/template line that used to sit under the agent name (#2076) is gone from the card body entirely — it only lives in the info tooltip now.
- **Duplicate** opens `DuplicateAgentDialog` (name field prefilled with the source's name); confirming rebuilds a `CreateAgentInstanceRequest` from the source instance via the same `buildAgentFormSubmitPayload`/`extractCapabilityConfigValues` helpers the edit form uses (correct capability filtering against the live template), then calls the normal create endpoint — no backend change.
- **Delete** reuses `TeamAgentsPage`'s existing `handleDelete` (previously only reachable from inside the edit modal) via the same `ConfirmationDialog`, with the same inverted emphasis as the "Leave team" dialog: Cancel is `filled`/primary (visually dominant, the safe choice), Delete is `text`/error (low emphasis).
- The `Tooltip` atom gained an optional `content: ReactNode` prop (alongside the existing `text: string`) for this rich variant — sizes to content instead of forcing a single nowrap line, same hover/`:focus-within`/above-anchor positioning as every other tooltip in the app.
- Disabled cards render with muted colours, driven by the existing `data-enabled` CSS custom-property cascade (unchanged by #2096).
- The Chat button's hover treatment (rotating conic-gradient border) is unchanged from #2076.

#### Open UX issues

- Not yet design-reviewed against a live stack. First functional pass only.
- **Gradient animation colours** — the spectrum stops (`#37c9e4`, `#6f78fc`, `#e4ae66`, `#db47ae` — saturated and moderately darkened 2026-08-21 from the original pastels, same hues: the pastels washed out on the light theme, a fully darkened pass sank into the dark one, so these sit halfway between; one gradient serves both themes) are intentional branding colours outside the semantic token system — confirm with designer whether they should be folded into it or kept as-is. Since 2026-08-27 they live once in `styles/gradients.css` as `--gradient-spectrum-stops` (full, for borders) and `--gradient-spectrum-stops-core` (saturated run only, for gradients clipped to text), with the rotating-border recipe in the `spectrum-border` SCSS mixin. Three consumers: this Chat button, the Home page's recently-used agent tiles (same "start a conversation with this agent" affordance), and the composer's `Boost` text.

#### Resolved

- **Toolbar restructure (#2076)** — edit/toggle icon buttons moved from a persistent bottom-left pair into the top-right more-menu (#2096); the whole-card click-to-chat interaction was already removed in #2076 in favour of the explicit Chat button.
- **Extracted to reusable organism** — card logic was previously inlined (575 lines) in `TeamAgentsPage.tsx`. Now in `shared/organisms/AgentCard/` with a clean prop interface against `ManagedAgentInstanceSummary`.

---

### `TeamCard`

**Location:** `src/rework/components/shared/organisms/TeamCard/TeamCard.tsx`
**Status:** `Functional`

Displays one team in the marketplace (`MarketplaceTeams`). The footer's join
affordance (TEAM-09, narrowed to 2 states 2026-07-26) is driven entirely by
the team's `joining_mode`, gated on `!team.is_member`:

| `joining_mode` | Footer content |
| --- | --- |
| `open` | "Join" button (`person_add` icon) — calls `useJoinTeamMutation` directly (instant self-service, no confirmation step); on success calls the `onJoined` prop so the page can refresh anything outside this card's own cache (bootstrap's team navbar) |
| `invite_only`, team is `public`, at least one admin has an email | "Join" button (`mail` icon) - opens the user's mail client on a `mailto:` prefilled for the team admins (#2453, see below) |
| `invite_only`, any other case | No button; muted label (`on-surface-retreat`) |
| already a member | Nothing renders in the footer's join slot |

The former lock icon next to the team name (driven by the retired
`is_private` bool) was removed rather than remapped to `joining_mode` — the
footer label already communicates restricted-join state more specifically,
so keeping both would duplicate the signal.

`request_only` (a disabled "Request to join" button — the notification
system to route requests to team admins was never built) and `closed` (a
second muted label, indistinguishable in practice from `invite_only`) were
dropped from the enum entirely; see `CONTROL-PLANE-PRODUCT-CONTRACT.md` §29.

**Ask for an invitation (#2453, 2026-08-27).** A public invite-only team is
discoverable but not joinable, and the muted label alone left the visitor with
no next step. The card restores the pre-TEAM-09 escape hatch: a `mailto:`
addressed to every team admin whose `UserSummary.email` resolved, prefilled
with the subject, the caller's identity, and two links: the team's agents page
for context (what `main` sent) plus a deep link to its members page, where the
recipients - the admins - actually add the sender by hand. The wording is the
pre-TEAM-09 one (`rework.teamCard.invitationMail.*`) plus that second line, and
now lives in the locale files instead of hardcoded French as it did then.

The button reuses the `join` label - it is the same intent, and a second,
longer label wrapped the card's footer onto two lines; the `mail` icon and the
draft that opens are what distinguish it from the instant `open` join.

Two guards decide whether the button replaces the label:

- **public only.** A private team keeps the label: the UI does not offer a
  non-member a private team's admin addresses. This is a product rule about
  what the card *proposes*, not a disclosure guarantee - `GET /teams` puts
  `admins` (email included) in the payload for every team it returns, and
  `MarketplaceTeams` records that private teams reach the client at all when
  authorization is disabled. Withholding them from the wire is a server-side
  question, still open. `TeamCard` checks `visibility` itself rather than
  trusting `MarketplaceTeams`' filter: it is a shared component, and the check
  is `=== "public"` so a payload with no `visibility` fails closed (#2433).
- **a reachable address.** `admins` falls back to a bare `UserSummary(id=...)`
  when the Keycloak lookup returns nothing, so an admin list can render with no
  email at all. With no recipient there is nothing to open, so the label stays
  rather than producing an empty `mailto:`.

Mechanics worth keeping: the draft opens with `window.open(..., "_blank",
"noopener,noreferrer")` rather than a `location.href` assignment, so a webmail
registered as the `mailto:` handler opens beside the app instead of replacing
it (a native client takes over the throwaway tab and the browser drops it);
`noopener` makes `window.open` return `null` by spec, so there is nothing to
test for a fallback - the click is the user gesture popup blockers key off.
Recipients are comma-separated (RFC 6068) and
percent-encoded, since the addresses come from a directory sync and nothing
guarantees they are URL-safe; `URLSearchParams`' `+` is rewritten to `%20` or
mail clients render it literally in the subject; the team link prepends the
router basename (`normalizeBasename`, shared with `buildDocumentViewerPath`)
because a mailed URL inherits nothing from the router; and the identity line
degrades to whichever of `name` / `preferred_username` Keycloak returned.

No server-side request flow is involved: this is a client-side mail draft, the
same as before TEAM-09. Nothing routes an invitation request through the API.

**Footer layout.** The card is a fixed 290px, so the admin avatars and the join
button compete for one line: a team with five admins pushed the button past the
card's right edge and squashed the avatars into ellipses on the way. Three
changes, none of them resizing an avatar: the button never shrinks (it must
keep its whole label), `AvatarGroup` gained a `max` prop (default 4, so its
other consumer is unchanged) and the card drops to `max={2}` whenever a button
shares the footer, and an avatar is now `flex-shrink: 0` - a fixed-size circle
should clip, never deform. `.teamCardAdmins` does that clipping as a last
resort for an unusually long translation; the row runs right-to-left, so the
overflow falls off the left and the "+N" badge stays visible.

Two `AvatarGroup` fixes came out of the same pass, and apply everywhere it is
used. The "+N" badge now goes through the same `Tooltip` wrapper as the other
avatars: `.userAvatarContainer > *` puts the 2px ring on the direct child, so
under the global `box-sizing: border-box` a bare badge paid for that ring out
of its own 2rem while a wrapped avatar grew by it - the badge rendered 4px
smaller than its neighbours. That wrapper also gives the badge a tooltip
listing the hidden names, one per line (a `content` tooltip, so it owns its own
padding).

**Footer layout.** The card is a fixed 290px, so the admin avatars and the join
button compete for one line: a team with five admins pushed the button past the
card's right edge. The button never shrinks (it must keep its whole label) and
the avatar row is the half that gives up width - `AvatarGroup` gained a `max`
prop (default 4, so its other consumer is unchanged) and the card drops to
`max={2}` whenever a button shares the footer, collapsing the rest into "+N".
`.teamCardAdmins` clips as a last resort for an unusually long translation; the
avatars run right-to-left, so the overflow falls off the left and the badge
stays visible.

---

### `MarketplaceTeams` — what the discover section may list (#2398)

**Location:** `src/rework/components/pages/marketplace/MarketplaceTeams/MarketplaceTeams.tsx`
**Status:** `Functional`

`GET /teams` is a general-purpose listing, not a marketplace feed: the page
decides on its own what is discoverable, and drops from the "discover"
(non-member) bucket every team that is a personal space (#2068) or whose
`visibility` is `private` (#2398). The server already withholds the ReBAC
`public` relation from a private team, but that filter is skipped entirely
when authorization is disabled — so the page never relies on it. A team the
caller *is* a member of stays listed under "your teams" whatever its
visibility: members need it to navigate.

---

### `TeamSettingsParameters` — visibility + joining-mode controls

**Location:** `src/rework/components/shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamSettingsParameters.tsx`
**Status:** `Functional`

Two stacked rows (`.team-settings-toggle-row`, label left / control right)
share one `form-section` (`.team-settings-toggles`, `flex-direction: column`,
`gap: var(--spacing-s)`): **visibility** (`public`/`private`) on top,
**joining mode** below it (a `ButtonGroup` only while the team is public —
see the #2398 note below). Both are `ButtonGroup`s (`variant="radio"`,
`size="small"`, plain group-level `color="secondary"` — no per-item color,
same pattern as the theme/language pickers in `UserSettingsPage.tsx`).
Selecting an option PATCHes immediately (no separate save step), mirroring
the retired `is_private` `Switch`'s auto-save behavior this control replaced.

Joining mode narrowed to 2 options (`open`, `invite_only`) 2026-07-26 —
`request_only` and `closed` were dropped from the `JoiningMode` enum
entirely (see `CONTROL-PLANE-PRODUCT-CONTRACT.md` §29). Originally shipped
as a 4-way group with a distinct selected-state color per option
(`open`→`success`, `closed`→`error`) via a `ButtonGroupItem` per-item
`color?: ColorTheme` override; both the 2 extra options and the per-item
color scheme were dropped in the same pass. `ButtonGroupItem` still
supports the `color` override prop, but no shipped consumer uses it — the
plain group-level color pattern is what every `ButtonGroup` consumer
follows now.

**Visibility control (TEAM-10, 2026-07-26).** New `ButtonGroup`
(`public`/`private`; default `public` at the time — new teams default to
`private` since 2026-08-26, #2433) gating marketplace discoverability
— see `CONTROL-PLANE-PRODUCT-CONTRACT.md` §30/§44 for the full ReBAC
mechanism. No client-side write of `joining_mode` ever accompanies a
visibility PATCH — the resulting `joining_mode`, if it changes, comes back
from the server on refetch.

**Joining mode while private — one disabled button, no toggle (#2398,
2026-08-20).** A `private` team can never be `open`, and the product has no
invitation flow at all (there is no invite endpoint — a team admin adds
members by hand from `TeamSettingsMembers`). So while
`visibility === "private"` the joining-mode row renders no `ButtonGroup`:
the control slot holds a single **disabled** `Button` (`secondary` /
`outlined` / `small`, `lock` icon) reading "Manual only", and the row's
support line switches to the `privateSupport` copy ("a private team is not
listed on the marketplace: its members are added manually by a team
admin"). One inert, locked control states the fact; the original 2026-07-26
treatment kept the whole group mounted with every item `disabled`, and a
greyed-out *two-state* toggle still reads as a live choice — while "Invite
only" named a mechanism that does not exist. Plain muted text was tried
first and read as too weak for the row (it also wrapped onto two lines),
hence a real button shape. `.team-settings-toggle-action` carries the
`flex-shrink: 0` + `white-space: nowrap` the row needs: the label column
takes the free width and `.btn` clips its own overflow. The group returns
unchanged the moment visibility goes back to `public`.

**`ButtonGroupItem` — `:disabled` visual state (2026-07-26).** The atom
previously had no disabled styling at all — a `disabled` item was
functionally inert (native attribute blocks the click) but visually
identical to an enabled one. Added `&:disabled` with `pointer-events: none`
(bulletproof no-hover/no-active/no-click, no need to guard the existing
`:hover`/`:active` rules individually) plus, scoped to
`.stateLayer:not([data-selected="true"])` only, a transparent background
and `on-surface-muted` label color. Scoping to the unselected sub-case
mattered for the original driving call site — the joining-mode group's
disabled-while-private state, which always had one selected item
(`invite_only`, forced) and one not (`open`): the selected item kept its
normal filled selected-color styling, only the unselected `open` option
read as muted/transparent. That call site is gone since #2398 (see above),
but the rule was a generic addition to the shared atom, never special-cased
to it — any disabled+unselected item elsewhere still gets the treatment for
free.

**`ButtonGroup` — pill `backgroundColor` override (2026-07-26).** Gained an
optional `backgroundColor` prop (default `var(--surface-container)`,
matching every existing consumer's look exactly), applied via a
`--button-group-background-color` CSS custom property rather than a
hardcoded class — same escape-hatch pattern as `DataTable`'s own
`backgroundColor` prop. Both rows in this panel override it to
`var(--surface-container-lowest)`, since they already sit inside a
`surface-container` `form-section` and the default pill color would
otherwise blend into it.

### `TeamSettingsParameters` — team banner upload

**Location:** `src/rework/components/shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamSettingsParameters.tsx`
**Status:** `Functional`

Banner upload is a `Button` (`variant="outlined"`, `size="small"`,
`icon={{ category: "outlined", type: "upload" }}`, label "Importer"/"Import")
that triggers a hidden native `<input type="file">` via `fileInputRef`,
replacing the earlier click-the-image `ImageFileInput` pattern. Below the
button, a `body-small` / `on-surface-muted` caption states the supported
formats and size limit (JPEG/PNG/WebP, 5 MB max — matches the
`ALLOWED_TYPES`/`MAX_BANNER_SIZE` client-side validation already in
`handleBannerUpload`). To the button's right, an `<img>` preview
(`.team-banner-preview`) renders the current/staged banner at the same
240×88 width/height ratio as `TeamContentNavbar`'s `.bannerContainer`, so
the preview shows the same crop the image gets once applied to the nav
banner.

---

### `TeamContentNavbar` / `TeamSettingsPage` — self-service team leave (AUTHZ-09)

**Location:** `src/rework/components/shared/layouts/Sidebar/TeamContentNavbar/TeamContentNavbar.tsx`,
`src/rework/components/pages/TeamSettingsPage/TeamSettingsPage.tsx`,
`src/rework/components/shared/organisms/TeamSettingsPanel/TeamSettingsMembers/LeaveTeamButton/LeaveTeamButton.tsx`
**Status:** `Functional`

The team-settings gear icon (previously `canAdministerAdmins`-gated, admin
only) is now visible to every team member (`canReadMembers`). What a member
sees inside scales with their role:

- a plain member: a read-only "Members" list (no invite field, no actions
  column; the role column stays visible with the same chips as the editable
  view, just non-interactive, so a plain member can still see who holds
  elevated roles) and nothing else in the sidebar;
- editors/analysts/admins: the same sections as before (Members with edit
  controls, Parameters gated on `can_update_info`, Activity/Evaluations per
  their existing gates) — Activity's gate moved from `canReadMembers` (now
  true for everyone) to a new `hasElevatedTeamRole` helper
  (`teamCapabilities.ts`), since it isn't part of the plain-member baseline.

**"Leave team" button (relocated 2026-07-24, #2108).** No longer in the
settings sidebar — now a `filled` / `error` `Button` (`LeaveTeamButton.tsx`)
rendered inline in the Members section header, `24px` to the right of the
"Membres" page title (`.team-settings-members-header-left`, `gap:
var(--spacing-l)`), so it only appears on the Members section, not on
Parameters/Activity/Evaluations. Disabled with an explanatory `title`
tooltip only for a team's sole remaining `team_admin` (computed client-side
from the members list; the backend's last-admin invariant is the actual
source of truth and still applies server-side regardless). Confirms via
`ConfirmationDialog`, then redirects to `/team/personal/agents`.

#### `ConfirmationDialog` — mandatory inverted emphasis for `criticalAction`

Every `criticalAction: true` dialog now defaults to the same button
formalism, without any call site needing to opt in: `Cancel` = filled +
primary (the safe, reversible choice stays visually dominant), `Confirm` =
text + error (the destructive choice is low-emphasis, M3 "Text" tier).
Non-critical dialogs keep the old defaults (`Cancel` = outlined/on-surface,
`Confirm` = filled/primary). `cancelVariant`/`cancelColor`/`confirmVariant`
props (threaded through `ConfirmationDialogProvider`'s
`showConfirmationDialog`) still exist for an explicit per-call override, but
every existing critical dialog (leave team, delete agent, delete session,
delete prompt) now gets the inverted emphasis for free — the three call
sites that used to pass the override triplet by hand had it removed since
it's now redundant with the default.

#### Open UX issues

- Not yet design-reviewed. First functional pass only.

---

### `DataTable` — opt-in pagination, `TeamSettingsMembers` full-height layout (#2108)

**Location:** `src/rework/components/shared/molecules/DataTable/DataTable.tsx`,
`src/rework/components/shared/organisms/TeamSettingsPanel/TeamSettingsMembers/TeamSettingsMembers.tsx`
**Status:** `Functional`

`DataTable` gained an optional `pageSize` prop. Omitted (the default), it
renders exactly as before — every consumer that doesn't pass it
(`AdminTeamsPage`, `MigrationPage`, `CapabilitiesPage`) is unaffected. When
set, the table slices `data` to one page and renders a persistent pagination
footer, height `3.75rem` — same height as a table row — with two flex
containers:

- **Left:** total item count (`{{count}} items/éléments`, `body-medium`,
  `on-surface-retreat`).
- **Right**, left to right: a rows-per-page `Select` (20/50/100, our own
  molecule, not MUI), then `IconButton` (`medium`, `icon` variant,
  `on-surface`) first-page / previous-page, the current page label
  ("Page X sur Y" / "Page X of Y", `body-medium`, `on-surface-retreat`,
  `tabular-nums`), then next-page / last-page. All four nav buttons disable
  at their respective bound (first/prev at page 1, next/last at the last
  page) — the footer itself never hides, even when every row fits on one
  page, so the count and page-size control stay reachable. New icons
  `first_page`/`last_page` added to the app's Material Symbols allow-list
  (`shared/utils/Type.ts`). New i18n keys: top-level
  `dataTable.pagination.{first,prev,next,last,totalItems}`. The page label
  (`dataTable.pagination.pageNumber`) is fixed-width (`7rem`, centered) so
  the neighbouring nav buttons don't shift as either the current page or the
  total page count gains a digit.

`TeamSettingsMembersTable` is the first consumer, at an initial `pageSize={20}`
(the rows-per-page `Select` lets the user switch to 50/100 from there).

The Members section (`TeamSettingsMembers.module.scss`) is now a full-height
flex column (`height: 100%` from the already-24px-padded `.teamSettingsPage`
shell): the header row is fixed height, and the table wrapper takes
`flex: 1; min-height: 0` so the table's bottom edge sits exactly `24px`
above the viewport bottom, scrolling internally past `pageSize` rows on very
short viewports rather than growing the page. The container's own
`overflow: hidden` was removed — it isn't needed for the shrink-to-fit
chain (`min-height: 0` on both the container and the table wrapper already
does that; `DataTable` clips its own rounded corners) and it was cropping
the "add member" `Autocomplete` input's focus ring at the top of the flex
column.

**`Autocomplete` compact-field alignment (fixed 2026-07-26).** Uses
`TextInput`'s `compact` variant, which now sets `display: none` on the
hint/error/counter container (`.information`) instead of just skipping its
flex/padding rules — previously the empty container still reserved a row's
worth of height, which (a) misaligned the input's visual center against the
title/`LeaveTeamButton` row and (b) pushed `Autocomplete`'s `menu-popover`
(`top: 100%` of the input's own wrapper) below the input with a large gap.
Both now resolve automatically since the wrapper's rendered height matches
the input exactly; the popover's only remaining offset is the deliberate
`margin-top: var(--spacing-3xs)` in `Autocomplete.module.scss`.

#### Open UX issues

- Not yet design-reviewed. First functional pass only.

---

### `DataTable` — body cells contain their content; primitive values truncate (#2284, 2026-08-07)

**Location:** `src/rework/components/shared/molecules/DataTable/DataTable.tsx`,
`src/rework/components/shared/molecules/DataTable/DataTable.module.scss`
**Status:** `Functional`

Reported on the Team members table: long values in the "Identifiant" column
(usernames are full email addresses) ran under the First name column, and
some wrapped onto two lines. Fixed in the molecule, not the call site, since
any table with free-length text had the same bug (`AdminTeamsPage` team
names, `MigrationPage` team names):

- `.datatable-cell` gained `overflow: hidden` — whatever a `cellRenderer`
  produces, it can no longer spill under the neighbouring column. Safe with
  in-cell popovers (`IconButtonMenu`, `Tooltip`): their content portals to
  `document.body`, so cell clipping can't touch it. Headers already
  truncated (`.header-content`); this is the body-cell half.
- Primitive `cellRenderer` values (string/number) are wrapped by DataTable
  in a `.cell-text` span: single-line `text-overflow: ellipsis`, full value
  readable via the span's native `title` on hover — same idiom as
  `CorpusAuditPage`/`CapabilitiesPage` name cells. Element values pass
  through untouched (the caller owns their layout).

`TeamSettingsMembersTable`'s three text columns (Identifiant, First name,
Last name) now return plain strings and get this behaviour for free.

#### Open UX issues

- The hover reveal is the native browser tooltip, not the design-system
  `Tooltip` atom (and it also shows for values that aren't cut). A styled
  only-when-truncated variant was prototyped and dropped as
  disproportionate; revisit if design review wants tooltip consistency in
  tables.

---

### `TeamSettingsMembers` — member search field (2026-07-26)

**Location:**
`src/rework/components/shared/organisms/TeamSettingsPanel/TeamSettingsMembers/TeamSettingsMembers.tsx`,
`src/rework/components/shared/organisms/TeamSettingsPanel/TeamSettingsMembers/TeamSettingsMembersTable/TeamSettingsMembersTable.tsx`
**Status:** `Functional`

Reuses the exact same input the header's `AddTeamMembersDialog`-launch used
to use before #2117 replaced it with a button: `TextInput` in `compact`
mode with a leading `search` icon, no `label` — not the `SearchField`
molecule (`PromptsPage`/`CapabilityTeamMatrixDrawer`'s search), which was
tried first and rejected as visually inconsistent with the rest of this
panel. `TextInput` already accepts native input attributes (`placeholder`,
`aria-label`, `style`, `ref`) via its prop spread, so no component change
was needed for the placeholder text, the accessible name on an icon-only
field, or the clear button below.

Placeholder: "Nom, Prénom, Identifiant" / "Last name, First name,
Identifiant" — matches the three searchable fields (and the `username`
column's "Identifiant" label) rather than a full sentence, unlike
`AddTeamMembersDialog`'s own search placeholder ("Entrer un nom, prénom ou
ID utilisateur").

Clear button: once `search` is non-empty, a `small`/`on-surface-retreat`
`IconButton` (`close`) appears absolutely-positioned inside the field
(`.team-settings-members-search-clear`, vertically centered, `right:
var(--spacing-2xs)`) — composed locally around `TextInput` rather than
built into it, so the shared atom's API/behavior for every other consumer
stays untouched. Clearing calls `setSearch("")` and refocuses the input via
a local `ref` (same pattern as `SearchField`'s own clear button), so focus
never leaves the field. `TextInput` gets an inline `style={{ paddingRight:
... }}` only while the button is showing, reserving room so typed text
never runs under it.

Sits in the header's right-hand group (`.team-settings-members-header-right`,
`gap: var(--spacing-m)` = 16px), immediately left of the conditional
"Ajouter des membres" `Button` — both share that flex row so the search
field is still shown flush right even for members without
`can_administer_members` (button hidden, search alone). Fixed
`width: 280px` on the field's wrapper, since `TextInput`'s root is
`width: 100%` and needs a container to stop it filling the header row.

Filtering is purely client-side: `useListTeamMembersQuery({ teamId })`
already fetches every member in one uncapped call (`DataTable`'s pagination,
per #2108 above, only slices that already-fetched array), so there's no
backend search endpoint to coordinate with. Below 2 characters the query is
ignored (every member shows); at 2+, the query is split on whitespace into
tokens and a member matches when **every** token is found in **at least
one** of `first_name`/`last_name`/`username` (case-insensitive substring) —
so "doe alice" and "alice doe" both match a member named Alice Doe, and a
lone token matches on first name, last name, or the "Identifiant" column
(`username`) alone.

The row's `IconButtonMenu` ("more" action) color also moved from
`on-surface` to `on-surface-retreat` in this pass — a deliberate de-emphasis
of that column, unrelated to search but shipped in the same change.

#### Open UX issues

- Not yet design-reviewed. First functional pass only.

---

### `AddTeamMembersDialog` — bulk add with per-user role selection (2026-07-26)

**Location:**
`src/rework/components/shared/organisms/TeamSettingsPanel/TeamSettingsMembers/AddTeamMembersDialog/AddTeamMembersDialog.tsx`,
`src/rework/components/shared/molecules/TeamRoleChips/TeamRoleChips.tsx`
**Status:** `Functional`, first pass from a supplied mockup — not yet
design-reviewed.

The Members header's inline Autocomplete text input is replaced by a
`filled`/`primary` `Button` ("Ajouter des membres", same header slot). It
opens `AddTeamMembersDialog` — a `Portal`-based modal following the
`ConfirmationDialog`/`DuplicateAgentDialog` shell (overlay + card, no
generic `Dialog` primitive exists yet):

- **Header:** title + subtitle (`body-medium`, `on-surface-retreat`).
- **Search:** the same `Autocomplete` the old inline field used, reused
  as-is (candidates come from the existing `candidate-members` endpoint,
  already scoped to non-members) — auto-focused on open, and its menu only
  opens once the query is 2+ characters (`minQueryLength={2}`, see below),
  matching the backend search's own minimum.
- **Pending-list container** — always rendered, even with zero pending
  candidates (`1px solid outline-retreat` border, `radius-s` (`8px`)
  corners, `spacing-s` (`12px`) padding so content isn't flush against the
  border): a fixed `pendingListHeader` label ("Membres à ajouter à
  l'équipe", `label-large`, `on-surface-retreat`) above either —
  - the rows `<ul>` (no column headers) once ≥1 candidate is pending, `2px`
    (`spacing-3xs`) gap between rows: name/username, a `TeamRoleChips` role
    selector (see below, `8px` gap between its own chips), and a
    `close`-icon `IconButton` to drop the row. Each row is
    `surface-container-highest` background, `radius-s` (`8px`) corners,
    `padding-left: spacing-m` (`16px`, `padding-right` stays `spacing-xs`/
    `8px`), height `3rem` (`48px`) — a visually distinct "chip" resting
    inside the outer bordered container, not flush rules between rows.
    List capped at `8.5 * var(--row-height)` — the half-row is a deliberate
    "more below" affordance — with a `4px`-wide `::-webkit-scrollbar`
    (thumb color inherited from the app's existing global `outline-retreat`
    scrollbar rule in `styles/index.css`, already thin by default; this
    only narrows it further for the denser list); or
  - a centered (`body-medium`, `on-surface-muted`) "Aucun utilisateur
    sélectionné pour l'instant" placeholder, `height: var(--row-height)`
    (`48px`) — same height as a single pending row, so the container's
    overall height doesn't jump between the empty and one-candidate states.

  **No `overflow: hidden` at the dialog level** — everything is inset by
  the dialog's own padding, and clipping would also cut off the
  `Autocomplete` menu popover in the search row above the list (same class
  of bug just fixed on the old inline field, see above).
- **Actions:** `Annuler` (`outlined`/`on-surface`) / `Ajouter`
  (`filled`/`primary`, disabled while the list is empty or a submit is in
  flight). Clicking `Ajouter` always closes the dialog once the batch
  finishes, whether every add succeeded or not — per-user failures still
  surface as an error toast (`notifyApiError`), they just don't block the
  rest of the batch or keep the dialog open for a retry.

**No new backend endpoint** — confirming always calls `addTeamMember` on
the `team_member` baseline first, then `grantTeamMemberRole` for every
selected elevated role, one call per role (same pattern the members table
already uses for role changes on existing members, § AUTHZ-06 above).
**Never add directly onto an elevated relation** — a member added straight
onto e.g. `team_editor` with no separate `team_member` tuple has no floor
to fall back to: revoking their only elevated role later leaves them with
zero relations at all, and the backend correctly 409s ("would silently
remove them from the team, use remove_team_member instead") rather than
allow that. Fixed 2026-07-26 — the first version picked the
highest-priority selected role as the `addTeamMember` relation directly
(skipping the grant call for that one role, saving an API round trip), which
silently produced exactly this trap for every member added through the
dialog with at least one elevated role: they'd display correctly, but their
only/highest role could never be revoked back down to plain membership.

**`useMutationAction`: `T | null` can't tell "failed" from "succeeded with
a falsy result" (fixed 2026-07-26).** After the fix above shipped, every
grant call in the batch was still silently skipped — `handleConfirm`
checked `addResult === null` to detect a failed `addTeamMember` call before
proceeding to the grant loop. `add_team_member`/`grant_team_member_role`
both respond `204 No Content`; `fetchBaseQuery` resolves an empty body to
`null` **on success**. Every add in this dialog therefore always looked
like a failure to that check, and the grant loop below it never ran — with
no thrown error, no console error, and no toast, since nothing had actually
failed. This reproduced 100% of the time against the real backend but
**never** against any mocked backend used to investigate the two prior
reports in this session, because every mock's fetch stub serialized a
JSON body (`"{}"`, 2 characters) for every response regardless of status
code — never a truly empty one — so `added` was never `null` in any of
that testing. `useMutationAction.ts` (`core/hooks/useMutationAction.ts`)
now returns a discriminated `{ ok: true; data: T } | { ok: false }`
instead of `T | null`; `handleConfirm` branches on `.ok`. No other call
site branched on the return value (every other consumer just awaits the
call and relies on the `onError` toast), so this is a non-breaking
contract change. Caught by reproducing with a mock that returns a
genuinely empty `204` body (`new Response(null, { status: 204 })`)
instead of a serialized empty object.

**`TeamRoleChips`** — the members table's inline role-chip toggle group
(admin/editor/analyst, multi-select, `data-active` fills `--primary`
background with `on-primary` text) is extracted from
`TeamSettingsMembersTable` into this shared molecule so the dialog's
pending rows and the table use the identical implementation/CSS. Both gate
each chip via the new `canAdministerTeamRole(capabilities, role)` helper
(`core/hooks/teamCapabilities.ts`), replacing the table's former private
closure of the same logic. Sizing: height `2rem` (`32px`), `label-medium`
text, default (inactive) border `1px solid outline` — was `0.5px
outline-variant`, a size/color pair that didn't match any other chip-style
control in the app. Chip padding-left/right `spacing-s` (`12px`, was
`spacing-xs`/`8px`). That geometry now lives in one `%pill` placeholder
`@extend`ed by both the toggles and the baseline badge below, so the two
cannot drift apart in the same row.

**`TeamRoleChips`: a static `Member` badge and a description tooltip on
every badge** (2026-08-17, #2383). Two complaints from team admins, one
fix. (1) A member holding no elevated role rendered as three *inactive*
pills — visually indistinguishable from a row that hadn't loaded. A
non-interactive `Member` badge now closes the row, after the three toggles,
always visible. It shares the toggles' pill geometry (a `%pill` placeholder
both `@extend`, so height/padding cannot desync mid-row) but carries its own
fill: tonal `secondary-container` / `on-secondary-container`, with a
transparent 1px border to keep the geometry identical. Deliberately *not*
the toggles' `--primary` fill — in this row `--primary` reads as "someone
granted this and someone can revoke it", whereas `team_member` is neither
granted nor revocable, just always true. The same tonal pairing already
marks non-interactive identity in `UserAvatar`, `MessageBubble`, and the
agent-card icon. What the badge lacks is affordance, not presence: `cursor:
default`, `role="note"`, no hover state, no `aria-pressed`, no click
handler. It is deliberately not a fourth toggle —
`team_member` is the implicit baseline (automatic for anyone holding an
elevated role, granted directly to anyone holding none) and the API refuses
to revoke a member's last relation, so a toggle would promise an action
that cannot happen. (2) The role names carried no meaning on the page: all
four badges now open a rich `Tooltip` (title + one-line description), copy
condensed from the help centre's `features/roles.md` tables so the two
surfaces agree. The Analyst panel alone carries a `--warning` footer row —
it grants evaluation-campaign execution *and* the limited conversation
slices those datasets are built from, which a flat pill row hinted at
nowhere.

A chip the actor may not administer switched from `disabled` to
`aria-disabled` + a guard in the click handler. The visual state is
unchanged (`[aria-disabled="true"]` replaces `:disabled` in the SCSS), but
a `disabled` button leaves the tab order and fires no pointer events, so it
would have been the one badge unable to explain itself — to exactly the
reader who cannot act on the role and most needs to know what it is.

**Members table: role chips are a live, single-click toggle in both
directions.** `TeamRoleChips` renders identically here and in the
add-members dialog, but only the table's instance is *live* — a click
there immediately grants/revokes via the API, while the dialog's is a
staged selection with no effect until "Ajouter". A confirmation step was
added on the revoke path (2026-07-26) while investigating a report of "a
member added with 2-3 roles ends up holding only the highest-priority
one" — it turned out not to be the cause (see the `addTeamMember`-on-
baseline fix above for the actual root cause) and was removed again at the
developer's explicit request the same day: revoking a role is back to a
single click, symmetric with granting. Also fixed in the same investigation
(kept): `DataTable` accepted an optional `rowKey` (default: array index,
unchanged for other consumers); `TeamSettingsMembersTable` now passes
`(member) => member.user.id` — with the previous index-based key, any
row-scoped state or in-flight handler could misattribute to the wrong
member as soon as the list re-sorted (which `sortedMembers` does on every
role change).

**`Autocomplete` open-state rework (`isOpen` now derived, plus
`minQueryLength`).** Previously `isOpen` was an imperatively toggled
boolean (set on focus/blur/select), which needed a one-off patch when a
second query typed while still focused (post-selection) didn't reopen the
menu. Replaced with a derived value: `isOpen = isFocused && !dismissed &&
queryValue.trim().length >= minQueryLength`, where `dismissed` is a
one-shot flag set by Escape or a selection and cleared on the next
focus/keystroke. New optional prop `minQueryLength` (default `0`, opens
immediately on focus — e.g. `AdminTeamsPage`'s browsable full-user-list
field) lets a consumer whose menu is backed by a server search that itself
only queries past a minimum length (this dialog, `minQueryLength={2}`)
avoid flashing an empty "no options" state below that threshold. Affects
every `Autocomplete` consumer, not just this dialog.

**`Autocomplete` keyboard navigation (2026-07-26).** The first option is
now virtually focused (`aria-activedescendant` pattern, DOM focus stays on
the input) as soon as the menu opens with results; `ArrowDown`/`ArrowUp`
move it, wrapping at each end; `Enter` selects whichever option is
currently focused (closing the menu and clearing the field, same as a
click). The focused index resets to `0` on every fresh keystroke or
re-focus rather than reactively whenever the `options` prop changes —
`options` is a new array reference (`.filter()`/`.map()` result) on nearly
every parent render, not only when the candidate list itself changes, so
tying the reset to it would keep stomping on the user's own up/down
navigation mid-browse. Implementation mirrors `Select`'s existing
`activeIndex`/`moveActive` pattern verbatim (same wrap-around, same
disabled-skip behavior). Surfaced (and fixed in the same pass) a latent bug
in the shared `Menu`: its per-option DOM id was built from `option.value`,
which for `Select`'s own primitive-typed options happened to stringify
uniquely, but for `Autocomplete`'s object-typed candidates (`UserSummary`
records) stringifies to the same `"[object Object]"` for every option —
breaking both `activeId` matching and the `#${activeId}` scroll-into-view
selector (unescaped `[`/`]` aren't valid there). Menu's item id (and
`Select`'s matching `activeOptionId`) now use `option.key` instead — already
required, already unique by contract (it's the React list key), and a
plain string regardless of `T`.

**`IconButton` default color.** `color` is now optional, defaulting to
`on-surface-retreat` — the baseline color intended for icon buttons that
don't need a stronger color to draw attention (e.g. this dialog's row
`close` button). Every existing call site already passed `color` explicitly
so this is additive only; new call sites can omit it instead of repeating
the same value.

**`Button`/`IconButton` outlined-variant border fix.** Both previously set
`--btn-border` to the passed `color`'s own "main" token (e.g. `on-surface`'s
`main` is `on-surface`, which in dark theme is a near-white tone) —
per M3, the outlined variant's border is always the neutral `outline`
token regardless of `color`; only the label/icon take the scheme's color.
This was invisible in light theme (where `on-surface` happens to read dark
too) but washed the border out to near-invisible in dark theme, which is
what surfaced it here (this dialog's `Annuler` button, `color="on-surface"`).
Fixed at the shared-component level (`--btn-border: var(--outline)` in both
`Button.module.scss` and `IconButton.module.scss`), so every existing
`variant="outlined"` call site is corrected without touching call sites.

#### Open UX issues

- Not yet design-reviewed. First functional pass only.

---

### `TeamContentNavbar` banner / `TeamSelectionItem` — team role badges (#2100)

**Location:** `src/rework/components/shared/layouts/Sidebar/TeamContentNavbar/TeamContentNavbar.tsx`,
`src/rework/components/shared/layouts/Sidebar/TeamSelectionNavbar/TeamSelectionItem/TeamSelectionItem.tsx`
**Status:** `Functional`

Helps a user recognize their role in each team they belong to.

- **Left team rail (`TeamSelectionItem`, `teamAvatarContainer`):** a 14×14
  Shield icon badge (`color: secondary`, 2px `surface-container-lowest`
  outline forming a clean cutout against the avatar underneath — same
  technique as the existing `activityDot`) appears bottom-right of a team's
  avatar (`right: 8px; bottom: 2px`) when the current user is admin of that
  team. Derived client-side from `Team.admins` (`admin.id === currentUserId`)
  — no `my_relations` needed here, just a boolean.
- **Team banner (`TeamContentNavbar`):** `.bannerContainer` is now a column
  (`justify-content: space-between`) instead of a single bottom-aligned row —
  the team name + settings gear move to the top, and a new bottom-left label
  lists every role the user holds, joined by " · " (e.g.
  "Administrateur · Analyste"), reusing the existing `rework.teamRoles.*`
  labels (already shown as chips in the Members table). Falls back to
  "Membre" when no elevated role is held. Not shown for the personal space,
  or for a non-member merely browsing a public/marketplace team pre-join
  (`selectedTeam.is_member`). When `team_admin` is held (always the first
  token — roles are priority-sorted, admin first), the same Shield glyph as
  the `TeamSelectionItem` badge (`color: secondary`, 12px) prefixes the
  label, without that badge's circular background/outline — inline, `gap:
  var(--spacing-3xs)`. Personal-space admin has no equivalent yet (the role
  label itself isn't shown there) — left for a follow-up task.
- Backend: new `TeamWithPermissions.my_relations` field — see
  `CONTROL-PLANE-PRODUCT-CONTRACT.md` §26 for why `permissions` alone
  couldn't reliably answer "is this user actually team_analyst".

#### Open UX issues

- Not yet design-reviewed. First functional pass only.

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

Complete create / edit modal for managed agent instances, organized as a clean sub-component tree:

- `AgentFormModal.tsx` — modal shell + `FormState` ownership; no field rendering
- `AgentFormBody.tsx` — controlled form body; 4-tab layout, create or edit
- `TemplateBrowser/` — responsive card grid for template selection
- `TemplateCard/` — single selectable card with category label, name, clamped description
- `TuningFieldRenderer.tsx` — handles all field types: string, number/integer, boolean (`SwitchRow`), enum (design-system `Select` molecule), secret (password+reveal), url, array (`TagInput` molecule), prompt/multiline (`TextArea`)

Step 1: template browser. Step 2: a full-width `ButtonGroup` tab strip (`variant="radio"`, `size="medium"` — same pattern as the theme/language pickers in `UserSettingsPage.tsx`) with 4 top-level tabs (#2105, 2026-07-24):

- **Général** — Nom, Rôle, Description, plus every tuning field whose `ui.group` is not `"Prompts"` (the pre-#2105 catch-all "Settings" tab content — `Settings`, `Credentials`, `Document reading`, `Mindmap`, `Grounding`, `Comparison`, `Fallback`, ... — verified against real `fred-agents` templates). No template-side (`ui.group`) changes; purely a frontend regrouping.
- **Prompts** — every `ui.group == "Prompts"` field, unchanged content.
- **Outils** — capability cards, unchanged content. Hidden when the template has none.
- **Engagement** — required "Cas d'usage" field (large `TextArea`, label + placeholder, no field-level hint text), persisted as `ManagedAgentInstanceSummary.usage_statement` (screens agent purpose for platform/org risk). A compliance-framing paragraph sits above the textarea ("Afin de garantir la conformité de votre agent aux normes et règlementations en vigueur...", i18n'd) explaining why the field is mandatory.

Edit mode: same 4 tabs → metadata footer (created_by · relative date) → delete button.

Header reorg (#2102, 2026-07-24): dropped the agent icon/avatar and the back button; merged the team name and selected template name into one subtitle line (`"Équipe : <team> · Template : <template>"`, i18n'd — template segment omitted until a template is picked, or in edit mode if the original template is missing); dropped the in-body context bar (template name + category pill). Page backdrop `--surface-container`, form card `--surface-main`, no drop shadow — scoped to this modal only via `FullPageModal`'s new `background` prop (other `FullPageModal` consumers unchanged).

#### Open UX issues

- **Tuning field groups** — flat scroll within the Général tab; no accordion. Decide if needed for agents with many fields.
- **Template browser on mobile** — grid collapses to single column below ~480px; confirm whether list layout is preferable.
- **Single-template auto-select** — single available template is auto-selected; browser is still shown. Decide if it should collapse directly to step 2 immediately.

#### Resolved

- **Template browser** — replaced raw `<select>` with responsive card grid; selected state uses `--primary` border.
- **All field types** — secret, url, prompt, number/integer, enum, boolean (`SwitchRow`), multiline all implemented.
- **Field grouping** — `ui.group` groups fields under labeled sections; ungrouped fields land in Général.
- **MCP tools section** — read-only list of tools advertised by the selected template (display_name or id + require_tools).
- **Header reorg** (#2102) — avatar, back button, and context bar (template name + category pill) removed; team + template now shown as one subtitle line under the title.
- **Template browser container** (#2103) — pod filter + card grid sit inside a titled `--surface-container-low` container ("Sélectionner un template d'agent" + explanatory subtitle, i18n'd). Card border 1px `--outline-muted` (`--outline-retreat` on hover, no transition), background fixed `--surface-container` in every state (no hover/selected shift), category/pod labels moved to a card footer. Card name `--font-body-large`/`--primary`, description `--font-body-medium`/`--on-surface`, category/pod labels `--font-label-small`/`--on-surface-muted`.
- **4-tab restructure + Engagement field** (#2105) — see above.
- **Metadata footer** — created_by + relative date shown in edit mode when `created_by` is set.
- **Inline validation** — `submitAttempted` gates required-field errors, including displayName (Général tab), missing required tuning fields (routed to their own tab via `sectionOfField`), a blocking capability config error (Outils tab — e.g. ppt_filler's missing mandatory template, #1903), and usage_statement (Engagement tab); no toast for validation. Every tab with an unmet requirement gets the `ButtonGroupItem` `hasError` dot (a plain `--error`-coloured span, not a Material icon despite the "error_dot" naming convention used to describe it) and `handleSubmit`'s "jump to first error tab" logic covers all four tabs, Outils included. The validation banner ("Complétez les champs marqués d'un \*...") renders directly above the tab strip in `AgentFormBody.tsx`, before the user picks which tab to fix first.
- **State isolation** — `FormState` resets fully on modal close; template change resets tuning values.

---

### `TeamUsagePage`

**Location:** `src/rework/components/pages/TeamUsagePage/TeamUsagePage.tsx`
**Status:** `Functional`

Personal token-usage dashboard (OBSERV-02 / `BACKLOG.md` §7b), extended in place for v3
(`CONTROL-PLANE-PRODUCT-CONTRACT.md` §36, 2026-07-26): the personal section (unchanged, wrapped in
its own `Disclosure`) now sits below a capability-gated team section prepended above it, all
in-page gating (`FRONTEND-AUTHZ-PATTERN.md`, no route guard) via `useTeamCapabilities()`/
`hasElevatedTeamRole()`. Shared section (team_admin/editor/analyst): members/agents/documents
tiles, team-scoped token usage + green/cost (`TokenUsageImpact`, shared with `AnalyticsPage`),
storage quota, conversations over time, and a most-active-agents breakdown. Entry point is a new
gear icon on the personal-space banner (`TeamContentNavbar.tsx`) — the same slot team settings
uses, gated on `isPersonalTeam` instead of `canOpenTeamSettings` since the two are mutually
exclusive.

The page's `<h1>` is role-aware (2026-07-30 fix): "My token usage" for a plain member or anyone
on a personal team (only the personal section ever renders for them), "Team usage" for an
elevated viewer (admin/editor/analyst) — the original always-"My token usage" title read as
mislabeled for an admin looking at a page that's majority team-scoped content.

**Activités removed from this page (2026-07-30).** team_editor's ingestion-filtered and
team_admin's unfiltered `TaskActivity` sections (plus team_admin's `team_activity_summary` trend
line) were embedded here per v3 §2.8 — removed as a live-review finding: they duplicated
`/team/:teamId/settings/activity` (`TeamSettingsPage`'s Activity tab), one click away in the same
nav rail, which additionally has ack support this embed never did. With this page as its only
consumer gone, the `team_activity_summary` preset endpoint itself was retired outright
(2026-08-08) — it is no longer part of the contract. See `CONTROL-PLANE-PRODUCT-CONTRACT.md` §36
and the `TaskActivity` entry below.

The Team Settings nav (`TeamContentNavbar.tsx`) was also widened the same day: being on
`/team/:teamId/usage` used to collapse the sidebar to a bare "← Back" with no indication of where
you were; it now renders the same `settingsItems` tab list Team Settings uses (Members/Settings/
Activity/Evaluations/Usage/Routing), with Usage highlighted via `NavLink`'s own active-route
match — consistent with every other elevated-role tab instead of a dead end. Personal-space Usage
(no sibling tabs to switch to) keeps the bare Back.

#### Open UX issues

- Not yet design-reviewed. First functional pass only — layout and empty/loading states mirror
  `AnalyticsPage` but haven't been checked against a live stack with real token data.

---

### `PageHeader`

**Location:** `src/rework/components/shared/molecules/PageHeader/PageHeader.tsx`
**Status:** `Functional`

The single canonical page-title row — `<h1>` + optional subtitle + optional right-aligned
`actions` + optional `breadcrumb` (full-width row above the title) + optional `tabs` (full-width
row below the title/actions row). This is the only place a page-level title should ever be
rendered — no page should hand-roll its own `<h1>`/`<h2>` page title. Vertically centers the
title against `actions` when there's no subtitle; aligns to the top when there is one, so
`actions` sits at the title's baseline instead of drifting toward the two-line block's middle.

Extracted 2026-07-30 (commit `e01d0b47`) because `TeamUsagePage`, `TaskActivity`, and the team
Evaluations view had each hand-rolled a slightly different heading level/subtitle placement.
Extended 2026-07-31 with the `breadcrumb`/`tabs` slots and retrofitted onto every remaining
admin-scope and team-admin-scope page in the same pass, so platform-admin and team-admin pages
now share one consistent header pattern instead of diverging per page:

| Page | Slots used |
| --- | --- |
| `TeamUsagePage` | title, actions (`TimeRangeSelector` + refresh) |
| `TaskActivity` (platform Activity + team Activity tab) | title, subtitle |
| `Evaluations` (team Evaluations tab) | title, subtitle, actions |
| `AnalyticsPage` | title, actions (`TimeRangeSelector` + refresh) |
| `CorpusAuditPage` | title, subtitle, actions (refresh + Fix) |
| `SelfTestPage` | title only |
| `CapabilitiesPage` | title, subtitle, tabs (kind-filter `ButtonGroup`) |
| `MigrationPage` (Platform data) | title, breadcrumb (Kea cutover link) |
| `AdminTeamsPage` | title only (new — page previously had no page-level header) |
| `TeamSettingsMembers` | title, actions (search + `LeaveTeamButton` + Add members) |
| `TeamSettingsParameters` | title only (new) |
| `TeamSettingsRouting` | title only (new) |
| `KeaMigrationPage` (temporary, unlisted) | title only — hardcoded French string kept as-is; this page has no i18n at all and is slated for deletion with the Kea cutover, so it was wrapped for visual consistency without doing a full i18n pass |

Known deliberate non-adoption: `CapabilitiesPage`'s Tools/Agents/Models control is `ButtonGroup
variant="radio"` (a mutually-exclusive filter), not `variant="tabs"` (a content-switcher) —
visually similar but semantically different ARIA roles; kept as `radio` since it is in fact a
filter, not a tab strip.

#### Open UX issues

- No lint rule enforces `PageHeader` usage — a new or edited page can still hand-roll a title.
  Consider an eslint rule or code-review checklist item if regressions show up again.

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

Push layout supports opt-in drag-to-resize (`resizable` prop, 2026-07-22): a col-resize
grip on the left edge, bounds 320–900px capped at 45vw, width persisted per
`persistKey` — the legacy chat's `ResizablePaneShell` UX ported to the rework.
`CapabilitySidePanelHost` enables it with one shared key, so the
writable-document editor and the PPT preview panels share a persisted width.
Hidden below the 720px breakpoint (push drawers go fixed full-width there).

Opt-in **floating-card** variant (`floating` prop, push layout, 2026-08-06): the panel detaches
into a card inset from every edge — single `outline-muted` 1px border, `--radius-m` (16px)
corners, subtle `--shadow-s` — dropping the flush edge border and the header divider. Width stays
fixed during the open animation so content doesn't reflow. First consumer: the document-scope
panel (see "Document-scope side panel"). Default push panels stay flush: full page height, square
corners, a 1px `outline-muted` left divider, no top/bottom inset (2026-09-01 — previously a
`--radius-m` rounded card with a small top/bottom margin and a transparent left edge).

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

Generic `<T extends string>` pill-chip trigger + `MenuPopover`/`MenuPopoverItem` options popover anchored above the chip (`position: absolute; bottom: calc(100% + spacing-xs)`, same "opens above" grammar as `ComposerActionsMenu`). Chip: 32px height, fully rounded (`--radius-full`), `--surface-container-low` background, `--font-label-medium` in `--on-surface-retreat`, 18×18px icon; hover lightens via `--state-on-surface-hover`; open state (`data-open`) shows `--primary` text/icon over a `--state-primary-selected` background layer (a `primary`-tinted 16%-opacity overlay — the same token vocabulary as every other state layer in the app, not a one-off value). Self-contained `open` state (unlike `EnumSelectRow`'s externally-coordinated `open`/`onToggle`): each chip closes itself on outside mousedown or Escape, so multiple chips can sit side by side without a shared "one open at a time" coordinator — clicking a sibling chip already lands outside the first one's container. Full ARIA: `role="listbox"`/`role="option"` on the popover, `aria-haspopup`/`aria-expanded`/`aria-label` (`"{title}: {current value}"`) on the trigger. `ArrowUp`/`ArrowDown`/`Home`/`End` roving-tabindex navigation across options, mirroring `EnumSelectRow`'s pattern.

The trigger is wrapped in the shared `Tooltip` atom (`text={title}`) — the chip itself only shows
the current *value* ("Hybride"), the setting's *name* ("Recherche") shows on hover/focus via the
tooltip. `Tooltip` has no built-in show delay (toggles on `onMouseEnter`/focus immediately), so
this is an instant tooltip with no extra wiring needed. The wrapper stays mounted unconditionally
(not gated on `open`) — swapping it in/out based on `open` would remount the trigger `<button>`
and drop the focus `triggerRef.current?.focus()` restores after Escape/selection. Because the
tooltip can technically still be visible for a moment right after a click (pointer hasn't left the
chip yet), `.menu`'s `z-index` (1600) sits above `Tooltip`'s (1500, `Tooltip.module.scss`) so the
options popover always wins the stack when both are present.

First consumer: the composer's option chips (`ComposerOptionChips`, `features/capabilities/`) — see "Composer option chips" above for which chat-turn settings are currently chipped vs. shown as a tune-menu row instead (`ComposerControlSlot`); that split is iterated on regularly.

#### Open UX issues

- **Multi-select variant** — not implemented; single-value only. If a future control needs multi-select, a new variant is needed.

#### Resolved

- **Implemented (2026-08-05)** — this entry described `ContextualPicker` as already built since the CAPAB-01 chat-turn-control extraction, but the path never existed on disk; the composer instead reused `SettingChip`/`EnumSelectRow`/`MenuPopover` directly. This is the first real implementation, built for the composer option chips (search mode / scope).
- **Instant tooltip for the setting name (2026-08-06)** — added so the chip can stay compact
  (value only) without losing discoverability of which setting it controls.

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
- **Routine options moved to composer topSlot** (2026-05-24) — `AgentOptionsPanel` full-height right overlay removed. Libraries, search policy, and RAG scope moved into the composer instead of a full-height drawer. This entry originally named the destination `ComposerSettingsControls`, which was never built under that name — libraries went to a document-scope row in the "tune" popover (`ComposerControlSlot`), and search policy/RAG scope landed as `topSlot` rows there too until 2026-08-05, when they moved again into standalone `ContextualPicker` chips (`ComposerOptionChips`) — see the "Composer option chips" entry above.
- **Settings cluster no longer compresses textarea** (2026-05-24) — the settings controls moved from `leftSlot` to `topSlot` (dedicated row above/alongside the textarea). Textarea now has full composer width.
- **`compactLayout` removed (2026-08-06)** — `RichInputField` had a `compactLayout` prop that rendered a single-line inline row (textarea beside `leftSlot`) instead of the full multi-line layout, used only by `ManagedChatPage` for the empty "new conversation" state. Removed at the developer's request so the composer has the exact same structure (multi-line textarea + full `bottomRow`) in both the empty and mid-conversation states — `ManagedChatPage` now reuses the same `composer` element unconditionally. The now-unused `.inlineRow` CSS class was deleted with it.
- **Documents chip stays interactive on empty scope** (2026-06-12) — when `documents_selection` is enabled, the Documents chip must always open. Empty scope messaging is explicit: "Select a library first." when the library picker is visible but empty, and a configuration warning when documents are enabled without any library picker or bound library.
- **IME composition guard** (2026-05-24) — `handleKeyDown` now checks `!e.nativeEvent.isComposing` before calling `onSend`. CJK composition Enter no longer triggers send.

---

## CHAT-05 organisms (Waves 6–7)

---

### `UserTurn`

**Location:** `src/rework/components/shared/organisms/UserTurn/UserTurn.tsx`
**Status:** `Functional`

`UserMessage` + `ActionBar` (copy, optional edit). `.turn` has `position: relative`; hover shows actions. Edit action passes `onEdit` prop through to the action bar.

Copy is the same affordance as `AssistantTurn`'s (#2336): `content_copy` flips to `check` for
2s, no toast, no colour change. A second click inside that window restarts it rather than being
cut short by the first click's timer, and the pending revert is dropped on unmount. The payload
is `writeText` of the raw message: user messages are plain text, so none of the assistant side's
email-safe HTML serialisation applies.

A failed clipboard write is deliberately silent — the icon not flipping *is* the feedback, and
the API only fails in degraded contexts a toast would not fix (a denied permission rejects; a
non-secure origin has no `navigator.clipboard` at all, so the property access throws
synchronously and never reaches a `.catch`). Both turns get this from
`clipboardUtils.writeRichClipboard`, which wraps every path in `try` — `UserTurn` calls it with
no HTML, which is the same call `AssistantTurn` makes when it has no rendered node to serialise,
and writes `text/plain` only.

The `copied` flag and its 2s revert live in `core/hooks/useCopyConfirmation.ts`, shared by both
turns. It knows nothing about the clipboard on purpose: its predecessor bundled the write with
the flag, which hardcoded `writeText` and made it unusable by the assistant side — see Resolved
below.

Unlike `AssistantTurn`, the bar is **not** `alwaysVisible`. The assistant's is a footer toolbar
under the reply, where hover-only made it easy to miss (#2336); these sit beside a right-aligned
bubble and include Edit, so pinning them visible on every user message in a thread is a louder
change — deliberately left as its own call (see Hover zone below).

#### Open UX issues

- **Edit action** — `onEdit` prop exists but is not wired in `ConversationThread` yet. When wired, confirm that editing a message and re-sending correctly creates a new branch in the message tree.
- **Hover zone** — the hover area is the full `.turn` div. On mobile, confirm touch events correctly show/hide the action bar. Decide at the same time whether this bar should follow `AssistantTurn` and become `alwaysVisible`.

#### Resolved

- **Converged onto the shared copy affordance (2026-08-13, #2359)** — the copy button shipped
  here (#2339) and on `AssistantTurn` (#2336) in the same week, as two separate implementations:
  a hand-rolled `IconButton`/`Tooltip` row driven by a bespoke `useCopyToClipboard` hook, with a
  `success`-coloured check, a `copy-pop` scale keyframe and a 1.5s revert — against the
  assistant's `ActionBar`, plain check, 2s revert. Same interaction, two visual languages,
  depending on who wrote the message. This section already described `ActionBar`, so the code
  was also diverging from its own doc. `UserTurn` now renders `ActionBar`, and the keyframe is
  deleted.

  `useCopyToClipboard` is deleted too, replaced by `useCopyConfirmation`. The distinction is
  the point: the old hook bundled the clipboard *write* with the confirmation flag, which
  forced it to hardcode `writeText` — unusable by the assistant side, which writes email-safe
  HTML. Unshareable by construction, so it was reimplemented per turn and the copies drifted.
  The new hook holds only the flag and its timer, so both turns really do share it, and the
  write goes through `writeRichClipboard` on both sides.

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

Page composition (`.page` is a **flex row**, 2026-09-01): `[ .pageBody (flex:1) ][ launcher rail ]`.
`.pageBody` (flex row) holds the `.leftStack` on the left and the push drawers (capability /
attachments / document-scope) on the right. `.leftStack` is a flex column — the `topBar` (holding
`SessionTitleEditor`) above, the `.contentRow` → main column (`chatArea` scroll container + sticky
composer) below. An opening push drawer reflows the **whole left stack, header included**, so the
drawer spans the full page height for better viewer visualization (changed 2026-09-01 — previously
the drawers lived inside `.contentRow` and reflowed only the content, the panel sliding **under**
the full-width header; before that again the header lived inside the main column and shrank on
open). The `topBar` is an inset rounded card — `--radius-s` corners, 12px top/left/right margin,
flush bottom (2026-09-01). The launcher rail is a **page-root in-flow column** at the far right
(see "Capability side-panel launcher rail"), not part of `.pageBody`. The
`data-picker-top-boundary` attribute stays on the header so the composer's anchored pickers still
stop just below it. The composer is
built once (a single `composer` element) and placed either centered in the empty "new
conversation" state or in the sticky `inputOverlay` mid-conversation — same structure both times
(2026-08-06, see `RichInputField`'s "Resolved" entry). `topSlot` holds `ComposerOptionChips` —
currently just RAG scope, see "Composer option chips" (`COMPOSER_CHIP_WIDGETS` changes as
placement is iterated on); `leftSlot` holds the add/tune `ComposerActionsMenu` buttons (search
policy, document scope, reasoning, library selection, when the agent exposes them). No
`AgentOptionsPanel`, no `ConversationHeader`.

#### Open UX issues

_(none — all prior issues resolved below)_

#### Resolved

- **Options drawer retired** (2026-05-24) — `AgentOptionsPanel` full-height right overlay removed. Search policy, RAG scope, and library selection moved into the composer instead (see `RichInputField`'s "Resolved" entry for exactly where each landed and when).
- **Composer settings placement** (2026-05-24) — settings controls moved from `leftSlot` to `topSlot` (dedicated row above/alongside textarea). Textarea has full composer width.
- **Persistent setting summary** (2026-05-24) — active search policy and RAG scope are always visible as chips in the `topSlot` settings row, even while reading a reply.
- **Drawer role narrowing** (2026-05-24) — right-side drawers reserved for deep inspection only (source detail, debug, admin diagnostics). Routine controls do not use drawers.
- **Conversation files drawer** (2026-06-11) — attachment chips remain the transient per-turn affordance above the textarea, while persisted conversation files now live in a dedicated right drawer opened from a badge button next to the paperclip. This keeps routine composer controls lightweight while still exposing reload-safe file preview/delete flows.
- **Same composer structure in the empty and mid-conversation states** (2026-08-06) — the empty "new conversation" state used to render the composer with `compactLayout` (single-line, buttons inline with the textarea); it now renders identically to the mid-conversation composer (multi-line textarea + full `bottomRow`) per the developer's request. See `RichInputField`'s "Resolved" entry.

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

Two call sites remain, both dedicated Activity surfaces rather than embeds inside another
dashboard: `TasksPage` (`/admin/tasks`, `scope="platform"`) and `TeamSettingsPage`'s Activity tab
(`/team/:teamId/settings/activity`, `scope="team"`). This organism's own rows have no ack/dismiss
affordance — the per-task acknowledgement UI (`TASK-EVENT-STREAM-RFC.md` §2.10) lives in
`TaskCard`/`TaskDetailPopover` (the personal tray, `TaskTray`/`MigrationPage`), a different,
non-overlapping consumer of the same `acknowledged_at`/`acknowledged_by` fields.

**Removed call sites (v3, OBSERV-02, shipped 2026-07-26; reverted 2026-07-30).**
`AnalyticsPage`'s admin-only section (`scope="platform"`) and `TeamUsagePage`'s team_editor
(`scope="team" kind="ingestion"`) and team_admin (`scope="team"`, unfiltered) sections briefly
embedded this organism per `CONTROL-PLANE-PRODUCT-CONTRACT.md` §36. Removed as a live-review finding: they
duplicated the two dedicated surfaces above, one click away in the same nav rail, without this
organism's missing ack affordance ever getting fixed for the duplicate. See
`CONTROL-PLANE-PRODUCT-CONTRACT.md` §36.

#### Open UX issues

- **Not yet design-reviewed** — implemented and covered by unit tests
  (`TaskActivity.test.tsx`), but no designer/product-owner pass has validated the
  counter disclosure's layout, the "With warnings" flag's visual weight against the
  state badge, or density once a migration result has most of its ~15 counters
  populated at once.
- **No ack affordance in this organism's own rows** — a platform/team admin reading
  Activités here has no one-click way to mark a failed/cancelled row seen; only the
  personal tray (`TaskCard`/`TaskDetailPopover`) offers that today. Lower urgency now
  that the only two call sites are the dedicated Activity tabs, not a dashboard embed
  seen incidentally.

#### Resolved

_(none yet)_

---

### `TaskCard` / `TaskDetailPopover`

**Location:** `src/rework/components/shared/molecules/TaskCard/TaskCard.tsx`,
`src/rework/components/shared/molecules/TaskDetailPopover/TaskDetailPopover.tsx`
**Status:** `Functional`

The personal-tray task surface (`TaskTray`, `MigrationPage`'s active/terminal grids) —
`TaskCard` renders one row per task with the ack/dismiss affordance referenced above; clicking
its status indicator opens `TaskDetailPopover`, a floating detail panel showing state,
progress %, step, elapsed time, and the raw `task.error` on failure.

#### Open UX issues

_(none yet)_

#### Resolved

- **Error text unreachable/uncopyable on failure, "Ignorer" a no-op for attachment tasks
  (2026-08-13, #2366)** — three gaps found live-testing a real ingest failure. The popover
  positioned itself purely from the anchor's rect with no vertical bound, so a long raw
  backend error (e.g. a DuckDB sniffer dump) could render past the bottom of the viewport with
  no way to reach the rest — now capped at `min(400px, 100vh - 16px)` with internal scroll, and
  the vertical position clamps against that same cap. The error text had no copy affordance
  short of a screenshot — added, reusing the existing `IconButton` + `useCopyConfirmation` +
  `writeRichClipboard` pattern. And "Ignorer" silently did nothing for a chat-attachment task:
  `fast/ingest` is synchronous and never creates a server-side task record, so the task is a
  client-only Redux entry and acknowledging it always 404'd — it now acknowledges locally for
  these `localOnly` tasks instead of calling an endpoint that never heard of them.

---

### `WritableDocumentPane` (writable_document capability)

**Location:** `src/rework/features/capabilities/writable_document/WritableDocumentPane.tsx`
**Status:** `Functional`

The right-column side panel of the `writable_document` capability (#1905, Kea port):
a Markdown WYSIWYG editor (`@mdxeditor/editor`) where the user and the agent co-write
documents. Tab strip when the session has several documents; editor remounts on agent
writes (keyed `${document_id}:${updated_at}`) but never while the user types; 800 ms
debounced autosave with a "Saving…" indicator; export menu (Word `.docx` / Markdown).
Mounted by `CapabilitySidePanelHost` when the capability is active.

Auto-open (2026-07-22): opening a conversation that already holds a document
opens the editor pane immediately (`WritableDocumentAutoOpenProbe`, a headless
`sessionProbes` plugin entry evaluated once per conversation-open against the
authoritative list API). Live writes mid-conversation keep their existing pop
via the card renderer; a list refresh never re-opens a pane the user closed.
writable_document only — the PPT preview declares no probe.

Double close removed (2026-07-22): the pane (and `PptPreviewPane`) shipped its
own header close button — a Kea-port leftover from `ResizablePaneShell`, which
had no chrome. Inside `InlineDrawer` that made two ✕ with the same action; the
drawer's header ✕ is now the single close affordance, like every other push
drawer.

#### Open UX issues

- **Not yet design-reviewed** — MDXEditor toolbar density, tab strip styling, and the
  saving indicator's placement have had no designer pass; the editor ships MDXEditor's
  default theme which may clash with the design tokens in dark mode.

#### Resolved

_(none yet)_

---

### `WritableDocumentCardRenderer` (writable_document capability)

**Location:** `src/rework/features/capabilities/writable_document/WritableDocumentCardRenderer.tsx`
**Status:** `Functional`

The `writable_document` chat-part card shown in an assistant message after the agent
writes or revises a document: title, last-author caption, open-in-panel action, and
the export menu. Auto-opens the pane once per `(document_id, updated_at)` for fresh
parts only (>5 s history-replay guard, same heuristic as the ppt_filler preview card).

#### Open UX issues

_(none)_

#### Resolved

_(none yet)_

---

## #1903 PPT Filler capability organisms

### `PptFillerConfigForm`

**Location:** `src/rework/features/capabilities/ppt_filler/PptFillerConfigForm.tsx`
**Status:** `Functional`

The ppt_filler capability's custom agent-form widget (rendered inside its
`CapabilityCard` via the `configWidgets` plugin slot, RFC §9 item 4): `.pptx`
upload/replace control, instant per-slide schema preview through the
capability's stateless `/analyze` pod route, slide-numbered template errors
i18n'd by stable code, and Save gating while the mandatory template is missing
or invalid. The staged file travels with the atomic save (multipart
`with-assets` endpoints); the preview never persists anything.

#### Open UX issues

- **Not yet design-reviewed** — upload row layout, schema-preview density on
  templates with many slides, and error-list prominence all need a designer
  pass.
- **No drag-and-drop** — file selection is button+picker only.

#### Resolved

_(none yet)_

---

### `PptPreviewCardRenderer` + `PptPreviewPane`

**Location:** `src/rework/features/capabilities/ppt_filler/PptPreviewCardRenderer.tsx`, `.../PptPreviewPane.tsx`
**Status:** `Functional`

The `ppt_preview` chat part (compact card: title, open-preview, `.pptx`
download) and the PDF side pane it opens (react-pdf, all pages vertical,
width-fitted, fresh pdf.js worker per mount). A live fill auto-opens the pane
once per deck version (5s page-age gate keeps history replay from popping it);
the pane mounts through the capability side-panel host's push drawer.

#### Open UX issues

- **Not yet design-reviewed** — card visual weight in the thread, pane default
  width, and the auto-open heuristic all need product validation.
- **No page thumbnails / jump navigation** — long decks scroll only.

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

### `FilesystemWorkspace` / `AgentsWorkspace` (Resources tabs — Mon espace/Espace d'équipe/Agents)

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
already honors. The manifest version stays 0.1.0 pre-GA; stored older slices
revalidate unchanged (the single scope toggle maps onto the split ones, and a
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

### `DocumentWorkspace` — bulk actions extend to selected folders (#2446, 2026-08-26)

Folder rows have always rendered a selection checkbox, but ticking one did
nothing: the contextual `BulkActionsBar` (delete / download / exclude-from-
search) and every bulk handler read `selectedDocs` (documents only). Selecting
a folder now drives the same bar, with each action applied **recursively to the
folder's subtree**; a mixed selection (files + folders) shows the union, applied
to both. The selected-count label counts every selected row.

- **Delete** — one `deleteTag` per selected folder (the backend cascades to
  sub-folders + their documents, same path as the single-folder delete) plus the
  existing untag path for loose documents. The confirmation warns generically
  ("… and all their content? This cannot be undone.") once folders are involved,
  rather than recomputing a precise recursive count (that would cost one browse
  per subtree tag — the single-folder delete keeps its live count).
- **Download** — resolves each folder's descendant documents on click and zips
  them under their folder-relative path, preserving the tree; loose documents sit
  at the archive root.
- **Exclude from search** — a folder-containing selection can't be resolved to a
  single include/exclude direction cheaply, so it offers **exclude only**: on
  click it resolves the subtree's documents and forces every non-tabular one
  non-retrievable (one summary toast, not one per document). The directional
  include/exclude toggle is unchanged for file-only selections.

Descendant documents are fetched **only when the action fires**, never on
selection, so ticking a folder box stays instant even for a large subtree; each
heavy action (download / exclude / delete) shows an in-button spinner while it
runs (`BulkActionsBar` gained `deleteLoading` and `searchToggle.loading`,
mirroring the existing `downloadLoading`).

### `DocumentWorkspace` — drag-and-drop: folder rows, full page, corpus root (2026-08-12)

Three drop surfaces, all behind the same `canUpdateResources` gate as the
explicit upload action, all opening the ingestion drawer
(`DocumentUploadDrawer`) pre-seeded with the dropped files so the user only
picks mode/profile (fast/medium/rich) and saves:

- **Folder row** (since 2026-07-23): targets that folder; the row shows the
  drawer dropzone's affordance (dashed `--primary` outline + 6% tint) while
  hovered with files, and its drop wins over the page surface below
  (`stopPropagation`).
- **Full page of an open folder**: the drill-down model shows one folder at a
  time, so dropping anywhere on the page reads as "add to this folder" — an
  overlay names the destination while a file drag hovers.
- **Corpus root**: only dropped FOLDERS are accepted — each becomes a library
  mirroring its structure (see below). Loose files are rejected with an error
  toast (they have no tag to land in and would upload invisible); a mixed
  drop keeps the folders' content and warns about the skipped loose files.

A dropped directory keeps its on-disk structure: each subdirectory becomes a
nested document tag (created exactly like `CreateFolderModal` would, existing
levels reused), and every file uploads under its own subdirectory's tag
instead of being flattened into the drop target. The drawer lists files under
their relative path and announces how many subfolders the save will create; a
failed/forbidden tag creation aborts the save before any upload starts.
Depth guardrail (#2355, 2026-08-13): the resulting folder path — destination
folder included, so a deep destination doesn't sidestep it — is capped at 15
levels (`MAX_FOLDER_DEPTH`, mirrored server-side by `MAX_TAG_PATH_DEPTH` on
tag creation; the value is bounded by OpenFGA's parent-chain permission
resolution, see structure.py). Files that would land deeper are skipped with
a warn toast naming the count; a drop with nothing shallow enough is
rejected with an error toast. Manual creation (`CreateFolderModal`) enforces
the same cap inline — Create disabled with an explanation instead of a 422
toast — and rejects "/" in a folder name on both sides (a slashed name would
smuggle several levels past the cap in one call; found live 2026-08-13).
The fs `mkdir` variant of the modal keeps the slash rule but not the depth
cap (not tag-backed, so the ReBAC-chain constraint doesn't apply).
Folder-originated files still upload under their leaf name: browsers put the
relative path in the multipart filename (one opaque "Upload failed: 404" per
file, found live 2026-07-23), pinned frontend-side and sanitized backend-side
(`upload_basename`).

Status refresh: a folder's document page reloads on every entry (not just the
first), and while any ingestion is live the 3s status poll also covers the
folder being viewed — a subfolder opened before its files' uploads (or fresh
ReBAC tuples) landed used to freeze forever on its first empty snapshot,
hiding the live "processing" rows (found live 2026-08-12).

Quota (#2360, 2026-08-13): Save first asks the server's `/quota/precheck`
with the batch's declared total, so a whole over-quota batch is rejected in
one round-trip — before any tag creation or upload, and covering the
personal quota the client can't see. A denial keeps the drawer open with the
server's numbers in the existing warning panel (usage / limit / batch /
excess) and disables Save until the file list changes. This replaced the
client-side team-only quota math; the check is advisory (upload endpoints
still re-check received sizes), so a precheck transport error falls through
to the save rather than blocking it.

### `DocumentWorkspace` — folder rows roll up their subtree's ingestion state (#2384, 2026-08-17)

A folder row now summarizes everything under it — its own documents and every
sub-folder's, at any depth — in the status column that used to be blank on
folder rows. Three states, in strict precedence:

| State | Chip | Lifetime |
| --- | --- | --- |
| something still ingesting | `StatusChip status="processing"` | until the last child settles |
| some documents failed | `status="warning"`, labelled with the count ("2 errors"), naming the files on hover | persistent |
| something under it finished this session | `status="ready" justCompleted` ("Done") | session-only |

`raw` is never rolled up: a folder of stored-but-unprocessed documents is a
steady state, not news. Precedence is processing > failures > done — while
anything runs the folder is not settled, and once it is, an unresolved failure
outranks a "your upload landed" marker.

"Done" means *something* under the folder finished this session and nothing
under it is still running or failed — not that every document it holds has been
processed. The stricter reading would never fire on a folder of long-stored
documents, and the mark exists to answer "did what I just started land?". It is
therefore normal for a folder holding fifty old documents to read "Done" after
one upload into it, until the next refresh.

Only the LAST terminal task per document counts. A document uid is derived from
its content, so re-uploading a file that failed produces a second task for the
same uid, and nothing removes the first (see the eviction note below) — reading
every task equally left a folder flagged with a failure the user had already
fixed, for the rest of the session, with no way to clear it. `cancelled` counts
as neither outcome: stopping an ingestion on purpose is not an error to chase.

Why the folder chip and not the document rows alone: from the top of the tree
the only way to tell whether a bulk upload had landed was to walk into each
sub-folder and read the rows one by one. That is also why failures are **named**
rather than only counted — hovering answers "which files do I go and look at?",
which a count cannot. The names cost nothing: `TaskTarget.label` for a session
failure (so a never-opened sub-folder is still nameable) and
`identity.document_name` for anything a loaded page covers.

The `warning` status is `StatusChip`'s alone, never `DocStatus`'s — no document
is ever "warning", and widening the shared type would push a meaningless case
onto every `DocStatusBadge` consumer. It uses the warning palette, not the error
one: the folder itself is not broken, and a red folder standing over a subtree
reads as a bigger problem than it is. It shares those colors with `pending`, so
the static warning triangle (against pending's breathing `sync`) is the
differentiator.

No new endpoint, no new backend status, no persisted field — two in-memory
source families are unioned, because neither subsumes the other:

- the **already-loaded pages** (`perTag`), read per tag id. Survives a page
  reload, and is the only source that sees what the browse snapshot knows and
  the task feed cannot: a teammate's ingestion, or a document a dead worker left
  `in_progress`/failed (#2279). Only reaches folders visited this session — but
  without it a folder could read "settled" while a row inside it visibly spins,
  the exact confusion the feature removes.
- the **SSE task feed** the document badge already reads (#2315), matched
  against the tag tree's `item_ids` via `collectDescendantDocUids`. Reaches
  folders that were never opened, live over SSE, but is memory-only and
  `scope=user`.
- the **team's ingestion history**, ONE unfiltered
  `GET /tasks?scope=team&kind=ingestion`. The Redux store is memory-only, and at
  the Corpus root no child page is loaded either, so without this the whole tree
  went blank on every reload and only lit up once the user opened a folder.
  `exclude_terminal` only defaults to hiding terminal tasks on the `scope=user`
  branch (authz.py); a team-scoped query returns every state, so **filtering by
  state would cost extra round-trips and drop data** — `cancelled` tasks, needed
  to clear a failure whose retry the user stopped, and teammates' in-flight runs.
  Team scope also surfaces a **teammate's** failure, which a user-scoped feed can
  never see. `can_read_members` is granted to `team_member`, which every team
  role inherits, so this is not admin-only: a member who cannot ingest at all
  sees the failures other people's uploads produced, and for them it is the only
  feed that ever reports anything.

A personal space cannot use team scope — personal uploads deliberately leave the
task's `team_id` NULL (`ingestion_controller.py`), so the query would come back
empty. It asks `scope=user` instead, which filters by creator rather than by
space; the caveat only bites if the same file was ingested into both a team and
a personal space, since uids are content-derived.

Only the LAST terminal outcome per document counts (`resolveDocOutcomes`), and
it governs **both** failure sources — a `succeeded` or `cancelled` outcome
clears a failure the loaded-page snapshot still reports, not just one the task
feed reported. Ranking is per clock domain and the two are never compared: the
history carries the server's `updated_at`, the Redux store the browser's
`Date.now()`, and a laptop minutes behind the server would otherwise leave a
just-repaired document flagged. A live entry wins outright, which is correct by
construction since it was observed after the page and its history loaded. An
unrankable timestamp sorts last rather than pinning whichever entry arrived
first.

The history feeds that ranking **only**. It is deliberately kept out of
`justCompletedDocUids`: folding it in would count every document the team has
ever ingested, turning the transient "your upload landed" cue into a permanent
green tick on every ready row and every folder. Completion therefore stays read
from the Redux store alone — session-only, expiring for free on refresh — while
a failure persists, because it still needs someone to act on it.

The derivation itself is pure and lives in `folderRollups.ts` beside
`deriveDocStatus.ts`, not inline in the workspace: it is directly unit-testable
(clock skew, unrankable timestamps, cross-source dedup) without rendering
anything, and reusable by any other tag-tree view. `deriveDocStatus` stays the
single owner of the "which stages mean failed" rule — the rollup calls it rather
than re-deriving stages, so a folder chip can never disagree with the rows it
summarizes.

The rollup is an inverted index, not a walk: `folderByDocUid` maps every
document uid to the visible child folder it sits under, built once per tag tree
(subtrees are disjoint — a document is tagged into exactly one folder), and each
rollup is then O(tasks in flight) lookups against it. Walking each subtree per
recompute instead would re-read the team's whole corpus at the Corpus root,
every page load and every 3s poll tick during an ingestion.

The live inputs are read through stable sorted string keys, never their own
identities: the task store is a fresh object on every SSE progress event, and
depending on it directly recomputes on each one — the same trap `pendingTagKey`
avoids for the 3s poll. Keys join on NUL (`KEY_SEP`), not a comma, so two
different id sets cannot collide onto one key: a document uid is not always a
uuid (scheduler pulls build `pull-{source_tag}-{hash}` from a configurable tag).
They are compared, never split back apart. The failure key carries the names
too, not just the uids — `taskEventReceived` rewrites `target` on any event that
carries one, so a label refined after the failure was first recorded must still
reach the tooltip.

Known scope, all of it inherent to deriving this client-side rather than from a
server-side per-tag counter:

- the history query carries no server-side LIMIT, so it returns the team's whole
  ingestion history (narrowed to `kind=ingestion`), and this API slice is
  configured `keepUnusedDataFor: 0` + `refetchOnMountOrArgChange: true`, so it is
  re-fetched on every mount of the workspace rather than cached across them.
  Bounding it server-side is a small follow-up if a large team feels it;
- the snapshot half of the failure count only sees the loaded page
  (`rowsPerPage`, 50 by default), so a visited folder holding 200 documents of
  which 60 failed can report fewer than 60, and the number moves as the user
  pages. The session half is uncapped, so the case this feature was built for —
  "I just uploaded, what broke?" — is counted in full;
- a document stuck `in_progress` (dead worker, #2279) pins its folder to
  "processing" for as long as the snapshot says so, and because processing wins
  the precedence, real failures under that folder stay hidden behind the
  spinner. That is the same stuck state the document's own row shows; fixing it
  belongs to #2279, not here;
- `item_ids` is a snapshot refreshed on tag refetch, so on the very first file
  of a batch the chip can appear a beat late, then self-corrects.

The chip is advisory throughout — not a count the user acts on directly, unlike
the folder-deletion count which had to move to live totals (#2173).

Both failure panels — the folder rollup's file list and a document's per-stage
errors — are **interactive** hover panels: the pointer can move into them,
select the text, and hit a copy button. That is `Tooltip`'s new `interactive`
mode rather than a bespoke popover, so every other hover panel in the app can
opt into the same affordance. The clipboard write goes through
`writeRichClipboard` and the receipt through `useCopyConfirmation`, the two
mechanisms every copy site already shares (#2366, #2359).

The rendered list names the first 10 failures and summarizes the rest ("and 12
more"), but **copy always writes the full list** — copying is exactly when the
whole thing is wanted.

A document's panel also carries the message the ingestion **task** reported,
under "Signalé par le traitement", alongside the per-stage `processing.errors`.
A run killed before any pipeline stage started (worker saturation, a Temporal
`TIMED_OUT` verdict) stamps nothing per stage, so the tab used to show "Erreur"
with an empty panel while the message sat on the task — visible only in the task
popover, which is not mounted for most users. The parent workflow already pulls
it out of the Temporal child job (`_wf_file_terminal_event_args`, #2315) and the
rollup already fetches it with the task history, so this is a wiring change, not
a new source. It is skipped when a stage message already says the same thing.

One coupling worth knowing: terminal tasks are never evicted today because
`taskEvicted` is only dispatched by `TaskTray`, which is currently unmounted
from the app. If the tray is remounted, `EVICTION_DELAY_MS` (5 min) starts
applying and both the session "done" mark and any task-sourced failure would
begin disappearing on that timer. The snapshot-sourced half is unaffected.

`countUniqueDocs` was deleted in the same change: it had lost its last caller in
#2173 and its DFS is now `collectDescendantDocUids`.

### `DocumentWorkspace` — embedded-title hint on the Name column

The Name column always shows `identity.document_name` (the real filename) now,
never `identity.title`: the latter is populated ingestion-time straight from a
file's own embedded metadata (PDF `/Title`, docx `core_properties.title`) with
no validation, so it was as likely to be empty, a stale value copied from a
shared template, or a generic "Untitled" placeholder as a real title. When a
document does carry a meaningful embedded title (different from the filename
or its stem), a small `info` icon next to the name surfaces it via the
`Tooltip` atom instead of silently overriding the display name. The icon is
`tabIndex={0}` so Tooltip's keyboard-focus disclosure actually reaches it, and
its own flex-row cell wraps the Tooltip's wrapper span in a `flex-shrink: 0`
guard so a narrow column with a long filename can't crush the icon down to
nothing. (Found live 2026-08-09.)

### `DocumentWorkspace` / `ManageLabelsModal` — descriptive label management (2026-08-11)

**Status:** `Functional` — pending manual visual review

A document row's "more" menu offers "Manage labels": a compact dialog
listing the document's current `DocumentMetadata.labels` as removable
chips, plus an add field (explicit accessible name, focused on open) with
suggestions from `listDocumentLabels`. Every add/remove applies immediately
(no Save/Cancel) through a single canonical mutation
(`useMutateDocumentLabelsMutation`, `PATCH /documents/{uid}/labels` with a
JSON body) — `CorpusTreeService` and `CorpusVirtualFilesystem` stay
read-only consumers, untouched.

No character restriction on a new label: the JSON body transport carries
any Unicode text, including `/`, `#`, `?`, `%`, and spaces, which the
original URL-path-segment routes could not (see FILESYSTEM.md "Business
labels"). **Open product question, still not settled:** whether labels are
meant to be bounded technical tokens (e.g. `DAT`) or free descriptive text;
this UI takes no position on it — see FILESYSTEM.md.

**Open UX issue — shared `Dialog` duplication.** `ManageLabelsModal`
hand-rolls the same Portal/overlay/dialog shell as the pre-existing
`RenameModal` (same directory) instead of the shared `Dialog` molecule:
`Dialog` is built around a confirm/cancel action pair, but every action
here already applies immediately — there is no "confirm" step, only a
single "Close". Reusing `Dialog` as-is would mean either a redundant second
button or modifying `Dialog` to support a single-action mode, both out of
scope for this increment. Revisit if a third "auto-applies, single close
action" dialog appears — three is when a shared "no-confirm" `Dialog`
variant pays for itself.

### `CategoryPicker` / prompt category surfaces (PROMPT-09)

**Location:** `src/rework/components/shared/molecules/CategoryPicker/CategoryPicker.tsx`
**Status:** `Functional`

Categories are team-owned content, not a fixed global list (PROMPT-09) —
`CategoryPicker` takes a live `categories: PromptCategorySummary[]` prop
(fetched per-team) instead of a static catalog. Rendered as a single
flex-wrap row of small selectable chips (name only, no icon, no colour —
colour-coding categories was tried and dropped as adding no value). Selected
chip gets a filled `--primary` background; no fold/show-more, chips just
wrap. First chip is always "Sans catégorie" (`onChange(null)`) — the default
selection for a new prompt (`emptyForm.category_id === null`) and for any
existing prompt with no category.

#### Open UX issues

_(none)_

---

### `ManageCategoriesDialog`

**Location:** `src/rework/components/pages/PromptsPage/ManageCategoriesDialog/ManageCategoriesDialog.tsx`
**Status:** `Functional`

Reachable from a `tune`-icon button in `PromptsPage`'s category filter-chips row, rendered only for
`canManage` (`canUpdateResources`, the same team-editor flag that gates the card hover-edit pencil) —
non-editors never see the button, and every mutation is independently `team_editor`-gated server-side
too (403 toast on denial if that ever drifts). Staged draft/save/cancel model: Créer / Éditer / Supprimer only edit
local state — nothing hits the backend until "Enregistrer" is clicked, which diffs the draft against
the original list and fires exactly the needed create/rename/delete calls; "Annuler" discards the
draft with zero calls. No per-row delete confirmation (the staging itself is the undo). Rows show a
name only, no colour swatch (dropped along with `CategoryPicker`'s).

Every row icon button (edit, delete, and the check/close pair shown while editing) is wrapped in the
instant `Tooltip` atom. A row whose category id is in `usedCategoryIds` (computed in `PromptsPage`
from the live prompt list, mirroring the backend's own in-use check) has its delete button disabled
with a tooltip explaining why ("Cette catégorie ne peut être supprimée, des prompts lui sont
rattachés") instead of letting the user stage a delete that would 409 on save — a UI-level pre-empt
of the same rule the backend still enforces as the source of truth.

#### Open UX issues

_(none)_

---

### `PromptViewDialog`

**Location:** `src/rework/components/pages/PromptsPage/PromptViewDialog/PromptViewDialog.tsx`
**Status:** `Functional`

Clicking a `PromptCard` opens this read-only view (name, description, category as a static
non-interactive chip — "Sans catégorie" when unset — and the full prompt text) instead of jumping
straight to the edit form, which was the old, editor-only behaviour. Editing is now reachable only
through the card's hover-edit pencil (gated on `canManage`); the dialog itself has no edit action,
only a close (X) — deliberately pure read-only, no "Edit" shortcut inside it. The close button is
`size="medium"`, `color="on-surface-retreat"`, absolutely positioned 16px from the card's top and
right edges (not a flex sibling of the title, so a long name never pushes it around). Uses
`FullPageModal`'s `background="scrim"` variant (a normal translucent `--scrim` backdrop) rather than
the opaque `main`/`container` full-page takeover the rest of the app's `FullPageModal` instances use.
Clicking the scrim (outside the card) closes the dialog — `FullPageModal` gates this click-to-close
on `background === "scrim"` only, so the opaque `main`/`container` data-entry forms (edit form,
`ManageCategoriesDialog`) keep their current behaviour and can't lose in-progress input to a stray
click.

Prompt text is a plain scrollable `div` (`white-space: pre-wrap`, fixed height, `overflow-y: auto`),
not a `textarea` — a `readOnly` textarea can still be focused, clicked into, and have its text
selected/dragged, which this deliberately avoids (`tabIndex={-1}`, `user-select: none`): scroll is
the only interaction, the copy button is the only way to get the text out. A `content_copy`/`check`-
toggling `size="medium"` icon button in the text section's header copies the full prompt text to the
clipboard (same 2s-revert pattern as `CodeBlock`'s copy button) and fires a 2s `showSuccess` toast
("Copié dans le presse-papier"). Fetches the full prompt (`text` isn't on the list-level
`PromptSummary`, only `text_preview`) via the same detail query the edit form uses, keyed off the
clicked prompt's id.

#### Open UX issues

_(none)_

---

## HELP-01 Help Center (#2189, 2026-07-31)

### `HelpCenterPage` (+ `HelpSidebar`, `HelpArticle`)

**Location:** `src/rework/components/pages/HelpCenterPage/`
**Status:** `Functional`

Standalone wiki-style documentation page (own tab, no app chrome) at
`/help/:lang/:sectionId/:pageId`, rendered from the markdown corpus in
`features/helpCenter/content/`. Two panes: navigation rail
(`surface-container`, 32px `label-medium` section headers, `NavigationMenuItem`
page items, `Separator` dividers) and the article column
(`Breadcrumb` + copy-page-link `IconButton`, `MarkdownRenderer` with
`headingAnchors`). fr/en switch as an xs `ButtonGroup` in the header, synced
with the URL. Entry: profile menu item below "Profil" (icon `help`).

### `MarkdownRenderer` `headingAnchors` + `HeadingWithAnchor`

**Location:** `src/rework/components/shared/molecules/MarkdownRenderer/`
**Status:** `Functional`

Opt-in h2/h3 rendering with a slug `id` and a hover/focus-revealed copy-link
button (xs icon `IconButton`, `link` → `check` feedback). Off by default —
chat rendering unchanged.

### `HelpSearch` (HELP-01.B)

**Location:** `src/rework/components/pages/HelpCenterPage/HelpSearch.tsx`
**Status:** `Functional`

Global help search in the page header: a `SearchInput` (reused) with a
results dropdown. The index (`features/helpCenter/search.ts`) is built
client-side, lazily on the first keystroke, cached per language for the
session — nothing runs until the user types. Weighted scoring (title >
description > heading > body), AND semantics across terms, `<mark>`-highlighted
snippet; a heading hit carries the heading's anchor so selecting the result
lands on the exact section.

#### Open UX issues

- **Not yet design-reviewed** — sidebar density, header weight, article
  measure, the anchor-button hover affordance, and the search dropdown
  (result density, snippet length, keyboard navigation) need a designer pass
  once real content lands (HELP-01.C).

---

## Platform model binding admin UI (#2365, 2026-08-15)

### `PlatformModelBindingsPanel`

**Location:** `src/rework/components/pages/admin/CapabilitiesPage/PlatformModelBindingsPanel/`
**Status:** `Functional`

`InlineDrawer` opened from `CapabilitiesPage`'s Models tab, sibling to
`CapabilityTeamMatrixDrawer`. Renders exactly one row — chat — never a
4-capability list; V1 has no `language`/`embedding`/`image` binding to show.
Row states: bound (`{{provider}} / {{name}}`), unset ("Using pod default"),
loading, and load-error, each with its own translation key. Edit opens a
form with two `TextInput`s (`provider`, `name`) and a `TextArea` JSON
settings editor. `provider` is deliberately a free-text input, not a
generated-enum picker — the server's `ModelBinding` validator (provider
restricted to `fred_core.model.models.ModelProvider`) is the actual
authority and 422s an unsupported value; the generated client only supplies
a closed TypeScript union for the request payload's type, not a picker
widget. The settings editor parses JSON explicitly, reports invalid JSON
inline, and disables Save while invalid — it does not re-implement the
server's typed/credential-shape validation client-side, since
`ModelBindingSettings` is the real security boundary. Reset ("delete")
clears the binding back to "Using pod default".

#### Open UX issues

- **Not yet design-reviewed.** Functional and covered by tests, but no
  designer pass yet on the drawer layout, the raw-JSON settings editor (vs.
  a structured form), or the provider free-text input's error affordance
  when a 422 comes back.

---

## Global info banner (2026-08-19)

### `InfoBanner`

**Location:** `src/rework/components/shared/molecules/InfoBanner/`
**Status:** `Functional`

Full-width, non-dismissable announcement banner mounted once at
the app root (`src/app/App.tsx`), above the GCU/bootstrap guards, so it shows
on every page — pre-auth ones included — and pushes the app content down
instead of overlaying it (the app shell is now a `100vh` flex column; routed
pages size with `height: 100%`, never `100vh` — see
`FRONTEND_CODING_GUIDELINES.md` §2.5). Entirely config-driven from
`platform.frontend.info_banner` (public pre-auth `/frontend/config`): without
the config block, nothing renders — there is no default banner. Persistent
by default; the optional `auto_hide_seconds` removes it that many seconds
after app load with a 300ms eased collapse (opacity + `grid-template-rows`
1fr→0fr, so the content below slides up instead of jumping; snaps under
`prefers-reduced-motion`, and the banner is aria-hidden as soon as the exit
starts). Background
color comes from configuration via the `--banner-bg` custom property
(deliberate token exception, comment in the module CSS); title/message/link
labels are locale maps resolved with `en` fallback; links open in a new tab,
separated by a `·`, and only http(s)/relative URLs are rendered.
`role="status"` + `aria-live="polite"`.

#### Open UX issues

- **Fixed dark text over a configured background.** `--banner-text: #00222c`
  assumes the configured color stays light (like the documented `#00BBDD`
  example); a dark configured color would fail contrast. Revisit only if a
  deployment actually needs a dark banner.

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
24. **HitlPrompt — focus management** — focus should move to the first actionable element when the prompt appears (interaction design; may require Figma update). Elevation/containment resolved 2026-08-05 (see component section).

## Composer model label (#2387, 2026-08-17)

### `ReasoningChip`

**Location:** `src/rework/features/capabilities/ReasoningChip.tsx`
**Status:** `Functional`

The composer's right-edge chip. Two concerns, now independent:

- **Model identity** — the model the next turn will actually route to, from
  `GET /teams/{team_id}/routing-policy/effective-chat-model`. Read-only; the
  choice lives in the team routing policy and the platform binding.
- **Reasoning toggle** — still emitted only when the agent's author enabled
  reasoning and a platform-enabled reasoning model exists (REASON-01 §8's
  diagnosability rule: a control that can do nothing must be absent).

Previously the model identity rode on the `reasoning_toggle` control's own
`params`, i.e. the single model whose *reasoning* an admin had enabled
platform-wide. That is unrelated to routing, so the chip contradicted any
platform binding or team override in force. The name is kept (`ReasoningChip`)
because the reasoning menu is still what makes it interactive.

Three render states:

| Condition | Renders |
| --------- | ------- |
| Reasoning control present **and** `reasoning_enabled` | Interactive `<button>`: model name, then reasoning state one step fainter (`--on-surface-muted`), then chevron. Menu on click. |
| Reasoning control present but `reasoning_enabled === false` | Static label only. The toggle would be inert — the pod strips reasoning for this model — so it is hidden rather than shown as a no-op. `undefined` (not resolved yet, or an older backend) keeps the control the platform served. |
| No reasoning control at all, model resolved | Non-interactive `<span class="static">`, same 38px metrics so the composer row keeps its rhythm. Deliberately **not** a disabled button — no action is being withheld, so nothing should look clickable. |
| Neither | Nothing (`null`). An empty chip would be worse than none. |

**Unavailable model.** When `enabled_for_team` is `false` the turn will fail
with `ModelNotUsableError` before the LLM call. The model name takes
`--error` + `line-through` via `.model[data-unavailable]`, an `error_outline`
icon sits beside it, and the reason reaches the accessible name and `title` —
colour alone would leave a colour-blind reader with no signal.

**Label fallback**: `modelLabel(display_name, name, capability_id)` prefers the
ops-authored `model_display_name`, then prettifies the real model `name`, then
falls back to splitting the capability id. The `name` step matters because
`model_capability_id` normalizes non-id-safe characters — derived from the id,
`mistral:latest` would read "Mistral Latest".

### `PlatformRolesPage` (`/admin/platform-roles`, 2026-08-21, #2405)

**Status:** `Functional`

Admin-sidebar entry "Platform roles" (`admin_panel_settings` icon), gated
`Protected requires="admin"`. Layout mirrors `AdminTeamsPage` (760px column,
uppercase section titles): a holders table then a grant form. (A dedicated
root card above the table was tried on 2026-08-21 and removed the same day
— the pinned first row with its badge is prominence enough.)

- **Holders table** — one row per user holding `platform_admin` /
  `platform_observer`; roles render as full-label `Chip`s kept on **one
  line** (developer decision 2026-08-21: full labels, same line, page width
  staying at the 760px admin default — the roles column takes `3fr` vs the
  user column's `2fr` and the cell is `nowrap`, so a two-role holder never
  stacks). The remove affordance
  follows the backend rules (PLATFORM-ADMIN-DELEGATION-RFC.md §3): observer
  chips are removable by any platform admin, admin chips only when
  `caller_is_bootstrap_root`, and never on the bootstrap root's own row. The
  root row is **pinned first** (backend sort) and carries a small filled
  **crown icon** in `--primary` next to the name (tooltip + aria-label
  "Admin principal"/"Primary admin" — a text badge was tried 2026-08-21 and
  replaced by the crown the same day). Product wording is "primary admin";
  "bootstrap root" stays a backend/docs term.
- **Grant form** — `Autocomplete` over the admin user list, then a two-button
  segmented choice (observer/admin). The admin option renders **disabled**
  (not hidden) for non-root callers, with a persistent hint line explaining
  the root-only rule — the restriction stays discoverable instead of the
  option silently missing.
- All affordances are display-only mirrors; every action is re-checked
  server-side (403/404/409 mapped to toasts via `useApiErrorToast`).
## Bundled applications host

### `TeamApplicationsPage`

**Location:** `src/rework/components/pages/TeamApplicationsPage/`

The collaborative-team application index renders one responsive card per
authorized application. Each card uses the generated name, description, and
validated Material icon. A control-plane/local version or digest mismatch
keeps the card visible but non-interactive with an "unavailable in this Fred
build" label, so one rolling-update mismatch does not hide or break unrelated
apps. Loading, load-error, empty, and personal-space states are explicit.

The team sidebar adds exactly one **Apps** entry when at least one authorized
application is compatible with the local build. It never adds one navigation
item per application and never shows the entry in a personal space.

### `TeamApplicationHostPage`

**Location:** `src/rework/components/pages/TeamApplicationHostPage/`

The wildcard host fills the normal Fred content area and keeps the Fred shell
mounted. Catalog loading, generic unavailability, local contract mismatch,
module-load failure, and render failure have distinct contained empty states.
Application code is lazy-loaded only after the authorized team catalog and
local registration agree.

The platform-admin Capabilities page exposes applications through its **Apps**
filter. App rows reuse default-on and collaborative-team matrix controls but
omit personal-space and agent-health controls.

#### Host constraints

- Application-owned information architecture remains outside the generic host
  contract; the host specifies containment and failure behavior only.

---

### Capability side-panel launcher rail (2026-08-28)

**Location:** `src/rework/features/capabilities/CapabilitySidePanelHost.tsx`,
`src/rework/features/capabilities/<id>/plugin.ts`

**Status:** `Functional`

The launcher rail on the chat page's right edge, one small icon button per side panel
a session's active capabilities declare. **Since 2026-09-01 it is a page-root in-flow
column** — extracted into `CapabilityLauncherRail` (a flex sibling of `.pageBody`, not
inside it), `flex-shrink: 0`, full page height, 12px top/right/bottom margin — so it
reserves its own space at the far right and reflows the chat body left, rather than
floating over it as an absolutely-positioned overlay. Opening a panel retires the whole
rail (returns `null`), so the body-side push drawer takes the full width. Earlier
behaviour (#2459):

- **A launcher appears only once its panel has something to show.** The rail used to
  render one button per DECLARED panel, so activating `ppt_filler` + `writable_document`
  put two buttons onto empty panels from the first message. Each plugin now answers for
  the open conversation through a `useHasContent` hook on its `sidePanels` spec
  (ppt_filler: a deck was rendered; writable_document: the list API or a live snapshot
  holds a document); a panel that omits the hook stays always-on. The rail is invisible
  chrome until the agent actually produces something.
- **Each panel carries its own glyph** instead of the `edit_note` the host hardcoded for
  every one of them. `ppt_filler` → `slideshow`, `writable_document` → `edit_document`
  (a new entry in `materialIcons`, the page-with-a-pencil glyph) - each the one that
  capability's own card and pane header already carry, so the launcher reads as the
  thing it opens. The whole writable_document surface moved off `edit_note` to
  `edit_document` in the same pass (2026-08-28). Colour stays the rail's neutral
  `on-surface-retreat`: the launchers sit in the same floating-chrome band as the trace
  and attachments buttons, and tinting only these two would break that band.
- **The rail dropped to 68px from the top** (2026-08-28, superseded 2026-09-01). Back when
  the rail was absolutely positioned, its top offset was tuned against the two-line top bar;
  in-flow at the page root this offset is gone (the 12px top margin replaces it).
- **The rail retires entirely while a panel is open** (2026-08-28, still current). When it was
  an absolutely-positioned overlay this avoided landing on the open drawer's close button;
  now that it is an in-flow column, retiring also hands its width back to the body so the
  drawer fills the page. Moving the remaining launchers into the drawer's `headerActions` was
  tried the same day and dropped: closing the open panel to reach another one is cheap, and
  one home for the launchers beats two (developer decision).
- **The drawer's own title band is gone for both panes** (2026-08-28). A pane that
  names the artefact it holds does not also need the drawer naming the panel above
  it - two title rows said the same thing twice and ate the top of the column. A
  panel declares `ownsHeader: true` on its `sidePanels` spec; the host then passes
  `InlineDrawer`'s new `hideHeader` (the drawer keeps `title` as its accessible
  name) plus `flushBody`, and the pane renders its own close button. `demo_echo`,
  which has no header of its own, keeps the drawer's.
- **Switching conversations closes any open push drawer** (2026-08-28). Opening one
  is a statement about one conversation and every panel reads the open session, so
  a drawer carried across sat there empty. A capability whose new conversation
  warrants its panel asks for it again through the open-request counter.
- **Both panes' header bands were trimmed** (2026-08-28) - `PptPreviewPane` and
  `WritableDocumentPane` share the same title + actions row, padded down from
  `8px/16px` to `4px/12px`; the editor toolbar under it lost the same 4px. Two
  stacked bands (the drawer's own header, then the pane's) were eating the top of
  the panel. The download controls keep `size="small"`: those components are shared
  with the chat cards, where the smaller tier would have broken alignment.

Both capability slices now stamp the conversation their state belongs to, so a deck or a
document from a previous conversation can no longer light a launcher up on a fresh chat.
The writable_document editor applies the same scoping to its TAB STRIP (2026-08-28): its
document set merges the API list with the live snapshots, and the snapshots outlive the
conversation that produced them (the slice only drops them when the next conversation
upserts one of its own). A conversation whose documents all come from the API never
upserts, so the previous conversation's document showed up as an extra tab - someone
else's document, in an editor that autosaves.
