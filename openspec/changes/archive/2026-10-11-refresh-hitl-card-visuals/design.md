## Context

See proposal.md for the why. Everything renders through three molecules:

- `HitlPrompt`: the pending card. It covers agent questions (`stage: "agent_question"`, the compact card), tool approvals (`tool_approval`) and Graph questions (any other `stage`, full-width). It also shows the frozen read-only copy in history.
- `HitlAnswerSummary`: the answered record, either in the conversation flow (`ConversationThread`) or under the `ask_user` tool line (`inTrace`).
- `HitlChoiceRecap`: the recap in the trace detail drawer.

They compose shared atoms that the rest of the app also uses (`Button`, `ButtonGroup`, `TextArea`, `IconButton`). The design workbench used for the decisions is the reference rendering: https://claude.ai/artifact/4RgH1XoYN6wcXvW8fQuWmu. It is a private, disposable view, never a source of truth.

## Goals / Non-Goals

**Goals:**
- Reach the workbench rendering with existing tokens only. No new custom property and no new atom prop.
- Keep every visual variation local to the three molecules' CSS modules.

**Non-Goals:**
- Changing a shared atom. `ButtonGroup`'s `--spacing-2xl` radius and `IconButton`'s `50%` radius are tokenised in a separate PR, and `TextArea` keeps `--radius-s` app-wide.
- The active-card glow, which is shared with `RichInputField` and has no token.
- Runtime, wire contract or answer semantics.

## Decisions

1. **Local overrides, not atom props.** Choice rows need a full width, left-aligned content, `--radius-xs`, `--outline-muted` / `--outline-variant` borders, `--on-surface` labels and `--spacing-xs` vertical padding. All of this goes through classes on the `Button` instances inside `HitlPrompt.module.css`, the way `.choiceWithDescription` and `.selectedChoice` already do.
   - **Alternative:** a new `Button` variant. It was rejected because it widens a shared atom for one widget, which goes against the no-invented-variation rule and the scope discipline.
2. **Tool-approval emphasis by label colour only.** `--success` / `--error` labels in `--font-title-small-emphasized` on outlined buttons, keyed on the choice ids `proceed` / `cancel`, which the runtime already emits.
   - **Alternative 1:** filled success with an error refuse. Rejected by the owner as too loud.
   - **Alternative 2:** `color="error"`. Rejected because an error-coloured button means destructive in Fred.
   - "Approve for this conversation" stays neutral.
3. **Tab state icons through `ButtonGroupItem.icon`.** The atom already renders an optional `icon` before the label. Each tab gets `radio_button_unchecked`, `check_circle` or `do_not_disturb_on`, with an `accessibleName`.
   - The atom colours icons with the item's on-container colour. The answered state therefore needs the success colour from a `data-` attribute on the item, which `ButtonGroupItem` already spreads onto its `<button>`. A `:global` selector in `HitlPrompt.module.css` reads it, the same pattern the file already uses for `[role="tab"]`.
   - **Alternative:** per-item `color="success"`. Rejected because it also recolours the label and the selected background.
   - `do_not_disturb_on` and `reply` are missing from `materialIcons` (`shared/utils/Type.ts`) and are added there.
4. **Remove the close control.** `IconButton` disappears from the prompt. "Skip all" reuses the existing `onSkipAll` handler, shown only in grouped mode, as a text button left of "Skip". The action row order becomes: skip, send for a single question; skip all, send all for grouped questions, where skipping one question is its last choice and a small Confirm validates typed text.
5. **Answer record as a user bubble.** The conversation-flow `HitlAnswerSummary` keeps `MessageBubble`'s `.user` padding and 65% max width, in a lighter, squarer treatment: `--surface-container-highest` fill, 1px `--secondary-container` border, `--radius-s`, `--shadow-xs`, text `--on-surface`, `reply` icon `--secondary`, so it stays distinct from a composer message.
   - Below the `ask_user` line in the trace, the same bubble is used, aligned with the steps (left) instead of the user side. That is where an agent question's answer shows in most conversations, so a neutral trace card would hide the bubble in the common case.
   - **Alternative:** render it through `MessageBubble` itself. That is possible, but it would also bring the copy action bar, which an answer record does not need. Matching the tokens keeps the two in step without coupling.
6. **Compact typography.** The six `font-size: 0.8125rem` rules are deleted:
   - title: `--font-title-small`;
   - question: `--font-body-medium-emphasized`, in a full-bleed header band (`--surface-container-highest`, no divider); "Other": `--font-body-medium`;
   - choices: the `Button` atom's own `--font-title-small`;
   - tabs: the atom's `--font-label-large`, at size `2xs`, above the header band.
   - The free-text `TextArea` keeps `--font-body-large` (owner decision, matches the chat input).

## Risks / Trade-offs

- [Muted borders are low-contrast: 1.22:1 in light, 1.45:1 in dark, and the same as the disabled border in light] → The label identifies each control (15:1 enabled, 2.3–3.3:1 disabled). The owner accepted this after the check. Verify both themes in the app before merge.
- [`:global` selectors on atom internals (tab icon, material-symbols class) can break if the atom's markup changes] → They stay scoped under `.questionTabs` and are covered by a `HitlPrompt` test that asserts the state attribute and the icon names.
- [The in-flight change `refine-agent-question-answers` (all tasks done, only its archive is left) carries a MODIFIED delta of the same requirement, identical to the current spec] → If it is archived after this change, it would restore the old text. It has to be archived before this change, or its delta dropped. This is recorded as a task.

## Migration Plan

Frontend-only and visual. No operator action, migration note impact `none`. Rollback is a revert of the PR.
