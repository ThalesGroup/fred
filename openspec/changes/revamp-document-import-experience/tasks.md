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

## 5. Interruption and cancellation

- [ ] 5.1 On return after an interruption, name the files that were not received and offer to finish the import for those only.
- [ ] 5.2 Allow cancelling files not yet transferred; leave received files untouched.
- [ ] 5.3 Test: tab closed mid-import, then reopened — received files unaffected, missing files named.

## 6. Wording

- [ ] 6.1 Replace the save wording with "Importer {count} fichiers" / "Import {count} files", including the plural rules.
- [ ] 6.2 Make the dialog title plural in fr and en.
- [ ] 6.3 Drop the now-unused "saving" strings.

## 7. Help Center

- [ ] 7.1 Add the fr and en Help Center pages for the import panel in this change, per the repo rule that a user-visible feature needing onboarding ships its pages with it.

## 8. Verify and close out

- [ ] 8.1 `make code-quality` and `make test` in the frontend.
- [ ] 8.2 Run `/code-review` on the diff.
- [ ] 8.3 Migration note: no operator action, user-visible change.
- [ ] 8.4 Record which lifecycle defects were observed while testing, as input to the lifecycle work, without fixing them here.
