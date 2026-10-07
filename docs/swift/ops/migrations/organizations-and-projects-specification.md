---
schema: 1
title: "Specify the organizations and projects target model (RFC only)"
impact: none
configuration: none
configuration_reason: "Adds an RFC under docs/swift/rfc/; no code, configuration key or default changes."
no_action_reason: "A design document only; nothing deployed reads it, so a normal deployment is unaffected."
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

`docs/swift/rfc/ORGANIZATIONS-AND-PROJECTS-RFC.md` is present and renders on GitHub.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

Migration toward this target is specified separately; its PRs carry their own notes.
