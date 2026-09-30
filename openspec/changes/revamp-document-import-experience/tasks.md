## 1. Give the application back

- [x] 1.1 Close the dialog as soon as the selection is accepted, instead of awaiting every batch outcome. What must be settled first (quota, folders, the name question) stays awaited; the transfer does not.
- [x] 1.2 Keep the upload running after the dialog unmounts, and make sure its per-file outcomes still reach the panel — `runImport` is detached and holds only the store and the toast provider, both of which outlive the dialog.
- [x] 1.3 Test: confirming an import of 50 files returns control without a perceptible wait — the dialog is closed while the transfer is deliberately held open, every file still reaches the panel afterwards, and the folder refreshes only at the end.

## 2. Mount the panel

- [x] 2.1 Mount the panel beside the documents card on the resources page, as a dedicated rail that widens in place into the panel — one element with two widths, the same button opening and closing it, carrying the card's surface, radius and full height. `TaskTray` was not reused: it is a floating popover anchored to a trigger, a different object. It also opens itself when an import hands off (`importPanelOpenRequested`), so the work is visible instead of hidden behind a closed rail.
- [x] 2.2 Audit of what the panel rendered for an import before section 3, and what was missing:
  - A file appeared only once the server had accepted it and named a task. Batches run a few at a time, so on a large import most files were invisible for most of the wait.
  - The card showed name, state badge, progress bar and `step`. `stepLabel` translated only `uploading|processing|indexing|done`, while the task feed also carries `listed`, `vectorized` and `skip` — those reached the page as raw English identifiers.
  - Nothing distinguished the transfer from the analysis, so "how far along is this file" had no answer.
- [x] 2.3 Test: an import started on Resources is still listed after the panel unmounts and remounts (`ImportPanel.test.tsx`). Surviving a reload is the rehydration path, which re-registers non-terminal server tasks; a transfer cut off by the reload is section 6's subject, not this one's.

## 3. Make the two stages legible

- [x] 3.1 `ImportStage` on the task view model, set by `uploadStarted` (the browser's half, no server task yet) and `uploadHandedOff` (the server named the task). Every file is listed before a byte moves. `stepLabel` names the stage rather than printing a pipeline identifier, and the steps the feed actually emits are all translated now.
- [x] 3.2 Handing off resets the entry to `pending`: only the ingestion task's own `succeeded` settles it. The transfer's `finished` line settles a file only when it never got a task — upload-only mode, or one the server skipped.
- [x] 3.3 Test: `taskSlice.test.ts` "the two stages of an import" — a transferred file is `analysis`/`pending`, the end-of-transfer line does not settle it, and only the task event does.

## 4. Make failures survivable

- [x] 4.1 A failed entry stays listed until retried or dismissed (`selectVisibleTasks` keeps unacknowledged failures indefinitely) and carries a retry. The import engine moved out of the dialog into `features/imports/importRun.ts` — the dialog is gone long before the transfer is, and the panel, not the dialog, is where a retry is asked for.
- [x] 4.2 `importFailure` maps the sentences the backend actually writes (quota guard, `_wf_file_terminal_event_args`) onto one line the reader can act on, keeping the original as hover detail. `Execution failed` and `No failure details were reported` are treated as no cause at all, because that is what they mean.
- [x] 4.3 The file behind a failed entry is held in a module-level vault — a `File` handle, not its bytes — released as soon as it is no longer ours to send, and gone on reload. No held file, no retry button: the panel says the file has to be picked again instead.
- [x] 4.4 Test: `ImportPanel.failures.test.tsx` — six cases over the real `TaskCard`, including the failure surviving an unmount/remount and its neighbour in the same batch being untouched.

## 5. Conflicts awaiting a decision

- [x] 5.1 A third `ImportStage`, `decision`: `pending`, no error, holding the name and the folder it clashes in. The panel opens itself when one arrives — a question no one sees is not one. The end-of-run toast that used to say "import it again to choose what to do" is gone, along with its strings: the panel is the report now.
- [x] 5.2 Replace and Skip under the entry in the panel. `resolveConflict` sends the same file to the same folder with `conflict_decisions` attached for Replace, and sends nothing at all for Skip — the point of asking is not to transfer bytes the answer makes useless.
- [x] 5.3 A warning marker after the contested document's name, opening the panel on click. It carries no decision. Matched on (folder, name) from the store, so a same-named document in another folder is untouched.
- [x] 5.4 Same rule as a retry: no held file, no Replace and no Skip — the panel says the import has to be started again.
- [x] 5.5 Test: `ImportPanel.conflicts.test.tsx` (six cases, including Replace's request metadata and Skip sending nothing) and `DocumentWorkspace.conflictMarker.test.tsx` (the row points, and offers nothing).

## 6. Interruption and cancellation

- [x] 6.1 `unfinishedImports` writes the names and where they were headed to `localStorage` before the first byte moves, and strikes each one off as it gets there. On return the panel names whatever is still listed — minus anything it is already following, since coming back to the page re-reads the record. The offer is `resumeUnfinishedImports`: the user picks the files again (the browser cannot reopen what it no longer holds), and only the missing ones are sent, to the folder they were headed for, with the mode and profile they were being sent with. Anything else picked is left alone.
- [x] 6.2 `canCancelImport` is true only while a file's request has not left — batches go four at a time, so on a large import most files are still queued. `cancelImport` takes it back and `sendBatch` filters it out; a batch emptied that way is never sent. A file already on the wire is the server's and is not offered.
- [x] 6.3 Test: `ImportPanel.interruption.test.tsx` — six cases, including the received file being struck off while the lost one is named, resuming sending only the missing file with its original destination and mode, and cancelling a queued file without touching the four in flight.

## 7. The dialog itself

- [x] 7.1 The action button says what it does and to how many files, with the plural forms in both languages. Nothing picked yet: just "Importer" / "Import", rather than a count of zero.
- [x] 7.2 "Ajouter des documents" / "Add documents" — the dialog has taken several files at a time for a long time.
- [x] 7.3 `save` and `saving` are gone. There was nothing to say while loading either: the button is disabled, and the dialog now closes as soon as the checks pass.
- [x] 7.4 560px instead of 480px.
- [x] 7.5 Mode and profile share a row. At 560px each is about 256px wide, which the longest option label ("Importer et traiter", "Upload & process") clears comfortably.

## 8. Help Center

- [ ] 8.1 Add the fr and en Help Center pages for the import panel in this change, per the repo rule that a user-visible feature needing onboarding ships its pages with it.

## 9. Verify and close out

- [ ] 9.1 `make code-quality` and `make test` in the frontend.
- [ ] 9.2 Run `/code-review` on the diff.
- [ ] 9.3 Migration note: no operator action, user-visible change.
- [ ] 9.4 Record which lifecycle defects were observed while testing, as input to the lifecycle work, without fixing them here.
