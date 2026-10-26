## 1. Shared release implementation

- [x] 1.1 Add one package selector and portable release-directory contract for `design-tokens`, `ui`, and `iframe-sdk`; verify valid/invalid selection, manifest-derived versions, clean-source commit binding, exact metadata, explicit output paths, and altered/inconsistent output rejection with controlled tests.
- [x] 1.2 Reuse selected package builders, archive validators, and applicable consumer/browser/host checks without building unrelated packages; verify package-specific dispatch and actual archive creation for all three packages.
- [x] 1.3 Validate UI's declared design-token peer against compatible exact published versions while keeping iframe-sdk independent; verify compatible, unavailable, malformed, unauthorized, and network-error cases with a controlled registry.

## 2. Publication, verification, and promotion

- [x] 2.1 Implement exact-byte publication preflight and upload with `next` default, lifecycle scripts disabled, matching-version idempotency, conflicting-version rejection, and no rebuild; verify every mutation through command substitutes.
- [x] 2.2 Implement bounded post-upload visibility checks and small success/uncertain outcome records; verify delayed visibility, exhausted 404, ambiguous upload, actionable verification output, and no automatic second upload.
- [x] 2.3 Implement explicit local, CI-token, and GitHub OIDC authentication behavior with truthful provenance; verify missing/mixed credential modes fail and local mode never claims CI provenance.
- [x] 2.4 Implement exact registry verification and separate version/channel promotion, including dry runs; verify absence/auth/network/conflict handling and prove dry runs invoke no mutation.
- [x] 2.5 Expose and test `prepare-release`, `publish`, `verify-release`, and `promote` Make targets with sensible defaults and `RELEASE_DIR` transfer support.

## 3. CI simplification and cleanup

- [x] 3.1 Rewrite `.github/workflows/Publish-frontend-packages.yml` as a thin adapter around the Make targets, preserving filename, `npm-publish`, per-package serialization, scoped credentials, artifact transfer, and optional run selection; validate workflow structure locally.
- [x] 3.2 Remove manual candidate/attempt/terminal inputs and obsolete artifact-history, attempt, terminal, summary, and recovery helpers/tests after caller checks; preserve fixture transfer, packaging, consumers, registry primitives, and pull-request selection.
- [x] 3.3 Update release-input selection and workflow-contract tests so changes to the shared release implementation select the right CI jobs without relying on deleted machinery.

## 4. Documentation and migration

- [x] 4.1 Replace `libs/frontend/RELEASE.md` with prerequisites, fresh-clone local walkthrough, explicit authentication/provenance modes, dry runs, transfer, retries, promotion, rollback, and the equivalent CI flow; verify every documented command matches Make help.
- [x] 4.2 Update `libs/frontend/README.md`, Make help, and the required issue #3281 migration note; verify repository links and migration schema checks.

## 5. Verification and review

- [x] 5.1 Run focused release tests, formatting/lint, producer tests, package archive checks, applicable isolated consumers/browser/host checks, workflow validation, migration checks, and strict OpenSpec validation; separate fixture evidence, actual archive builds, and unexercised real mutation paths.
- [x] 5.2 Apply the branch-audit procedure against `origin/swift`, including unstaged/untracked files, and obtain an independent read-only review; fix in-scope findings and record reviewed base/head, verification, dispositions, and exclusions.
- [x] 5.3 Reconcile the final implementation with proposal, design, delta spec, tasks, and the main capability spec without publishing, promoting, committing, pushing, or writing to GitHub.
