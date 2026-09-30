## Why

Clicking the import dialog's save button does nothing visible for a long time,
then the dialog closes and ingestion starts. The dialog is modal, so the
application is unusable throughout, and the button says "Enregistrer" / "Save"
when nothing is being saved.

The backend already streams per-file, per-step progress, and the client already
parses it — the dialog discards all of it. A task panel with an aggregate
progress ring already exists and is mounted nowhere. Almost everything needed to
show the user what is happening is built.

See [RESOURCE-INGESTION-UX-RFC](../../../docs/swift/rfc/RESOURCE-INGESTION-UX-RFC.md) §3.2-3.4.

## What Changes

- The dialog closes as soon as the files are accepted, instead of when the last
  one has been prepared server-side. The application is usable immediately.
- Mount the existing `TaskTray` so a running import is visible from anywhere,
  not only on the Resources page.
- Show two named stages per file — upload, then analysis, then ready — rather
  than one merged bar. Only the second determines whether a document is usable.
- Show the user's own imports only.
- A failed file stays in the panel with a readable cause and a retry action,
  instead of a toast that disappears.
- On interruption, keep what arrived, name what is missing, and offer to finish
  by re-selecting those files.
- Allow cancelling the upload stage.
- Correct the wording: "Importer 12 fichiers" / "Import 12 files", and
  "Ajouter des documents" / "Add documents" in the plural.

## Capabilities

### New Capabilities
- `document-import-experience`: what the user sees and can do while an import is
  running, from dialog dismissal to a document becoming usable.

### Modified Capabilities

None.

## Impact

- Frontend only: `DocumentUploadDrawer` stops owning the wait, `TaskTray` is
  mounted and owns progress, `MainLayout` gains it, the fr/en strings change.
- No backend change: the per-file progress stream and the task events already
  exist and already carry what the panel needs.
- Depends on the task lifecycle for its truthfulness — see `design.md`. This
  change surfaces existing lifecycle defects rather than causing them.
- Document rows keep their own per-document status. The panel aggregates it and
  makes it reachable from anywhere; it does not replace it, and no row indicator
  is removed by this change.
- `add-import-conflict-resolution` has shipped the decision itself: the upload
  stream now carries a `conflict` status, and an import can be re-sent with the
  answer. This change owns where that question is answered — in the panel, on
  the item, never in the document table, which carries at most an indicator
  that opens the panel.
