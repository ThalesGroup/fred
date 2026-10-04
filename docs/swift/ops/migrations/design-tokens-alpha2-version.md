---
schema: 1
title: "Prepare @fred-oss/design-tokens 0.1.0-alpha.2 with the reworked surface tokens"
impact: none
configuration: none
configuration_reason: "Only the version and changelog of the design-tokens npm package change; no Fred configuration key or default changes."
no_action_reason: "Fred deployments do not consume the npm package; publishing it is a separate maintainer action."
---

## Applicability

Existing Fred deployments upgrading to this release. Teams that build UI on
`@fred-oss/design-tokens` are affected only once `0.1.0-alpha.2` is published.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

When `0.1.0-alpha.2` is published, teams that consume the package apply the
"Token migrations" section of `libs/frontend/design-tokens/README.md`: some
tokens were removed (for example `--outline-retreat` and the `--color-*`
aliases).

## Validation

`libs/frontend/design-tokens/package.json` reads `0.1.0-alpha.2` and its
`CHANGELOG.md` has a matching approved entry.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

This change does not publish the package. `@fred-oss/ui` keeps its peer range
until the tokens are published and its compatibility baseline is updated.
