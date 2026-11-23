## Context

The page remounts per agent instance, not per conversation, and the composer state is cleared only when a turn starts. The drawer and `attachments_markdown` read the full control-plane attachment list, which gets a row as soon as a file is dropped.

## Decisions

- **"Sent" is derived on the client.** The user messages of the loaded history already record their attachment ids. A `sent_at` column would duplicate that, and need a migration and a contract change.
- **Legacy rule.** An attachment created before the latest composer message without an attachment list counts as sent. New turns record `attachments: []` when no files are sent, so a later restart cannot classify an unsent draft as sent. HITL answers, steered text and optimistic rows are excluded from the legacy cutoff.
- **No history, no split.** When the history cannot load, every row counts as sent: showing sent files as removable drafts would let the user delete them.
- **Agent context.** A composer send lists the sent files and the drafts it sends; HITL resumes and restarts list only the sent files. A restart preserves any new composer draft added after the interrupted turn.
- **Drafts come back from the attachment list.** Rows that are not sent and not already in the local state are shown as ready composer chips. Local chips carry the conversation they were ingested for, and only those of the current conversation are shown and sent.
- **The attachment list never shows the previous conversation's rows** while the new one loads (`currentData`), so they cannot pass as drafts.
- **Drop and paste follow the composer.** Both reach the whole page, so they are refused while a question holds the composer, like typing.
- **Never-sent drafts are not cleaned up separately.** Removing the chip already deletes the row and its Knowledge Flow artifacts; session erasure covers the rest.

## Known gaps

- Knowledge Flow indexes a file in the session scope as soon as it is dropped. A file dropped during a running turn can be found by that turn's document search.
- A file cannot be dropped or removed while its composer send is being prepared. A send waits for history and attachment hydration before classifying persisted drafts.
