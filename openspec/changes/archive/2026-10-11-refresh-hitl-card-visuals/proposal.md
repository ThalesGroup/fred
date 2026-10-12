## Why

The widgets shown when an agent waits for a person mix hard-coded values with design tokens, and they no longer match the rest of the chat. The affected widgets are agent questions, tool approvals and their answer records. Epic #2642 left "the shared HITL card redesign" as its next slice. The product owner has now settled every visual decision in a design workbench rebuilt from the current code, with the Pebble light and dark values.

Tracked by [#3034](https://github.com/ThalesGroup/fred/issues/3034).

## What Changes

- **Tokens only.** The compact card's hard-coded `0.8125rem` font sizes become DS text styles. Hard-coded `2rem` offsets become `--spacing-xl`. The `color-mix(primary 12%)` selection tints in the prompt and in the drawer recap become `--state-primary-selected`.
- **Radii.**
  - Question and answer cards use `--radius-ms`.
  - Inner controls (choices, "Other" field, free-text field, capability preview, recap rows) use `--radius-xs`.
  - The free-text `TextArea` takes the local override; the shared atom does not change.
- **Close control removed (BREAKING for the current spec).**
  - The top-right cross on agent questions is removed, and "Skip" is the only skip action for a single question.
  - A grouped card with several questions gains a "Skip all" text button, which does what the cross did.
- **Action order.**
  - Secondary actions sit on the left: "Skip all", then "Skip".
  - The logical main action sits on the right: "Send", "Next", "Send all".
  - The gap between actions is `--spacing-2xs`.
  - This reverses today's "Send directly left of Skip".
- **Spacing.**
  - Padding is tighter: `--spacing-xs` on the compact card, `--spacing-s` on full-width cards, and `--spacing-xs` between card elements.
  - An extra `--spacing-2xs` separates the question from the choices.
- **Choices.**
  - Full width of the card, text left-aligned (description included).
  - `--outline-muted` border at rest, `--outline-variant` on hover.
  - `--spacing-xs` vertical padding, label in `--on-surface`.
  - Choices on tool approvals and graph questions use the same height as agent-question choices.
- **"Other" row.** It reads as an input field rather than a choice:
  - input surface (`--surface-container-low`, `--outline-variant`), with an edit icon (16 px);
  - the "Other" label styled like the choice labels, then the placeholder "write your answer…";
  - typed text in `--font-body-large`, and at least the height of a choice.
- **Grouped questions.** No "Next" action. Skipping one question is its last choice (with the neutral ESC key hint), and the action row keeps "Skip all" and "Send all", the only primary action. Typed text counts once validated with a small primary check icon button (at the end of the "Other" field, under the free-text field), which turns into a success check until the text changes, or its shortcut, which also moves to the next unanswered question. Editing a validated text withdraws it until it is validated again. Every tab carries a state icon, so nothing shifts when an answer lands:
  - waiting: empty circle;
  - answered: check circle in `--success`;
  - skipped: struck circle.
- **Tool approval.**
  - Choices look like every other choice. The "Accept" label is in `--success`, the "Refuse" label in `--error`, both in `--font-title-small-emphasized`.
  - "Approve for this conversation" stays neutral.
- **Tool-approval reply.** It uses the same reply bubble. It recalls the tool or tools concerned (from the request's `pending_calls`), then the decision: "Accepted" or "Refused". "Approve for this conversation" is remembered in the browser and is stored as a plain approval, so after a reload it reads "Accepted" too.
- **Question header.** Title and question sit in a full-width band at the top of the card (`--surface-container-highest`, no divider, no gap between them), the question in `--font-body-medium-emphasized`. With several questions, the tabs (`ButtonGroup` size `2xs`) stay on the card surface above the band.
- **Number badges and keys.** Each choice starts with a square number badge (`--secondary-container`). Keys 1 to 9 pick that choice, Enter sends grouped answers, and Escape skips an agent question. Keys never act from a field, and Escape never acts while a drawer or dialog is open. Nothing is focused automatically.
- **Composer held for every card.** A tool approval or a Graph question holds the composer like an agent question does, so number keys reach the card. Only the interrupted-run card leaves it free.
- **Answer in the thread.** A standalone answered-question record in the thread is a light card in the user bubble's family, with the padding and max width of `MessageBubble`: `--surface-container-highest` fill, 1px `--secondary-container` border, `--radius-s`, `--shadow-xs`, text `--on-surface`, `reply` icon `--secondary`. It reads as the person's decision without looking like a message sent from the composer.
  - The question is recalled on top in `--font-body-small`, with a reply icon.
  - The answer is in `--font-body-large`. A skipped answer is in italics.
  - The record below the `ask_user` tool line in the trace uses the same bubble, aligned with the steps. For a ReAct question, this is where the answer shows.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-initiated-human-questions`: the following change:
  - choice layout (full width, left-aligned, instead of centered rows);
  - removal of the close control and a grouped "Skip all" action;
  - the order of the free-text and skip actions;
  - tab state icons;
  - the answer record in the thread shown as a user bubble;
  - a new requirement that HITL cards use design-system tokens, including the tool-approval label emphasis.

## Impact

- **Frontend only:**
  - `apps/frontend/src/rework/components/shared/molecules/HitlPrompt/` (component, CSS module, tests);
  - `HitlAnswerSummary/HitlAnswerSummary.*` and `HitlChoiceRecap.module.css`;
  - fr/en locale keys for "Skip all" and the tab state labels.
- **Design-system token:** a new `--shadow-xs` (`shadow-light.css`, `shadow-dark.css`), the softest elevation, used by the HITL answer bubble and by the user `MessageBubble` so both turns share one elevation.
- **Unchanged:** runtime, wire contract (`HumanInputRequest`) and answer semantics.
- **Docs:** `docs/swift/ux/COMPONENT-UX.md`. The fr/en Help Center page on agent questions is updated if it mentions the close cross.
- **Out of scope:**
  - tokenising the shared `ButtonGroup` / `IconButton` radii, in a separate PR;
  - the active-card glow, shared with the composer field and without a token, kept as is;
  - layout widths, since the DS has no size tokens.
- **Migration note:** impact `none`, as a visual-only change with no operator action.
