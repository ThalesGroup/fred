## 1. Identifiable bulk exceptions

- [x] 1.1 Add generated identity fields and name search, remove product bulk cap, implement atomic bounded SQL batches and reuse member columns; remove import jargon.
- [x] 1.2 Verify large/duplicate lists, later-batch rollback, source preservation, non-admin refusal and selection across paging.

## 2. Reviewed activation

- [x] 2.1 Support independent-source-only activation with configured-source availability and unchanged actor/legacy/revocation safeguards.
- [x] 2.2 Add read-only bounded-concurrency population classification, counts/time/revision, and floating action plus shared confirmation dialog across tabs.
- [x] 2.3 Verify missing/stale/conflicted evidence, live independent sources, cancellation, stale revision, errors and no implicit draft save using targeted regressions and real users.

## 3. Delivery

- [x] 3.1 Regenerate API client, reconcile existing docs, run grouped root quality and obtain read-only author/independent review; resolve findings.
- [x] 3.2 Commit user selection and activation separately, record safe screenshots/evidence and sync/archive verified capability requirements.

Verification: 54 control-plane admission/ownership tests pass with isolated PostgreSQL, including atomic 1001-user grants and late-batch rollback, stale activation revision, fresh/uncertain/suspended classifications and live membership. Seventy shared admission tests pass. Fresh Alembic upgrade, downgrade/upgrade and schema check pass with no new operations. Real-account Playwright confirms member identity columns and a saved-policy dry run with 1 allowed, 1 blocked and 4 uncertain accounts; cancel sends no activation. The preview does not inspect other users' full tokens, save a draft or guarantee future admission. Bounded independent review covered this delta and live-source revocation; production multi-replica load remains excluded.

Final local verification: root `make code-quality` passes across all modules. Fifty-eight focused frontend tests, seventy shared admission tests and fifty-four control-plane tests with PostgreSQL pass; the population projection typing correction passes its three targeted regressions. The packed UI consumer and full browser smoke pass, including the shared Dialog child-scroll contract. Fresh migration upgrade/downgrade/upgrade and Alembic schema check pass. Generated clients were produced through the existing OpenAPI/RTK toolchain; intermediate clients preserve coherent separate commits. Independent full branch review covered base `05a773919` and head `2ce04bf27` plus all working implementation, contracts and safe screenshots. Its incorrect route/error wording finding was corrected and replayed; no supported production findings remain. Author review covers the same full scope plus final typing correction. Production load, private overlays and external SDK deployments remain excluded. Final GitHub CI/mergeability and bot discussions remain tracked in PR #2966.
