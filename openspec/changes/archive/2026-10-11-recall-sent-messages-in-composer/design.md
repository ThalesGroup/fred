## Context

See proposal.md for the why. The managed chat composer is `RichInputField`, mounted by `ManagedChatPage` with a controlled value (`useManagedChat`'s `input` / `setInput`). Its `handleKeyDown` first offers the key to the `/` command menu (`commandTrigger.onKeyDown`, which returns true when it consumed the key), then handles Enter. Nothing else uses the arrow keys.

The page already holds the conversation as `threadMessages`. User rows exclude human-input answers and carry `text` plus `command` (`command`, `appended_text`, `prompt_id`, `prompt_name`) for a command turn; the optimistic row added on send carries the same `command` metadata. The stored text of a command turn is the expanded prompt, so the typed line has to be rebuilt from `command`.

## Goals / Non-Goals

**Goals:**
- Keep `RichInputField` generic: it learns about one extra optional key handler, not about history.
- Derive the recall list from `threadMessages` on each render, with no extra state beyond the browsing position.

**Non-Goals:**
- Recalling attachments, turn options or the agent's answers.
- Persisting history across conversations, reloads or devices.
- Changing what the command menu lists or how it runs a command (only its dismissal rule moves, see decision 5).

## Decisions

1. **A `useComposerRecall` hook in `ManagedChatPage`.** It takes the user rows' recall lines, the current input, `setInput` and whether the menu is open, and returns an `onKeyDown(event): boolean` with the same contract as the command trigger. `RichInputField` gets one optional prop (`onRecallKeyDown`) called right after `commandTrigger`, so the menu always wins.
   - **Alternative 1:** handle history inside `RichInputField`. Rejected: the molecule would need the conversation, and other users of the field don't want it.
   - **Alternative 2:** fold recall into `commandTrigger.onKeyDown`. Rejected: it mixes two features and the trigger's `open` / active-descendant semantics.
2. **"Recalling" is derived, not toggled.** The hook keeps only the index of the shown entry. It is in browsing mode when `input` is empty, or equals the entry at that index; any other value resets the index. Editing therefore ends browsing without a change handler, and a conversation switch (new list, cleared input) starts fresh.
3. **Recall line.** `command ? "/" + command.command + (appended_text ? " " + appended_text : "") : text`, then consecutive duplicates collapsed. Rows with empty text are skipped.
4. **Caret at the end.** A recall bumps the field's existing `focusEndRequestId`, which already puts the caret at the end after an inserted library prompt. No new caret code.
5. **The menu opens only on typed text (owner decision).** A recalled `/summary` matches the menu query, so the recall marks that query as dismissed, through the same `dismissedQuery` state Esc already uses (`useComposerCommands` exposes a `dismiss(line)`). The menu stays shut and the arrows keep browsing.
   - The dismissal is cleared as soon as the query changes to another value, not only when it becomes null. A Backspace on the recalled line therefore opens the menu. This also fixes the Esc case where deleting and retyping the same last character found the menu still shut.
   - The menu also opens only while its query matches the composer's current value. The query is reported after the render that changed the value, so leaving a recalled `/command` used to flash the menu for one frame.
   - **Alternative:** let the recalled line open the menu, with Esc to get back to browsing. The owner rejected it: the menu answers typing, not a recall.

## Risks / Trade-offs

- [The person presses ArrowUp in an empty composer to scroll the thread] → The textarea already captures the arrows when focused, so nothing scrolled before; no behaviour is lost.
- [A recalled multi-line message: ArrowUp keeps browsing instead of moving up a line] → Accepted while the text is unchanged (same as shells); any edit restores caret movement.
- [Optimistic row and persisted row for the same turn] → They share the exchange id, so only one user row exists per turn.

## Migration Plan

Frontend only. Migration note impact `none`. Rollback is a revert.
