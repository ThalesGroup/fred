## Decisions

1. **Typed field, not parsing.** `attachments_markdown` lists the whole session and is model input; a typed per-turn list is the only reliable source for display.
2. **Mirror skill selections.** Same path as `skills` → `metadata.extras.skill_invocations`: sent in `RuntimeContext`, persisted by `_write_turn_history`, read back by `toThreadMessages`.
3. **Compatible both ways.** `RuntimeContext` ignores unknown fields, so older pods drop it; messages without `extras.attachments` render as today.
4. **Read-only chips in the bubble.** Owner decision: `Chip` with `attachmentIcon` and a new `appearance="tonal"`, inside the bubble above the text; no click, download or removal.
5. **A turn needs text.** The runtime already rejects an empty input, so the composer keeps its send button disabled until there is text. A restart re-sends the interrupted turn's files.
