# RFC — Resource import: explicit conflicts, visible progress

**Status:** all three slices built (2026-09-30). This RFC is trimmed to the two
things still genuinely open; everything it proposed and that shipped is current
truth elsewhere, listed below. Archive this file once both have left it.

## Where the shipped design lives now

| What | Where |
| --- | --- |
| Same-name conflicts, one decision per name | `openspec/specs/document-import-conflicts/spec.md`; reasoning in `openspec/changes/archive/2026-09-30-add-import-conflict-resolution/` |
| The import panel, interruption, wording | `openspec/specs/document-import-experience/spec.md`; reasoning in `openspec/changes/archive/2026-09-30-revamp-document-import-experience/` |
| Retiring document versioning, and the migration that renamed the alternates already in production | `openspec/changes/retire-document-versioning/` until it is archived; the duplicate rule it leaves behind is in [INGESTION.md](../design/INGESTION.md) |
| Operator-facing effect of that migration | `docs/swift/ops/migrations/retire-document-versioning.md` |

One design point recorded only here, because it was decided against during the
build: an import is **not** surfaced application-wide. The Resources page of the
team it belongs to is its surface; the transfer and its tracking survive
navigating away, and the panel restores the full list on return (developer
decision, 2026-09-30).

## 1. Open question — replacing a document whose ingestion is still running

Cancelling the running workflow is likely correct, but it depends on a
user-facing cancel route that does not exist: the underlying capability is being
built by the `isolate-ingestion-extraction-queues` OpenSpec change, and task
visibility itself belongs to `TASK-EVENT-STREAM-RFC.md` (OPS-04). Until that
lands, replacing a document mid-ingestion is undefined rather than decided.

Renaming, by contrast, needed no answer: a task addresses its document by
`TaskTarget.id`, the `document_uid`, so the migration's renames reached no task.
Only a task's `label` keeps the old name — the same display snapshot a citation
keeps.

## 2. Unfiled findings on import latency

Surfaced while mapping this path. Neither has an issue yet; both are independent
of everything above and should be filed rather than folded into anything.

- **Every uploaded file is read twice to compute two fingerprints, and one of
  them is never used.** `_probe_file_info` computes sha256 and md5 in two
  separate full passes (`base_input_processor.py`). `md5` is declared on the
  metadata model and read nowhere in the repository. Dropping it removes a full
  read per file; the remaining hash can be computed in one pass rather than two.
- **Every uploaded file is copied on disk one more time than necessary, on the
  event loop.** The upload is already spooled to disk by the framework, then
  `_preload_uploaded_files` copies it again. The copy is synchronous, so it
  stalls the whole Knowledge Flow API — including the sibling batches of the same
  import — for its duration.

Both are the same shape as #2370: work done on the event loop that blocks every
other request while it runs. That shape, not the individual call, is what makes
the import feel slow from the browser.

## 3. What this RFC never owned

- **The shared task surface itself** — `TASK-EVENT-STREAM-RFC.md` (OPS-04) owns
  task visibility and presentation, and requires reusing existing components
  rather than adding one activity UI per feature.
- **The ingestion task lifecycle.** Stuck tasks and misclassified failures are a
  distinct mechanism with its own defects, agreed (2026-09-29) as the work to
  take up immediately after this.
- **Server-side latency** beyond the scans the versioning mechanism caused: the
  blocking content-store write is #2370, the remaining deletion costs #2844, the
  non-PostgreSQL name lookup #2860.
