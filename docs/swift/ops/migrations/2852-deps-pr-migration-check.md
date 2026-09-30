---
schema: 1
title: "Skip migration notes CI for Dependabot and stop commit-tagged dev images"
impact: none
configuration: none
configuration_reason: "Only GitHub Actions workflows change; Fred configuration is unaffected."
no_action_reason: "The workflow changes do not alter deployed code, data or APIs."
---
## Applicability

Fred maintainers reviewing pull requests and publishing development images after this change is merged.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

A pull request opened by `dependabot[bot]` skips the Migration notes job. Other pull requests and merge groups still run it. Swift branch images receive the `swift-dev` tag without a commit-specific tag.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
