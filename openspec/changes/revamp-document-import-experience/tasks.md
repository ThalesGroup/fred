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

- [ ] 5.1 Carry a file the server returned as `conflict` (status distinct from `failed`, see `add-import-conflict-resolution`) as awaiting a decision, never as an error.
- [ ] 5.2 Offer replace-or-skip on that item in the panel, and apply it by re-sending the file with `conflict_decisions`; the interactions live in the panel, not in the document table.
- [ ] 5.3 On a document row, at most an indicator that something needs attention, opening the panel on click. The row never carries the decision itself.
- [ ] 5.4 Offer the decision only while the browser still holds the file; otherwise say the file must be imported again, as for a retry.
- [ ] 5.5 Test: a conflict raised at write time is listed as a question, is answerable from the panel, and leaves the other files of the import untouched.

## 6. Interruption and cancellation

- [ ] 6.1 On return after an interruption, name the files that were not received and offer to finish the import for those only.
- [ ] 6.2 Allow cancelling files not yet transferred; leave received files untouched.
- [ ] 6.3 Test: tab closed mid-import, then reopened — received files unaffected, missing files named.

## 7. The dialog itself

- [ ] 7.1 Replace the save wording with "Importer {count} fichiers" / "Import {count} files", including the plural rules.
- [ ] 7.2 Make the dialog title plural in fr and en.
- [ ] 7.3 Drop the now-unused "saving" strings.
- [ ] 7.4 Widen the dialog a little.
- [ ] 7.5 Put the ingestion mode and the processing profile on one row; they get narrower, but the option labels must stay readable in both dropdowns.

## 8. Help Center

- [ ] 8.1 Add the fr and en Help Center pages for the import panel in this change, per the repo rule that a user-visible feature needing onboarding ships its pages with it.

## 9. Verify and close out

- [ ] 9.1 `make code-quality` and `make test` in the frontend.
- [ ] 9.2 Run `/code-review` on the diff.
- [ ] 9.3 Migration note: no operator action, user-visible change.
- [ ] 9.4 Record which lifecycle defects were observed while testing, as input to the lifecycle work, without fixing them here.
