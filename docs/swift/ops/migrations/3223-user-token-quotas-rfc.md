---
schema: 1
title: "Propose per-user usage quotas with credit gauges (RFC only)"
impact: none
configuration: none
configuration_reason: "Adds a design RFC under docs/swift/rfc/ and its README entry; no configuration keys, defaults or chart values change."
no_action_reason: "Documentation only: no code, data, API or deployment behavior changes, so a normal deployment is enough."
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

Open docs/swift/rfc/USER-TOKEN-QUOTAS-RFC.md and check that it is listed in docs/swift/README.md.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.

## Limitations

No additional migration limitations identified for this change.
