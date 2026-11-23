---
schema: 1
title: "Centralize the exact Node baseline in .nvmrc"
impact: none
configuration: local
configuration_reason: "Developer tooling, CI and build-image Node selection read .nvmrc; deployed configuration keys and chart values are unaffected."
no_action_reason: "Node is used during frontend builds; the deployed nginx runtime requires no extra upgrade operation."
---

## Applicability

Developers, frontend CI and build-image preparation. The exact Node baseline is
24.22.2, selected after reviewing the October 2026 Node 24 security fixes.

## Prerequisites

Run nvm install from the repository to install the exact version selected by
.nvmrc. Release preparation continues to require npm 11.19.0. Without nvm,
ordinary development still accepts the existing >=24.21.0 <25 engine range.

## Configuration

The frontend task loads nvm from NVM_DIR, defaulting to ~/.nvm, when present.
Make, CI and active build-image entry points consume the root .nvmrc. Local
frontend image builds should use make docker-build, which passes NODE_VERSION.
Direct docker build calls must pass --build-arg NODE_VERSION="$(cat .nvmrc)".
Devcontainer initialization generates its ignored build Dockerfile from the pin.

## Upgrade

Deploy Fred normally; no operator action is required. Developers install the
pinned version once and relaunch their tasks. Regenerate new release archives
and evidence with the selected exact toolchain; retain historical records.

## Validation

Launch the frontend task with an older Node version inherited from the IDE and
confirm it selects 24.22.2. Check that CI/build arguments agree with .nvmrc and
that release preparation rejects a divergent current toolchain policy.

## Rollback

Revert the coherent tooling change and regenerate any new candidate evidence
under the restored toolchain. Existing deployment rollback remains unchanged.

## Limitations

The task does not install Node or nvm automatically. Selecting a patched Node
version does not assert that the complete Docker image has zero known CVEs.
No data migration or runtime scaling behavior changes are introduced.
