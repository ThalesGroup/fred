---
name: openspec-sync-specs
description: Synchronize approved delta specifications for a selected OpenSpec increment when explicitly requested. Does not restore the retired specification corpus.
---

# Synchronize a selected delta

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

Read the selected change's status and spec instructions. Use `planningHome.root`
and returned artifact paths; compare each delta with its corresponding current
spec, preserving nested capability paths. Only touch capabilities this increment
changes. Missing specs do not authorize recreating historical capabilities.

Preserve scenario coverage and apply added/modified/renamed/removed requirements
according to CLI guidance. A modified requirement must retain all applicable
scenarios; omission is not evidence of retirement. Resolve conflicting edits and
unapproved removal before writing. Follow explicit CLI retirement metadata and
prerequisites; never delete a whole capability merely because one delta removes a
requirement. Prefer CLI-supported synchronization when available.

Run `openspec validate --specs` in the same selected planning home. Report actual
spec changes and validation. This synchronizes the selected contract; it does not
prove implementation, replace arc42 or authorize archiving/publishing.
