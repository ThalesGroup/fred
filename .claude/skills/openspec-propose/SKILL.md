---
name: openspec-propose
description: Prepare the change contract for a specifically selected OpenSpec increment. Not the default workflow for a feature, fix or ordinary design discussion.
---

# Propose an agreed OpenSpec increment

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

Understand the concrete need and agreed scope. Resolve material business questions
before writing dependent requirements; choose ordinary technical details yourself.
Reuse a relevant active change when one exists. For a new selected change, use
`openspec new change "<name>"`, preserving the selected store/schema, rather than
manually creating its directory.

Read `openspec status --change "<name>" --json`. Follow the transitive dependency
set of `applyRequires`; file existence alone does not mean prerequisites are done.
For each needed artifact read `openspec instructions <artifact-id> --change
"<name>" --json`, its current dependencies and its resolved output path. Respect
explicitly skipped or conditional artifacts; do not fill optional sections merely
to create more documentation. Recheck status after writes.

Keep the contract small: accepted need, invariants and owners, concrete schema and
transaction effects, reuse/removal choices, acceptance and bounded tasks. Do not
restate arc42 or rebuild capability-wide specs outside this increment. Record
unresolved decisions honestly, not as invented requirements.

Report the artifacts and any real unresolved decision. If only planning was
requested, stop there. If implementation is already authorized and its scope is
settled, continue under the repository's incremental workflow; do not impose a
second permission ceremony solely because these artifacts now exist.
