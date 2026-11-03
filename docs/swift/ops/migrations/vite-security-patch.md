---
schema: 1
title: "Patch Vite in frontend tooling and isolated consumers"
impact: none
configuration: none
configuration_reason: "Only frontend development and build dependencies change; deployed configuration and Helm values are unchanged."
no_action_reason: "The patched Vite version is installed by the normal locked build; deployments require no additional steps."
---
## Applicability

Frontend application builds, shared frontend package builds and isolated consumers.

## Prerequisites

No additional prerequisites beyond the supported Node/npm toolchain.

## Configuration

No configuration changes are required.

## Upgrade

Use the normal locked installation and build procedure.

## Validation

Confirm that the application, producer and isolated consumers resolve Vite 6.4.5
and that their existing build, quality and test checks pass.

## Rollback

Revert the dependency update and rebuild using the previous lockfiles.

## Limitations

This update addresses GHSA-8g5g-mxqh-grgj only. Other frontend dependency
updates are tracked separately, including Dependabot PR #3298.
