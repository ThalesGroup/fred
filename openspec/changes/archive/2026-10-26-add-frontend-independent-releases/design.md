## Context

The producer already has package-specific builders, archive validators, isolated consumers, browser/host checks, exact-version registry reads, and a registered package inventory. Publication is currently implemented separately in a GitHub-only workflow through retained candidate, attempt, terminal, and outcome artifacts. Issue #3281 keeps the validation assets but replaces that orchestration.

The implementation must remain useful from a local terminal and from CI, must not publish or promote during tests, and must keep the three package versions independent. A prepared archive identifies a Git commit truthfully, so real preparation requires a clean committed checkout; controlled disposable repositories cover that guard while this requested implementation remains uncommitted.

## Goals / Non-Goals

**Goals:**

- One implementation behind four Make targets, with one package per invocation.
- A portable directory whose metadata is generated automatically and whose tarball is never rebuilt during publish or verify.
- Explicit local, CI-token, and GitHub OIDC authentication modes with truthful provenance behavior.
- Deterministic idempotency, conflict detection, bounded visibility reads, and an actionable uncertain state.
- A thin GitHub adapter with a protected publication job and simple operation/package inputs.

**Non-Goals:**

- Publishing a package, changing a dist-tag, changing package versions, or configuring npm Trusted Publishers in this change.
- Migrating the repository to GitLab, adding a second CI release engine, changing Python releases, or repairing #3278 history.
- Removing package/archive/consumer validation used by pull-request CI.

## Decisions

### 1. A release directory is the complete handoff contract

Preparation writes one selected tarball and `release.json` to either `target/releases/<package>/<version>` or an explicit `RELEASE_DIR`. Metadata contains only schema version, stable package selector, npm name, manifest version, source commit, archive filename, and SHA-512 integrity. All later operations validate exact keys, manifest identity, contained paths, and bytes before registry access.

This replaces operator-supplied JSON and GitHub run history. A richer attempt ledger was rejected because it recreates the system being removed; publication writes at most one small outcome file beside the prepared release.

### 2. Preparation reuses package-specific checks

The shared dispatcher maps the stable selectors to existing builders, archive validators, and applicable isolated consumer/browser/host checks. It builds only the selected member. UI preparation resolves its manifest's design-token peer against exact published versions and fails with a publish-tokens-first instruction when no compatible version is available. iframe-sdk never selects UI or token publication.

Preparation requires a clean committed checkout and records `HEAD`. This prevents metadata from claiming that uncommitted source was the recorded commit. The implementation checkout therefore demonstrates actual selected pack/archive checks and uses disposable clean repositories for the preparation guard and metadata behavior.

### 3. Registry preflight controls idempotency

Publish first validates the local release, then performs one exact-version read. Matching registry integrity is success without npm mutation; different integrity is a conflict; only a definite 404 authorizes one publish command. Authentication, authorization, malformed responses, redirects, timeouts, and network errors are distinct failures rather than absence.

After npm accepts the command, bounded exact-version reads may wait for visibility. Exhausted 404s or a failed npm process are reported as uncertain with the exact `make verify-release` command. They never cause an automatic second upload.

### 4. Authentication and provenance are explicit

Local mode uses the operator's normal npm configuration and interactive authorization and does not request CI provenance. CI token mode requires `NODE_AUTH_TOKEN`. GitHub OIDC mode requires GitHub Actions/OIDC execution identity and requests provenance. Modes do not silently fall back to each other. Every npm mutation includes `--ignore-scripts` so package lifecycle scripts cannot rebuild or alter the prepared release.

Local mutations inherit the operator terminal. Token and OIDC mutations use temporary,
mode-specific npm user configuration: token mode scopes `NODE_AUTH_TOKEN` to the selected
registry, while OIDC mode removes token configuration. Non-OIDC publication explicitly
overrides package manifest provenance defaults. Mixed credential modes fail before npm.

Dry runs perform all local validation and read-only dependency/preflight checks but call no npm mutation command.

### 5. Promotion is independent

Promotion takes an explicit version and channel, verifies the exact version exists, and only then performs `npm dist-tag add`. It never prepares or publishes. Its dry run stops before tag mutation.

### 6. GitHub retains transfer, approval, and authentication only

The existing workflow filename is preserved. `prepare` checks out the requested committed source, invokes `make prepare-release`, and uploads the resulting directory. `publish` downloads one explicitly selected preparation artifact/run, invokes `make publish` inside the `npm-publish` environment with OIDC permissions, and serializes by package. `verify` and `promote` invoke their matching Make targets; only mutation jobs receive credentials or `id-token: write`.

GitHub artifact lookup remains workflow adapter code. Shared scripts never call GitHub APIs, so GitLab CI can transfer the same directory and invoke the same commands.

## Risks / Trade-offs

- [A dirty checkout cannot produce commit-bound release metadata] -> fail before packing; use actual archive checks plus disposable clean fixtures during this uncommitted implementation review.
- [Registry visibility can lag an accepted upload] -> bounded reads end in an uncertain outcome and an explicit verification command, never automatic republish.
- [Local and CI authentication differ] -> require a named mode and test each with controlled command substitutes.
- [Removing large recovery helpers can break validation callers] -> search callers first and retain record/evidence modules still used by fixture and pull-request checks.
- [UI peer resolution requires registry availability] -> use bounded read-only requests and report authentication/network failures separately from no compatible version.

## Migration Plan

1. Add and test the shared release dispatcher and public Make targets.
2. Convert the existing workflow to the thin adapter while preserving its filename and environment boundary.
3. Remove only helpers and tests whose remaining callers belonged to the obsolete workflow/history path; update CI input selection.
4. Replace the runbook with the local/CI walkthrough and add the required migration note.
5. Run focused mutation-substitute tests, actual archive builds, quality checks, workflow validation, OpenSpec validation, and branch review.

Rollback restores the previous workflow and helpers. Published npm versions and dist-tags are unaffected because this implementation performs no real mutation.
