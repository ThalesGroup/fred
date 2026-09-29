# RFC — Resource import: replace silent versioning with an explicit conflict prompt

**Status:** draft, pending sign-off. Product direction chosen by the developer
(2026-09-29); the open questions in §7 are not yet settled. Nothing here is
implemented.

## 1. Problem

Importing several documents into a team's Resources is slow, opaque, and ends in
a behaviour nobody can see or act on.

Three user-facing symptoms, reported from production:

1. Clicking the dialog's save button does nothing visible for a long time, then
   the dialog closes and ingestion starts.
2. The dialog is modal, so the rest of the application is unusable during that
   wait.
3. The button reads "Enregistrer" / "Save". Nothing is being saved — files are
   being imported and queued.

Behind the third symptom sits a fourth problem, invisible to users, which is the
reason this is an RFC rather than a UI ticket.

## 2. What the current versioning mechanism actually does

`IngestionService._apply_versioning` assigns every incoming document a
`canonical_name` plus a `version` integer within its destination tag. A second
document with the same name becomes version 1; a third is refused with:

> A draft version already exists for '<name>'. Delete or promote it before
> ingesting another version.

Verified on `swift` at `1bbe40614`:

- **The frontend never renders a document version.** The code comment at
  `ingestion_service.py:105` states "UI will use version field to render badge".
  No such badge exists anywhere in `apps/frontend/src`.
- **"Promote" is not an action.** There is no route and no UI for it. The error
  message instructs the user to do something the product does not offer. The
  only promotion is implicit, in `MetadataService._promote_alternate_version`,
  when the base document is deleted.
- **It is undocumented.** `docs/swift/design/INGESTION.md` does not mention
  versioning, canonical names or duplicates at all.
- **It is the dominant cost on two hot paths.** Both `_apply_versioning` (once
  per imported file) and `_promote_alternate_version` (once per deleted
  document) call `get_all_metadata`, which loads the entire `metadata` table,
  deserializes every row into Pydantic and filters in Python. Measured locally:
  6 ms at 45 documents, 36 ms at 545, 355 ms at 5045 — linear in corpus size,
  paid per file. See #2844.

So the platform pays a full corpus scan on every import and every deletion to
maintain a distinction that is never displayed and cannot be acted upon.

## 3. Proposed design

### 3.1 Conflict resolution replaces versioning

Drop `canonical_name` and `version` as an ingestion concept. On import, when a
document with the same name already exists in the destination folder, ask the
user what to do.

- **One prompt per import, not per file.** The import proceeds; conflicts are
  collected and presented once, as a list, with "overwrite all", "skip all", or
  a per-file choice. A 50-file import with 10 conflicts interrupts the user
  once.
- **Overwrite keeps the document's identity.** The `document_uid` is preserved
  and its content is replaced, so existing links, citations and agent answers
  that reference the document keep resolving, and point at the new content.
  Re-extraction and re-indexing follow, as for any content change.
- **Skip leaves the existing document untouched** and reports the skipped files.

The check becomes one scoped question — "does a document with this name exist in
this folder?" — answerable by an indexed lookup rather than a corpus scan.

### 3.2 Import experience

- **The dialog closes as soon as the files are accepted**, not when the last one
  has been prepared server-side. The user gets the application back immediately.
- **Progress is shown in the existing shared task surface.** The backend already
  streams per-file, per-step progress as NDJSON, and the client already parses
  it; the dialog discards it. A `TaskTray` component with an aggregate progress
  ring already exists and is mounted nowhere. This RFC does not design a new
  activity UI — see §6.
- **Labels are corrected.** The action is importing, not saving. The dialog
  title ("Ajouter un document" / "Upload a document") is singular while the
  dialog accepts many files.

### 3.3 Existing alternate versions

Documents already carrying `version = 1` in production are converted into
ordinary documents with a distinct name. Nothing is deleted, nothing stays
hidden, and the user can then decide for themselves. This is a one-off data
migration with an operator note.

## 4. Alternatives considered

**Keep versioning and build the missing UI.** Rejected: it would add a version
badge, a promote action and a version history to make a mechanism usable that no
one has asked for, while keeping both corpus scans.

**Rename silently on conflict** (`report.pdf` becomes `report (1).pdf` without
asking). Rejected: it is what the current mechanism approximates, and it is the
reason duplicates accumulate unnoticed. The user is the only one who knows
whether a same-named file is a correction or a different document.

**Keep the old document as history on overwrite.** Deferred, not rejected. It is
a richer product, but it reintroduces a version notion to display and manage —
exactly what §3.1 removes. If it is wanted later, it should be designed as
document history, not as an ingestion side effect.

**Block the import on conflict, as today.** Rejected: refusing with an
instruction the product cannot satisfy is the current defect.

## 5. Impact on existing contracts

- `fred_core.documents.document_structures.Identity`: `canonical_name` and
  `version` become unused by ingestion. Whether the fields are removed or
  retained as deprecated is an open question (§7).
- Knowledge Flow ingestion API: the upload routes gain a conflict outcome per
  file, and a way to express the user's decision on a second pass. The exact
  shape is not settled here.
- `MetadataService._promote_alternate_version` disappears with the mechanism it
  serves, removing one of the two corpus scans reported in #2844.
- `docs/swift/design/INGESTION.md` gains the conflict-resolution rule, which it
  has never described.
- Frontend: `DocumentUploadDrawer` stops owning the wait; the shared task
  surface owns progress.

## 6. What this RFC does not own

- **The shared activity surface.** RFC OPS-04 (`TASK-EVENT-STREAM-RFC.md`) owns
  task visibility and presentation, and explicitly requires reusing existing
  components rather than adding one activity UI per feature. This RFC consumes
  that surface; it must not introduce an upload-specific progress panel.
- **Server-side import and deletion latency** beyond removing the scans that the
  versioning mechanism causes. The blocking content-store write is #2370; the
  second full disk copy of every uploaded file and the remaining scan costs are
  #2844.
- **Ingestion queue isolation**, owned by the `isolate-ingestion-extraction-queues`
  OpenSpec change.

## 7. Open questions

1. **How is the user's decision carried back?** A second request replaying the
   conflicted files is the simplest option, but it re-uploads their bytes. An
   alternative is a server-side staging area keyed by an import id. This choice
   determines the API shape and should be settled before any slice is scoped.
2. **Are `canonical_name` and `version` removed or deprecated?** Removing them
   is cleaner and matches the consolidation phase; keeping them costs a stale
   field in a shared contract. Check for external consumers first.
3. **What does overwrite do to an in-flight ingestion** of the document being
   overwritten? Cancelling the running workflow is likely correct, but it
   interacts with the reconciliation rules OPS-04 describes.
4. **Does the conflict check apply across folders or within one?** Today
   versioning is scoped to the destination tag. Keeping that scope is the
   assumption here; it should be confirmed as the intended product rule.

## 8. Next step

Sign-off on §3 and on the open questions in §7. Once §7.1 is settled, the work
splits into OpenSpec changes — conflict resolution, import experience, and the
data migration — each linking its own GitHub issue.
