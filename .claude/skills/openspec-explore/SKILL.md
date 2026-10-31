---
name: openspec-explore
description: Explore a specifically selected OpenSpec increment without editing implementation. Use for an explicit exploration request in that context; general Fred design uses the shared Weaver method.
---

# Explore a selected increment

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

Exploration is read-only unless the user also asks to capture or implement the
result. Begin with the business example, lifecycle and truly unresolved choices.
Inspect current schema, constraints, transaction owners and consumers to distinguish
facts from proposed behavior. Discuss tradeoffs with concrete examples; do not ask
the user to choose interchangeable SQL details.

Use `openspec list --json`, `status` and `instructions` only in the selected
planning home when relevant. An empty change list is not a requirement to create
one. No automatic artifact capture, RFC, status ledger or specification tree.
If artifact edits are requested, use the propose/update workflow for that scope.
If the user asks to implement, switch to the authorized incremental work; an
exploration stance does not require a special exit command or another proposal.

Finish with what is known, material questions, the minimal option, its limits and
whether the foundations are sufficient to proceed. Do not prolong exploration to
fill a workflow template.
