Groups are ordered by dependency and each is meant to land as its own commit.
Group 6 stays separate on purpose: a wording decision must not be reviewed
inside an authorization change.

## 1. Storing the mark (knowledge-flow)

- [x] 1.1 Add the optional qualified owner reference to the folder model, documented as absent-means-written-by-people; verify the model's own tests still pass and a folder without it serializes exactly as before
- [x] 1.2 Verify no schema change is needed: a folder round-trips through the store with the mark set, and a stored folder predating the field reads back with it absent
- [x] 1.3 Add the service-only route that records the mark against a library, alongside the existing service-only library routes; verify a service identity succeeds and a person's token is refused
- [x] 1.4 Expose the field on the folder read path so it travels in the payload the frontend already fetches; verify by reading a marked folder back through the API

## 2. The guard (knowledge-flow)

- [x] 2.1 Add root-ancestor resolution: given any folder, report whether its root carries a mark, short-circuiting when the folder is itself the root; verify with a unit test over a folder nested several levels deep and one at the root
- [x] 2.2 Guard `update_tag_for_user`, which is the single person-facing path for adding a document to a folder, removing one from it, and renaming or moving it; verify a person is refused naming the base, the folder keeps its recorded name, and the service identity succeeds
- [x] 2.3 Guard `create_tag_for_user` on its resolved parent, so a folder cannot be created beneath a marked one; verify the same pair
- [x] 2.4 Guard the ingestion upload routes, which authorize per target folder; verify an upload targeting a marked folder is refused and creates no document
- [x] 2.5 Map the refusal to its own status on the app, distinct from being unauthorized; verify the response names the base
- [x] 2.6 Assert the guard runs after the existing authorization check: verify a caller with no right is refused for lacking the right, not for the folder being marked
- [x] 2.7 Assert deletion is deliberately not guarded, and that its cascade — which reaches documents through the item service rather than through `update_tag_for_user` — is unaffected; verify a person holding the delete right still deletes a marked folder with its documents

## 3. The pod declares its own library (fred-sdk)

- [x] 3.1 Send the declaration once per run, from the SDK runtime between fetching the run context and invoking the handler, so no author writes it; verify the call carries the instance and the library from that context
- [x] 3.2 Send it only when the pod is configured to write documents into Fred; verify a pod keeping its own store declares nothing
- [x] 3.3 Let a failed declaration log and the run proceed; verify a refused or unreachable call does not fail synchronization, and that a conflicting machine is reported loudly enough to be noticed

## 4. Libraries created before this change

- [x] 4.1 Verify no backfill is needed: an unmarked library is marked by its own next run, and the declaration is idempotent from the second run onwards

## 5. Listing nested documents (fred-core, knowledge-flow, frontend)

- [x] 5.1 Extend the document store's folder listing to take a set of folders rather than one, keeping paging and total behaviour; verify the total counts the same set that can be paged through, and that a document in exactly one folder is never counted twice
- [x] 5.2 Resolve a library's descendant folders with one prefix read on the tag store; verify against a tree several levels deep
- [x] 5.3 Serve the library document listing from those two reads; verify a library whose documents all sit in nested folders is no longer reported as holding none
- [x] 5.4 Regenerate the knowledge-flow client (`make update-knowledge-flow-api` in `apps/frontend`) and commit it alongside; verify the generated types carry the new field and the listing shape
- [ ] 5.5 Point the Knowledge Base Documents page at the full listing; verify its tests cover a library with nested documents and assert the empty state is not shown

## 6. Resources reflects the partition (frontend)

- [ ] 6.1 Badge a marked folder in the Resources document workspace from the field already present in the folder payload; verify no additional request is made
- [ ] 6.2 Hide the write actions the backend now refuses — upload, rename, move, create folder inside — leaving deletion offered; verify with a test over a marked and an unmarked folder
- [ ] 6.3 Name the base in the delete confirmation for a marked folder; verify the confirmation text in a test

## 7. The folder-name field (frontend, separate commit)

- [ ] 7.1 Relabel the create form's name field to the folder it creates, with one line of help saying where it lands and that the source type is already shown; update both locales and verify no key is left untranslated
- [ ] 7.2 Verify by reading the form that nothing invites restating the source type, and that the placeholder reads as subject matter

## 8. Verification and close-out

- [ ] 8.1 Run `make code-quality` and `make test` in each touched project root and fix everything before proceeding
- [ ] 8.2 Run the `fred-performance-reviewer` skill over the diff — the guard sits on the ingestion upload path, which runs per request under concurrent load
- [ ] 8.3 Run `/code-review` on the diff at default effort or higher, and address what it finds
- [ ] 8.4 Hand the frontend to the developer for a manual browser pass before the UI commits are considered done
- [ ] 8.5 Update the component UX document with the Resources badge and the withheld actions; verify the entry names both
- [ ] 8.6 Close GitHub issue #2687 with what shipped, and state explicitly that KPI/log attribution and per-instance identity were left out
