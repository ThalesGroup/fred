## 1. Give the application back

- [ ] 1.1 Close the dialog as soon as the selection is accepted, instead of awaiting every batch outcome.
- [ ] 1.2 Keep the upload running after the dialog unmounts, and make sure its per-file outcomes still reach the panel.
- [ ] 1.3 Test: confirming an import of 50 files returns control without a perceptible wait.

## 2. Mount the panel

- [ ] 2.1 Mount `TaskTray` in the main layout so it is reachable from every page.
- [ ] 2.2 Check what it renders for an import task today, and list what is missing for the two stages.
- [ ] 2.3 Test: an import started on Resources stays visible after navigating away and after a reload.

## 3. Make the two stages legible

- [ ] 3.1 Carry upload and analysis as distinct, named states per file, from the existing progress stream to the panel.
- [ ] 3.2 Derive "ready" from the event that actually makes the document usable, not from the end of the upload.
- [ ] 3.3 Test: a file transferred but still being analysed is shown as being analysed, never as ready.

## 4. Make failures survivable

- [ ] 4.1 Keep a failed file listed with its cause and a retry action until retried or dismissed.
- [ ] 4.2 Map backend failure causes onto text a non-technical reader understands; where no cause is available, say so honestly rather than inventing one.
- [ ] 4.3 Offer retry only when the browser still holds the file; otherwise ask for re-selection.
- [ ] 4.4 Test: a failure is still listed after navigating away and back; the other files are unaffected.

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

## 7. Wording

- [ ] 7.1 Replace the save wording with "Importer {count} fichiers" / "Import {count} files", including the plural rules.
- [ ] 7.2 Make the dialog title plural in fr and en.
- [ ] 7.3 Drop the now-unused "saving" strings.

## 8. Help Center

- [ ] 8.1 Add the fr and en Help Center pages for the import panel in this change, per the repo rule that a user-visible feature needing onboarding ships its pages with it.

## 9. Verify and close out

- [ ] 9.1 `make code-quality` and `make test` in the frontend.
- [ ] 9.2 Run `/code-review` on the diff.
- [ ] 9.3 Migration note: no operator action, user-visible change.
- [ ] 9.4 Record which lifecycle defects were observed while testing, as input to the lifecycle work, without fixing them here.
