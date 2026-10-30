---
schema: 1
title: "Knowledge-flow image rebuilds when the Weaver OpenFGA model changes"
impact: none
configuration: none
configuration_reason: "Changes only which pull requests rebuild the knowledge-flow image in CI; no runtime configuration key or default changes."
no_action_reason: "CI and local tooling only: published images, charts and deployed services are unchanged."
---
## Applicability

Contributors and CI on the weaver branch; deployed Fred 5.x environments are not affected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

No operator action is required. A pull request that changes
`apps/control-plane/openfga/model.json` now rebuilds the knowledge-flow images, which
embed that model. The root `make code-quality` also runs `make docker-images-tests`.

## Validation

`make docker-images-tests` passes, and the `docker-images / Resolve image matrix` check
succeeds on pull requests to weaver.

## Rollback

Revert the change; no data or deployment state depends on it.

## Limitations

The check covers the knowledge-flow production Dockerfile only, the one image built
selectively in pull requests; other images are always built.
