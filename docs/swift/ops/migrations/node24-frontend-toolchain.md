---
schema: 1
after: [chat-active-turn-steering]
title: "Require Node 24 for frontend builds and package consumers"
impact: minor
configuration: none
configuration_reason: "Only frontend build/development tooling and npm engine contracts change; deployed nginx settings and Helm configuration are unchanged."
---

## Applicability

Frontend source builds, development containers, CI and consumers of the shared frontend npm packages.

## Prerequisites

Install the exact Node version in `.nvmrc` (24.22.2 for this release) and npm 11.19.0. The supported Node range is >=24.21.0 <25; Node 22 and Node 25 or newer are unsupported. Release preparation retains exact Node/npm pins.

## Configuration

No deployment configuration changes are required. Custom build environments must use the supported tooling before installing dependencies.

## Upgrade

Upgrade custom builders and local Node installations, then reinstall with `npm ci` in the affected frontend workspace. Rebuild existing development containers. Official frontend images include the updated builder; their deployed nginx runtime is unchanged.

## Validation

Check `node --version` and `npm --version`, then run the normal frontend build/tests and package consumer validation. Unsupported Node versions must fail before installation or build, including with an existing dependency tree.

## Rollback

Revert the toolchain change together with its manifests, lock metadata and contracts. Node 22 cannot validate dependency updates that require newer Node APIs, so revert those updates as well if restoring the previous toolchain.

## Limitations

This change publishes no npm packages or release tags. Previously built browser assets and persisted data require no migration. Consumers install Node 24 before adopting packages with the new engine contract.
