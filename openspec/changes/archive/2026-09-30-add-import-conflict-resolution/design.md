## Context

Today `IngestionService._apply_versioning` answers "does this name already
exist here?" by calling `get_all_metadata`, which loads the entire `metadata`
table, builds a Pydantic model per row and filters in Python — once per imported
file. Measured: 6 ms at 45 documents, 36 ms at 545, 355 ms at 5045 (see #2844).
The question is about one folder; the cost is the whole corpus.

This change replaces that with a scoped question asked at the right moment. It
does not remove the versioning fields — that is `retire-document-versioning`,
which depends on this one.

## Goals / Non-Goals

**Goals**

- Detect conflicts before any byte is uploaded, so the user answers in well
  under a second and nothing is transmitted twice or for nothing.
- Make overwrite safe: the existing document keeps its identity.
- Make the name question cheap, by index rather than by scan.

**Non-Goals**

- Removing `canonical_name` / `version` and `_promote_alternate_version`.
- The import panel, progress and wording (`revamp-document-import-experience`).
- The remaining import latency: the blocking content-store write (#2370), the
  redundant disk copy and the double hashing (RFC §8).

## Decisions

### Check names before upload rather than during

The client sends names only and gets conflicts back. The alternatives both cost
more: resolving conflicts mid-upload forces the overwritten files to be re-sent
in full, and holding them server-side means storing and expiring uploads the
user may never decide on. Names are cheap, and the answer arrives before the
transfer starts.

The trade-off is that the answer can go stale, so the write path re-checks.
Correctness lives in the write-time check; the pre-check only spares the user a
pointless upload.

### The two questions live in two different places

The pre-check question is asked while the user is still in the import dialog,
before any transfer begins — it belongs there, and needs nothing else.

The write-time conflict surfaces after the dialog has closed. Answering it is
the import panel's job, not the table's: the panel is where an import's files
and their outcomes live, and where actions on them belong. A document row may
carry an indicator that something needs attention and open the panel on click,
but the decision is never taken from the row.

Until the panel ships, this change reports a late conflict as a notice saying
how many files need importing again — enough not to lose the information, and
deliberately not a second, throwaway surface for resolving it. That is the same
exposure as the transient notifications used today, so it is not a regression,
and the panel closes it.

### Overwrite reuses the existing `document_uid` deliberately

`_generate_file_unique_id` returns a random UUID per ingestion
(`base_input_processor.py:61-67`). It was made random precisely because a
deterministic name-derived id let "later ingests overwrite earlier versions"
silently. This change does not revert that: an overwrite happens only because
the user asked for it on a named file. But it does mean the overwrite path must
pass the existing uid in explicitly; nothing will do it by default.

Preserving the uid is what keeps citations and links resolving, which is the
whole reason to prefer overwrite over delete-then-create.

### The conflict question is scoped to the destination folder

That matches how users reason about their documents. The accepted consequence:
the same file imported into two folders becomes two independent documents,
charged and analysed twice. That is often legitimate, so it must not raise a
second blocking prompt. A non-blocking mention ("this file already exists in
another folder") is in scope for the panel change, not here.

### One decision per import, taken before the first write

The plan — overwrite, skip, or still unanswered — is resolved once per request,
from one query covering every name in the batch, before any file is touched.
Re-asking per file would cost a query each and buy nothing: a decision taken at
file 20 is as stale as one taken at file 1.

What that leaves open: a name taken *during* the request is still imported as a
new document. Closing that needs a unique constraint on (folder, name), which
cannot exist while alternate versions deliberately let two documents share a
display name. It belongs to `retire-document-versioning`, which can add it.

### An unanswered conflict stops its own file, not the batch

A file that conflicts and carries no decision is reported on the stream as
awaiting an answer, and the rest of the import proceeds. Refusing the whole
request would punish the files that are fine, and the common cause of a late
conflict — a teammate importing the same name meanwhile — affects one file, not
the batch.

That is a deliberate reading of "the request is refused": the *file* is refused,
nothing is created, modified or deleted for it, and the error names it. The
status is `conflict`, distinct from `failed`: the user has something to answer,
not something that went wrong.

### The decision travels outside the typed contract

`IngestionInput` arrives as a `metadata_json` form field, so it never reaches
the OpenAPI schema and the generated client cannot type it. The client builds
that object by hand today. Accepted as-is rather than reshaping the upload
routes in this change; the field is validated server-side by Pydantic, so a
malformed decision is rejected rather than ignored.

### Replacing drops the index first and the bytes last

The order is: point the metadata at the existing uid, mark the row as having
nothing processed, drop that document's vectors and tabular artifacts, write
the new content over the old, save the row.

Dropping the index first is what makes an interrupted replacement safe. Writing
the content first would leave the previous index answering for content that is
no longer the one it describes — the exact disagreement to avoid. This way an
interruption leaves the document unindexed, never wrongly indexed, and never
without content.

Clearing the row's stages *before* the purge, rather than only in the metadata
saved at the end, is the other half of that. Otherwise a failure between the
purge and the final save leaves a row claiming vectors the document no longer
has: silently unsearchable, with nothing saying so and nothing to retry.

The stage reset goes through the conditional update, so it doubles as the fence
against a document deleted since the import was planned: if the row is gone,
nothing is purged and the file imports as a new document.

Charging the difference needs no new code in the save path: it already loads the
previous metadata by uid and moves the quota by `new_size - old_size`. Reusing
the uid is what makes that fall out. The *admission* check is separate and did
need it — see below.

### Replacing is not moving

A document can sit in several libraries. The metadata a fresh extraction
produces carries only the folder being imported into, so adopting it wholesale
would quietly take the document out of every other library it was in, releasing
their quota and leaving their ReBAC grants behind. The tags are unioned: the
document keeps where it was, plus where it is being imported.

### What an import costs is not what it carries

The admission check summed every uploaded file at full size. Two ways that is
wrong once a plan exists: a skipped or unanswered file is never stored, and a
file replacing a document costs the difference. A team near its limit was
refused outright for a replacement that frees space — the case where replacing
matters most. The check now takes the plan, ignores what will not be written,
and credits what will be replaced.

The client-declared precheck cannot do that arithmetic: it does not know the
existing sizes. Rather than teach it, a denial is no longer final when the
destination already holds one of the names — the drawer defers to the upload
endpoint, which nets it out for real. Scoped to the destination folder alone, so
no folder is created to answer a question that may end in a refusal.

### One name, one file, one decision

Two files of one import cannot land in the same folder under the same name. A
decision keyed by name would mean two things at once, and "replace" would let
one file take the other's place unremarked. The dialog refuses the selection and
names the collision, instead of importing something the user did not ask for.
Previously the second file became an alternate version of the first, which is
the mechanism this whole change exists to retire.

### A name held twice cannot be overwritten

While alternate versions exist, a folder can hold two documents under one
display name, and "the existing document" then names neither. That file is
refused with an error saying so, rather than overwriting an arbitrary one. The
case disappears with `retire-document-versioning`.

### An index, not a scan

The `metadata` table indexes `document_uid`, `tag_ids` (GIN) and `source_tag`.
Nothing supports "name within tag". The check needs an index covering the
document name alongside the tag, or the change simply moves the scan.

## Risks / Trade-offs

- **The overwrite path is the risky one.** It replaces content on a live
  document: the old extraction and vectors must go, the new must land, and the
  quota delta is a difference rather than an addition. A partial overwrite
  leaves a document whose content and index disagree. This needs explicit
  ordering and a test for the interrupted case.
- **A conflicting file with no decision is refused.** This is a deliberate
  behaviour change: the old path silently versioned. Any non-UI caller of the
  upload routes must be found and updated, or it starts receiving errors.
- **Concurrent overwrite of the same document** by two users is undefined here.
  Last writer wins is acceptable for a first slice, but it should be a
  conscious choice rather than an accident.

## Migration Plan

None in this change: existing documents are untouched, and the versioning
fields keep being written. The data migration belongs to
`retire-document-versioning`.

## Open Questions

- What does overwrite do to an ingestion of that same document still in flight?
  Cancelling it is likely correct but depends on a cancellation capability that
  does not exist yet (RFC §7).
