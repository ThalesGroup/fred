## 1. Contract and typed foundation

- [x] 1.1 Confirm the proposed authority/defaults and establish the implementation issue linked to #3092; record the approved scope and issue in this change before implementation.
- [x] 1.2 Add validated policy/configuration types and sample catalog, including defaults, unknown fields, duration overflow, precedence and immediate-mode tests; prove omitted lifecycle configuration preserves existing startup and disables new deletion requests.
- [x] 1.3 Add the new SQL migration for requests/retirement markers and indexed candidate selection; verify fresh and existing-schema upgrades, target-independent receipts, uniqueness and atomic progress updates on disposable PostgreSQL.
- [x] 1.4 Add `can_delete_space` in the OpenFGA model and typed probe, regenerate the model and extend exact additive publication compatibility; verify platform-owner permission and refusal for every other role, including upgrades from both supported prior models.

## 2. Acceptance and isolation

- [x] 2.1 Implement authenticated DELETE/status handlers with stable receipts, frozen policy, complete subtree discovery and platform-then-organization locking; test lost responses, overlap in both directions, authorization revocation while waiting, and rollback before retirement commit.
- [x] 2.2 Gate all existing resource/probe/mutation/provisioning/personal-space consumers on retirement and preserve unique-organization attachment from remaining direct roles; test concurrent create/import/grant and partial FGA-link removal without missing-link failures, slot reuse or missed ancestor overlap, using the receipt's root-parent snapshot.
- [x] 2.3 Refuse document-bearing scopes atomically and preserve accounts/consent/platform roles; cover root and descendant documents, personal descendants and unrelated organizations, marking invariant tests with `// Proves: I<n>`.
- [x] 2.4 Regenerate the manager OpenAPI/RTK client without UI changes; verify operation coverage, response/status typing and no accidental frontend behavior changes.

## 3. Cleanup and Temporal worker

- [x] 3.1 Implement bounded SQL folder batches and model-filtered FGA tuple cleanup with fresh-page draining, metadata-last deletion and organization-guard finalization; inject failures/ambiguous acknowledgments at each store boundary and prove replay after the final guard disappears.
- [x] 3.2 Add typed Temporal workflow/activities, bounded retries, fair candidate selection, safe progress/errors and completion receipts; test future due times, exhausted candidates, blocked state recovery and late activities after UUID replacement.
- [x] 3.3 Add the separate worker command, explicit dependency bootstrap, graceful shutdown, readiness and idempotent schedule reconciliation; verify real Temporal execution/replay, two worker startups, disabled lifecycle and namespace/queue isolation on disposable services.
- [x] 3.4 Extend the existing logger with a worker service role and acceptance/completion audit events; verify partial failure emits no completion claim and neither logs nor Temporal payloads contain credentials, raw dependency errors or canonical grants.
- [x] 3.5 Add Make/deployment/configuration mounts for API and worker using the existing manager image/overlay; render/lint manifests, verify disabled defaults, worker registration/readiness and the all-producers-upgraded activation barrier; test that worker startup cannot bootstrap or silently change the published authorization model.

## 4. Review, evidence and documentation

- [x] 4.1 Run the end-to-end API-to-worker journey against disposable PostgreSQL, OpenFGA and Temporal with short retention; prove restart recovery, complete target cleanup and untouched out-of-scope state.
- [x] 4.2 Measure and assert request filters/counts, maximum batch size and SQL lock boundaries using multi-page tuples, >1000 folders, unrelated organization growth and 1/8 concurrent actors; record fixture sizes, timings and observed limits here and in arc42 quality.
- [x] 4.3 Apply the branch audit and obtain independent authority/recovery/deployment review; fix actionable findings with regression tests and have corrections reviewed, recording reviewed base/head and dispositions here.
- [x] 4.4 Perform the dedicated arc42 pass: update 02-user-journeys, 03-security, 03a-action-role-matrix, 04-organizations, 08-operations, 09-quality and A1/A2/A3 manager references as applicable; regenerate derived blocks, add the two-phase activation/rollback note including SQL and FGA publication incompatibility with older binaries, and check all described behavior against the implementation.
- [x] 4.5 Run manager `make test`, `make test-integration`, `make code-quality`, root `make code-quality`, `make -C docs/architecture check`, the targeted Temporal suite and strict OpenSpec validation; retain exact results in this task file.
- [x] 4.6 Reconcile/sync/archive the completed change using the archive procedure and commit one reviewed implementation lot with its architecture updates; push only with explicit developer agreement for this lot.

## Planning review

- Base/head: `ec26cc51b114430c46380fec0a160464bec3d6c4`; reviewed the uncommitted proposal, design, delta specification and tasks against this source revision.
- Independent read-only reviewer: `review_deletion_design`. Coverage: authority, SQL/OpenFGA recovery, retirement consumers, Temporal scheduling, rollout and rollback contracts.
- Findings resolved: persist the deletion root's parent snapshot and consult receipts for reservations/overlap after FGA link removal; require disabled rollout until all producers understand retirement; document older model-publication incompatibility on rollback. The correction pass also reconciled the hierarchy specification with the operational snapshot.
- Corrections were reviewed; no outstanding planning findings. `openspec validate add-manager-space-deletion --strict` passes and all four planning artifacts are complete.
- Exclusions: no implementation, runtime tests, deployment or full-branch readiness review in this planning pass. Developer confirmation of authority, defaults and acceptance criteria was obtained before implementation.

Developer approved the complete proposed scope, platform-owner authority and P7D default on 2026-10-17. Implementation tracking: #3160 (follow-on to #3092).

## Implementation review and verification

- Implemented on `chore/rust-rebac` for #3160. Reviewed base/HEAD was
  `ec26cc51b114430c46380fec0a160464bec3d6c4` plus the working implementation.
  Actual branch target is `origin/swift`; merge-base is
  `e24856249275cede3447b5be18dcc854e2a460ff`.
- `review_space_deletion_impl` independently reviewed authority, retirement,
  SQL/FGA recovery and Temporal progress. Corrections restored the first-acceptance
  permission check, moved exhausted failure persistence into an activity, stamped
  candidate visits for fairness, preserved schedule CAS tokens, and bounded local
  activity/SQL execution and shutdown. Each correction was source-reviewed again.
  Failure/authority/concurrency regressions and the real Temporal suite pass.
- `audit_deletion_final` applied the branch audit to the complete branch inventory
  (246 committed files, approximately 35,000 added lines), deeply reviewed this
  lifecycle delta and consumers, and sampled earlier manager/frontend integration.
  Its supported finding was the k3d reset rejecting the new worker. The optional
  workload group, release/config classification, stop/restore and regression tests
  were corrected and re-reviewed. Later test/budget and audit-field corrections
  were independently reviewed with no remaining findings.
- Coverage limits: earlier authentication/provisioning implementations, reset
  storage internals, all browser interactions and historical specifications were
  not exhaustively re-audited. No live Kubernetes/reset run, browser/manual user
  test or production deployment was performed. This is a reviewed implementation
  lot, not an exhaustive new readiness approval of the entire historical branch.
- Manager `make test`: 40 unit tests and 5 OpenAPI tests pass. Manager
  `make test-integration`: 80 pass in 41.23 s; final targeted lifecycle rerun after
  strengthening the three concurrent mutation waiters: 7 pass in 0.82 s.
  Both model predecessor publication tests and populated-0006-to-0007 migration
  preservation pass. Manager `make code-quality`: model parity, rustfmt and
  Clippy all targets with denied warnings pass.
- `make test-lifecycle-temporal`: 1 pass in 24.95 s; real API, SQL, OpenFGA and separately spawned
  Rust workers verify retention, SIGKILL restart, history replay, schedule reuse,
  disabled schedule, SIGTERM during a held advisory lock, server wait release,
  exhausted retries and recovery. Logs use the existing `audit_event` contract,
  distinguish worker role, exclude private errors/tokens and omit premature completion.
- Root `make code-quality` passes all configured modules and migration-tool tests.
  `python3 -m unittest discover -s deploy/k3d -p 'test_reset*.py'`: 18 pass,
  one live-storage test skipped. Helm lint and template rendering pass for the
  dedicated manager overlay. `make migration-check MIGRATION_BASE=HEAD` validates
  the new migration declaration. Frontend RTK generation passes, with no UI edits.
- Arc42 dedicated final pass covers journeys, security and action-role matrix,
  organizations, operations, runtime, HTTP/schema contracts and quality. Generated
  schema/configuration/model/proof blocks were regenerated; `make -C
  docs/architecture check` passes, including every diagram render.
- Focused budget fixture: three spaces, 1001 folders, 243 target tuples and 241
  unrelated member tuples plus unrelated owner/admin grants. One acceptance:
  17.740 ms, four Reads, one Check, one Write. Six cleanup attempts including a
  lost FGA acknowledgment: 149 ms; combined 34 Reads, one Check, seven Writes,
  every Write <=100 operations. Eight concurrent receipt retries on two spaces:
  165 ms. Six lifecycle tests ran concurrently during this measurement. These
  service timings are not isolated lock-hold measurements or scalability claims;
  forced waiters prove locking boundaries. Arc42 records the exact filters and costs.
- Strict change validation passes. Delta sync modifies the two existing hierarchy
  and membership requirements, adds seven lifecycle requirements to the existing
  provisioning capability and preserves all prior scenarios. All 33 durable specs
  validate. The completed change is archived with the implementation commit.
  No push is authorized or performed for this lot.
