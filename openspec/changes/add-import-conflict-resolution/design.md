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
