---
name: openspec-apply-change
description: Implement a specifically selected current OpenSpec change within its agreed scope. Not a prerequisite for ordinary Fred implementation.
---

# Apply a selected change

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

Resolve the change from the request or current context; ask only when the choice
is genuinely ambiguous. Read `openspec status --change "<name>" --json`, then
`openspec instructions apply --change "<name>" --json` and its referenced files.
If required artifacts are missing, identify the actual dependency. Do not invent
acceptance criteria or widen scope to make an unchecked task implementable.

Implement one bounded responsibility at a time, reusing shared owners and removing
superseded paths. Check the current migration sequence immediately before adding
one. Preserve dirty changes, applied migrations and authorization boundaries.
If the selected plan contradicts current agreed decisions, explain the concrete
conflict before dependent edits rather than treating the old text as authoritative.

Update task state only for work actually completed. Apply scoped formatting and
code quality; run tests/reviews/campaigns only within the authorized validation
scope. Update arc42 for implemented architectural changes, distinguishing prepared
structures from integrated journeys. Report actual changes, production-code impact,
verification and remaining work. Do not automatically commit, publish or archive.
