## Why

Every imported document is assigned a hidden `version` within its folder, and
every deleted document triggers a search for an alternate version to promote.
The frontend never renders a version, no promote action exists anywhere, and
`docs/swift/design/INGESTION.md` never describes the mechanism.

Both halves call `get_all_metadata`, which loads the entire `metadata` table and
filters in Python — once per imported file, and once per deleted document.
Measured: 355 ms per call at 5045 documents, linear in corpus size (#2844).

The platform pays a full corpus scan on every import and every deletion for a
distinction nobody can see and nobody can act on. Once
`add-import-conflict-resolution` handles duplicates explicitly, the mechanism
has no remaining purpose.

See [RESOURCE-INGESTION-UX-RFC](../../../docs/swift/rfc/RESOURCE-INGESTION-UX-RFC.md) §2, §3.5.

## What Changes

- Convert every existing document carrying an alternate version into an ordinary
  document with a distinct name. Nothing is deleted and nothing stays hidden.
- Remove the versioning assignment from the import path and the alternate-version
  promotion from the deletion path, and with them both corpus scans.
- **BREAKING** for the document contract: `canonical_name` and `version` are
  removed from the document identity, and the generated frontend client is
  regenerated in the same change.

Depends on `add-import-conflict-resolution`: duplicates must already be handled
before the old mechanism is removed.

## Capabilities

### Modified Capabilities
- `document-import-conflicts`: same-name handling is the only duplicate
  mechanism; no implicit version is assigned and no alternate version is
  promoted on deletion.

## Impact

- `IngestionService`: versioning assignment removed from the import path.
- `MetadataService`: `_promote_alternate_version` removed, and with it one of
  the two scans reported in #2844. Deleting a document gets materially faster
  on a large corpus.
- `fred_core.documents.document_structures.Identity`: `canonical_name` and
  `version` removed. Confined to `ingestion_service.py`, `metadata/service.py`
  and `document_structures.py`; no capability, CLI or export path consumes them.
  They are exposed in `knowledgeFlowOpenApi.ts`, so the client is regenerated.
- Data migration over existing documents, with an operator note.
- `docs/swift/design/INGESTION.md` gains the duplicate rule it never described.
