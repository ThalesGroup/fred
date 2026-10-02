**Tracking:** #2847

## Why

Importing a document whose name already exists in the destination folder
silently creates a hidden "alternate version", or refuses the import with an
instruction the product cannot satisfy ("delete or promote it") because no
promote action exists. The user is never asked, never told, and cannot act.

Deciding what to do about a same-named file is the user's call. See
[RESOURCE-INGESTION-UX-RFC](../../../docs/swift/rfc/RESOURCE-INGESTION-UX-RFC.md) §3.1.

## What Changes

- Add a name pre-check for a destination folder: the client sends the file names
  it is about to import and receives the list that already exists there. Names
  only — no file content leaves the browser.
- Ask the user once per import, not once per file: the conflicting files are
  presented as one list with "overwrite all", "skip all", or a per-file choice.
- Carry the per-file decision on the upload request. Overwrite replaces the
  content of the existing document and **preserves its `document_uid`**, so
  existing links, citations and agent answers keep resolving. Skip leaves the
  existing document untouched and reports the skipped files.
- Re-check at write time and return a file whose conflict appeared in between
  (a teammate imported the same name) as a conflict to resolve, rather than
  failing it or silently overwriting.
- **BREAKING** for the import API surface: the upload routes gain a per-file
  decision field, and a conflicting file without a decision is refused instead
  of being versioned.

Deliberately unchanged here: `canonical_name` and `version` still exist and are
still written. Retiring them is a separate change that depends on this one, so
that duplicates are already handled before the old mechanism is removed.

Independent of `revamp-document-import-experience`; the two can proceed in
parallel. The main question is asked before the upload starts, while the import
dialog is still open. A conflict detected at write time surfaces on the affected
document's row in the folder, which keeps its own status whether or not the
panel exists — the panel aggregates that state, it does not replace it. Until
the panel ships, a user who has navigated away from the folder can miss a late
conflict; that is the same exposure as today's transient notifications, and the
panel closes it.

## Capabilities

### New Capabilities
- `document-import-conflicts`: detecting same-name conflicts in a destination
  folder before upload, carrying the user's decision, and applying overwrite or
  skip.

### Modified Capabilities

None.

## Impact

- Knowledge Flow: a new name-check route, and a per-file decision on
  `/upload-documents` and `/upload-process-documents`
  (`features/ingestion/ingestion_controller.py`).
- `IngestionService`: overwrite must reuse an existing `document_uid`;
  `_generate_file_unique_id` returns a random UUID per ingestion
  (`base_input_processor.py:61-67`), so nothing does this by default.
- Postgres: an index supporting "does this name exist in this folder" so the
  check is not a corpus scan. The `metadata` table has no such index today.
- Frontend: `DocumentUploadDrawer` gains the pre-check and the conflict list;
  the generated Knowledge Flow client is regenerated in the same change.
- Storage accounting: an overwrite replaces content rather than adding a
  document, so the team quota delta is the size difference, not the full size.
