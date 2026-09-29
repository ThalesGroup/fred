## Context

`_apply_versioning` (import) and `_promote_alternate_version` (deletion) are the
two halves of one mechanism. Both call `get_all_metadata`, which issues
`select(DocumentMetadataRow)` with no `WHERE`, builds a Pydantic model per row,
hydrates labels and filters in Python. Measured cost of one call: 6 ms at 45
documents, 36 ms at 545, 355 ms at 5045 — roughly 0.07 ms per document in the
table, paid once per imported file and once per deleted document.

Removing the mechanism removes both scans. That is a side effect of a product
decision, not the reason for it: the mechanism goes because it is invisible and
unactionable.

## Goals / Non-Goals

**Goals**

- Leave no document hidden or unreachable after the migration.
- Remove both halves together, so no half-mechanism survives.
- Remove the fields from the shared contract rather than leaving them stale.

**Non-Goals**

- The conflict mechanism itself (`add-import-conflict-resolution`, a hard
  dependency).
- The other costs on these paths: the blocking content-store write (#2370), the
  redundant disk copy and the double hashing (RFC §8), the remaining deletion
  costs in #2844. Removing this scan does not close #2844.

## Decisions

### Migrate before removing

The migration reads `version` and `canonical_name`, so it has to run while they
still exist. Migration and removal ship together, migration first, in one
change: splitting them would leave a release where alternate versions exist with
no code that understands them.

### Remove the fields rather than deprecate them

They live in three files and nothing outside consumes them. A deprecated field
in a shared contract is a question every future reader has to re-answer. They
are exposed in the generated frontend client, so that client is regenerated in
the same change per the repo's generated-client rule.

### Renaming, not deleting

An alternate version is a real document a user imported. The migration makes it
visible under a distinct name and lets the user decide. Deleting it would
destroy content on their behalf to tidy a mechanism they never saw.

The exact renaming scheme is left to implementation, with one constraint: the
result must be unambiguous in its folder and must not collide with another
document there.

## Risks / Trade-offs

- **The migration touches every document that has an alternate version.** It
  must be idempotent and re-runnable: a half-applied migration that renamed some
  documents and not others must be safe to resume.
- **Removing a field from a shared contract is visible to every consumer.** The
  audit says only three files and the generated client. That audit must be
  re-run at implementation time, not trusted from this document.
- **Deletion behaviour changes.** Deleting a base document no longer promotes
  anything. That is the intent, but any test asserting promotion will fail and
  must be removed deliberately rather than adjusted to keep passing.
- **This change alone does not make deletion fast.** It removes one scan; #2844
  documents the rest. Do not close #2844 on the strength of this change.

## Migration Plan

1. Find every document with an alternate version.
2. Rename each to a distinct, non-colliding name within its folder, leaving
   content, identifiers and folder membership untouched.
3. Clear the versioning fields.
4. Then remove the code and the fields.

Idempotent, re-runnable, and reversible in the sense that nothing is destroyed:
a rollback leaves renamed documents, which remain valid ordinary documents.

## Open Questions

- What renaming scheme reads best to a user who never knew versions existed?
  This is a wording decision worth settling with the developer before the
  migration is written.
