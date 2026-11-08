## Context

The page remounts per agent instance, not per conversation, and the composer state is cleared only when a turn starts. The drawer and `attachments_markdown` read the full control-plane attachment list, which gets a row as soon as a file is dropped.

## Decisions

- **"Sent" is derived on the client.** The user messages of the loaded history already record their attachment ids. A `sent_at` column would duplicate that, and need a migration and a contract change.
- **Legacy rule.** An attachment created before the latest user message counts as sent: before #3488, every ready attachment left with the next message.
- **Drafts come back from the attachment list.** Rows that are not sent and not already in the local state are shown as ready composer chips. Local chips carry the conversation they were ingested for, and only those of the current conversation are shown and sent.
- **The attachment list never shows the previous conversation's rows** while the new one loads (`currentData`), so they cannot pass as drafts.
- **Never-sent drafts are not cleaned up separately.** Removing the chip already deletes the row and its Knowledge Flow artifacts; session erasure covers the rest.

## Known gaps

- Knowledge Flow indexes a file in the session scope as soon as it is dropped. A file dropped during a running turn can be found by that turn's document search.
- A message cannot be queued while the composer holds attachments (already refused), so a draft is never left next to a sent message.
