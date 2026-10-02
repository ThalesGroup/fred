## 1. Confirm the audit before touching anything

- [x] 1.1 Re-run the consumer audit for `canonical_name` and `version` across backends, capabilities, CLI, export/import and the generated clients. Record the result; do not trust the proposal's summary.
- [x] 1.2 Confirm `add-import-conflict-resolution` is merged and duplicates are handled, since this change removes the old handling. *Satisfied by stacking instead: this change sits on top of PR #2876, so the conflict handling is present in its base and the stack enforces the merge order.*
- [x] 1.3 Agree the renaming scheme with the developer.

## 2. Migrate existing alternate versions

- [x] 2.1 Write the migration: rename each alternate version to a distinct, non-colliding name in its folder; leave content, identifiers and folder membership untouched; clear the versioning fields.
- [x] 2.2 Make it idempotent and re-runnable, and test resuming it after a partial run.
- [x] 2.3 Test on a seeded corpus containing base documents with and without alternate versions, and folders where the obvious new name would collide.
- [x] 2.4 Verify no document is deleted and none becomes unreachable.

## 3. Remove the import half

- [x] 3.1 Remove the versioning assignment from the import path, and the corpus scan it performs.
- [x] 3.2 Remove or rewrite the tests asserting version assignment, deliberately rather than adjusting them to keep passing.

## 4. Remove the deletion half

- [x] 4.1 Remove alternate-version promotion from the deletion path, and the corpus scan it performs.
- [x] 4.2 Remove the tests asserting promotion on deletion. *One test named it; it only stubbed the promotion out to get past it, so the stub went with the function rather than being kept alive.*
- [ ] 4.3 Measure deletion cost before and after on a seeded corpus; record the figures on #2844 without closing it. *Measured — see verification.md. The comment on #2844 is written but NOT posted: waiting on the developer, who has a standing rule against publishing without an explicit ask.*

## 5. Remove the fields

- [x] 5.1 Remove `canonical_name` and `version` from the document identity.
- [x] 5.2 Regenerate the Knowledge Flow OpenAPI and the frontend client in this change.
- [x] 5.3 Check that nothing in the frontend read them.

## 6. Verify and close out

- [x] 6.1 `make code-quality` and `make test` in knowledge-flow-backend, fred-core and frontend.
- [x] 6.2 Run `/code-review` on the diff. *Three findings, all real, all fixed — see verification.md.*
- [x] 6.3 Document the duplicate rule in `docs/swift/design/INGESTION.md`, which has never described it.
- [x] 6.4 Migration note: data migration, operator-visible, with what to check afterwards.
