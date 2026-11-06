## Decisions

1. **Typed field, not parsing.** `attachments_markdown` lists the whole session and is model input; a typed per-turn list is the only reliable source for display.
2. **Mirror skill selections.** Same path as `skills` → `metadata.extras.skill_invocations`: sent in `RuntimeContext`, persisted by `_write_turn_history`, read back by `toThreadMessages`.
3. **Compatible both ways.** `RuntimeContext` ignores unknown fields, so older pods drop it; messages without `extras.attachments` render as today.
4. **Read-only chips.** Reuse the `Chip` atom with `attachmentIcon`; no download or removal from the turn.
5. **Chips above the text.** Owner decision: the chips render above the message text in the user bubble.
