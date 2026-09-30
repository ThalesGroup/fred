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

## Consumer audit, re-run 2026-09-30

The proposal's audit was re-run rather than trusted (task 1.1). It holds. Every
reader of `canonical_name` or `version` on the document identity:

| Where | What it does |
|---|---|
| `fred_core/documents/document_structures.py` | declares both fields; `_set_canonical_defaults` backfills `canonical_name` by regex |
| `ingestion/ingestion_service.py` | `_split_versioned_name`, `_existing_versions`, `_apply_versioning` |
| `metadata/service.py` | `_promote_alternate_version`, and the `version == 0` guard on the deletion path |
| `slices/knowledgeFlow/knowledgeFlowOpenApi.ts` | generated only — no hand-written frontend code reads either field |
| `tests/features/test_metadata_service_storage_release.py` | the only test that names them |

Nothing in the capabilities, the CLI, or the export/import paths consumes them.
Unrelated `version` keys exist in `features/resources/utils.py` (a file header)
and `corpus_manager_service.py` (a payload's `"v1"`); neither is this field.

### The audit above was scoped too narrowly, and a review caught it

It asked which code reads the two *fields*. That is why it came back saying two
docs had to follow and the frontend was clean, and it is why the first pass of
this change missed every site below — each of which depends on the *mechanism*,
not on the field names:

| Missed | What it was |
| --- | --- |
| `ingestion_controller.py` `AMBIGUOUS_CONFLICT_MESSAGE` | told users to promote an alternate version, an action this change deletes |
| `locales/{en,fr}` `rework.imports.failure.ambiguousName` | the sentence a user actually reads, saying "remove the duplicate"; the backend string is only the tooltip |
| `imports/importFailure.test.ts` | its fixture pinned the old backend sentence verbatim, so the only automated check of that classification tested a sentence nothing emits |
| `imports/importFailure.ts` comment | explained the cause as "a base and an alternate version" |
| `ingestion_controller.py` name-check endpoint description | promised a write-time re-check that the removed `apply_versioning` flag was the last thing performing |
| `tests/.../test_fast_ingest_tabular.py`, `ingestion_controller.py:706` | both justified bypassing `extract_metadata` by its versioning step |
| `scheduler/pull_files_activities.py` | see below — a behaviour loss, not just stale prose |

The lesson is cheap to state and was expensive here: audit the mechanism, not
the identifier.

### The scheduler pull path loses its only same-name bound

`create_pull_file_metadata` calls `extract_metadata` with no conflict plan, and
nothing on that path dedupes: `_generate_file_unique_id` returns a fresh uuid,
and `source_key`/`source_library_id` — the pair `uq_metadata_source_library_key`
constrains — are set only by `library_sync`. `_apply_versioning` used to raise
from the third identical pull onward, so a pull source re-presenting
`report.pdf` accumulated at most two rows before erroring.

It now accumulates without bound, and each extra row makes that name permanently
ambiguous for any UI import into that folder.

Not fixed here, deliberately: the right guard needs a decision this change has
no business taking — whether re-presenting an external path is an update to the
document already made from it or a new document — and adding one would bundle a
behaviour change into a removal. The old behaviour was not a guard worth keeping
either (it created one hidden duplicate, then hard-failed). Recorded rather than
quietly dropped.

### An alternate can outlive its base

The developer's local corpus holds one alternate — `2-regl_PASSI_v2.2.pdf`,
`version = 1` — with no `version = 0` twin. Promotion only runs when the
deleted document is itself a base *and* shares the removed folder, so an
alternate is easily orphaned. Nothing filters `version > 0` out of a listing,
so it is already visible under its own name.

The migration therefore has three cases, not one: an alternate whose base name
is still taken in its folder needs a new name; an orphaned alternate keeps the
name it has; and the name the first case would pick may itself be taken by a
third document.

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

### The name is `report (1).pdf`

Agreed with the developer, 2026-09-30. The number goes before the extension,
the convention Windows, macOS and every browser's download folder already use,
so a user who never knew versions existed has nothing to learn. On collision the
number increments until the folder is free.

The extension is whatever follows the last dot; a name without one takes the
suffix at the end. An orphaned alternate — no other document holds its name in
that folder — keeps the name it has and is only stripped of the two fields.

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

None. The renaming scheme, the last one open, was settled with the developer on
2026-09-30 (see Decisions).
