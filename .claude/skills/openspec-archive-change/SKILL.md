---
name: openspec-archive-change
description: Archive a completed, selected OpenSpec increment when the user requests close-out. Not an automatic consequence of any code change.
---

# Archive a completed increment

Follow the active checkout's `AGENTS.md`. Use this workflow only for an OpenSpec
increment the user/team has selected because it needs a change contract. Ordinary
work does not trigger it. Do not initialize OpenSpec or recreate the retired corpus
as a prerequisite for a fix or discussion. Preserve the user's authorized scope;
planning-only requests do not authorize implementation, and an already authorized
implementation does not lose that authorization merely because a skill was loaded.

For domain work, establish business need and invariants, then schema/transactions,
then application usages, API and UI using `fred-reconstruction-method`. Explain
reuse, replacement and removal before proposing additions. Distinguish observed
behavior, prepared schema and intended deltas; arc42 remains the current account.

Use the installed CLI's `status` and `instructions` output instead of inventing
artifact formats. Resolve the selected planning home; if a registered store was
named, discover it with `openspec store list --json` and retain `--store <id>` on
commands that accept it. Use returned roots/paths, never an assumed local directory.
Read only the relevant current decisions, sources and selected increment. If no
planning home exists, establish the intended destination before creating one; do
not silently fall back to another checkout or global store.

Resolve the selected change. Read its current status, tasks, acceptance evidence
and relevant spec differences. Identify unfinished work and verification limits;
do not label incomplete implementation complete to clear a workflow gate.
An explicit request to archive unfinished work requires an accurate disposition,
not false completion claims.

Use the CLI's supported archive and synchronization procedures for the selected
change. Preserve the planning-home/store selection, current edits, applicable
scenarios and unrelated capabilities. Do not bulk-archive old directories or
recreate the retired corpus. If a destination already exists, investigate rather
than overwrite it. Validate the result and report the actual archive path,
synchronization outcome and remaining limitations. No implicit commit or push.
