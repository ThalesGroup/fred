## 1. Retire the corpus-manager surface

- [x] 1.1 Remove the `/corpus/*` controller, service and dedicated tests; verify no corpus-manager route remains in the live OpenAPI while `/documents/tree` and `/fs` remain.
- [x] 1.2 Remove dedicated revectorize and repair Temporal workflow/activities and registrations while retaining ordinary ingestion; verify scheduler tests and source search find no dead imports or registrations.

## 2. Reconcile consumers and documentation

- [x] 2.1 Remove the repair-only shared task result and UI display, regenerate both frontend API clients, and remove endpoint-matrix and validation cases for the deleted routes; verify frontend typecheck and authorization matrix tests.
- [x] 2.2 Update active contract documentation and migration note for the breaking API removal and worker drain; verify a current-doc search has no claim that `/corpus/*` remains supported.

## 3. Verify and close out

- [x] 3.1 Run affected backend, capability and root quality checks; verify `list_document_tree`, PPT Filler and independent `/fs` consumers remain covered.
- [x] 3.2 Review the full branch diff against `swift`, obtain independent read-only review, and disposition supported findings in the PR.
- [x] 3.3 Sync the final delta spec, validate it, archive this change, and update the draft PR and issue with final scope and verification.
