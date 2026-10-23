## 1. Stabilize retained-attempt enumeration

- [ ] 1.1 Extract a metadata-only repository artifact snapshot helper in `libs/frontend/scripts/release-artifact.mjs` that starts from page one, enforces one count per pass, full pagination, unique IDs, exact final cardinality, and the existing 100-page bound; verify focused unit fixtures reject count drift, duplicate IDs, short pages, and count/cardinality mismatches without downloading attempt ZIPs.
- [ ] 1.2 Require two consecutive snapshots with identical counts and ID sets within at most three complete attempts, discarding all state from a drifted pass; verify controlled count-drift and same-count ID-drift fixtures restart from page one and later return each retained attempt exactly once.
- [ ] 1.3 Run attempt ZIP, manual-reference, expiry, cross-candidate, visible-run, and workflow-history validation only after snapshot stability; verify the existing incomplete-history negatives still fail closed and an injected npm command counter remains zero on every enumeration failure.

## 2. Verify the exact historical pre-command abort

- [ ] 2.1 Add a narrowly scoped schema-validated reviewed-abort evidence file under `libs/frontend/release/` containing only the exact #3278 candidate, attempt `12502631030`, source, run/attempt, job, step, digest, log-signature, and selected-member bindings; verify schema/policy tests reject omitted, additional, malformed, or altered fields without changing the retained candidate's policy digest.
- [ ] 2.2 Implement independent verification of the reviewed abort against the already verified candidate and attempt plus GitHub's exact attempt-specific run/job/step response and job log; verify controlled fixtures reject wrong or unavailable artifact IDs/digests, source commits, candidate bindings, run attempts, job IDs, step order/outcomes, log signatures, and selected members.
- [ ] 2.3 Feed only the verified #3278 boundary into absence reconciliation as distinct reviewed proof, not as a fabricated retained terminal; verify the exact fixture permits the untouched selection with all four attempts and original three terminals, performs no npm invocation during reconciliation, and every other missing-terminal case remains blocked.

## 3. Retain future pre-command terminal evidence

- [ ] 3.1 Refactor the publisher's terminal writer so failures after current-attempt readback but before ordinary publication write an empty-prefix terminal and rethrow, while failures before current-attempt trust write no terminal; verify generated records bind the exact candidate/attempt/execution and place every selected member in `neverInvoked`.
- [ ] 3.2 Extend `executeOrdinaryPublication` terminal coverage to all validations before and between commands without overlapping the outer pre-command catch; verify failures before the first command retain an all-never-invoked terminal, failures after a command retain the actual serialized prefix/possibly-invoked set, terminal-write failures never fall back to a false empty prefix, and npm invocation counts match the boundary.
- [ ] 3.3 Preserve the single workflow execution step followed by the failure-only terminal upload in `.github/workflows/Publish-frontend-packages.yml`; verify `libs/frontend/tests/ci-selection.test.mjs` proves ordering, one publication path, and no later command path after terminal creation.

## 4. Document the recovery boundary

- [ ] 4.1 Update `libs/frontend/RELEASE.md` with the exact `39955383905/1` evidence, the stable-snapshot behavior, the original candidate, all four attempt refs, the original three terminal refs, and the instruction not to rerun job `120419935080`; verify every recorded identity and digest matches issue #3278 and the retained run log.
- [ ] 4.2 Add an English `impact: none` migration note under `docs/swift/ops/migrations/` explaining that normal deployment is sufficient and that any later protected dispatch is a separate maintainer action; verify it with `make migration-check` from the repository root.

## 5. Validate and review the implementation

- [ ] 5.1 Run the focused producer regressions with the pinned frontend release toolchain using `node --test tests/release-publisher.test.mjs tests/ci-selection.test.mjs` from `libs/frontend`; record the exact pass counts and confirm no test reaches the public registry or executes `npm publish`.
- [ ] 5.2 Run `make release-check release-test code-quality test` from `libs/frontend`, then `openspec validate recover-frontend-artifact-listing-race --strict`, `openspec validate --all --strict`, `make migration-check`, and `git diff --check` from the repository root; fix every failure and record exact results in the existing task/PR response.
- [ ] 5.3 Apply the repository branch-audit procedure against the actual `origin/swift` base and obtain an independent read-only review of the full non-trivial concurrency/recovery diff; record base/head, reviewed files and consumers, findings and dispositions, verification, and exclusions without dispatching a workflow or publishing to npm.
- [ ] 5.4 Reconcile proposal, design, tasks, and delta spec with the final implementation and verification evidence; leave the protected recovery dispatch, public npm verification, spec sync, and archive for separately authorized post-merge work.
