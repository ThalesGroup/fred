# RFC — Resource import: explicit conflicts, visible progress

**Status:** two of three slices shipped and archived (2026-09-30) — conflict
resolution and the import panel. What remains open, and all this RFC still
owns, is `retire-document-versioning`: migrating the alternate versions that
already exist and removing the mechanism. §7 lists the questions that slice
still has to settle.

## 1. Problem

Importing documents into a team's Resources is slow, opaque, and ends in a
behaviour nobody can see or act on.

Reported from production: clicking the dialog's save button does nothing
visible for a long time, then the dialog closes and ingestion starts. The dialog
is modal, so the application is unusable throughout. The button reads
"Enregistrer" / "Save" — nothing is being saved; files are being imported.

Behind that sits a fourth problem, invisible to users, which is why this is an
RFC and not a UI ticket.

## 2. What the current versioning mechanism actually does

`IngestionService._apply_versioning` assigns every incoming document a
`canonical_name` and a `version` integer within its destination folder. A second
document with the same name becomes version 1; a third is refused with:

> A draft version already exists for '<name>'. Delete or promote it before
> ingesting another version.

Verified on `swift` at `1bbe40614`:

- **The frontend never renders a document version.** The comment at
  `ingestion_service.py:105` says "UI will use version field to render badge".
  No such badge exists anywhere in `apps/frontend/src`.
- **"Promote" is not an action.** No route, no UI. The error tells the user to
  do something the product does not offer. The only promotion is implicit, in
  `MetadataService._promote_alternate_version`, when the base document is
  deleted.
- **It is undocumented.** `docs/swift/design/INGESTION.md` never mentions
  versioning, canonical names or duplicates.
- **It is the dominant cost on two hot paths.** `_apply_versioning` (once per
  imported file) and `_promote_alternate_version` (once per deleted document)
  both call `get_all_metadata`, which loads the entire `metadata` table,
  deserializes every row into Pydantic and filters in Python. Measured locally:
  6 ms at 45 documents, 36 ms at 545, 355 ms at 5045 — linear in corpus size,
  paid per file. See #2844.

The platform pays a full corpus scan on every import and every deletion to
maintain a distinction nobody can see and nobody can act on.

## 3. Design

### 3.1–3.4 Conflicts, the panel, interruption, wording — shipped

Built and archived. What they do now is the current truth, and it lives in the
capability specs, not here:

- `openspec/specs/document-import-conflicts/spec.md`
- `openspec/specs/document-import-experience/spec.md`

The archived changes carry the reasoning and the task-by-task record:
`openspec/changes/archive/2026-09-30-add-import-conflict-resolution/` and
`.../2026-09-30-revamp-document-import-experience/`.

One design point recorded here was decided against during the build: an import
is **not** surfaced application-wide. The Resources page of the team it belongs
to is its surface; the transfer and its tracking survive navigating away, and
the panel restores the full list on return (developer decision, 2026-09-30).

### 3.5 Existing alternate versions

Documents already carrying `version = 1` in production become ordinary
documents with a distinct name. Nothing is deleted, nothing stays hidden, and
the user can then decide for themselves. One-off data migration, with an
operator note.

### 3.6 What the panel requires of the task lifecycle

The panel is only as truthful as the states it renders. Two guarantees are
requirements of this design, not nice-to-haves:

- **A task must never stay non-terminal forever.** Today a stuck task is not
  cosmetic: a unique partial index treats it as an ingestion still in flight
  (`models/task_models.py:62-70`), so the document can never be re-imported.
  The user can neither watch it finish nor retry it. Showing that faithfully in
  a panel makes the dead end more visible, not less.
- **A failure must say why, in the user's terms.** "Execution failed" is not a
  reason. Section 3.3 promises a readable cause and a retry action; that
  promise is only keepable if the pipeline distinguishes a genuinely unusable
  file from an internal problem that would succeed on a second attempt.

Both are properties of the ingestion task lifecycle, which this RFC does not
own (§6). They are stated here so the panel is not built on top of them
silently.

## 4. Alternatives considered

**Keep versioning and build the missing UI.** Rejected: it would add a version
badge, a promote action and a version history to make usable a mechanism nobody
asked for, while keeping both corpus scans.

**Rename silently on conflict.** Rejected: it is what the current mechanism
approximates, and it is why duplicates accumulate unnoticed. Only the user knows
whether a same-named file is a correction or a different document.

**Check conflicts during the upload instead of before it.** Rejected: the files
the user chooses to overwrite would have to be re-sent in full, which is slow
and doubles the transfer on large files. Holding them server-side avoids the
re-send but requires storing and expiring abandoned uploads.

**Keep the old document as history on overwrite.** Deferred, not rejected. It is
a richer product, but it reintroduces a version notion to display and manage —
exactly what §3.1 removes. If wanted later, design it as document history, not
as an ingestion side effect.

**Show the whole team's imports in the panel.** Rejected for now: it avoids
duplicate work but fills the panel with noise on an active team. Folder rows
already carry team activity.

## 5. Impact on existing contracts

- `fred_core.documents.document_structures.Identity`: `canonical_name` and
  `version` are removed, and the generated frontend client is regenerated in
  the same change (§7).
- Knowledge Flow ingestion API: a new name-check endpoint for the destination
  folder, and a per-file decision carried on the upload request.
- `MetadataService._promote_alternate_version` disappears with the mechanism it
  serves, removing one of the two corpus scans reported in #2844.
- `docs/swift/design/INGESTION.md` gains the conflict rule, which it has never
  described.
- Frontend: `DocumentUploadDrawer` stops owning the wait; `TaskTray` is mounted
  and owns progress.

## 6. What this RFC does not own

- **The shared task surface itself.** RFC OPS-04
  (`TASK-EVENT-STREAM-RFC.md`) owns task visibility and presentation and
  requires reusing existing components rather than adding one activity UI per
  feature. §3.2 consumes that surface and states what import needs from it.
- **Cancelling an analysis in flight.** The underlying capability is being built
  by the `isolate-ingestion-extraction-queues` OpenSpec change; no user-facing
  route exists today. §3.3 deliberately stops at the upload stage.
- **Server-side latency** beyond the scans the versioning mechanism causes. The
  blocking content-store write is #2370; the remaining scan costs are #2844.
  Two further findings are not filed anywhere yet — see §8.
- **The ingestion task lifecycle.** Stuck tasks and misclassified failures are a
  distinct mechanism with its own defects, agreed (2026-09-29) as the piece of
  work to take up immediately after this one. Bundling it here would make both
  unreviewable. §3.6 states only what the import experience requires of it.

## 7. Open questions

Two earlier questions are now settled (2026-09-29).

**`canonical_name` and `version` are removed, not deprecated.** They are confined
to `ingestion_service.py`, `metadata/service.py` and `document_structures.py`,
and no capability, CLI or export path consumes them. They are exposed in the
generated frontend client (`knowledgeFlowOpenApi.ts:2940-2942`), so that client
must be regenerated in the same change.

**The conflict check stays scoped to the destination folder**, with the
cross-folder consequence recorded in §3.1.

Still open:

1. **What does overwrite do to an in-flight ingestion of the same document?**
   Cancelling the running workflow is likely correct, but it depends on the
   cancellation capability referenced in §6 and on the reconciliation rules
   OPS-04 describes.
2. ~~How long do finished entries stay in the panel?~~ Settled while building
   the panel (2026-09-30): a file that succeeded says so and then leaves the
   list on its own after three seconds, without being acknowledged — the
   document is in the table by then. Only a failure or an unanswered question
   waits for the user. The task itself keeps its own eviction window in the
   store, which the documents table and the task tray both read.
## 8. Unfiled findings on import latency

Surfaced while mapping this path, on the same code the conflict work touches.
Neither has an issue yet; both are independent of the design above and should be
filed rather than folded in.

- **Every uploaded file is read twice to compute two fingerprints, and one of
  them is never used.** `_probe_file_info` computes sha256 and md5 in two
  separate full passes (`base_input_processor.py:117-118`). `md5` is declared on
  the metadata model (`document_structures.py:257`) and read nowhere in the
  repository. Dropping it removes a full read per file; the remaining hash can
  be computed in one pass rather than two.
- **Every uploaded file is copied on disk one more time than necessary, on the
  event loop.** The upload is already spooled to disk by the framework, then
  `_preload_uploaded_files` copies it again
  (`ingestion_controller.py:466-473` → `:294-317`). The copy is synchronous, so
  it stalls the whole Knowledge Flow API — including the sibling batches of the
  same import — for its duration.

Both are the same shape as #2370: work done on the event loop that blocks every
other request while it runs. That shape, not the individual call, is what makes
the import feel slow from the browser.

## 9. Next step

`retire-document-versioning` (`openspec/changes/retire-document-versioning/`,
19 tasks, not started). It depends on conflict resolution, which has shipped,
and it is the one slice carrying a data migration: existing alternate versions
have to be migrated before `canonical_name` and `version` can go.

The two questions in §7 are both its to settle. The two latency findings in §8
are still unfiled and are independent of it.
