## 1. Make the name question cheap

- [x] 1.1 Add a Postgres index supporting "does this document name exist in this tag", and an Alembic migration for it, re-parented onto the current `swift` head.
- [x] 1.2 Add a metadata-store query answering that question for a list of names in one round trip, returning the existing `document_uid` per matching name.
- [x] 1.3 Test it against a seeded corpus large enough that a scan would be visibly slower, and record the measured cost. Measured on 5045 documents: the old per-file scan takes 542 ms, so a 20-file import spends 10.8 s answering it; the new query answers all 20 names in 6.8 ms, in one round trip.

## 2. Expose the pre-check

- [x] 2.1 Add the name-check route: destination folder plus a list of names in, conflicting names out. Authorize it exactly like an import into that folder. `POST /documents/name-check` takes several destinations per request, because a dropped directory targets one folder per subdirectory.
- [x] 2.2 Test: names present, names absent, a name present only in another folder, a caller without write access to the folder.
- [x] 2.3 Regenerate the Knowledge Flow OpenAPI and the frontend client in this change.

## 3. Carry the decision on the import

- [x] 3.1 Accept a per-file decision (overwrite or skip) on `/upload-documents` and `/upload-process-documents`, as `conflict_decisions` on the `metadata_json` payload, keyed by file name.
- [x] 3.2 Refuse a conflicting file carrying no decision, with an error naming the file, before anything is written. Refused per file rather than per request, on the stream with status `conflict`; see design.md.
- [x] 3.3 Re-check conflicts at write time; return a newly-conflicting file as a conflict to resolve, not as a failure. One check per request, before the first write; the window still open inside a request needs a unique constraint and belongs to `retire-document-versioning`.
- [x] 3.4 Find every non-UI caller of the upload routes and update it, or confirm there is none. Only `tests/scripts/temporal_ingestion_load_test.py`: documented that a re-run against an already-filled folder now imports nothing.

## 4. Apply the decisions

- [x] 4.1 Skip: import nothing for that file, leave the existing document untouched, report it as skipped and not as failed (status `ignored`).
- [x] 4.2 Overwrite: reuse the existing `document_uid` explicitly, replace the content, drop the previous extraction and vectors, re-index (`IngestionService.adopt_existing_document`).
- [x] 4.3 Charge the quota the size difference, not the full size — reusing the uid makes the existing save path do it; pinned by a test.
- [x] 4.4 Test the interrupted overwrite: content and index must not be left disagreeing. The index is dropped before the new content lands, so an interruption leaves the document unindexed, never wrongly indexed.
- [x] 4.5 Test that a reference to an overwritten document still resolves, and resolves to the new content.

## 5. Ask the user once

- [ ] 5.1 Run the pre-check in `DocumentUploadDrawer` when the selection is complete, before any upload starts.
- [ ] 5.2 Present all conflicts as one list with overwrite-all, skip-all and per-file choice; do not block the non-conflicting files on that decision.
- [ ] 5.3 Surface a conflict returned at write time on the affected document's row, as awaiting a decision rather than as a failure. Do not build a dedicated surface for it: the import panel aggregates row state once it ships.
- [ ] 5.4 Component tests for: no conflict (no prompt at all), some conflicts, all conflicts, a conflict appearing late.

## 6. Verify and close out

- [ ] 6.1 `make code-quality` and `make test` in knowledge-flow-backend and frontend.
- [ ] 6.2 Run `/code-review` on the diff; the overwrite path is correctness-sensitive shared code.
- [ ] 6.3 Migration note covering the refused-without-decision behaviour change.
- [ ] 6.4 Record measured before/after cost of the name check against the seeded corpus.
