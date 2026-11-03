---
schema: 1
title: "Run the frontend unit test suite on pull requests"
impact: none
configuration: none
configuration_reason: "Only the pull-request CI workflow changes; no application code, image, chart value or configuration file is touched."
no_action_reason: "The change adds a CI check on pull requests; deployed Fred components are identical before and after."
---

## Applicability

Contributors opening pull requests that touch `apps/frontend`. Deployed Fred
instances are not affected.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

On a pull request touching `apps/frontend`, the check
`Code Quality - frontend - test` runs `make test` and fails when a frontend
unit test fails.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
