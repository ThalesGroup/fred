# RFC — Resource import: explicit conflicts, visible progress

**Status:** all three slices built (2026-09-30) — conflict resolution, the
import panel, and retiring document versioning. Everything this RFC proposed
now lives in the capability specs and in
[INGESTION.md](../design/INGESTION.md); what is left below is one design
question that is still genuinely open (§7) and two latency findings that still
need issues of their own (§8). Archive this RFC once both have left it.

## 1. Problem

Importing documents into a team's Resources is slow, opaque, and ends in a
behaviour nobody can see or act on.

Reported from production: clicking the dialog's save button does nothing
visible for a long time, then the dialog closes and ingestion starts. The dialog
is modal, so the application is unusable throughout. The button reads
"Enregistrer" / "Save" — nothing is being saved; files are being imported.

Behind that sits a fourth problem, invisible to users, which is why this is an
RFC and not a UI ticket.

## 2. The versioning mechanism, and why it went

`_apply_versioning` gave every incoming document a `canonical_name` and a
`version` within its folder; a second document of that name became version 1, a
third was refused outright. Nothing rendered the distinction, "promote" was not
an action anywhere in the product, and both halves of the mechanism scanned the
whole `metadata` table — 355 ms per call at 5045 documents, once per imported
file and once per deleted document (#2844).

It is gone, along with `canonical_name` and `version`. What replaced it is
current truth and lives in [INGESTION.md](../design/INGESTION.md) §"When a
folder already holds that name"; the build record is
`openspec/changes/archive/*-retire-document-versioning/`.

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

### 3.5 Existing alternate versions — shipped

Migration `02d556a6f182` renamed each one to `report (1).pdf`, deleting nothing.
Operator note: `docs/swift/ops/migrations/retire-document-versioning.md`.

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

All shipped, and now the current contract rather than a proposal:

- `Identity` lost `canonical_name` and `version`; the generated frontend client
  was regenerated with them.
- Knowledge Flow ingestion API gained a name-check endpoint for the destination
  folder and a per-file decision on the upload request.
- `MetadataService._promote_alternate_version` went with the mechanism it
  served, removing one of the two corpus scans reported in #2844 — which #2844
  itself is not closed by, the rest of its cost being untouched.
- `docs/swift/design/INGESTION.md` now describes the duplicate rule.
- Frontend: `DocumentUploadDrawer` no longer owns the wait; `TaskTray` is
  mounted and owns progress.

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

## 7. Open question

One, and it is not the versioning slice's — that slice is built.

**What does overwrite do to an in-flight ingestion of the same document?**
Cancelling the running workflow is likely correct, but it depends on the
cancellation capability referenced in §6 and on the reconciliation rules OPS-04
describes. Until that exists, replacing a document whose ingestion is still
running is undefined rather than decided.

Renaming, by contrast, is settled and needed no cancellation: a task addresses
its document by `TaskTarget.id`, the `document_uid`, so the migration's renames
reach no task. Only a task's `label` keeps the old name, the same display
snapshot a citation keeps.

Settled earlier and recorded where they belong now: `canonical_name`/`version`
removal (§5), the conflict check's scope (§3.1), and how long a finished entry
stays in the panel (three seconds, unacknowledged — in the panel's capability
spec).
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

Nothing left to build here. Two things have to leave this RFC before it can be
archived: the open question in §7 needs the cancellation capability it waits on,
and the two findings in §8 need issues of their own.
