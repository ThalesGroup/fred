## Why

Frontend publication run `39955383905` retained its exact pre-command attempt and then failed before `executeOrdinaryPublication` because the repository-wide GitHub artifact count changed from 9936 to 9937 during pagination. The fail-closed check prevented an unsafe publish, but it also left no terminal artifact, so the untouched iframe SDK cannot be retried unless the listing race is corrected and this one pre-command abort is established from stronger evidence than a missing terminal.

## What Changes

- Make retained-attempt discovery tolerate concurrent unrelated GitHub artifact additions by retrying a complete repository artifact scan from page one, discarding every unstable partial scan, and accepting history only after a bounded stable count and artifact-ID snapshot is observed.
- Keep history verification fail-closed for retry exhaustion, duplicate or missing IDs, expired or unavailable attempt artifacts, omitted manual references, unresolved publishing executions, and cross-candidate coordinate reuse.
- Add one source-reviewed exception for the exact pre-command abort from run `39955383905`, attempt `1`, publish job `120419935080`, bound to attempt artifact `12502631030`, its ZIP and record digests, source commit, candidate, selected members, and independently checked GitHub run/job/step evidence. No other missing terminal is accepted by inference.
- Ensure a future failure after the current attempt is durably retained but before the first package command writes an aborted terminal that explicitly marks every selected member as never invoked, so normal terminal verification handles later continuations.
- Add controlled regressions for artifact count/ID drift, bounded retry exhaustion, incomplete or forged history, exact incident-evidence mismatches, future pre-command terminal retention, and zero npm invocation during either history recovery or incident reconciliation.
- Document the recovery procedure and no-deployment-impact migration note. This change does not dispatch the workflow, publish to npm, create a fresh candidate, or alter the retained release identities.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: Refine evidence-bound partial-publication recovery so unrelated repository artifact churn cannot invalidate a complete retained-attempt history, while allowing only the exact independently proven `39955383905/1` pre-command abort to substitute for its missing terminal and requiring explicit terminal evidence for future pre-command failures.

## Impact

- Release evidence and publisher control flow: `libs/frontend/scripts/release-artifact.mjs`, `libs/frontend/scripts/release-publisher.mjs`, and, only if needed for a source-reviewed incident record, the existing `libs/frontend/release/` policy/schema surface.
- Workflow contract: `.github/workflows/Publish-frontend-packages.yml` retains the sole publication step and terminal upload path; changes are limited to ensuring pre-command terminal output is available on failure.
- Tests: `libs/frontend/tests/release-publisher.test.mjs` and `libs/frontend/tests/ci-selection.test.mjs`, plus an existing release-policy/schema test if the incident proof is stored as reviewed data.
- Documentation: `libs/frontend/RELEASE.md` and a PR migration note under `docs/swift/ops/migrations/`; the broader frontend packaging RFC remains unchanged because this is a scoped recovery correction, not a new open design question.
- Tracking: [GitHub issue #3278](https://github.com/ThalesGroup/fred/issues/3278). The original candidate and four attempt references remain authoritative, as do the original three terminal references.
