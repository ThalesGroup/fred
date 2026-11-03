## Why

Routine frontend npm releases are coupled to GitHub artifact history, manual JSON references, and incident-recovery state. That complexity blocked publication before npm ran and prevents the same release operation from being used naturally from a terminal or another CI provider.

## What Changes

- Provide one shared Make interface under `libs/frontend` to prepare, publish, verify, and promote exactly one of `design-tokens`, `ui`, or `iframe-sdk`.
- Prepare a portable release directory containing the validated tarball and generated package, version, source-commit, and SHA-512 metadata.
- Publish only those prepared bytes, default to `next`, make local and CI authentication explicit, and treat matching existing bytes as success and different bytes as a conflict.
- Add bounded read-only visibility checks, actionable uncertain outcomes, dry runs, and separate promotion after exact-version existence checks.
- Validate UI's declared design-token peer against an available compatible published version while keeping iframe-sdk independent.
- Reduce the existing GitHub workflow to artifact transfer and the same Make commands, preserving the workflow filename, protected `npm-publish` boundary, credential isolation, and per-package serialization.
- Remove manual candidate/attempt/terminal references, repository-wide artifact-history recovery, and the obsolete release-attempt machinery while preserving archive, consumer, and pull-request validation.
- Update the operator runbook and migration note for issue #3281. This change does not publish packages, change versions, or modify npm/GitHub configuration.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `frontend-package-archives`: Replace artifact-history-driven publication and recovery with a portable one-package release directory and shared local/CI commands.

## Impact

- Release implementation and tests in `libs/frontend`, including the Makefile, package scripts, registry handling, and release documentation.
- `.github/workflows/Publish-frontend-packages.yml` remains the GitHub adapter but no longer implements the release engine.
- Obsolete GitHub artifact-reference, publishing-attempt, terminal-history, and summary helpers/tests are removed after caller checks.
- Pull-request packaging, isolated-consumer, browser, host, and fixture-transfer validation remain available.
- Tracking: [#3281](https://github.com/ThalesGroup/fred/issues/3281). It supersedes the #3278 incident-repair approach without changing historical published versions.
