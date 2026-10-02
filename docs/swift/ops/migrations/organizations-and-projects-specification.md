---
schema: 1
title: "Specify organizations and projects (RFC and OpenSpec changes only)"
impact: none
configuration: none
configuration_reason: "Adds an RFC and two OpenSpec changes under docs/ and openspec/; no code, configuration key or default changes."
no_action_reason: "Specification documents only; nothing deployed reads them, so a normal deployment is unaffected."
---
## Applicability

Existing Fred deployments upgrading to this release.

## Prerequisites

No additional prerequisites beyond the normal deployment procedure.

## Configuration

No configuration changes are required.

## Upgrade

Deploy Fred normally; no additional operator or user action is required.

## Validation

`openspec validate platform-type-and-explicit-team-kind --strict` and `openspec validate explicit-organization-and-org-admin --strict` both report the change as valid.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

The specified changes, once implemented, will require operator action (a new required organization setting); their own PRs carry that note.
